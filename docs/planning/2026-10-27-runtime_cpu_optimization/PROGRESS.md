# PROGRESS — Steam Deck runtime CPU optimization

Status: M0 baseline evidence captured; candidate mapping open

[Product brief](PRD.md) · [Technical plan](TECH_PLAN.md)

## Milestones

### M0: Freeze baseline and method

Architecture: [performance workflow](../../performance/Overview.md#performance-workflow).

- [x] M0-T01: Capture and categorize a fixed worst-angle rendered Steam Deck profile.
- [ ] M0-T02: Measure three same-build stable/slow/worst rounds and record A/A noise.
- [ ] M0-T03: Freeze source/build receipts, scenes, metrics, and candidate-record format.

### M1: Map translated hotspots (depends: M0)

Parallel with M2 and M3; owns translated/decomp source mapping.

- [ ] M1-T01: Resolve the five leading `func_*` chunks to contained original functions and sampled instructions.
- [ ] M1-T02: Record callers, activation counts, exclusive cost, and existing native/generator coverage.
- [ ] M1-T03: Select one safety-bounded candidate or record a measured no-go.

### M2: Split dispatch and guest-state cost (depends: M0)

Parallel with M1 and M3; owns dispatch/resolver/guard analysis.

- [ ] M2-T01: Measure calls and exclusive cost for dispatch, alias resolution, direct-call readiness, and host guards.
- [ ] M2-T02: Document invariants and invalidation events for the dominant repeated check.
- [ ] M2-T03: Select one eliminable/amortizable operation or record a measured no-go.

### M3: Establish GX impact (depends: M0)

Parallel with M1 and M2; owns GX worker and game-thread wait correlation.

- [ ] M3-T01: Correlate conversion symbols, draw volume, worker CPU, queues, and game-thread waits per frame.
- [ ] M3-T02: Determine whether conversion blocks frame progress in stable, slow, or worst views.
- [ ] M3-T03: Select one GX candidate or record that it is not currently frame-limiting.

### M4: Implement the strongest candidate (depends: M1, M2, M3)

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

Private profiles, saves, session logs, modules, and AppImages are not published.
