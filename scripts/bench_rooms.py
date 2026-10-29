#!/usr/bin/env python3
"""Time the stage select's costliest rooms rendered, with their GPU time, the way the timed sweep did.

  python3 bench_rooms.py APP OUT_DIR --card CARD [--rooms rooms.tsv] [--top N] [--repeat N] [--unpaced]
                         [--frames 600] [--warp-file 1] [--set KEY=VALUE ...] [--variant NAME [KEY=VALUE ...]] ...

Each room is a warp (BLUEWAKE_WARP=stage:room:point) from quest log --warp-file on CARD, run by
scripts/rendered_run.py with Aurora's GPU profiler on (DOL_AURORA_GPU_PROF=1), for
--frames play frames after Link arrives. A room's numbers come from its log after the "[warp] arrived" line,
the first reading left out, as the October 25 sweep ranked them (tools/bench/sweep470-*/rank.py):
  rate       the median [perf] rate, retraces a second (60 is full speed; game frames a second are half)
  busy       the median game-thread busy %
  gpu_ms     the median GPU busy time a frame from the [gpu-prof] reports (every 240 frames)
  zones      the last report's three costliest zones
Paced (the default), the rate stops at full speed: compare busy and gpu_ms. A GPU near a frame's budget
(16.7 ms at 60 retraces) with the game thread below 100% busy is a GPU limit; the other way round is the
CPU. --unpaced runs as fast as it can, so the rate is the speed.

Rooms are run one after another, and within a room every variant in turn (builds or settings alternate,
so a slow drift - heat, battery - affects them alike). OUT_DIR gets each room's runs (rendered_run.py's
folders), rooms.tsv with a line per run and a table at the end.

--rooms takes picks.txt (place, stage:room:point, name, ...) or ranked.tsv (with its header) from the
sweep; the default is bench_rooms.tsv beside this script. rendered_run.py is looked for with --rendered-run,
then scripts/rendered_run.py under the current folder, then beside this script.

Example on the Steam Deck (Desktop Mode, so the game has a display), the top 3, the build against 0.9.0,
twice each, at render scale 2:
  python3 bench_rooms.py ~/BlueWake-x86_64.AppImage out/deck --card ~/my.card --top 3 --repeat 2 \\
      --set DOL_AURORA_RENDER_SCALE=2 --variant new --variant v090 APP=$HOME/BlueWake-0.9.0.AppImage
Settings against each other, one build:
  python3 bench_rooms.py ~/BlueWake-x86_64.AppImage out/filter --card ~/my.card --top 3 \\
      --variant aniso16 DOL_AURORA_FORCE_ANISO=16 --variant aniso1 DOL_AURORA_FORCE_ANISO=1
"""
import argparse
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

PERF = re.compile(r"\[perf\] retrace=\d+ rate=([\d.]+) worst_ms=[\d.]+ hitches=\d+ busy=([\d.]+)%")
GPU = re.compile(r"\[gpu-prof\] frames=\d+ frame_ms=[\d.]+ max=[\d.]+ busy_ms=([\d.]+)")
ZONE = re.compile(r"\| ([^|]+?) (\d+\.\d+) x\d+(?:\.\d+)?")
CODE = re.compile(r"^[A-Za-z0-9_]+:\d+:\d+(?::\d+)?$")


