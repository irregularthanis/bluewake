#!/usr/bin/env python3
"""Model-call jobs at wrapper granularity (M1-T02 of the guest-services-migration plan).

A job is one mDoExt_modelUpdate / modelUpdateDL / modelEntry / modelEntryDL / modelDiff call:
the J3DModel calls it makes (calc or update, entry, viewCalc; PR #12's 'J' regions, whose pass
is the call site) together with the slices of the actor's own region between them (calcMaterial
and diff: J3D code, unmarked). The job's outputs are the words those regions write outside the
stack. For every job: its guest cycles, its abort flags, and the first same-frame reader of its
outputs - the actor's own code after the wrapper (with the position of the first hit inside that
slice, from the slice's read lines in first-touch order), another model call of the same actor,
another actor's model call, execute or draw, or a scene sub-phase - and the window in guest
cycles from the job's end to that reader. Also the window under the one-job-in-flight policy
(the next model call anywhere, or the next interrupt or DSP step, whichever comes first) and the
overlap it allows: min(job, window), summed, against the loop's cycles.

usage: j3d_wrapper_jobs.py TRACE --symbols SYMBOLS.txt --profiles f_pc_profile_lst.cpp
       [--exclude LO-HI]... [--top N] [--dump N]
"""
import argparse, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from j3d_contract_study import load_symbols, name_of, load_profiles, records, CALLS

WRAP = {0x8000F7FC: "modelUpdate", 0x8000F81C: "modelUpdate", 0x8000F838: "modelUpdate",
        0x8000F7A8: "modelDiff",
        0x8000F88C: "modelUpdateDL", 0x8000F8C8: "modelUpdateDL", 0x8000F8E4: "modelUpdateDL",
        0x8000F944: "modelEntry", 0x8000F960: "modelEntry", 0x8000F9DC: "modelEntryDL", 0x8000F9F8: "modelEntryDL"}
LAST = {0x8000F838, 0x8000F8E4, 0x8000F960, 0x8000F9F8}            # viewCalc: the wrapper's last call
OPENERS = {0x8000F7FC, 0x8000F81C, 0x8000F88C, 0x8000F8C8, 0x8000F944, 0x8000F9DC}
FLAGS = {1 << 2: "hw-read", 1 << 3: "hw-write", 1 << 4: "alias", 1 << 5: "fallback", 1 << 6: "timer",
         1 << 7: "psq-fallback", 1 << 8: "dcbz", 1 << 9: "interrupt", 1 << 0: "read-overflow", 1 << 1: "write-overflow"}

