#!/usr/bin/env python3
"""Stage B's timing question (M1-T03 of the guest-services-migration plan), from a shadow trace with
PR #12's 'P' region: per management, the guest cycles of each segment - the painter's retrace wait,
the painter proper, the handlers, the execute window (the execute loop and the scene's execute
sub-phases, up to the draw loop), the draw loop - and the events inside each: interrupt deliveries by
PI cause (0 = the decrementer), the DSP steps, and the regions that read the time base. An event's
place in the execute window depends on when the painter ends; a stage-B design that runs the window
before the painter's end must place or defer each of them.

usage: painter_window_events.py TRACE [TRACE...]"""
import bisect, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from j3d_contract_study import records

CAUSE = {0x0: "decrementer", 0x40: "DSP", 0x100: "VI", 0x400: "PE finish", 0x200: "PE token", 0x20: "AI",
         0x4: "DI", 0x8: "SI", 0x10: "EXI", 0x800: "CP"}
def cause_name(v):
    v &= ~0x10000   # the reset switch's state bit is always set
    if v == 0: return "decrementer"
    names = [n for b, n in CAUSE.items() if b and v & b]
    return "+".join(names) or f"0x{v:X}"

def pct(v, p):
    s = sorted(v); return s[min(len(s) - 1, int(p * len(s)))] if s else 0

for path in sys.argv[1:]:
    recs = list(records(path))
    events = sorted((r[3], r[1], r[2]) for r in recs if r[0] == "E" and r[1] in ("I", "S"))
    ev_c = [e[0] for e in events]
    def between(a, b):
        i, j = bisect.bisect_left(ev_c, a), bisect.bisect_left(ev_c, b)
        return events[i:j]
    p0 = [i for i, r in enumerate(recs) if r[0] == "R" and r[1] == "P" and r[2] == 0]
    seg_cycles = {k: [] for k in ("wait", "painter", "handlers", "execute", "draw")}
    seg_ev = {k: Counter() for k in seg_cycles}
    seg_none = Counter()      # managements whose segment holds no interrupt
    timer = Counter(); n = 0
    first_int_in_exec = []    # cycles from the execute window's start to its first interrupt
    for k, pi in enumerate(p0[:-1]):
        nxt = p0[k + 1]
        P = recs[pi]
        first_x = next((j for j in range(pi + 1, nxt) if recs[j][0] == "R" and recs[j][1] == "X"), None)
        if first_x is None: continue
        first_d = next((j for j in range(first_x, nxt) if recs[j][0] == "R" and recs[j][1] == "D"), None)
        if first_d is None: continue
        # the painter proper ends at the last record before the first execute region
        last_p = max(j for j in range(pi, first_x) if recs[j][0] == "R")
        t_wait0, t_wait1 = P[6], P[7]
        t_paint1 = recs[last_p][7]
        t_x0 = recs[first_x][6]; t_d0 = recs[first_d][6]; t_next = recs[nxt][6]
        segs = {"wait": (t_wait0, t_wait1), "painter": (t_wait1, t_paint1), "handlers": (t_paint1, t_x0),
                "execute": (t_x0, t_d0), "draw": (t_d0, t_next)}
        n += 1
        for name, (a, b) in segs.items():
            seg_cycles[name].append(b - a)
            ints = [e for e in between(a, b) if e[1] == "I"]
            for e in between(a, b):
                seg_ev[name]["DSP step" if e[1] == "S" else cause_name(e[2])] += 1
            if not ints: seg_none[name] += 1
            if name == "execute" and ints: first_int_in_exec.append(ints[0][0] - a)
        for j in range(first_x, first_d):
            r = recs[j]
            if r[0] == "R" and (r[8] & (1 << 6)):
                timer["execute window: regions reading the time base"] += 1
        for j in range(pi, first_x):
            r = recs[j]
            if r[0] == "R" and (r[8] & (1 << 6)):
                timer["painter: regions reading the time base"] += 1
    print(f"##### {path}: {n} managements")
    for name in seg_cycles:
        evs = ", ".join(f"{k} {v / n:.2f}" for k, v in sorted(seg_ev[name].items(), key=lambda kv: -kv[1]))
        print(f"  {name:9s} cycles p10 {pct(seg_cycles[name], .1):>9} p50 {pct(seg_cycles[name], .5):>9} p90 {pct(seg_cycles[name], .9):>9}; "
              f"no interrupt in {100 * seg_none[name] / n:3.0f} % of frames; a frame: {evs}")
    if first_int_in_exec:
        print(f"  the execute window's first interrupt, cycles after its start: p10 {pct(first_int_in_exec, .1)} p50 {pct(first_int_in_exec, .5)} p90 {pct(first_int_in_exec, .9)}")
    for k, v in timer.items(): print(f"  {k}: {v / n:.2f} a frame")
