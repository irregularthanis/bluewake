# PROGRESS — Steam Deck runtime CPU optimization

Status: M0 complete; M1 rejected; M2 complete; M3 ready

[Product brief](PRD.md) · [Technical plan](TECH_PLAN.md)

## Milestones

### M0: Freeze baseline and method

Architecture: [performance workflow](../../performance/Overview.md#performance-workflow).

- [x] M0-T01: Capture and categorize a fixed worst-angle rendered Steam Deck profile.
- [x] M0-T02: Measure three same-build stable/slow/worst rounds and record A/A noise.
- [x] M0-T03: Freeze source/build receipts, scenes, metrics, and candidate-record format.

### M1: Measure paired direct-call guards (depends: M0)

Parallel with M2; owns direct-call generator and readiness-path analysis.

Decision: rejected. A bounded return specialization regressed every automated
scene and changed the geometric-mean median by -1.88%.

- [x] M1-T01: Measure entry and return readiness checks separately and run a direct source-matched candidate A/B.
- [x] M1-T02: Record which readiness inputs remain mutable across an eligible callee and retain their checks.
- [x] M1-T03: Test one semantics-preserving specialization and record the measured no-go.

### M2: Split FP and gather-pipe helper cost (depends: M0)

Parallel with M1; owns helper-operation attribution only.

- [x] M2-T01: Attribute `inline_fp.h` samples by PowerPC operation and surrounding state work.
- [x] M2-T02: Split gather-pipe samples among packing, validation, parsing, queueing, and waits with thread ownership.
- [x] M2-T03: Select one shared-helper candidate or record measured no-go results for both paths.

### M3: Select the implementation candidate (depends: M1, M2)

- [ ] M3-T01: Rank D1–D3 by exclusive cost, removable work, safety, and expected player-facing gain.
- [ ] M3-T02: If none qualifies, price a complete GroundCross-family replacement against its measured ceiling and PR #436.
- [ ] M3-T03: Freeze one candidate contract and its focused correctness/activation tests.

### M4: Implement the strongest candidate (depends: M3)

- [ ] M4-T01: Rank the three tracks and select the strongest safety-bounded candidate.
- [ ] M4-T02: Implement one default-off isolated change with a fallback and focused contract tests.
- [ ] M4-T03: Build source-matched control and candidate artifacts and record hashes.

### M5: Qualify or reject (depends: M4)

- [ ] M5-T01: Run interleaved stable/slow/worst fixed-view A/B against measured noise.
- [ ] M5-T02: If positive, run the full headless/rendered scenes, checkpoints, and player-facing traversal.
- [ ] M5-T03: Publish aggregate evidence and retain or reject the candidate.

## Evidence ledger

| Task | Commit / artifact | Command / method | Environment / input | Result |
| --- | --- | --- | --- | --- |
| M0-T01 | Profiler prototype [`d1bb41b`](https://github.com/irregularthanis/bluewake/commit/d1bb41b); private `perf.data`/JSON/Markdown | 20 s rendered capture at 99 Hz; 3,195 leaf samples | Steam Deck LCD, Game Mode, fixed worst Outset angle | Process: translated 39.6%, GX/Aurora 15.3%, guest/dispatch 9.1%. Game thread: translated 64.6%, guest/dispatch 13.4%, host 9.1%, native replacements 6.3%. |
| M0 control receipt | Upstream [`v0.9.0`](https://github.com/chrissotraidis/bluewake/releases/tag/v0.9.0) `211abfd`; private provenance and AppImage | Verify clean checkout, release dependency lock, provenance fields and SHA-256 | Clang 18.1.3, `x86-64-v3`, production options and local PGO | AppImage `476a335…`; module `7b094be…`; source clean. Ready for same-build Deck A/A. |
| M0-T02 (headless portion) | Private Deck evidence `bluewake-m0-control-a-vs-bluewake-m0-control-b-20261027T123601Z` | Ten runs/alias, five-pair ABBA tour; identical AppImage SHA-256 `476a335…` | Steam Deck; shared fixed state; five headless scenes | 5/5 scenes and 31/31 identical checkpoints every run; scene noise -0.07% to +0.17%; geometric-mean drift -0.00%. Rendered fixed views remain open. |
| M0-T02 | Private Deck evidence `/home/deck/bluewake-m0/rendered/{stable,slow,worst}-{1,2,3}` | Three stationary 30 s Game Mode rounds/view; session rate/busy plus `perf stat` | Same running `0.9.0` control; stable, slow and worst Outset camera views | Stable 59.88–59.95, slow 55.00–55.78, worst 49.01–49.70 retraces/s; rendered rate spread 0.12%, 1.42%, 1.41%. |
| M0-T03 | [`v0.9.0`](https://github.com/chrissotraidis/bluewake/releases/tag/v0.9.0) receipt and this planning trio | Freeze source/pins/options/hashes, fixed-view fields, headless checkpoints, metrics and candidate record | Control AppImage `476a335…`; private state/card and evidence retained on Deck | Control and method frozen; later candidates require isolated source receipts and view-specific improvement beyond observed noise. |
| M1 setup | [`direct_calls.h`](../../../cmake/composite/direct_calls.h), [`direct_calls.py`](../../../scripts/windows/direct_calls.py), and host reporting in [`main.c`](../../../runtime/host/src/main.c) | Opt-in `BLUEWAKE_DIRECT_CALL_MEASURE=1`; separate entry/return outcomes and expected/diverted returns | Branch remains based on frozen `v0.9.0` control `211abfd` | Source prepared; transformation tests, repository audit and diff check pass. Build and Deck measurements remain open. |
| M1-T01/T02 | Private Deck evidence `bluewake-m1-direct-calls/`; AppImage SHA-256 `03bb2b60…` | Game Mode stable/slow/worst session; entry/return outcomes at clean exit | PR head `d97adec`; Clang 18; `x86-64-v3`; measurement enabled | 2.239B entry checks, 99.40% allowed; 1.750B reached return checks, 99.79% allowed; 20.60% of allowed entries diverted before that guard. Mutable budget/address state produced real rejections. |
| M1-T03 | Private Deck evidence `bluewake-m1-return-specialized/headless/bluewake-m1-candidate-vs-bluewake-m1-control-20261027T174009Z`; underlying AppImage `ce0e8bed…` | 10 runs/mode, five-pair ABBA, fixed five-scene tour; same AppImage with candidate env flag toggled | Steam Deck; 5/5 scenes and 31/31 identical checkpoints every run | Candidate regressed every scene by 1.65–2.34%; aggregate -1.88%. Rendered stable/worst neutral; slow -4.15%. Rejected and specialization source removed. |
| M2 initial attribution | Private Deck evidence `/home/deck/bluewake-m2-attribution/worst-control/`; frozen M0 AppImage `476a335…` | 120 s whole-process `perf` capture at 99 Hz; leaf symbols grouped by helper family | Steam Deck Game Mode; fixed worst Outset view; 18,946 samples; zero lost | FP helpers 0.46%; slow memory helpers 1.48%; combined ceiling 1.94%. Gather stages are inlined, so an attribution-only build is required before selection. |
| M2 diagnostic setup | `--gather-pipe-profile`; [`gather_pipe.h`](../../../cmake/composite/gather_pipe.h) and [`gather_pipe_batch.h`](../../../cmake/composite/gather_pipe_batch.h) | Preserve validation, packing and drain as distinct symbols only when explicitly requested | Default production build remains inline; diagnostic build changes code shape and cannot be an A/B candidate | Syntax/CLI checks passed; the same-view capture completed in M2-T01/T02/T03. |
| M2-T01/T02/T03 | Private Deck evidence `/home/deck/bluewake-m2-attribution/worst-pipe-profile/`; AppImage `b188e84d…`; module `9cfce5bd…` | 120 s whole-process `perf` capture at 99 Hz with profiler-visible gather stages | Steam Deck Game Mode; fixed worst Outset view; 18,617 samples | Validation 1.01%, packing 0.14%, drain 0.09%, FP 0.44%. Diagnostic calls inflate the combined total, so values rank stages rather than predict gain. Select alias-overlap fast answer; reject packing, drain and FP as standalone candidates. |
| M2 alias rejection census | Private Deck log `/home/deck/bluewake-m2-attribution/alias-cost.log` | Existing `BLUEWAKE_TRACE_ALIAS_COST=1`; stable/slow/worst views; clean exit | Diagnostic AppImage `b188e84d…`; no FPS claim; temporary launcher variable and redirection removed afterward | Primary runtime copy: 1.384B resolver calls, 97.7% bounds-pruned; 31.49M remaining calls and 31.49M hits. Select generation-keyed FIFO-window overlap cache using RecompCore #45; preserve resolver fallback. |

Screening evidence: a private 120-second headless diagnostic recorded 861
samples in `func_802456E0` (7.23% process share). Generated-source and GZLE01
symbol mapping assigns approximately 1.55% process-wide to the three principal
GroundCross routines and 3.37% to shared helpers. This informs M1/M2 ordering;
it does not complete their operation-level attribution or Deck acceptance.

Private profiles, saves, session logs, modules, and AppImages are not published.
