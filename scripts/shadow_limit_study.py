#!/usr/bin/env python3
"""The shadow-batch limit study over a BLUEWAKE_SHADOW_TRACE dump.

    shadow_limit_study.py TRACE [--workers N] [--max-cycles C] [--privatize ADDR,...]
                          [--symbols symbols.txt] [--top N]

The trace (runtime/host/src/main.c, shadow_trace_*) holds, per fpc region (one
actor's execute or draw), its guest cycles, the cache lines it read, the words
it wrote and flags for what a shadow run could not keep private; and the
interrupt deliveries, DSP steps and retraces with their cycles.

The study replays each frame's regions in order and forms batches as the
engine would: the region at hand runs on the game thread, the next ones on
workers, as long as the batch's cycles fit before the next interrupt and no
region reads a line an earlier region of the batch wrote (serial-order
read-after-write; write-after-write and write-after-read are settled by the
ordered commit). A region that fails runs on the game thread instead, and the
batch ends there. The frame's critical path is the sum over batches of the
longest region in each; the serial time is the sum of all regions. Overhead is
not modelled: the result is a ceiling for the mechanism at this granularity.

--privatize lists words (hex) excluded from the read-after-write test, for the
rules of the plan (the RNG's words, reduction counters); --symbols names the
serializing addresses through the decompilation's symbols.txt.
"""
from __future__ import annotations

import argparse
import bisect
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

PASS_NAMES = {0x8003E370: "execute", 0x8003E318: "draw"}
FLAGS = [(1 << 0, "read-overflow"), (1 << 1, "write-overflow"), (1 << 2, "hw-read"),
         (1 << 3, "hw-write"), (1 << 4, "alias"), (1 << 5, "fallback"), (1 << 6, "timer"),
         (1 << 7, "psq-fallback"), (1 << 8, "dcbz"), (1 << 9, "interrupt")]
ABORTING = (1 << 2) | (1 << 3) | (1 << 5) | (1 << 6)  # a shadow could not run this region


class Region:
    __slots__ = ("tag", "proc", "pass_", "name", "start", "end", "flags", "alias", "hardware",
                 "read_lines", "write_words", "wlines", "kind", "part", "marker")

    def __init__(self, tag, proc, pass_, name, start, end, flags, alias, hardware, reads, writes,
                 kind="X", part=0, marker=0x80040198):
        self.tag, self.proc, self.pass_, self.name = tag, proc, pass_, name
        self.kind, self.part, self.marker = kind, part, marker
        self.start, self.end, self.flags = start, end, flags
        self.alias, self.hardware = alias, hardware
        self.read_lines = reads
        self.write_words = writes

    @property
    def cycles(self):
        return self.end - self.start


def read_trace(path):
    data = Path(path).read_bytes()
    if data[:4] != b"BWST":
        sys.exit(f"{path}: not a shadow trace")
    version = data[4]
    at = 8
    events, regions = [], []
    n = len(data)
    while at < n:
        kind = data[at:at + 1]
        at += 1
        if kind in (b"I", b"S", b"F"):
            value, cycle = struct.unpack_from("<IQ", data, at)
            at += 12
            events.append((cycle, kind.decode(), value))
        elif kind == b"R":
            if version >= 2:
                (tag, proc, pass_, name, rkind, part, marker, start, end, flags, alias, hw, nr,
                 nw) = struct.unpack_from("<IIIHBBIQQIIIII", data, at)
                at += 4 * 3 + 2 + 1 + 1 + 4 + 8 * 2 + 4 * 5
                rkind = chr(rkind)
            else:
                tag, proc, pass_, name, _pad, start, end, flags, alias, hw, nr, nw = struct.unpack_from(
                    "<IIIHHQQIIIII", data, at)
                at += 4 * 3 + 2 + 2 + 8 * 2 + 4 * 5
                rkind, part, marker = "X", 0, 0x80040198
            reads = struct.unpack_from(f"<{nr}I", data, at)
            at += 4 * nr
            waddr = struct.unpack_from(f"<{nw}I", data, at)
            at += 4 * nw
            wsize = data[at:at + nw]
            at += nw
            words = set()
            for a, s in zip(waddr, wsize):
                for w in range(a & ~3, a + s, 4):
                    words.add(w)
            regions.append(Region(tag, proc, pass_, name, start, end, flags, alias, hw,
                                  frozenset(reads), frozenset(words), rkind, part, marker))
        else:
            sys.exit(f"{path}: bad record {kind!r} at {at - 1}")
    events.sort()
    return events, regions


