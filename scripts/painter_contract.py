#!/usr/bin/env python3
"""The painter's contract (M1-T02b of the guest-services-migration plan), from a shadow trace with
PR #12's 'P' region: cAPIGph_Painter (mDoGph_Painter), the first thing fpcM_Management does, which
draws the previous frame's lists into the GX stream.

Inside the painter nothing but the model calls dDlst_shadowReal_c::imageDraw makes reaches the edge
service (the draw functions are direct calls), so the trace shows a management as: P part 0 (the
retrace wait inside JFWDisplay::beginRender, the clear and the 2D copy), the imageDraw model calls
('J' regions with no process) with the painter's parts between them, the last of those model-call
regions running on to the painter's return, then the delete/create handlers (a gap of a few hundred
cycles) and the execute loop's first region. So: the painter = every record from P part 0 to the
first execute region; the wait = P part 0; the painter proper = the rest.

Per frame: the wait's and the painter proper's cycles; the proper's read lines, written words (by
symbol group: audio thread, OS, J3D/GX, heap by page), flags and hardware accesses; the interrupt
and DSP-step events inside each; and against the same management's later regions (the execute loop,
the draw loop): who reads a word the painter proper wrote (RAW: what a job must have committed before
that reader), who writes one (WAW: the merge at the join), and how much of what it read they rewrite
(WAR: the snapshot a job needs if the game thread writes in place). The painter's own stack and the
audio thread's stack are excluded from the sets.

usage: painter_contract.py TRACE --symbols SYMBOLS.txt --profiles f_pc_profile_lst.cpp [--exclude LO-HI]... [--top N]
"""
import argparse, bisect, re, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from j3d_contract_study import load_symbols, name_of, load_profiles, records, CALLS

FLAGS = {1 << 2: "hw-read", 1 << 3: "hw-write", 1 << 4: "alias", 1 << 5: "fallback", 1 << 6: "timer",
         1 << 7: "psq-fallback", 1 << 8: "dcbz", 1 << 9: "interrupt", 1 << 0: "read-overflow", 1 << 1: "write-overflow"}
GROUPS = [("audio thread", re.compile(r"^(JAS|JAI|JAU|sAudio|saAudio|DSP|__DSP|AI|AX|sAudioproc)")),
          ("OS", re.compile(r"^(OS|__OS|Run|Idle|Reschedule|mainThread|DvdErr|regs|shdw|changed|HorVer|Thread|__Thread|RunQueue)")),
          ("J3D / GX state", re.compile(r"J3D|j3dSys|gxData|^GX|^GD|^__GX|^__GD|sOldVcd|sMtxPtrTbl|sCurrent|sNBTFlag|sEnvelope|J2D|JUT")),
          ("dComIfG / dDlst / dKy", re.compile(r"dComIfG|dDlst|dKy|g_env_light|mDoGph|mDoMtx|mDoLib")),
          ("JPA (particles)", re.compile(r"JPA|dPa"))]

def pct(v, p):
    if not v: return 0
    s = sorted(v); return s[min(len(s) - 1, int(p * len(s)))]

