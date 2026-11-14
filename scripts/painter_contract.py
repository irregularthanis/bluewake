#!/usr/bin/env python3
"""The painter's contract (M1-T02b of the guest-services-migration plan), from a shadow trace with
PR #12's 'P' region: cAPIGph_Painter (mDoGph_Painter), the first thing fpcM_Management does, which
draws the previous frame's lists into the GX stream.

Per management (the P region, the gap to the first execute region = the delete/create handlers,
the execute loop's X regions, then the draw loop): the painter's cycles, read lines, written words
(by symbol or heap, by page), flags and hardware accesses; the interrupt and DSP-step events that
fall inside it; and against the same management's later regions: who reads a word the painter
wrote (RAW: what a job must have committed before that reader), who writes one (WAW: the merge at
the join), and how much of what the painter read the execute loop rewrites (WAR: the snapshot a
job needs if the game thread writes in place). The painter's own stack is excluded.

usage: painter_contract.py TRACE --symbols SYMBOLS.txt --profiles f_pc_profile_lst.cpp [--exclude LO-HI]... [--top N]
"""
import argparse, bisect, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from j3d_contract_study import load_symbols, name_of, load_profiles, records, CALLS

FLAGS = {1 << 2: "hw-read", 1 << 3: "hw-write", 1 << 4: "alias", 1 << 5: "fallback", 1 << 6: "timer",
         1 << 7: "psq-fallback", 1 << 8: "dcbz", 1 << 9: "interrupt", 1 << 0: "read-overflow", 1 << 1: "write-overflow"}

