GAP S182 | sport nba | worktree a18 | log cx_s182_nba_spine_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check section B and section Q (Q1-Q8) before you report.
PREMISE (step 0; re-measured 2026-09-04, reconfirm before any work -- if falsified STOP, write the memo, commit, report FALSIFIED):
data/domains/basketball_nba/games.parquet = 4,846 rows, ALL home_win non-null, seasons 2022-23..2025-26 = 1,230 / 1,230 / 1,230 / 1,156, dates 2022-10-18..2026-04-12.
data/cache/combo/gate_corpus_nba.parquet = 1,814 rows / 1,814 distinct event_id = 37.4329 pct; hole 3,032 = 62.5671 pct; per season 0/1,230, 0/1,230, 1,225/1,230, 589/1,156.
Root cause: scripts/platformkit/combo/corpus_cache_sources.py:78 reads asof_features_ext.parquet as `af` and :83-84 left-joins games ONTO it, so the as-of table is the
denominator; asof_features_ext and asof_box_extra_ext are each 1,814 rows / 1,814 distinct game_id. Nothing in the build, the sidecar or freshness_report reports the hole.
LIMIT (step 1): per (column, season), the maximum games.parquet coverage its on-disk carrier can support. Measured today, distinct game_id and per-season coverage:
asof_team_adv 3,685 rows / 3,685 distinct (1,230 / 1,230 / 1,225 / 0); asof_quarter_shape 2,634 rows / 2,386 non-null game_id, 248 null (0 / 0 / 1,230 / 1,156);
player_value_features 7,222 rows / 3,611 distinct, 2 rows per game (0 / 1,230 / 1,225 / 1,156). No carrier outside asof_box_extra_ext supplies dreb/fg3m/stl/blk, and
asof_team_adv's oreb_pct / tov_ratio / ast_pct are percent-and-ratio variants, NOT the corpus's per-game oreb_pg / tov_pg -- so expect CLOSED AT LIMIT on most of the
11 columns. Record every column with its own numerator and denominator. Never lower a bar to fit; a bar found unmeetable is reported CLOSED AT LIMIT, not moved.
CHANGE (step 2): ONE new module scripts/platformkit/combo/nba_spine_census.py (<= 300 LOC). Additive only. It (a) writes the per-column x per-season census, and
(b) writes a NEW data/cache/combo/gate_corpus_nba_full.parquet plus a repo-relative sidecar (S68 portable=True must load it) whose spine is games.parquet:
all 4,846 outcome-known games, y and p_base/p_elo from walk_forward_elo over the full frame, the 9 as-of feature columns LEFT-joined and NaN outside their
carriers (missing != bad, B3), and one boolean column naming the legacy 1,814 subset. Do NOT edit _build_nba; do NOT rewrite gate_corpus_nba.parquet.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = rows in gate_corpus_nba_full.parquet and its per-season coverage; denominator 4,846 games.parquet rows with home_win non-null (1,230/1,230/1,230/1,156)
  before        = 1,814 rows = 37.4329 pct; per season 0/1,230, 0/1,230, 1,225/1,230, 589/1,156
  bar           = >= 3,044 rows (62.8 pct of 4,846) with 2022-23 > 0 AND 2023-24 > 0, PLUS one census row for each of the 11 non-key gate-corpus columns giving its
                  maximum per-season coverage; a column whose carrier cannot reach a season is recorded CLOSED AT LIMIT with its own numerator and denominator
  n             = 4,846 (CONSTRUCT -- every outcome-known game enumerated, nothing sampled)
  eye check     = n/a (S-row); reproduction = the verifier re-reads games.parquet, gate_corpus_nba.parquet and gate_corpus_nba_full.parquet, recomputes the per-season
                  set difference on game_id, and re-reads every census numerator from the artifact
  must not move = gate_corpus_nba.parquet byte-identical (sha256) with its 15-column schema unchanged; y and p_base .equals-identical on all 1,814 pre-existing
                  event_ids; data/cache/eval_gate/backtest_fwer.jsonl byte-identical (18 rows)
NON-TAUTOLOGY: the denominator is all 4,846 outcome-known games with 0 excluded, and every per-column numerator uses that same denominator. Counting only the joined
rows is the S35 defect; a census that reports coverage over the as-of table is circular -- if you find yourself doing that, say so and report REJECT yourself.
REPORT ALSO (measured today, not a bar): 443 of the 663 data/cache/venue_history/nba_close_corpus.parquet closes fall outside the 1,814 spine (331 in 2022-23, 1 in
2024-25, 111 in 2025-26), and 289 of those are non-placeholder (close_prob_home != 0.500) against 220 non-placeholder inside -- state what a full spine would attach.
EVIDENCE: docs/evidence/harness/nba_spine_census_2026-09-04.md -- before/after table, the full per-column x per-season census with denominators, the summary JSON and
the census rows copied under docs/evidence/, and a NOT VERIFIED list. Calibration language only (Q6): no dollar, ROI, profit or edge word in any artifact or line.
UNCHARGED: no prereg, no scored OOS comparison, no ledger row -- this is a coverage census, not a trial. Leave the FWER ledger at 18 rows, untouched.
TEST: exactly one new per-file test; run only that file.
POD: not needed -- local parquet reads only. No scp of any module.
COMMIT: explicit pathspec, in the worktree, no push. Report the sha. NEVER PARK: poll your own jobs in a blocking loop; never end waiting.
