GAP S296 | sport nba | worktree a17 | log cx_s296_full_boxscore_oof
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
DEPENDENCY: dispatch after S271 lands. If its memo or ledger line is absent at run time, run the landed S271 module
  path only if present; otherwise CLOSE AT LIMIT and state the reason.
CONTEXT: audit gap 2 (S262 census): no durable OOF full box-score distribution vector exists; four median-only
  OOF stores (pts/reb/ast/blk q50) plus data/domains/basketball_nba/player_boxscores.parquet (77,744 rows) and
  data/cache/omni_box_refresh/nba_player_box_extension.parquet (1,023 rows) are the verified inputs.
INPUTS: name data/cache/{pts,reb,ast}_q50_oof_int95.parquet and data/cache/blk_q50_oof_int90.parquet; print each
  first 3 ids separately.
FIRST IDS: PTS/REB/AST start 2544@2022-10-18; BLK starts 1626149@2022-10-18.
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
  bar = zero future-label reads, zero algebra violations, and every score reported against a named train-only
        empirical baseline with paired CIs.
  sign = improvement = baseline loss minus candidate loss; positive = candidate better; compared with the frozen
         +0.004 bar.
  n = held-out player-games and game clusters, printed per stat and jointly.
  eye check = n/a; reproduction = rerun one fold and recompute every score from samples.
  must not move = source parquets, existing model files, existing quantile summaries.
NON-TAUTOLOGY: include DNPs, bench players, zeros, and every stat even when a baseline wins.
EVIDENCE: docs/evidence/harness/S296_full_boxscore_oof_2026-09-04.md plus samples/JSON.
REQUIRED EVIDENCE DURABILITY: archive samples, fold dates, paired scores, and source dates.
RE-EMITTED TABLES: game_id, player_id, date, all observed fields, all forecast fields.
TEST: one per-file test for strict prior dates, quantile order, and box-score identities.
REPORT: premise counts, the metric table with CIs, RSS, test line, SHA. No push. NEVER PARK.

## VERSION 2026-09-07 (finish audit)
ABSORBS the S292 feasibility PREFLIGHT and the full field list (MERGED 2026-09-07; no separate dispatch). EVERY
acceptance clause above is RETAINED UNCHANGED; the clauses below are ADDED.
PREFLIGHT FROM S292 -- runs BEFORE any fit; a count that fails to reproduce is FALSIFIED and closes the preflight
  honestly. Label each of the four archived inputs TESTABLE or NOT_TESTABLE_TODAY with its exact blocking fact:
  data/cache/prop_calibration_history.parquet 4,942 player-stat AGGREGATE rows (7 stats, no per-game rows);
  data/cache/props_eval_nba_calibration.json overall n=356,678, aggregate only; data/cache/prop_sigma_scale.json rolling
  scale factors with no archived per-game residuals; data/frontend/prop_history_corpus.jsonl 3,000 rows with
  market_prob NULL on ALL 3,000 (no market comparison possible), 15 unique prop_player ids, 619 unique player-game
  pairs, model_prob tail bins <= 0.05: 21 rows and >= 0.90: 20 rows (both below n=30). n = 4 (CONSTRUCT, exhaustive).
  RETAINED DISTINCTION: aggregate vs per-bet granularity and the LACK of market comparisons are reported as blocking
  facts, never omitted; S262/S271 already distinguish absent intervals from new quantiles.
ADDED FULL FIELD LIST -- archive full PMFs or joint samples PLUS q10/q50/q90 for each of: min, pts, reb, oreb, dreb,
  ast, stl, blk, tov, fgm, fga, fg3m, fg3a, ftm, fta, pf, plus_minus. RECOUNT the two exact boxscore parquets before
  fitting (union 78,767 unique player-games / 3,645 games, zero overlap, zero source algebra violations). PRESERVE
  recorded zero-minute players and DISTINGUISH missing roster records from observed DNPs. The baseline is the
  strict-past empirical and the candidate is strict-past too.
ADDED BARS: 0 future-label dependencies, 0 sample algebra violations, no missing keyed fields; per-field CRPS, pinball
  and coverage plus joint train-scaled ENERGY CIs; >= 30 held-out games per scored fold; nominal q10-q90 = 0.80 with
  endpoint exceedances and discrete atoms reported. ALL comparative NULLs are valid results. CRPS, pinball, log score
  and energy have their OWN units -- the +0.004 bar is not their threshold.
ADDED TESTS: key uniqueness, truncation, an unseen player, a DNP, signed plus_minus, makes <= attempts, and the PTS/REB
identities checked ON SAMPLES (never on marginal quantiles), plus an independent fold and score replay.
