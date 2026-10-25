# Inline register saves after #480: what helped, what didn't (October 24–25, 2026)

The question: #480 makes the inline `_savegpr`/`_restgpr` eligibility check one range test instead of one per
register, and measured +2.4% on a Steam Deck. Does that hold with the training profile held fixed, and is there more
to take in the same place?

The short answer: #480's gain is real and comes from the code (+1.1 to +1.6% here). Writing the frame directly once it
is proven adds about 1 to 2.4%. Inlining the REL modules' calls, which were never inlined, adds about 5.4% more, but
only in a build trained on that source: with `main`'s profile the same source is 3.4% *slower* than `main`. The full
stack, trained, is +7.9% and +8.2% over `main` on the benchmark tour in two separate sets of rounds, with identical
guest checkpoints.

## How it was measured

- **Builds.** All in the Linux CI container (`--ci-container`, Clang 18, `-march=x86-64-v3`, default switches,
  `--portable`) from `main` `211abfd`, on an i5-12600KF (Arch). "Trained" means a normal build with its own local
  training. "With `main`'s profile" means the source was rebuilt with `--host-only` in the folder of a trained `main`
  build, which keeps that folder's profile whatever source has changed.
- **Profile match.** Checked rather than assumed: sample chunks were recompiled with `-Wprofile-instr-out-of-date`
  back on (the builder passes `-Wno-profile-instr-out-of-date`). The changed builds report 1 or 2 mismatched
  functions of 45 to 93 per chunk (the rewritten helpers), so every other function keeps its counts.
- **The benchmark tour.** `scripts/bench_tour.py` from #459 (with #450's `--setup-state`), headless, on an i5-6500
  (Debian 13, all four cores): Outset, Windfall, Dragon Roost Cavern, Forest Haven and the sea by the Fortress,
  1,800 retraces each with the first 300 skipped. One setup state, made once from a copy of a card, is loaded by
  every run, so every build measures the same guest state. Three rounds unless noted, with the order of the builds
  rotated each round. Each run took about 80 seconds.
- **Three kept states** (Outset, the bird, Tower of the Gods by boat; 2,400 to 2,800 retraces, headless, unpaced,
  `perf stat` instruction counts) for the first comparisons, before the tour was used.
- **Rendered** runs on four E-cores of the i5-12600KF (`taskset -c 12-15`), RTX 5070 Ti, Vulkan, unpaced, Smooth
  Motion off.

## 1. #480 at a fixed profile

A 2×2 of source and profile from `main` and #480 at `7d6a30d` (RecompCore `47a5229`). Kept states, mean over the
three, headless:

| Comparison | i5-6500 | E-cores |
| --- | ---: | ---: |
| #480's source at `main`'s profile | +1.4% (9/9 pairs) | +1.1% (9/9) |
| #480's source at #480's profile | +2.2% (9/9) | +2.2% (9/9) |
| `main` with #480's profile instead of its own | −0.9% | −0.9% |
| #480 with `main`'s profile instead of its own | −0.1% | +0.2% |
| Each with its own training | +1.3% | +1.3% |

The gain does not depend on retraining. #480's profile mostly costs `main`, so the source-at-#480's-profile figure
overstates it. Instructions drop 1.8 to 3.3%. Rendered on the E-cores, each with its own training: +1.4% (8/9). On the
tour, at `main`'s profile: **+1.6%**, every stop. Posted on #480, with the plan section in irregularthanis/bluewake#1.

## 2. Direct frame writes

Once `bw_inline_gpr_memory_ready()` has proven the frame plain MEM1 with no journal, `bw_inline_gpr_frame()` returns
its bytes and, for a save, clears a reservation on any granule the frame covers once. The generated code then uses
`write_be32`/`read_be32` at fixed offsets instead of 18 `mem_write32`/`mem_read32` calls. Each of those rechecks the
alias flag, the bounds, the reservation and the journal, and the compiler cannot merge those checks across the stores
because each byte store may alias them. `tests/inline_gpr_memory_test.c` checks the direct path against the helpers
for every first register, both stack forms and a reservation on every word in both forms. It passes, and a copy with
the reservation range cut short fails it.

At `main`'s profile, on top of #480:

| Where | Change |
| --- | ---: |
| Kept states, i5-6500 | +2.2% (9/9), instructions −0.7 to −1.2% more |
| Kept states, rendered, E-cores | +0.6% (9/9) |
| Benchmark tour, i5-6500 | **+1.0%**, every stop (+2.6% over `main`) |

