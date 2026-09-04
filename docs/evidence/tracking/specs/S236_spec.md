GAP S236 | sport all | worktree a17 | log cx_s236_season_block_partition
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: REDTEAM SF-11: `combo/fwer_budget.min_corpora_eff` caps at `n_corpora`; NBA has 2 `corpus_unit`s
(2024-25: 1,225 rows, 2025-26: 589), MLB 2 (era_2010_2021: 27,983, era_2022_2026: 11,179 -- S50 line 96-97), tennis
2 (ATP 25,764 joined / WTA 8,002 joined -- S03), soccer 6 (D1/E0/E1/F1/I1/SP1). If S234's screen/verdict partition
consumes one `corpus_unit` for screening, T3 (replication) has ZERO left and every NBA/MLB/tennis verdict becomes
SINGLE-WINDOW by construction; soccer is unaffected (6 units) and serves as the control. S202 (LANDED) already
prints one-way clustered n_eff by `corpus_unit`: nba 751.5553/1,814, mlb 10,802.5823/39,162, soccer 9,733.4018/
25,834, tennis 37,961.8277/41,886 -- computed on the corpus_unit partition (6-way for soccer), not a season block.
PREMISE (step 0): reproduce SF-11's `min_corpora_eff` cap-at-`n_corpora` behavior (`fwer_budget.py:77-90`) and the
four sports' `corpus_unit` value counts above from the live gate corpora; reconcile `s81_market_move.py:198`'s
"a one-unit corpus (mlb: era_2022_2026)" against S50's 2-unit MLB reading -- that line describes a modern-close
SUBSET, not the full gate corpus; state which is which before building anything.
LIMIT (step 1): if a season/ISO-week block partition for NBA/MLB/tennis yields fewer than 3 non-empty blocks per
sport (too coarse to raise `n_corpora` above 2), report CLOSED AT LIMIT for that sport and leave `corpus_unit`
partitioning as the honest current answer; soccer needs no new partition and is reported unchanged as the control.
CHANGE (step 2): additive-only module `scripts/platformkit/eval_gate/season_block_partition.py` (<=300 LOC):
`season_blocks(rows, sport) -> Series` assigning each row a season/ISO-week block id (NOT `corpus_unit`) for
NBA/MLB/tennis only; `n_corpora_by_block(rows, sport) -> int` and a re-quoted n_eff per sport under the block
partition, beside (not replacing) the S202 figures. Propose the one-line `min_corpora_eff` caller-side swap as a
PROPOSED snippet under docs/research/organization-sprint/ -- do not edit fwer_budget.py or replication_gate.py.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = n_corpora and one-way clustered n_eff per sport under the season-block partition, printed
                  beside the S202 corpus_unit figures on identical rows
  before        = corpus_unit n_corpora: nba 2, mlb 2, tennis 2, soccer 6; n_eff (S202) nba 751.5553/1,814, mlb
                  10,802.5823/39,162, soccer 9,733.4018/25,834, tennis 37,961.8277/41,886
  bar           = nba/mlb/tennis each report a season-block n_corpora >= 3 (or an honest <3 CLOSED AT LIMIT per
                  sport); soccer's block partition reproduces n_corpora == 6 (its own corpus_unit count) to
                  confirm the block method agrees with the unaffected control; 0 rows dropped from any corpus
  n             = 4 sports (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns season_blocks + n_corpora_by_block per sport and
                  diffs against the memo's printed counts and n_eff
  must not move = fwer_budget.min_corpora_eff formula; the S202 corpus_unit n_eff figures (kept as BEFORE)
NON-TAUTOLOGY: a sport with n_corpora < 3 under the block partition is CLOSED AT LIMIT for that sport, never
omitted from the four-sport table.
EVIDENCE: docs/evidence/harness/S236_season_block_partition_2026-09-04.md + per-sport block-count JSON. ASCII only.
Calibration language only (no dollar, ROI or edge words); a SINGLE-WINDOW verdict stays SINGLE-WINDOW if unmet.
TEST: one new per-file test (block assignment + n_corpora on all 4 sports), run only that file.
REPORT: the four sports' n_corpora and n_eff, reconciled S50/s81 unit-count note, test line, SHA. Commit by
pathspec, no push. NEVER PARK.
