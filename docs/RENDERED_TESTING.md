# Rendered testing with an agent

How to let a coding agent (Claude Code, Codex and the like) test BlueWake's rendering on its own: build, warp to a
place, play scripted input, capture or dump frames, time the GPU, compare builds and settings, and show you the
result as images and numbers. Everything here was used on Windows 11 (PowerShell, Direct3D 12) while tracking down
#491's flickering shadows and the ambient occlusion halo. The game-side switches are the same on Linux and Mac; the
window and launch tricks are Windows-specific.

The short version: **a save state, a pad script and a frame dump give you the same frames on every run, so two
builds or two settings can be compared pixel for pixel.** The rest of this page is how to get there and what trips
agents up.

## The scripts

[`scripts/rendered_run.py`](../scripts/rendered_run.py) runs the app the same way each time, once or once a
variant, and keeps what it made: frame captures, frame dumps, its log, and what the log says about speed and GPU
time (`results.json`). Each run gets its own copy of the card, its own settings and data folder, and none of the
caller's `BLUEWAKE_`/`DOL_` variables. [`scripts/frame_compare.py`](../scripts/frame_compare.py) reads the frames
(it needs `pip install numpy pillow`). Both print their full usage with `--help`; the sections below are what they
set and why. A run that ends at start-up leaves the app's launch marker, and the next run in that folder would start
in safe mode (no HD look, no mods, 4:3): `rendered_run.py` clears the marker before each run, and marks a run that
still started in safe mode (SAFE MODE on its line, `safe_mode` in `results.json`).

**Flicker, `main` against a build.** From a save state, two sword swings, frames dumped at 60 FPS and render scale 2,
sun shadows on and off on each build, plus a debug run whose frames mark where the shadows are:

```
python3 scripts/rendered_run.py build/new/BlueWake/BlueWake.exe out/flicker --card my.card \
    --state trees.bwstate --pad 1885:0x0200:6,1915:0x0200:6 --max-retraces 2035 \
    --dump 0:80 --smooth 1 --scale 2 --set BLUEWAKE_HD_LOOK=1 --set BLUEWAKE_HD_SUN_SHADOWS=1 \
    --variant new --variant new-nosun BLUEWAKE_HD_SUN_SHADOWS=0 \
    --variant main APP=build/main/BlueWake/BlueWake.exe \
    --variant main-nosun APP=build/main/BlueWake/BlueWake.exe BLUEWAKE_HD_SUN_SHADOWS=0 \
    --variant mask DOL_AURORA_SUN_SHADOW_MAP_DEBUG=1 DOL_AURORA_AO_DEBUG=1 BLUEWAKE_HD_AO=0
python3 scripts/frame_compare.py ratio out/flicker/main out/flicker/main-nosun --mask out/flicker/mask
python3 scripts/frame_compare.py ratio out/flicker/new out/flicker/new-nosun --mask out/flicker/mask
python3 scripts/frame_compare.py blinks out/flicker/new --sheet blinks.png
python3 scripts/frame_compare.py sheet out/flicker/main out/flicker/new --frames 26,28,30 --out hit.png
```

`ratio`'s "full" column is shadowed ground against the same ground without shadows: 0.65 is one shadow (1 - 0.35
strength). On `main`, while the hit's motion blur was on, it went 0.51, 0.56, 0.44, 0.61, 0.41; with the fix it held
0.65.

**Benchmarking an effect.** The same state, paced, render scale 3, twice each, with Aurora's GPU time per zone:

```
python3 scripts/rendered_run.py build/new/BlueWake/BlueWake.exe out/bench --card my.card \
    --state trees.bwstate --max-retraces 2700 --scale 3 --gpu-prof --repeat 2 \
    --set BLUEWAKE_HD_LOOK=1 --variant ao-on --variant ao-off BLUEWAKE_HD_AO=0
```

prints each run and each variant's mean (game frames a second, busy, GPU busy time); `results.json` has every zone
(ambient occlusion: 0.114 and 0.122 ms a frame on an RTX 5070 Ti). Paced, game frames a second stop at 30, so compare
busy and GPU time; `--unpaced` measures speed instead. The standard speed benchmark at fixed stops is
[BENCHMARK_TOUR.md](BENCHMARK_TOUR.md) (`scripts/bench_tour.py`).

