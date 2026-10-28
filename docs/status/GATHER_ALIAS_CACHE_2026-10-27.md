# The gather alias cache (#495): Steam Deck and Windows, October 27, 2026

A gather-pipe write first checks that no guest alias overlaps the FIFO window, which used to mean resolving the address
through `get_ram_ptr()` on every write. With the cache (`BLUEWAKE_GATHER_ALIAS_CACHE`, `cmake/composite/gather_pipe.h`),
whether an alias overlaps the window (0xCC008000 or its 0x8C008000 mirror, 32 bytes) is worked out again only when
RecompCore's `g_ppc_guest_alias_generation` moves. While nothing overlaps, the write skips the lookup; when something
does, the ordinary resolver still runs, so a registered alias keeps taking the write. Linux and Windows builds turn it
on by default, and `--no-gather-alias-cache` builds the same source without it.

## Steam Deck (irregularthanis)

From #495. Both builds share #480's foundation, Clang 18, `x86-64-v3`, the same optimizations and Game Mode, with
interpolation pacing off, and each had its own local training. Control `73ef48e`, candidate `8d8587b`.

Headless: ten runs a build of the five-scene tour, in interleaved candidate/control/control/candidate order. Every run
loaded all 5 scenes and gave all 31 checkpoints, matching across builds.

| Scene | Control | Candidate | Change |
| --- | ---: | ---: | ---: |
| Outset | 44.287 | 45.365 | +2.43% |
| Windfall | 46.711 | 48.058 | +2.88% |
| Dragon Roost Cavern | 63.448 | 65.255 | +2.85% |
| Forest Haven | 37.806 | 39.079 | +3.37% |
| Sea by the Fortress | 35.580 | 36.445 | +2.43% |

The per-run geometric mean of the medians is +2.84%. Rendered, matched 20-second `perf stat` captures at fixed Outset
camera views gave CPU time −0.72% (stable), +0.08% (slow) and −0.61% (worst), with instructions −1.76%, −0.26% and
−4.47%.

## Windows (pdale-boop)

i5-12600KF, RTX 5070 Ti, Direct3D 12, clang 22.1.3. Three builds:

- **cache:** #495 with the Windows builder turning the cache on, with its own training.
- **stack:** `d9424af`, the same source with the cache off, trained October 25.
- **0.9.0:** the release, given the disc's files.

`scripts/bench_tour.py`, rendered and unpaced, every run pinned to the four E-cores (CPUs 12-15), from one setup
state, three rounds in rotated order. Game frames a second, mean of the three rounds:

| Stop | 0.9.0 | stack | cache | cache vs stack | cache vs 0.9.0 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Outset | 39.26 | 41.47 | 42.35 | +2.1% | +7.9% |
| Windfall | 37.03 | 39.38 | 40.18 | +2.0% | +8.5% |
| Dragon Roost Cavern | 48.01 | 51.49 | 52.73 | +2.4% | +9.8% |
| Forest Haven | 34.52 | 36.87 | 37.66 | +2.2% | +9.1% |
| Sea by the Fortress | 40.58 | 42.62 | 43.19 | +1.4% | +6.4% |
| All five (geometric mean) | 39.63 | 42.09 | 42.94 | **+2.0%** | +8.3% |

- **The cache:** faster in every round (+3.0%, +0.8%, +2.3%) and at 14 of 15 stop-rounds. Separate trainings have
  moved results by about ±1% (`INLINE_GPR_FOLLOWUP_2026-10-25.md` §1), so this is more than profile luck, though not
  by a wide margin.
- **The stack:** +6.2% over 0.9.0, as the October 25 Windows tour found against a `main` build (+6.6%).
- **Checkpoints:** CPU, MEM2 and aliases matched across all nine runs. MEM1 matched in eight. The odd run was one of
  the first of the session, and in an earlier attempt it was a different build's with a different hash, so it isn't
  the cache: something written to MEM1 that the game doesn't read back varies now and then in rendered runs.

## The runtime the measurements used

Every measurement above was taken with RecompCore `47a5229`. `8d8587b` moved `config/dependencies.lock.json` to
RecompCore #45's `caeedd8` ("Track every guest alias registry mutation"), but the builders follow
`scripts/builder/profiles/bluewake.sh`, which still said `47a5229` until `0c95acb`.

In `47a5229`, adding an alias moved the generation only when the alias overlapped 0x80000000-0x90000000. So the cache
missed an alias added over the FIFO window itself, and `bluewake_gather_memory_cache_test` fails there at its
alias-precedence check. The Linux CI asked for that test, but `linux/CMakeLists.txt` didn't define it, so the job
stopped before running it; Windows didn't build the variant.

The game never hits this case:
- The host registers aliases only for the linked REL modules (their sections and BSS, and a save state restoring
  them).
- In the generated layout, all 2,316 of those sections lie between 0xC04000F4 and 0xC1F80954, over 160 MiB below the
  FIFO window.
- So the cached "nothing overlaps" was always right.

`caeedd8` moves the generation on every add, remove and clear. With it, on Windows, the three gather-memory variants,
the guest-memory bounds tests (`caeedd8`'s own generation checks) and the runtime test pass. Its only cost in play is
one extra counter step each time a REL module is linked, so the measurements carry over. A rebuild on `caeedd8`
hasn't been timed.

## Not done

- A second training of either build, to put a number on profile luck.
- A Mac. The Apple builder's `--combined-optimizations` list (`scripts/builder/module_optimizations.py`) has
  `GATHER_PIPE` but not `GATHER_ALIAS_CACHE`; adding it changes the Mac's measured configuration, so it needs its own
  check.
- The stage select's costliest untrained rooms, rendered with the GPU profiler, on the Deck.
