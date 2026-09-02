GAP G85 | sport tennis | worktree a6 | log cx_g85_ball_label_consistency
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. A CONSISTENCY measurement. Relabel nothing wholesale.
THE QUESTION: is tennis_10's low resolved rate a property of the CLIP or of the LABELLER? Three
chunks resolved the G65 `uncertain` rows with the same instructions and the same tiled 2x method,
and they disagree sharply:
  - nyYk 720p:    **29/30 = 96.7 pct** resolved to ball-visible
  - tennis_09 1080p: **27/32 = 84.4 pct**
  - tennis_10 1080p: **13/47 = 27.7 pct**
Resolution does not explain it -- nyYk is the 720p clip where the ball is SMALLEST and it resolved
almost everything. Two of three agree at 84-97 pct and one sits at 28 pct.
WHY IT MATTERS CONCRETELY: pooled, the three chunks would take total ball-visible from 41/150 to
110/150, which clears the **>= 100 resolved positives** that G44B named as its precondition for
measuring recall and precision at all. So this one clip is what stands between here and the tennis
ball measurement. The pooled figure must not be used until this is settled.
METHOD:
  (a) ONE labeller re-does a SEEDED BLIND sample of >= 20 rows from EACH of the three clips --
      60 rows total -- without seeing the prior label. Record the seed. Seeing the prior label first
      is the anchoring that would simply reproduce whatever each chunk did.
  (b) Report per-clip agreement against the chunk labels, and the DIRECTION of each disagreement.
  (c) Answer the question in one sentence: clip property or labeller property.
  (d) If it is a CLIP property, record WHAT makes tennis_10 hard -- zoom, motion blur, ball leaving
      frame, court contrast, rally phase. That is a real and reusable fact about which tennis
      footage supports ball work.
  (e) If it is a LABELLER property, say so plainly and state what the resolved counts need before
      they can be pooled. Do NOT silently re-label all 109 to your own standard in this row.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-clip agreement between a blind relabel and the chunk labels
  before        = 96.7 / 84.4 / 27.7 pct resolved across three clips, cause unknown
  bar           = THERE IS NO PASS BAR. Success is the per-clip agreement with its direction and a
                  clear one-sentence answer. "The clips genuinely differ" and "the labellers
                  differ" are equally good outcomes.
  n             = >= 20 blind rows per clip, 60 total; state the seed and the per-clip counts
  eye check     = this row IS the eye check, at tiled 2x or better. A judgement made at lower zoom
                  is exactly the error G65 attempt 1 made when it returned 100 pct uncertain from
                  whole frames.
  must not move = the existing chunk labels (write yours to a separate file), every harness
                  threshold, and the coordinate contract
PRECEDENT worth knowing: G76 asked this same question of the basketball paint census and found the
criterion measurably permissive -- 20 of 69 positives over-called, 18 of 52 negatives under-called,
raw agreement only 68.6 pct. So do not assume high agreement; measure it. And note that a high
disagreement rate in BOTH directions means an ambiguous criterion rather than a biased one, which
has a different fix.
DURABILITY (A7): commit your blind labels, the seed and the renders under
docs/evidence/tracking/g85_consistency/ BEFORE reporting.
EVIDENCE: docs/evidence/tracking/g85_ball_label_consistency_2026-09-0X.md with the per-clip
agreement and directions, the one-sentence answer, what makes tennis_10 hard if it is the clip, and
a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only. Never kill anything -- three tennis re-tracks of mine are running there.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a6,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
