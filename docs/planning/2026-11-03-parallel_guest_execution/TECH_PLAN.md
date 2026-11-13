# TECH_PLAN — Parallel guest execution

Status: Design (2026-11-13); the 2026-11-03/04 sections below stay as the record
Source: BlueWake `main` after #554; RecompCore DSP HLE; tww
[PRD](PRD.md) · [Tracker](PROGRESS.md)

## Design (2026-11-13): shadow batches

### Vocabulary

- **Live state**: the guest CPU, MEM1, the REL alias storage and the host's device state, as the serial build keeps them.
- **Region**: one call the serial program makes from a takeover point: an actor's execute or draw, `pMethod(pNode)` inside `cNdIt_Method`.
- **Batch**: regions R0…Rk that the serial program runs back to back from logical time T.
- **Shadow run**: a region executed by the shadow module on a private CPU state, reading live memory and writing only a private copy, counting its cycles.
- **Join**: the game thread has finished its own region and waits for the workers. **Commit**: private writes applied to live state in serial order. **Fallback**: the rest of the batch run through the live module, the serial path, from the current logical point.

### Invariants

1. During a batch nothing writes live guest memory or device state: every participant is a shadow, and the host's deadline services inside the span are deferred to the join.
2. A shadow reads live memory and its own writes, never another shadow's.
3. Commit order is serial order; the cycles charged are the sum of the regions' counted cycles; the host then services the deadlines that fell inside the span, in cycle order, before the guest resumes.
4. Whatever can't be shown serial-equivalent is not committed: the valid prefix commits, the rest runs live. The live path is the serial build's, untouched.

### Serial-equivalence conditions, checked at the join

| Condition | Rule | Why it is sufficient |
| --- | --- | --- |
| C1 window | Σ cycles(R0…Rk) ≤ D(T), the distance to the next guest-visible interrupt (VI event clock, audio DMA, decrementer, pending or dirty sources), computed as [`host_cycle_deadline_distance`](../../../runtime/host/src/main.c) does without its DSP-cadence term | No interrupt would have landed inside the batch in the serial run; DSP interrupts need a guest mailbox write, which aborts a shadow (C4) |
| C2 RAW | For i < j: reads(Rj) ∩ writes(Ri) = ∅, words; cache lines as the first filter | Rj read pre-batch values; serial Rj would have seen Ri's write |
| C3 host services | DSP steps whose deadlines fall in [T, T+Σ) read nothing in writes(R0…Rk); the engine runs them after the commit, in order | The HLE reads guest memory (voice blocks, DAC buffers) at its step; those reads must equal the serial ones |
| C4 replayable | No region aborted: no MMIO (except FIFO stores in the draw pass, logged), no timer read, no exception, no `mtmsr`, no call to a watched address, no direct-call depth overflow, no alias write beyond the side buffer | Everything else the shadow can't keep private or can't time |
| C5 links | The iterator's `pNext->next` words, read early by the takeover, are not in the writes of the regions that serially precede their read | `cNdIt_Method` reads the next link after each method; the takeover reads it before |

WAW is settled by commit order (the last writer wins, as in serial); WAR is settled because shadows read pre-batch values, as the earlier serial reader did. The guest stack is ordinary memory under these rules: all regions write the same range, an uninitialized read of a leftover is a real dependence and falls back, and the ordered commit leaves the serial stack image.

### Privatization rules (each exact)

| Rule | Words | Commit |
| --- | --- | --- |
| P1 reductions | A certified list (`J3DDrawBuffer::entryNum`, allocator counters found by the census) | If every access to the word in the batch is a read followed by a write of read + δ, the word leaves C2 and the engine commits Σδ |
| P2 the RNG | `cM_rnd`'s three words, `cM_rnd2`'s three (tww `c_math.cpp:167`) | Plain, when at most one region of the batch touched them; otherwise the later region fails C2 and falls back. E2 says whether re-seeding a later region from the earlier one's final seed and re-running it on the worker is worth a stronger rule |
| P3 the link words | C5 | Read again after the commit |

### Mechanism

