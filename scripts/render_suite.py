#!/usr/bin/env python3
"""Rendered tests of build A against build B on this machine: the scenes' frames and the rooms' speed.

  python3 scripts/render_suite.py collect APP_A APP_B OUT_DIR --card CARD --states STATES_DIR
                                  [--scenes scripts/render_scenes.json] [--suite quick|full] [--repeat 3]
                                  [--display auto|headless|desktop|none] [--size 1280x800]
                                  [--label-a A] [--label-b B]
  python3 scripts/render_suite.py differing OUT_DIR
  python3 scripts/render_suite.py analyze OUT_DIR [--floor 5]
  python3 scripts/render_suite.py run ...          (collect, then analyze, on one machine)
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

collect is the part that renders, on the target; it needs only python3 (no numpy): it runs the scenes and
rooms and writes OUT_DIR/collected.json and a SHA-256 for every frame (scenes/NAME/hashes.json). differing names
the scenes whose frames differ between A and B, the only frames that need copying back. analyze, where numpy
and Pillow are, judges the scenes (identical by their hashes alone, the rest with frame_compare.py check) and the
rooms, and writes OUT_DIR/summary.json; `report` prints it. Exit codes: 0 all pass, 1 a scene failed or
changed or a room was flagged, 2 a usage or setup error.
"""
import argparse
import gzip
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUICK_ROOMS, FULL_ROOMS = 3, 10


PERF = re.compile(r"\[perf\] retrace=(\d+)")


def scenes_for(manifest, suite):
    scenes = json.loads(Path(manifest).read_text(encoding="utf-8"))["scenes"]
    return [s for s in scenes if suite == "full" or s.get("suite", "quick") == "quick"]


def recipes_for(manifest):
    """How to make each state the scenes use: {file name: {warp, time, file, settle}}."""
    return json.loads(Path(manifest).read_text(encoding="utf-8")).get("states", {})


def state_retrace(path):
    """The retrace a save state was made at (its BWSTATE1 header), or None if it is not a save state.

    As scripts/bench_tour.py reads it: gzip; HostStateHeader (main.c) has the retrace as the little-endian u64
    at byte 32 of the HEADER chunk."""
    try:
        with gzip.open(path, "rb") as handle:
            if handle.read(8) != b"BWSTATE1":
                return None
            handle.read(4)
            if not handle.read(16).startswith(b"HEADER") or int.from_bytes(handle.read(8), "little") < 40:
                return None
            header = handle.read(40)
    except (OSError, EOFError):
        return None
    return int.from_bytes(header[32:40], "little") if len(header) == 40 else None


def shifted(scene, base):
    """The scene's retraces (counted from its state) as the game counts them: from boot, the state's on."""
    out = {"max_retraces": base + scene["length"]}
    if scene.get("pad"):
        presses = []
        for press in scene["pad"].split(","):
            first, _, rest = press.partition(":")
            presses.append(f"{base + int(first)}:{rest}")
        out["pad"] = ",".join(presses)
    if scene.get("capture"):
        first, _, every = scene["capture"].partition(":")
        out["capture"] = f"{base + int(first)}:{every}"
    return out


