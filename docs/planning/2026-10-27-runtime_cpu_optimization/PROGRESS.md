# PROGRESS — Steam Deck runtime CPU optimization

Status: M0 control frozen; same-build Deck noise pending

[Product brief](PRD.md) · [Technical plan](TECH_PLAN.md)

## Milestones

### M0: Freeze baseline and method

Architecture: [performance workflow](../../performance/Overview.md#performance-workflow).

- [x] M0-T01: Capture and categorize a fixed worst-angle rendered Steam Deck profile.
- [ ] M0-T02: Measure three same-build stable/slow/worst rounds and record A/A noise.
- [ ] M0-T03: Freeze source/build receipts, scenes, metrics, and candidate-record format.

### M1: Measure paired direct-call guards (depends: M0)

Parallel with M2; owns direct-call generator and readiness-path analysis.

- [ ] M1-T01: Measure entry and return readiness checks separately, including calls/frame and exclusive cost.
- [ ] M1-T02: Record which readiness inputs can change during each eligible callee and which constant addresses are already filtered by generation.
- [ ] M1-T03: Propose one semantics-preserving specialization/amortization or record a measured no-go.

### M2: Split FP and gather-pipe helper cost (depends: M0)

Parallel with M1; owns helper-operation attribution only.

- [ ] M2-T01: Attribute `inline_fp.h` samples by PowerPC operation and surrounding state work.
- [ ] M2-T02: Split gather-pipe samples among packing, validation, parsing, queueing, and waits with thread ownership.
- [ ] M2-T03: Select one shared-helper candidate or record measured no-go results for both paths.

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

Screening evidence: a private 120-second headless diagnostic recorded 861
samples in `func_802456E0` (7.23% process share). Generated-source and GZLE01
symbol mapping assigns approximately 1.55% process-wide to the three principal
GroundCross routines and 3.37% to shared helpers. This informs M1/M2 ordering;
it does not complete their operation-level attribution or Deck acceptance.

Private profiles, saves, session logs, modules, and AppImages are not published.
