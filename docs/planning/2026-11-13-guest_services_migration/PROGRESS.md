# PROGRESS — Guest services migration

Status: Opened 2026-11-13 (programme; estimates, no measurements of its own yet)
[Product brief](PRD.md) · [Technical plan](TECH_PLAN.md)

## Milestones

### M0: Measured shares (depends: #9's M8-T04/T05)
- [x] M0-T01 (2026-11-13, from #9's third trace pass B1c: three states, 100 game frames each, guest cycles with the native routines off): **the draw loop is 3.3 / 2.3 / 3.2 M guest cycles a frame** (busiest view / play / Outset) against the execute loop's 7.1 / 6.6 / 7.0 M, so 26–32 % of the two `fpc` loops; ≈ 200 process draws a frame. **The scene's own draw is 35–41 % of the draw loop**, and the grass system is most of it: `executeGrass` 14 / 20 / 15 % and `drawGrass` 6 / 8 / 6 % (≈ 0.7 M cycles a frame, one call each from `dScnPly_Draw`), then `dCcS::Move` 3–4 %, the particle `calc3D` 2–3 % (`calc2D`, `calcMenu` ≈ 0), the trees and flowers 5–6 % together, `drawMagma` 2 % at the busiest view. Per-process draws: PLAYER 8 / 14 / 9 %, BRIDGE 8 / 12 / 9 %, then MACHINE, VRBOX2, BWDG, the MP (50 a frame at ≈ 2.5 k cycles). The Z-targeting remainder: `dAttention_c::Run` is 40–43 % of the execute loop (one call a frame, ≈ 2.9 M cycles), `dAttention_c::Draw` ≈ 0. Write sets, from the serializing words: the draw's are J3D's current context (`j3dSys`: current matrix calc, flags, model, material packet, texture, `mCurrentMtx`), the clipper's planes under the change-far/clip/reset pattern, the draw buffer's `entryNum` (the packet order) and `J3DDisplayListObj::sInterruptFlag`; the execute loop's actors chain on the collision registration counters (`cCcS::mObjAtCount/mObjTgCount/mObjCoCount`) besides the matrix scratch. Reports: `measure-shadow-batches/v3/reports/` (local, per state); the method and the ceilings in #9's M8-T05/T07. **For the ranking (M0-T04): the grass system is a new, well-separated candidate** (two functions, once a frame, their own data, ≈ 20–28 % of the draw loop); the per-model J3D draw is many small regions (≈ 7 k cycles each) whose order is fixed by the draw buffer
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
| (basis) | fork PR #9: `measure-shadow-batches/` traces and reports | B1 trace build, `shadow_limit_study.py` | Steam Deck traces, workstation study | The execute loop at actor granularity gives ≈ 1.5 % at two workers, ≈ 4 % at best with unbounded batches over a queue (the ceiling, the same at 1–3 workers); the scene's execute is 40–43 % of its guest cycles (`dAttention_c::Run`, native in shipped builds); the median region is 618 cycles. Third pass (B1c, 2026-11-13): the draw loop is 26–32 % of the two loops' guest cycles; at actor granularity it gives 2.1–2.7 % at two workers and ≈ 3–5.5 % at best (ceilings), the J3D context, the clipper and the draw-buffer order being the chain; see M0-T01 |
| (basis) | #592, #593 | Named profiles, headless | Steam Deck, busiest view | Draw side 19.9–26 M cycles a frame; game thread 124–131 M; ≈ 89 % translated |
| (basis) | #9 E0, E1a | Headless and Game Mode A/B | Steam Deck | Two busy cores: −0.65 % headless, −21 % in Game Mode at full duty; the non-fixed module 2–5 % slower, exact |

## Decisions

| Date | Decision |
| --- | --- |
| 2026-11-13 | Opened on the owner's request after #9's E2: the scalable path is migrating guest services to parallel host implementations, ranked by gain; the draw side first. On the fork for now |
