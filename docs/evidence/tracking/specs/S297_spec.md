GAP S297 | sport nba | worktree aXX | log cx_s297_minutes_dnp_distribution
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: audit gap 3 (S241): minutes and DNP mass are not distributionally modeled; verified inputs are the two
  boxscore parquets above (zero-minute rows 326/77,744 and 221/1,023). DNP rows stay in the denominator.
WHERE: local; pyarrow row-group reads of the two verified boxscore parquets.
PREMISE: reproduce zero-minute counts 326/77,744 and 221/1,023 before fitting.
LIMIT: if a forward fold has fewer than 30 games, emit INSUFFICIENT and do not pool it.
CHANGE: fit a DNP probability plus positive-minutes q10/q50/q90 with player partial pooling.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Print RSS before/after; a scorer above 500 MB runs via ~/bin/pod_run <aN> --fetch <outputs> --
  <command> (B5 NOTE). Never write data/ or docs/research/; never rewrite an existing artifact (new dated names).
ACCEPTANCE RULE:
  metric = candidate versus a train-fold empirical DNP-rate plus train-fold positive-minutes empirical-CDF
           baseline.
  before = no scored minutes quantiles; heuristic floor/ceiling are not quantiles.
  bar = baseline CRPS minus candidate CRPS > 0 with CI lower > 0; NULL is valid.
  sign = improvement = baseline loss minus candidate loss; positive = candidate better; compared with the frozen
         +0.004 bar.
  n = all held-out roster player-games and >= 30 held-out game clusters per fold; retain zero-minute rows.
  eye check = n/a; reproduction = refit one fold and replay paired scores.
  must not move = source parquets and existing minutes modules.
NON-TAUTOLOGY: never condition evaluation on playing or on target minutes >0.
EVIDENCE: docs/evidence/harness/S297_minutes_dnp_distribution_2026-09-04.md plus CSV/JSON.
REQUIRED EVIDENCE DURABILITY: archive DNP probability, quantiles, outcomes, folds, and losses.
RE-EMITTED TABLES: retain game_id/player_id/date and explicit DNP status.
TEST: one per-file test with DNP, short rotation, overtime, and future-row plant.
REPORT: premise counts, the metric table with CIs, RSS, test line, SHA. No push. NEVER PARK.