def pct(v, p):
    if not v: return 0
    s = sorted(v); return s[min(len(s) - 1, int(p * len(s)))]

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("trace"); ap.add_argument("--symbols", required=True); ap.add_argument("--profiles", required=True)
    ap.add_argument("--exclude", action="append", default=["80408000-8040D000"])
    ap.add_argument("--top", type=int, default=24); ap.add_argument("--dump", type=int, default=0)
    ap.add_argument("--named", action="store_true", help="count the named (symbol-bearing) words among a job's outputs too")
    ap.add_argument("--chain", type=int, default=0, help="a same-actor model call reading a job's outputs within this many cycles joins the job (a chain on one worker)")
    ap.add_argument("--hits", type=int, default=0, help="print the first N immediate own-code hits: the line, the job's words in it, the slice")
    a = ap.parse_args(argv)
    table, starts = load_symbols(a.symbols); profiles = load_profiles(a.profiles)
    excl = [(int(lo, 16), int(hi, 16)) for lo, hi in (x.split("-") for x in a.exclude)]
    def excluded(w):
        if any(lo <= w < hi for lo, hi in excl): return True
        return (not a.named) and bool(name_of(table, starts, w, offset=False))

    regions = []        # (kind, part, marker, proc, name, frame, tag, pass_, cycles, start, end, flags)
    jobs = []           # dicts
    open_job = {}       # proc -> job dict
    pending = {}        # line -> {word: job_idx}
    resolved = {}       # job_idx -> (reader_idx, class, window, position)
    events = []         # cycles of I/S events, in order
    game_frame = 0; last_kind = ""; last_kind_of_proc = {}; scene_proc = None
    loop_cycles = Counter(); dumped = 0; j_seen = False

    def close(job):
        # a chain: the previous job of this actor named this call as its continuation
        for ji in range(len(jobs) - 1, max(len(jobs) - 6, -1), -1):
            prev = jobs[ji]
            if prev["proc"] == job["proc"] and prev.get("chain_to") is not None and prev["chain_to"] >= job["start_idx"] and ji not in resolved:
                prev["cycles"] += job["cycles"] + (job["start"] - prev["end"]); prev["end"] = job["end"]; prev["flags"] |= job["flags"]
                prev["calls"] += job["calls"]; prev["writes"] += job["writes"]; prev["chain_to"] = None
                words = set()
                for (waddr, wsize) in job["writes"]:
                    for addr, size in zip(waddr, wsize):
                        w = addr & ~3
                        while w < addr + size:
                            if not excluded(w): words.add(w)
                            w += 4
                prev["words"] += len(words)
                for w in words: pending.setdefault(w >> 6, {})[w] = ji
                prev["end_idx"] = len(regions) - 1
                return
        words = set()
        for (waddr, wsize) in job["writes"]:
            for addr, size in zip(waddr, wsize):
                w = addr & ~3
                while w < addr + size:
                    if not excluded(w): words.add(w)
                    w += 4
        job["words"] = len(words)
        ji = len(jobs); jobs.append(job)
        for w in words:
            pending.setdefault(w >> 6, {})[w] = ji
        job["end_idx"] = len(regions) - 1

    def finish_frame():
        pending.clear()

    for rec in records(a.trace):
        if rec[0] == "E":
            if rec[1] == "F":
                pass
            else:
                events.append(rec[3])
            continue
        _, kind, part, marker, proc, name, start, end, flags, reads, waddr, wsize, tag, pass_ = rec
        if kind == "X" and last_kind in ("D", "J") and any(r[0] == "D" for r in regions[-3:]):
            game_frame += 1; finish_frame()
        if kind != "J": last_kind = kind
        frame = game_frame
        enclosing = last_kind_of_proc.get(proc, "?") if kind == "J" else ""
        if kind != "J": last_kind_of_proc[proc] = kind
        idx = len(regions)
        regions.append((kind, part, marker, proc, name, frame, tag, pass_, end - start, start, end, flags, enclosing))
        loop_cycles[enclosing if kind == "J" else kind] += end - start
        if kind == "S" and scene_proc is None: scene_proc = proc
        if kind == "J": j_seen = True
        if a.dump and j_seen and dumped < a.dump:
            print(f"  rec {idx}: {kind} part={part} proc={proc:08X} name={name} tag={tag:08X} pass={pass_:08X} "
                  f"{CALLS.get(marker, '')} cycles={end - start} reads={len(reads)} writes={len(waddr)}"); dumped += 1

        # a job of another proc still open: the actor's region ended without a viewCalc
        for p in [p for p in open_job if p != proc]:
            close(open_job.pop(p))
        # this record as a reader of the closed jobs
        if pending:
            n = len(reads) or 1
            for i, line in enumerate(reads):
                hit = pending.get(line)
                if not hit: continue
                for w, ji in hit.items():
                    if ji in resolved: continue
                    job = jobs[ji]
                    if kind == "J" and proc == job["proc"] and a.chain and start - job["end"] <= a.chain and open_job.get(proc) is None:
                        # the chain: this call joins the job; its own writes are added when it closes (below)
                        job["chained"] = job.get("chained", 0) + 1; job["chain_to"] = idx
                        continue
                    if kind == "J" and proc == job["proc"]:
                        cls = "same actor: another model's call"
                    elif proc == job["proc"]:
                        cls = "own code after the wrapper" if idx == job["end_idx"] + 1 else ("own code later (" + kind + ")")
                    elif kind == "J": cls = "other actor: a model call"
                    elif proc == scene_proc: cls = ("scene sub-phase " + (name_of(table, starts, marker, offset=False) or f"{marker:08X}")) if kind == "S" else "scene: execute/draw"
                    else: cls = {"X": "other actor: execute", "D": "other actor: draw", "S": "other actor: sub-phase"}[kind]
                    f = i / n
                    window = (start - job["end"]) + (f * (end - start) if proc == job["proc"] and kind != "J" else 0)
                    resolved[ji] = (idx, cls, max(window, 0), f)
                    if a.hits and cls == "own code after the wrapper" and window < 500:
                        a.hits -= 1
                        jw = sorted(hit.keys())
                        print(f"  hit: {profiles.get(job['name'], job['name'])} {job['wrapper']} job {job['cycles']} cyc, slice {end - start} cyc {len(reads)} lines; "
                              f"line {line << 6:08X} ({name_of(table, starts, line << 6) or 'heap'}) job words in it: {', '.join(f'{w:08X}' for w in jw)}; read #{i}")
        # the job accumulation
        j = open_job.get(proc)
        if kind == "J" and pass_ not in WRAP:    # a direct call (mDoExt_McaMorf::calc, the player, REL actors): a job of its own
            if j is not None: close(open_job.pop(proc))
            p = pass_ & ~0x40000000
            site = name_of(table, starts, p, offset=False) or ("REL" if p >= 0x80500000 else f"{p:08X}")
            open_job[proc] = {"proc": proc, "name": name, "tag": tag, "frame": frame, "wrapper": site,
                              "enclosing": enclosing, "start": start, "end": end, "cycles": end - start, "writes": [(waddr, wsize)],
                              "flags": flags, "calls": [CALLS.get(marker, "?")], "closed_by_last": True, "start_idx": idx}
            close(open_job.pop(proc)); j = None
        elif kind == "J" and pass_ in WRAP:
            if j is not None and (tag != j["tag"] or pass_ in OPENERS or j["closed_by_last"]):
                close(open_job.pop(proc)); j = None
            if j is None:
                j = open_job[proc] = {"proc": proc, "name": name, "tag": tag, "frame": frame, "wrapper": WRAP[pass_],
                                      "enclosing": enclosing, "start": start, "end": end, "cycles": 0, "writes": [],
                                      "flags": 0, "calls": [], "closed_by_last": False, "start_idx": idx}
            j["cycles"] += end - start; j["end"] = end; j["writes"].append((waddr, wsize)); j["flags"] |= flags
            j["calls"].append(CALLS.get(marker, "?"))
            if pass_ in LAST:
                j["closed_by_last"] = True
                close(open_job.pop(proc))
        elif j is not None:
            if kind == "J":                      # a model call outside the wrappers: the job ended
                close(open_job.pop(proc))
            else:                                # the actor's own slice between two of the wrapper's calls
                j["cycles"] += end - start; j["end"] = end; j["writes"].append((waddr, wsize)); j["flags"] |= flags
        # the writes of a non-job record supersede pending words
        if kind != "J" and open_job.get(proc) is None and pending:
            for addr, size in zip(waddr, wsize):
                w = addr & ~3
                while w < addr + size:
                    hit = pending.get(w >> 6)
                    if hit and w in hit: del hit[w]
                    w += 4
    for p in list(open_job): close(open_job.pop(p))
    frames = max(game_frame, 1)

    # the next model call anywhere and the next event after each job's end
    j_starts = sorted(r[9] for r in regions if r[0] == "J")
    import bisect
    for ji, job in enumerate(jobs):
        k = bisect.bisect_right(j_starts, job["end"])
        job["next_call"] = (j_starts[k] - job["end"]) if k < len(j_starts) else None
        k = bisect.bisect_right(events, job["end"])
        job["next_event"] = (events[k] - job["end"]) if k < len(events) else None
        r = resolved.get(ji)
        job["reader"] = r[1] if r else "none in the frame"
        job["window"] = r[2] if r else None
        job["pos"] = r[3] if r else None

    print(f"##### {a.trace}  (jobs: the mDoExt wrapper calls)")
    print(f"frames {frames}, regions {len(regions)}, jobs {len(jobs)} ({len(jobs) / frames:.1f} a frame); loop cycles a frame: "
          + ", ".join(f"{k} {v / frames:.0f}" for k, v in sorted(loop_cycles.items())))
    for side in ("X", "D"):
        js = [j for j in jobs if j["enclosing"] == side]
        if not js: continue
        print(f"\n== jobs inside {side} regions: {len(js) / frames:.1f} a frame, {sum(j['cycles'] for j in js) / frames:.0f} cycles a frame "
              f"({100 * sum(j['cycles'] for j in js) / max(loop_cycles['X' if side == 'X' else 'D'] + loop_cycles[side], 1):.1f} % of that loop's cycles, the jobs included), "
              f"cycles a job p10 {pct([j['cycles'] for j in js], .1)} p50 {pct([j['cycles'] for j in js], .5)} p90 {pct([j['cycles'] for j in js], .9)}; words a job p50 {pct([j['words'] for j in js], .5)} ==")
        byw = Counter(j["wrapper"] + ":" + "+".join(j["calls"]) for j in js)
        if a.chain: print(f"  chains: {sum(1 for j in js if j.get('chained'))} jobs absorbed a later call of the same actor ({a.chain}-cycle rule)")
        print("  shapes: " + ", ".join(f"{k} {v / frames:.1f}/frame" for k, v in byw.most_common(8)))
        fl = Counter()
        for j in js:
            for bit, nm in FLAGS.items():
                if j["flags"] & bit: fl[nm] += 1
        print("  flags (jobs carrying one): " + (", ".join(f"{k} {100 * v / len(js):.1f} %" for k, v in fl.most_common()) or "none"))
        byr = Counter(j["reader"] for j in js)
        print("  first same-frame reader of the job's outputs (share of jobs; window cycles p10/p50/p90):")
        for cls, n in byr.most_common():
            ws = [j["window"] for j in js if j["reader"] == cls and j["window"] is not None]
            extra = ""
            if cls == "own code after the wrapper":
                ps = [j["pos"] for j in js if j["reader"] == cls]
                extra = f"; first hit at read-line position p10 {pct(ps, .1):.2f} p50 {pct(ps, .5):.2f} p90 {pct(ps, .9):.2f} of the slice (0 = its first line)"
            print(f"    {cls:46s} {100 * n / len(js):5.1f} %   {pct(ws, .1):>9.0f} {pct(ws, .5):>9.0f} {pct(ws, .9):>9.0f}{extra}")
        # the policy: one job in flight, joined at the first reader, the next model call anywhere, or the next event
        tot = sum(j["cycles"] for j in js); ov1 = ov2 = ov3 = 0; cut_call = cut_event = 0
        for j in js:
            w = j["window"] if j["window"] is not None else (j["next_call"] or 0)
            ov1 += min(j["cycles"], w)
            w2 = min(w, j["next_call"] if j["next_call"] is not None else w)
            if w2 < w: cut_call += 1
            ov2 += min(j["cycles"], w2)
            w3 = min(w2, j["next_event"] if j["next_event"] is not None else w2)
            if w3 < w2: cut_event += 1
            ov3 += min(j["cycles"], w3)
        print(f"  overlap allowed (sum of min(job, window) over the jobs, against the jobs' cycles): first reader only {100 * ov1 / tot:.1f} %; "
              f"also joined at the next model call anywhere {100 * ov2 / tot:.1f} % (cuts {100 * cut_call / len(js):.0f} % of the jobs); "
              f"also at the next interrupt or DSP step {100 * ov3 / tot:.1f} % (cuts {100 * cut_event / len(js):.0f} %)")
        # per actor type
        print(f"  by actor type (jobs a frame, cycles a job, flags, first reader, window p50, overlap under the full policy):")
        byt = defaultdict(list)
        for j in js: byt[profiles.get(j["name"], str(j["name"]))].append(j)
        for t, lst in sorted(byt.items(), key=lambda kv: -sum(j["cycles"] for j in kv[1]))[:a.top]:
            tot_t = sum(j["cycles"] for j in lst); ov = 0; fl = Counter()
            for j in lst:
                w = j["window"] if j["window"] is not None else (j["next_call"] or 0)
                if j["next_call"] is not None: w = min(w, j["next_call"])
                if j["next_event"] is not None: w = min(w, j["next_event"])
                ov += min(j["cycles"], w)
                for bit, nm in FLAGS.items():
                    if j["flags"] & bit: fl[nm] += 1
            byr = Counter(j["reader"] for j in lst)
            top = ", ".join(f"{c} {100 * n / len(lst):.0f} %" for c, n in byr.most_common(2))
            print(f"    {t:14s} {len(lst) / frames:5.1f}/frame  {tot_t / len(lst):7.0f} cyc  flags[{', '.join(f'{k} {100 * v / len(lst):.0f}%' for k, v in fl.most_common(3)) or '-'}]  "
                  f"{top}; window p50 {pct([j['window'] for j in lst if j['window'] is not None], .5):.0f}; overlap {100 * ov / tot_t:.0f} %")

if __name__ == "__main__":
    main()
