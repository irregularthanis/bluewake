# PROGRESS — Parallel guest execution

Status: **Reopened 2026-11-13: shadow batches** (exact by construction; see the PRD's revision and the TECH_PLAN design). Week 1: E0 running on the Deck, E1 and the open questions next. The 2026-11-04 stop stands for the earlier model.
[Product brief](PRD.md) · [Technical plan](TECH_PLAN.md)

## Milestones

### M0: Baseline and audit
- [x] M0-T01: Reentrancy and guest-state audit (fixed CPU/MEM1 ABI, globals, write journal, worker pool)
- [x] M0-T02: Track decision: A first, B second choice with a reopen criterion
- [x] M0-T03: Guest-PC profile of Outset with subsystem attribution (contended run)
- [ ] M0-T04: Repeat on an idle machine; all five tour stops; real FPS
- [x] M0-T05: Pass sampler variables through `bench_tour.py`; commit the attribution script (`scripts/pc_sample_attribute.py`)

### M1: Decline census (depends: M0)
- [x] M1-T00: Decline reasons from source (see TECH_PLAN, *Decline reasons*)
- [ ] M1-T01: Reason codes for `key-s`, `transform-simple` declines (skinning: done in #541)
- [ ] M1-T02: Rank reasons by translated time they leave behind

### M2: Native widening (depends: M1)
- [x] M2-T00: Found existing natives for multi-key transforms (`native_anim.c`), mtx-calc (`native_mtxcalc.c`) and audio channels (`native_jas.c`); blockers: behaviour-timing leaders, `_ato` accesses, hashes (TECH_PLAN)
- [ ] M2-T01: Port `native_gx_gen.py`/`native_leaf_gen.py` to the behaviour-timing block shape and `_ato` accesses; generator runs on the current composite
- [ ] M2-T01b: Re-run the sets' differential tests, record hashes; Deck A/B
- [ ] M2-T02: Deck A/B, checkpoints and pictures identical

### M3: Overlap window (parallel with M1)
- [x] M3-T01: Check `entry()`/`entryIn` for matrix reads: reads values only for Z-sorted buffers and env/proj-map texture matrices
- [ ] M3-T02: Read trace of an eligible model's matrices between update and flush in Outset
- [ ] M3-T03: Count eligible models per frame and joints per model; go/no-go for M4

### M4: Async pose job harness (depends: M2, M3 go)
- [ ] M4-T01: Off-gameplay harness: concurrent jobs equal serial results; break-even size

### M5: Opt-in gameplay proof of concept (depends: M4)
- [ ] M5-T01: Submit in `mDoExt_modelUpdateDL`, join at flush, behind a flag
- [ ] M5-T02: Deck A/B; keep or reject

### M6: Audio lead
- [x] M6-T00: Source and sampler survey (PRD, *Audio lead*)
- [x] M6-T01a: Sampler counts per guest thread (`PATH.threads`); standalone check of the sampler block
- [x] M6-T01: Steam Deck run (idle, rendered): the audio thread is **6.1 %** of Outset's guest samples; the game thread is 93.7 %. Upper bound for overlapping it: ≈ +6.5 %. Other tour stops not yet measured
- [ ] M6-T03: Any async audio path: opt-in behind `BLUEWAKE_ASYNC_AUDIO=1`, off by default; serial audio is the default and the oracle
- [ ] M6-T02: If ≥ 8 %: port the `JASChannel` natives from `--native-entries`; measure the game thread's first audio-state access after each wake

### M7: Feasibility week (shadow batches)
- [ ] M7-T01: E0, occupied cores on the Deck: headless A/B/B/A/A/B with two spinning cores (running 2026-11-13), then Game Mode
- [ ] M7-T02: Shadow module build: `fixed_cpu=0`, `fixed_mem1=0`, gather pipe off, `BLUEWAKE_SHADOW` memory paths (read filter, write log, alias side buffer, aborts)
- [ ] M7-T03: E1, shadow overhead: trace mode, no parallelism, same route as live
- [ ] M7-T04: Open questions: timer reads per region, alias share per region, `dlmopen` twice on the Deck, memfd-backed MEM1 with the fixed-MEM1 live module
- [ ] M7-T05: Stop/go: E0 < 15 %, E1 < 35 %

### M8: Limit study (depends: M7)
- [ ] M8-T01: Trace dumps: `8-busiest`, `6-play`, `1-outset`, 300 frames each, paced, on the Deck
- [ ] M8-T02: `scripts/shadow_limit_study.py`: parallel fraction by workers and batch size; failure causes; serializing words
- [ ] M8-T03: Stop/go: ≥ 15 % of game-thread time in validating batches at 2 workers after P1/P2; < 10 % stops

### M9: Engine and takeover (depends: M8 go)
- [ ] M9-T01: Workers, private mappings, batch formation, validation C1–C5, commit, deferred deadlines, census
- [ ] M9-T02: `cNdIt_Method` takeover as a certified native entry; fallback = live method call
- [ ] M9-T03: Verify build (`BLUEWAKE_SHADOW_VERIFY=1`) and `tests/shadow_engine_test.c`; CI on the headless routes
- [ ] M9-T04: Draw pass: FIFO log and ordered append to the live gather pipe

### M10: Deck qualification (depends: M9)
- [ ] M10-T01: ≥ 6 interleaved Game Mode launches × 8 states, workers 2 (and 1, 3): FPS, checkpoints, pictures, power, thermals
- [ ] M10-T02: Keep or revert under #503's rule

## Evidence ledger

| Task | Commit / artifact | Command / method | Environment / input | Result |
| --- | --- | --- | --- | --- |
| M7 (facts) | `main` after #554; RecompCore `Zelda.cpp`, `MailHandler.cpp`; `dsp_hle_backend.cpp:95`; `main.c` `host_cycle_deadline_distance`, `host_dsp_interrupt` | Source reading, 2026-11-13 | — | HLE DSP interrupts are raised synchronously by the guest's mailbox writes (`SendCommandAck` from `HandleMail*`); `Update()` only pushes `DSP_RESUME`; the delay argument is ignored. Deadline terms: VI event clock, DSP cadence, audio DMA, decrementer, pending. So the DSP cadence (92 % of turn ends, #530) raises no interrupts in play; main-thread landings are VI, audio DMA, decrementer, DVD |
| M7 (facts) | tww `c_node_iter.cpp:11–24`, `c_tree_iter.cpp`, `f_pc_line_iter.cpp:27`, `c_math.cpp:167`, `J3DJoint.cpp:253` | Source reading | — | The process iterator reads `pNext` before the method and `pNext->next` after; the RNG is three static words read-modify-written per draw; `J3DDrawBuffer::entryNum++` per joint entry |
| M7 (facts) | `scripts/windows/build.py:925`, `global_guest_cpu.py` | Source reading | — | The fixed CPU is a post-pass over the chunks (`#define ctx (&bw_guest_cpu)`), run only with `--fixed-cpu`; `--fixed-mem1` requires it. Without them the same chunks use `ctx_param` and `cpu->ram` |
| M0-T01 | `main` `ee991d3`, RecompCore `0fe472a`, generated source of `m437-a` | Source reading | — | Translated code bound to one global CPU and RAM; see PRD |
| M0-T03 | `m437-a-14c558d62d1c` | `bench_tour.py --mode headless`, `BLUEWAKE_PC_SAMPLE` 2700–4200, tww `symbols.txt` | Desktop, **concurrent build running** | J3D 21.9 %, collision 14.1 %, audio 9.3 %; FPS figures invalid |
| M0-T03 | same | `[native-*]` exit counters | same | `key-s` 77 % declined, `transform-simple` 76 %, skinning 9 % |
| M6-T01 | stack `afb6c35d8805` + this branch's sampler host (`531706966`, module byte-identical) | `render_bench --runs 1`, `BLUEWAKE_PC_SAMPLE` over the whole run, `1-outset.bwstate`, render scale 3, Smooth Motion | Steam Deck, desktop session, nothing else running | Threads: `803A2960` 212,470 (93.7 %), `803E9260` 13,785 (**6.1 %**), `803A7320` 481, `804211E0` 63. `803E9260`'s pcs: 54.5 % in `0x8027xxxx`–`0x8028xxxx` (JAudio), 44.3 % in `0x8030xxxx`–`0x8032xxxx` (SDK, math): the audio thread |
| M6-T01 | stack `afb6c35d8805`, gate and huge pages on | `render_bench --cpu-profile`, Outset | Steam Deck | Game host thread: translated code ≈ 90 % (`[JIT]` 38.7 % is the module on huge pages, which perf can't name, plus `gGZLE01_recomp.so` 7.0 %, of 50.9 % of all samples), `bluewake` 4.6 % (≈ 9 %), libc 0.7 %. Host-side offload is worth at most ≈ 9 % |

## Decisions

| Date | Decision |
| --- | --- |
| 2026-11-03 | Track A (native async jobs) first; Track B kept as second choice, reopened only by the PRD criterion |
| 2026-11-03 | Async audio, if built, is opt-in (`BLUEWAKE_ASYNC_AUDIO=1`), off by default; serial audio stays the default and the oracle |
| 2026-11-03 | Host DSP excluded (HLE by default, ≈ 1 %). Audio lead is the guest `JASystem` thread; gated on a per-thread measurement |
| 2026-11-03 | Skinning dropped from this plan: #541 measured it (≈ 1.5 % of the Deck game thread, threading ≈ +0.5–1 %). Estimates lowered to Deck cycle counts: serial widening ≈ 1–2 %, async pose job ≈ 1–3 %. Next lead: audio |
| 2026-11-13 | **Reopened with the shadow-batch model** (owner: weeks are fine if behaviour is preserved and game-thread work moves to other cores). Exactness by construction is the bar: identical checkpoints, pictures and GX order against the serial build; nothing speculative writes live state; serial fallback at the same logical point. Stop points after week 1 (E0/E1) and week 3 (E2) |
| 2026-11-13 | PRs for this work go to the fork (irregularthanis/bluewake) only, not upstream, until the owner says otherwise |
| 2026-11-04 | **Stopped (no-go for now).** At these shares a second thread can't reliably pay for itself: ≤ +6.5 % for the audio thread before synchronization, after weeks of reentrant codegen. Reopen if a scene's audio or another separable guest thread measures well above 8 % on the Deck, or once Track A's natives make an async job cheap |
| 2026-11-04 | Measured on the Deck: audio thread 6.1 % of Outset, translated code ≈ 90 % of the game host thread. Overlapping audio is worth at most ≈ +6.5 % and needs translated code on a second thread (Track B: reentrant codegen). Host-side offload is worth at most ≈ 9 %. Any multi-threaded path must beat the serial build (full stack, opt-ins on) in every one of ≥ 6 interleaved Deck launches with identical checkpoints, or it's reverted |
| 2026-11-03 | Native widening comes before any async job. An async pose job is all-or-nothing per model: one declining joint keeps the whole model serial, so M4 is gated on M2 covering multi-key transforms and large-model skinning. |
| 2026-11-03 | Async pose job eligibility adds: every material in a material-sorted or non-sorted buffer, no env/proj-map texture matrix |
