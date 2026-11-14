#!/usr/bin/env python3
"""Field-level view of the painter's RAW words: for every word the painter proper wrote that a later
region of the same management read (line granularity), the symbol+offset, the reader side (the
execute loop: X, J inside X, S inside the scene's execute; the draw loop: D, J inside D, S inside
the scene's draw), and the share of reader regions that also wrote the word (a scratch indicator)."""
import bisect, re, sys
from pathlib import Path
from collections import Counter, defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from j3d_contract_study import load_symbols, name_of, load_profiles, records, CALLS
trace, symf, proff = sys.argv[1:4]
table, starts = load_symbols(symf); profiles = load_profiles(proff)
def nearest(addr):
    i = bisect.bisect_right(starts, addr) - 1
    if i < 0: return "?"
    a, size, nm = table[i]
    return f"{nm}+0x{addr - a:X}" + ("" if addr < a + size else " (past its end)")
excl = [(0x80408000, 0x8040D000)]
for addr, size, nm in table:
    if nm.startswith("saAudioStack") or nm.startswith("DvdErr_stack"): excl.append((addr, addr + size))
def excluded(w): return any(lo <= w < hi for lo, hi in excl)
recs = list(records(trace))
p0 = [i for i, r in enumerate(recs) if r[0] == "R" and r[1] == "P" and r[2] == 0]
hits = Counter(); hits_side = Counter(); readers_total = Counter(); readers_writing = Counter(); first_words = Counter(); writer_of = Counter(); job_cycles = []
N = 0
for n, pi in enumerate(p0):
    end_i = p0[n + 1] if n + 1 < len(p0) else len(recs)
    j = pi; proper = []; first_x = None
    while j < end_i:
        r = recs[j]
        if r[0] == "R":
            if r[1] == "X": first_x = j; break
            if j > pi: proper.append(r)
        j += 1
    if first_x is None: continue
    N += 1
    words = set(); writer = {}
    # the job: the longest region inside the painter (the list draws to the return); before it the prologue, after it the epilogue
    last_j = max(range(len(proper)), key=lambda k: proper[k][7] - proper[k][6]) if proper else -1
    job_cycles.append(proper[last_j][7] - proper[last_j][6] if last_j >= 0 else 0)
    for k, r in enumerate(proper):
        part = "job" if k == last_j else ("prologue" if k < last_j else "epilogue")
        for addr, size in zip(r[10], r[11]):
            w = addr & ~3
            while w < addr + size:
                if not excluded(w):
                    words.add(w)
                    if w not in writer or part == "job" or (part == "epilogue" and writer[w] != "job"): writer[w] = part
                w += 4
    for w in words: writer_of[(w, writer[w])] += 1
    wl = defaultdict(list)
    for w in words: wl[w >> 6].append(w)
    side = "execute"; first_done = False; scene_proc = None
    for j in range(first_x, end_i):
        r = recs[j]
        if r[0] != "R": continue
        _, k, prt, mk, pr, nm, st, en, f, rd, wa, ws, tg, ps = r
        if k == "X": side = "execute"
        elif k == "D": side = "draw"
        wrote = set()
        for addr, size in zip(wa, ws):
            w = addr & ~3
            while w < addr + size: wrote.add(w); w += 4
        for l in set(rd):   # the trace's read list repeats a line the direct-mapped filter evicted: count a region once per line
            if l in wl:
                for w in wl[l]:
                    hits[w] += 1; hits_side[(w, side)] += 1; readers_total[w] += 1
                    if w in wrote: readers_writing[w] += 1
                    if not first_done: first_words[w] += 1
                if not first_done: first_done = True
print(f"managements {N}; painter-written words read later: {len(hits)}; the job (the last model-call region, the list draws to the return) cycles p50 {sorted(job_cycles)[len(job_cycles)//2]}")
jw = sum(c for (w, part), c in writer_of.items() if part == "job") / N; pw = sum(c for (w, part), c in writer_of.items() if part == "prologue") / N; ew = sum(c for (w, part), c in writer_of.items() if part == "epilogue") / N
print(f"words a frame written by the job {jw:.0f}, by the prologue only {pw:.0f}, by the epilogue (after the job) {ew:.0f}")
job_raw = [(w, c) for w, c in hits.items() if writer_of[(w, 'job')] > 0]
print(f"RAW words written by the job: {len(job_raw)} distinct; hits a frame: execute side {sum(hits_side[(w, 'execute')] for w, _ in job_raw) / N:.1f}, draw side {sum(hits_side[(w, 'draw')] for w, _ in job_raw) / N:.1f}")
print("first reader's words (frames):", ", ".join(f"{name_of(table, starts, w) or nearest(w)} {c}" for w, c in first_words.most_common(8)))
print(f"{'hits/frame':>10} {'exec':>7} {'draw':>7} {'reader also writes':>19} {'writer':>9}  word")
for w, c in hits.most_common(70):
    e = hits_side[(w, 'execute')]; d = hits_side[(w, 'draw')]
    share = 100 * readers_writing[w] / max(readers_total[w], 1)
    wr = "job" if writer_of[(w, 'job')] > 0 else ("epilogue" if writer_of[(w, 'epilogue')] > 0 else "prologue")
    print(f"{c / N:10.1f} {e / N:7.1f} {d / N:7.1f} {share:18.0f} % {wr:>9}  {w:08X} {name_of(table, starts, w) or nearest(w)}")
print("\n== the job's RAW words with execute-side readers (inside a job's window) ==")
for w, c in sorted(job_raw, key=lambda x: -hits_side[(x[0], 'execute')])[:30]:
    e = hits_side[(w, 'execute')]
    if e == 0: break
    share = 100 * readers_writing[w] / max(readers_total[w], 1)
    print(f"   {e / N:7.1f} exec hits/frame, readers also write {share:3.0f} %  {w:08X} {name_of(table, starts, w) or nearest(w)}")
