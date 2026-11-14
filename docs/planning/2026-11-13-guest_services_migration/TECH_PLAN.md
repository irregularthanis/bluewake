# TECH_PLAN — Guest services migration

Status: Planning only (programme)
Source: fork PR #9's research and tooling; #593 (the draw side's own plan); #542 (collision harness); #541 (native skinning); #561 (the audio thread)
[PRD](PRD.md) · [Tracker](PROGRESS.md)

## What a migration is

A guest service is a subsystem the game calls through a narrow set of entry points and whose effects on guest memory are bounded: the J3D draw side, background collision, the audio thread, particles. Migrating one means the host answers those entry points natively, writes back exactly the guest memory the translation would have written (or a certified subset nothing else reads), charges the cycles the plan's exactness class requires, and runs its own work on as many cores as it likes. The translation stays as the fallback and the oracle, selected per service by an opt-in switch, as the native routines are today ([NativeRoutines](../../architecture/NativeRoutines.md)).

```mermaid
flowchart LR
    GT["Game thread<br/>(translated game logic)"] -->|"entry point<br/>(hook)"| H{"Native service<br/>enabled and eligible?"}
    H -->|"no"| T["Translated subsystem<br/>(serial, the oracle)"]
    H -->|"yes"| N["Host service"]
    N --> J1["Job on worker 1"]
    N --> J2["Job on worker k"]
    J1 --> W["Guest-visible writes,<br/>in the translation's order;<br/>cycles charged per class"]
    J2 --> W
    T --> R["Resume game thread"]
    W --> R
```

## Common infrastructure (exists on #9 and in the tree)

| Piece | Use here |
| --- | --- |
| `BLUEWAKE_SHADOW_TRACE` (B1 trace build) and `scripts/shadow_limit_study.py` | A service's read and write sets, cycles and flags per region, at any marked entry/return pair: the contract a migration must honour, measured, not guessed |
| The shadow module (built without the fixed CPU and MEM1, exact, 2–5 % slower) | For any job that must still run *translated* code off the game thread (a certified translated region as an async job) |
| `native_entries.py` hooks with body hashes, `native_leaf_test.c`, the differential oracles | Routing an entry to the host only where the translation matches what was certified; the test shape |
| The verify-build idea from #9 | Run the translation beside the service and compare outputs, in CI and on the Deck |
| `render_bench`, Game Mode runs, the per-thread sampler, the testing strategy in #9 | Acceptance: ≥ 6 interleaved Deck launches, checkpoints or digests, power and the per-update tail |

## Per service

### 1. The J3D draw side ([#593](https://github.com/chrissotraidis/bluewake/pull/593) phase 2 owns the design)

