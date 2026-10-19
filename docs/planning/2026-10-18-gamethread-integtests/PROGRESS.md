# PROGRESS — Game-thread integrity tests

**Status:** Planned; nothing implemented or tested.
**Revision:** 1.2 · October 18, 2026
**Source:** `4a68ecae4725eb1ecea2d5d02f990e70c315237d`
[Requirements](PRD.md) · [Implementation](TECH_PLAN.md)

## Milestones

### M0: Baseline and qualification contracts

Architecture: [runtime entities](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Runtime.md#runtime-entities) · [guest execution loop](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Host.md#main-loop-execution).

- [ ] M0-T01: Record revisions, tests, exports, fixtures and existing failures.
- [ ] M0-T02: Trace native/worker selection and both CMake entry points.
- [ ] M0-T03: Validate logic-update marker; freeze metrics/report contracts.
- [ ] M0-T04: Check overlapping PRs/branches and release-freeze rules.

### M1: Source-only test build integration (depends: M0)

Architecture: [Linux build flow](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Build.md#linux-builder) · [compile/package flow](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Build.md#7-compile-and-package).

- [ ] M1-T01: Extract shared native-math CMake registration; preserve targets/flags.
- [ ] M1-T02: Add standalone real-pool build without renderer dependencies.
- [ ] M1-T03: Register worker configurations, labels/timeouts and Linux build targets.
- [ ] M1-T04: Verify Linux tests and Windows serial build compatibility.

### M2: Guard and differential boundary coverage (depends: M1)

Architecture: [CPUState](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GuestState.md#cpustate-layout) · [guest address resolution](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GuestState.md#guest-to-host-address-resolution).

- [ ] M2-T01: Add threshold, uneven, non-identity, sentinel and invalid-input cases.
- [ ] M2-T02: Extend three-path oracle and guest-state mismatch diagnostics.
- [ ] M2-T03: Test unchanged decline, routed fallback, overlaps and timing guards.
- [ ] M2-T04: Assert synthetic worker ranges; detect deliberate partition/output defects.

### M3: Worker lifecycle and opt-in execution diagnostics (depends: M2)

Architecture: [module loading and ABI](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GameModule.md#module-loading-and-abi) · [shutdown](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Host.md#shutdown).

- [ ] M3-T01: Inject creation failures; verify effective worker counts.
- [ ] M3-T02: Add 1,000-submission stress and repeated DSO lifecycle tests.
- [ ] M3-T03: Add gated diagnostics and candidate-owned activation snapshots.
- [ ] M3-T04: Verify outputs, exports, delayed-worker completion and publication.

### M4: Sanitizer and regression CI lanes (depends: M3)

Architecture: [Linux build flow](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Build.md#linux-builder).

- [ ] M4-T01: Add separate standalone TSan and ASan/UBSan jobs.
- [ ] M4-T02: Run fast C/Python regressions; preserve Windows checks.
- [ ] M4-T03: Measure budgets; report unsupported sanitizer coverage explicitly.
- [ ] M4-T04: Run audits/attribution and mutation/timeout failure checks.

### M5: Qualification runner and report foundation (depends: M0)

Architecture: [host lifecycle](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Host.md#host-lifecycle) · [runtime persistence](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Host.md#runtime-inputs-and-persistence).

- [ ] M5-T01: Define versioned report/manifest and status aggregation.
- [ ] M5-T02: Implement isolated subprocess groups, timeouts, cleanup and outputs.
- [ ] M5-T03: Test malformed evidence, fake-app failures, cleanup and paths.
- [ ] M5-T04: Expose native/gameplay/load/soak commands.

### M6: Deterministic gameplay worker comparisons (depends: M3, M5)

Architecture: [guest execution loop](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Host.md#main-loop-execution) · [guest time and exceptions](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GuestState.md#guest-time-callbacks-and-exceptions).

- [ ] M6-T01: Pass explicit worker/settings overrides after sanitization.
- [ ] M6-T02: Validate complete modes, scenes, retraces and checkpoint grids.
- [ ] M6-T03: Run repeatable serial baselines and interleaved worker comparisons.
- [ ] M6-T04: Separate smoke correctness from activation; document scene fixtures.

### M7: Portable save acceptance (depends: M6)

Architecture: [memory card and SRAM](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Services.md#memory-card-and-sram) · [runtime persistence](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Host.md#runtime-inputs-and-persistence).

- [ ] M7-T01: Parameterize inputs; preserve legacy save entry point.
- [ ] M7-T02: Replace stale constants with bounded baseline-validated predicates.
- [ ] M7-T03: Compare copied-card serial/candidate save/reset/reload routes.
- [ ] M7-T04: Test source-data preservation, failure cleanup and missing evidence.

### M8: Game-thread metrics and topology (depends: M3, M6)

Architecture: [guest time and exceptions](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/GuestState.md#guest-time-callbacks-and-exceptions) · [EFB/copies/VI presentation](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Graphics.md#efb-copies-and-vi-presentation).

- [ ] M8-T01: Add bounded game-update/job timing and overflow detection.
- [ ] M8-T02: Discover real TIDs, topology, affinities and task counters.
- [ ] M8-T03: Calculate frame percentiles, hitches, histograms and join wait.
- [ ] M8-T04: Test units, timeline math, capability gaps and telemetry overhead.

### M9: Multicore load and soak orchestration (depends: M7, M8)

Architecture: [runtime entities](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Runtime.md#runtime-entities) · [graphics synchronization](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Graphics.md#synchronization-and-completion).

- [ ] M9-T01: Add deterministic pressure helper with scoped cleanup/placement.
- [ ] M9-T02: Run interleaved renderer/worker/core/SMT pressure matrix.
- [ ] M9-T03: Run paired 30-minute rendered soaks and save/reload.
- [ ] M9-T04: Test pressure validation, interruption, coverage and regression flags.

### M10: Steam Deck qualification and handoff (depends: M4, M9)

Architecture: [runtime lifecycle](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Runtime.md#runtime-lifecycle) · [audio/DSP/ARAM](https://github.com/chrissotraidis/bluewake/blob/4a68ecae4725eb1ecea2d5d02f990e70c315237d/docs/architecture/Services.md#audio-dsp-and-aram).

- [ ] M10-T01: Run source-only/private oracle lanes with binary provenance.
- [ ] M10-T02: Complete Deck repeatability, rendered/save/load/soak checks.
- [ ] M10-T03: Run optional 5800X3D no-pressure comparison.
- [ ] M10-T04: Record outcomes/limits; retain private evidence locally.

## Routing and decisions

PRD phases map to implementation: baseline M0; fast M1–M2; lifecycle/oracle M3–M4; gameplay M5–M7; Deck M8–M10.

Confirmed: existing context, opt-in diagnostics, ordinary documents, finalization. Technical decisions and rationale are in TECH_PLAN. Task IDs/completion state remain unchanged.

## Evidence

No execution results.

For completed tasks, record commit, command, machine/toolchain, fixture digest or synthetic status, result and local evidence path. Required skips/inconclusive results leave qualification incomplete.

Follow-ups stay in the discovering milestone. Update dependencies here and in TECH_PLAN together. Preserve task IDs and recorded completion state.
