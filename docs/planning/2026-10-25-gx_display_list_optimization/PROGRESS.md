# PROGRESS — Repeated GX display-list optimization

Status: M0 attribution complete; implementation candidates unblocked

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

- [ ] M2-T01: Freeze the display-list/layout/array-generation key and bounded eviction contract.
- [ ] M2-T02: Reuse decoded vertices and topology with counters and an uncached fallback.
- [ ] M2-T03: Test mutable lists/arrays, unknown addresses, eviction and shutdown.
- [ ] M2-T04: Run the matched Deck qualification and retain only a measurable improvement.

Candidate status: [`RecompCore@857ca0d`](https://github.com/irregularthanis/RecompCore/commit/857ca0dc720b028e66328d5feef207beb691af3f) implements default-off decoded-vertex reuse with bounded storage and hit/miss/bypass counters. Direct-payload mutation, indexed-array mutation and unknown-address fallback pass focused tests. Topology reuse, eviction/shutdown coverage and Deck evidence remain open, so no M2 task is complete yet.

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

Private logs, saves, translated modules and AppImages are not published.