def validate(scenes, recipes=None):
    """Problems with a manifest's scenes and state recipes, as messages."""
    problems, names = [], set()
    for state, recipe in (recipes or {}).items():
        if not re.match(r"^[A-Za-z0-9_]+:\d+:\d+(:\d+)?$", str(recipe.get("warp", ""))):
            problems.append(f"state {state}: warp must be stage:room:point[:layer]")
        unknown = set(recipe) - {"about", "warp", "time", "file", "settle"}
        if unknown:
            problems.append(f"state {state}: unknown keys {', '.join(sorted(unknown))}")
    for i, s in enumerate(scenes):
        name = s.get("name") or f"scene {i}"
        if not s.get("name"):
            problems.append(f"{name}: no name")
        if name in names:
            problems.append(f"{name}: name used twice")
        names.add(name)
        if not s.get("state"):
            problems.append(f"{name}: no state")
        if s.get("tour"):
            if s["tour"] not in ("default", "untrained"):
                problems.append(f"{name}: tour is default or untrained")
            if not isinstance(s.get("every"), int) or s.get("every", 0) <= 0:
                problems.append(f"{name}: every (retraces between a tour's captures) must be a positive number")
            for key in ("length", "pad", "capture", "dump"):
                if key in s:
                    problems.append(f"{name}: a tour scene has no {key}")
            unknown = set(s) - {"name", "about", "state", "tour", "every", "scale", "set", "suite", "min_psnr",
                                "flicker_margin", "region", "timeout"}
            if unknown:
                problems.append(f"{name}: unknown keys {', '.join(sorted(unknown))}")
            if s.get("suite", "quick") not in ("quick", "full"):
                problems.append(f"{name}: suite is quick or full")
            continue
        if not (s.get("capture") or s.get("dump")):
            problems.append(f"{name}: give capture or dump")
        if s.get("dump") and not s.get("smooth"):
            problems.append(f"{name}: dump needs smooth")
        if not isinstance(s.get("length"), int) or s.get("length", 0) <= 0:
            problems.append(f"{name}: length (retraces after the state) must be a positive number")
        for press in (s.get("pad") or "").split(",") if s.get("pad") else []:
            if not re.match(r"^\d+:0x[0-9A-Fa-f]+:\d+", press):
                problems.append(f"{name}: pad press {press!r} is not RETRACES_AFTER_STATE:0xBUTTONS:LENGTH")
        if s.get("suite", "quick") not in ("quick", "full"):
            problems.append(f"{name}: suite is quick or full")
        unknown = set(s) - {"name", "about", "state", "pad", "length", "capture", "dump", "smooth", "scale",
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


def tour_timing(scene, base):
    """A tour scene as rendered_run.py options, and its stops as (name, first retrace, end retrace). The tour
    is scripts/bench_tour.py's, warped every 1800 retraces from just after the state (retrace BASE)."""
    import bench_tour
    stops = bench_tour.DEFAULT_STOPS if scene["tour"] == "default" else bench_tour.UNTRAINED_STOPS
    every, start = scene["every"], base + 10
    timed = {"max_retraces": bench_tour.tour_end(stops, start=start),
             "capture": f"{start + bench_tour.SETTLE}:{every}",
             "set": [*scene.get("set", []), f"BLUEWAKE_TEST_WARP={bench_tour.warp_string(stops, start=start)}"]}
    windows = []
    for i, stop in enumerate(stops):
        first = start + i * 1800
        slug = re.sub(r"[^a-z0-9]+", "-", stop.name.lower()).strip("-")
        windows.append((f"{scene['name']}-{i + 1}-{slug}", first + bench_tour.SETTLE, first + 1800))
    return timed, windows


def split_tour(scene, row, folder, windows, out):
    """One scene folder per stop, with that stop's frames (hard links) and their hashes."""
    rows = []
    for name, first, end in windows:
        stop = out / "scenes" / name
        shutil.rmtree(stop, ignore_errors=True)
        for v in ("A", "B"):
            (stop / v).mkdir(parents=True)
            for frame in (folder / v).glob("frame-*.ppm"):
                if first <= int(frame.stem.split("-")[1]) < end:
                    os.link(frame, stop / v / frame.name)
        (stop / "hashes.json").write_text(json.dumps({v: frame_hashes(stop / v) for v in ("A", "B")}, indent=1))
        rows.append({"name": name, "scene": scene["name"], "runs": row["runs"]})
    return rows


def collect_scene(scene, apps, out, args, env):
    """Run one scene on both builds and hash its frames; the frames stay where they are. A tour scene comes
    back as one row a stop."""
    folder = out / "scenes" / scene["name"]
    state = Path(args.states) / scene["state"]
    cmd = [sys.executable, str(HERE / "rendered_run.py"), str(apps["A"]), str(folder), "--card", str(args.card),
           "--state", str(state), "--timeout", str(scene.get("timeout", 600 if not scene.get("tour") else 1200))]
    windows = None
    if scene.get("tour"):
        timed, windows = tour_timing(scene, state_retrace(state))
        timed = {**scene, **timed}
    else:
        timed = {**scene, **shifted(scene, state_retrace(state))}
    for key, flag in (("max_retraces", "--max-retraces"), ("pad", "--pad"), ("capture", "--capture"),
                      ("dump", "--dump"), ("smooth", "--smooth"), ("scale", "--scale")):
        if timed.get(key) is not None:
            cmd += [flag, str(timed[key])]
    for item in timed.get("set", []):
        cmd += ["--set", item]
    cmd += ["--variant", "A", "--variant", "B", f"APP={apps['B']}"]
    subprocess.run(cmd, env=env, stdout=sys.stdout, stderr=subprocess.STDOUT)
    results = folder / "results.json"
    runs = {r["variant"]: r for r in (json.loads(results.read_text()) if results.exists() else [])}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "hashes.json").write_text(json.dumps({v: frame_hashes(folder / v) for v in ("A", "B")}, indent=1))
    row = {"name": scene["name"], "runs": runs}
    return split_tour(scene, row, folder, windows, out) if windows else [row]


def frame_hashes(folder):
    """{frame file: SHA-256} for a run's captures or dump."""
    return {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(list(folder.glob("*.ppm")) + list(folder.glob("dump/*.ppm")))}


