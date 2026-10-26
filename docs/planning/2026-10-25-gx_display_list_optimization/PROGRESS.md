# PROGRESS — Repeated GX display-list optimization

Status: M0 diagnostic wired into the builder; corrected build pending

[Product brief](PRD.md) · [Technical plan](TECH_PLAN.md)

## Milestones

### M0: Attribute repeated work

Architecture: [GX command path](../../architecture/Graphics.md#gx-command-path).

- [x] M0-T01: Measure matched stable and slow Outset camera angles with plan counters.
- [x] M0-T02: Map the hot path to RecompCore GXCore and candidate Wind Waker foliage loops.
- [x] M0-T03: Add a per-frame display-list identity histogram and reconcile it with plan totals.
- [ ] M0-T04: Rank display-list owners by contribution to the stable/slow delta.

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
| M0-T03 | [RecompCore `4b5f0ae`](https://github.com/irregularthanis/RecompCore/commit/4b5f0ae989fcbd8f544984fdc79679acd25e87c3); BlueWake pin in [fork PR #2](https://github.com/irregularthanis/bluewake/pull/2) | Replay the diagnostic on current runtime base `1446450`; pin both `config/dependencies.lock.json` and `scripts/builder/profiles/bluewake.sh` | Fork-only integration | Diagnostic source is integrated. The earlier `gx-fix-c7b7ced2d88c` AppImage used builder-profile pin `47a5229` and is rejected as evidence; corrected build and M0-T04 capture remain pending. |

Private logs, saves, translated modules and AppImages are not published.