def load_profiles(path):
    """Process name ids -> profile names, from tww's src/f_pc/f_pc_profile_lst.cpp (ProfileList[] order)."""
    t = Path(path).read_text()
    m = re.search(r"ProfileList\[\]\s*=\s*\{(.*?)\};", t, re.S)
    if not m:
        return {}
    names = {}
    for e in m.group(1).split(","):
        e = e.strip()
        if not e:
            continue
        e = re.sub(r"#.*", "", e).strip()
        e = re.sub(r"^&?g_profile_", "", e).split(".")[0].strip()
        if e:
            names[len(names)] = e
    return names


def load_symbols(path):
    sym = re.compile(r"^(\S+) = \.\S+:0x([0-9A-Fa-f]+); // type:(?:object|function) size:0x([0-9A-Fa-f]+)")
    table = []
    for line in open(path):
        m = sym.match(line)
        if m:
            table.append((int(m.group(2), 16), int(m.group(3), 16), m.group(1)))
    table.sort()
    return table


def name_of(table, addr):
    if not table:
        return ""
    i = bisect.bisect_right([t[0] for t in table], addr) - 1
    if i >= 0 and addr < table[i][0] + table[i][1]:
        return f"{table[i][2]}+0x{addr - table[i][0]:X}"
    return ""


