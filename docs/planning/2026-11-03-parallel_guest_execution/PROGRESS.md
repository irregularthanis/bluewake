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
- [ ] M8-T04: Markers for the rest of the frame (owner, 2026-11-13: get the data): 'D' one process's draw (`fpcDw_Execute` 0x8004042C → the return into `fpcM_Draw` 0x8003E328) and 'S' the scene execute's sub-phases (`calcPauseTimer`, `dKy_itudemo_se`, `dDemo_manager_c::update`, `executeEvtManager`, `dAttention_c::Run`, `dDetect_c::proc`, each back into `dScnPly_Execute`), splitting the enclosing region into parts; trace record v2 (kind, part, marker); the study reports per loop and names processes from `f_pc_profile_lst.cpp`
- [~] M8-T05: B1b built 15:12 from `902b501c4` (`artifacts/shadow-b1/902b501c4c58`, 271 MB; the markers compiled clean); the three traces and the study per loop running from 15:13 (`measure-shadow-batches/v2/`)
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
- [x] M7-T01: E0, occupied cores on the Deck: headless **−0.65 %**; Game Mode, six launches: **−21.3 %** (A 25.77, B 20.30 game FPS) with the GPU 18.2 → 24.4 ms, spinners at 100 % duty pinned to the two other physical cores. Not a stop (owner, 2026-11-13): the penalty is the Deck's power budget, priced per device in M10; a duty sweep (25/50/75 %) gives the Deck's curve later
- [x] M7-T02: Builds: B2 shadow module done (second attempt; `--shadow` = the builder's `--no-fixed-cpu --no-fixed-mem1`, gather pipe left on for E1a); B1 trace build done 13:03 (second attempt, `--shadow-trace`, from `453bc5179`): `artifacts/shadow-b1/453bc5179e77/BlueWake-shadow-b1-x86_64.AppImage`, 271 MB, exports `bluewake_composite_shadow_trace`
- [~] M7-T03: E1a done: the shadow module as the live module costs **≈ 2–5 %** headless (A 30.48 vs B 29.79 game FPS, −2.3 % on means; −5 % on the two clean pairs, the first A launch being a warm-up outlier), guest checkpoints identical; E1b (the trace build's logging cost) comes with B1
- [~] M7-T04: Open questions: timer reads (settled: creation only), takeover addresses (settled), `RTLD_LOCAL` and the `MAP_FIXED` precedent (settled); left: `dlmopen` cost on the Deck, alias share per region
- [ ] M7-T05: Stop/go: E0 < 15 %, E1 < 35 %

### M8: Limit study (depends: M7)
- [x] M8-T01: Trace dumps: `8-busiest`, `6-play`, `1-outset`, 100 game frames each, headless, paced, natives off, on the Deck (13:04–13:06); ≈ 300 MB each in `measure-shadow-batches/traces/` on the workstation, removed from the Deck. The execute pass only: the draw pass does not go through `fpcLnIt_MethodCall`
- [x] M8-T02: `scripts/shadow_limit_study.py` run on the three traces (`measure-shadow-batches/reports/`): with the guest stack excluded and the RNG, current-layer and matrix-scratch words privatized, half the regions offload at 2 workers and the loop's critical path shrinks **1.3–1.7 %**; the serializing words that remain are global scratch (`mDoMtx_stack_c::now`, `mtx`, `mDoLib_clipper`)
- [x] M8-T03: **Stop for the actor-level model.** The loop's time is one process and dust: PLAY_SCENE holds 41 % of the execute loop's guest cycles in one region of ≈ 2.8 M a frame (constant to the cycle; several interrupt windows long, so never a shadow as a whole); PLAYER 5.9 %, BRIDGE 5.6 %, KAMOME 5.3 %, Obj_Timer 4.3 %, BWDG 4.0 %, CAMERA2 3.6 %; the median region is 618 cycles. The top 10 regions a frame hold 69 % of the loop, the top 20 hold 82 %. Batches of neighbours can only overlap the dust. **Correction (same day):** the scene's region is `dAttention_c::Run`, the Z-targeting scan over every actor (it reads `atntable`, `dAttention_c::dist_table`, `loc_type_num`, writes `g_dComIfG_gameInfo`, ≈ 1,000 calls a frame); in shipped builds it is mostly the host's native actor search (#503), so its share of *host time* is a few percent, while the traces (natives off, to log every access) charge its full guest cycles. In host time the loop is a dozen heavy actors (≈ 30 %) plus dust; the conclusion stands

### M9: Engine and takeover (depends: M8 go)
- [ ] M9-T01: Workers, private mappings, batch formation, validation C1–C5, commit, deferred deadlines, census
- [ ] M9-T02: `cNdIt_Method` takeover as a certified native entry; fallback = live method call
- [ ] M9-T03: Verify build (`BLUEWAKE_SHADOW_VERIFY=1`) and `tests/shadow_engine_test.c`; CI on the headless routes
- [ ] M9-T04: Draw pass: FIFO log and ordered append to the live gather pipe

### M10: Deck qualification (depends: M9)
- [ ] M10-T00: Tooling: the host's `[threads]` exit line, the engine census, the merged summary with the sampler's power and clock series, the fault-injection switches (TECH_PLAN, *Testing strategy*)
- [ ] M10-T01: Exactness: checkpoints every retrace vs serial on all 8 states; identical run to run with workers; pictures, route and audio digests; the verify build; fault injection
- [ ] M10-T02: ≥ 6 interleaved Game Mode launches × 8 states, workers 2 (and 1, 3): FPS and the per-update tail, busy and per-thread CPU time, engine census, GPU time, IPC; the worker count that wins on the tail without a loss at 30-FPS states becomes the default
- [ ] M10-T03: Power and heat: APU power, clocks, energy a frame, a 15-minute soak on battery and docked
- [ ] M10-T04: Stability: transitions, REL load/unload, states, menus, suspend/resume, a 30-minute session; core-hog degradation
- [ ] M10-T05: Keep or revert under the extended rule

### M11: Settings (follow-up, after M10 keeps the feature)
- [ ] M11-T01: A `settings.ini` entry (`BLUEWAKE_SHADOW_WORKERS`, like the HD-look switches), read at launch, surfaced in the settings menu as "Parallel workers: Off / Auto / 1 … N", N the device's physical cores less one; Off is the default. A chosen number is honoured as set (clamped only to N), Auto is one entry among them
- [ ] M11-T02: Auto: a per-device rule from M10's results (the Deck's measured optimum; elsewhere from the core count less the game thread, the GX worker and the renderer, clamped to what M10 qualified), shown as the resolved number
- [ ] M11-T03: The menu refuses the setting with one line when the shadow module is absent or mismatched, and the census is visible in the diagnostics overlay

## Evidence ledger

| Task | Commit / artifact | Command / method | Environment / input | Result |
| --- | --- | --- | --- | --- |
| M7 (facts) | `main` after #554; RecompCore `Zelda.cpp`, `MailHandler.cpp`; `dsp_hle_backend.cpp:95`; `main.c` `host_cycle_deadline_distance`, `host_dsp_interrupt` | Source reading, 2026-11-13 | — | HLE DSP interrupts are raised synchronously by the guest's mailbox writes (`SendCommandAck` from `HandleMail*`); `Update()` only pushes `DSP_RESUME`; the delay argument is ignored. Deadline terms: VI event clock, DSP cadence, audio DMA, decrementer, pending. So the DSP cadence (92 % of turn ends, #530) raises no interrupts in play; main-thread landings are VI, audio DMA, decrementer, DVD |
| M7 (facts) | tww `c_node_iter.cpp:11–24`, `c_tree_iter.cpp`, `f_pc_line_iter.cpp:27`, `c_math.cpp:167`, `J3DJoint.cpp:253` | Source reading | — | The process iterator reads `pNext` before the method and `pNext->next` after; the RNG is three static words read-modify-written per draw; `J3DDrawBuffer::entryNum++` per joint entry |
| M7 (facts) | `scripts/windows/build.py:925`, `global_guest_cpu.py` | Source reading | — | The fixed CPU is a post-pass over the chunks (`#define ctx (&bw_guest_cpu)`), run only with `--fixed-cpu`; `--fixed-mem1` requires it. Without them the same chunks use `ctx_param` and `cpu->ram` |
| M7-T02 (B2, first attempt) | `build/shadow-b2.log` | `build_script shadow-b2 eaa85f0f13ca --shadow …` | Workstation, 6 jobs | **Lost.** The Linux builder enables `fixed_cpu`/`fixed_mem1` by default and had no opt-out, so dropping the positive flags changed nothing (the fixed-cpu pass ran); and `build_script` was edited while the build ran it, so the running copy failed after packaging and its cleanup removed the folder. Fix: `--no-fixed-cpu`/`--no-fixed-mem1` in the builder, passed by `--shadow`; never edit `build_script` during a build |
| M7-T02 (B2, second attempt) | `build/shadow-b2-736b568cc967/`, branch `shadow-b2-base` = `eaa85f0f13ca` + `736b568cc` (the builder's `--no-fixed-cpu`/`--no-fixed-mem1`) | `build_script shadow-b2 shadow-b2-base --shadow --clang22 --gather-alias-cache --fp-checks --direct-gate --jobs 6 --tour-playbacks 2` | Workstation, started 10:38 | Shadow confirmed at the compile stage: no `fixed-cpu` pass in the stage list, and the generated chunks take `CPUState* ctx` with no `#define ctx (&bw_guest_cpu)`. Done 11:40: `artifacts/shadow-b2/736b568cc967/BlueWake-shadow-b2-x86_64.AppImage` (200 MB, sha256 `c62064a7…`), module 427 MB with no `bluewake_composite_guest_cpu`/`_mem1` export (ABI v3); copied to the Deck as `~/BlueWake-shadow-b2-x86_64.AppImage` |
| M7-T02 (B1, first attempt) | `build/shadow-b1.log` | `build_script shadow-b1 fork/docs/parallel-guest-execution --shadow-trace …` | Workstation, 6 jobs | Failed in the host build: `main.c` included `shadow_trace.h` by bare name, but the host reaches `cmake/composite` headers by relative path (`../../../cmake/composite/…`). Fixed (`e211a1b96`); a local syntax check of `main.c` with RecompCore's include dirs then reaches the end with only a build-time macro missing. Rebuilt from 12:20 |
| M7-T03 (E1a) | `~/e1a/01…06` on the Deck; A = `BlueWake-hd` (`eaa85f0f13ca`), B = `BlueWake-shadow-b2` (`736b568cc`: the same commit, the shadow builder flags) | Headless, unpaced, `8-busiest`, 23819 retraces, A/B/B/A/A/B; checkpoints every 300 retraces | Steam Deck, idle | A 28.71 / 31.63 / 31.09 (mean 30.48), B 29.83 / 29.91 / 29.62 (mean 29.79): **−2.3 %** on means, −5.4 % and −4.7 % on the two pairs after the warm-up launch. **6 of 6 checkpoints identical** between the fixed and the non-fixed module: the shadow variant is exact |
| M7-T01 (E0 Game Mode, full) | `~/e0-gm/01…06` on the Deck | `gm-launch2.sh`, `8-busiest`, 23819 retraces, A/B/B/A/A/B; B = two spinning threads pinned to cpus 4 and 6 (the two physical cores the game's threads then share with nothing) | Steam Deck Game Mode, 3x + HD look as set in `settings.ini` | A 26.06 / 25.92 / 25.34 (mean 25.77, GPU 18.2 ms), B 20.36 / 20.40 / 20.14 (mean 20.30, GPU 24.4 ms): **−21.3 %**, every pair in the same direction. The earlier single pair (−10.4 %) had unpinned spinners |
| M7-T01 (E0 Game Mode, partial) | `~/e0-gm/01-A`, `02-B` on the Deck | `gm-launch2.sh`, `8-busiest`, 23819 retraces; B = two spinners pinned to cpus 4 and 6 (separate cores) | Steam Deck Game Mode, 3x + HD look as set in `settings.ini` | A 25.92 game FPS, GPU 18.1 ms; B 23.22, GPU 22.4 ms: **−10.4 %**. One pair; the third launch hit Steam's cloud-sync prompt and the run was stopped |
| M7-T01 (E0 headless) | `BlueWake-hd` (Nov 10 build), `gm-states/8-busiest.bwstate`, `~/e0-cores/` on the Deck | Headless, unpaced, `BLUEWAKE_MAX_RETRACES=23819`, A/B/B/A/A/B; B = two unpinned spinning threads; game FPS = mean `[perf]` rate/2 after 300 retraces | Steam Deck, idle, `BLUEWAKE_DIRECT_GATE=1 BLUEWAKE_MODULE_HUGEPAGES=1` | A 30.83 (29.91, 31.24, 31.34), B 30.63 (29.82, 31.05, 31.02): **−0.65 %**, inside the first-launch warm-up spread. Note: unpaced headless runs the busiest view at ≈ 31 game FPS against 26.5 in Game Mode (#592), so the GPU's power share already costs the game thread ≈ 15 % there |
| M7-T04 | tww `f_op_actor.cpp:97`, `symbols.txt`; `main.c:7763`; `guest_cpu.c:29`; `module_hugepages.h:89` | Source reading, 2026-11-13 | — | Timebase read once per actor creation, not in execute/draw; `cNdIt_Method` at 0x80244EB4; module loaded `RTLD_LOCAL`; MEM1 page-aligned; the host already `MAP_FIXED`-remaps the module's code |
| M8 (E2) | `measure-shadow-batches/traces/{8-busiest,6-play,1-outset}.trace`, `reports/*.txt`, `*.v2.txt` (stack excluded, scratch privatized), `*.ceiling.txt` | B1 trace build (`453bc5179`), `e2trace.sh` on the Deck: headless, paced, natives off, 100 game frames after a 300-retrace settle; `shadow_limit_study.py` here | Steam Deck (traces), workstation (study) | Per state ≈ 209 execute regions a game frame, mean ≈ 34k guest cycles, p50 618, p99 393k, max 3.2 M; ≈ 22 interrupt deliveries a game frame but inside only ≈ 1 % of regions; 10 % of regions use the interpreter's quantised loads (logged), 1.4 % an interpreter instruction (abort). First pass: 0 % (every pair "conflicted" through the guest stack, `0x8040CC00–0x8040CE84`, and `l_fpcLy_CurrLayer_p`). Stack excluded and those words privatized: 2 workers offload 10,315 of 20,896 regions for **1.6 %** (busiest), 1.7 % (play), 1.3 % (Outset) off the loop; 3 workers 1.4–2.1 % |
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
| 2026-11-13 | Opt-in at run time (`BLUEWAKE_SHADOW_WORKERS`) and at build time (the shadow module is a second player-built module); +150–300 MB RAM and ≈ 400 MB disk (≈ 150 MB in an AppImage, or an opt-in sidecar) when on, nothing when off; the live module keeps every existing optimization, the shadow gives up the fixed CPU, fixed MEM1, gather pipe and 2 MB pages |
| 2026-11-13 | E0 Game Mode: two cores at 100 % duty cost the game thread 21.3 % and the GPU 34 % of its frame time. **Owner: not a stop.** The penalty is the Deck's shared power budget, not the design's; other devices keep the gain, and the worker setting is per device. On the Deck, M10 decides with the gain at the workers' real duty against a duty sweep's penalty at that duty. Runs on the Deck start only on the owner's OK |
| 2026-11-13 | Owner: E2 answered; keep gathering data on this PR (the draw pass, the scene's sub-phases) and open a separate trio for the migration of guest services to the host, ranked by gain, on the fork |
| 2026-11-13 | **E2 stops the actor-level model** (the gate was ≥ 15 %, measured ≈ 1.5 % of the execute loop). The loop is one process (PLAY_SCENE, 41 %) plus dust; what batches of neighbours can overlap is cheap, and the heavy regions are few, far apart and longer than an interrupt window. Open: a trace of the draw pass (its iterator is not `fpcLnIt_MethodCall`), and whether PLAY_SCENE's own sub-phases are separable (a different, hand-certified takeover inside one function) |
| 2026-11-13 | Owner: build the module variants locally (B2 shadow, then B1 trace) once the plan is written up. Workers park between batches; the Deck's power budget is a measured cost (E0 Game Mode) |
| 2026-11-13 | PRs for this work go to the fork (irregularthanis/bluewake) only, not upstream, until the owner says otherwise |
| 2026-11-04 | **Stopped (no-go for now).** At these shares a second thread can't reliably pay for itself: ≤ +6.5 % for the audio thread before synchronization, after weeks of reentrant codegen. Reopen if a scene's audio or another separable guest thread measures well above 8 % on the Deck, or once Track A's natives make an async job cheap |
| 2026-11-04 | Measured on the Deck: audio thread 6.1 % of Outset, translated code ≈ 90 % of the game host thread. Overlapping audio is worth at most ≈ +6.5 % and needs translated code on a second thread (Track B: reentrant codegen). Host-side offload is worth at most ≈ 9 %. Any multi-threaded path must beat the serial build (full stack, opt-ins on) in every one of ≥ 6 interleaved Deck launches with identical checkpoints, or it's reverted |
| 2026-11-03 | Native widening comes before any async job. An async pose job is all-or-nothing per model: one declining joint keeps the whole model serial, so M4 is gated on M2 covering multi-key transforms and large-model skinning. |
| 2026-11-03 | Async pose job eligibility adds: every material in a material-sorted or non-sorted buffer, no env/proj-map texture matrix |