- **Boundary:** `mDoExt_modelUpdateDL` / `J3DModel::calc`, `entry`, `viewCalc`, the material and shape `load`/`draw`, `J3DDrawBuffer` entry and draw, the room draws in the scene's draw; the GX stream they produce.
- **Contract to measure:** per model, the reads (model data, animation state, base matrix) and writes (`mpNodeMtx`, draw matrices, packet state, `j3dSys`, draw-buffer links), from a trace with 'D' markers and markers inside `dScnPly_Draw`.
- **Measured at actor-draw granularity (2026-11-14, tracker M1-T01):** the outputs (53–55 % of the words an actor's draw writes; ≈ 70 % for PLAYER and BRIDGE) are consumed only by the painter, which runs first in the next `fpcM_Management`, so the join is there and the jobs' window is the rest of the draw loop. The chain between consecutive draws is the draw-side scratch (`j3dSys`, `J3DSys::mCurrentMtx`, `mCurrentS`, `mParentS`, `mDoLib_clipper::mClipper`, `mDoMtx_stack_c::now`, `sGDLObj`/`__GDCurrentDL`, `sNoUseDrawMtxPtr`/`sNoUseNrmMtxPtr`, `sInterruptFlag`) and heap shared by instances of one actor type: job-private copies, with the draw-buffer order serial. The cross-pass set the next execute reads: `j3dSys`, `dStage_roomControl_c::mStatus`, `l_fopDwTg_id`, `g_env_light`, `J3DSys::sTexCoordScaleTable`, `g_dComIfG_gameInfo`, the dMap fields, and the model matrices attachments read. Per-model sets (M1-T01b, PR #12's markers; tracker): 380 model calls a frame over 131 models at the busiest view, `calc` in the execute loop as heavy as all the draw-side calls together; 44–47 % of their words are the painter's input, 47–54 % the model's own next-frame state, the rest the named scratch and the heap shared by instances of one actor type; a third of the draw-side calls have no same-frame reader of their outputs, the execute-side calcs have an immediate consumer in 41 % of cases; actor code runs inside `calc` (the joint callbacks).
- **Host shape:** per-model jobs (calc, skinning, material setup, the model's GX bytes into a private buffer) over the pool; the draw-buffer order and the final GX assembly on the game thread; the gather pipe fed in the translation's order.
- **Decided (2026-11-14, the owner): cycle-exact; shape (a), translated model code in shadow jobs for `calc`.** The two shapes as they were weighed: (a) *translated* model code run off the game thread in the shadow module, the J3D scratch privatized per job, the cycles charged exactly, joined at the first reader; (b) a *native* `calc`/`entry` as per-model jobs, faster per unit but the joint callbacks are actor code inside `calc` and the cycle charge needs a model.
- **Measured at job granularity the same day (tracker M1-T02, `scripts/j3d_wrapper_jobs.py`): shape (a) does not pay.** The job is one `mDoExt_model*` wrapper call (calc → calcMaterial → diff → entry → viewCalc; `calcMaterial` reads calc's matrices at once) or one direct `J3DModel::calc`. The windows to the first reader allow 35–45 % of the execute-side calls' cycles to overlap (the actors copy a joint matrix ≈ 30 cycles after `mDoExt_McaMorf::calc` returns in a third of the jobs; the next model call anywhere is 42 k cycles away at the median against 22 k-cycle jobs) and 34–37 % of the draw side's (4.7 k-cycle jobs whose outputs the actor's own draw code or the next actor's `entry` reads within ≈ 150 cycles). In the shipped build the calc side of J3D is 7.7 % of the busy samples at the busiest view (the painter side 10.5 %), so the gross gain is ≈ 3–4 % of the frame against ≈ 170 dispatch–validate–commit cycles a frame (≈ 2–3 % of a 33 ms frame): net ≈ 0–1 %. The DSP steps (every 10.7 k cycles) must be deferred under any overlap design; respected, they cut the figures to 10–22 %.
- **The painter as the job (M1-T02b, measured 2026-11-14; tracker):** `cAPIGph_Painter` → `mDoGph_Painter` runs first in `fpcM_Management`. Its prologue (the retrace wait in `beginRender`, the clear, the 2D copy, `imageDrawShadow`, the viewport, `setCurrentWindow/View/Viewport`, `GXSetProjection`, `setViewMtx`, `dKy_setLight`) stays on the game thread; **the job is the draw lists** (`drawOpaListSky` … `drawXluList`, the particles, the alpha, light and spot models, the filters and the 2D), **1.71 / 1.33 / 1.76 M guest cycles a frame at the busiest view / play / Outset, ≈ 10–12 % of the game thread's host time**; its window the handlers and the execute loop. Measured: it must run on a **snapshot** (the execute loop rewrites 0.8–1.5 k of the ≈ 13.5 k lines it read, from 219 cycles after its serial end: actor objects and model matrices read through the dDlst callbacks); the loop writes only 17–64 of its ≈ 4 k written words; **what the loop reads of its writes** is the matrix stack pointer (balanced), the `j3dSys` scratch fields (set before use by every model call) and its `mDrawMode`/`mMaterialMode` (the last list's), the view matrix (the prologue's value, two words touched), the no-use matrix pointers (value-preserving swaps), the light caches (2–5 regions a frame), the game-info current window and view (`dAttention_c::Run`, 12 k cycles in), a packet flag of one actor; and the audio thread's and scheduler's state when a DSP interrupt lands inside the job (1.6–2.9 a frame). The draw loop, after the join, reads the J3D shape statics and the light caches in bulk.
- **Mechanism (the engine of #9 specialized to one region):** a worker runs the job's translated code from the shadow module on a snapshot (copy-before-write pages taken by the game thread's store path on its first write to a page the job may read, ≈ 100–150 pages a frame, with a seqlock-style re-check on the worker's loads; or the game thread shadowed), writes the gather pipe itself (the execute loop writes no GX; a hardware access by the game thread inside the window aborts the batch), performs the painter's hardware register writes in its stream, reads the time base as its own cycle count. The DSP steps inside the window are deferred to the join; the window's interrupts are delivered on the game thread at the dispatch point, in order, with the time base presented as their due time (exact if the painter and the handlers touch disjoint state: to certify with a handler region in the trace); interrupts due after the painter are placed in the execute loop once its cycle count is known, with a checkpoint at the uncertainty window. The words the loop reads are handled by a **certified list**: nothing for the balanced stack, the value-preserving swaps and the scratch fields; **pre-commit at dispatch** of the known final values (the view matrix, the modes, the game-info view, the packet flags' clear) with the job's own writes to them dropped; a stall at the join for anything else on the job's written pages. A write by the job outside the certified set, or a read of a snapshot page the loop rewrote before the copy, is a fatal report in verify builds. The basis is certification plus runtime containment (the native routines' class), not a universal validator: the trio records that as the exactness argument.
- **Cost model:** ≈ 10–12 % of the frame gross at the busiest view on one worker at ≈ 10 % duty (the Deck's power curve costs ≈ 0.5–1 % there); the snapshot copies ≈ 0.3 %, the store-path page check ≈ 1–2 % (always on in the live module, or a module variant that only a configured worker count selects), the deferred DSP burst and the stalls on the certified list to measure. **≈ 6–8 % net at the busiest view**; less at the play state (the job is 1.33 M there). Weeks of engine work; the owner's call.
- **Exactness:** **cycle-exact (decided 2026-11-14)**: identical guest checkpoints against the serial build; the GX stream digest and pictures besides.
- **Expected:** per-model calc jobs ≈ 0–1 % net (measured ceiling); the painter job ≈ 10–12 % gross, ≈ 6–8 % net at the busiest view (measured contract, estimated costs), one worker at ≈ 10 % duty.

### 2. Background collision

- **Boundary:** `dBgS` queries (`GroundCross`, `WallCorrect`, roof, line checks) and the world's per-frame update; the `cBgW` block structures in REL alias storage (#501).
- **Contract:** the results of each query (exact), the world update's writes; #542's harness and census.
- **Assets (checked 2026-11-14):** the differential harness `tests/native_bg_test.c` with `cmake/composite/native_bg.c` is on main (random registers, flags, cycle state and collision data, 60,000 cases a function, an edge service that ends the run at the return); the module census `bg_census_module.c` and the exact ground-walk prototype `native_ground_walk.c` (`f102f07`, 400,000 cases identical, no gain as a native walk) live on #542's branch and history. The hit collision (`cCcS`/`dCcS`, the scene's `dCcS::Move`) is a different system: 2.9 % of the shipped build's busy samples, its outputs read by the actors' execute (a fifth) — not this item.
- **Host shape:** a host spatial index built from the BG data at room load, answering queries serially (each actor needs its answer at once) and updating moving BG in parallel per object.
- **Exactness:** exact results; the cycles as the translation charges (#542's model) or "plays the same".
- **Expected:** ≈ 3–5 % here, more in collision-heavy rooms.

### 3. The audio thread

- **Boundary:** `TAudioThread::audioproc`'s work (`Kernel::updateDac`, `TDSP_DACBuffer::updateDSP`), woken by the AI DMA and DSP interrupts (#561; #9's audio notes).
- **Contract:** the JAI command queue in, DSP mails and guest audio state out; measured with markers at the wake points.
- **Host shape:** its own host thread, consuming a per-frame snapshot of the queue, one frame of latency at most; deterministic by construction.
- **Exactness:** bit-exact DSP command output; the `JASChannel` natives of round 7 as building blocks.
- **Expected:** ≈ 5 %.

### 4. Particles

- **Boundary:** `dPa_control_c::calc` (emitters, particles) and the JPA draw.
- **Contract:** emitter inputs written by actors, particle state, the draw's reads; JPA's own RNG.
- **Host shape:** per-emitter jobs after the execute pass, joined before the draw pass.
- **Exactness:** bit-exact simulation.
- **Measured contract (2026-11-14, tracker M0-T04):** `calc3D` writes ≈ 3.75 k words a frame, 95–98 % of them read only by `calc3D` itself next frame (2 % by `calc2D`); the shipped-build share is 3.0 % at the busiest view and 14.5 % at the shipwreck. The deferral hazards (what a job after the execute pass must snapshot) are in the tracker's evidence row.
- **Expected:** ≈ 2–3 % (14 % at the shipwreck).

### 5 and 6. Host overheads; the Z-targeting scan

Serial work on the existing paths (the direct-call check, the dispatch loop, the GX writes; the remainder of `dAttention_c::Run` beside the native actor search). Weeks each, a percent or two each, diminishing.

## Order and dependencies

1. Finish #9's data gathering (the draw pass and the scene's sub-phases traced), which gives services 1, 4 and 6 their measured shares.
2. The draw side (#593 phase 2), designed parallel from the start.
3. Collision and the audio thread in either order; particles alongside the draw side if its measured share justifies it.

## Validation

Per service: the differential oracle (translation beside the host service) in CI on the headless routes; on the Deck, #503's rule with the testing strategy of #9 (checkpoints or digests every retrace, the per-update tail, per-thread CPU time, power and energy a frame, a soak).
