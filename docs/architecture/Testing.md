# BlueWake test architecture

## Contents

- [Purpose](#purpose)
- [End-to-end view](#end-to-end-view)
- [Evidence levels](#evidence-levels)
- [Test families](#test-families)
- [Registration and execution](#registration-and-execution)
- [Platform entry points](#platform-entry-points)
- [Continuous integration](#continuous-integration)
- [Fixtures and test data](#fixtures-and-test-data)
- [Results and failure evidence](#results-and-failure-evidence)
- [Running tests locally](#running-tests-locally)
- [Adding or changing a test](#adding-or-changing-a-test)
- [Private and hardware validation](#private-and-hardware-validation)
- [Current extension: game-thread integrity](#current-extension-game-thread-integrity)
- [Source map](#source-map)

Architecture path: [Index](README.md) → [Overview](Overview.md) → **Testing**

## Purpose

BlueWake tests code at several boundaries: repository policy, build scripts,
generated source, the native host, GXRuntime and Aurora integration, packaged
applications, translated game modules, and player-visible behavior. No single
runner owns all of this coverage. Python scripts, standalone compiled tests,
CTest graphs, platform builders, GitHub Actions, and private hardware runs each
cover a different part of the system.

This chapter explains how those parts connect from a source change to evidence
that can support a merge. It describes the current framework on `main`; planned
or draft additions are labeled separately.

The central distinction is between **public source-only evidence** and
**private game-backed evidence**:

- public tests use repository source and generated synthetic fixtures, so they
  can run in CI without a disc, extracted game code, save, or console key;
- private tests may use a contributor's own translated module, disc, state, or
  memory card, and their artifacts remain local; and
- hardware checks establish behavior that a source-only process cannot prove,
  such as controller feel, renderer output, device packaging, or sustained
  Steam Deck performance.

Passing one layer does not imply that a later layer passed. A successful
compile is not a test execution, a source-only test is not a gameplay run, and
a CI result is not a hardware qualification.

## End-to-end view

The usual path starts with the changed component and expands only as far as the
risk requires.

```mermaid
flowchart TD
    Change["Source or<br>build change"]
    Focused["Focused<br>test"]
    Register["Platform test<br>registration"]
    Local["Local build<br>and run"]
    Audit["Repository and<br>Python checks"]
    CI["Linux, Windows,<br>audit CI"]
    Private["Private module<br>or gameplay"]
    Hardware["Device and<br>release checks"]
    Evidence["Recorded<br>evidence"]

    Change --> Focused --> Register --> Local
    Change --> Audit
    Local --> CI
    Audit --> CI
    CI --> Private
    Private --> Hardware
    CI --> Evidence
    Private --> Evidence
    Hardware --> Evidence
```

Not every change travels through every node. A documentation edit may need
only the repository audit and link review. A host service change normally needs
focused CTest coverage on Linux and Windows. A renderer or timing change needs
source-only checks first, followed by representative gameplay and hardware
evidence. A release additionally has its own artifact gate.

The test system consumes the same pinned public runtime described in
[Build](Build.md#2-fetch). Linux and Windows CI fetch the
RecompCore revision from `config/dependencies.lock.json`; they do not fetch or
construct a personal game module.

## Evidence levels

The layers below answer progressively broader questions.

| Level | Question answered | Typical runner | Public CI |
| --- | --- | --- | --- |
| Repository safety | Is the tree structurally safe and free of prohibited tracked artifacts or unresolved merges? | `scripts/audit_repo.sh` | Yes |
| Static/source contract | Do scripts, generated text, manifests, and build rules retain an expected contract? | Direct Python tests | Yes |
| Component behavior | Does a host helper, service, parser, state machine, or native routine behave correctly with synthetic data? | Compiled C/C++/Objective-C tests under CTest | Yes |
| Integration behavior | Do components compile, link, and cooperate through the Linux, Windows, or host build graph? | Platform CMake entry point plus CTest | Yes |
| Packaging behavior | Can a disc-free fixture be assembled, audited, and launched far enough to check its container contract? | Builder/package scripts in CI | Yes, without playable game data |
| Generated-module behavior | Does the locally generated composite module satisfy ABI and guest-behavior contracts? | Conditional or explicit local test | No module in public CI |
| Gameplay behavior | Does a repeatable route preserve guest checkpoints and player-visible behavior? | Local headless/rendered app and benchmark tooling | No private inputs in CI |
| Hardware/release behavior | Does the result work on the target device and meet packaging, performance, and release gates? | Maintainer hardware and release tools | Only public-safe checks run in CI |

Evidence is cumulative, not interchangeable. For example, a synthetic renderer
fixture can prove a blend equation but cannot prove that a complete scene has
no visual regression. Conversely, a scene that looks correct does not exercise
all malformed inputs or concurrency boundaries that a focused test can cover.

## Test families

### Repository and policy checks

`scripts/audit_repo.sh` is the common safety baseline. It checks the tracked
tree for private/generated artifact types and directories, validates the
dependency lock, requires core planning/status files, and rejects unresolved
merge markers. It is intentionally fast and does not compile the project.

The attribution workflow separately checks commit authors and co-authors. A
repository-audit pass does not imply that attribution passed, and neither
implies that compiled tests ran.

### Python source-contract tests

Python files under `tests/` exercise build and tooling contracts directly.
They commonly create temporary synthetic trees, invoke a script or import its
logic, and compare generated output, manifests, commands, or failure behavior.

Representative groups include:

| Area | Examples | What they protect |
| --- | --- | --- |
| Composite preparation | `test_composite.py`, `test_prepare.py`, `test_return_ranges.py` | Generated-source composition, deterministic preparation, and address/range rules |
| Native preparation | `native_*_source_test.py`, `test_direct_calls.py`, `test_inline_gpr.py` | Certified source transformations and host boundaries |
| Timing and checkpoints | `test_guest_clock.py`, `test_cycle_invariance.py`, `test_guest_checkpoints.py` | Clock contracts and completeness of comparison evidence |
| Builder behavior | `test_mac_package.py`, `test_windows_training.py`, `test_linux_ci_container.py` | Platform command construction, cache selection, interrupted builds, and packaging inputs |
| Benchmark tooling | `test_bench_tour.py`, `test_sample_owners.py`, `test_one_game_guard.py` | Synthetic logs, ownership, process isolation, and complete measurement grids |
| Import and storage | `wwhd_disc_fixture.py`, `wwhd_disc_import_test.py`, `wwhd_staging_recovery_test.py` | Generated disc structures, decoding, staging, cancellation, and recovery |

Most of these tests use Python's standard assertion or `unittest` behavior and
are invoked as scripts, for example `python3 tests/test_bench_tour.py`. The
audit workflow lists the public Python set explicitly rather than discovering
every `test_*.py`; some scripts are helpers, private comparison tools, or need a
compiled executable.

### Compiled component tests

C, C++, Objective-C, and Objective-C++ files under `tests/` exercise production
headers and sources with synthetic inputs. CMake creates one executable per
contract or closely related group, links only the dependencies it needs, and
registers it with CTest through `add_test`.

The compiled suite covers, among other areas:

- CPU scheduling, cycles, interrupt sources, callbacks, and ABI boundaries;
- guest memory aliases, gather/inline-memory paths, and dispatch loops;
- audio, ARAM DMA, cards, save states, atomic files, and shutdown;
- input, controller mapping, haptics, menus, camera, and motion;
- native math/vector/skinning/J3D guard behavior;
- renderer shared state, worker identity, frame interpolation, and pipeline
  shutdown; and
- HD texture/disc import, cancellation, output staging, and recovery.

Tests often compile a production `.c` file directly beside the harness. This
keeps the exercised logic identical to the application while avoiding the full
host or renderer when those dependencies are irrelevant. Other tests link the
real `gxruntime`, Aurora, or gxcore targets because the integration boundary is
the behavior under test.

### Generated and conditional tests

Some targets can compile publicly but can run only when a local generated
artifact exists. In `runtime/host/CMakeLists.txt`, the generated scheduler,
ARAM-stream, and DVD-callback contracts are registered only when the local
composite module path exists. This distinction matters:

- a target declared by CMake may not be a registered CTest;
- a target that built successfully may not have run; and
- the absence of a private module is an expected public-CI condition, not
  evidence that the generated contract passed.

Other manual targets use `EXCLUDE_FROM_ALL`. They must be named explicitly in
`cmake --build --target ...` and run with their required local arguments.
Native differential oracles and the fast-block comparison follow this pattern.

### Runtime and renderer tests

BlueWake reuses selected tests from the pinned RecompCore checkout when the
actual linked runtime or renderer behavior is the contract. The host CMake
graph can build Aurora/gxcore fixtures for frame interpolation, audio sink,
pipeline shutdown, frontend replay, texture encoding, and pixel-level GPU
oracles.

Not every renderer target is registered in ordinary CTest. Several pixel
oracles are deliberately manual because they require an available graphics
backend or are intended for focused visual/readback investigation. The CMake
target definition, CTest registration, and CI target list together determine
whether a test is automatic.

### Packaging and process tests

Some failures appear only across process or filesystem boundaries. These tests
use real child processes, temporary output directories, generated fixtures,
and bounded timeouts to cover atomic replacement, killed-child recovery,
launcher behavior, packaging, and ABI checks.

Linux CI builds a non-playable AppImage fixture with an empty synthetic module
and placeholder DSP files. It checks packaging, the glibc ABI ceiling, `--help`,
and zsync creation, then deliberately does not upload the fixture. That proves
the packaging path without publishing game data or claiming gameplay success.

## Registration and execution

CTest is the main coordinator for compiled tests, but CMake registration is
distributed across platform entry points and reusable `.cmake` fragments.

```mermaid
flowchart TD
    Tests["Tests and<br>fixtures"]
    Shared["Shared CMake<br>fragments"]
    Host["runtime/host<br>CMake"]
    Linux["linux<br>CMake"]
    Windows["windows<br>CMake"]
    Targets["Test<br>executables"]
    CTest["CTest<br>registry"]
    Logs["Console and<br>LastTest.log"]

    Tests --> Shared
    Tests --> Host
    Tests --> Linux
    Tests --> Windows
    Shared --> Host
    Shared --> Linux
    Shared --> Windows
    Host --> Targets
    Linux --> Targets
    Windows --> Targets
    Targets --> CTest --> Logs
```

The main registration styles are:

| Style | Location | Use |
| --- | --- | --- |
| Direct target and `add_test` | Platform `CMakeLists.txt` | Platform-specific linkage or a small single-use test |
| Shared CMake fragment | `cmake/*_test.cmake` | The same target definition is included by multiple entry points |
| Loop-generated variants | Platform CMake | One harness runs against compile-time modes such as plain/global guest memory |
| Repeated CTest command | `add_test` plus properties | One binary runs with different arguments or environments, such as haptics modes |
| CTest fixture | `FIXTURES_SETUP` and dependent tests | A generated artifact is created before consumers run |
| Conditional registration | `if(EXISTS ...)` or target availability | A local module or optional runtime component is required |
| Manual target | `EXCLUDE_FROM_ALL`, no `add_test` | Private input, GPU oracle, or explicit developer workflow |

CTest properties carry operational contracts such as environment variables,
timeouts, labels, and fixture dependencies. A new test should encode these in
CMake rather than rely on a developer remembering an unstated invocation.

`ctest --test-dir BUILD --show-only` is the authoritative list for one
configured build. Reading `tests/` alone overstates coverage because helpers and
manual targets are present; reading only CMake understates direct Python and
shell checks.

## Platform entry points

### Host CMake graph

`runtime/host/CMakeLists.txt` is the broad native-host test graph. It uses
`include(CTest)`, builds many source-only component tests, incorporates shared
CMake fragments, and conditionally registers tests that need a local composite
module or optional DSP adapter.

The macOS helper `scripts/build_macos_dsp_host.sh` builds the pinned donor DSP,
configures the host with the DSP adapter and ThinLTO, builds the host graph, and
runs CTest serially while excluding `_NOT_BUILT` placeholders.

### Linux graph

`linux/CMakeLists.txt` keeps regression targets behind
`BLUEWAKE_LINUX_REGRESSION_TESTS=ON`. The option enables CTest, builds focused
host-service tests through the Linux application dependencies, and includes
shared tests for state saving, DVD completion, cache fallback, and HD import.

Linux CI configures this graph with the pinned runtime inside the repository's
container environment, names the targets it expects to compile, verifies that
no `gGZLE01_recomp*` personal module appeared, and then runs tests whose names
begin with `bluewake_`.

### Windows graph

`windows/CMakeLists.txt` uses
`BLUEWAKE_WINDOWS_REGRESSION_TESTS=ON` for source-only regression targets. The
Windows graph adds compatibility includes and forced-include flags where the
same portable harness needs Win32 shims, and it links those targets through the
Windows host/runtime configuration.

Windows CI fetches the same pinned public runtime, runs Windows-specific Python
contracts, configures with Visual Studio's Clang/LLD toolchain, explicitly
builds the host and expected tests, rejects any unexpected personal module,
and runs the `bluewake_` CTest set.

### Apple application and device paths

The host CMake graph supplies native macOS component coverage, while Apple
application packaging and launcher contracts are also exercised by direct
Python and Objective-C/Objective-C++ tests in the audit workflow. Simulator,
signed-device, PadMint, controller, and app-only packaging checks remain
separate workflows or maintainer commands where SDK, signing, or hardware is
required.

An Apple package building successfully does not imply that it launched on a
device, imported a private module, rendered a scene, or passed controller and
persistence checks. Those results must be stated independently.

## Continuous integration

Four GitHub Actions workflows form the public pull-request gate.

```mermaid
flowchart LR
    PR["Pull request"]
    Repo["Repository<br>audit"]
    Linux["Linux host<br>and AppImage"]
    Windows["Windows<br>source-only host"]
    Attribution["Attribution"]
    Merge["Reviewable<br>evidence"]

    PR --> Repo --> Merge
    PR --> Linux --> Merge
    PR --> Windows --> Merge
    PR --> Attribution --> Merge
```

| Workflow | Environment | Principal work | Deliberate limit |
| --- | --- | --- | --- |
| Repository Audit | `macos-latest` | Safety audit, dependency-lock check, direct Python contracts, focused sanitizer builds, Objective-C++ import operation | Does not build the complete host |
| Linux host and AppImage | Ubuntu 24.04 container | Fetch pinned runtime, configure/build source-only host tests, run CTest, create and audit disc-free AppImage fixture | Fixture is non-playable and not uploaded |
| Windows source-only host | Windows Server 2025 | Fetch pinned runtime, run Windows Python contracts, compile host/test targets with Clang/LLD, run CTest | No disc or personal module; no artifact upload |
| Attribution | Ubuntu | Check commit and co-author identities over the PR range | Does not assess code behavior |

The Linux container image is cached, but the commands inside it remain the
test contract. CI explicitly names build targets before running CTest so that a
registered test cannot appear to pass merely because its executable was never
built. Windows follows the same principle with an explicit target list.

CI logs are the public evidence for the exact pull-request commit. They should
be read together: a green audit cannot compensate for a failed Windows build,
and a green Linux CTest cannot establish attribution or hardware behavior.

## Fixtures and test data

Public fixtures are generated, bounded, and disposable. Common patterns are:

- arrays, CPU structures, memory images, logs, manifests, and filesystem trees
  constructed entirely by a harness;
- toy disc/container structures with synthetic keys and payloads;
- temporary directories created by Python or CTest and removed by the test;
- empty or stub modules used only to exercise packaging and loader boundaries;
  and
- source snippets that resemble generated output structurally without
  containing translated game code.

The HD disc tests use a CTest fixture: a Python setup test creates toy WUD/WUX
inputs under the ignored build tree, and native/Python consumers use those
outputs. The fixture is synthetic; it is not a redacted game dump.

Private inputs follow a different policy. Disc images, extracted DOL/REL files,
translated modules, saves, memory cards, keys, profiles, and rendered assets are
never committed or uploaded by ordinary test jobs. Tests that accept such an
input should keep the path explicit, avoid copying it into public artifacts,
and report only safe derived results.

`tests/coverage/catalog.json` records public-safe coverage claims and provenance
summaries. It is required by the repository audit. The catalog is evidence
metadata, not a dynamic test runner and not a substitute for the referenced
test result.

## Results and failure evidence

Each runner has a different result surface:

| Runner | Success signal | Failure evidence |
| --- | --- | --- |
| Repository audit | `AUDIT PASS` and exit 0 | Named prohibited path, missing file, invalid lock, or merge-marker list |
| Direct Python test | Exit 0 | Assertion traceback, subprocess output, or explicit contract error |
| Build command | Requested targets complete | Compiler/linker diagnostic and failed target |
| CTest | All selected registered tests pass | Failing command, captured output, timeout, and `Testing/Temporary/LastTest.log` |
| Packaging smoke | Audit and launch probes exit 0 | Package script, ABI report, launch output, or missing expected file |
| Private/gameplay run | Complete expected route and comparison | Retained local logs, checkpoint differences, hashes, and platform context |

Keep configuration, build, and execution results separate. If configuration
fails, no test ran. If a target was excluded or conditional, a shorter CTest
count may indicate missing coverage rather than success. Use `ctest --show-only`
to record what the configured build actually registered.

A useful test report states:

1. the commit and working-tree state;
2. platform, device, compiler, and relevant dependency revision;
3. the exact configure, build, and execution commands;
4. test counts and any selected/excluded expression;
5. whether private fixtures, a renderer, or real hardware were involved; and
6. failures, warnings, skips, unavailable capabilities, and retained log paths.

## Running tests locally

The correct command depends on the changed boundary. These are entry points,
not a promise that every test can run on every host.

### Fast repository and Python checks

```bash
scripts/audit_repo.sh
python3 tests/test_composite.py
python3 tests/test_bench_tour.py
```

Run the audit for every change. Select Python contracts that own the changed
script or generated format. The full public list is explicit in
`.github/workflows/audit.yml`.

### Native host tests

With the pinned RecompCore checkout present:

```bash
cmake -S runtime/host -B build/runtime-host -DCMAKE_BUILD_TYPE=Debug
cmake --build build/runtime-host --parallel
ctest --test-dir build/runtime-host --show-only
ctest --test-dir build/runtime-host --output-on-failure
```

Configuration describes available targets; building creates them; `--show-only`
reveals the registered set; the final command executes it. Optional components
and local generated modules change the registration count.

### Linux source-only integration

The normal Linux builder fetches `ref/recompcore`; see
[Linux build behavior](../LINUX.md#build-behavior). Configure the regression
graph and build only the affected targets when iterating:

```bash
cmake -S linux -B build/linux-host \
  -DBLUEWAKE_LINUX_REGRESSION_TESTS=ON
cmake --build build/linux-host --parallel --target TARGET_NAME
ctest --test-dir build/linux-host --show-only
ctest --test-dir build/linux-host --output-on-failure -R '^bluewake_'
```

For parity with CI—including compiler, container, dependency providers, and
the explicit target set—use the commands in `.github/workflows/linux-host.yml`.

### Windows source-only integration

Windows uses the analogous opt-in graph:

```powershell
cmake -S windows -B build/windows-host -G Ninja `
  -DBLUEWAKE_WINDOWS_REGRESSION_TESTS=ON
cmake --build build/windows-host --parallel --target TARGET_NAME
ctest --test-dir build/windows-host --show-only
ctest --test-dir build/windows-host --output-on-failure -R '^bluewake_'
```

The CI workflow supplies its exact Visual Studio environment, Clang/LLD flags,
runtime checkout, Python fixture environment, and complete target list. A local
developer may need the same prerequisites before these abbreviated commands
configure successfully.

### Focused and verbose execution

Use CTest names or labels to shorten iteration without weakening final scope:

```bash
ctest --test-dir BUILD --show-only -R 'PATTERN'
ctest --test-dir BUILD --output-on-failure -R 'PATTERN'
ctest --test-dir BUILD --verbose -R 'ONE_TEST_NAME'
```

The complete captured log is under `BUILD/Testing/Temporary/LastTest.log`.
Delete or use a new build directory when changed options, optional dependencies,
or stale conditional registration make the configured graph ambiguous.

## Adding or changing a test

Start from the production boundary, not from a preferred test language.

1. Identify the owning source, expected behavior, failure mode, and platforms.
2. Choose the lowest layer that can reproduce the defect with public synthetic
   data.
3. Put reusable fixtures or comparisons in `tests/`; compile production source
   directly or link its real target rather than copying its implementation.
4. Register compiled tests in every relevant platform graph, using a shared
   `.cmake` fragment when definitions should remain identical.
5. Encode arguments, environment, timeouts, labels, and fixture dependencies in
   CTest properties.
6. Keep private or graphics-dependent targets explicit and document why they
   are manual or conditional.
7. Add the target to the relevant CI build list as well as CTest registration.
   Registration alone does not guarantee that CI builds the executable.
8. Run the focused test, the platform CTest subset, repository audit, and the
   other platform's CI when shared code is involved.
9. Record exactly what ran and which gameplay or hardware checks remain.

Good source-only tests are deterministic and bounded. They use explicit
barriers or conditions for concurrency, temporary owned paths for filesystem
work, stable seeded inputs where randomness adds coverage, and timeouts for
process or thread failure. Sleep duration alone should not be the correctness
condition.

When a regression spans multiple layers, keep the assertions close to the
failure. A Python source check may protect generated syntax, a C component test
may protect the runtime contract, and a gameplay checkpoint may protect the
end-to-end effect. One oversized test is usually less diagnostic than these
linked layers.

## Private and hardware validation

Several important tests cannot run in public CI:

- native differential oracles compare a contributor's own translated module
  with guarded native replacements;
- generated scheduler/ARAM/DVD contracts consume a local composite module;
- benchmark tours and checkpoint comparisons consume local states, modules,
  or gameplay logs;
- renderer pixel or visual checks may require a real GPU/backend;
- controller, haptics, signing, installation, persistence, thermal, and
  performance checks require the corresponding device; and
- save/load and long soak qualification use copied private player data.

These are not reasons to weaken CI. Public synthetic coverage should establish
the narrow invariant first; private runs then establish that real generated
code and gameplay reach it. Keep private artifacts outside git and CI, retain
local failure evidence, and publish only safe summaries.

Performance runs follow the separate
[performance methodology](../performance/Overview.md). They require correctness,
complete routes, comparable settings, and path-activation evidence before a
timing difference is treated as an optimization result.

## Current extension: game-thread integrity

Draft [PR #399](https://github.com/chrissotraidis/bluewake/pull/399) applies the
existing architecture to one focused gap: the native worker pool. It proposes a
renderer-free target that compiles the real pool, runs one-time worker settings
in fresh CTest processes, and checks partition, publication, sentinel, stress,
and activation contracts. It also shares native-math guard/oracle registration
between host and Linux entry points.

That work is one component suite within the broader framework described here.
Its planning documents remain unmerged in
[PR #397](https://github.com/chrissotraidis/bluewake/pull/397):

- [Product requirements](https://github.com/irregularthanis/bluewake/blob/docs/gamethread-integtests/docs/planning/2026-10-18-gamethread-integtests/PRD.md)
- [Technical plan](https://github.com/irregularthanis/bluewake/blob/docs/gamethread-integtests/docs/planning/2026-10-18-gamethread-integtests/TECH_PLAN.md)
- [Milestones](https://github.com/irregularthanis/bluewake/blob/docs/gamethread-integtests/docs/planning/2026-10-18-gamethread-integtests/PROGRESS.md)

Later milestones add private oracle boundaries, lifecycle fault injection,
sanitizer lanes, gameplay qualification, topology-aware load, and hardware
soaks. They should extend the appropriate layers rather than turn one CTest
binary into the entire qualification system.

## Source map

| Responsibility | Source of truth |
| --- | --- |
| Repository safety gate | [`scripts/audit_repo.sh`](../../scripts/audit_repo.sh) |
| Public audit/Python workflow | [`.github/workflows/audit.yml`](../../.github/workflows/audit.yml) |
| Linux build, CTest, and package workflow | [`.github/workflows/linux-host.yml`](../../.github/workflows/linux-host.yml) |
| Windows build and CTest workflow | [`.github/workflows/windows-host.yml`](../../.github/workflows/windows-host.yml) |
| Commit attribution workflow | [`.github/workflows/attribution.yml`](../../.github/workflows/attribution.yml) |
| Broad native host registration | [`runtime/host/CMakeLists.txt`](../../runtime/host/CMakeLists.txt) |
| Linux source-only registration | [`linux/CMakeLists.txt`](../../linux/CMakeLists.txt) |
| Windows source-only registration | [`windows/CMakeLists.txt`](../../windows/CMakeLists.txt) |
| Reusable CTest fragments | [`cmake/`](../../cmake) |
| Test sources and fixture helpers | [`tests/`](../../tests) |
| Public-safe coverage catalog | [`tests/coverage/catalog.json`](../../tests/coverage/catalog.json) |
| macOS DSP/host build and CTest entry | [`scripts/build_macos_dsp_host.sh`](../../scripts/build_macos_dsp_host.sh) |
| Performance validation methodology | [`docs/performance/Overview.md`](../performance/Overview.md) |

For the systems these tests protect, continue to [Build](Build.md),
[Runtime](Runtime.md), [Host](Host.md), [Game module](GameModule.md),
[Guest state](GuestState.md), [Services](Services.md), and
[Graphics](Graphics.md).
