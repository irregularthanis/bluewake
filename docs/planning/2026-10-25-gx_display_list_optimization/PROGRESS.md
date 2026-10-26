# PROGRESS — Repeated GX display-list optimization

Status: M0 complete; M2-B preliminary Deck A/B positive, full qualification pending

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

- [ ] M2-B0-T01: Attribute FIFO hashing, array/epoch validation, lookup/conflicts and vertex-copy work in stable, slow and worst views.
- [ ] M2-B0-T02: Rank costs with activation counts and select one B1–B4 candidate; record a no-go if no component dominates.
- [ ] M2-B1-T01: If selected, reduce FIFO identity cost without weakening payload mutation coverage.
- [ ] M2-B2-T01: If selected, reduce indexed-array epoch work after auditing runtime mutation paths.
- [ ] M2-B3-T01: If selected, map `DrawPlan`/interpolation/upload lifetimes before prototyping reduced vertex copying.
- [ ] M2-B4-T01: If selected, measure conflicts, evictions and resident bytes before changing cache organization.
- [ ] M2-B5-T01: Complete mutation, collision, eviction, reset, shutdown and cached-versus-uncached equivalence tests.
- [ ] M2-B6-T01: Run A/A then rotated cache-off/M2-B/optimized-candidate Deck rounds across fixed views and the five-scene tour.
- [ ] M2-B6-T02: Record FPS/frame-time, GX-worker/process CPU, activation and player-facing results; retain only a repeatable improvement.

### M3: Generation-keyed derived state (depends: M0)

Parallel with M1 and M2; owns state generations and cache-hit comparison.

- [ ] M3-T01: Measure current cache hit/miss rates and comparison cost.
- [ ] M3-T02: Replace large hot-path comparisons with verified generation identities.
- [ ] M3-T03: Run GXCore equivalence tests and matched Deck profiling.

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

Private logs, saves, translated modules and AppImages are not published.