| Part | What |
| --- | --- |
| **Shadow module** | The same composite built with `fixed_cpu=0` and `fixed_mem1=0` (so `ctx` is the parameter and memory is `cpu->ram`: [`global_guest_cpu.py`](../../../scripts/windows/global_guest_cpu.py) is simply not run), gather pipe off, and a shadow variant of the memory fast path in [`gather_pipe.h`](../../../cmake/composite/gather_pipe.h): loads append their line to a per-CPU read filter, stores append (address, size) to a per-CPU write log; the `_slow` paths keep alias writes in a private side buffer that alias reads consult first; MMIO and timer reads abort; FIFO stores in the draw pass go to a per-region GX log. `bw_direct_depth` thread-local; `bw_host_can_skip` answers quiet, and a watched address aborts. One module copy per worker (`dlmopen`) in v1 |
| **Private memory** | Live MEM1 becomes a `MAP_SHARED` mapping of a memfd (mapped over the live module's `BW_GUEST_MEM1` at [`bw_module_cpu_init`](../../../cmake/composite/module_cpu_contract.h), or the live module runs with `cpu->ram` on it); each shadow CPU's `ram` is a `MAP_PRIVATE` mapping of the same memfd: reads see live pages, writes copy privately. After each batch, `madvise(MADV_DONTNEED)` on the pages the write log names resets the view |
| **Workers** | N persistent threads (2 on the Deck by default), spinning on a dispatch word inside a frame and parked between frames; each owns a shadow CPU, a private mapping and its logs |
| **Engine** | At a takeover point: form the batch (up to the workers available, sized against D(T) with last frame's cost per process type), dispatch, run R0 as a shadow on the game thread, join, check C1–C5 and P1–P3, commit the write logs in order and append the GX logs to the live gather pipe, charge the cycles, service the deferred deadlines, continue. On failure: commit the valid prefix, run the first invalid region live, continue iterating |
| **Takeover** | A native entry at `cNdIt_Method` (tww `c_node_iter.cpp:11`), hooked by the existing native-entry mechanism with its body hash, engaged only when `pMethod` is `fpcLnIt_MethodCall` on `g_fpcLn_Queue`'s execute or draw pass; it is the iterator, so a fallback is just calling the method live. Declines to the translation when `BLUEWAKE_SHADOW_WORKERS` is unset or 0 |
| **Verify build** | `BLUEWAKE_SHADOW_VERIFY=1`: after each commit the engine re-executes the batch's regions live from a saved copy of the touched state and compares memory over the union of write sets, the CPU state, the cycles and the GX bytes; any difference is a fatal report. For CI's headless routes and for the Deck during qualification |
| **Census** | Per batch: regions, cycles, window, outcome (committed, C1…C5), per-region abort reasons, the top conflicting words named through the symbol map; printed at exit like the other censuses. It drives the P1 list |

### Limit study (E2), from the same logs, single-threaded

Trace mode runs every region of the execute and draw passes as a shadow on the game thread, one at a time, committing each at once, and dumps per region: the process type, cycles, read lines, write words, abort reason, and the interrupt and deadline events with their cycles. Offline, a script simulates the engine's choices per frame for a batch policy (workers, maximum cycles) and reports the parallel fraction, the failure causes and the serializing words. Three states (`8-busiest`, `6-play`, `1-outset`), 300 frames each, paced to real time so the interrupt pattern is the real one, on the Deck over SSH.

### Experiments

| Id | Question | Method | Stop if |
| --- | --- | --- | --- |
| E0 | Does occupying two more Deck cores slow the game thread? | `8-busiest`, headless unpaced, A/B/B/A/A/B with two spinning cores; then Game Mode through `gm-launch2.sh` with the same spinners | ≥ 15 % |
| E1 | Shadow overhead | The shadow module in trace mode, no parallelism, same route as live | ≥ 35 % |
| E2 | Available exact parallelism | The limit study | < 10 % at 2 workers |

### Changes (proposed)

| Status | File / symbol | Edit | Milestone |
| --- | --- | --- | --- |
| Proposed | `scripts/windows/build.py`, `cmake/composite/CMakeLists.txt` | A second module target, `gGZLE01_shadow.so`: same composite, no `fixed-cpu`/`fixed-mem1`, `BLUEWAKE_SHADOW=1` | M7 |
| Proposed | `cmake/composite/gather_pipe.h`, `shadow_memory.h` (new) | Under `BLUEWAKE_SHADOW`: read filter, write log, alias side buffer, FIFO log, abort on MMIO and timers | M7 |
| Proposed | `cmake/composite/direct_calls.h` | `bw_direct_depth` thread-local under `BLUEWAKE_SHADOW`; shadow `bw_host_can_skip` | M7 |
| Proposed | `runtime/host/src/shadow_engine.c` (new) | Workers, private mappings, batches, validation, commit, deferred deadlines, census, verify mode | M9 |
| Proposed | `runtime/host/src/main.c` | Load the shadow module copies; memfd-backed MEM1; `BLUEWAKE_SHADOW_WORKERS`, `_VERIFY`, `_TRACE` | M7, M9 |
| Proposed | `scripts/windows/native_entries.py` list, `cmake/composite/native_iter.c` (new) | The `cNdIt_Method` takeover as a certified native entry | M9 |
| Proposed | `scripts/shadow_limit_study.py` (new) | The offline simulation over trace dumps | M8 |
| Proposed | `tests/shadow_engine_test.c` (new) | Synthetic batches: every condition's failure path, commit order, reductions, links | M9 |

### Effort

Week 1: E0, E1, the open questions. Weeks 2–3: E2. Weeks 4–8: engine, takeover, verify build, tests. Weeks 9–10: Deck qualification under #503's rule (≥ 6 interleaved Game Mode launches, every one ahead, identical checkpoints and pictures). About ten weeks to a go/no-go with code; the first stop point is after week 1, the decisive one after week 3.

### Open questions for week 1

| Question | Status |
| --- | --- |
| How often does the execute pass read the timebase? | **Settled from source:** game code reads it in `d_timer.cpp` (the timer display), `d_s_play.cpp`, the exception and memory-card paths, and once per actor *creation* (`fopAc_ac_c` constructor, `f_op_actor.cpp:97`); `JUTGamePad` reads it in the main loop's pad read. Execute and draw regions rarely do; the trace counts the rest |
| Takeover addresses | `cNdIt_Method` 0x80244EB4 (0x90 bytes), `fpcLnIt_MethodCall` 0x80040198, `fpcLnIt_Queue` 0x80040200, `cTrIt_Method` 0x802450D0, `cLsIt_Method` 0x80244BF0, `cM_rnd` 0x802462C8 (tww `symbols.txt`) |
| Module copies | The host loads the module with `dlopen(RTLD_NOW \| RTLD_LOCAL)` (`main.c:7763`), so a second copy loads with `dlmopen(LM_ID_NEWLM)` or from a differently named file without symbol interposition. Load time and resident memory on the Deck: to measure |
| MEM1 on a memfd with the fixed-MEM1 live module | `BW_GUEST_MEM1` is `aligned(4096)` (`guest_cpu.c:29`) and `bw_module_cpu_init` zeroes it, so the host can map a shared memfd over it with `MAP_FIXED` first; the host already remaps the module's code the same way for 2 MB pages (`module_hugepages.h:89`) |
| What share of a REL actor's accesses go through the alias slow path? | To measure in the trace (its side-buffer cost) |

---

## Earlier plan (2026-11-03/04)

## Inspected facts

- **Fixed CPU and RAM.** Generated chunks carry `extern CPUState bw_guest_cpu; #define ctx (&bw_guest_cpu)` and take `CPUState* ctx_param` unused. ABI v4 requires `bluewake_composite_guest_cpu()`, v5 the MEM1 getter ([`module_cpu_contract.h`](../../../cmake/composite/module_cpu_contract.h)). With `BW_GUEST_MEM1`, `BW_RAM_BYTES` is the linked symbol, not `cpu->ram` ([`gather_pipe.h`](../../../cmake/composite/gather_pipe.h)).
- **Globals on the translated path.** `bw_direct_depth`, `bw_direct_enabled`, `bw_chunk_fns`, host flag pointers in [`direct_calls.h`](../../../cmake/composite/direct_calls.h); gather-pipe drains at hardware accesses and chunk returns ([`dispatch_loop.h`](../../../cmake/composite/dispatch_loop.h)); RecompCore `g_mem_write_journal` (post-store callback), `g_ppc_guest_aliases_overlap_mem1`.
- **Worker pool.** One global pool, one batch at a time, joins before return; caller takes the last share; off unless `BLUEWAKE_NATIVE_WORKERS` is set (Linux and Windows hosts default it to 2); serial on Windows ([`native_work_pool.c`](../../../cmake/composite/native_work_pool.c)).
- **Native coverage.** `native_skin.c` (`calcWeightEnvelopeMtx`, `0x802EE67C`), `native_game_math.c` (`key-s`, `transform-simple`, clipper, cM3d), native J3D transform info; all on by default on Linux and Windows, declining back to translation on unsupported inputs.
- **Model calc** (tww `J3DModel.cpp:690`): `j3dSys.setModel`, skin flags, `frameInit`, visibility, deform, two hooks, `calcAnmMtx` → `recursiveCalc` (static `J3DSys::mCurrent*`, joint callbacks In/Out), `calcWeightEnvelopeMtx`, skin deform, `mCalcCallBack`. Outputs `mpNodeMtx`, `mpWeightEnvMtx`, scale-flag arrays; `viewCalc` derives draw matrices.
- **Guest PC sampler.** `BLUEWAKE_PC_SAMPLE=path`, `_FROM`, `_TO` ([`main.c`](../../../runtime/host/src/main.c)); reads `cpu->pc` every 100 µs; overweights short dispatched functions.
- **Tooling gap.** `bench_tour.py` strips `BLUEWAKE_*` from the child environment, so sampler runs need a wrapper app script.

## Changes

| Status | File / symbol | Practical edit | Milestone | Architecture |
| --- | --- | --- | --- | --- |
| Proposed | `scripts/bench_tour.py` | Pass through an allowlist of diagnostic variables (`BLUEWAKE_PC_SAMPLE*`) | M0 | [Testing](../../architecture/Testing.md) |
| Proposed | `scripts/pc_sample_attribute.py` | Attribute `BLUEWAKE_PC_SAMPLE` output to tww functions and subsystems | M0 | — |
| Modify | `runtime/host/src/main.c`: guest PC sampler | Also count samples per guest thread (the word at `0x800000E4`, as `OSGetCurrentThread` loads it) into `PATH.threads`; `BLUEWAKE_PC_SAMPLE_THREAD=hex` keeps one thread's pcs | M6 | [Host](../../architecture/Host.md) |
| Proposed | `cmake/composite/native_skin.c`, `native_game_math.c` | Count declines by reason (a reason code per guard) | M1 | [Native routines](../../architecture/NativeRoutines.md) |
| Proposed | same, plus generators and oracle tests | Widen the certified domain for the dominant decline reasons | M2 | [Native routines](../../architecture/NativeRoutines.md) |
| Proposed | host diagnostic (opt-in) | Trace reads of one model's `mpNodeMtx`/draw-matrix range between `mDoExt_modelUpdateDL` and the draw-list flush | M3 | [Guest state](../../architecture/GuestState.md) |
| Proposed | new async job path (separate from the pool) | Submit, join at flush, ordered publication; opt-in flag | M4–M5 | [Game thread](../../architecture/GameThread.md) |

## Contracts

**Eligibility** (decided before submission; anything else runs serially as today): no joint callback on any node, no `mCalcCallBack`, no `mpDeformData`/`mpSkinDeform`, no hooks at `0xc4`/`0xc8`, no visibility manager (or proven pure), key-frame or no animation with Basic/Maya/Softimage calc, not the locked `getModelDataType()==1` path, called from `draw()`.

Added by M3-T01: every material's draw buffer is material-sorted or non-sorted (the main opaque list; `mpXluList`, `mpOpaListFilter`, `mpXluListMaskOff`, `mpXluListInvisible` are Z-sorted), and no texture matrix uses an env-map, proj-map or view-proj-map mode.

**What `entry()` reads** (tww `J3DJoint.cpp:230`, `J3DDrawBuffer.cpp:126`, `J3DMatBlock.cpp:1782`, `d_drawlist.cpp:1906`): `entryIn` takes `getAnmMtx(jnt)` and stores it as the buffers' Z matrix (a pointer). `entryZSort` reads its translation to compute the sort key, at entry time. `J3DTexGenBlockPatched::calc` reads the matrix only for env-map, proj-map and view-proj-map texture matrices; other modes ignore it. Material sort (the default) and non-sort don't read it.

**Async pose job** (proposed):

```
actor draw(): setBaseTRMtx → capture inputs → submit(calc+viewCalc) → entry()
...remaining actors' draw()...
draw-list flush: join all → publish matrices + scale flags → set j3dSys as the last serial calc would → draw
```

Guest cycles for the serial calc are charged at submit. A job never writes live guest memory; publication happens on the game thread.

## Existing native sets: port, don't write (2026-11-03)

The natives this plan needs already exist, certified on an older pipeline, and are off:

| File (set) | Covers | Recorded cost |
| --- | --- | --- |
| `native_anim.c` (set 4) | Multi-key `J3DAnmTransformKey::calcTransform`, `J3DGetKeyFrameInterpolation<f32>`/`S`, Hermite | 2.2–2.5 % at Forest Haven, Dragon Roost |
| `native_mtxcalc.c` (entries) | Maya/Basic/Softimage `calcTransform` with callees | 0.46 + 0.14 % on Outset |
| `native_jas.c` (entries, seventh round) | `TOscillator`, `TChannel::updateEffectorParam`/`updateMixer`/`updateAutoMixer`, `Calc::sinfT` | 2.6 % at Forest Haven, 0.9 % at sea |

Why they don't run (generator run against the `m437-a` composite, and #541):

1. **Behaviour timing is on by default** (`build.py`, `--no-behaviour-timing` turns it off). Blocks now start `if (downcount <= -LOOP_BUDGET) return; cycle_block_prepaid = true; downcount -= N; goto bwfast_K;` with budget checks only at loop heads (`behaviour_timing.py --loop-checks`). `native_gx_gen.py`'s `LEADER` expects `cycle_block_prepaid = dolrecomp_block_can_precharge(ctx, N);`, so `native_leaf_gen.py` stops at the first entry (`__ieee754_fmod: 8032EC1C is not a block leader`).
2. **`lean_deadlines.py`'s access form** (`{ bool bw_ool = false; … bw_write32_ato(&bw_ool, ctx, …); if (__builtin_expect(bw_ool, 0) && …) }`) is unknown to the generator (#541's `unhandled ctx` failure).
3. **Hashes.** `native_entries.py` hooks a native only where the translation hashes to the body its differential test ran against; set 4 builds but is never hooked on this tree.

Port: teach `native_gx_gen.py` the behaviour-timing leader and the `_ato` form (the new block shape is simpler: one charge per block, budget at loop heads), re-run `tests/native_leaf_test.c` and the set-4 tests against the current translation, record the hashes. This replaces "write new natives" in M2 and is the serial half of M6-T02.

## Decline reasons (from source, M1-T00)

| Path | Guards | Likely dominant reason | Widening |
| --- | --- | --- | --- |
| Skinning (`native_skin.c`) | FP/PS state, no write journal, plain RAM, stores apart from reads, finite floats < 2^31, **the whole function's cycles (58 + 23 per envelope + 60 per joint) inside the turn budget and before the next deadline** | The turn-budget guard, **confirmed by [#541](https://github.com/chrissotraidis/bluewake/pull/541)** (8k+ cycle calls decline 91–100 %) | Done and dropped: #541's partial runs were exact but within noise; out of scope here |
| `transform-simple` (`J3DAnmTransformKey::calcTransform`) | **zero- or one-key channels only**; `ready(256)` | By design: any animated channel (> 1 key) declines | Native multi-key transform calling the native `key-s`/`key-f` interpolation; the largest M2 item |
| `key-s` (`J3DGetKeyFrameInterpolationS`) | `ready(512)` (no positive `downcount`, budget and deadline ≥ 512 cycles), GQR5 must be signed short with scale 0, ≤ 256 keys, strictly increasing times, time in range | Unknown: GQR5 scale, key count and the cycle bound are all plausible | Count reasons first (M1-T01) |

## Validation

- Native widening: existing differential oracles extended to each widened case; checkpoint and picture comparison over `bench_tour` stops.
- Async: serial build as oracle; identical checkpoints and pictures; A/A then A/B with `render_bench` on the Deck; report p95/p99 update time, not only means.

## Commands

```sh
# guest-PC profile of the Outset stop (wrapper app sets BLUEWAKE_PC_SAMPLE, _FROM=2700, _TO=4200)
python3 scripts/bench_tour.py CARD wrapper.sh --mode headless
python3 pc_sample_attribute.py tww/config/GZLE01/symbols.txt outset.pcs 45
```
