#!/usr/bin/env python3
"""Which heap words do the model calls write that several models of one actor type write (per-type shared
heap) and that several actors' models read? For each actor type: the words its model calls write in a frame,
split into private (one model only) and shared (two or more distinct J3DModels of the type), with the
shared words' address clusters. usage: shared_heap.py TRACE SYMBOLS PROFILES"""
import struct, re, sys, bisect
from collections import defaultdict, Counter
from pathlib import Path
SYM = re.compile(r"^(\S+) = \.\S+:0x([0-9A-Fa-f]+); // type:(?:object|function) size:0x([0-9A-Fa-f]+)")
table = []
for line in open(sys.argv[2]):
    m = SYM.match(line)
    if m: table.append((int(m.group(2), 16), int(m.group(3), 16), m.group(1)))
table.sort(); starts = [t[0] for t in table]
def named(a):
    i = bisect.bisect_right(starts, a) - 1
    return i >= 0 and a < table[i][0] + table[i][1]
t = Path(sys.argv[3]).read_text()
prof = {}
for i, e in enumerate([x.strip() for x in re.search(r"ProfileList\[\]\s*=\s*\{(.*?)\};", t, re.S).group(1).split(",") if x.strip()]):
    prof[i] = re.sub(r"^&?g_profile_", "", re.sub(r"#.*", "", e)).split(".")[0].strip()
data = Path(sys.argv[1]).read_bytes(); at = 8; n = len(data)
# per type: word -> set of model tags writing it (first 30 frames are enough)
writers = defaultdict(lambda: defaultdict(set)); models = defaultdict(set); frames = 0; last = ""; regs = 0
while at < n and frames < 30:
    k = data[at:at+1]; at += 1
    if k in (b"I", b"S", b"F"): at += 12; continue
    tag, proc, pass_, name, rkind, part, marker, start, end, flags, alias, hw, nr, nw = struct.unpack_from("<IIIHBBIQQIIIII", data, at)
    at += 4*3+2+1+1+4+8*2+4*5
    reads = struct.unpack_from(f"<{nr}I", data, at); at += 4*nr
    waddr = struct.unpack_from(f"<{nw}I", data, at); at += 4*nw
    wsize = data[at:at+nw]; at += nw
    kind = chr(rkind)
    if kind == "X" and last in ("D", "J"): frames += 1
    if kind != "J": last = kind
    if kind != "J": continue
    tp = prof.get(name, str(name)); models[tp].add(tag)
    for a, s in zip(waddr, wsize):
        for w in range(a & ~3, a + s, 4):
            if 0x80408000 <= w < 0x8040D000 or named(w): continue
            writers[tp][w].add(tag)
print(f"{frames} frames scanned")
print(f"{'type':14} {'models':>6} {'heap words':>10} {'shared by 2+ models':>19}  shared clusters (address: words, models)")
rows = []
for tp, wm in writers.items():
    shared = {w: tags for w, tags in wm.items() if len(tags) >= 2}
    rows.append((len(wm), tp, len(models[tp]), shared))
for nw, tp, nm, shared in sorted(rows, reverse=True)[:14]:
    # cluster shared words by 4 KB page
    pages = Counter(); pm = defaultdict(set)
    for w, tags in shared.items():
        pages[w >> 12] += 1; pm[w >> 12] |= tags
    cl = ", ".join(f"{p << 12:08X}: {c} w / {len(pm[p])} m" for p, c in pages.most_common(3))
    print(f"{tp:14} {nm:6d} {nw:10d} {len(shared):19d}  {cl}")
