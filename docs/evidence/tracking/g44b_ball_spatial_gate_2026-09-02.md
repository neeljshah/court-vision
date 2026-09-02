# G44B tennis ball spatial gate -- attempt 2 premise stop

Date: 2026-09-02. Gap: G44B. Worktree: a3. Contract:
`docs/evidence/tracking/VERIFIER_CONTRACT.md`, including A7 and B1--B10.

**VERDICT: NOT VALIDATED -- STOPPED BEFORE CHANGE.** This is not a source
availability result. Both the local linked corpus and the read-only pod contain
`tennis__tennis_nyYk2nPZAwY_720p.mp4`; the pod source was explicitly opened.
The original G44 *per-frame* hand-label artifact, however, does not exist
locally or on the pod. Its published aggregate counts cannot supply either a
fit/held-out split or the required ball pixel tolerance. I did not create a
rule, a threshold, or synthetic labels from the aggregate claim.

## Premise review

| Required observation | Attempt-2 result | Durable evidence |
|---|---|---|
| Ball size / resolution wall | Source review is consistent with the existing 6--8 px near-net and 15--30 px cutaway observations, but no new pixel measurement is claimed without a labelled source record. | `g44_ball_detectability_limit_2026-09-02.md` |
| G44 64% (32/50) visible-ball rate | Not independently recomputable: no per-frame visibility decisions survived the original measurement. The documented 50-frame source review set was regenerated and viewed, but its review pages do not encode a hand-label decision per frame. | `g44b_premise_review_2026-09-02/` |
| G44 52% (16/31) in-window rate | Not independently recomputable: no per-frame ball coordinates/window decisions survived. | `g44_ball_detectability_limit_2026-09-02.md` |
| G39 12-of-12 false candidates | **REPRODUCED.** All twelve evenly spaced retained renders were reviewed; each marked candidate is non-ball. | `g39_renders/`, `g44b_g39_per_frame_decisions_2026-09-02.csv` |

The G39 tally is 0/12 candidates that are balls (Wilson 95%: 0.0%--24.2%).
Nine marked candidates are a far player/body/racket and three are
crowd/staff/scoreboard objects; the actual ball is visible elsewhere in four
frames. This does not turn the two undocumented G44 aggregates into a
reproducible label set. Under the specification's step-0 rule, work stops here.

## Why no spatial rule was fitted

The compliant successor must use a signal beyond image row (for example a
label-derived size, motion or local-colour feature), fit it on one frame split,
and score a disjoint split. No >=150 three-clip hand-labelled rally frame set,
ball coordinates, tolerance decisions, or candidate decision records exist.
Choosing a colour/size boundary now would be B8 self-fit and could not report
held-out recall and precision. No player detection, court solver, camera lock,
harness threshold, or coordinate contract changed. No pod file was copied,
deployed, restarted, or killed.

## Downstream status

No rally-tempo, serve-speed, or contact-frame teacher may be built. This gate
has not passed.

## A7 and B self-check

All available paths named by this memo exist at write time:

- `docs/evidence/tracking/VERIFIER_CONTRACT.md`
- `docs/evidence/tracking/FOOTAGE_CORPUS_INVENTORY.md`
- `docs/evidence/tracking/g44_ball_detectability_limit_2026-09-02.md`
- `docs/evidence/tracking/g39_ball_projection_diagnosis_2026-09-02.md`
- `docs/evidence/tracking/g39_renders/`
- `docs/evidence/tracking/g44b_g39_per_frame_decisions_2026-09-02.csv`
- `docs/evidence/tracking/g44b_premise_review_2026-09-02/`
- `docs/evidence/tracking/g44b_label_artifact_status_2026-09-02.json`

- B1: no scored metric excludes failures; uncomputed metrics are named.
- B2--B4: no schema, reader, gate or claim path changed.
- B5: pod access was read-only; no pre-verification deployment occurred.
- B6: no module moved or retired.
- B7: the retained G39 set is evenly spaced; the regenerated G44 review uses
  the documented seeded sample rather than a head slice.
- B8: no boundary was fitted or represented as independent.
- B9: the only precision denominator is 12 unique retained frame decisions.
- B10: no harness threshold changed.

## NOT VERIFIED

- Per-frame reproduction of the 32/50 and 16/31 G44 values.
- A >=150-frame, seeded three-clip hand-label corpus.
- A disjoint fit/held-out rule, held-out recall, held-out precision, Wilson
  intervals, or fifteen held-out candidate renders.
- Any code change or focused test: the mandatory premise stop occurred first.