## Build A against build B: `render_test`

[`scripts/render_test`](../scripts/render_test) does all of the above for two builds in one command, on a Steam
Deck (or any Linux machine) over SSH, or here:

```
render_test [user@host] BUILD_A BUILD_B [--suite quick|full] [--repeat 3] [--format terminal|github]
```

The target only renders: it needs `python3` and nothing else. The analysis runs on the machine you start
`render_test` from, which needs numpy and Pillow (`pip install --user numpy pillow`).

A build is an AppImage, or a folder holding `BlueWake-x86_64.AppImage`. B is the reference: there are no stored
reference images. Every scene starts from a save state, so A and B make the same frames unless the rendering
changed. Two things run, both through the scripts above:

- **Scenes** ([`scripts/render_scenes.json`](../scripts/render_scenes.json)): each is a `rendered_run.py` run per
  build from a save state, with its pad script, captures or Smooth Motion dump and settings. Then
  `frame_compare.py check A B` gives a verdict. **identical**: every pixel is the same. **similar**: every image's
  PSNR is at least the scene's `min_psnr` (default 40). **changed**: an image's PSNR is below that. **failed**: a
  run crashed, timed out, started in safe mode or made no frames, the image sets differ, or A blinks more than B
  (flicker).
- **Rooms**: [`scripts/bench_rooms.py`](../scripts/bench_rooms.py) over the costliest stage-select rooms
  ([`scripts/bench_rooms.tsv`](../scripts/bench_rooms.tsv), the October 25 sweep). The quick suite runs the top 3,
  the full suite the top 10. A and B alternate in each room, `--repeat` runs each. A room is flagged when A's GPU
  time or busy % differs from B's by more than 5% and more than twice the spread between repeats.

The quick suite runs the scenes marked `quick` and the top 3 rooms.
`--suite full` runs every scene and the top 10 rooms. The exit code is 0 when everything passed, 1
when a scene changed or failed or a room was flagged, and 2 when the setup is wrong (a missing state, card,
display, or numpy/Pillow here).

**Examples:**

```
# Over SSH on the Deck: a branch build against main (folders from build_script, or AppImages).
# SSH keys or ~/.ssh/config are used, else it asks for the password once (--ssh-key for a given key).
scripts/render_test deck@10.10.20.168 build/artifacts/gpr/latest build/artifacts/main/latest

# The same here, with the table ready to paste into a PR
scripts/render_test build/artifacts/gpr/latest build/artifacts/main/latest --format github

# Every scene and the top 10 rooms, five runs a room
scripts/render_test deck@10.10.20.168 new.AppImage main.AppImage --suite full --repeat 5

# A Deck in Desktop Mode without gamescope's headless backend: use the running session
scripts/render_test deck@10.10.20.168 new.AppImage main.AppImage --display desktop

# The halves by hand: collect renders (on the target), analyze judges (where numpy is); run does both
python3 scripts/render_suite.py collect new.AppImage main.AppImage out/rt --card my.card --states states/
python3 scripts/render_suite.py differing out/rt      # the scenes whose frames need copying to analyze them
python3 scripts/render_suite.py analyze out/rt
python3 scripts/render_suite.py report out/rt/summary.json --format github
```

**Output.** The run streams each scene's and room's runs, then prints a table like this one (the numbers are
illustrative):