def group_of(sym):
    if not sym: return "heap"
    for g, rx in GROUPS:
        if rx.search(sym): return g
    return "other named"

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("trace"); ap.add_argument("--symbols", required=True); ap.add_argument("--profiles", required=True)
    ap.add_argument("--exclude", action="append", default=["80408000-8040D000"])
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args(argv)
    table, starts = load_symbols(a.symbols); profiles = load_profiles(a.profiles)
    excl = [(int(lo, 16), int(hi, 16)) for lo, hi in (x.split("-") for x in a.exclude)]
    # the audio thread's stack and thread object, from the symbols
    for addr, size, nm in table:
        if nm.startswith("saAudioStack") or nm.startswith("DvdErr_stack"): excl.append((addr, addr + size))
    def excluded(w): return any(lo <= w < hi for lo, hi in excl)

    recs = list(records(a.trace))
    p0 = [i for i, r in enumerate(recs) if r[0] == "R" and r[1] == "P" and r[2] == 0]
    if not p0:
        print("no painter ('P') regions in this trace"); return
    events_all = [(r[3], r[1], r[2]) for r in recs if r[0] == "E" and r[1] in ("I", "S")]
    ev_cycles = [e[0] for e in events_all]
    def events_between(s, e):
        k0 = bisect.bisect_left(ev_cycles, s); k1 = bisect.bisect_left(ev_cycles, e)
        return Counter(kd for _, kd, _ in events_all[k0:k1])
    def words_of(waddr, wsize):
        out = set()
        for addr, size in zip(waddr, wsize):
            w = addr & ~3
            while w < addr + size:
                if not excluded(w): out.add(w)
                w += 4
        return out

    N = 0
    wait_c = []; proper_c = []; gap_c = []; exec_c = []; draw_c = []
    lines_p = []; words_p = []; pages_p = []; flags_c = Counter(); hw_c = []
    ev_wait = Counter(); ev_proper = Counter()
    sym_written = Counter(); grp_written = Counter(); page_written = Counter()
    raw_by = Counter(); raw_words = Counter(); raw_first = []
    waw_by = Counter(); waw_words = Counter()
    war_lines = []; war_pages = []; war_syms = Counter()
    for n, pi in enumerate(p0):
        end_i = p0[n + 1] if n + 1 < len(p0) else len(recs)
        # the painter's records: from P0 to the first X after it
        j = pi; painter = []; first_x = None
        while j < end_i:
            r = recs[j]
            if r[0] == "R":
                if r[1] == "X": first_x = j; break
                painter.append(r)
            j += 1
        if first_x is None: continue
        N += 1
        P0 = painter[0]
        wait_c.append(P0[7] - P0[6])
        proper = painter[1:]
        p_start = proper[0][6] if proper else P0[7]
        x0 = recs[first_x]
        gap = x0[6] - painter[-1][7]
        gap_c.append(gap)
        proper_c.append(x0[6] - p_start - gap)
        ev_wait.update(events_between(P0[6], P0[7])); ev_proper.update(events_between(p_start, x0[6]))
        rl = set(); words = set(); fl = 0; hw = 0
        for r in proper:
            _, k, prt, mk, pr, nm, st, en, f, rd, wa, ws, tg, ps = r
            rl.update(rd); words |= words_of(wa, ws); fl |= f; hw += r[8] and 0
        lines_p.append(len(rl)); words_p.append(len(words)); pages_p.append(len({w >> 12 for w in words}))
        for bit, nmf in FLAGS.items():
            if fl & bit: flags_c[nmf] += 1
        for w in words:
            s = name_of(table, starts, w, offset=False)
            sym_written[s or "heap"] += 1; grp_written[group_of(s)] += 1
            if not s: page_written[w >> 12] += 1
        wl = {w >> 6 for w in words}
        # the rest of the management: the execute loop, the draw loop, up to the next P0
        ex = dr = 0; war = set(); raw_seen = False
        for j in range(first_x, end_i):
            r = recs[j]
            if r[0] != "R": continue
            _, k, prt, mk, pr, nm, st, en, f, rd, wa, ws, tg, ps = r
            if k == "X": ex += en - st
            if k == "D": dr += en - st
            who = profiles.get(nm, str(nm)) if k in ("X", "D", "J") else ("scene sub-phase " + (name_of(table, starts, mk, offset=False) or f"{mk:08X}") if k == "S" else k)
            cls = {"X": "execute", "D": "draw", "J": "model call", "S": "sub-phase"}.get(k, k)
            hits = [l for l in set(rd) if l in wl]   # a region once per line: the read list repeats lines the direct-mapped filter evicted
            if hits:
                for l in hits:
                    for w in range(l << 6, (l << 6) + 64, 4):
                        if w in words: raw_words[name_of(table, starts, w, offset=False) or f"heap {w:08X}"] += 1
                raw_by[(cls, who)] += len(hits)
                if not raw_seen:
                    raw_first.append((st - x0[6], cls + ": " + who)); raw_seen = True
            for addr, size in zip(wa, ws):
                w = addr & ~3
                while w < addr + size:
                    if w in words:
                        waw_by[(cls, who)] += 1; waw_words[name_of(table, starts, w, offset=False) or f"heap {w:08X}"] += 1
                    w += 4
                for l in range(addr >> 6, ((addr + size - 1) >> 6) + 1):
                    if l in rl:
                        war.add(l)
        exec_c.append(ex); draw_c.append(dr)
        war_lines.append(len(war)); war_pages.append(len({l >> 6 for l in war}))
        for l in war: war_syms[name_of(table, starts, l << 6, offset=False) or "heap"] += 1

    print(f"##### {a.trace}: {N} managements")
    print(f"\n== cycles a frame (guest, natives off): the retrace wait and the prologue (P part 0) p50 {pct(wait_c, .5)} (p10 {pct(wait_c, .1)}, p90 {pct(wait_c, .9)}); "
          f"the painter proper p50 {pct(proper_c, .5)} (p10 {pct(proper_c, .1)}, p90 {pct(proper_c, .9)}); the handlers' gap {pct(gap_c, .5)}; "
          f"the execute loop's regions {pct(exec_c, .5)}; the draw loop's {pct(draw_c, .5)} ==")
    print(f"  the painter proper: read lines p50 {pct(lines_p, .5)} ({pct(lines_p, .5) * 64 // 1024} KB), written words p50 {pct(words_p, .5)} on {pct(pages_p, .5)} pages; "
          f"flags (frames carrying one): " + (", ".join(f"{k} {100 * v / N:.0f} %" for k, v in flags_c.most_common()) or "none"))
    print(f"  events inside the wait: " + (", ".join(f"{k} {v / N:.1f} a frame" for k, v in ev_wait.items()) or "none")
          + f"; inside the painter proper: " + (", ".join(f"{k} {v / N:.1f} a frame" for k, v in ev_proper.items()) or "none"))
    tot = sum(grp_written.values()) or 1
    print(f"\n== what the painter proper writes (distinct words a frame): " + ", ".join(f"{g} {v / N:.0f} ({100 * v / tot:.1f} %)" for g, v in grp_written.most_common()) + " ==")
    for sym, c in sym_written.most_common(a.top):
        print(f"  {c / N:8.0f}  {sym}")
    print("  heap pages written (words a frame, the page's first symbol if any):")
    for pg, c in page_written.most_common(12):
        print(f"  {c / N:8.0f}  {pg << 12:08X}  {name_of(table, starts, pg << 12, offset=False) or ''}")
    print(f"\n== RAW: the management's later regions reading a line that holds a word the painter proper wrote (line-hits a frame) ==")
    for (cls, who), c in raw_by.most_common(a.top):
        print(f"  {c / N:8.1f}  {cls:11s} {who}")
    print("  the words read (word-hits a frame):")
    for w, c in raw_words.most_common(a.top): print(f"     {c / N:8.1f}  {w}")
    fr = [c for c, _ in raw_first]
    print(f"  first RAW after the painter's end: in {100 * len(raw_first) / N:.0f} % of the frames; cycles p10 {pct(fr, .1)} p50 {pct(fr, .5)} p90 {pct(fr, .9)}; "
          + ", ".join(f"{k} {v}" for k, v in Counter(c for _, c in raw_first).most_common(6)))
    print(f"\n== WAW: later regions writing a word the painter proper wrote (word-writes a frame) ==")
    for (cls, who), c in waw_by.most_common(a.top):
        print(f"  {c / N:8.1f}  {cls:11s} {who}")
    for w, c in waw_words.most_common(a.top): print(f"     {c / N:8.1f}  {w}")
    print(f"\n== WAR: lines the painter proper read that the management's later regions write ==")
    print(f"  lines a frame p50 {pct(war_lines, .5)} p90 {pct(war_lines, .9)} of {pct(lines_p, .5)} read; pages p50 {pct(war_pages, .5)} p90 {pct(war_pages, .9)}")
    for s, c in war_syms.most_common(a.top): print(f"     {c / N:8.1f}  {s}")

if __name__ == "__main__":
    main()
