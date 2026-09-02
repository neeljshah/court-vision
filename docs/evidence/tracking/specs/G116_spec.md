GAP G116 | sport all | worktree a2 | log cx_g116_source_retention_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This row addresses the single most COMPOUNDING problem in the tracking programme.
THE PATTERN, four independent blockages in one day, none of them looking for it:
  - G96 could not complete the eye check that would have decided whether to reinstate a retracted
    harness change: the original tennis_10 source is pruned from pod and local corpus, three public
    retrieval paths failed, and the surviving stream is a 6,145 s 23.98 fps re-encode rather than
    the original 25 fps clip. That half is permanently NOT VERIFIED.
  - G110 found 3 of 33 basketball frames are different CONTENT because the `WFl3V7ZY4ss` source has
    a timeline divergence -- it was re-acquired and the old frames are gone.
  - G114 found **no source asset at all** for any of five legacy tennis tables, in either
    data/footage_corpus/ or data/videos/, so they can be neither validated nor re-tracked.
  - G38B earlier found zero retained selected-player tennis tables.
A tracking table whose source is gone is a number nobody can ever re-check. That is the opposite of
what this evidence programme is for, and it is getting worse as the corpus turns over.
MEASURE IT, do not fix it yet:
  (a) For every tracking table on the pod (G109 counted 196; state what you find), determine whether
      its SOURCE video still exists, and where -- data/footage_corpus/, data/videos/, the bridge
      stage, or nowhere. Report the retained fraction overall and per sport.
  (b) Report the retained fraction for the tables that MATTER MOST: the jump-gate-eligible ones
      (7 to 8 at last count) and any table cited as evidence in a committed memo. A corpus that
      retains 90 pct of junk and 0 pct of its cited evidence is worse than the headline suggests.
  (c) Determine WHY sources disappear. Read footage_bridge.py, which documents
      "download -> scp -> track on pod -> delete local AND remote copies immediately", and
      track_daemon.py, which moves a tracked video to data/footage_corpus/ instead of deleting it
      and says re-staging one game is a single cp. Those two policies differ. Establish which
      applies when, and whether the corpus policy post-dates the missing tables. Quote the code;
      do not infer.
  (d) MEASURE THE COST BOUND. What would retaining every source cost in disk? Report the mean and
      total size of the current corpus and extrapolate. If full retention is not affordable, say so
      with the number, because that reframes the fix from "retain everything" to "retain what is
      cited".
  (e) RECOMMEND a retention policy in one paragraph. Candidates: retain any source cited by a
      committed memo; retain any source behind a gate-eligible table; retain a deterministic
      re-acquisition manifest (URL, duration, fps, frame count, checksum) instead of the bytes so
      loss is at least DETECTABLE. Note that G110 proved decoding is deterministic (33/33
      seek-versus-sequential pixel-identical), so a manifest plus a stable source really would
      reproduce -- but G96 and G110 both found the upstream source itself had CHANGED, so a
      manifest must record enough to detect that, not just to re-download.
DO NOT delete, move, re-download or re-track anything. Do not change the bridge, the daemon, any
threshold, or the coordinate contract. This row counts and recommends.
ACCEPTANCE RULE:
  metric        = fraction of pod tracking tables whose source video still exists, overall, per
                  sport, and for gate-eligible and memo-cited tables specifically
  before        = unmeasured; four separate measurements blocked by source loss in one day
  bar           = NO pass bar. Success is the retained fraction measured with its denominators, the
                  cause quoted from the code, the disk cost bounded, and one policy recommendation.
                  A high retention rate would be reassuring and is a full success.
  n             = every pod tracking table; state the count you read, and state the gate-eligible
                  and memo-cited subsets separately with their own denominators
  eye check     = n/a. But do CONFIRM presence by stat-ing the file, not by trusting a ledger field;
                  a ledger row saying a corpus copy exists is exactly the kind of claim that has
                  been wrong today.
  must not move = every clip, every table, the bridge, the daemon, every threshold, the coordinate
                  contract, and every verdict
EVIDENCE: docs/evidence/tracking/g116_source_retention_census_2026-09-0X.md with the retention table,
the quoted policies, the disk bound, the recommendation, and a NOT VERIFIED list. Commit derived
tables under docs/evidence/tracking/g116_retention/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, strictly. Never kill anything -- the daemon and seven bridge lanes are live and the
corpus is turning over while you measure, which is itself worth noting in the memo.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
SHARED MODULE: track_daemon.py is under the token; READ it, do not change it.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
