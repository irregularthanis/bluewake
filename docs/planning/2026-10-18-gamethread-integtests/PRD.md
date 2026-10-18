# PRD — Game-thread optimization integrity tests

**Version:** 1.4 · October 18, 2026 · **Status:** Draft
**Requested by:** irregularthanis
**Audience:** Runtime contributors, maintainers, Deck testers
**Code baseline:** `087246ac43322484fb323af4e33b453c7a80a3cc`
**Committed PRD inspected:** `4a68ecae4725eb1ecea2d5d02f990e70c315237d`
[Technical plan](TECH_PLAN.md) · [Task tracker](PROGRESS.md)

## Problem and goal

Deck profiling identifies a game-thread bottleneck in measured outdoor scenes. Before offloading more work, extend correctness coverage around the existing native matrix-array routine and worker pool.

Deliver synthetic CI tests, translated/native comparisons, reproducible gameplay checks and multicore load evidence. A boot, higher CPU usage or serial fallback must not count as successful parallel qualification.

No implementation or passing tests are claimed.

## Scope

**Included:** FR-01–FR-09 below; test-first qualification before worker changes.
**Excluded:** Arbitrary guest-block/actor parallelism, Windows worker backend, changed timing/defaults/algorithms, cross-build save compatibility and guaranteed FPS gains.

| User | Required outcome |
|---|---|
| Contributor | Reproduce failures and prove optimized-path execution |
| Maintainer | Review exact outputs, activation and device evidence |
| Deck tester | Run bounded checks using isolated local inputs |
| Player | Preserve gameplay and saves during performance work |

## Existing coverage

| Foundation | Extend |
|---|---|
| Native math guards | Nontrivial inputs, thresholds, unchanged decline |
| Translated/native oracle | Three paths, boundary cases, candidate-owned evidence |
| POSIX pool | Partitions, publication, creation failure, teardown |
| Benchmark tour | Explicit settings, complete checkpoint/route validation |
| Save acceptance | Portable inputs and current route predicates |

