GAP G36 (new; DISPATCH ONLY IF G33 CLEARS IT) | sport baseball | worktree a4 | log cx_g36_baseball_day_corpus
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report.
DO NOT DISPATCH THIS LANE until G33 has reported and its dominant failure bin is NOT
resolution_360p. If 360p dominates, more day broadcasts buy nothing until the HLS route works
(G27 ACCESS LIMIT) and this lane is a waste of a slot. The orchestrator makes that call.
PREMISE (step 0): G12 is CLOSED. It acquired 8 candidates over 8 parks (4 day, 4 night) and kept
2 at the >= 6/12 field-view bar. The validated-scale fraction stands at 9 of 36 segments
(25.0 pct) on the four T5b clips. Confirm the current clip count and the kept/rejected tallies
from docs/evidence/tracking/baseball_footage_acq2_2026-09-02.md before fetching anything.
LIMIT (step 1): day centre-field pitch view only. Night is CLOSED AT LIMIT after three rejected
gate designs (G11); do not fetch night broadcasts and do not re-open the night question. The
achievable result is a larger DAY corpus and a validated-scale fraction with a real confidence
interval, not a higher fraction by construction.
CHANGE (step 2): acquire 8 more OFFICIAL MLB day broadcasts through the footage bridge (the
cookie jar is provisioned into the worktree by the dispatch wrapper; never print the cookie
path). Keep a clip only at >= 6 of 12 field-view census frames. Push kept clips to the pod
bridge. Re-run the existing scale validation unchanged over the enlarged corpus.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = validated pitch segments / total pitch segments (denominator = all pitch
                  segments across the enlarged day corpus), with a Wilson 95 pct interval, plus
                  the G33 failure bins for every NEW failure
  before        = 9 of 36 segments (25.0 pct) on 4 day clips
  bar           = the fraction is REPORTED with its interval and every new failure carries a G33
                  bin. The fraction is a LIMIT measurement of the day gate; it is not required to
                  rise, and a flat or lower fraction on more footage is a valid honest result.
  n             = >= 30 pitch segments in the enlarged corpus
  eye check     = 12 field-view census frames per candidate clip, EVENLY SPACED; plus 3 evenly
                  spaced renders for each new failing segment
  must not move = the 10 pct scale tolerance, the 24 in rubber constant, the >= 6/12 field-view
                  keep bar, and every harness threshold
NON-TAUTOLOGY: the fraction must be computed over ALL segments in the enlarged corpus, not only
the newly acquired ones and not only the ones that pass. Name every excluded segment.
EVIDENCE: docs/evidence/tracking/baseball_day_corpus_growth_2026-09-04.md -- the acquisition
table (kept/rejected with field-view tallies), the validated-fraction table with intervals, the
bin table for new failures, the render tally, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file.
POD: tracking the kept clips is pod work; own nohup nice job, unique /tmp log, never kill
anything (the MLB book capture is 24/7), no git on the pod, NO scp of any module.
COMMIT: explicit pathspec, in a4, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