def run_problems(runs):
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
    return problems


def hashes_differ(folder):
    path = folder / "hashes.json"
    if not path.exists():
        return True
    hashes = json.loads(path.read_text())
    return not hashes.get("A") or hashes.get("A") != hashes.get("B")


def judge_scene(scene, row, out):
    """A scene's verdict: from its hashes when A and B match, else from its frames with frame_compare.py check."""
    folder = out / "scenes" / row["name"]  # a tour's stops have folders of their own
    row = dict(row)
    problems = run_problems(row["runs"])
    if problems:
        row.update(verdict="failed", why=", ".join(problems))
        return row
    if not hashes_differ(folder):
        images = len(json.loads((folder / "hashes.json").read_text())["A"])
        row.update(verdict="identical", images=images, max_diff=0, min_psnr=None, flicker_a="=", flicker_b="=",
                   why="")
        return row
    if not any((folder / "A").glob("**/*.ppm")):
        row.update(verdict="failed", why="frames differ but were not copied here")
        return row
    check = folder / "check.json"
    cmd = [sys.executable, str(HERE / "frame_compare.py"), "check", str(folder / "A"), str(folder / "B"),
           "--json", str(check), "--sheet", str(folder / "worst.png"),
           "--min-psnr", str(scene.get("min_psnr", 40)), "--flicker-margin", str(scene.get("flicker_margin", 50))]
    if scene.get("region"):
        cmd += ["--region", scene["region"]]
    subprocess.run(cmd, stdout=sys.stdout, stderr=subprocess.STDOUT)
    if not check.exists():
        row.update(verdict="failed", why="frame_compare.py check wrote nothing")
        return row
    row.update(json.loads(check.read_text()))
    return row


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


def warp_run(app, folder, recipe, quest_log, args, env, stop_after, extra=()):
    # A quest log that is empty leaves the game at the file select: the retrace cap ends that run.
    cmd = [sys.executable, str(HERE / "rendered_run.py"), str(app), str(folder), "--card", str(args.card),
           "--warp", recipe["warp"], "--warp-file", str(quest_log), "--stop-after", str(stop_after),
           "--max-retraces", "9000", "--timeout", "600", "--stop-on", "is empty; stopped pressing A",
           "--set", "BLUEWAKE_PERF_LOG=1",
           "--set", "BLUEWAKE_LOOSE_REL_RETRACES=1", *extra]
    if recipe.get("time"):
        cmd += ["--warp-time", str(recipe["time"])]
    subprocess.run(cmd, env=env, stdout=sys.stdout, stderr=subprocess.STDOUT)
    log = folder / "log.txt"
    return log.read_text(errors="replace") if log.exists() else ""


def make_state(name, recipe, app, out, args, env):
    """Make a scene's save state from its recipe: warp there, see when Link arrives, then warp again and save
    the state `settle` retraces later (the camera and the room settled). Returns a message on failure."""
    path = Path(args.states) / name
    folder = out / "make-state" / Path(name).stem
    settle = int(recipe.get("settle", 180))
    print(f"== making {name}: warp {recipe['warp']}, saved {settle} retraces after Link arrives", flush=True)
    # The recipe's quest log first, then the card's others: a card's saves are not always in the same one.
    for quest_log in dict.fromkeys([int(recipe.get("file", 1)), 1, 2, 3]):
        text = warp_run(app, folder / f"find-{quest_log}", recipe, quest_log, args, env, stop_after=120)
        at = text.find("[warp] arrived")
        after = [int(m) for m in PERF.findall(text[at:])] if at >= 0 else []
        if after:
            break
        print(f"== quest log {quest_log} did not get there" + (" (empty)" if "is empty" in text else ""), flush=True)
    else:
        return f"{name}: the warp to {recipe['warp']} never arrived from quest logs 1-3 (see {folder}/find-*/log.txt)"
    target = after[0] + settle
    made = folder / "made.bwstate"
    made.unlink(missing_ok=True)
    text = warp_run(app, folder / "save", recipe, quest_log, args, env, stop_after=settle + 240,
                    extra=("--set", f"BLUEWAKE_SAVE_STATE={made.resolve()}@{target}"))
    arrived, saved = text.find("[warp] arrived"), text.find("[state] saved")
    if arrived < 0 or saved < 0 or saved < arrived or not target <= (state_retrace(made) or 0) <= target + 2:
        return (f"{name}: no state saved after Link arrived at retrace {target} "
                f"(see {folder / 'save' / 'log.txt'})")
    Path(args.states).mkdir(parents=True, exist_ok=True)
    shutil.move(str(made), str(path))
    print(f"== made {path} at retrace {target}, from quest log {quest_log}", flush=True)
    return None


