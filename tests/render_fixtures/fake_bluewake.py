#!/usr/bin/env python3
"""A stand-in for BlueWake in tests/test_render_suite.py: the log lines and frames rendered_run.py reads.

Its file name picks what it draws: "bright" a brighter picture than "plain", "flicker" one image that
blinks, "noise" a few pixels off by one, "slow" a GPU twice as busy, "hang" never ends.
"""
import os
import sys
import time
from pathlib import Path

name = Path(sys.argv[0]).name
env = os.environ
if "hang" in name:
    time.sleep(600)
shade = 140 if "bright" in name else 100
W, H = 32, 24


def picture(n, between=False):
    rows = bytearray()
    for y in range(H):
        for x in range(W):
            v = shade + (x + n) % 8
            if "flicker" in name and n == 3 and not between and 8 <= x < 24 and 6 <= y < 18:
                v += 80
            if "noise" in name and x == y:
                v += 1
            rows += bytes((v, v, v))
    return f"P6 {W} {H} 255\n".encode() + bytes(rows)


if env.get("BLUEWAKE_CAPTURE_OPENING_FRAME"):
    folder = Path(env["BLUEWAKE_CAPTURE_OPENING_FRAME"]).parent
    first, every = int(env["BLUEWAKE_CAPTURE_RETRACE"]), int(env["BLUEWAKE_CAPTURE_INTERVAL"])
    for n, retrace in enumerate(range(first, int(env.get("BLUEWAKE_MAX_RETRACES", first + 5 * every)), every)):
        (folder / f"frame-{retrace}.ppm").write_bytes(picture(n))
if env.get("DOL_AURORA_FRAME_INTERP_DUMP"):
    folder = Path(env["DOL_AURORA_FRAME_INTERP_DUMP"])
    for n in range(int(env["DOL_AURORA_FRAME_INTERP_DUMP_FROM"]), int(env["DOL_AURORA_FRAME_INTERP_DUMP_TO"])):
        (folder / f"frame{n:06d}-between.ppm").write_bytes(picture(n, True))
        (folder / f"frame{n:06d}-real.ppm").write_bytes(picture(n))
if env.get("BLUEWAKE_WARP"):
    print("[warp] arrived")
gpu = 8.0 if "slow" in name else 4.0
for i in range(6):
    print(f"[perf] retrace={600 + 120 * i} rate=60.0 worst_ms=17.0 hitches=0 busy={60 + i % 2}.0%")
    print(f"[gpu-prof] frames=240 frame_ms=16.6 max=17.0 busy_ms={gpu + 0.01 * i} | ssao {gpu / 2:.2f} x1 "
          f"| main {gpu / 4:.2f} x1 | copy {gpu / 8:.2f} x1")
sys.exit(1 if env.get("BLUEWAKE_WARP") else 0)