def read_rooms(path):
    """(place, stage:room:point, name) for each room in picks.txt or ranked.tsv."""
    lines = [l.rstrip("\n").split("\t") for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if lines and "stage" in lines[0] and "room" in lines[0]:
        head, rows = lines[0], lines[1:]
        col = {name: head.index(name) for name in ("place", "name", "stage", "room", "point")}
        return [(r[col["place"]], f"{r[col['stage']]}:{r[col['room']]}:{r[col['point']]}", r[col["name"]])
                for r in rows]
    rooms = []
    for r in lines:
        code = next((f for f in r if CODE.match(f)), None)
        if code:
            rooms.append((r[0], code, r[2] if len(r) > 2 and r[2] != code else ""))
    return rooms


def after_arrival(log):
    """What a run's log says after Link arrives."""
    text = log.read_text(errors="replace") if log.exists() else ""
    at = text.find("[warp] arrived")
    if at < 0:
        return {"arrived": False}
    perf = PERF.findall(text[at:])
    perf = perf[1:] if len(perf) > 3 else perf
    gpus = [l for l in text[at:].splitlines() if GPU.search(l)]
    out = {"arrived": True}
    if perf:
        out["rate"] = round(statistics.median(float(r) for r, _ in perf), 1)
        out["busy"] = round(statistics.median(float(b) for _, b in perf), 1)
    if gpus:
        out["gpu_ms"] = round(statistics.median(float(GPU.search(l).group(1)) for l in gpus), 3)
        zones = sorted(((float(ms), name.strip()) for name, ms in ZONE.findall(gpus[-1])), reverse=True)
        out["zones"] = ", ".join(f"{name} {ms:.2f}" for ms, name in zones[:3])
    return out


def find_rendered_run(given):
    for path in ([given] if given else []) + [Path.cwd() / "scripts/rendered_run.py",
                                              Path(__file__).resolve().parent / "rendered_run.py"]:
        if path and Path(path).is_file():
            return Path(path)
    sys.exit("rendered_run.py not found: pass --rendered-run PATH, or run from a checkout "
             "(scripts/rendered_run.py)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="\n".join(__doc__.splitlines()[2:]))
    parser.add_argument("app", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--card", type=Path, required=True)
    parser.add_argument("--rooms", type=Path, default=Path(__file__).resolve().parent / "bench_rooms.tsv")
    parser.add_argument("--top", type=int, help="only the first N rooms (the costliest)")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--frames", type=int, default=600, help="play frames after Link arrives")
    parser.add_argument("--warp-file", type=int, default=1, help="the card's quest log to warp from")
    parser.add_argument("--unpaced", action="store_true")
    parser.add_argument("--rendered-run", type=Path)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--variant", action="append", nargs="+", default=[], metavar=("NAME", "KEY=VALUE"))
    args = parser.parse_args()
    if not args.app.exists():
        sys.exit(f"no such app: {args.app}")
    if not args.card.is_file():
        sys.exit(f"no card at {args.card}")
    runner = find_rendered_run(args.rendered_run)
    rooms = read_rooms(args.rooms)[:args.top] if args.top else read_rooms(args.rooms)
    if not rooms:
        sys.exit(f"no rooms in {args.rooms}")
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, (place, code, name) in enumerate(rooms, 1):
        folder = args.out / f"{n:02d}-{code.replace(':', '_')}"
        print(f"[{n}/{len(rooms)}] {place} {code} {name}", flush=True)
        cmd = [sys.executable, str(runner), str(args.app), str(folder), "--card", str(args.card),
               "--warp", code, "--warp-file", str(args.warp_file), "--stop-after", str(args.frames),
               # An empty quest log leaves the game at the file select: end that run at once, and any run that
               # does not finish within 5 minutes.
               "--stop-on", "is empty; stopped pressing A", "--timeout", "300",
               "--gpu-prof", "--repeat", str(args.repeat), "--set", "BLUEWAKE_PERF_LOG=1",
               "--set", "BLUEWAKE_LOOSE_REL_RETRACES=1"]
        cmd += ["--unpaced"] if args.unpaced else []
        for item in args.set:
            cmd += ["--set", item]
        for variant in args.variant:
            cmd += ["--variant", *variant]
        subprocess.run(cmd)
        results = folder / "results.json"
        for run in (json.loads(results.read_text()) if results.exists() else []):
            log = (folder / run["run"] / "log.txt") if run["run"] != folder.name else folder / "log.txt"
            rows.append({"place": place, "room": code, "name": name, "variant": run["variant"] or "-",
                         "run": run["run"], "exit": run["exit"], **after_arrival(log)})
    keys = ("place", "room", "name", "variant", "run", "exit", "arrived", "rate", "busy", "gpu_ms", "zones")
    with open(args.out / "rooms.tsv", "w", encoding="utf-8") as tsv:
        tsv.write("\t".join(keys) + "\n")
        for r in rows:
            tsv.write("\t".join(str(r.get(k, "")) for k in keys) + "\n")
    print(f"\n{'room':22} {'variant':10} {'rate':>6} {'busy%':>6} {'gpu ms':>7}  costliest GPU zones")
    for code in dict.fromkeys(r["room"] for r in rows):
        for variant in dict.fromkeys(r["variant"] for r in rows if r["room"] == code):
            mine = [r for r in rows if r["room"] == code and r["variant"] == variant]
            mean = lambda k: (f"{statistics.mean(r[k] for r in mine):.1f}" if all(k in r for r in mine) else "-")
            gpu = (f"{statistics.mean(r['gpu_ms'] for r in mine):.2f}" if all("gpu_ms" in r for r in mine)
                   else "-")
            note = "" if all(r["arrived"] for r in mine) else "  (did not arrive)"
            print(f"{code:22} {variant:10} {mean('rate'):>6} {mean('busy'):>6} {gpu:>7}  "
                  f"{mine[-1].get('zones', '')}{note}")
    print(f"\n{args.out / 'rooms.tsv'} has every run")


if __name__ == "__main__":
    main()
