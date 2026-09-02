# G44B tennis ball spatial gate -- stop at premise reproduction

Date: 2026-09-02. Gap: G44B. Worktree: a3. Contract:
`docs/evidence/tracking/VERIFIER_CONTRACT.md`, including A7 and section B.

**VERDICT: NOT VALIDATED -- STOPPED BEFORE CHANGE.** The specification requires
independent reproduction of the G44 64% visible-ball rate and 52% in-window
rate before changing the detector. Neither the source clip nor G44's per-frame
hand-label file is available in this worktree, so those two figures cannot be
recomputed. No detector, player detection, court solver, camera lock, harness
threshold, or coordinate contract was changed.

## Premise reproduction

| Required observation | Result | Evidence |
|---|---|---|
| Ball size: 6-8 px near net and 15-30 px in cutaways | Read from the prior G44 measurement; not independently measurable without source | `g44_ball_detectability_limit_2026-09-02.md` |
| 64% (32/50) visible-ball rally frames | **NOT REPRODUCIBLE**: the 50 per-frame labels and source frames are absent | prior G44 memo only |
| 52% (16/31) inside `y < 480` | **NOT REPRODUCIBLE**: the 31 classified pixel labels and source frames are absent | prior G44 memo only |
| G39's 12-of-12 false candidates | **REPRODUCED**: every retained render was viewed, evenly sampled by the prior G39 artifact | `g44b_g39_per_frame_decisions_2026-09-02.csv` |

The 12 renders show zero marked candidates that are tennis balls: nine are a
far player's head, body, racket, leg, or shoe; three are crowd/staff/scoreboard
objects. The real yellow ball is visible elsewhere in frames 5687, 5711, 5727,
and 5794. This reproduces G39's 0/12 candidate precision observation, with a
Wilson 95% interval of 0.0% to 24.2% (0 correct of 12). It does not supply the
missing G44 labels and cannot turn the 64% or 52% reports into independently
recomputed measurements.

## Required input and label durability

The required source path,
`data/footage_corpus/tennis__tennis_nyYk2nPZAwY_720p.mp4`, is absent locally and
is not tracked by git. No G44 per-frame label artifact is tracked. The durable
status record is `g44b_label_artifact_status_2026-09-02.json`; it explicitly
records zero copied labels rather than fabricating a label set. The retained
G39 per-frame visual decisions are copied under `docs/evidence/` in
`g44b_g39_per_frame_decisions_2026-09-02.csv`.

Because the source and labels are absent, this lane cannot satisfy the required
minimum of 150 labels across three clips, cannot construct a disjoint fit and
held-out split, and cannot produce the required 15 held-out renders.

## Metrics

| Metric | Result |
|---|---|
| Held-out ball recall | **NOT COMPUTABLE** -- no source-backed, disjoint held-out labels |
| Held-out ball precision | **NOT COMPUTABLE** -- no candidate decisions on a held-out set |
| Prior G39 candidate precision, retained decision set | 0/12 = 0.0% (Wilson 95%: 0.0% to 24.2%) |

No recall gain is claimed. No precision-improving rule was fit or selected.

## Decision-boundary and downstream status

No boundary was selected. If the prerequisite artifacts are restored, the rule
must be derived only from a disjoint fit split and use an image signal beyond a
bare row cutoff (for example, component size and motion magnitude); a
hand-drawn clip rectangle is disallowed. Until a held-out evaluation clears
both the recall and precision bars, **no rally-tempo, serve-speed, or
contact-frame teacher may be built.** It may not be built now.

## Verifier self-check

### A7

All evidence paths named as available in this memo exist at write time:

- `docs/evidence/tracking/g44_ball_detectability_limit_2026-09-02.md`
- `docs/evidence/tracking/g39_ball_projection_diagnosis_2026-09-02.md`
- `docs/evidence/tracking/g39_renders/` (12 JPEGs)
- `docs/evidence/tracking/g44b_g39_per_frame_decisions_2026-09-02.csv`
- `docs/evidence/tracking/g44b_label_artifact_status_2026-09-02.json`

The original video and label artifacts are explicitly absent prerequisites, not
claimed evidence. Their absence makes the lane NOT VALIDATED.

### B1-B10

- B1: No scored held-out metric was produced; the complete retained 12-frame
  G39 decision set is named and preserved.
- B2: No schema or reader changed.
- B3: No gate changed.
- B4: No claim path changed.
- B5: No pod copy or deployment occurred.
- B6: No module moved or retired.
- B7: G39's stored 12 frames were evenly sampled by its source artifact and all
  were reviewed; no new head slice is claimed.
- B8: No rule was fitted or independently scored.
- B9: The preserved precision denominator is 12 unique frame decisions.
- B10: No harness threshold or gate value changed.

## NOT VERIFIED

- Independent 64% visibility and 52% window-rate reproduction.
- A source-backed 150-label, three-clip corpus.
- A disjoint fit/held-out rule, held-out recall, held-out precision, and their
  Wilson intervals.
- Fifteen held-out decision renders.
- Any code change or per-file test; the mandatory premise stop gate was reached
  before implementation.
