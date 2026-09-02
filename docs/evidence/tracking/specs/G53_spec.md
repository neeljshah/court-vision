GAP G53 | sport baseball | worktree a7 | log cx_g53_baseball_provenance
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. This is a PROVENANCE REPAIR and a restatement. No new tracking.
PREMISE (step 0, reproduce it): the headline "9 of 36 validated segments" is not reproducible from
the artifact that reports it. docs/evidence/tracking/baseball_scale_validation_2026-09-01/summary.json
holds only the two Window A clips and totals 9 of 30 segments over 322 pitch-view frames. The 36
and the 332 appear only if you silently ALSO add night_stride20/summary.json, which contributes
0 of 6 segments and 10 frames. Reproduce both sums yourself and print them; if your arithmetic
does not land on 9/30 + 0/6 = 9/36, report what you actually get and stop.
LIMIT (step 1): two separate defects, and they must not be conflated in the write-up.
  (a) PROVENANCE. A headline that requires combining an artifact the memo never names is not
      reproducible, and every downstream row quoting 9/36 inherits that.
  (b) INTERPRETATION. The 6 added segments are NIGHT, and the night lane is CLOSED AT LIMIT
      (G11, three rejected designs). A day-corpus number has therefore been carrying segments
      already known to be unfixable, which drags the fraction down and silently mixes two
      different questions into one number.
CHANGE (step 2): restatement only, no re-tracking and no new footage.
  (a) State the DAY fraction on its own: 9/30 = 0.300, with its own Wilson 95 pct interval.
  (b) State the NIGHT fraction separately, 0/6, with its interval, and label it CLOSED AT LIMIT
      with the G11 pointer, so no reader mistakes it for an open measurement.
  (c) Do NOT report a combined 9/36 anywhere as a headline. If it appears, it appears once, in a
      reconciliation line explaining what the old number was and why it is superseded.
  (d) Name EVERY artifact each restated number reads, by path. This is the actual deliverable.
  (e) Find and list every other memo or register row that quotes 9/36 or 332, so the orchestrator
      can correct them. Listing them is your job; editing other lanes' memos is not.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = reproducibility -- can a reader recompute each stated number from the named paths
  before        = 9/36 over 332 frames, reproducible from no single named artifact
  bar           = every restated number recomputes exactly from the artifacts named beside it, and
                  the day and night fractions are reported separately with Wilson intervals
  n             = all segments in both summary.json files; state the counts, do not sample
  eye check     = n/a (an arithmetic and provenance repair, not a perception claim). If you make
                  ANY claim about what a segment shows, that claim needs a render and you must
                  view it.
  must not move = every harness threshold, the G11 closed-at-limit verdict, and the segment data
                  itself. You are restating existing measurements, not re-measuring them.
NON-TAUTOLOGY: do not "fix" the fraction by re-defining what counts as a validated segment. The
definition stays exactly as the 2026-09-01 run applied it. If you believe the definition is wrong,
that is a NEW row and it takes a new id from the orchestrator -- lanes never invent gap ids.
GATES: G33's failure binning depends on this premise reproducing, so state clearly at the top of
the memo whether G33 may now proceed.
EVIDENCE: docs/evidence/tracking/g53_baseball_provenance_2026-09-0X.md with both reproduced sums,
the separated fractions with intervals, the full artifact path list, the list of memos quoting the
old number, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only if at all. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a7,
no push. Report the sha.
SHARED MODULE: none. If you find yourself editing the harness, STOP.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