```
A (candidate): gpr
  /home/me/bluewake/build/artifacts/gpr/latest/BlueWake-x86_64.AppImage
B (reference): main
  /home/me/bluewake/build/artifacts/main/latest/BlueWake-x86_64.AppImage
Checking deck@10.10.20.168...
Evidence on target: deck@10.10.20.168:/home/deck/bluewake-render/runs/gpr-vs-main-20261028T214500Z
Staging builds and harness...
== 2 scene(s) on steamdeck (AMD Custom GPU 0405 (RADV VANGOGH), headless 1280x800)
== scene 1/2: outset-trees-swing
A: exit 1 after 31 s, 0 frames, 160 dumped images
B: exit 1 after 30 s, 0 frames, 160 dumped images
== scene 2/2: outset-trees-still
...
== rooms: the costliest 3, 3 run(s) each build
...
== wrote /home/deck/bluewake-render/runs/gpr-vs-main-20261028T214500Z/out/collected.json
Copying back logs, timings and frame hashes...
Copying back outset-trees-swing frames (A and B differ)...

Analysing here...
changed: 160 images, 41 differ, max diff 96, min PSNR 31.2, flicker A 0 B 212 (52-between PSNR 31.2 < 40.0)
wrote build/render-tests/gpr-vs-main-20261028T214500Z/out/scenes/outset-trees-swing/worst.png

Rendered tests: A gpr against B main
steamdeck, AMD Custom GPU 0405 (RADV VANGOGH), display headless 1280x800, quick suite, 3 run(s) a room

scene               verdict    images  max diff  min PSNR  flicker A/B  why
outset-trees-swing  CHANGED    160     96        31.2      0/212        52-between PSNR 31.2 < 40.0
outset-trees-still  IDENTICAL  10      0         -         =/=

room        name            GPU ms A  GPU ms B  busy% A  busy% B  GPU Δ   flag
SubD51:1:0  SubD51          11.42     11.51     78.5     79.1     -0.8%   ok
Hyroom:0:0  Inside (day 0)  9.87      9.80      74.2     73.9     +0.7%   ok
WarpD:0:0   Warp maze       12.90     11.61     81.0     80.4     +11.1%  gpu_ms +11.1%

FAIL

Summary: /home/me/bluewake/build/render-tests/gpr-vs-main-20261028T214500Z/out/summary.json
```

Here the swing scene changed because A fixed B's flicker (0 blink pixels against 212). Its `worst.png` shows A, B
and their difference (x8) side by side. The still scene was identical by its frame hashes alone, so its frames
were not copied (`=/=`: no flicker check needed, A is B). A **changed** verdict means "look at it", not
"wrong". The Warp maze is 11% slower on the GPU, well outside the spread between runs. With `--format github` the
same tables come out as Markdown.

**What stays where.** Builds, the card and save states stay on the target, and the runs are in
`~/bluewake-render/runs/<A>-vs-<B>-<time>/` there (`out/scenes/<scene>/A|B`, `out/rooms/`, `suite.log`). Copied back
to `build/render-tests/<A>-vs-<B>-<time>/out/` here: logs, timings, `results.json`, each frame's SHA-256
(`hashes.json`), and the frames of the scenes whose hashes differ between A and B, which the analysis needs. A run
of two identical builds copies no frames. Analysed here: `summary.json`, `check.json` and `worst.png` per scene.
Nothing is uploaded anywhere else, so none of this runs in CI. CI runs `tests/test_render_suite.py`, which drives the same
scripts end to end with a fake app (`tests/render_fixtures/fake_bluewake.py`) that writes frames and log lines.

**One-time setup on the target:**

- the card: `~/.local/share/BlueWake/GZLE01.card` (`--card` for another). Each run gets a copy; the states are
  made from its quest log 1, so use a file that has Outset's hilltop open (any file past the start of the game).
- nothing for the save states: a state the scenes need that is missing (or is not a save state, such as a
  placeholder of a few bytes, which the game hangs on) is **made on the target from its recipe** the first time,
  with build B, and kept for later runs in `~/bluewake-render/states/` (`~/.local/share/BlueWake/render-states/`
  here; `--states-dir` for another). Delete it to make it again.
- a display. `--display auto` (the default) runs the game under `gamescope --backend headless` when gamescope is
  there (SteamOS has it), at 1280x800 on a Deck (`--size` for another). Without it, the game uses the running
  desktop session (Desktop Mode on a Deck, `DISPLAY=:0`).
- `python3` and `tar` (SteamOS has both). numpy and Pillow are needed only on the machine running `render_test`.

**Save states from a recipe.** `render_scenes.json` has a `states` section:

```json
"outset_trees.bwstate": {"warp": "sea:44:8:0", "time": "noon", "file": 1, "settle": 180}
```

To make it, the suite warps there once (stage select, quest log `file`, `time`) and reads the log for the first
`[perf]` retrace after `[warp] arrived`. Then it warps again and saves the state (`BLUEWAKE_SAVE_STATE`) `settle`
retraces after that (180 is 3 seconds, for the camera and the room to settle). It checks that the save came after
Link arrived and that the file's header holds that retrace. `sea:44:8:0` is Outset's hilltop, by the small
trees where #491's shadows flickered (fixed in #494).

