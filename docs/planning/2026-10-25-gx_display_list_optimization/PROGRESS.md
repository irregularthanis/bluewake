# PROGRESS — Repeated GX display-list optimization

Status: M0 complete; narrow M2-B3 rejected; M2-B4 miss attribution ready to build

[Product brief](PRD.md) · [Technical plan](TECH_PLAN.md)

## Milestones

### M0: Attribute repeated work

Architecture: [GX command path](../../architecture/Graphics.md#gx-command-path).

- [x] M0-T01: Measure matched stable and slow Outset camera angles with plan counters.
- [x] M0-T02: Map the hot path to RecompCore GXCore and candidate Wind Waker foliage loops.
- [x] M0-T03: Add a per-frame display-list identity histogram and reconcile it with plan totals.
- [x] M0-T04: Rank display-list owners by contribution to the stable/slow delta.

### M1: Same-transform fusion (depends: M0)

Parallel with M2 and M3; owns plan concatenation and its exactness tests.

- [ ] M1-T01: Implement the constrained fusion contract from merged PR #454 behind a default-off switch.
- [ ] M1-T02: Test state/resource boundaries, ordering, index rebasing and Smooth Motion tags.
- [ ] M1-T03: Measure activation, plan reduction, GX-worker time and rendered output.

### M2: Geometry and topology reuse (depends: M0)

Parallel with M1 and M3; owns geometry keys, cache storage and invalidation.

- [x] M2-T01: Freeze the FIFO/layout/dirty-epoch key and bounded direct-mapped storage contract.
- [x] M2-T02: Reuse decoded vertices with counters and an uncached fallback.
- [ ] M2-T03: Test mutable lists/arrays, unknown addresses, eviction and shutdown.
- [ ] M2-T04: Run the matched Deck qualification and retain only a measurable improvement.

| Candidate | Validation | Deck result | Decision |
| --- | --- | --- | --- |
| [M2-A `857ca0d`](https://github.com/irregularthanis/RecompCore/commit/857ca0dc720b028e66328d5feef207beb691af3f) | Payload and referenced array bytes hashed; focused contract passed | 91.4% eligible hit rate; ~28 → ~24 FPS; GX worker ~26% → 41–43%; CPU +9.7% | Rejected |
| [M2-B `739de26`](https://github.com/irregularthanis/RecompCore/commit/739de26186b636ad251c4062ad20db0f916fda35) | FIFO payload hash + one dirty epoch per distinct indexed array; focused contract passed | 91.5% eligible hit rate; repeated worst-view GX worker -5.1%, process CPU -1.1%; no visual issue; subjectively more stable | Continue qualification |

M2-T03 and M2-T04 remain open: FPS was not captured, and eviction/shutdown plus the full interleaved methodology still require validation.

#### M2-B follow-up: Optimize successful hits (depends: M2-B evidence)

- [x] M2-B0-T01: Attribute FIFO hashing, array/epoch validation, lookup/conflicts and vertex-copy work in stable, slow and worst views.
- [x] M2-B0-T02: Rank costs with activation counts and select one B1–B4 candidate; B3's redundant vertex initialization is the first isolated change.
- [ ] M2-B1-T01: If selected, reduce FIFO identity cost without weakening payload mutation coverage.
- [ ] M2-B2-T01: If selected, reduce indexed-array epoch work after auditing runtime mutation paths.
- [x] M2-B3-T01: Map `DrawPlan`/interpolation/upload lifetimes and implement the narrow hit-path zero-initialization removal without changing ownership.
- [x] M2-B3-T02: Complete the standard Clang 18 container build and verify the AppImage contains BlueWake `8a6376d` with RecompCore `2a4a985`.
- [ ] M2-B3-T03: Measure A/A noise, then rotate cache-off, original M2-B and M2-B3 across stable, slow and worst fixed views.
- [ ] M2-B3-T04: Run the five-scene tour and player-facing Outset traversal; compare checkpoints, rendered behavior, frame time and CPU.
- [x] M2-B3-T05: Record the negative fixed-view gate and stop the narrow candidate before the full tour; retain broader zero-copy work as deferred.
- [x] M2-B4-T01: Select a fixed-capacity two-way layout from measured conflicts and document its 128-byte replacement metadata.
- [x] M2-B4-T02: Implement 128 two-way sets, restore the original B3 initialization behavior, and pass the focused collision/invalidation contract.
- [x] M2-B4-T03: Build and publish the two-way B4 AppImage with source receipts and diagnostics enabled for the first fixed-view pass.
- [x] M2-B4-T04: Compare conflicts, hit rate and process/GX-worker CPU; record the inconclusive result rather than advancing the layout.
- [x] M2-B4-T05: Restore direct-mapped behavior and add diagnostic-only miss classes plus 256/512 direct/two-way shadow caches.
- [ ] M2-B4-T06: Build the attribution AppImage and use one representative session to decide whether B4 or B2 owns the remaining misses.
- [ ] M2-B5-T01: Complete mutation, collision, eviction, reset, shutdown and cached-versus-uncached equivalence tests.
- [ ] M2-B6-T01: Run A/A then rotated cache-off/M2-B/optimized-candidate Deck rounds across fixed views and the five-scene tour.
- [ ] M2-B6-T02: Record FPS/frame-time, GX-worker/process CPU, activation and player-facing results; retain only a repeatable improvement.

### M3: Generation-keyed derived state (depends: M0)

Parallel with M1 and M2; owns state generations and cache-hit comparison.

- [x] M3-T01: Measure current cache hit/miss rates and comparison cost.
- [ ] M3-T02: Replace large hot-path comparisons with verified generation identities.
- [ ] M3-T03: Run GXCore equivalence tests and matched Deck profiling.

| Candidate | Validation | Result | Decision |
| --- | --- | --- | --- |
| Compact keys for the derived-state cache (`DerivedCache`, `gxcore.cpp`) | `[gx-derived]` counters over 400-game-frame windows; ETW CPU sampling resolved to source lines; Windows desktop, all cores and 2/4-core affinity | 68% hits in the hilltop grass, 35% at the pier. Texture key and hit check 0.13% of GX-worker samples; the whole cache under 1% | Proposed no-go as written: nothing left to cut measurably (owner's call) |

The derived cache already works: its version check and `memcmp`s are about a tenth of a percent of the GX worker. Where compact state identities could still pay is the copying of register snapshots into every packet (`emit_new_packets`, the render sink: about 18% of GX-worker samples together), not the cache's comparison. The GX worker's largest costs in the same profile are the rest of `build_draw_plan_into` (22%, the M2 area), `RetailGxFrontend::parse_stream` (12%) and guest address resolution (5.5%). These are desktop numbers; the Deck matched qualification is unchanged.

### M4: Matrix-varying instancing decision (depends: M1, M2)

- [ ] M4-T01: Profile the remaining repeated matrix-varying lists after accepted reuse/fusion work.
- [ ] M4-T02: Specify ordering, transparency, shadow and interpolation contracts.
- [ ] M4-T03: Build a default-off prototype or record a measured no-go decision.

### M5: Integrate and qualify (depends: M0; selected candidate must also be complete)

- [ ] M5-T01: Land the runtime companion in RecompCore, then pin and export it in BlueWake.
- [ ] M5-T02: Run A/A and interleaved A/B across the full benchmark methodology on Steam Deck.
- [ ] M5-T03: Complete player-facing Outset and transition checks and publish redacted aggregate evidence.

## Evidence ledger

| Task | Commit / artifact | Command / method | Environment / input | Result |
| --- | --- | --- | --- | --- |
| M0-T01 | Local stable/slow counter captures; tested BlueWake `b721e785fbfb`; AppImage SHA-256 `406fcf53...cc575` | 15-second `[cutscene]` plan-counter captures at two fixed camera angles | Steam Deck LCD, Game Mode, Outset, Smooth Motion disabled | Stable 445 frames at 629.13 plans/frame; slow 399 at 1,076.34; +71.1%; no skipped/cull/decode failures |
| M0-T02 | BlueWake main `b1bf26a`; RecompCore GXCore/frontend sources; zeldaret/tww foliage sources | Source inspection plus existing flat profiles | Current main docs and tested candidate source | Hot path mapped; foliage loops are candidates, not yet attributed owners |
| M0-T03 | [RecompCore `4b5f0ae`](https://github.com/irregularthanis/RecompCore/commit/4b5f0ae989fcbd8f544984fdc79679acd25e87c3); BlueWake `24291d4`; AppImage SHA-256 `f84ff19b...948ff` | Standard Clang 18 container build; verify compiled diagnostic strings and runtime activation | Linux build plus Steam Deck LCD Game Mode | Build, AppImage packaging and ABI audit passed; live process emitted per-present attribution records. |
| M0-T04 | Private logs: stable `9ed7955d...f692`, slow `6efea0f9...fb70`, worst `f8b2bdd6...a83cd`; [GZLE01 symbols](https://github.com/zeldaret/tww/blob/main/config/GZLE01/symbols.txt) | Matched 15-second fixed-camera captures; aggregate top-12 identities per present and map main-DOL addresses to symbols | Outset state; 449/388/353 frames; pacing disabled | Plans/frame 500.63 → 983.61 → 1,776.96. Grass rises 115 → 840 from slow to worst, explaining 91% of that plan delta. Prioritize M2 geometry reuse for repeated grass lists. |
| M2 candidate | [RecompCore `857ca0d`](https://github.com/irregularthanis/RecompCore/commit/857ca0dc720b028e66328d5feef207beb691af3f) | Build and run focused `gxcore_tests`; inspect opt-in counters | GCC 16 isolated GXRuntime build; `DOL_GXCORE_GEOMETRY_CACHE=1` test process | PASS: repeat hit, direct payload mutation miss, indexed-array mutation miss and unknown-address bypass. Full frontend test build is independently blocked by the pre-existing unqualified `RenderPacket` name in `frontend_replay_test.cpp`. |
| M2 Deck decision | Private candidate log `519c1b5c...d15ac1`; control `b4726b7e...c5c28` | Same AppImage, cache on/off, near-matched worst grass-heavy angle, 15-second process sample and runtime FPS/GX markers | Steam Deck LCD, Game Mode, pacing disabled | REJECT: 91.4% eligible hit rate, but cache-on was about 24 FPS versus 28 control; GX worker 41–43% versus 26%; CPU 2,231 versus 2,033 jiffies. |
| M2-T01 | [RecompCore `739de26`](https://github.com/irregularthanis/RecompCore/commit/739de26186b636ad251c4062ad20db0f916fda35) | Inspect and test the implemented cache key and fallback | 256-entry thread-local cache; default-off | FIFO payload and layout identify direct data; distinct indexed arrays use tracked dirty epochs; unavailable identity bypasses. |
| M2-T02 | BlueWake [`c0eea43`](https://github.com/irregularthanis/bluewake/commit/c0eea43686bfd30085986ef6a0e09937fa3b53e4), AppImage `ebbc9a47...c79e` | Focused CTest; same-AppImage cache-off/cache-on 15-second fixed-view samples | Steam Deck LCD, Game Mode, pacing disabled | PASS: 91.5% eligible hit rate; repeated worst-view GX-worker CPU -5.1% and process CPU -1.1%. Stable view process CPU +3.2%; slow -1.4%. No visual issue; player reported greater stability. |
| M2-B0 diagnostic | [RecompCore `3586581`](https://github.com/irregularthanis/RecompCore/commit/3586581a76cd4c7720357271a4c49449c3eee08b) | Build and run focused `gxcore_tests` with `DOL_GXCORE_OPT_LOG=1` | GCC 16 isolated GXRuntime build | PASS: reports payload bytes, epoch queries, arrays examined, hit vertices, copied bytes, conflicts and evictions. Detailed updates remain opt-in; Deck attribution pending. |
| M2-B0-T01 | Private stable `b5e2bfde...900e7`, slow `3c27693b...67f`, worst `717c9fff...a2c` counter logs and private worst-view `perf.data` | Three isolated fixed-view runs plus 15-second 499 Hz cycles profile | Steam Deck LCD, Game Mode, pacing disabled; BlueWake `f27330a`, RecompCore `3586581` | Hit rates 78.5–90.8%; cached copy volume 15.6–20.3× FIFO hash volume. Worst-view profile: `build_draw_plan_into` 3.55%, vector zero-fill 0.49%, dirty epoch 0.10%, visible long hash 0.05%. |
| M2-B0-T02 / M2-B3-T01 | [RecompCore `2a4a985`](https://github.com/irregularthanis/RecompCore/commit/2a4a985615029acedf1de76e17c6126ace1d66ce) | Source lifetime audit; defer `plan.vertices.assign(...)` from pre-lookup to miss branch; focused `gxcore_tests` | GCC 16 isolated GXRuntime build | PASS: hit path no longer zeroes the complete vector immediately before cached assignment; ownership and cached copy remain unchanged. Deck A/B pending. |
| M2-B3-T02 | BlueWake [`8a6376d`](https://github.com/irregularthanis/bluewake/commit/8a6376d5dd923a68652217b21f5282562c5831b7), RecompCore [`2a4a985`](https://github.com/irregularthanis/RecompCore/commit/2a4a985615029acedf1de76e17c6126ace1d66ce), AppImage `7d7a3cc3...98a2` | Standard Clang 18 CI-container build with `-march=x86-64-v3`, package, publish and verify checksum | Local build `gx-cache-m2b3-8a6376d5dd92`; Steam Deck LCD | PASS: dependency receipt and published AppImage match the intended B3 sources. |
| M2-B3-T02 / T05 | AppImage SHA-256 `7d7a3cc3...98a2`; control `ebbc9a47...c79e` | Same wrapper variables; 15-second fixed-view samples; control then rotated B3 worst-view repeats | Steam Deck LCD, Game Mode; cache on, pacing off, diagnostics off | REJECT narrow B3: control mean process/game/GX 2,194.5/1,480.5/583.5; B3 2,243.5/1,482/626 (+2.2%/+0.1%/+7.3%). Manual placement limits precision, but no positive signal justified the full tour. |
| M2-B4-T01 / T02 | [RecompCore `b8f9e2f`](https://github.com/irregularthanis/RecompCore/commit/b8f9e2f3ffdf0e6b87dc60b02bdf56b9f6a4728f) | Reorganize 256 entries into 128 two-way sets; add same-set coexistence case; build `gxcore_tests`; run focused CTest | GCC 16 isolated GXRuntime build | PASS: two colliding identities coexist; existing payload mutation, dirty-epoch invalidation and safe-bypass checks pass. Deck build pending. |
| M2-B4-T03 / T04 | BlueWake `a4fd684`, RecompCore `b8f9e2f`, AppImage `485e1df3...5a2b`; private log `54f64b9a...ed8a` | Stable/slow and two worst-view 15-second samples; flush aggregate counters on exit | Steam Deck LCD, Game Mode; cache/diagnostics on, pacing off | INCONCLUSIVE: 90.870% eligible hit rate; worst GX-worker mean 607; mixed view results. Old conflict metric did not distinguish invalidation from address collision. |
| M2-B4-T05 | [RecompCore `79282e7`](https://github.com/irregularthanis/RecompCore/commit/79282e7bcb30809f113f288731c8e475dcc58c4c) | Restore direct map; add miss classes and four diagnostic shadow layouts; build/run focused `gxcore_tests` | GCC 16 isolated GXRuntime build | PASS: production contract remains direct-mapped; focused mutation, collision and fallback tests pass. Deck build pending. |
| M3-T01 counters | BlueWake `main` `211abfd`, RecompCore `1446450`, its own training (Clang 22, `x86-64-v3`, Windows) | `DOL_GXCORE_OPT_LOG=1`; two runs of each view from one save state to two retraces, the longer minus the shorter (runs from a state are deterministic) | i5-12600KF, RTX 5070 Ti, Windows 11, D3D12; unpaced, Smooth Motion off, HD look off; Outset hilltop grass (retraces 1600-2400) and the tour's Outset pier (2800-3600) | Hilltop grass: 1,531 draws per game frame, 67.9% derived-cache hits. Pier: 738 draws per game frame, 35.1%. |
| M3-T01 profile | Same build; `BlueWake.pdb` | WPR CPU sampling (about 8.2 kHz effective, 20 s), `xperf` dumper, samples of the GX worker resolved to source lines with DbgHelp | Same PC; hilltop grass, unpaced, cache on | GX worker 62,523 samples (about 38% of a core). Texture key 0.05%, hit check 0.08%, hit copy and counter replay 0.22%, miss derivation 0.46%, store 0.08%. Rest of `build_draw_plan_into` 21.9%, `parse_stream` 12.3%, render sink `submit_packet` 7.9% and `fill_render_packet` 4.3%, `GxCoreSink::submit_packet` 6.2%, `emit_new_packets` 5.7%, guest address resolution 5.5%. |
| M3-T01 core budget | Same build | Same view and trace, the process's affinity set to fewer cores | Same PC; unpaced | All cores 56.5 game frames/s; 2 P-cores 55.9; 4 E-cores 30.1; 2 E-cores 28.1, and 27.6 with the HD look, sun shadows and render scale 4. The GX worker's work stayed 0.37-0.42 of the game thread's in every case; the game thread, not the GX worker, set the pace. |

Private logs, saves, translated modules and AppImages are not published.
