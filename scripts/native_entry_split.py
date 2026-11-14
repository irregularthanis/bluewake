#!/usr/bin/env python3
"""For named guest functions: the sampler's share at the function's entry instruction (where a
hooked native's run and the hook itself are attributed, since the guest pc stays there) against
the rest of the body (the translation running: declined calls or no hook).
usage: entry_split.py SYMBOLS PCS NAME_REGEX..."""
import bisect, re, sys
symf, pcsf = sys.argv[1:3]; pats = [re.compile(p) for p in sys.argv[3:]]
SYM = re.compile(r"^(\S+) = \.(\S+):0x([0-9A-Fa-f]+); // type:function size:0x([0-9A-Fa-f]+)")
funcs = []
for line in open(symf):
    m = SYM.match(line)
    if m: funcs.append((int(m.group(3), 16), int(m.group(4), 16), m.group(1)))
funcs.sort(); starts = [f[0] for f in funcs]
idle = re.compile(r"^SelectThread|^OSIdle|^__OSIdle|^PPCHalt|^OSSleepThread|^OSWaitEvent")
samples = {}; busy = 0
for line in open(pcsf):
    p, c = line.split(); pc = int(p, 16); c = int(c)
    i = bisect.bisect_right(starts, pc) - 1
    if i >= 0 and pc < funcs[i][0] + funcs[i][1] and idle.search(funcs[i][2]): continue
    busy += c; samples[pc] = samples.get(pc, 0) + c
print(f"{'function':52s} {'total':>7s} {'entry':>7s} {'body':>7s}   (% of busy samples)")
for pat in pats:
    for a, size, name in funcs:
        if not pat.search(name) or name.startswith("@"): continue
        tot = sum(c for pc, c in samples.items() if a <= pc < a + size)
        if tot == 0: continue
        entry = samples.get(a, 0)
        print(f"{name[:52]:52s} {100 * tot / busy:7.2f} {100 * entry / busy:7.2f} {100 * (tot - entry) / busy:7.2f}")
