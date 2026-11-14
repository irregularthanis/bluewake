#!/usr/bin/env python3
"""Step 1 of the native go/no-go: for the named guest functions, the sampler's host-time share at a
state and the hot instructions inside them, labelled from the generated chunk source (the
'// ADDR: mnemonic' comments), with the translation path each hot instruction takes (inline, a
helper, or the interpreter's paired-single fallback).
usage: hot_pcs.py SYMBOLS PCS CHUNKDIR FUNC_REGEX... """
import bisect, glob, os, re, sys
symf, pcsf, chunkdir = sys.argv[1:4]; pats = [re.compile(p) for p in sys.argv[4:]]
SYM = re.compile(r"^(\S+) = \.(\S+):0x([0-9A-Fa-f]+); // type:function size:0x([0-9A-Fa-f]+)")
funcs = []
for line in open(symf):
    m = SYM.match(line)
    if m: funcs.append((int(m.group(3), 16), int(m.group(4), 16), m.group(1)))
funcs.sort(); starts = [f[0] for f in funcs]
def fn_of(pc):
    i = bisect.bisect_right(starts, pc) - 1
    return funcs[i] if i >= 0 and pc < funcs[i][0] + funcs[i][1] else None
idle = re.compile(r"^SelectThread|^OSIdle|^__OSIdle|^PPCHalt|^OSSleepThread|^OSWaitEvent")
samples = {}; busy = 0
for line in open(pcsf):
    p, c = line.split(); pc = int(p, 16); c = int(c)
    f = fn_of(pc)
    if f and idle.search(f[2]): continue
    busy += c; samples[pc] = samples.get(pc, 0) + c
chunks = sorted((int(os.path.basename(f).split("_")[3].split(".")[0], 16), f) for f in glob.glob(os.path.join(chunkdir, "chunk_*_text*_*.c")))
chunk_starts = [c[0] for c in chunks]
cache = {}
def instr(pc):
    i = bisect.bisect_right(chunk_starts, pc) - 1
    if i < 0: return "?", ""
    f = chunks[i][1]
    if f not in cache:
        txt = open(f, errors="replace").read().split("\n"); cache[f] = txt
    txt = cache[f]; key = f"// {pc:08X}: "
    for k, l in enumerate(txt):
        if l.strip().startswith(key):
            mn = l.strip()[len(key):]
            body = " ".join(x.strip() for x in txt[k + 1:k + 12])
            path = "interpreter psq" if ("bw_psq_load" in body or "bw_psq_store" in body or "ppc_psq" in body) else ("fallback" if "fallback_instruction" in body else ("helper" if re.search(r"\b(bw_|ppc_)[a-z_0-9]+\(", body) else "inline"))
            return mn, path
    return "?", ""
for pat in pats:
    for a, size, name in funcs:
        if not pat.search(name): continue
        tot = sum(c for pc, c in samples.items() if a <= pc < a + size)
        if tot == 0: continue
        print(f"\n{name} @ {a:08X} size 0x{size:X}: {100 * tot / busy:.2f} % of busy samples; hot instructions:")
        top = sorted(((c, pc) for pc, c in samples.items() if a <= pc < a + size), reverse=True)[:8]
        for c, pc in top:
            mn, path = instr(pc)
            print(f"   {100 * c / tot:5.1f} %  {pc:08X}  {mn:40s} [{path}]")
