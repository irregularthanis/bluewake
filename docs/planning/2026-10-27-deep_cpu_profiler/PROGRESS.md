# PROGRESS — Deep CPU profiler

Status: Planned; measured prototype available on fork

[Product brief](PRD.md) · [Technical plan](TECH_PLAN.md)

## Milestones

### M0: Freeze attribution contract

Architecture: [runtime entities](../../architecture/Runtime.md#runtime-entities) and [performance domains](../../performance/Overview.md#performance-domains).

- [x] M0-T01: Inspect the existing Linux profiling workflow and architecture ownership boundaries.
- [x] M0-T02: Capture a rendered worst-angle Deck profile and record the initial domain/thread distribution.
- [ ] M0-T03: Confirm that the maintained-tool scope, taxonomy, JSON schema, and artifact names are accepted.

### M1: Implement parser and classifier (depends: M0)

Parallel with M2; owns `scripts/linux/perf_domains.py` and `tests/perf_domains_test.py`.

- [ ] M1-T01: Parse desktop one-line and SteamOS multiline callchain records, selecting one leaf per sample.
- [ ] M1-T02: Implement ordered symbol/DSO classification and terminal, JSON, and Markdown renderers.
- [ ] M1-T03: Add sample-accounting, format, classification, unknown, and empty-input regression cases.

### M2: Integrate workflow and documentation (depends: M0)

Parallel with M1; owns `scripts/linux/profile_deck.sh` and `docs/PROFILING.md`; consumes the frozen M1 CLI.

- [ ] M2-T01: Generate `domains.txt`, `domains.json`, and `domains.md` after a successful capture.
- [ ] M2-T02: Report missing tools, failed/non-finalized captures, and zero parsed samples clearly.
- [ ] M2-T03: Document commands, artifacts, interpretation limits, and private-data handling.

### M3: Validate integration (depends: M1, M2)

- [ ] M3-T01: Run source-only tests, syntax checks, diff checks, and repository audit.
- [ ] M3-T02: Generate reconciled reports from a real desktop capture.
- [ ] M3-T03: Run a source-identified fixed-scene Steam Deck capture and record aggregate evidence.

## Evidence ledger

| Task | Commit / artifact | Command / method | Environment / input | Result |
| --- | --- | --- | --- | --- |
| M0-T01 | Upstream [`a773185`](https://github.com/chrissotraidis/bluewake/commit/a7731853c197cc9763a86d62e731d65ca0b25556) | Inspect `profile_deck.sh`, profiling/performance docs, runtime architecture and issue #215 | Current upstream main | Existing workflow records process-wide callchains and flat symbols but has no architecture-domain report. |
| M0-T02 | Prototype [`d1bb41b`](https://github.com/irregularthanis/bluewake/commit/d1bb41b); private `perf.data`, JSON and Markdown | 20 s rendered capture at 99 Hz; post-process 3,195 leaf samples | Steam Deck LCD, Game Mode, fixed worst Outset angle | Whole process: translated 39.6%, GX/Aurora 15.3%, guest/dispatch 9.1%; game thread: translated 64.6%, guest/dispatch 13.4%. Prototype handled SteamOS multiline callchains. |

Private captures, saves, session logs, and game-derived binaries are not published.