def collect(args):
    scenes = scenes_for(args.scenes, args.suite)
    recipes = recipes_for(args.scenes)
    problems = validate(scenes, recipes)
    states = dict.fromkeys(s["state"] for s in scenes)
    # A state that is not one (a placeholder of a few bytes, which the game hangs on) is made again from its recipe.
    to_make = [n for n in states if state_retrace(Path(args.states) / n) is None and n in recipes]
    problems += [f"no save state at {Path(args.states) / n} and no recipe to make it" for n in states
                 if state_retrace(Path(args.states) / n) is None and n not in recipes]
    if not Path(args.card).is_file():
        problems.append(f"no card at {args.card}")
    if problems:
        for p in problems:
            print(f"render_suite: {p}", file=sys.stderr)
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
               "repeat": args.repeat, "a": args.label_a, "b": args.label_b, "scene_list": scenes, "scenes": []}
    for name in to_make:
        failed = make_state(name, recipes[name], apps["B"], out, args, env)
        if failed:
            print(f"render_suite: {failed}", file=sys.stderr)
            return 2
    summary["states"] = {n: state_retrace(Path(args.states) / n) for n in states}
    print(f"== {len(scenes)} scene(s) on {summary['host']} ({summary['gpu'] or 'GPU unknown'}, {summary['display']})",
          flush=True)
    for n, scene in enumerate(scenes, 1):
        print(f"== scene {n}/{len(scenes)}: {scene['name']}", flush=True)
        summary["scenes"] += collect_scene(scene, apps, out, args, env)
    top = QUICK_ROOMS if args.suite == "quick" else FULL_ROOMS
    print(f"== rooms: the costliest {top}, {args.repeat} run(s) each build", flush=True)
    cmd = [sys.executable, str(HERE / "bench_rooms.py"), str(apps["A"]), str(out / "rooms"), "--card",
           str(args.card), "--rooms", str(HERE / "bench_rooms.tsv"), "--top", str(top), "--repeat",
           str(args.repeat), "--rendered-run", str(HERE / "rendered_run.py"),
           "--variant", "A", "--variant", "B", f"APP={apps['B']}"]
    subprocess.run(cmd, env=env, stdout=sys.stdout, stderr=subprocess.STDOUT)
    (out / "collected.json").write_text(json.dumps(summary, indent=1))
    print(f"== wrote {out / 'collected.json'}")
    return 0


def differing(out):
    """The scenes whose frames are needed to judge them: A and B ran, and their frames differ."""
    collected = json.loads((Path(out) / "collected.json").read_text())
    return [row["name"] for row in collected["scenes"]
            if not run_problems(row["runs"]) and hashes_differ(Path(out) / "scenes" / row["name"])]


def analyze(out, floor):
    out = Path(out)
    try:
        import numpy, PIL  # noqa: F401  (frame_compare.py needs them)
    except ImportError:
        print("render_suite: analyze needs numpy and Pillow (pip install --user numpy pillow)", file=sys.stderr)
        return 2
    summary = json.loads((out / "collected.json").read_text())
    scenes = {s["name"]: s for s in summary.pop("scene_list")}
    summary["scenes"] = [judge_scene(scenes[row.get("scene", row["name"])], row, out) for row in summary["scenes"]]
    summary["rooms"] = compare_rooms(read_rooms_tsv(out / "rooms" / "rooms.tsv"), floor)
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
    for command in ("collect", "run"):
        p = sub.add_parser(command)
        collect_arguments(p)
    p = sub.add_parser("differing")
    p.add_argument("out")
    p = sub.add_parser("analyze")
    p.add_argument("out")
    p.add_argument("--floor", type=float, default=5.0, help="percent a room must differ by to be flagged")
    p = sub.add_parser("report")
    p.add_argument("summary")
    p.add_argument("--format", choices=("terminal", "github"), default="terminal")
    p = sub.add_parser("validate")
    p.add_argument("scenes", nargs="?", default=str(HERE / "render_scenes.json"))
    args = parser.parse_args()
    if args.command == "collect":
        sys.exit(collect(args))
    if args.command == "run":
        code = collect(args)
        sys.exit(code if code else analyze(args.out, args.floor))
    if args.command == "differing":
        print("\n".join(differing(args.out)))
        sys.exit(0)
    if args.command == "analyze":
        sys.exit(analyze(args.out, args.floor))
    if args.command == "report":
        summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
        print(report(summary, args.format))
        sys.exit(status(summary))
    problems = validate(scenes_for(args.scenes, "full"), recipes_for(args.scenes))
    for p in problems:
        print(p)
    sys.exit(1 if problems else 0)


def collect_arguments(p):
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


if __name__ == "__main__":
    main()