**Adding a scene.** Scenes count their retraces from their state, so a state made again (at a slightly different
retrace, as a warp from boot is not frame-exact) still fits. The suite reads the state's retrace from its header
and adds it. Add an entry to `render_scenes.json`, with a recipe under `states` for a new place:

```json
{
 "name": "windfall-night-lights",
 "about": "what it covers",
 "suite": "full",
 "state": "windfall_night.bwstate",
 "length": 300,
 "pad": "30:0x0200:6",
 "capture": "30:30",
 "set": ["BLUEWAKE_HD_LOOK=1"],
 "region": "0,0.1,1,0.9",
 "min_psnr": 40
}
```

Required: `name`, `state`, `length` (retraces to run after the state), and `capture` (`AFTER:EVERY`, retraces
after the state) or `dump` (game frames; also needs `smooth`). Optional: `pad` (each press's retrace counted after
the state), `scale`, `set`, `region` (to leave the HUD out), `min_psnr`, `flicker_margin` (default 50 blink pixels),
`timeout` (seconds, default 600) and `suite` (`quick` by default). A state made by hand (F5, or
`BLUEWAKE_SAVE_STATE=FILE@RETRACE`) works too: put it in the states folder under the scene's `state` name. Without
a recipe it is never remade. `python3 scripts/render_suite.py validate` checks the file. CI runs it too.

## Rules to give the agent first

[AGENTS.md](../AGENTS.md) applies; for rendered tests in particular:

- Never touch the real user folder (`%APPDATA%\BlueWake`, `~/.local/share/BlueWake`, ...). Every run gets its own
  folder with `BLUEWAKE_DATA_DIR`, and a **copy** of a card in it.
- Never commit or upload save states, cards, frame dumps, disc files or the game module. States hold the game's
  memory; dumps hold the game's pictures. Keep them in a scratch folder outside the repository.
- Capture the game's own window or its own frames, never the screen: a screen grab of a live desktop picks up
  whatever else is open (it did, once, for us).
- Ask before sending real keyboard or mouse input to the desktop (see "Menus" below).
- Don't patch the app just to get a screenshot. Use its test hooks and input paths, so what you test is what ships.

## Builds

- **Host-only over a trained build.** Renderer work (RecompCore/Aurora, `runtime/host/src`) needs
  `scripts/windows/build.py DISC --out <build> --host-only --jobs 16`: it keeps the last build's training and
  recompiles only what changed. A RecompCore change: commit it locally, put its hash in
  `scripts/builder/profiles/bluewake.sh` (`RECOMPCORE_SHA`), check `ref/recompcore` out at that commit, build. The
  builder refuses a `ref/recompcore` with uncommitted changes.
- **A second build to compare against.** Copy a whole build folder (robocopy is fine) to keep a baseline. CMake keeps
  absolute paths inside it, so a copy only builds under its original folder name: rename the original aside, rename
  the copy into its place, build, rename both back.
- **Surprise full rebuilds.** Checking `ref/recompcore` out at another commit gives every header that differs a new
  timestamp, and a header every game-module file includes (`GXRuntime/include/core/cpu.h`) recompiles all ~850
  chunks. If the header's content matches what the module was built against, set its timestamp back before the
  module's objects and the rebuild drops to the app.

## Launching without anyone at the PC

- The PC can be locked; it must not sleep. Rendered runs work from a locked session.
- Start long jobs detached so they don't steal focus or open empty console windows:

  ```powershell
  $si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}
  Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
      CommandLine = 'python scripts\rendered_run.py ... > C:\scratch\out\console.txt 2>&1'
      CurrentDirectory = 'C:\src\bluewake'; ProcessStartupInformation = $si }
  ```

