GAP S296 | sport nba | worktree aXX | log cx_s296_full_boxscore_oof
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: audit gap 2 (S262 census): no durable OOF full box-score distribution vector exists; four median-only
  OOF stores (pts/reb/ast/blk q50) plus data/domains/basketball_nba/player_boxscores.parquet (77,744 rows) and
  data/cache/omni_box_refresh/nba_player_box_extension.parquet (1,023 rows) are the verified inputs (first ids
  2544@2022-10-18). S271 (a18) produces pts/reb/ast q10/q50/q90; this row extends to minutes + every field.
WHERE: local; pyarrow row-group reads of the two verified boxscore parquets.
PREMISE: reproduce 78,767 unique game_id+player_id rows and 3,645 games, with zero overlap.
LIMIT: if fewer than 30 held-out games for any stat, label that stat NOT SCORABLE.
CHANGE: emit strict-prior OOF samples and q10/q50/q90 for minutes and every box-score field.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Print RSS before/after; a scorer above 500 MB runs via ~/bin/pod_run <aN> --fetch <outputs> --
  <command> (B5 NOTE). Never write data/ or docs/research/; never rewrite an existing artifact (new dated names).
ACCEPTANCE RULE:
  metric = CRPS, q10/q50/q90 pinball, 80% coverage, energy score, coherence violations.
  before = no durable OOF player-game distribution vector; four median-only stores exist.
  bar = 0 future-label reads and 0 algebra violations; score differences reported with CIs.
  n = held-out player-games and game clusters, printed per stat and jointly.
  eye check = n/a; reproduction = rerun one fold and recompute every score from samples.
  must not move = source parquets, existing model files, existing quantile summaries.
NON-TAUTOLOGY: include DNPs, bench players, zeros, and every stat even when a baseline wins.
EVIDENCE: docs/evidence/harness/S296_full_boxscore_oof_2026-09-04.md plus samples/JSON.
REQUIRED EVIDENCE DURABILITY: archive samples, fold dates, paired scores, and source dates.
RE-EMITTED TABLES: game_id, player_id, date, all observed fields, all forecast fields.
TEST: one per-file test for strict prior dates, quantile order, and box-score identities.
REPORT: premise counts, the metric table with CIs, RSS, test line, SHA. No push. NEVER PARK.
