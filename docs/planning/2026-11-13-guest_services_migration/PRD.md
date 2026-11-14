# PRD — Guest services migration

Status: Draft (programme, ranking only; each migration gets its own plan)
Source: the parallel-execution research on fork PR #9 (`docs/planning/2026-11-03-parallel_guest_execution/`: E0, E1a, E2 and the traces of 2026-11-13); the busy-view profiles of #592 and #593; #503's Outset breakdown; #541 (skinning), #542/#436 (collision), #561 (the audio thread)
Scope: moving whole guest subsystems ("services") from translated code to native host implementations that can use more cores, ranked by what each is worth; excluded: changes to the game's own logic, 60 game updates a second, non-deterministic concurrency
[Technical plan](TECH_PLAN.md) · [Tracker](PROGRESS.md)

## Problem

BlueWake's game thread is one core's worth of translated PowerPC code, and the busiest Outset view needs ≈ 124–131 M host cycles a frame against ≈ 113 M for 30 FPS (#592). The research on #9 settled how far the translated program itself can be spread over cores: a few percent. Its execute loop at actor granularity is one scene region plus ≈ 200 regions of a few hundred cycles; the dependences run through global scratch, list links and counters; every exact reordering must be validated against the serial order, and what survives validation is cheap. Faster single cores keep helping; more cores don't.

The direction that does scale is to stop running subsystems as guest code. A subsystem the host implements natively is free of the guest's ordering inside itself: it can run on as many cores as it likes, as long as what it writes back to guest memory and what it charges in cycles is what the original would have produced. That is the certified-native discipline the project already applies to small routines, at subsystem scale, and it attacks single-core dependence from both sides: native code is faster per unit of work, and the work can be spread.

## Ranking

By potential gain at the busiest Outset view, largest first. "Native" is the serial gain from being host code at all; "parallel" is what two to four cores add on top. Estimates, not measurements; the first milestone of each plan replaces them.

| # | Service | Share of the frame today | Native, serial | Parallel, 2–4 cores | Scales to | Exactness class | Effort |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | **J3D draw side**: model calc, skinning, materials, packets, the GX stream | 16–20 % (#593: 19.9–26 M cycles) | ≈ 8 % of the frame | ≈ 6 % more (per-model jobs; the draw-buffer order and the GX assembly stay serial) | 4 lanes | "plays the same" with the GX stream and pictures as the oracle; cycle-exact possible at a higher cost | Months (#593 phase 2) |
| 2 | **Background collision**: `cBgW`/`dBgS` ground, wall and roof checks | ≈ 7 % here, 10–14 % in the lava room (#503, #501) | ≈ 3–5 % (a host spatial structure answers queries faster; #436/#542 showed a walk alone doesn't) | Little: each actor needs its answer at once; the world's per-frame update parallelizes | 1–2 lanes | Exact results (#542's harness) | Months |
| 3 | **The audio thread** (`JASystem`) | ≈ 6 % (#561) | ≈ 5 % (its own host thread, one frame of latency at most) | It *is* the parallel part | 1 lane | Bit-exact DSP command output; the `JASChannel` natives exist (#593's round 7) | Months |
| 4 | **Particles** (`dPa`, JPA) | ≈ 2–4 % (#592: sea, sky and particles ≈ 2.2 %; the Outset sampler ≈ 4 %) | ≈ 1–2 % | ≈ 1 % more (per emitter; JPA has its own RNG; consumed only at draw) | 2–3 lanes | Bit-exact simulation | Months |
| 5 | **Host overheads on the game thread**: the direct-call check, the dispatch loop, the GX stream's own writes | ≈ 10 % of the game thread is host code (#592) | ≈ 2–3 % more after #552/#531 | — | — | Exact by construction | Weeks each, diminishing |
| 6 | **Z-targeting scan** (`dAttention_c::Run`) | 41 % of the execute loop's guest cycles, mostly the native actor search already (#503) | ≈ 1–2 % for the remainder | — | — | Exact | Weeks |

Together: ≈ 25–30 % at the busiest view in theory, ≈ 12–18 % after overheads, the ordered parts of each subsystem and, on the Deck, the power budget (two cores at 25 / 50 / 75 % duty cost 1.9 / 7.4 / 11.7 % of game FPS, #9's sweep of 2026-11-13). The draw side is half of it and the only item that uses cores well; it goes first.

## How the gains vary by device

| Device | What applies |
| --- | --- |
| Steam Deck (4 cores, three in use, a shared power budget: E0 measured −21 % with two cores at full duty, and the duty sweep −1.9 / −7.4 / −11.7 % at 25 / 50 / 75 %) | The native half of each item in full; the parallel half discounted by the power penalty at the workers' real duty; two workers at most |
| Android (big.LITTLE, tighter thermals) | The native half on the big core; one worker, maybe two, on big cores only |
| Low-end desktop (slow, uniform cores, no cap) | Everything: the best case for the parallel half, three or four lanes |
| Apple, fast Windows desktops | Mostly headroom: these hold 30 already; the gain is render scale and the HD effects |

## Principles

- **Exact by the project's rules.** Each migration ships opt-in with the serial translation as the oracle: identical guest checkpoints where the class is cycle-exact; identical pictures, GX stream and audio digests where it is "plays the same"; deterministic run to run in every case.
- **Parallel from day one.** A hoisted subsystem is designed as jobs over a worker pool, never as a faster serial routine that is threaded later.
- **Measure before building.** Each plan's first milestone traces the subsystem's read and write sets and cycles with #9's tooling (`BLUEWAKE_SHADOW_TRACE`, `scripts/shadow_limit_study.py`) at the eight bench states, and replaces this table's estimate with a number.
- **One plan per service**, with #503's acceptance rule: ahead in every interleaved Deck launch, identical checkpoints or digests, per state; the per-device decision from the testing strategy in #9.

## Goals

| Goal | Target |
| --- | --- |
| The busiest Outset view at 30 FPS on the Deck | Needs ≈ 13 %: the draw side alone, if its estimate holds |
| Each service's plan opened with a measured share | #9's trace tooling, eight states |
| Every migration opt-in, serial as the default and the oracle | — |

## Non-goals

Parallelizing the translated program itself (settled by #9's E2); frame pipelining with latency; non-deterministic threading; changing game logic; 60 game updates a second.

## Risks

| Risk | Mitigation |
| --- | --- |
| A subsystem's guest-visible writes are wider than its API (J3D packets, draw buffers, `j3dSys`) | The trace's write sets define the contract before design |
| Cycle charges for a hoisted subsystem | Choose the class per service; the GX stream and pictures are the oracle for "plays the same" |
| The Deck's power budget takes back the parallel half | Workers park between jobs; the per-device decision; E0's duty sweep (measured 2026-11-13: two cores cost 1.9 / 7.4 / 11.7 / 21.3 % of game FPS at 25 / 50 / 75 / 100 % duty, so an item's net Deck gain is its gross gain less that curve at its duty) |
| Months per service | Order by gain; the draw side first; each lands and pays separately |
