GAP G74 | sport basketball | worktree a5 | log cx_g74_offframe_coast_measure
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report.
THIS IS A NEW ROW, NOT A THIRD G19 ATTEMPT. G19's attempt 2 was REJECTED by the verifier (codex a2
ea5835abb, never merged) because its "MEASURED" tag was circular: the /tmp/t3b_reemit tables it
relied on carry NO bbox columns at all, so the off-frame claim could not be evaluated from them.
Rule 2 is respected -- this row exists because the PREMISE CHANGED, exactly as G70 followed G26.
Do not cite G19's attempts as prior art for the bar.
WHAT CHANGED: G35 corrected the premise. 183 of 184 tracking tables carry no bbox, but ONE does --
`test720_4MoMewm2j-o` with 29,830 rows and 69 columns including bbox_x1..bbox_y2. So the
measurement can now run READ-ONLY against a real table, with NO re-tracking. That single table is
the whole opportunity and also the whole limitation; say so.
THE UNDERLYING CLAIM to be measured, not assumed: roughly 4 pct of rows were said to be residual
off-frame Kalman coasts (advanced_tracker.py around line 1165), and wnba_04's tracker was said to
have latched onto bench or crowd. Neither has been measured against bbox evidence.
MEASURE:
  (a) Using the bbox columns, count rows whose box lies wholly or partly OUTSIDE the frame, and
      rows that are pure coasts (predicted, not matched to a detection) if the table distinguishes
      them. State the frame width and height you used and WHERE you got them -- if the table does
      not carry them, say so and state what you assumed; G54 records that a re-emitted table can
      silently drop the columns a later lane needs.
  (b) Report the off-frame fraction over the stated row denominator with a Wilson 95 pct interval.
      Report it per track as well as pooled: one pathological track producing all the coasts is a
      completely different defect from a uniform low rate, and the pooled number cannot tell them
      apart.
  (c) EYE CHECK, MANDATORY: render >= 10 rows flagged off-frame or coasting, with the box drawn,
      and LOOK. Say what is actually there -- a player genuinely leaving the frame, a bench or
      crowd latch, or a box on nothing. That distinction IS the finding; the count alone is not.
  (d) Say explicitly whether the wnba_04 bench/crowd claim can be evaluated from this table at all.
      If test720_4MoMewm2j-o is not wnba_04, then it CANNOT, and the honest answer is that the
      claim remains unmeasured -- do not substitute one clip's result for another's.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = off-frame / coast row fraction, pooled and per track, with Wilson intervals
  before        = ~4 pct asserted, never measured against bbox evidence; attempt 2 rejected as
                  circular
  bar           = THERE IS NO PASS BAR. Success is a reproducible count from real bbox columns with
                  a stated denominator, plus the rendered look that says what the flagged rows
                  actually are. "The 4 pct does not reproduce" is a fine outcome. So is "it
                  reproduces and they are genuine exits", which would CLOSE the concern.
  n             = all 29,830 rows of the one table that has bbox; state the count you actually read
  eye check     = >= 10 rendered flagged rows, described from having looked at them
  must not move = every harness threshold, the tracker, and every verdict. This row MEASURES
                  read-only; it changes no code and re-tracks nothing.
NON-TAUTOLOGY: do not define "off-frame" using the same rule the tracker uses to decide to coast,
and then report that coasting rows are off-frame (B1). Define off-frame purely geometrically from
the bbox and the frame bounds, and state the definition in one sentence.
SINGLE-TABLE HONESTY: n=1 table and n=1 clip. Whatever you find is scoped to that clip, and the
memo must say so in its first paragraph. Do not generalise to basketball.
DURABILITY (A7): commit the per-row flags, the counts and the renders under
docs/evidence/tracking/g74_offframe/ BEFORE reporting.
FOOTAGE: the local worktree links data/footage_corpus (4 clips, no basketball); the full corpus is
on the pod, listed in docs/evidence/tracking/FOOTAGE_CORPUS_INVENTORY.md. Render read-only on the
pod. Check the inventory before reporting anything unavailable.
EVIDENCE: docs/evidence/tracking/g74_offframe_coast_measure_2026-09-0X.md with the definition, the
pooled and per-track fractions with intervals, the renders and what you saw, the explicit answer on
wnba_04, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. No scp, no deploy, no daemon restart, never kill anything -- another session has
live processes there.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a5,
no push. Report the sha.
SHARED MODULE: none. advanced_tracker.py is under src/ which is HUMAN-GATED -- do NOT edit it. If a
fix looks warranted, describe it as a PROPOSED diff in the memo and stop.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
