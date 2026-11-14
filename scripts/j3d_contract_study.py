#!/usr/bin/env python3
"""Who reads what the actors' draw regions write (the J3D draw side's contract, M1-T01 of the
guest-services-migration plan), from a shadow trace (BWST v2, the B1c trace build).

For every region of kind 'D' (an actor's fpcM_Draw call: its model calc, skinning, draw-buffer
entry) the words it writes outside the stack are remembered; every later region that reads a
64-byte line holding one of them is a reader, classified by who it is relative to the writer
and by frame distance. Words nobody reads before they are overwritten or the trace ends are
"unread".

usage: j3d_contract_study.py TRACE --symbols SYMBOLS.txt --profiles f_pc_profile_lst.cpp
       [--exclude LO-HI]... [--window FRAMES] [--top N]
"""
import argparse, bisect, re, struct, sys
from collections import Counter, defaultdict
from pathlib import Path

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
            yield ("R", chr(rkind), part, marker, proc, name, start, end, flags, reads, waddr, wsize)
        else:
            sys.exit(f"bad record {kind!r} at {at - 1}")

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--exclude", action="append", default=["80408000-8040D000"], help="address ranges to ignore as writes (the stack)")
    ap.add_argument("--window", type=int, default=3, help="frames a written word stays watched for readers")
    ap.add_argument("--exclude-symbols", default=r"Stack|Thread|^r[0-9]+$|^main$", help="regex of data symbols whose words are ignored (other guest threads' stacks and thread objects, written when an interrupt switches threads inside a region)")
    ap.add_argument("--top", type=int, default=20)
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

    # first pass facts: the scene's process (the one whose regions carry sub-phases) is found on the fly
    retraces = 0
    frame_of_region = []
    regions = []       # (kind, part, marker, proc, name, frame)
    pending = {}       # line -> {word: writer_idx}
    writer_words = Counter()        # writer idx -> words written (non-stack)
    reads_by = Counter()            # (writer profile, reader class) -> word-reads
    read_words = set()              # (writer_idx, word) seen read at least once
    sym_written = Counter()         # symbol (no offset) -> words written by D regions
    sym_read_by_class = Counter()   # (symbol, reader class) -> count
    heap_pairs = Counter()          # (writer profile, reader profile, class) for heap words
    d_regions = 0
    scene_proc = None
    frames_seen = 0
    evictions = Counter()
    nwritten_total = 0

    def reader_class(w_idx, r_idx):
        wk, wpart, wmark, wproc, wname, wframe = regions[w_idx]
        rk, rpart, rmark, rproc, rname, rframe = regions[r_idx]
        dist = rframe - wframe
        when = "same frame" if dist == 0 else ("next frame" if dist == 1 else "later")
        if rproc == wproc:
            who = {"D": "same actor: draw", "X": "same actor: execute", "S": "same actor: sub-phase"}[rk]
        elif rproc == scene_proc:
            if rk == "S":
                who = "scene sub-phase " + (name_of(table, starts, rmark, offset=False) or f"{rmark:08X}")
            else:
                who = "scene: draw" if rk == "D" else "scene: execute"
        else:
            who = {"D": "other actor: draw", "X": "other actor: execute", "S": "other actor: sub-phase"}[rk]
        return who, when

    idx = -1
    for rec in records(a.trace):
        if rec[0] == "E":
            if rec[1] == "F":
                retraces += 1
            continue
        _, kind, part, marker, proc, name, start, end, flags, reads, waddr, wsize = rec
        idx += 1
        frame = retraces // 2
        regions.append((kind, part, marker, proc, name, frame))
        if kind == "S" and scene_proc is None:
            scene_proc = proc
        # readers of pending draw writes
        if pending:
            for line in reads:
                hit = pending.get(line)
                if not hit:
                    continue
                for word, w_idx in list(hit.items()):
                    if w_idx == idx:
                        continue
                    who, when = reader_class(w_idx, idx)
                    wprof = profiles.get(regions[w_idx][4], str(regions[w_idx][4]))
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
                            evictions[(profiles.get(regions[w_idx][4], "?"), "unread")] += 1
                        del d[word]
                if not d:
                    del pending[line]
        # an execute or sub-phase write supersedes a pending draw write: later readers see its value
        if kind != "D" and pending:
            for ad, sz in zip(waddr, wsize):
                for w in range(ad & ~3, ad + sz, 4):
                    d = pending.get(w >> 6)
                    if d and w in d:
                        old = d.pop(w)
                        if (old, w) not in read_words:
                            evictions[(profiles.get(regions[old][4], "?"), "overwritten unread by the execute pass")] += 1
                        if not d:
                            del pending[w >> 6]
        # remember this draw region's writes
        if kind == "D":
            d_regions += 1
            words = set()
            for ad, sz in zip(waddr, wsize):
                for w in range(ad & ~3, ad + sz, 4):
                    if not excluded(w):
                        words.add(w)
            writer_words[idx] = len(words)
            nwritten_total += len(words)
            wprof = profiles.get(name, str(name))
            for w in words:
                sym_written[name_of(table, starts, w, offset=False) or "heap"] += 1
                d = pending.setdefault(w >> 6, {})
                old = d.get(w)
                if old is not None and (old, w) not in read_words:
                    oprof = profiles.get(regions[old][4], "?")
                    evictions[(oprof, "overwritten unread by " + ("the same actor" if regions[old][3] == proc else "another actor"))] += 1
                d[w] = idx
    # the rest
    for line, d in pending.items():
        for word, w_idx in d.items():
            if (w_idx, word) not in read_words:
                evictions[(profiles.get(regions[w_idx][4], "?"), "unread at the end")] += 1

    frames = retraces // 2
    print(f"##### {a.trace}")
    print(f"frames {frames}, regions {len(regions)}, draw regions {d_regions} ({d_regions / max(frames,1):.0f} a frame), "
          f"words written by draw regions outside the stack: {nwritten_total} ({nwritten_total / max(frames,1):.0f} a frame)")
    print(f"scene process {scene_proc:08X}" if scene_proc else "no scene process found")
    print("\n== what the draw regions write (words, by symbol; 'heap' = no symbol) ==")
    for s, c in sym_written.most_common(a.top):
        print(f"  {100*c/nwritten_total:6.2f}%  {c:9d}  {s}")
    total_reads = sum(reads_by.values())
    print(f"\n== who reads them: word-reads of draw-written words, {total_reads} in all ==")
    by_class = Counter()
    for (wprof, who, when), c in reads_by.items():
        by_class[(who, when)] += c
    for (who, when), c in by_class.most_common():
        print(f"  {100*c/total_reads:6.2f}%  {c:9d}  {who:40} {when}")
    print("\n== draw-written words never read (before being overwritten or the end) ==")
    unread = sum(evictions.values())
    print(f"  {unread} word-writes unread of {nwritten_total} written ({100*unread/max(nwritten_total,1):.1f} %)")
    for (p, how), c in evictions.most_common(8):
        print(f"  {c:9d}  {p:16} {how}")
    print("\n== named words read by the actors' execute pass or the scene's execute (the cross-pass contract) ==")
    cross = Counter()
    for (s, who), c in sym_read_by_class.items():
        if "execute" in who and s != "heap":
            cross[(s, who)] += c
    for (s, who), c in cross.most_common(a.top):
        print(f"  {c:9d}  {s:50} {who}")
    print("\n== heap words written by one actor's draw and read by another actor (writer -> reader) ==")
    for (wp, rp, who), c in heap_pairs.most_common(a.top):
        print(f"  {c:9d}  {wp:16} -> {rp:16} ({who})")
    print("\n== by writer profile: words written, share never read inside the loops (the outputs the end-of-frame draw consumes), word-reads by class ==")
    by_writer = Counter()
    for (wprof, who, when), c in reads_by.items():
        by_writer[wprof] += c
    written_by = Counter(); unread_by = Counter()
    for w_idx, n in writer_words.items():
        written_by[profiles.get(regions[w_idx][4], "?")] += n
    for (p, how), c in evictions.items():
        unread_by[p] += c
    for wprof, nwr in written_by.most_common(12):
        row = Counter()
        for (wp, who, when), c in reads_by.items():
            if wp == wprof:
                row[who] += c
        tot = sum(row.values())
        print(f"  {wprof:16} written {nwr:8d} ({100*nwr/nwritten_total:4.1f}%), unread {100*unread_by[wprof]/max(nwr,1):5.1f}%; reads {tot:8d}: " + ", ".join(f"{who} {100*c/max(tot,1):.0f}%" for who, c in row.most_common(4)))

if __name__ == "__main__":
    main()
