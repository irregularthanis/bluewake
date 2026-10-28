#!/usr/bin/env python3
"""Rendered tests of build A against build B on this machine: the scenes' frames and the rooms' speed.

  python3 scripts/render_suite.py run APP_A APP_B OUT_DIR --card CARD --states STATES_DIR
                                  [--scenes scripts/render_scenes.json] [--suite quick|full] [--repeat 3]
                                  [--display auto|headless|desktop|none] [--size 1280x800]
                                  [--label-a A] [--label-b B]
  python3 scripts/render_suite.py report OUT_DIR/summary.json [--format terminal|github]

scripts/render_test runs this on a Steam Deck (or any Linux machine) over SSH, or here; use that. Build B is
the reference: there are no stored reference images, because every scene starts from a save state and two runs
from a state are frame-exact (docs/RENDERED_TESTING.md).

Scenes (render_scenes.json): each is one scripts/rendered_run.py run per build from a state in STATES_DIR,
then scripts/frame_compare.py check A B. A scene is identical (every pixel), similar (each image's PSNR at or
above the scene's min_psnr), changed (below it) or failed (a run that crashed, timed out, started in safe mode
or made no frames, or new flicker in A).
Rooms: scripts/bench_rooms.py over the costliest rooms (top 3 quick, top 10 full), A and B alternating in each
room, --repeat runs each. A room is flagged when A's GPU time or busy % differs from B's by more than both
--floor percent and twice the spread between repeats.

OUT_DIR/summary.json has everything; `report` prints it. Exit codes: 0 all pass, 1 a scene failed or
changed or a room was flagged, 2 a usage or setup error.
"""
import argparse
import json
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUICK_ROOMS, FULL_ROOMS = 3, 10


def scenes_for(manifest, suite):
    scenes = json.loads(Path(manifest).read_text(encoding="utf-8"))["scenes"]
    return [s for s in scenes if suite == "full" or s.get("suite", "quick") == "quick"]


def validate(scenes):
    """Problems with a manifest's scenes, as messages."""
    problems, names = [], set()
    for i, s in enumerate(scenes):
        name = s.get("name") or f"scene {i}"
        if not s.get("name"):
            problems.append(f"{name}: no name")
        if name in names:
            problems.append(f"{name}: name used twice")
        names.add(name)
        if not s.get("state"):
            problems.append(f"{name}: no state")
        if not (s.get("capture") or s.get("dump")):
            problems.append(f"{name}: give capture or dump")
        if s.get("dump") and not s.get("smooth"):
            problems.append(f"{name}: dump needs smooth")
        if not isinstance(s.get("max_retraces"), int):
            problems.append(f"{name}: max_retraces must be a number")
        if s.get("suite", "quick") not in ("quick", "full"):
            problems.append(f"{name}: suite is quick or full")
        unknown = set(s) - {"name", "about", "state", "pad", "max_retraces", "capture", "dump", "smooth", "scale",
                            "set", "suite", "min_psnr", "flicker_margin", "region", "timeout"}
        if unknown:
            problems.append(f"{name}: unknown keys {', '.join(sorted(unknown))}")
    return problems


def display_mode(asked):
    if asked != "auto":
        return asked
    if shutil.which("gamescope"):
        return "headless"
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or Path("/tmp/.X11-unix/X0").exists():
        return "desktop"
    return "none"


def is_deck():
    try:
        return Path("/sys/devices/virtual/dmi/id/product_name").read_text().strip() in ("Jupiter", "Galileo")
    except OSError:
        return False


def launcher(app, folder, mode, size):
    """APP for rendered_run.py: the app itself, or a script that starts it under headless gamescope."""
    app = Path(app).resolve()
    if mode != "headless":
        return app
    w, _, h = size.partition("x")
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / f"{app.stem}-gamescope.sh"
    script.write_text(f"#!/bin/sh\nexec gamescope --backend headless -W {w} -H {h} -w {w} -h {h} -- '{app}' \"$@\"\n")
    script.chmod(0o755)
    return script


def environment(mode):
    env = dict(os.environ, APPIMAGE_EXTRACT_AND_RUN="1")
    if mode == "desktop":
        env.setdefault("DISPLAY", ":0")
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return env


