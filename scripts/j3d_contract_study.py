#!/usr/bin/env python3
"""Who reads what the draw side writes: the J3D draw side's contract (M1-T01 and M1-T01b of the
guest-services-migration plan), from a shadow trace (BWST v2, the trace build of fork PR #9, or
PR #12's with the model-call markers).

--writers D (default): every region of kind 'D' (an actor's fpcM_Draw call: its model calc,
skinning, draw-buffer entry and its own draw code) is a writer. --writers J: every region of kind
'J' (a J3DModel::calc/update/viewCalc/entry call an mDoExt_model* function makes; its tag is the
J3DModel, its pass the call site) is a writer, and readers are told apart by model.

A writer's words outside the stack are remembered for --window frames; every later region that
reads a 64-byte line holding one of them is a reader, classified by who it is relative to the
writer and by frame distance. A write by a region of another kind supersedes the remembered word
(later readers see that value). Words nobody reads before they are overwritten or the trace ends
are "unread": the painter's input (it runs first in the next fpcM_Management, outside the loops).

usage: j3d_contract_study.py TRACE --symbols SYMBOLS.txt --profiles f_pc_profile_lst.cpp
       [--writers D|J] [--exclude LO-HI]... [--window FRAMES] [--top N]
"""
import argparse, bisect, re, struct, sys
from collections import Counter, defaultdict
from pathlib import Path

CALLS = {0x802EE8C0: "calc", 0x802EE874: "update", 0x802EEE30: "viewCalc", 0x802EEA2C: "entry"}
SITES = {0x8000F7FC: "modelUpdate", 0x8000F81C: "modelUpdate", 0x8000F838: "modelUpdate",
         0x8000F88C: "modelUpdateDL", 0x8000F8C8: "modelUpdateDL", 0x8000F8E4: "modelUpdateDL",
         0x8000F944: "modelEntry", 0x8000F960: "modelEntry", 0x8000F9DC: "modelEntryDL", 0x8000F9F8: "modelEntryDL"}

def load_symbols(path):
    sym = re.compile(r"^(\S+) = \.\S+:0x([0-9A-Fa-f]+); // type:(?:object|function) size:0x([0-9A-Fa-f]+)")
    table = []
    for line in open(path):
        m = sym.match(line)
        if m:
            table.append((int(m.group(2), 16), int(m.group(3), 16), m.group(1)))
    table.sort()
    return table, [t[0] for t in table]

def name_of(table, starts, addr, offset=True):
    i = bisect.bisect_right(starts, addr) - 1
    if i >= 0 and addr < table[i][0] + table[i][1]:
        return f"{table[i][2]}+0x{addr - table[i][0]:X}" if offset else table[i][2]
    return ""

def load_profiles(path):
    t = Path(path).read_text()
    m = re.search(r"ProfileList\[\]\s*=\s*\{(.*?)\};", t, re.S)
    names = {}
    for e in m.group(1).split(","):
        e = re.sub(r"#.*", "", e.strip()).strip()
        e = re.sub(r"^&?g_profile_", "", e).split(".")[0].strip()
        if e:
            names[len(names)] = e
    return names

