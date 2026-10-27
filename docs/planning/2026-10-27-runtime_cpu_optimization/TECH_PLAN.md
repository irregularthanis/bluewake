# TECH_PLAN — Steam Deck runtime CPU optimization

Status: Planning only

Control source: upstream [`v0.9.0`](https://github.com/chrissotraidis/bluewake/releases/tag/v0.9.0) at [`211abfd`](https://github.com/chrissotraidis/bluewake/commit/211abfdecf13beb5b9f2120459a1a3cde50dd84e). Measurement tooling: [`d1bb41b`](https://github.com/irregularthanis/bluewake/commit/d1bb41b).

[Product brief](PRD.md) · [Tracker](PROGRESS.md)

## Inspected facts

- BlueWake's game thread runs translated DOL/REL code, host edges, guest-state access, and service delivery serially; see the [game-thread execution model](../../architecture/GameThread.md#high-level-execution).
- The graphics path moves GX writes from that thread into frontend/GX conversion and platform rendering; see the [GX command path](../../architecture/Graphics.md#gx-command-path).
- The rendered worst-angle capture attributes 64.6% of game-thread samples to translated code, 13.4% to guest state/dispatch, 9.1% to host coordination, and 6.3% to native replacements. Whole-process GX/Aurora is 15.3%.
- A private 120-second, 99 Hz headless diagnostic attributed 7.23% of process cycles to `func_802456E0`. Generated-source mapping assigns about 1.55% process-wide to `GroundCross`, `GroundCrossRp`, and `GroundCrossGrpRp`, versus 3.37% to shared generated helpers. Optimized shared tails make the helper-to-caller split approximate.
- [PR #436](https://github.com/chrissotraidis/bluewake/pull/436) already tested a guarded `GroundCrossGrpRp` path: 28.1% acceptance, 226.1 ns native versus 179.3 ns translated for accepted early returns, and fixed-view results within noise. That partial hook is closed and is not the next candidate.
- [`direct_calls.py`](../../../scripts/windows/direct_calls.py) already rewrites eligible constant and indirect guest calls. [`bw_direct_call_ready`](../../../cmake/composite/direct_calls.h) checks exception/budget state, interrupt state, depth and host observation at entry and return; the plan must measure those existing checks before proposing a change.
- Compatibility services account for 0.1% of whole-process samples and are not a current candidate.
- [`profile_deck.sh`](../../../scripts/linux/profile_deck.sh), [`bench_tour.py`](../../../scripts/bench_tour.py), session timing, and guest checkpoints already provide the measurement layers described in the [performance workflow](../../performance/Overview.md#performance-workflow).

## M0 control receipt

| Field | Frozen control |
| --- | --- |
| Application source | Upstream tag `v0.9.0`, commit `211abfdecf13beb5b9f2120459a1a3cde50dd84e`, clean checkout |
| RecompCore | `1446450c79046bd34e43abadc27522eeab768a6e` from the release lock |
| DolRecomp | `b8b534591cba8ca7cd43943a655ee6e2591cf5de` from the release lock |
| Toolchain / target | Ubuntu Clang 18.1.3, `x86-64-v3`, reproducible Linux container |
| Production options | Prepared/fixed CPU/fixed MEM1, inline FP/GPR, gather pipe, direct calls, native J3D/vector/math/skin/game-math, lean blocks, local PGO |
| AppImage | Private `BlueWake-main-090-x86_64.AppImage`; SHA-256 `476a335f0cf6ec35a4070850de5a17e5c8d45441a60638603fc3e6e7e8d4be48` |
| Module | SHA-256 `7b094be4e42b62c3d59db293ec364f71bcbca299e23d81859a258d992b519398` |
| Training profile | SHA-256 `a160ddf641108d1f56c994f6739ec83df0cff44d6bb20da6a1d6f9a0ebd77535` |

The retained private artifact is
`build/artifacts/main-090/211abfdecf13/BuilderProvenance.json` in the local
workspace; it is intentionally not a repository link. M0 A/A
uses this exact AppImage for every round; candidate profiling tools must attach
to it without rebuilding or changing its runtime source.

The completed headless A/A tour used two aliases of that identical AppImage,
ten measured runs per alias, ABBA interleaving, five scenes and 31 checkpoints.
Every checkpoint matched. Scene deltas ranged from -0.07% to +0.17%, while the
per-run geometric-mean median changed by -0.00%. For this workload, changes
below 0.2% are therefore noise unless a later source-matched A/A shows a wider
band. Rendered stable/slow/worst noise was measured separately below.

Rendered Game Mode measurements used one continuous `0.9.0` process, stationary
camera views, and three 30-second rounds per view. Each round records session
rate/busy samples plus `perf stat` task-clock, cycles, instructions, branches
and cache events:

| View | Retraces/s across rounds | Busy | IPC | Observed rate spread |
| --- | --- | --- | --- | ---: |
| Stable | 59.88, 59.92, 59.95 | 87.2–89.1% | 1.796–1.830 | 0.12% |
| Slow | 55.00, 55.40, 55.78 | 97.0–97.1% | 1.833–1.873 | 1.42% |
| Worst | 49.01, 49.25, 49.70 | 96.9–97.3% | 1.955–1.964 | 1.41% |

Candidate fixed-view results must exceed the corresponding view's observed
spread consistently; a single faster round is insufficient. The headless tour
and checkpoint gate remain required because manual camera placement alone is
not deterministic correctness evidence.

## Investigation flow

```mermaid
flowchart LR
    Baseline["Freeze source, build,<br/>scene and A/A noise"]
    D["D1<br/>direct-call guards"]
    F["D2<br/>floating-point helpers"]
    G["D3<br/>gather-pipe path"]
    Gate["Candidate gate<br/>cost, safety, expected gain"]
    Build["Isolated candidate build"]
    Fixed["Stable / slow / worst A/B"]
    Tour["Full scenes and<br/>player-facing checks"]
    Decision["Retain or reject"]

    Baseline --> D --> Gate
    Baseline --> F --> Gate
    Baseline --> G --> Gate
    Gate --> Build --> Fixed
    Fixed -->|positive| Tour --> Decision
    Fixed -->|neutral/regression| Decision
```

## Workstreams

| Order | Existing surface to inspect | Practical investigation | Candidate gate |
| --- | --- | --- | --- |
| D1 | [`bw_direct_call_ready`](../../../cmake/composite/direct_calls.h), generated sites in [`direct_calls.py`](../../../scripts/windows/direct_calls.py), and `host_direct_can_skip_with` | Count entry/return checks; attribute each predicate; classify constant watched addresses and state changes between paired checks | Remove, combine, or specialize a check only when its invalidation contract is preserved |
| D2 | [`inline_fp.h`](../../../cmake/composite/inline_fp.h) and generated call sites | Attribute samples by FP operation and inspect rounding, conversion and CPU-state synchronization around hot blocks | Eliminate only repeated state work; preserve PowerPC results and exceptions |
| D3 | [`gather_pipe.h`](../../../cmake/composite/gather_pipe.h), GXRuntime submission, and [GX command path](../../architecture/Graphics.md#gx-command-path) | Separate packing, bounds/alias checks, parsing, queueing and waits by thread/frame | Change the dominant component only if it improves game-thread progress |
| Fallback | `GroundCross` → `GroundCrossRp` → `GroundCrossGrpRp` | Price a complete-region replacement against the measured 1.55% ceiling and [PR #436](https://github.com/chrissotraidis/bluewake/pull/436) | Proceed only with broader coverage and a predicted gain beyond noise |

D1 and D2 share generated-module sources, so their instrumentation can run in
parallel but candidate edits must remain separate. D3 is independently
measurable; RecompCore runtime changes require a companion PR before BlueWake
pins them.

## First candidate: paired direct-call guards

Eligible calls already bypass the chassis, but generated sites commonly run
`bw_direct_call_ready` before entering the callee and again after it returns:

```c
/* Existing generated shape, simplified. */
if (bw_direct_call_ready(ctx, target)) {
    bw_chunk_fns[index](ctx);
    if (ctx->pc == return_pc && bw_direct_call_ready(ctx, return_pc))
        goto translated_return;
}
```

The investigation will measure the two checks separately and record which
inputs can change during the callee: exception, cycle budget/downcount,
interrupt-source state, direct depth, and host-observed addresses. A proposed
specialized path may reuse only facts proven unchanged; otherwise the second
check remains. Constant-target classification must come from the builder's
watch list, while mutable host flags remain runtime inputs.

The M1 diagnostic is implemented in this PR. Generated direct calls use
[`bw_direct_call_ready_measured`](../../../cmake/composite/direct_calls.h) for
entry and return checks and record whether the callee reached its expected
return address. `BLUEWAKE_DIRECT_CALL_MEASURE=1` enables counters for unavailable
state, depth, exception, budget, host activity, fast/slow rejection and success.
The normal path continues to call the original predicate and emits no report.

### Initial M1 measurement

One Game Mode session covered startup plus stable, slow and worst Outset views.
It recorded 2,239,201,382 entry checks: 99.40% passed, 0.43% were rejected by
the fast address filter, 0.15% by the cycle budget and 0.02% by host activity.
Of the accepted entries, 79.23% returned to the expected continuation and
20.77% diverted elsewhere. The 1,749,593,903 reached return checks passed
99.79%; budget and fast-filter rejection accounted for the remaining 0.21%.

These cumulative counts identify where the path exits, but do not yet measure
exclusive guard cost or calls per rendered frame. M1-T01 therefore remains
open pending source-matched cost attribution and normalized runs.

## Candidate contract

Every proposal adds a short record before implementation:

```text
source/build + scene → owning thread → calls/frame → exclusive samples/time
                     → safety invariant → expected avoided work → acceptance metric
```

For a translated routine, source mapping must prove the original function range contains the sampled instruction; proximity to a symbol is insufficient. A native replacement must preserve guest registers, memory, exceptions, timing fields required by callers, and fallback behavior. For dispatch/state work, the plan must identify what invalidates any cached decision. For GX work, cached or reused data must retain ordering, mutation, interpolation, and lifecycle contracts.

## Verification

| Layer | Method | Required evidence | Stop condition |
| --- | --- | --- | --- |
| Baseline | Three same-build fixed-view samples | Noise interval, source/build receipt, activation | Unstable scene or mismatched build |
| Attribution | `perf`, counters, source/range inspection | Thread, calls, exclusive share, exact code path | Unresolved ownership |
| Focused correctness | Existing host/GX/native tests plus candidate-specific regression | Candidate path activated; fallback and mutation covered | Missing activation or mismatch |
| Fixed-view A/B | Interleaved control/candidate at stable, slow, worst angles | CPU/frame-time/game-speed delta exceeds noise | Neutral or regression stops full tour |
| Full qualification | Established headless/rendered scenes, checkpoints, player traversal | Repeatable benefit and no observable regression | Incomplete scene or checkpoint evidence is inconclusive |

The profiler ranks work; it does not validate an optimization. A lower worker percentage alone is insufficient if game speed and frame progress do not improve.

## Implementation order

| Milestone | Depends | Can run with | Deliverable / gate |
| --- | --- | --- | --- |
| M0 | — | — | Freeze source-matched baseline, A/A noise, scenes, and candidate-record format |
| M1 | M0 | M2 | Direct-call entry/return cost split, invalidation contract, and candidate or no-go |
| M2 | M0 | M1 | FP and gather-pipe operation attribution, each ending in a candidate or no-go |
| M3 | M1, M2 | — | Rank shared-cost candidates; price the complete GroundCross fallback only if needed |
| M4 | M3 | — | Implement the strongest isolated candidate with focused tests |
| M5 | M4 | — | Fixed-view gate, then full qualification only if positive |

Critical path: M0 → parallel M1/M2 → M3 → M4 → M5. Candidate implementation is serialized so A/B results have one cause.

## Decisions and gaps

- Start with the existing direct-call guards; do not propose adding direct-call rewriting because it is already present.
- `func_802456E0` decomposition confirms the prior GroundCross target was reasonable but does not reverse its negative Deck result.
- FP and gather-pipe percentages are source-attribution signals, not exclusive operation timings; M2 must split them before selection.
- The current profile has 17.7% unresolved samples. Known stripped GX leaves were classified, but unresolved entries must not be assigned speculatively.
- No candidate is accepted from this profile alone.

## References

- [Steam Deck tracker #215](https://github.com/chrissotraidis/bluewake/issues/215)
- [Runtime interaction boundaries](../../architecture/Runtime.md#interaction-boundaries)
- [Performance domains](../../performance/Overview.md#performance-domains)
- [Profiling guide](../../PROFILING.md)