def gpu_name():
    try:
        out = subprocess.run(["vulkaninfo", "--summary"], capture_output=True, text=True, timeout=20).stdout
        names = [l.split("=", 1)[1].strip() for l in out.splitlines() if l.strip().startswith("deviceName")]
        return names[0] if names else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def run_scene(scene, apps, out, args, env):
    folder = out / "scenes" / scene["name"]
    cmd = [sys.executable, str(HERE / "rendered_run.py"), str(apps["A"]), str(folder), "--card", str(args.card),
           "--state", str(Path(args.states) / scene["state"]), "--max-retraces", str(scene["max_retraces"]),
           "--timeout", str(scene.get("timeout", 600))]
    for key, flag in (("pad", "--pad"), ("capture", "--capture"), ("dump", "--dump"), ("smooth", "--smooth"),
                      ("scale", "--scale")):
        if scene.get(key) is not None:
            cmd += [flag, str(scene[key])]
    for item in scene.get("set", []):
        cmd += ["--set", item]
    cmd += ["--variant", "A", "--variant", "B", f"APP={apps['B']}"]
    subprocess.run(cmd, env=env, stdout=sys.stdout, stderr=subprocess.STDOUT)
    runs = {}
    results = folder / "results.json"
    for r in (json.loads(results.read_text()) if results.exists() else []):
        runs[r["variant"]] = r
    out_row = {"name": scene["name"], "runs": runs}
    problems = []
    for v in ("A", "B"):
        r = runs.get(v)
        if not r:
            problems.append(f"{v} did not run")
        elif r.get("timed_out"):
            problems.append(f"{v} timed out")
        elif r["exit"] not in (0, 1):
            problems.append(f"{v} exit {r['exit']}")
        elif r.get("safe_mode"):
            problems.append(f"{v} safe mode")
        elif not (r.get("frames") or r.get("dumped")):
            problems.append(f"{v} made no frames")
    if problems:
        out_row.update(verdict="failed", why=", ".join(problems))
        return out_row
    check = folder / "check.json"
    cmd = [sys.executable, str(HERE / "frame_compare.py"), "check", str(folder / "A"), str(folder / "B"),
           "--json", str(check), "--sheet", str(folder / "worst.png"),
           "--min-psnr", str(scene.get("min_psnr", 40)), "--flicker-margin", str(scene.get("flicker_margin", 50))]
    if scene.get("region"):
        cmd += ["--region", scene["region"]]
    subprocess.run(cmd, stdout=sys.stdout, stderr=subprocess.STDOUT)
    if not check.exists():
        out_row.update(verdict="failed", why="frame_compare.py check wrote nothing")
        return out_row
    out_row.update(json.loads(check.read_text()))
    return out_row


def read_rooms_tsv(path):
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if not lines:
        return []
    head = lines[0].split("\t")
    return [dict(zip(head, l.split("\t"))) for l in lines[1:] if l.strip()]


def number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def compare_rooms(rows, floor):
    """Each room's A and B means, their spreads, and whether A differs from B by more than the noise."""
    out = []
    for room in dict.fromkeys(r["room"] for r in rows):
        mine = [r for r in rows if r["room"] == room]
        entry = {"room": room, "name": mine[0].get("name", ""), "flags": []}
        arrived = all(r.get("arrived") == "True" for r in mine)
        if not arrived:
            entry["flags"].append("did not arrive")
        for key in ("gpu_ms", "busy", "rate"):
            values = {v: [x for x in (number(r.get(key)) for r in mine if r["variant"] == v) if x is not None]
                      for v in ("A", "B")}
            if not (values["A"] and values["B"]):
                continue
            a, b = statistics.mean(values["A"]), statistics.mean(values["B"])
            spread = max(max(vs) - min(vs) for vs in values.values())
            delta = a - b
            pct = 100 * delta / b if b else 0.0
            entry[key] = {"a": round(a, 3), "b": round(b, 3), "delta_pct": round(pct, 1), "spread": round(spread, 3)}
            if key != "rate" and abs(pct) > floor and abs(delta) > 2 * spread:
                entry["flags"].append(f"{key} {'+' if pct > 0 else ''}{pct:.1f}%")
        out.append(entry)
    return out


def run(args):
    scenes = scenes_for(args.scenes, args.suite)
    problems = validate(scenes)
    missing = [s["state"] for s in scenes if not (Path(args.states) / s["state"]).is_file()]
    if problems or missing:
        for p in problems:
            print(f"render_suite: {p}", file=sys.stderr)
        for m in missing:
            print(f"render_suite: no state {Path(args.states) / m}", file=sys.stderr)
        return 2
    if not Path(args.card).is_file():
        print(f"render_suite: no card at {args.card}", file=sys.stderr)
        return 2
    try:
        import numpy, PIL  # noqa: F401  (frame_compare.py needs them)
    except ImportError:
        print("render_suite: needs numpy and Pillow (pip install --user numpy pillow)", file=sys.stderr)
        return 2
    mode = display_mode(args.display)
    if mode == "none":
        print("render_suite: no display: install gamescope, or start a desktop session (Desktop Mode on a Deck)",
              file=sys.stderr)
        return 2
    size = args.size or ("1280x800" if is_deck() else "1280x720")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    env = environment(mode)
    apps = {"A": launcher(args.app_a, out / "launch", mode, size),
            "B": launcher(args.app_b, out / "launch", mode, size)}
    if apps["A"] == apps["B"]:
        apps["B"] = launcher(args.app_b, out / "launch-b", mode, size)
    summary = {"host": socket.gethostname(), "machine": platform.platform(), "gpu": gpu_name(),
               "display": f"{mode} {size}" if mode == "headless" else mode, "suite": args.suite,
               "repeat": args.repeat, "a": args.label_a, "b": args.label_b, "scenes": [], "rooms": []}
    print(f"== {len(scenes)} scene(s) on {summary['host']} ({summary['gpu'] or 'GPU unknown'}, {summary['display']})",
          flush=True)
    for n, scene in enumerate(scenes, 1):
        print(f"== scene {n}/{len(scenes)}: {scene['name']}", flush=True)
        summary["scenes"].append(run_scene(scene, apps, out, args, env))
    top = QUICK_ROOMS if args.suite == "quick" else FULL_ROOMS
    print(f"== rooms: the costliest {top}, {args.repeat} run(s) each build", flush=True)
    cmd = [sys.executable, str(HERE / "bench_rooms.py"), str(apps["A"]), str(out / "rooms"), "--card",
           str(args.card), "--rooms", str(HERE / "bench_rooms.tsv"), "--top", str(top), "--repeat",
           str(args.repeat), "--rendered-run", str(HERE / "rendered_run.py"),
           "--variant", "A", "--variant", "B", f"APP={apps['B']}"]
    subprocess.run(cmd, env=env, stdout=sys.stdout, stderr=subprocess.STDOUT)
    summary["rooms"] = compare_rooms(read_rooms_tsv(out / "rooms" / "rooms.tsv"), args.floor)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"== wrote {out / 'summary.json'}")
    return status(summary)