def pct(v, p):
    if not v: return 0
    s = sorted(v); return s[min(len(s) - 1, int(p * len(s)))]

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("trace"); ap.add_argument("--symbols", required=True); ap.add_argument("--profiles", required=True)
    ap.add_argument("--exclude", action="append", default=["80408000-8040D000"])
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args(argv)
    table, starts = load_symbols(a.symbols); profiles = load_profiles(a.profiles)
    excl = [(int(lo, 16), int(hi, 16)) for lo, hi in (x.split("-") for x in a.exclude)]
    def excluded(w): return any(lo <= w < hi for lo, hi in excl)

    # pass 1: the records in order, with the events
    recs = []
    for rec in records(a.trace):
        recs.append(rec)
    p_idx = [i for i, r in enumerate(recs) if r[0] == "R" and r[1] == "P"]
    if not p_idx:
        print("no painter ('P') regions in this trace"); return
    print(f"##### {a.trace}: {len(p_idx)} painter regions")
    # per management: from a P region to the next P region
    cyc_p = []; lines_p = []; words_p = []; pages_p = []; flags_c = Counter(); hw = []; events_in = Counter()
    gap_handlers = []; exec_cycles = []; draw_cycles = []
    sym_written = Counter(); raw_by = Counter(); waw_by = Counter(); raw_words = Counter(); waw_words = Counter()
    war_lines = []; war_pages = []; raw_first = []  # (cycles after the painter's end, class) of the first RAW
    events_all = [(r[3], r[1]) for r in recs if r[0] == "E" and r[1] in ("I", "S")]
    ev_cycles = [e[0] for e in events_all]
    for n, pi in enumerate(p_idx):
        end_i = p_idx[n + 1] if n + 1 < len(p_idx) else len(recs)
        _, kind, part, marker, proc, name, start, end, flags, reads, waddr, wsize, tag, pass_ = recs[pi]
        cyc_p.append(end - start); lines_p.append(len(reads))
        for bit, nm in FLAGS.items():
            if flags & bit: flags_c[nm] += 1
        words = {}
        for addr, size in zip(waddr, wsize):
            w = addr & ~3
            while w < addr + size:
                if not excluded(w):
                    words[w] = True
                    sym_written[name_of(table, starts, w, offset=False) or "heap"] += 1
                w += 4
        words_p.append(len(words)); pages_p.append(len({w >> 12 for w in words}))
        wl = {w >> 6 for w in words}
        rl = set(reads)
        k0 = bisect.bisect_left(ev_cycles, start); k1 = bisect.bisect_left(ev_cycles, end)
        for c, kd in events_all[k0:k1]: events_in[kd] += 1
        # the later regions of this management
        first_x = None; ex = dr = 0; war = set(); raw_seen = False
        for j in range(pi + 1, end_i):
            r = recs[j]
            if r[0] != "R": continue
            _, k, prt, mk, pr, nm, st, en, fl, rd, wa, ws, tg, ps = r
            if k == "X" and first_x is None: first_x = st
            if k in ("X",): ex += en - st
            if k in ("D",): dr += en - st
            if k == "J": (ex if False else None)
            who = profiles.get(nm, str(nm)) if k in ("X", "D", "J") else ("scene sub-phase " + (name_of(table, starts, mk, offset=False) or f"{mk:08X}") if k == "S" else k)
            cls = {"X": "execute", "D": "draw", "J": "model call", "S": "sub-phase"}.get(k, k)
            # RAW: this region reads a line holding a painter-written word
            hits = [l for l in rd if l in wl]
            if hits:
                for l in hits:
                    for w in range(l << 6, (l << 6) + 64, 4):
                        if w in words:
                            raw_words[name_of(table, starts, w, offset=False) or f"heap {w:08X}"] += 1
                raw_by[(cls, who)] += len(hits)
                if not raw_seen:
                    raw_first.append((st - end, cls + ": " + who)); raw_seen = True
            # WAW: this region writes a painter-written word
            for addr, size in zip(wa, ws):
                w = addr & ~3
                while w < addr + size:
                    if w in words:
                        waw_by[(cls, who)] += 1; waw_words[name_of(table, starts, w, offset=False) or f"heap {w:08X}"] += 1
                    w += 4
            # WAR: this region writes a line the painter read
            for addr, size in zip(wa, ws):
                l0 = addr >> 6; l1 = (addr + size - 1) >> 6
                for l in range(l0, l1 + 1):
                    if l in rl: war.add(l)
        if first_x is not None: gap_handlers.append(first_x - end)
        exec_cycles.append(ex); draw_cycles.append(dr)
        war_lines.append(len(war)); war_pages.append(len({l >> 6 for l in war}))
    N = len(p_idx)
    print(f"\n== the painter: cycles a frame p10 {pct(cyc_p, .1)} p50 {pct(cyc_p, .5)} p90 {pct(cyc_p, .9)} (natives off); the execute loop's X regions {pct(exec_cycles, .5)} cycles at the median, "
          f"the draw loop's D regions {pct(draw_cycles, .5)}; the handlers' gap after the painter {pct(gap_handlers, .5)} cycles ==")
    print(f"  read lines p50 {pct(lines_p, .5)} ({pct(lines_p, .5) * 64 / 1024:.0f} KB), written words p50 {pct(words_p, .5)} on {pct(pages_p, .5)} pages; "
          f"flags: " + (", ".join(f"{k} {100 * v / N:.0f} %" for k, v in flags_c.most_common()) or "none"))
    print(f"  events inside the painter: " + ", ".join(f"{k} {v / N:.1f} a frame" for k, v in events_in.items()))
    print(f"\n== what the painter writes (words a frame, by symbol; 'heap' = no symbol) ==")
    tot = sum(sym_written.values())
    for sym, c in sym_written.most_common(a.top):
        print(f"  {100 * c / tot:6.2f}%  {c / N:8.0f}  {sym}")
    print(f"\n== RAW: later regions of the same management reading a line that holds a painter-written word (line-hits a frame; the exactness question) ==")
    for (cls, who), c in raw_by.most_common(a.top):
        print(f"  {c / N:8.1f}  {cls:11s} {who}")
    print("  the words read (hits a frame):")
    for w, c in raw_words.most_common(a.top): print(f"     {c / N:8.1f}  {w}")
    fr = [c for c, _ in raw_first]
    print(f"  first RAW after the painter's end: in {100 * len(raw_first) / N:.0f} % of the frames; cycles p10 {pct(fr, .1)} p50 {pct(fr, .5)} p90 {pct(fr, .9)}; "
          + ", ".join(f"{k} {v}" for k, v in Counter(c for _, c in raw_first).most_common(6)))
    print(f"\n== WAW: later regions writing a painter-written word (word-writes a frame; the merge at the join) ==")
    for (cls, who), c in waw_by.most_common(a.top):
        print(f"  {c / N:8.1f}  {cls:11s} {who}")
    for w, c in waw_words.most_common(a.top): print(f"     {c / N:8.1f}  {w}")
    print(f"\n== WAR: lines the painter read that the same management's later regions write (the snapshot a job needs if the game thread writes in place) ==")
    print(f"  lines a frame p50 {pct(war_lines, .5)} p90 {pct(war_lines, .9)} of {pct(lines_p, .5)} read; pages p50 {pct(war_pages, .5)} p90 {pct(war_pages, .9)}")

if __name__ == "__main__":
    main()