The module is slightly smaller than `main`'s (370.9 MB of code against 372.6).

## 3. What the boundary census found

`BLUEWAKE_BOUNDARY_CENSUS_BY_ADDRESS` over the three kept states, with #480 and the direct writes.

**Caveat:** the census turns on `g_diagnostics_need_full`, which takes the full edge service and so turns off the
native actor search (`host_actor_search_native`). Its three addresses (`0x80245640`, `0x80245664`, `0x80040068`,
about 35% of boundaries in the census) are a census artefact. Ordinary runs log `[actor-search-native]` with about
1.6 million runs and 183 million nodes; census runs log none.

Of the rest:

- **`_savegpr`/`_restgpr` were still about 8.6% of boundaries** (`0x80328F34` to `0x80328F8C`). Two reasons:
  - **The REL modules' calls were never inlined.** They call through the mirror (`bl 0xC0328Fxx`), and the
    generator's call pattern only matched `bl 0x80328Fxx`. That is about 9,800 call sites, none inlined. The direct
    calls already treat them by their 0x8 form.
  - **2,610 calls in `main.dol` were skipped because their entry is "watched".** `0x80328F84` (`_restgpr_27`) is
    named for the GroundCross check, which only looks at returns to `0x80246A04`. `0x80328F40` (`_savegpr_29`) is
    named in a run-queue trace, also tied to one return address. Those returns are watched too, so excluding every
    other caller of the two entries was not needed.
- **`strcmp` from the actor search by name** (`0x8032DB44` and its call at `0x80041574`): about 6% of boundaries,
  17.6% at Outset. `native_search.c` covers it, behind `--native-entries`, which is off: on October 2 the natives
  measured about 1% of the game thread together (on Elliott's module), each must be certified against the BlueWake
  translation (#179, #361), and generation is currently blocked by lean deadlines' `_ato` forms (#451). Counted in
  boundaries, the natives' targets (`strcmp`, `ChkGrpThrough` at `0x800A9684` at 1.3%, `ChkSameActorPid` at
  `0x8024734C` at 0.5%) are a larger share than that 1% suggests.

## 4. Inlining the REL modules' calls: lost, then won

The generator now matches `bl 0xC0328Fxx` and checks the entry by its 0x8 form. `RETURN_KEYED` lets every caller
of `0x80328F84` and `0x80328F40` run inline except the ones whose return is watched (`0x80246A04` for the first;
`0x802B09C4` and `0x802B4100` for the second). A test fails if the host ever names either entry without one of
those returns, so a later hook that ignores `lr` cannot be skipped silently; it found the second return of
`0x80328F40`. Inline sites in the module
source went from 11,648 to 28,590, and 496 REL chunks now have them (none before).

| Build | Module code | Tour mean | vs `main` |
| --- | ---: | ---: | ---: |
| `main` | 372.6 MB | 53.99 | — |
| #480 + direct writes, `main`'s profile | 370.9 MB | 55.28 | +2.4% |
| + REL inlining, **`main`'s profile**\* | **397.2 MB** | 52.07 | **−3.4%** (−5.9% against the line above) |
| + REL inlining, **its own training** | **374.3 MB** | 58.31 | **+7.9%** |

\* From the first set of tour rounds, where `main` was 53.92 and #480 + direct writes 55.33; the other rows are from
the second set. Both sets loaded the same setup state.

Per stop, the trained build against `main` (three rounds each, game frames a second):

| Stop | `main` | Full stack, trained | Change |
| --- | ---: | ---: | ---: |
| Outset | 53.56 | 57.51 | +7.4% |
| Windfall | 46.12 | 49.86 | +8.1% |
| Dragon Roost Cavern | 66.05 | 72.59 | +9.9% |
| Forest Haven | 47.97 | 51.51 | +7.4% |
| Sea by the Fortress | 56.26 | 60.07 | +6.8% |

A second set of three rounds, later the same night, gave +8.2% (53.93 to 58.37). Guest checkpoints were identical
across every build in every run.

**Why the same source lost with `main`'s profile:** not because the profile stopped matching (the check above found 1
or 2 mismatched functions per chunk), but because of size. With `main`'s profile the new code in the REL chunks was
compiled at full size and the module grew 7%. The October finding was that a module only 4% bigger costs 2 to 3% on
small-cache cores, and the i5-6500 is one. Trained on its own source, the compiler optimized the cold sites for size,
and the module stayed at `main`'s size.

