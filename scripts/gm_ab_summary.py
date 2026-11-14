#!/usr/bin/env python3
"""Summarize Game Mode A/B runs (gm-launch2.sh run dirs): per run the game FPS (the perf lines'
retrace rate / 2, from 300 retraces after the loaded state's retrace), the busy share, the
[painter] report, and the guest checkpoints; per label the mean FPS; and whether every run's
checkpoints agree at the retraces they share. usage: gmsum.py RUN_DIR [SETTLE=300]"""
import glob, os, re, sys
run_dir = sys.argv[1]; settle = int(sys.argv[2]) if len(sys.argv) > 2 else 300
perf = re.compile(r"\[perf\] retrace=(\d+) rate=([\d.]+) worst_ms=([\d.]+) hitches=(\d+) busy=(\d+)%")
loaded = re.compile(r"\[state\] loaded .* retrace=(\d+)")
ckpt = re.compile(r"\[guest-checkpoint\] version=\d+ retrace=(\d+) cycle=(\d+) cpu=([0-9A-F]+) mem1=([0-9A-F]+)")
runs = []
for d in sorted(glob.glob(os.path.join(run_dir, "[0-9][0-9]-*"))):
    logs = sorted(glob.glob(os.path.join(d, "data", "logs", "session-*.log")), key=os.path.getsize)
    if not logs: print(f"{os.path.basename(d)}: no session log"); continue
    txt = open(logs[-1], errors="replace").read()
    m = loaded.search(txt); base = int(m.group(1)) if m else None
    rates = []; busy = []; worst = []
    for mm in perf.finditer(txt):
        r = int(mm.group(1))
        if base is None or r >= base + settle:
            rates.append(float(mm.group(2))); worst.append(float(mm.group(3))); busy.append(int(mm.group(5)))
    cks = {int(mm.group(1)): (mm.group(2), mm.group(3), mm.group(4)) for mm in ckpt.finditer(txt)}
    painter = [l.strip() for l in txt.splitlines() if "[painter]" in l]
    label = os.path.basename(d).split("-", 1)[1]
    fps = sum(rates) / len(rates) / 2 if rates else float("nan")
    runs.append((os.path.basename(d), label, fps, sum(busy) / len(busy) if busy else 0, max(worst) if worst else 0, cks, painter, base, len(rates)))
    print(f"{os.path.basename(d)}: base={base} perf-lines={len(rates)} fps={fps:.2f} busy={sum(busy) / max(len(busy), 1):.0f}% worst={max(worst) if worst else 0:.1f}ms checkpoints={len(cks)}")
    for l in painter[-2:]: print("    " + l[:220])
labels = sorted({r[1] for r in runs})
print()
for lab in labels:
    v = [r[2] for r in runs if r[1] == lab and r[2] == r[2]]
    if not v: print(f"{lab}: no measured runs"); continue
    print(f"{lab}: fps mean {sum(v) / len(v):.2f} over {len(v)} runs: " + ", ".join(f"{x:.2f}" for x in v))
if len(labels) >= 2:
    a = [r[2] for r in runs if r[1] == labels[0] and r[2] == r[2]]
    for lab in labels[1:]:
        b = [r[2] for r in runs if r[1] == lab and r[2] == r[2]]
        if a and b: print(f"{lab} vs {labels[0]}: {100 * (sum(b) / len(b) / (sum(a) / len(a)) - 1):+.2f} %")
# checkpoints: the retraces every run has, and whether the digests agree
common = None
for r in runs:
    common = set(r[5]) if common is None else common & set(r[5])
common = sorted(common or [])
same = all(len({r[5][c] for r in runs}) == 1 for c in common)
print(f"checkpoints: {len(common)} retraces shared by all runs; {'identical in every run' if same else 'DIFFER'}")
if not same:
    for c in common:
        vals = {r[5][c]: r[0] for r in runs}
        if len(vals) > 1: print(f"  retrace {c}: " + "; ".join(f"{k[1][:8]}/{k[2][:8]} ({v})" for k, v in vals.items()))