- `rendered_run.py` writes `status.txt` in its output folder as each run starts and ends: let the agent wait on
  that file (a loop that ends when the run's own line appears), not with fixed sleeps.
- Writing your own launcher instead: `BlueWake.exe` is a GUI program, so PowerShell's `& BlueWake.exe` returns at
  once (use `Start-Process $app -Wait -PassThru`), and `powershell -File script.ps1 -List a,b` passes `a,b` as
  **one** string.

## Getting to a place

The stage select can start a quest log and go straight somewhere ([STAGE_SELECT.md](STAGE_SELECT.md#for-tests-and-benchmarks)):

| Variable | |
| --- | --- |
| `BLUEWAKE_STAGE_SELECT=1` | the stage select on |
| `BLUEWAKE_WARP=stage:room:point[:layer]` | `sea:44:8:0` is Outset's hilltop, `sea:11:0:1` Windfall's pier at night, `M_NewD2:0:0` Dragon Roost Cavern; names are in `config/stage_select/names.tsv` |
| `BLUEWAKE_WARP_FILE=1` | which quest log on the card copy to start (pick one without effects you don't want, e.g. before the Master Sword's glow) |
| `BLUEWAKE_WARP_TIME=noon` | `0`-`23`, `morning`, `noon`, `evening`, `night` |
| `BLUEWAKE_WARP_STOP_AFTER=600` | quit that many play frames after Link arrives (the exit code is then 1; that's normal) |

To find a good spot, sweep a room's spawn points (one short run each, one frame each) and tile the frames into one
image for the agent to look at.

## Save states

- `BLUEWAKE_SAVE_STATE=C:\scratch\states\spot.bwstate@1935` saves at retrace 1935 (several, comma-separated).
- `BLUEWAKE_LOAD_STATE=C:\scratch\states\spot.bwstate` starts from it.
- **A state is what makes runs repeatable.** From boot, the game's randomness differs run to run (grass drops a
  random item, cut pieces fly differently), so two "identical" runs aren't. From a state, every run is frame-exact:
  we checked, the sky differed by 0.00 between two runs.
- Loading restores the retrace count, so everything timed in retraces (`BLUEWAKE_MAX_RETRACES`, the pad script,
  captures) counts on from the state's retrace. A limit below it ends the run at once.
- Make the state just before the thing you want to see happen. A state "at the trees" saved after the walk's last
  swing had a tree already falling.

## Input

`BLUEWAKE_PAD_SCRIPT="retrace:buttons:length[:x:y[:cx:cy]],..."` presses GameCube buttons (hex: A `0x0100`, B
`0x0200`, X `0x0400`, Y `0x0800`, Start `0x1000`) for that many retraces, with the stick if given (`0:80` is forward).
It is added to what else is pressing, and it works after a state load. Example, two sword swings from a state saved
at 1875: `BLUEWAKE_PAD_SCRIPT=1885:0x0200:6,1915:0x0200:6`.

## Pictures

**Frame captures** (cheap, unpaced):

```
BLUEWAKE_CAPTURE_OPENING_FRAME=C:\scratch\run1\frame.ppm
BLUEWAKE_CAPTURE_RETRACE=1300
BLUEWAKE_CAPTURE_INTERVAL=60
BLUEWAKE_WALL_PACE=0
BLUEWAKE_MAX_RETRACES=3200
```

writes `frame-<retrace>.ppm` beside that path: the game's picture with its HUD, no settings menu. Unpaced runs take
seconds. Smooth Motion makes no in-between frames unpaced.

**Frame dumps** (every real and in-between frame, paced, big):

```
DOL_AURORA_FRAME_INTERP=1
DOL_AURORA_FRAME_INTERP_STEPS=3        # 1 = 60 FPS, 3 = 120 FPS, display = the display's rate
DOL_AURORA_FRAME_INTERP_DUMP=C:\scratch\dumps\run1
DOL_AURORA_FRAME_INTERP_DUMP_FROM=0
DOL_AURORA_FRAME_INTERP_DUMP_TO=260    # game frames
DOL_AURORA_RENDER_SCALE=2
```

Files are `frameNNNNNN-real.ppm` and `-between.ppm`, `-between2`, `-between3`. **Order on screen: frame N's
in-betweens come before real N** (they run from N-1 toward N). Get that wrong and every real frame looks like a
flicker. Size: about 0.9 MB an image at render scale 1 (640x480), 3.5 MB at scale 2; 260 game frames at 120 FPS is
about 1 GB at scale 1, 3.5 GB at scale 2.

**Comparing builds and settings:** run the same state and pad script with only one thing changed: `main` against your
build, render scale 1 against 2, Smooth Motion 60 against 120, an effect on against off (`BLUEWAKE_HD_LOOK`,
`BLUEWAKE_HD_SUN_SHADOWS`, `BLUEWAKE_HD_AO`, ...). Launch variables win over the settings file for the run.

## Finding flicker and other differences in the frames

Let the agent do the counting and only show you the frames that matter (`frame_compare.py` does each of these:
`blinks`, `ratio`, `track`, `diff`, `sheet`):

- **One-image blinks:** an image that differs from both neighbours in the same direction (by 40 or more of 255)
  while the neighbours match each other (within 12). Motion doesn't do that; flicker does. Count blink pixels per
  image, rank, and look at the top few with the blinks painted red.
- **What an effect does on its own:** divide a frame with the effect by the same frame without it (the runs must be
  from a state). With sun shadows, shadowed ground sat at exactly 0.65 of its unshadowed brightness (1 - 0.35
  strength) and lit ground at 1.000; during the camera shake it dropped to 0.41, below what one shadow can do, which
  is how the doubled shadows were found.
- **Split by a debug view:** a debug run from the same state gives a mask (fully shadowed, fully lit) to measure the
  real frames with.
- **A brightness track:** the mean of a region, image by image, shows a pulse at the game's 30 FPS at a glance.
- Before believing a difference, rule out what moves anyway: the sword's trail, cut pieces, smoke, swaying ground
  plants, the camera.

## Debug views

| Variable | Shows |
| --- | --- |
| `DOL_AURORA_AO_DEBUG=1` | ambient occlusion alone |
| `DOL_AURORA_SUN_SHADOW_MAP_DEBUG=1` | the shadow map's term (with `DOL_AURORA_AO_DEBUG=1` and `BLUEWAKE_HD_AO=0` it replaces the picture: black shadow, white lit) |
| `DOL_AURORA_SUN_SHADOW_MAP_DEBUG=6` | each shadow cascade tinted (red, green, blue, yellow) |
| `DOL_AURORA_FAR_BLUR_DEBUG=1` | distance as brightness (log2 of near-plane units over 24), the sky blue |

[HD_SUN_SHADOW_MAP.md](HD_SUN_SHADOW_MAP.md) lists the shadow map's other tools.

## Menus

- `BLUEWAKE_SETTINGS_TEST_OPEN=10:60` opens the settings menu 10 seconds in, for 60, on its first tab.
- Capture the window itself with Win32 `PrintWindow(hwnd, hdc, 2)` (full content); it works with other windows in
  front.
- Posted key and mouse messages don't reach the game (SDL takes input only with focus). To press keys, bring the
  window in front (press and release Alt with `keybd_event`, then `ShowWindow(hwnd, 9)` and `SetForegroundWindow`),
  then send keys with `keybd_event`. That is real input on the desktop for a few seconds: get the PC owner's OK. With
  the menu opened by the hook, the cursor starts on the close button: the first Down lands on the first setting.
- `BLUEWAKE_BACKGROUND_INPUT=1` lets a controller in while the window is in the background (a virtual pad on ViGEm
  would do for scripted presses).

## GPU cost

`DOL_AURORA_GPU_PROF=1` (`rendered_run.py --gpu-prof`) prints each zone's average GPU time every 240 frames to stderr
(`Ambient occlusion 0.089 x2.0`, ...); `rendered_run.py` keeps the last report of each run in `results.json`. Measure
paced runs: unpaced, the whole frame's GPU time varied by tens of percent between runs; paced, two runs of the same
variant were within 2%. A zone is the steadier number.
`DOL_AURORA_RENDER_SCALE` takes effect at the first frame, after the startup log line that still reports scale 1.

## Agent pitfalls we hit

- Windows paths in shell heredocs lose their backslashes (`\b` became a control character in a path): write scripts
  with a file editor tool, not through `cat <<EOF`.
- A wait loop that greps a shared status file can match an older run's "done": wait for the run's own line.
- A shell whose working directory is inside a folder keeps Windows from moving or deleting that folder.
- Keep the agent's own changes for a screenshot or a test out of commits: one change per commit, and say plainly
  what was measured, on what, and what wasn't checked.