## 5. A shared helper instead: no better

To make the REL sites smaller without relying on training, each REL and return-keyed site called one out-of-line
`bw_gpr_run()` per source file instead of carrying its own stores (the main executable's sites kept the inline form).

| Build | Module code | Tour | Against the full-inline form |
| --- | ---: | ---: | ---: |
| Helper, `main`'s profile | 394.1 MB | 51.75 (2 rounds) | −0.5% (against full inline, `main`'s profile) |
| Helper, its own training | 372.0 MB | 58.01 | **−0.6%** (against full inline, trained), slower at every stop |

So the size came from the profile, not from the inlined stores, and the extra call costs a little. The full-inline
form stays.

## 6. The full stack as real AppImages, rendered: #472's runtime is +3.6%

The trained full-stack module, packaged twice with `scripts/linux/make_appimage.sh` from apps built in the CI
container at the same commit: today's AppImage runtime (LLVM libc++, Dawn compiled from source, 237 MB) and #472's
(static libstdc++, the prebuilt Dawn package, 182 MB). Both pass `check_appimage_abi.py` (14 and 12 ELF files,
`GLIBC_2.38` at most), and both carry the same module byte for byte. The tour, rendered, on the four E-cores, three
rounds with the order rotated. A local copy of `bench_tour.py` also set `BLUEWAKE_DATA_DIR` to its scratch folder and
pointed `BLUEWAKE_DISC`, `BLUEWAKE_DOL` and `BLUEWAKE_RELS_DIR` at a prepared game folder: an AppImage carries no game
files, and without that it opens its setup window and writes into the player's own data folder.

| Stop | Today's AppImage | #472's AppImage | Change |
| --- | ---: | ---: | ---: |
| Outset | 45.90 | 47.77 | +4.1% |
| Windfall | 40.00 | 41.06 | +2.7% |
| Dragon Roost Cavern | 58.17 | 60.73 | +4.4% |
| Forest Haven | 40.61 | 42.02 | +3.5% |
| Sea by the Fortress | 47.46 | 48.90 | +3.0% |
| Mean | 46.43 | 48.10 | **+3.6%** (faster at every stop in 3/3 rounds) |

Against `main`, rendered the same way (one pass of `main`'s folder app, which uses libstdc++ and the prebuilt Dawn
like #472's AppImage; checkpoints identical to the full stack's):

| Stop | `main` | Full stack, #472's AppImage | Change | Full stack, today's AppImage |
| --- | ---: | ---: | ---: | ---: |
| Outset | 44.85 | 47.77 | +6.5% | 45.90 |
| Windfall | 38.30 | 41.06 | +7.2% | 40.00 |
| Dragon Roost Cavern | 55.83 | 60.73 | +8.8% | 58.17 |
| Forest Haven | 39.47 | 42.02 | +6.5% | 40.61 |
| Sea by the Fortress | 45.70 | 48.90 | +7.0% | 47.46 |
| Mean | 44.83 | 48.10 | **+7.3%** | 46.43 (+3.6%) |

So the game-code gain holds rendered (+7.3%, against +7.9 and +8.2% headless), and the libc++ runtime takes back about
3.5 points of it. That is in line with the folder-app measurements on #472 (+2.5 to +3%), now on the real packages. One rendered run
(the first of the pass, today's AppImage) had checkpoints that differ from the other five in `mem1` only, at every
checkpoint, with the CPU state identical throughout: memory the CPU's state never depends on, most likely frames
copied from the GPU into guest RAM while the driver's shader cache was cold for that binary. Every other rendered run,
and every headless run, matched.

## Builds and branches

- `pdale-boop/bluewake` `exp/gpr-direct`: #480 at `7d6a30d`, then `043495d` (direct frame writes) and `52583a4` (REL
  and return-keyed inlining). This is the full stack measured above.
- `pdale-boop/bluewake` `exp/gpr-helper`: `4345be3`, the shared-helper experiment on top of `52583a4`. Kept for the
  record, not proposed.

## Not done yet

- `main` rendered for three rounds (§6 has one pass), and `main` as today's libc++ AppImage.
- A Steam Deck or another AMD CPU, Windows, and a Mac. All the numbers here are Intel x86-64.
- A second independent training of the full stack, to put a number on profile luck. It moved results by about ±1% in
  §1, small against +8%.
- Hand play. The checkpoints match, but nobody has played these builds.
