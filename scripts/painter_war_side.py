#!/usr/bin/env python3
"""The painter job's reads against the window: lines the job (the painter's longest region: the list
draws to the return) read that the same management's execute side (X, J inside X, S inside the
scene's execute) writes - a job reading live memory would see them if the game thread writes in
place - against the draw side's (after the join); and the job's written words the execute side
writes too (WAW inside the window). By symbol or heap page."""
import bisect, sys
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parent))
from j3d_contract_study import load_symbols, name_of, load_profiles, records
trace, symf, proff = sys.argv[1:4]
table, starts = load_symbols(symf); profiles = load_profiles(proff)
excl = [(0x80408000, 0x8040D000)]
for addr, size, nm in table:
    if nm.startswith("saAudioStack") or nm.startswith("DvdErr_stack"): excl.append((addr, addr + size))
def excluded(w): return any(lo <= w < hi for lo, hi in excl)
recs = list(records(trace))
p0 = [i for i, r in enumerate(recs) if r[0] == "R" and r[1] == "P" and r[2] == 0]
N = 0; war_x = Counter(); war_d = Counter(); war_x_lines = []; war_d_lines = []; waw_x = Counter(); waw_x_words = []
war_x_who = Counter(); first_war = []
for n, pi in enumerate(p0):
    end_i = p0[n + 1] if n + 1 < len(p0) else len(recs)
    j = pi; proper = []; first_x = None
    while j < end_i:
        r = recs[j]
        if r[0] == "R":
            if r[1] == "X": first_x = j; break
            if j > pi: proper.append(r)
        j += 1
    if first_x is None or not proper: continue
    N += 1
    big = max(proper, key=lambda r: r[7] - r[6])
    rl = set(big[9])
    words = set()
    for addr, size in zip(big[10], big[11]):
        w = addr & ~3
        while w < addr + size:
            if not excluded(w): words.add(w)
            w += 4
    side = "execute"; wx = set(); wd = set(); wwx = set(); seen_first = False
    for k in range(first_x, end_i):
        r = recs[k]
        if r[0] != "R": continue
        _, kind, prt, mk, pr, nm, st, en, f, rd, wa, ws, tg, ps = r
        if kind == "X": side = "execute"
        elif kind == "D": side = "draw"
        who = profiles.get(nm, str(nm)) if kind in ("X", "D", "J") else ("sub-phase " + (name_of(table, starts, mk, offset=False) or f"{mk:08X}"))
        for addr, size in zip(wa, ws):
            for l in range(addr >> 6, ((addr + size - 1) >> 6) + 1):
                if l in rl:
                    (wx if side == "execute" else wd).add(l)
                    if side == "execute":
                        war_x_who[(kind, who)] += 1
                        if not seen_first: first_war.append((st - big[7], kind + ":" + who)); seen_first = True
            if side == "execute":
                w = addr & ~3
                while w < addr + size:
                    if w in words: wwx.add(w)
                    w += 4
    war_x_lines.append(len(wx)); war_d_lines.append(len(wd)); waw_x_words.append(len(wwx))
    for l in wx: war_x[name_of(table, starts, l << 6, offset=False) or f"heap page {l << 6 >> 12:05X}000"] += 1
    for l in wd: war_d[name_of(table, starts, l << 6, offset=False) or "heap"] += 1
    for w in wwx: waw_x[name_of(table, starts, w, offset=False) or f"heap page {w >> 12:05X}000"] += 1
def p(v, q): s = sorted(v); return s[min(len(s) - 1, int(q * len(s)))] if s else 0
print(f"managements {N}")
print(f"WAR, execute side (inside the window): lines a frame p50 {p(war_x_lines, .5)} p90 {p(war_x_lines, .9)}; draw side (after the join): p50 {p(war_d_lines, .5)} p90 {p(war_d_lines, .9)}")
fw = [c for c, _ in first_war]
print(f"first execute-side write to a line the job read: in {100 * len(first_war) / N:.0f} % of frames, cycles after the job's end p10 {p(fw, .1)} p50 {p(fw, .5)} p90 {p(fw, .9)}; " + ", ".join(f"{k} {v}" for k, v in Counter(c for _, c in first_war).most_common(5)))
print("  execute-side WAR lines by symbol or heap page (a frame):")
for s, c in war_x.most_common(24): print(f"     {c / N:7.1f}  {s}")
print("  execute-side WAR writers (line-writes a frame):")
for (k, who), c in war_x_who.most_common(16): print(f"     {c / N:7.1f}  {k} {who}")
print(f"WAW inside the window: job-written words the execute side writes too, a frame p50 {p(waw_x_words, .5)} p90 {p(waw_x_words, .9)}")
for s, c in waw_x.most_common(16): print(f"     {c / N:7.1f}  {s}")
print("  draw-side WAR lines by symbol (a frame):")
for s, c in war_d.most_common(10): print(f"     {c / N:7.1f}  {s}")
