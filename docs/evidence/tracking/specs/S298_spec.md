GAP S298 | sport nba | worktree aXX | log cx_s298_rare_count_mixture
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: audit gap 4: rare counts (STL/BLK) have no OOS hurdle/mixture comparison (quantile_calibration.py:74-80);
  verified inputs = the two boxscore parquets; the per-player sparsity is the named risk.
WHERE: local; pyarrow row-group reads of the two verified boxscore parquets.
PREMISE: reproduce STL/BLK zero counts and first three composite ids above.
LIMIT: if any model cannot produce a finite integer CDF, reject that model before scoring.
CHANGE: compare Poisson, negative-binomial, hurdle, and zero-inflated count forecasts.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Print RSS before/after; a scorer above 500 MB runs via ~/bin/pod_run <aN> --fetch <outputs> --
  <command> (B5 NOTE). Never write data/ or docs/research/; never rewrite an existing artifact (new dated names).
ACCEPTANCE RULE:
  metric = discrete log score, ranked probability score, zero reliability, randomized PIT.
  before = no OOS mixture-count comparison for STL/BLK on these player-games.
  bar = paired log-score improvement >0 with player/game-clustered CI above 0; NULL is valid.
  n = every held-out STL and BLK player-game; zero rows retained.
  eye check = n/a; reproduction = replay PMFs and paired scores from the archive.
  must not move = source parquets, quantile models, and calibration files.
NON-TAUTOLOGY: choose families on train folds only and publish every family, including worst.
EVIDENCE: docs/evidence/harness/S298_rare_count_mixture_2026-09-04.md plus PMF/CSV/JSON.
REQUIRED EVIDENCE DURABILITY: archive integer PMFs through a stated tail cutoff and losses.
RE-EMITTED TABLES: retain observed count, zero flag, ids, dates, and all model PMFs.
TEST: one per-file test for PMF sum, finite tails, zeros, and strict-prior features.
REPORT: premise counts, the metric table with CIs, RSS, test line, SHA. No push. NEVER PARK.
