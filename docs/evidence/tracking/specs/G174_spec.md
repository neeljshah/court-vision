GAP G174 | sport basketball | worktree a2 | log cx_g174_late_stamp_skip_rate
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it (A2, A3, A5, A7, Q8); self-check B.
RAILS: heavy work ON THE POD under nohup, batched collection, never poll. A local decode was
RAM-killed today at 1.4 GB. NEVER kill, restart or deploy over the pod daemon or keeper.

THE LIVE RISK. G158 established there are TWO producers of `tracking_data.csv` and they behave
differently. `src/pipeline/unified_pipeline.py:_checkpoint_csv` writes UNSTAMPED -- it imports no
provenance helper. `scripts/run_clip.py` wraps it and attempts a LATE `stamp_image_space_rows`, but
**only when every provenance column is absent, and inside a `try/except` that logs `stamp skipped`
and continues**. `track_daemon.CLIP_SPORTS` routes wnba, basketball, ncaa_basketball and nba through
`run_clip.py`, which is the bulk of the workload.

So every basketball-family table the daemon produces depends on a fragile late stamp succeeding, and
nobody has measured how often it does. 358 of 359 surviving undeclared local tables are basketball
(G158b), which is consistent with it failing often -- but that is a hypothesis about legacy files, not
a measurement of what production does TODAY.

MEASURE, read-only:
  (a) Over the ELIGIBLE DENOMINATOR of basketball-family tables the daemon has produced on the NEW pod
      (list them by game_id; there were 19 tables total when this was written), how many carry a
      coordinate declaration and how many do not? Report counts and shares. Never a bare sample size.
  (b) For any table missing the declaration, find the `stamp skipped` line in its job log if one
      survives, and quote it. If logs are gone, say so -- an absent log is not evidence of success.
  (c) Quote the exact `try/except` from `run_clip.py` with file:line, and name every exception class
      it swallows. Say what a caller can and cannot distinguish afterwards.
  (d) THE QUESTION THAT MATTERS: does a missing declaration change the table's EligIBILITY
      classification? Run `scripts/platformkit/g154_local_table_census.py` logic (or read it) and say
      whether an unstamped basketball table lands in `other` and is therefore invisible to the jump
      gate. If so, the late stamp silently decides whether a table is even considered.
  (e) A5: grep every reader that branches on the presence of a coordinate declaration.

**DO NOT change `src/`** -- it is human-gated; write a PROPOSED diff under docs/research/ if a change
is warranted. Do not change run_clip.py's behaviour in this row; measure first. Do not re-stamp or
modify any table. Move no threshold, bar, eligibility definition, coordinate contract or verdict.

ACCEPTANCE RULE:
  metric        = declared vs undeclared counts and shares over the eligible denominator of
                  daemon-produced basketball-family tables; the quoted try/except and its swallowed
                  exceptions; whether an undeclared table is invisible to the jump gate
  before        = the late stamp's real-world skip rate is entirely unmeasured
  bar           = NO pass bar. "The stamp succeeds on every table measured" is a FULL SUCCESS and
                  would retire the concern; say so plainly if that is what you find.
  n             = every daemon-produced basketball-family table on the pod (CONSTRUCT, exhaustive)
  eye check     = replaced by REPRODUCTION (Q7): quote each command with raw output
  must not move = `src/`, run_clip.py, every threshold and bar, the eligibility definition, the
                  coordinate contract, every existing table, and every verdict
EVIDENCE: docs/evidence/tracking/g174_late_stamp_skip_rate_2026-09-03.md with the per-table table, the
quoted exception handling, the eligibility consequence, the A5 list, and a NOT VERIFIED list. Commit
BEFORE reporting (A7).
TEST: one per-file test only if you add code. NEVER a full pytest.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
NEVER PARK.