Architecture: [runtime entities](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Runtime.md#runtime-entities) · [interaction boundaries](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Runtime.md#interaction-boundaries). Source changes live in TECH_PLAN.

## Requirements

### FR-01 — Differential correctness · P0

Architecture: [CPUState](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GuestState.md#cpustate-layout) · [guest-state ownership](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GuestState.md#ownership-and-address-model).

**Story:** Compare original translation, serial-native and parallel-native execution to detect semantic regressions.

Acceptance:

- Identical seeded inputs and timing mode across paths.
- Exact guest fields and relevant RAM/stack/global regions; sentinels detect unintended writes.
- Preserve floating-point bits, signed zero, FPSCR, reservations, return state and cycle/observation fields.
- Normalize declared host identity only.
- Report first field/address difference, function, seed, count, layout and requested/effective workers.
- Preserve existing cases; explain contract changes rather than rewriting expectations to hide failures.

### FR-02 — Thresholds and partitions · P0

Architecture: [module contents](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GameModule.md#module-contents) · [guest-state ownership](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GuestState.md#ownership-and-address-model).

**Story:** Detect skipped, duplicate and out-of-range work.

Acceptance:

- Serial plus 1/2/3 effective POSIX workers.
- Below/at/above each split threshold: currently 511/512/513, 767/768/769, 1023/1024/1025.
- Small/large and uneven arrays, non-identity matrices, distinct per-index values.
- Every index exactly once; no out-of-range writes.
- Worker-required cases prove nonempty worker-thread execution.
- Zero-length pool ranges covered; native-invalid counts follow decline contracts.

### FR-03 — Guards and fallback · P0

Architecture: [guest address resolution](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GuestState.md#guest-to-host-address-resolution) · [device deadlines](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Services.md#guest-time-and-deadlines).

**Story:** Unsafe native attempts decline without corrupting subsequent translated execution.

Acceptance:

- Disjoint, exact in-place and partial overlaps in both directions.
- Invalid values at first/middle/last positions; NaN/infinity and rejected ranges.
- Invalid addresses/aliases, write observation, FP modes, exceptions and timing limits.
- Cases on both sides of actual budget/deadline guards.
- Decline leaves CPU/RAM unchanged; routed fallback matches reference.

### FR-04 — Lifecycle and publication · P0

Architecture: [module loading and ABI](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GameModule.md#module-loading-and-abi) · [shutdown](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Host.md#shutdown).

**Story:** Completed calls leave no unfinished or stale worker activity.

Acceptance:

- At least 1,000 changing submissions.
- Outputs correct immediately on return and after subsequent jobs.
- Delayed workers cannot cause early return.
- Repeated isolated module load/run/unload completes within bounds.
- Preserve single-submitter contract; no concurrent unload promise.
- Supported TSan and separate ASan/UBSan coverage.
- Synchronization-based checks; sleeps alone cannot prove correctness.

### FR-05 — Configuration and failures · P0

Architecture: [host lifecycle](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Host.md#host-lifecycle) · [module contents](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GameModule.md#module-contents).

**Story:** Missing resources preserve correct results and bounded completion.

Acceptance:

- Fresh process per initialization/configuration.
- Unset/zero/negative/malformed/valid/over-limit worker requests.
- Inject failure before first worker and after partial creation.
- Verify effective count, output, return and teardown.
- Fault injection remains test-only; no per-vector player overhead.

### FR-06 — Execution evidence · P0

Architecture: [module loading and ABI](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GameModule.md#module-loading-and-abi) · [interaction boundaries](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Runtime.md#interaction-boundaries).

**Story:** Reviewers can distinguish parallel work from silent serial fallback.

Acceptance:

- Requested/effective workers, native hits/declines, array sizes/vectors and completed batches.
- Structured opt-in evidence from the actual candidate module.
- Missing diagnostics preserve compatibility but leave worker qualification incomplete.
- Synthetic worker-required case fails without activation.
- Gameplay with no eligible jobs may pass smoke checks, never worker qualification.
- Do not change computation/thresholds merely to activate tests.

### FR-07 — Gameplay smoke checks · P0 for device qualification

Architecture: [guest execution loop](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Host.md#main-loop-execution) · [input](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Services.md#input) · [graphics synchronization](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Graphics.md#synchronization-and-completion).

**Story:** Equivalent worker configurations preserve complete scripted routes.

Acceptance:

- Reuse existing benchmark launch/scene infrastructure.
- Worker settings 0/1/2; same binaries, state, inputs, modes, mods and settings.
- Outset, Forest Haven, dungeon and separate bird-cutscene fixture.
- Two repeatable serial baselines before candidates.
- Compare complete, nonempty checkpoint grids at equal guest progress.
- Missing modes/scenes/checkpoints, truncated logs or abnormal completion cannot pass.
- Headless and rendered evidence remain separate.
- Rendered cutscene/music/sailing observations include animation, geometry, audio and stalls.
- Missing fixtures/environments report explicit skips.

### FR-08 — Save/quit/reload · P1; required before new-offload promotion

Architecture: [memory card and SRAM](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Services.md#memory-card-and-sram) · [runtime persistence](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Host.md#runtime-inputs-and-persistence).

**Story:** Optimized execution preserves saving and restored progress.

Acceptance:

- Explicit input/output paths; copied card and isolated mutable data.
- Source inputs unchanged, including failures.
- Guest save chain, actual card change, guest reset and separate same-build reload.
- Serial/candidate routes independently regain control and expected progress.
- Current bounded route predicates replace historical constants.
- Same-build reload makes no upgrade-compatibility claim.

### FR-09 — Multicore load · P0 for multicore qualification

Architecture: [guest execution loop](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Host.md#main-loop-execution) · [guest time and exceptions](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GuestState.md#guest-time-callbacks-and-exceptions) · [EFB/copies/VI presentation](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Graphics.md#efb-copies-and-vi-presentation) · [graphics synchronization](https://github.com/irregularthanis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Graphics.md#synchronization-and-completion).

**Story:** Measure critical-path improvement under CPU contention while preserving results.

| Dimension | Required coverage |
|---|---|
| Workers | 0/1/2/3, effective count recorded |
| Mode | Headless; rendered Smooth Motion off/60 |
| Placement | Default; separate physical cores; shared SMT |
| Pressure | None; remote-core competitor; game-thread sibling; bounded all-core |
| Work | Threshold/large synthetic batches and actual scenes |
| Duration | Repeated short runs and paired 30-minute rendered soaks |

Acceptance:

- Discover topology and actual game/worker TIDs; validate scoped per-thread affinity.
- Deterministic compute-only competitors; record achieved duty/load.
- Bounded cleanup on every exit; no persistent system-policy changes.
- At least three interleaved short samples with fixed guest windows/warmup.
- Hold binaries/settings/power/display/charging constant; record clocks/temperature and available limits.
- Report throughput, thread CPU/runnable/blocked time where available, worker work, join wait and graphics-worker load.
- Validate true logic-completion timing before p50/p95/p99; retain sample count/window. VI/presentation timing is separate.
- Scripted load runs retain exact correctness; slowdown alone is not semantic failure.
- Soaks include transition, cutscene/music, sailing, pressure and copied-card save/reload.
- Manual segments use observations; scripted segments provide exact checkpoints.
- Separate synthetic scaling from real gameplay activation.
- Optional 5800X3D comparison cannot replace Deck qualification.
- Flag >3% median-throughput/p95 regressions with variability; no automatic significance claim.
- Later default changes require repeatable Deck benefit above noise and explained regressions.
- Report baseline defects separately; never attribute them without controlled comparison.

## Success and gates

| Gate | Target |
|---|---|
| Differential | Zero unexplained guest/RAM mismatches |
| Coverage | Every required path proven; candidate evidence belongs to candidate |
| Pool stress | ≥1,000 submissions; no duplicate/skipped/late work |
| Sanitizers | Zero findings in supported exercised lanes |
| Repeatability | Two matching serial baselines |
| Multicore | Named matrix, topology, pressure and paired soaks |
| Reporting | Truthful pass/fail/skipped/inconclusive |
| Execution budgets | ≤60 s fast; ≤10 min stress/sanitizers after build; validate on designated runner |

Unavailable required evidence leaves qualification incomplete. No FPS target applies to the infrastructure itself.

## Delivery

| Acceptance phase | Deliverable | Implementation milestones |
|---|---|---|
| M0 | Baseline/contracts | M0 |
| M1 | Fast tests | M1–M2 |
| M2 | Lifecycle/oracle/CI | M3–M4 |
| M3 | Runner/gameplay/save | M5–M7 |
| M4 | Metrics/load/Deck | M8–M10 |

Dates unscheduled. Milestone dependencies/task state live in PROGRESS.

## Constraints and risks

- Existing C/CMake/Python toolchain and single guest stream remain.
- Linux/POSIX workers qualify first; Windows retains serial coverage.
- Private modules/disc data/cards/states/audio/memory dumps stay local.
- Public CI uses generated inputs only.
- Keep a small fast lane; separate sanitizers, own-disc tests and device runs.
- Shared optimized code can share bugs: retain translated oracle.
- Nondeterministic baseline blocks exact comparisons.
- No eligible jobs means no demonstrated gameplay offload benefit.
- Instrumentation may perturb performance: compare diagnostics-off controls.
- A translated oracle validates this reference implementation, not perfect console equivalence.

## Clarifications

User confirmed existing context, opt-in diagnostics, ordinary documents and finalization. No Belmont installation or model setup.

Implementation choices, proposed APIs, exact files and milestone dependencies belong in TECH_PLAN. Manual soak and scripted checkpoint evidence are distinct. True game-update timing requires validation.

Before implementation, settle CI budgets/support, local fixture reproducibility, current save predicates and Deck tester availability. Missing decisions do not block synthetic MVP work.

## Definition of done

Required synthetic/oracle gates pass; deliberate partition/output/activation defects are detected. Fixture-dependent outcomes are explicit. Full Deck qualification additionally passes gameplay/save/multicore requirements.

No source, workflow, GitHub or hardware changes are implied by this PRD.

**History:** v1.0 initial; v1.1 multicore load; v1.2 planning reconciliation; v1.3 concise rewrite; v1.4 architecture entity/flow links. Requirements preserved.