def records(path):
    data = Path(path).read_bytes()
    assert data[:4] == b"BWST" and data[4] >= 2, "not a v2 shadow trace"
    at, n = 8, len(data)
    while at < n:
        kind = data[at:at + 1]; at += 1
        if kind in (b"I", b"S", b"F"):
            value, cycle = struct.unpack_from("<IQ", data, at); at += 12
            yield ("E", kind.decode(), value, cycle)
        elif kind == b"R":
            (tag, proc, pass_, name, rkind, part, marker, start, end, flags, alias, hw, nr,
             nw) = struct.unpack_from("<IIIHBBIQQIIIII", data, at)
            at += 4 * 3 + 2 + 1 + 1 + 4 + 8 * 2 + 4 * 5
            reads = struct.unpack_from(f"<{nr}I", data, at); at += 4 * nr
            waddr = struct.unpack_from(f"<{nw}I", data, at); at += 4 * nw
            wsize = data[at:at + nw]; at += nw
            yield ("R", chr(rkind), part, marker, proc, name, start, end, flags, reads, waddr, wsize, tag, pass_)
        else:
            sys.exit(f"bad record {kind!r} at {at - 1}")

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--writers", default="D", choices=["D", "J", "S"], help="whose writes to follow: D the actors' draws, J the model calls, S the scene's sub-phases (with --markers)")
    ap.add_argument("--markers", default="", help="with --writers S: comma-separated hex entry addresses of the sub-phases to follow (default: all)")
    ap.add_argument("--exclude", action="append", default=["80408000-8040D000"], help="address ranges to ignore as writes (the stack)")
    ap.add_argument("--exclude-symbols", default=r"Stack|Thread|^r[0-9]+$|^main$",
                    help="regex of data symbols whose words are ignored (other guest threads' stacks and thread objects, written when an interrupt switches threads inside a region)")
    ap.add_argument("--window", type=int, default=3, help="frames a written word stays watched for readers")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--defer", action="store_true", help="also report the deferral hazards: lines a writer region reads that a later region of the same frame writes (what a job deferred to the frame's end must snapshot)")
    a = ap.parse_args(argv)
    table, starts = load_symbols(a.symbols)
    profiles = load_profiles(a.profiles)
    excl = []
    for e in a.exclude:
        lo, hi = e.split("-"); excl.append((int(lo, 16), int(hi, 16)))
    exsym = re.compile(a.exclude_symbols) if a.exclude_symbols else None
    def excluded(w):
        if any(lo <= w < hi for lo, hi in excl):
            return True
        if exsym is not None:
            s = name_of(table, starts, w, offset=False)
            if s and exsym.search(s):
                return True
        return False
    W = a.writers
    marker_filter = {int(x, 16) for x in a.markers.split(",") if x.strip()}

    retraces = 0
    regions = []            # (kind, part, marker, proc, name, frame, tag, pass_, cycles, enclosing)
    last_kind_of_proc = {}
    pending = {}            # line -> {word: writer_idx}
    writer_words = Counter()
    reads_by = Counter()    # (writer profile, reader class, when) -> word-reads
    read_words = set()
    sym_written = Counter()
    sym_read_by_class = Counter()
    heap_pairs = Counter()
    evictions = Counter()
    cycles_by = Counter(); count_by = Counter()
    models_in_frame = defaultdict(set)
    words_by_call = Counter(); calls_by_call = Counter()
    n_writers = 0; nwritten_total = 0
    scene_proc = None
    game_frame = 0; last_kind = ""   # a game frame starts at the first execute region after the draw loop
    deferred = []                   # [(idx, frame, read_lines)] of this frame's writer regions
    hazard_by = Counter()           # (writer label, later writer class) -> lines
    hazard_sym = Counter()          # (symbol or heap) -> lines
    hazard_lines_total = 0; read_lines_total = 0

    def writer_label(w_idx):
        k, _, mark, _, nm, *_ = regions[w_idx]
        if k == "S":
            return name_of(table, starts, mark, offset=False) or f"{mark:08X}"
        return profiles.get(nm, str(nm))

    def reader_class(w_idx, r_idx):
        wk, wpart, wmark, wproc, wname, wframe, wtag, wpass, _, _ = regions[w_idx]
        rk, rpart, rmark, rproc, rname, rframe, rtag, rpass, _, _ = regions[r_idx]
        dist = rframe - wframe
        when = "same frame" if dist == 0 else ("next frame" if dist == 1 else "later")
        if wk == "J":
            if rk == "J":
                if rtag == wtag:
                    who = "same model: later call (" + CALLS.get(rmark, "?") + ")"
                elif rproc == wproc:
                    who = "same actor: another model's call"
                else:
                    who = "other actor: a model call"
            elif rproc == wproc:
                who = {"D": "same actor: its own draw code", "X": "same actor: its own execute code", "S": "same actor: sub-phase"}[rk]
            elif rproc == scene_proc:
                who = ("scene sub-phase " + (name_of(table, starts, rmark, offset=False) or f"{rmark:08X}")) if rk == "S" else ("scene: draw" if rk == "D" else "scene: execute")
            else:
                who = {"D": "other actor: draw", "X": "other actor: execute", "S": "other actor: sub-phase"}[rk]
            return who, when
        if wk == "S":
            if rk == "S":
                who = ("same sub-phase" if rmark == wmark else "sub-phase " + (name_of(table, starts, rmark, offset=False) or f"{rmark:08X}"))
            elif rproc == wproc:
                who = "scene: its own draw code" if rk == "D" else "scene: its own execute code"
            else:
                who = {"D": "an actor: draw", "X": "an actor: execute", "J": "an actor: model call"}[rk]
            return who, when
        if rproc == wproc:
            who = {"D": "same actor: draw", "X": "same actor: execute", "S": "same actor: sub-phase", "J": "same actor: model call"}[rk]
        elif rproc == scene_proc:
            if rk == "S":
                who = "scene sub-phase " + (name_of(table, starts, rmark, offset=False) or f"{rmark:08X}")
            else:
                who = "scene: draw" if rk == "D" else ("scene: execute" if rk == "X" else "scene: model call")
        else:
            who = {"D": "other actor: draw", "X": "other actor: execute", "S": "other actor: sub-phase", "J": "other actor: model call"}[rk]
        return who, when

    idx = -1
    for rec in records(a.trace):
        if rec[0] == "E":
            if rec[1] == "F":
                retraces += 1
            continue
        _, kind, part, marker, proc, name, start, end, flags, reads, waddr, wsize, tag, pass_ = rec
        idx += 1
        if kind == "X" and last_kind in ("D", "J") and any(r[0] == "D" for r in regions[-3:]):
            game_frame += 1
        if kind != "J":
            last_kind = kind
        frame = game_frame
        enclosing = last_kind_of_proc.get(proc, "?") if kind == "J" else ""
        if kind != "J":
            last_kind_of_proc[proc] = kind
        regions.append((kind, part, marker, proc, name, frame, tag, pass_, end - start, enclosing))
        call = CALLS.get(marker, "?") if kind == "J" else ""
        cycles_by[(kind, call, enclosing)] += end - start
        count_by[(kind, call, enclosing)] += 1
        if kind == "J":
            models_in_frame[frame].add(tag)
        if kind == "S" and scene_proc is None:
            scene_proc = proc
        # deferral hazards: this region writes a line one of the frame's earlier writer regions read
        if a.defer:
            deferred = [d for d in deferred if d[1] == frame]
            if deferred and waddr:
                wl = {}
                for ad, sz in zip(waddr, wsize):
                    for w in range(ad & ~3, ad + sz, 4):
                        if not excluded(w):
                            wl.setdefault(w >> 6, w)
                if wl:
                    for d_idx, d_frame, d_reads in deferred:
                        if d_idx == idx:
                            continue
                        hit = d_reads & wl.keys()
                        if hit:
                            who, when = reader_class(d_idx, idx)
                            hazard_by[(writer_label(d_idx), who)] += len(hit)
                            hazard_lines_total += len(hit)
                            for line in hit:
                                hazard_sym[name_of(table, starts, wl[line], offset=False) or "heap"] += 1
        # readers of remembered writes
        if pending:
            for line in reads:
                hit = pending.get(line)
                if not hit:
                    continue
                for word, w_idx in list(hit.items()):
                    if w_idx == idx:
                        continue
                    who, when = reader_class(w_idx, idx)
                    wprof = writer_label(w_idx)
                    reads_by[(wprof, who, when)] += 1
                    read_words.add((w_idx, word))
                    sname = name_of(table, starts, word, offset=False) or "heap"
                    sym_read_by_class[(sname, who)] += 1
                    if sname == "heap" and who.startswith("other actor"):
                        heap_pairs[(wprof, profiles.get(name, str(name)), who)] += 1
        # evict watched words older than the window
        if idx % 500 == 0 and pending:
            cutoff = frame - a.window
            for line in list(pending):
                d = pending[line]
                for word, w_idx in list(d.items()):
                    if regions[w_idx][5] < cutoff:
                        if (w_idx, word) not in read_words:
                            evictions[(writer_label(w_idx), "unread")] += 1
                        del d[word]
                if not d:
                    del pending[line]
        is_writer = kind == W and (not marker_filter or marker in marker_filter)
        if not is_writer:
            # another region's write supersedes a remembered word: later readers see its value
            if pending:
                for ad, sz in zip(waddr, wsize):
                    for w in range(ad & ~3, ad + sz, 4):
                        d = pending.get(w >> 6)
                        if d and w in d:
                            old = d.pop(w)
                            if (old, w) not in read_words:
                                evictions[(writer_label(old), f"overwritten unread by a {kind} region")] += 1
                            if not d:
                                del pending[w >> 6]
            continue
        # a writer region: remember its words
        n_writers += 1
        if a.defer:
            deferred.append((idx, frame, set(reads))); read_lines_total += len(reads)
        words = set()
        for ad, sz in zip(waddr, wsize):
            for w in range(ad & ~3, ad + sz, 4):
                if not excluded(w):
                    words.add(w)
        writer_words[idx] = len(words)
        nwritten_total += len(words)
        if kind == "J":
            words_by_call[call] += len(words); calls_by_call[call] += 1
        for w in words:
            sym_written[name_of(table, starts, w, offset=False) or "heap"] += 1
            d = pending.setdefault(w >> 6, {})
            old = d.get(w)
            if old is not None and (old, w) not in read_words:
                same = regions[old][6] == tag if kind == "J" else (regions[old][2] == marker if kind == "S" else regions[old][3] == proc)
                evictions[(writer_label(old), "overwritten unread by " + ("the same " + ("model" if kind == "J" else "writer") if same else "another " + ("model" if kind == "J" else "writer")))] += 1
            d[w] = idx
    for line, d in pending.items():
        for word, w_idx in d.items():
            if (w_idx, word) not in read_words:
                evictions[(writer_label(w_idx), "unread at the end")] += 1

    frames = max(game_frame, 1)
    writers_label = {"D": "the actors' draws", "J": "the model calls", "S": "the scene sub-phases " + (",".join(f"{m:08X}" for m in sorted(marker_filter)) or "(all)")}[W]
    print(f"##### {a.trace}  (writers: {writers_label})")
    print(f"frames {frames}, regions {len(regions)}, writer regions {n_writers} ({n_writers / frames:.0f} a frame), "
          f"words written outside the stack: {nwritten_total} ({nwritten_total / frames:.0f} a frame)")
    print(f"scene process {scene_proc:08X}" if scene_proc else "no scene process found")
    j_total = sum(c for (k, _, _), c in cycles_by.items() if k == "J")
    if j_total:
        d_parts = sum(c for (k, _, _), c in cycles_by.items() if k == "D"); x_parts = sum(c for (k, _, _), c in cycles_by.items() if k == "X")
        j_in_d = sum(c for (k, _, e), c in cycles_by.items() if k == "J" and e == "D"); j_in_x = sum(c for (k, _, e), c in cycles_by.items() if k == "J" and e == "X")
        print("\n== the model calls: count a frame, guest cycles a frame, share of the loop they run in ==")
        for (k, call, enc), c in sorted(cycles_by.items(), key=lambda kv: -kv[1]):
            if k != "J": continue
            loop = (d_parts + j_in_d) if enc == "D" else (x_parts + j_in_x) if enc == "X" else 0
            print(f"  {call:9} inside {enc:1}: {count_by[(k, call, enc)] / frames:7.1f} a frame, {c / frames:12.0f} cycles a frame, {100 * c / loop if loop else 0:5.1f} % of that loop")
        print(f"  all model calls inside draws: {100 * j_in_d / (d_parts + j_in_d):.1f} % of the draw loop's cycles; inside executes: {100 * j_in_x / max(x_parts + j_in_x, 1):.1f} % of the execute loop's")
        mpf = sum(len(s) for s in models_in_frame.values()) / max(len(models_in_frame), 1)
        print(f"  distinct models a frame: {mpf:.0f}; words a model a frame: {nwritten_total / frames / max(mpf, 1):.0f}; words a call: " +
              ", ".join(f"{call} {words_by_call[call] / max(calls_by_call[call], 1):.0f}" for call in ("calc", "update", "viewCalc", "entry") if calls_by_call[call]))
    print("\n== what the writers write (words, by symbol; 'heap' = no symbol) ==")
    for s, c in sym_written.most_common(a.top):
        print(f"  {100*c/max(nwritten_total,1):6.2f}%  {c:9d}  {s}")
    total_reads = sum(reads_by.values())
    print(f"\n== who reads them: word-reads of the writers' words, {total_reads} in all ==")
    by_class = Counter()
    for (wprof, who, when), c in reads_by.items():
        by_class[(who, when)] += c
    for (who, when), c in by_class.most_common(a.top + 10):
        print(f"  {100*c/max(total_reads,1):6.2f}%  {c:9d}  {who:44} {when}")
    print("\n== the same by reader class, heap words against named words ==")
    heap_c = Counter(); named_c = Counter()
    for (s, who), c in sym_read_by_class.items():
        (heap_c if s == "heap" else named_c)[who] += c
    for who, c in (heap_c + named_c).most_common(12):
        print(f"  {who:44} heap {heap_c[who]:9d}  named {named_c[who]:9d}")
    print("\n== written words never read inside the loops (before being overwritten or the end) ==")
    unread = sum(evictions.values())
    print(f"  {unread} word-writes unread of {nwritten_total} written ({100*unread/max(nwritten_total,1):.1f} %)")
    for (p, how), c in evictions.most_common(8):
        print(f"  {c:9d}  {p:16} {how}")
    print("\n== named words read by the execute pass or the scene's execute (the cross-pass contract) ==")
    cross = Counter()
    for (s, who), c in sym_read_by_class.items():
        if "execute" in who and s != "heap":
            cross[(s, who)] += c
    for (s, who), c in cross.most_common(a.top):
        print(f"  {c:9d}  {s:50} {who}")
    print("\n== heap words written by one actor and read by another actor (writer -> reader) ==")
    for (wp, rp, who), c in heap_pairs.most_common(a.top):
        print(f"  {c:9d}  {wp:16} -> {rp:16} ({who})")
    if a.defer:
        print(f"\n== deferral hazards: of the lines the writer regions read ({read_lines_total}, {read_lines_total / frames:.0f} a frame), those a later region of the same frame writes ({hazard_lines_total}, {100 * hazard_lines_total / max(read_lines_total, 1):.2f} %) ==")
        for (wl_, who), c in hazard_by.most_common(12):
            print(f"  {c:9d}  {wl_:34} written later by {who}")
        print("  by symbol:")
        for s, c in hazard_sym.most_common(12):
            print(f"  {c:9d}  {s}")
    print("\n== by writer profile: words written, share never read inside the loops, word-reads by class ==")
    written_by = Counter(); unread_by = Counter()
    for w_idx, n in writer_words.items():
        written_by[writer_label(w_idx)] += n
    for (p, how), c in evictions.items():
        unread_by[p] += c
    for wprof, nwr in written_by.most_common(12):
        row = Counter()
        for (wp, who, when), c in reads_by.items():
            if wp == wprof:
                row[who] += c
        tot = sum(row.values())
        print(f"  {wprof:16} written {nwr:8d} ({100*nwr/max(nwritten_total,1):4.1f}%), unread {100*unread_by[wprof]/max(nwr,1):5.1f}%; reads {tot:8d}: " +
              ", ".join(f"{who} {100*c/max(tot,1):.0f}%" for who, c in row.most_common(4)))

if __name__ == "__main__":
    main()
