# PRD: Game-thread optimization integrity tests

**Project:** BlueWake  
**Status:** Draft for engineering review  
**Version:** 1.1  
**Created:** October 18, 2026  
**Requested by:** irregularthanis  
**Audience:** Runtime contributors, maintainers, and Steam Deck testers  
**Source baseline:** `087246ac43322484fb323af4e33b453c7a80a3cc` on `main`  
**Delivery:** Phased work before changing worker scheduling or adding game-thread offloads; no calendar deadline assumed.

## Executive summary

Extend BlueWake’s existing correctness tests so game-thread optimizations can be evaluated without weakening guest-state, memory, timing, save, or gameplay guarantees. The first concrete target is the existing native matrix-array routine and its synchronous worker pool. This establishes a reusable qualification pattern for later offloads, rather than attempting to parallelize arbitrary translated blocks.

The deliverable is layered evidence: fast synthetic tests in CI, differential tests against a contributor’s own translated module, reproducible gameplay smoke runs, and an explicit report showing which execution paths were exercised. Performance measurements follow correctness qualification. This work does not promise an FPS increase or prove whole-game correctness.

## 1. Problem statement

Steam Deck profiling in [issue #215](https://github.com/chrissotraidis/bluewake/issues/215) identifies translated game execution as a major limitation in the measured outdoor scenes. BlueWake already supports independent native vector-array work through `bluewake_parallel_range()`, making it a plausible experiment for distributing some computation across CPU cores.

Threading introduces failure modes that a successful boot or short visual check can miss: incorrect partition boundaries, stale job data, incomplete output publication, races, altered guest registers, and unsafe fallback after partial mutation. A benchmark can also appear to qualify workers while all useful work actually stays on the serial path.

Existing tests are substantial. The gap is targeted coverage and reusable execution evidence, not the absence of a test suite.

### Current foundations

| Existing component | Inspected behavior | Extension needed |
|---|---|---|
| `tests/native_math_guard_test.c` | Synthetic identity cases, unsafe-input rejection, unchanged CPU/RAM on decline, parallel-batch assertion in worker mode | Boundary cases, nontrivial outputs, worker configuration coverage |
| `tests/native_math_test.c` | Differential matrix/vector comparisons; 360 array cases at counts 2, 3, 17, 127, 1024, 4096; in-place operation and routed candidate support | Exact split thresholds, explicit candidate-module activation evidence, richer failure diagnostics |
| `tests/cpu_state_compare.h` | Field-wise guest-state comparison and host-pointer presence comparison | Reuse or extend consistently; avoid masking real guest differences |
| `cmake/composite/native_work_pool.c` | Persistent POSIX workers, synchronous join, serial fallback, destructor teardown | Focused partition, publication, failure-injection, and lifecycle tests |
| `scripts/bench_tour.py` | Fixed scene stops, same-state runs, checkpoint comparison, performance summaries | Worker configuration matrix and explicit coverage/validity gates |
| `scripts/save_continue_acceptance.sh` | Guest save chain, real copied-card writes, quit and separate reload | Portable explicit inputs; remove dependence on one developer’s paths and historical milestone constants |

No test run or passing result is claimed by this PRD. The baseline describes source inspection only.

## 2. Goals and objectives

1. Detect numerical, memory, guest-state, and synchronization regressions before worker changes are accepted.
2. Show that intended serial, native, fallback, and parallel paths actually executed.
3. Give contributors a short source-only feedback loop and a separate own-disc qualification workflow.
4. Preserve real saves by isolating acceptance runs in copied player data.
5. Make failures reproducible by recording exact source, binaries, configuration, seeds, and first differences.

### Non-goals

- Parallelizing actor updates, guest OS threads, or arbitrary translated chunks.
- Adding a Windows parallel-worker backend.
- Changing worker defaults, thresholds, algorithms, timing semantics, or rendering quality.
- Requiring exact equivalence between different behaviour-timing modes.
- Defining cross-build save compatibility, which needs separate requirements.
- Claiming exhaustive game integrity or a guaranteed Steam Deck speedup.

## 3. Users and stakeholders

| Audience | Need |
|---|---|
| Optimization contributor | Identify whether a change preserves results and actually reaches the optimized path |
| Maintainer/reviewer | Review a compact, reproducible acceptance record with clear limits |
| Steam Deck tester | Run bounded checks against local inputs without manually reconstructing the test environment |
| Player | Continue gameplay and saving without regressions introduced by performance work |

The maintainer reviews runtime contracts; contributors implement and run tests; a Deck tester supplies device evidence. These are proposed responsibilities, not assignments or approvals already obtained.

## 4. User stories and functional requirements

### FR-01 — Differential correctness (P0)

**Story:** As an optimization contributor, I want the translated, serial-native, and parallel-native paths compared from equivalent initial states, so that I can locate semantic regressions.

**Acceptance criteria:**

- Run the original translated function, serial native implementation, and parallel native implementation with identical guest inputs and the same timing mode.
- Compare guest CPU fields, relevant RAM ranges, and sentinel regions around input/output buffers. RAM comparison includes unintended writes, not only expected numerical outputs.
- Preserve exact floating-point bit patterns, including signed zero, wherever the current implementation promises exact output.
- Report the first mismatching guest field or memory address, entry point, seed, count, layout, requested workers, and effective workers.
- Normalize only declared host identity differences, such as backing-pointer addresses. Do not ignore guest registers, FPSCR, reservation state, cycle accounting, or observation fields to force a pass.
- Keep existing cases and fallback coverage. A mismatch cannot be fixed by updating the expected result to match the candidate without explaining the changed contract.

**Likely extension:** `tests/native_math_test.c`, sharing diagnostics with `tests/cpu_state_compare.h` where compatible.

### FR-02 — Split thresholds and partitions (P0)

**Story:** As a runtime contributor, I want boundary and uneven-size cases, so that splitting work cannot skip, duplicate, or overrun elements.

**Acceptance criteria:**

- Test serial execution and 1, 2, and 3 successfully created POSIX workers.
- For effective worker count W and current minimum grain G=256, test counts immediately below, at, and above (W+1)×G. The current examples are 511/512/513, 767/768/769, and 1023/1024/1025.
- Retain small and large cases and add uneven partitions. Values must vary by index, with non-identity matrices, so omitted or misplaced elements are detectable.
- For the pure pool tests, each element must be processed exactly once and no element outside the requested range may change.
- For each qualifying configuration, assert that parallel execution occurred and that worker threads executed nonempty ranges. A completed-batch counter alone does not prove correct partition coverage.
- Handle zero-length ranges at the pool API level; invalid native-function counts must follow their documented decline contract rather than being forced through the native path.

**Likely extension:** Existing matrix tests plus a new focused `tests/native_work_pool_test.c`.

### FR-03 — Guard and fallback preservation (P0)

**Story:** As a maintainer, I want unsafe cases to fall back without partial mutation, so that original translated execution remains a valid recovery path.

**Acceptance criteria:**

- Cover disjoint buffers, exact in-place operation, and partially overlapping buffers in both directions.
- Exercise invalid values at the beginning, middle, and end of an array, including NaN/infinity and values outside the native implementation’s admitted range.
- Test invalid addresses, aliases, enabled write observation, unsupported floating-point modes, pending exceptions, and insufficient cycle/deadline budget.
- Derive timing boundary cases from the actual guard conditions and test both sides of each boundary.
- On decline, verify unchanged guest CPU state and unchanged relevant RAM. Returning “declined” after performing work is a failure.
- Check the routed path: a declined native attempt must resume the reference translation and produce the reference result.

### FR-04 — Pool lifecycle and publication (P0)

**Story:** As a runtime contributor, I want repeated work and teardown tested under varied scheduling, so that a completed call never leaves unfinished or stale worker activity.

**Acceptance criteria:**

- Complete at least 1,000 sequential submissions with changing contexts, sizes, and expected outputs in the stress configuration.
- Verify outputs immediately on return and after later submissions to detect late writes.
- Exercise workers waiting for work, completion waits, repeated wakeups, and orderly teardown after completed work.
- Repeatedly load, exercise, and unload the module in an isolated process; require bounded completion and no surviving worker access to unloaded code.
- Test the supported single-submitter contract. Concurrent submissions and unloading concurrently with an active external call are not newly promised.
- Run source-only pool tests under ThreadSanitizer and memory-safety tests under ASan/UBSan in separate supported configurations.
- Use synchronization and bounded timeouts for lifecycle tests; sleep timing alone must not determine correctness.

### FR-05 — Configuration and resource failures (P0)

**Story:** As a contributor testing constrained devices, I want serial fallback and partial worker creation covered, so that unavailable threads do not corrupt results or hang execution.

**Acceptance criteria:**

- Use separate process launches for each configuration because pool initialization is process/module lifetime state.
- Cover unset, zero, negative, malformed, valid, and over-limit `BLUEWAKE_NATIVE_WORKERS` values according to the inspected parser contract.
- Inject worker-creation failure before the first worker and after one or more successful creations.
- Verify correct results, correct effective-worker reporting, bounded return, and clean teardown.
- Keep fault injection confined to tests or test-only build hooks; do not add normal per-vector overhead.

### FR-06 — Explicit execution evidence (P0)

**Story:** As a reviewer, I want to know which paths ran, so that a fallback cannot masquerade as successful worker qualification.

**Acceptance criteria:**

- Record requested/effective workers, native hits, native declines, array counts/max size, and completed parallel batches for the implementation actually under test.
- When testing a dynamically loaded candidate, obtain activation evidence from that candidate, not only from a separately linked test copy.
- A synthetic worker-required case fails if the required parallel path was not exercised.
- A real scene with no qualifying arrays reports “no eligible parallel work observed.” It may pass a general gameplay smoke check, but must not be labeled a gameplay worker-coverage pass.
- Avoid thresholds or counters that require changing the production computation merely to make the test execute.

### FR-07 — Reproducible gameplay smoke suite (P0 for device qualification)

**Story:** As a Deck tester, I want equivalent worker configurations exercised from the same local state and inputs, so that integration regressions are caught beyond isolated functions.

**Acceptance criteria:**

- Extend or wrap the existing benchmark tour rather than create an unrelated launch pipeline.
- Support worker settings 0, 1, and 2 using the same host/module binaries, save state, input schedule, timing mode, mods, and settings.
- Cover Outset sea, Forest Haven, a dungeon, and a separately supplied bird-cutscene state. Verify actual loaded scenes and completed routes.
- First establish repeatability with two baseline runs from the same state. Compare checkpoints at the same guest retraces, never by wall-clock timestamp.
- For this exact-computation worker comparison, unexplained guest checkpoint differences fail. Keep behaviour timing identical between baseline and candidate.
- Require nonzero matching checkpoint coverage; missing/truncated logs and missing states are not successful comparisons.
- Separate headless correctness runs from rendered integration runs. Renderer-derived host-pointer differences must not be mistaken for guest-state differences.
- Record visible model deformation, missing geometry, audio anomalies, crashes, stalls, and route completion during a rendered check of a cutscene with music and sailing.
- Mark unavailable fixtures or unsupported environments as explicit skips with reasons.

### FR-08 — Save/quit/reload acceptance (P1; required before promoting a new offload)

**Story:** As a player, I want optimized execution to preserve saving and reloading, so that a performance change cannot silently damage progress.

**Acceptance criteria:**

- Accept explicit app, module, disc/data, card, and output paths rather than require historical developer directories.
- Copy the source card and isolate SRAM, preferences, and state outputs; verify the source card remains unchanged.
- Observe the game’s save chain and actual card-file change, then verify guest quit/reset and reload through a separate launch of the same build.
- Perform a serial reference run and a worker-enabled run from equivalent copied inputs; both must regain control and expected saved progress.
- Replace obsolete exact retrace assumptions with documented route invariants and justified bounds for the selected baseline.
- State that same-build reload does not establish upgrade compatibility.

### FR-09 — Multicore game-thread load and contention tests (P0 for multicore qualification)

**Story:** As a Steam Deck optimization contributor, I want the game execution thread and its offloaded jobs measured under controlled multicore load, so that extra CPU use demonstrably shortens the critical path without introducing races, starvation, or frame-time regressions.

These tests exercise one authoritative guest execution stream plus its supported native jobs. They do not run independent copies of translated guest blocks concurrently.

**Required test matrix:**

| Dimension | Required cases | Interpretation |
|---|---|---|
| Worker count | 0, 1, 2, 3 requested workers, with effective count recorded | Compare serial work with one through three extra worker threads on the Deck's four physical cores |
| Execution mode | Headless/unpaced; rendered with Smooth Motion off; rendered with Smooth Motion 60 | Separate computation throughput from competition with normal graphics/interpolation work |
| CPU placement | OS scheduling default; diagnostic placement on separate physical cores; diagnostic placement sharing an SMT core | Distinguish physical-core benefit from logical-thread contention |
| External CPU pressure | None; one competitor on a physical core separate from the game thread; competitor on the game thread's SMT sibling; bounded all-core contention | Measure scheduling and shared-resource sensitivity |
| Workload size | Below/at/above current split thresholds; large eligible batches; actual gameplay states | Distinguish insufficient job size from scheduler/worker overhead |
| Duration | Short repeatable comparisons; sustained rendered soak | Detect immediate throughput effects and changes as temperature/power settle |

**Acceptance criteria:**

- Discover and record CPU topology from the device. Logical CPU numbering must not be assumed to correspond to physical cores or SMT siblings.
- Identify the actual game execution TID and native worker TIDs. Process-wide CPU affinity alone is insufficient to claim controlled game-thread placement.
- Any diagnostic affinity controls are opt-in, scoped to test processes/threads, and do not change normal player scheduling.
- Use a deterministic compute-only background workload with a documented thread count, affinity, and duty cycle. Record achieved CPU load, not only requested load. Avoid unrelated storage/network activity.
- Bound and clean up every competitor process on normal exit, error, interruption, or timeout. Do not alter persistent system governor, power, or thermal settings as part of the test.
- For short runs, use the same guest state and fixed guest-time window, discard a documented warmup, and run at least three interleaved rounds per compared configuration. Keep changes to a single factor within each pair rather than require an impractical full Cartesian matrix.
- Hold timing mode, binaries, settings, mods, texture configuration, power limit, display refresh, and charging state constant within a comparison. Record CPU frequencies, temperature, and available power/throttling indicators so contaminated comparisons can be marked inconclusive.
- Collect game FPS/retraces per second with units, game-thread CPU time and runnable/blocked time where available, native-worker CPU time, completed parallel batches, job-size distribution, fork/join wait time, and GX/render/interpolation worker load.
- Record median and p95/p99 game-frame time, hitch count, and the sample count/window used for each percentile. If current logs cannot provide real game-frame timings, add bounded diagnostic instrumentation; do not label presentation intervals as game-frame intervals.
- All workers-off/on comparisons under CPU pressure retain FR-01/FR-07 correctness requirements. Under load, lower speed alone is not a correctness failure; guest-state divergence, corruption, incomplete work, deadlock, or a bounded test timeout is a failure.
- Repeatability and checksum checks remain required even if all-core contention prevents real-time gameplay.
- Run a minimum 30-minute rendered soak for serial and the selected candidate worker configuration, including a scene transition, cutscene with music, sailing, and save/reload on copied data. Record stalls and audio anomalies. Include a bounded background-load segment and compare against the serial configuration under the same pressure.
- Separate synthetic stress results from actual game-path activation. Synthetic parallel speedup cannot establish that a gameplay scene benefits.
- Run the same short no-pressure matrix on the user's Ryzen 5800X3D when available as a secondary comparison. Deck qualification remains required; desktop success is not a substitute.

**Result classification and optimization gate:**

- Report throughput ratios and frame-time changes against the serial configuration under the same pressure/placement, including run-to-run variation.
- Higher aggregate CPU utilization is not a success metric. The useful outcome is less wall time on the game-thread critical path with preserved outputs.
- If requested workers never activate, classify the test as insufficient workload coverage, not failed scaling.
- Flag regressions greater than 3% in median throughput or p95 game-frame time for investigation, while reporting the raw values and variability. This is a proposed triage threshold, not a universal proof of statistical significance.
- No worker-default change is part of this PRD. A later optimization proposal must demonstrate a repeatable Deck gain greater than measured noise and explain any repeatable contention or tail-latency regression before recommending a configuration.
- If the original build already stalls or diverges under the stress scenario, retain that evidence, report baseline failure separately, and do not attribute it to the candidate without a controlled comparison.

**Likely extension:** A separate multicore mode in a local qualification runner that reuses `bench_tour.py` launch/scene handling, plus opt-in per-thread/job timing. Detailed timing and load generation stay outside the fast CI lane.

## 5. Success metrics

Use engineering acceptance metrics rather than adoption metrics.

| Metric | Baseline from inspection | Completion target |
|---|---|---|
| Threshold adjacency | Existing array counts omit exact 512/768 boundaries | Below/at/above coverage for each tested effective worker count |
| Differential mismatches | Existing oracle coverage exists; not executed for this PRD | Zero unexplained CPU/RAM mismatches in the required matrix |
| Parallel activation | Existing assertions vary by local versus loaded-candidate path | Explicit activation evidence for every worker-required case |
| Pool stress | Dedicated suite not established by this inspection | At least 1,000 submissions; zero skips/duplicates/late writes |
| Sanitizer findings | No new results claimed | Zero findings in supported exercised configurations |
| Gameplay repeatability | Existing tour/checkpoint tools | Two repeatable baseline runs before candidate comparison |
| Acceptance reporting | Several independent scripts | One summary linking configuration, coverage, outcome, and evidence |
| Multicore load coverage | No fresh device runs claimed | Worker-count matrix, topology-aware contention cases, and 30-minute serial/candidate soaks |
| Scaling evidence | Aggregate CPU load cannot establish benefit | Critical-path timings, per-thread CPU/wait data, and frame-time distribution with configuration and variability |

Proposed runtime budgets after test binaries are built: fast source-only suite ≤60 seconds on the designated Linux CI runner; stress/sanitizer lane ≤10 minutes on that runner. Establish actual baselines during the first implementation milestone and adjust workload placement with recorded rationale rather than silently dropping cases. Module compilation and own-disc gameplay are outside those budgets.

No minimum FPS improvement is required to complete this test infrastructure.

## 6. Scope and delivery boundaries

**MVP:** FR-01 through FR-06, source-only CTest integration, private differential runner, and documented status/skip semantics.

**Integration qualification:** FR-07 and FR-08, using private local fixtures and actual Steam Deck runs. FR-09 adds mandatory multicore load, contention, and sustained-run qualification before promoting an offload.

**Future extensions:** Apply the same oracle/activation pattern to newly identified skinning, animation, or other native kernels once profiling identifies worthwhile candidates. Each new kernel needs its own dependency and guest-state contract.

The PRD does not authorize changing runtime semantics, worker defaults, or reference expectations. Those are separate changes reviewed with the evidence this suite produces.

## 7. Technical considerations

### Correctness layers

| Layer | Inputs | Expected environment | What a pass establishes |
|---|---|---|---|
| Synthetic guards and pool tests | Generated data only | Linux CI; applicable cross-platform jobs | Specific contracts and edge cases behave as asserted |
| Differential oracle | Local translated reference module and candidate | Contributor-owned environment | Tested functions match reference state/output on exercised inputs |
| Deterministic routes | Local disc, states, copied cards | Linux desktop and Deck | Tested routes preserve checkpoint behavior |
| Rendered/save acceptance | Real app and copied player data | Deck session | Bounded visible/audio/save behavior checks |

Linux/POSIX is the worker implementation target. Windows must retain its serial behavior and pass applicable compilation and serial tests; no Windows worker activation assertion is valid. Other POSIX platforms can run the focused tests without substituting their performance for Deck evidence.

### Comparison policy

Use field-wise guest comparison where allocations or host pointers differ. Preserve the established distinction between host identity and guest semantics; do not blanket-ignore `CPUState` bytes. An original translated module is a reference for this implementation, not proof of perfect GameCube hardware equivalence.

### Fixtures and data

CI uses generated matrices and buffers only. Disc-derived modules, saves, states, audio dumps, and full memory dumps remain local. Reports identify inputs by digest and local metadata; they must not upload private fixtures. Diagnostic memory excerpts require deliberate local inspection.

### Failure isolation

Worker configuration and injected failures run in child processes. Hangs terminate with a recorded timeout and failure; timeout handling must preserve the caller’s data and useful logs. A detected baseline problem is reported separately, not hidden by relaxing checks.

## 8. Developer experience and reporting

Provide a documented entry point for fast synthetic tests and one for optional private qualification. Each report includes:

- Source and RecompCore revisions; compiler; host/module digests.
- OS/device, timing mode, worker request/effective count, scene/state identifier, and relevant settings.
- Seed/case counts; actual path activation; checkpoint count and first mismatch.
- Separate correctness, sanitizer, gameplay, and performance outcomes; multicore reports also include CPU topology/affinity, competitor load, per-thread timing, and game-frame percentiles.
- Per-test status: pass, fail, skipped, or inconclusive. A required-gate skip/inconclusive result makes aggregate qualification incomplete.

Keep normal runs concise. Emit details on failure and structured machine-readable results for comparison. User-supplied output paths are explicit and unrelated files are preserved. No player-facing settings UI is required.

## 9. Milestones

Dates are intentionally unscheduled; estimates follow the first implementation review.

| Milestone | Deliverable | Exit criterion |
|---|---|---|
| M0 — Baseline | Re-run existing applicable tests; document current runner commands and gaps | Existing failures/skips separated from proposed additions |
| M1 — Fast regression tests | Threshold, partition, guard, activation, configuration coverage | Required synthetic matrix passes; deliberate boundary/output defects are detected |
| M2 — Lifecycle and oracle | Failure injection, stress, sanitizer jobs, three-path comparisons | Required lanes pass and loaded-candidate worker activation is proven |
| M3 — Gameplay harness | Worker-config route comparison and portable save acceptance | Repeatable reference runs; informative incomplete/failure statuses |
| M4 — Deck qualification | Own-disc headless/rendered/save and multicore load evidence | FR-07 through FR-09 pass; topology, contention and soak results distinguish correctness from scaling |

Each milestone can be a focused PR. Production optimization work follows the relevant completed gates.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Few or no eligible arrays in the slow scene | Record coverage honestly; retain synthetic worker proof; reassess profiling priorities |
| Both optimized paths share the same bug | Compare against original translated execution and independent synthetic expectations |
| Nondeterministic baseline | Reproduce twice first; stop exact comparison until its cause is understood |
| Raw host pointers cause false mismatches | Compare declared guest fields and normalize only documented host identity |
| Race is rare | Repeated deterministic cases, controlled scheduling, sanitizer lane, lifecycle subprocesses |
| Test instrumentation alters speed | Measure performance separately without sanitizer/stress hooks |
| Private inputs unavailable in CI | Keep synthetic checks public and own-disc lanes explicitly optional to invoke |
| Existing save script is stale | Port inputs and route assertions before making it a gate |
| More tests slow iteration | Keep a bounded fast lane and separate stress/device qualification lanes |

## 11. Dependencies and assumptions

- Existing host/module ABI, native math readiness handshake, and private reference-module support remain available.
- Implementation verifies the baseline and applicable repository instructions before edits; links below pin the inspected revision.
- A Linux runner supports pthread tests; at least one supported runner can execute ThreadSanitizer.
- A contributor provides local supported-disc and state/card inputs for private qualification.
- A Steam Deck is available for final device evidence; the user's 5800X3D is a secondary comparison if available.
- Worker callers retain the current single-submitter, synchronous-return contract.
- Contributors can add narrow test-only seams for worker-creation failures without changing normal runtime behavior.

## 12. Open questions and decisions

| Decision | Proposed default | Resolve by |
|---|---|---|
| Exact CI lane and runtime budget | Fast Linux lane plus separate sanitizer/stress lane | M0 |
| Worker evidence from loaded candidates | Use existing exported report first; add a structured test interface only if necessary | M1 |
| Which existing private state/route fixtures are reproducible on the candidate | Validate Outset first, then Forest Haven/dungeon/bird | M3 |
| Save-route invariants supported by current builds | Establish against the selected baseline, preserving actual write/reload checks | M3 |
| Other reference-suite CPU comparison inconsistencies | Align with documented guest semantics without weakening comparisons | M2 |
| Who performs Deck qualification | Request a contributor with the hardware after reproducible commands exist | M4 |

None blocks drafting or implementing the source-only MVP. Runtime contract changes discovered during implementation require explicit design review.

## 13. Review and definition of done

This document is a proposal; no maintainer or contributor sign-off is implied.

The test-extension work is complete when the mandatory synthetic and differential requirements pass, documented fixture-dependent checks report truthful outcomes, and the harness detects deliberately introduced partition/output/activation defects. Full Deck qualification additionally requires the device route and save checks.

A future offload must satisfy the applicable correctness gates, prove execution-path coverage, and then supply separate performance evidence. Passing this suite supports bounded confidence; it does not establish whole-game correctness.

## Appendix: source references

All BlueWake code links pin the inspected revision.

- [Guest-state ownership](https://github.com/chrissotraidis/bluewake/blob/087246ac43322484fb323af4e33b453c7a80a3cc/docs/architecture/GuestState.md)
- [Host execution loop](https://github.com/chrissotraidis/bluewake/blob/087246ac43322484fb323af4e33b453c7a80a3cc/docs/architecture/Host.md#main-loop-execution)
- [Native matrix/vector implementation](https://github.com/chrissotraidis/bluewake/blob/087246ac43322484fb323af4e33b453c7a80a3cc/cmake/composite/native_math.c)
- [Worker pool and lifecycle](https://github.com/chrissotraidis/bluewake/blob/087246ac43322484fb323af4e33b453c7a80a3cc/cmake/composite/native_work_pool.c)
- [Worker callback contract](https://github.com/chrissotraidis/bluewake/blob/087246ac43322484fb323af4e33b453c7a80a3cc/cmake/composite/native_work_pool.h)
- [Synthetic math guards](https://github.com/chrissotraidis/bluewake/blob/087246ac43322484fb323af4e33b453c7a80a3cc/tests/native_math_guard_test.c)
- [Translated/native differential comparisons](https://github.com/chrissotraidis/bluewake/blob/087246ac43322484fb323af4e33b453c7a80a3cc/tests/native_math_test.c)
- [Guest CPU comparison helper](https://github.com/chrissotraidis/bluewake/blob/087246ac43322484fb323af4e33b453c7a80a3cc/tests/cpu_state_compare.h)
- [Host CMake test registration](https://github.com/chrissotraidis/bluewake/blob/087246ac43322484fb323af4e33b453c7a80a3cc/runtime/host/CMakeLists.txt)
- [Benchmark tour](https://github.com/chrissotraidis/bluewake/blob/087246ac43322484fb323af4e33b453c7a80a3cc/scripts/bench_tour.py)
- [Benchmark-tour tests](https://github.com/chrissotraidis/bluewake/blob/087246ac43322484fb323af4e33b453c7a80a3cc/tests/test_bench_tour.py)
- [Save/quit/reload acceptance](https://github.com/chrissotraidis/bluewake/blob/087246ac43322484fb323af4e33b453c7a80a3cc/scripts/save_continue_acceptance.sh)
- [Existing integration evidence, PR #30](https://github.com/chrissotraidis/bluewake/pull/30)
- [Deck measurements, issue #215](https://github.com/chrissotraidis/bluewake/issues/215)
- [Requested PRD Generator skill](https://github.com/jamesrochabrun/skills/blob/main/skills/prd-generator/SKILL.md)
- [PRD template used as structure](https://github.com/jamesrochabrun/skills/blob/main/skills/prd-generator/references/prd_template.md)

**Change log:** v1.0 — October 18, 2026 — Initial technical PRD, grounded in source inspection and the preceding optimization discussion. v1.1 — October 18, 2026 — Added FR-09 multicore load, topology/SMT contention, scaling metrics, and sustained gameplay qualification at the user's request.
