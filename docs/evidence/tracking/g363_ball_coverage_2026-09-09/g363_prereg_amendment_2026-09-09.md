# G363 preregistration amendment 1 -- adjudication trigger for centre disagreement (sealed alone, Q1)

Sealed BEFORE any adjudicator row exists and BEFORE any score is computed (ratings_terra.csv and
ratings_sol.csv are complete: 881 rows each; no ADJUDICATOR row exists; no prediction has been scored).
The sealed prereg (g363_prereg_2026-09-09.md section 6) sends a frame to the blind adjudicator only when
the two primary LABELS disagree, and averages the two centres when both raters say VISIBLE. That rule has
a defect the rater outputs expose: when both raters say VISIBLE but point at different objects, the mean
of the two centres is a location that matches neither rater, so a correct detection would be scored as
a false positive and a missed ball as a hit at a place no rater named.

## Amended rule (additive; the label rule is unchanged)

1. A frame goes to the blind adjudicator when EITHER (a) the two primary labels disagree (the sealed
   rule), OR (b) both primary labels are VISIBLE and the Euclidean distance between the two reported
   centres, in sheet pixels of the 960-wide panel, exceeds CENTRE_DISAGREEMENT_SHEET_PX = 48 (about
   2.7 reference diameters: the reference diameter is 24 px at 720p = 18 px on a sheet whose
   sheet_scale is 0.5), or a centre is missing on one side.
2. The adjudicator sees the same sheet and the same fixed instruction, never a rater label or centre,
   and writes one `ADJUDICATOR` row; that row is the reference for the frame (label AND centre; the
   scorer's `reference()` already prefers the ADJUDICATOR row and takes its centre alone -- no code
   change). Frames not sent to the adjudicator keep the sealed mean-of-centres rule.
3. The memo reports, separately: label disagreements, centre disagreements under (b), Cohen kappa
   over the three-label series (unchanged), and for the centre-disagreement frames how often the
   adjudicator's centre lies within 48 sheet px of terra's, of sol's, of neither.
4. Nothing else moves: thresholds, arms, splits, bars, the one-to-one matching rule and the
   denominators are the sealed ones.

Counts at sealing time (from the two primary files, printed by the orchestrator, not yet scored):
label disagreements 170; both-VISIBLE centre distance > 48 px 125; frames sent to the adjudicator
295 of 881. These counts are inputs to the adjudication, not results.

VERSION 2026-09-09 amendment 1