def simulate(events, regions, workers, max_cycles, privatized, conflicts, excluded=(), max_batch=0):
    lanes = workers + 1
    cap = max_batch if max_batch > 0 else lanes
    # the words that count as writes for the RAW test, grouped by line, once per region
    for r in regions:
        if not hasattr(r, 'wlines'):
            by_line = {}
            for w in r.write_words:
                if w in privatized or any(lo <= w < hi for lo, hi in excluded):
                    continue
                by_line.setdefault(w >> 6, []).append(w)
            r.wlines = by_line
    """Per-frame batches; returns (serial, critical, stats)."""
    interrupts = [c for c, k, _ in events if k == "I"]
    retraces = [c for c, k, _ in events if k == "F"]
    serial = critical = 0
    stats = Counter()
    i = 0
    while i < len(regions):
        r0 = regions[i]
        # the window: to the next interrupt after the batch starts
        j = bisect.bisect_right(interrupts, r0.start)
        window = (interrupts[j] - r0.start) if j < len(interrupts) else 1 << 62
        batch = [r0]
        total = r0.cycles
        serial += r0.cycles
        stats["regions"] += 1
        k = i + 1
        while k < len(regions) and len(batch) < cap:
            r = regions[k]
            if r.flags & ABORTING:
                stats["abort"] += 1
                break
            if total + r.cycles > window:
                stats["window"] += 1
                break
            if max_cycles and total + r.cycles > max_cycles:
                stats["max-cycles"] += 1
                break
            dependent = False
            for earlier in batch:
                shared = r.read_lines & earlier.wlines.keys()
                hit = [w for line in shared for w in earlier.wlines[line]]
                if hit:
                    dependent = True
                    for w in hit[:4]:
                        conflicts[w] += 1
                    break
            if dependent:
                stats["raw"] += 1
                break
            batch.append(r)
            total += r.cycles
            serial += r.cycles
            stats["regions"] += 1
            stats["offloaded"] += 1
            k += 1
        if len(batch) <= lanes:
            critical += max(r.cycles for r in batch)
        else:
            lane = [0] * lanes
            for r in sorted(batch, key=lambda x: -x.cycles):
                least = lane.index(min(lane)); lane[least] += r.cycles
            critical += max(lane)
        stats["batches"] += 1
        stats["batch-size-sum"] += len(batch)
        i += len(batch)
    return serial, critical, stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-cycles", type=int, default=0, help="cap a batch's guest cycles (0: the window only)")
    ap.add_argument("--privatize", default="", help="hex words excluded from the RAW test, comma-separated")
    ap.add_argument("--exclude", action="append", default=[],
                    help="hex range LO-HI excluded from the RAW test (the guest stack: a region's own frames), repeatable")
    ap.add_argument("--symbols", help="tww config/GZLE01/symbols.txt, to name addresses")
    ap.add_argument("--profiles", help="tww src/f_pc/f_pc_profile_lst.cpp, to name processes")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--max-batch", type=int, default=0,
                    help="regions a batch may hold (default: workers + 1); larger values model a queue over the workers, "
                         "with the batch's time the longest lane of a greedy assignment")
    args = ap.parse_args(argv)

    events, all_regions = read_trace(args.trace)
    profiles = load_profiles(args.profiles) if args.profiles else {}
    privatized = {int(x, 16) for x in args.privatize.split(",") if x}
    excluded = []
    for r in args.exclude:
        lo, hi = r.split("-")
        excluded.append((int(lo, 16), int(hi, 16)))
    table = load_symbols(args.symbols) if args.symbols else []
    frames = sum(1 for _, k, _ in events if k == "F")
    game_frames = max(1, frames // 2)
    # the sub-phases of the scene's execute, if traced
    for pass_addr, pass_label in ((0x8003E370, "execute"), (0x8003E318, "draw")):
        subs = [r for r in all_regions if r.kind == "S" and r.pass_ == pass_addr]
        if not subs:
            continue
        loop_total = sum(r.cycles for r in all_regions if r.pass_ == pass_addr)
        by_marker = Counter(); n_marker = Counter()
        for r in subs:
            by_marker[r.marker] += r.cycles; n_marker[r.marker] += 1
        print(f"sub-phases of the scene's {pass_label} (share of the {pass_label} loop, calls a game frame, mean cycles):")
        for mk, c in by_marker.most_common():
            print(f"  {100*c/loop_total:5.1f} %  {n_marker[mk]/game_frames:5.1f}/frame  {c/n_marker[mk]:10,.0f}  {name_of(table, mk) or f'{mk:08X}'}")
        scene_parts = [r for r in all_regions if r.kind != "S" and r.pass_ == pass_addr and r.part > 0]
        if scene_parts:
            print(f"  {100*sum(r.cycles for r in scene_parts)/loop_total:5.1f} %  {len(scene_parts)/game_frames:5.1f}/frame  (the scene's own {pass_label} between the sub-phases)")
        print()
    loops = [("execute", [r for r in all_regions if r.pass_ == 0x8003E370]), ("draw", [r for r in all_regions if r.pass_ == 0x8003E318])]
    for loop_name, regions in loops:
        if not regions:
            continue
        print(f"##### {loop_name} loop")
        print(f"regions {len(regions)}, retraces {frames}, interrupts {sum(1 for _, k, _ in events if k == 'I')}, "
              f"dsp steps {sum(1 for _, k, _ in events if k == 'S')}")
        by_pass = Counter(PASS_NAMES.get(r.pass_, f"{r.pass_:08X}") for r in regions)
        print("passes:", dict(by_pass))
        total_cycles = sum(r.cycles for r in regions)
        print(f"region cycles {total_cycles:,} (mean {total_cycles // max(1, len(regions)):,} a region)")
        by_name = defaultdict(lambda: [0, 0])
        for r in regions:
            by_name[r.name][0] += r.cycles; by_name[r.name][1] += 1
        print("heaviest processes (share of the loop, regions a game frame, mean cycles):")
        for nm, (c, n) in sorted(by_name.items(), key=lambda kv: -kv[1][0])[:12]:
            print(f"  {100*c/max(1,total_cycles):5.1f} %  {n/game_frames:5.1f}/frame  {c/n:10,.0f}  {profiles.get(nm, nm)}")
        flag_counts = Counter()
        for r in regions:
            for bit, name in FLAGS:
                if r.flags & bit:
                    flag_counts[name] += 1
        print("flags:", dict(flag_counts))
        alias = sum(r.alias for r in regions)
        print(f"alias accesses {alias:,} over {sum(1 for r in regions if r.alias)} regions")

        for workers in sorted({1, 2, 3, args.workers}):
            conflicts = Counter()
            serial, critical, stats = simulate(events, regions, workers, args.max_cycles, privatized, conflicts, excluded, args.max_batch)
            gain = 1 - critical / serial if serial else 0
            print(f"\nworkers {workers}: serial {serial:,} critical {critical:,} -> {100 * gain:.1f} % off the loop "
                  f"time; batches {stats['batches']}, mean size {stats['batch-size-sum'] / max(1, stats['batches']):.2f}, "
                  f"offloaded {stats['offloaded']} of {stats['regions']} regions; "
                  f"ends: raw {stats['raw']}, window {stats['window']}, abort {stats['abort']}, max {stats['max-cycles']}")
            if workers == args.workers:
                print(f"top serializing words (workers {workers}):")
                for w, n in conflicts.most_common(args.top):
                    print(f"  {w:08X} {n:6d}  {name_of(table, w)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
