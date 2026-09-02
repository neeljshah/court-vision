GAP G38B | sport tennis | worktree a8 | log cx_g38b_jump_cause
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including the NEW A7 clause;
self-check every line of section B before you report. This is the experiment G38 itself named as
decisive, and it is now unblocked.
PREMISE (step 0, reproduce it): G38 established that tennis `jump_p95` is a real defect in player
SELECTION, not a metric artifact and not smoothing. Its evidence: the harness number reproduces
exactly (tennis_03 34.36, tennis_04 10.03 against a bar of 8.00); the mass of oversized jumps sits
at 10-29 ft, not at the 78 ft court length; and on three of four clips the MAJORITY of big jumps
happen between consecutive SAMPLED frames three apart (65.4, 64.3, 56.7 pct), where no
reappearance-gap explanation exists. At stride 3 and 30 fps a 10-29 ft displacement implies
100-290 ft/s against a world-class sprinter's ~39 ft/s, so it is one to two orders of magnitude
beyond human motion. Every clip has exactly TWO player tracks with exactly EQUAL row counts, so
there is no multi-track association to get wrong -- there is a per-half CHOICE, and it is unstable.
Reproduce the reproduction table and the 10-29 ft concentration before doing anything else.
WHAT IS NEW, and why this row exists now:
  (a) G38's own NOT VERIFIED list says the 30 fps assumption was never checked per clip. G48 has
      since landed `sampling_interval_s` and `jump_p95_ft_per_s` on the harness report. USE THEM.
      Re-express every jump as a SPEED and report it that way; a raw distance compared across
      clips with different intervals is not comparing like with like (that is G48's whole point).
  (b) G38 said "the G26 attempt-2 limit measurement is the experiment that settles it", because it
      dumps every candidate foot point with a render-attributed real/not-real label. That artifact
      now EXISTS and is preserved at
      docs/evidence/tracking/tennis_player_select_limit_2026-09-04/ (candidates.csv, 33,633 rows,
      plus report.json and renders/). This row is the join G38 asked for.
THE QUESTION (step 1): are the endpoints of the 10-29 ft jumps NON-PLAYERS? Join the big-jump
endpoints to the render-attributed candidate labels and answer it with a number. G38 already
falsified the weaker proxy -- testing whether an endpoint falls outside the generous G26 rectangle
accounted for only 4.9 to 13.0 pct of big jumps -- and explained why that proxy is weak: ball kids
and line judges stand INSIDE the rectangle. So do not re-run the rectangle test; use the labels.
ALSO SETTLE, because G38 left both open: whether the unstable partner is (i) a non-player, (ii) a
duplicate detection of the SAME player, or (iii) a partially-occluded second detection. These are
distinguishable -- a duplicate sits within a body-width of the true player, a non-player does not.
Report the three-way split with counts, not a single verdict.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the fraction of >8 ft stride-adjacent jump endpoints whose partner is labelled
                  NOT-a-real-player, over a stated denominator of such jumps
  before        = cause narrowed to "unstable per-half choice" by elimination, never by label
  bar           = THERE IS NO PASS BAR. This row succeeds by producing the labelled split with
                  Wilson intervals. "The partners ARE real players" would be a major finding and
                  would redirect the fix entirely, so report it plainly if that is what you find.
  n             = every stride-adjacent >8 ft jump on the clips that have both a table and
                  candidate labels; state the join rate and what you dropped and why
  eye check     = MANDATORY on >= 12 cases sampled seeded and evenly spaced across the three-way
                  split. Look at the render and say what the partner actually is. A label you
                  inherited and never looked at is not an eye check.
  must not move = every harness threshold including the 8.0 ft bar, the solver, the camera lock,
                  and the coordinate contract. This row MEASURES; it fixes nothing.
DATA CAVEAT you must handle honestly: G38 used four tables (tennis_02/03/04/05) and explicitly
excluded tennis_01/07/08/09 because they were re-tracked and no longer matched the census. The pod
has since been remediated (G59) and 13 modules deployed. So state clearly which tables you used,
when they were written, and whether they were produced before or after those changes. If the four
G38 tables no longer exist, say so and use what does, with the denominator stated -- do NOT
silently substitute a different corpus.
FOOTAGE: the local worktree links data/footage_corpus (4 clips); the full 63-clip corpus is on the
pod, listed in docs/evidence/tracking/FOOTAGE_CORPUS_INVENTORY.md. Render work may run read-only
on the pod. Check the inventory before reporting anything as unavailable.
EVIDENCE: docs/evidence/tracking/g38b_jump_cause_2026-09-0X.md with the reproduced premise, the
speeds in ft/s, the labelled three-way split with intervals, the renders, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a8,
no push. Report the sha.
SHARED MODULE: none. If you find yourself editing tracking_harness.py, STOP -- two other lanes are
in that file today.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
