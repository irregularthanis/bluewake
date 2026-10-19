# PROGRESS — Shorten the Steam Deck game update

Status: Planned; implementation and hardware validation not started.

[Requirements](PRD.md) · [Technical plan](TECH_PLAN.md)

## Milestones

### M0: Freeze baseline and contracts

Architecture: [host execution](https://github.com/chrissotraidis/bluewake/blob/095f7014cb2db2fb5640641133040593a7775a78/docs/architecture/Host.md#main-loop-execution), [measurement](https://github.com/chrissotraidis/bluewake/blob/095f7014cb2db2fb5640641133040593a7775a78/docs/performance/Overview.md#performance-workflow).

- [ ] M0-T01: Resolve merged prerequisite revision; recheck open PRs/branches and foundation runner interfaces. (FR-01, FR-04)
- [ ] M0-T02: Collect Deck A/A baseline, profiles, wait time and actual kernel activation/batch distributions. (FR-01, FR-05)
- [ ] M0-T03: Freeze scenes, thresholds, [run matrix](TECH_PLAN.md#run-matrix--proposed-freeze-at-m0), calculation rules and report schema; rank candidates. (FR-01, FR-02, FR-03, FR-05)

### M1: Independent calculation stream (depends: M0)

Parallel with M2/M3; owns `native_math.c`/`native_skin.c` and any new value-only helper. Uses M0 contract; integrates at M4. [Ownership](https://github.com/chrissotraidis/bluewake/blob/095f7014cb2db2fb5640641133040593a7775a78/docs/architecture/GuestState.md#ownership-and-address-model).

- [ ] M1-T01: Select measured kernel and estimate upper-bound benefit; record go/no-go. (FR-01, FR-02)
- [ ] M1-T02: Establish stable inputs and disjoint outputs; separate prepare/calculate/apply, preserving caller-owned effects, arithmetic and serial fallback. (FR-02, FR-04)
- [ ] M1-T03: Measure inclusive job cost and worker participation; retain only profitable batch sizes or record no-go. (FR-02, FR-05)

### M2: Serial overhead stream (depends: M0)

Parallel with M1/M3; owns selected dispatch/gather changes; integrates at M4. [Deadlines](https://github.com/chrissotraidis/bluewake/blob/095f7014cb2db2fb5640641133040593a7775a78/docs/architecture/Services.md#guest-time-and-deadlines).

- [ ] M2-T01: Identify remaining redundant crossings/checks; distinguish existing batching from new opportunity. (FR-01, FR-03)
- [ ] M2-T02: Implement one bounded change preserving deadlines and observer ordering, or record measured no-go. (FR-03, FR-04)
- [ ] M2-T03: Compare isolated candidate; document larger native/caching follow-ups only where evidence supports them. (FR-03, FR-05)

### M3: Correctness and evidence stream (depends: M0)

Parallel test development with M1/M2; owns test fixtures and qualification scripts. Final execution requires their candidate revisions. [Lifecycle](https://github.com/chrissotraidis/bluewake/blob/095f7014cb2db2fb5640641133040593a7775a78/docs/architecture/Services.md#lifecycle-and-observable-state).

- [ ] M3-T01: Test calculation rules: stable inputs, disjoint outputs, complete publication, arithmetic order, budgets and unchanged declines. (FR-02, FR-04)
- [ ] M3-T02: Verify positive worker activation, failure/unload behavior and required sanitizer/Windows lanes. (FR-02, FR-04)
- [ ] M3-T03: Report actual updates, hashes and pressure stages; distinguish fail/skipped/incomplete/inconclusive/retain outcomes. (FR-01, FR-05)

### M4: Integrate and qualify (depends: M1, M2, M3)

[Graphics barriers](https://github.com/chrissotraidis/bluewake/blob/095f7014cb2db2fb5640641133040593a7775a78/docs/architecture/Graphics.md#synchronization-and-completion); one benchmark per Deck at a time.

- [ ] M4-T01: Integrate retained changes; run complete oracle/source tests against final hashes. (FR-02, FR-03, FR-04)
- [ ] M4-T02: Execute frozen A/A and A/B matrix in separate unpaced/rendered modes; run serial/1/2/3-worker pressure checks and ≥30-minute rendered soak. (FR-05)
- [ ] M4-T03: Complete gameplay/audio/cutscene/save checks; record impacts, goal attainment and enablement decision. (FR-04, FR-05)

## Impact evidence

| ID | Actual | Outcome | Evidence |
|---|---|---|---|
| IMP-01 | Not measured | Planned | None |
| IMP-02 | Not measured | Planned | None |
| IMP-03 | Not measured | Planned | None |
| IMP-04 | Not tested | Planned | None |
| IMP-05 | Not measured | Planned | None |

## Evidence ledger

No implementation task is complete. Source inspection and planning validation do not establish game correctness or speed. Add commit, command, environment/input hashes, raw report path and result when each task runs. Keep private game inputs and copied saves local.
