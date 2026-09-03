GAP S176 | sport harness | worktree aXX | log cx_s176_screen_failure_rows
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- self-check B AND Q (S-row) before reporting.
PREMISE (step 0): census the READ-ONLY shipped DB data/cache/eval_gate/s85_screen_2026-09-03.sqlite
(md5 ef0919534012db3eda6dbc38d6d0c360; open mode=ro, never write it): queue 1,125 all claimed,
result 1,302 (T0 958 / T1 344), and 167 of 1,125 = 14.8444 pct queue rows have NO result row at
any tier (same at own tier), across 14 families led by mlb_catcher_framing_index 27/27 and
mlb_bullpen_relief_chains 22. Re-confirmed 2026-09-04 by this lane. Cause: foundry_runner.py
:160-173 `_screen_one` catches every exception, prints one stdout line (:171) and returns None --
no row written, though its docstring says a failed screen is "never dropped". If the census
differs, STOP, write the memo, report FALSIFIED.
LIMIT (step 1): read the re-claim path from the SQL, not the story. reap_expired (results_db.py
:226-239) frees ANY expired claim with no result predicate and claim() calls it (:283); release()
(:254-260) is predicated on NOT EXISTS(result). A permanently failing hypothesis was therefore
re-claimed on the lease cadence BEFORE S150, which made it immediate but did not create it -- say
so in the memo. If one durable row cannot close both paths, report CLOSED AT LIMIT.
CHANGE (step 2): additive only. (a) a new verdict value SCREEN_FAILED and a new nullable
`refusal` TEXT column on `result`, DDL/ALTER in foundry/results_db_sql.py (76 LOC --
results_db.py and foundry_runner.py are both 299 against the 300 cap); (b) the except branch at
foundry_runner.py:170-172 writes exactly ONE row carrying tier, family, feature, exception type
and the message (keep the stdout line); (c) claim() skips a queue row that already has a result
at its own tier. Rename or remove nothing.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = queue rows with no outcome row at any tier / queue rows in one seeded replay
  before        = 167 of 1,125 (14.8444 pct) in the shipped S85 DB; 3 of 3 re-claims
  bar           = 0 of 1,125 with no outcome row, AND a second claim() pass takes 0 of the 167,
                  AND the pass summary's screens count equals the rows it wrote
  n             = 1,125 (CONSTRUCT: exhaustive replay of the seed copied from the S85 DB into
                  tmp -- those 167 hashes raise, the other 958 return) + 3 (CONSTRUCT re-claim probe)
  eye check     = n/a (S-row); reproduction = replay the seed, then SELECT COUNT(*) FROM queue q
                  WHERE NOT EXISTS (SELECT 1 FROM result r WHERE r.hash=q.hash); then run a
                  second claim() pass and assert it returns 0
  must not move = LEASE_SECONDS 900.0; the release() and reap_expired() SQL predicates
                  byte-identical; verdicts COVERED / UNCOVERED / SCREEN (add, never rename);
                  backtest_fwer.jsonl 18 rows md5 a4ae7c13995672e478d59770591b83ba; the S85 DB
NON-TAUTOLOGY: the denominator is all 1,125 seeded rows, none excluded; the 167 hashes come from
the shipped census, not the fix. The metric scores bookkeeping, not whether a hypothesis screens.
EVIDENCE: docs/evidence/harness/screen_failure_rows_2026-09-04.md -- before/after table, 14-family
breakdown, n, denominator, NOT VERIFIED list.TEST: exactly one new per-file test; run only that file. POD: none, local construct.
COMMIT: explicit pathspec, in the worktree, no push. Report the sha. Calibration language only.
NEVER PARK: poll your own jobs in a blocking loop; never end waiting.