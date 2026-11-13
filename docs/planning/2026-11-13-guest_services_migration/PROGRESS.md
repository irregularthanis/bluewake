# PROGRESS — Guest services migration

Status: Opened 2026-11-13 (programme; estimates, no measurements of its own yet)
[Product brief](PRD.md) · [Technical plan](TECH_PLAN.md)

## Milestones

### M0: Measured shares (depends: #9's M8-T04/T05)
- [ ] M0-T01: From #9's second trace pass (draw-pass and scene sub-phase markers): the draw side's per-model cost distribution and write sets; the particle calc's share; the Z-targeting remainder
- [ ] M0-T02: Collision: #542's census at the eight states (queries a frame, cycles) as the measured share
- [ ] M0-T03: Audio: #561's per-thread sampler at the eight states
- [ ] M0-T04: Replace the PRD's estimates with the numbers; re-rank if they move

### M1: The J3D draw side (owned by #593 phase 2)
- [ ] M1-T01: The contract from the traces: per-model reads and writes, what other code reads of them
- [ ] M1-T02: Host design as per-model jobs; the GX assembly order; the exactness class decided with the owner
- [ ] M1-T03: Prototype on one model class; differential oracle; Deck A/B

### M2: Background collision
- [ ] M2-T01: Host spatial index from the BG data; exact query results against #542's harness
- [ ] M2-T02: Deck A/B at the lava room and the busiest view

### M3: The audio thread
- [ ] M3-T01: Wake-point markers and the queue contract
- [ ] M3-T02: Host thread prototype; DSP command digest identical

### M4: Particles
- [ ] M4-T01: Emitter contract from the traces; per-emitter jobs; bit-exact oracle

## Evidence ledger

| Task | Commit / artifact | Command / method | Environment / input | Result |
| --- | --- | --- | --- | --- |
| (basis) | fork PR #9: `measure-shadow-batches/` traces and reports | B1 trace build, `shadow_limit_study.py` | Steam Deck traces, workstation study | The execute loop at actor granularity gives ≈ 1.5 % at two workers, ≈ 4 % at best with unbounded batches over a queue (the ceiling, the same at 1–3 workers); the scene's execute is 40–43 % of its guest cycles (`dAttention_c::Run`, native in shipped builds); the median region is 618 cycles. The draw pass is not yet traced (B1c waits for the owner's OK) |
| (basis) | #592, #593 | Named profiles, headless | Steam Deck, busiest view | Draw side 19.9–26 M cycles a frame; game thread 124–131 M; ≈ 89 % translated |
| (basis) | #9 E0, E1a | Headless and Game Mode A/B | Steam Deck | Two busy cores: −0.65 % headless, −21 % in Game Mode at full duty; the non-fixed module 2–5 % slower, exact |

## Decisions

| Date | Decision |
| --- | --- |
| 2026-11-13 | Opened on the owner's request after #9's E2: the scalable path is migrating guest services to parallel host implementations, ranked by gain; the draw side first. On the fork for now |