def status(summary):
    bad = any(s.get("verdict") in ("failed", "changed") for s in summary["scenes"])
    return 1 if bad or any(r["flags"] for r in summary["rooms"]) or not summary["rooms"] else 0


def report(summary, fmt):
    def table(head, rows):
        if fmt == "github":
            return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] +
                             ["| " + " | ".join(r) + " |" for r in rows])
        widths = [max(len(x) for x in col) for col in zip(head, *rows)]
        return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in [head, *rows])

    def val(entry, key, side):
        return f"{entry[key][side]:g}" if key in entry else "-"

    title = f"Rendered tests: A {summary['a']} against B {summary['b']}"
    where = f"{summary['host']}, {summary['gpu'] or 'GPU unknown'}, display {summary['display']}, " \
            f"{summary['suite']} suite, {summary['repeat']} run(s) a room"
    scene_rows = []
    for s in summary["scenes"]:
        scene_rows.append([s["name"], s.get("verdict", "?").upper(), str(s.get("images", "-")),
                           f"{s['max_diff']}" if "max_diff" in s else "-",
                           f"{s['min_psnr']:.1f}" if s.get("min_psnr") is not None else "-",
                           f"{s.get('flicker_a', '-')}/{s.get('flicker_b', '-')}", s.get("why", "")])
    room_rows = []
    for r in summary["rooms"]:
        room_rows.append([r["room"], r["name"], val(r, "gpu_ms", "a"), val(r, "gpu_ms", "b"),
                          val(r, "busy", "a"), val(r, "busy", "b"),
                          f"{r['gpu_ms']['delta_pct']:+.1f}%" if "gpu_ms" in r else "-",
                          ", ".join(r["flags"]) or "ok"])
    verdict = "PASS" if status(summary) == 0 else "FAIL"
    heading = (lambda t: f"### {t}") if fmt == "github" else (lambda t: t)
    parts = [heading(title), where, "",
             table(["scene", "verdict", "images", "max diff", "min PSNR", "flicker A/B", "why"], scene_rows)
             if scene_rows else "no scenes", "",
             table(["room", "name", "GPU ms A", "GPU ms B", "busy% A", "busy% B", "GPU Δ", "flag"], room_rows)
             if room_rows else "no rooms ran", "", f"{'**' if fmt == 'github' else ''}{verdict}"
             f"{'**' if fmt == 'github' else ''}"]
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="\n".join(__doc__.splitlines()[2:]))
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("app_a")
    p.add_argument("app_b")
    p.add_argument("out")
    p.add_argument("--card", required=True)
    p.add_argument("--states", required=True)
    p.add_argument("--scenes", default=str(HERE / "render_scenes.json"))
    p.add_argument("--suite", choices=("quick", "full"), default="quick")
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--floor", type=float, default=5.0, help="percent a room must differ by to be flagged")
    p.add_argument("--display", choices=("auto", "headless", "desktop", "none"), default="auto")
    p.add_argument("--size", help="WxH for headless gamescope (default 1280x800 on a Deck, else 1280x720)")
    p.add_argument("--label-a", default="A")
    p.add_argument("--label-b", default="B")
    p = sub.add_parser("report")
    p.add_argument("summary")
    p.add_argument("--format", choices=("terminal", "github"), default="terminal")
    p = sub.add_parser("validate")
    p.add_argument("scenes", nargs="?", default=str(HERE / "render_scenes.json"))
    args = parser.parse_args()
    if args.command == "run":
        sys.exit(run(args))
    if args.command == "report":
        summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
        print(report(summary, args.format))
        sys.exit(status(summary))
    problems = validate(scenes_for(args.scenes, "full"))
    for p in problems:
        print(p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
