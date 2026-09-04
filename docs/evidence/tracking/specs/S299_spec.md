GAP S299 | sport nba | worktree aXX | log cx_s299_forward_vs_cpcv
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: audit gap 5: the headline design mixes forward walk-forward and symmetric CPCV (cpcv_engine.py:12-18,
  walkforward.py:122-156); this row measures design sensitivity on one frozen tail calibrator (S272's) and
  labels it, never promotes it. Input: nba_checkpoints_full.parquet (465,249 / 1,593).
WHERE: local; pyarrow row-group reads of verified NBA checkpoints only.
PREMISE: reproduce S272 Brier/ECE, two season groups, and the fixed one-day embargo.
LIMIT: if exact S272 replay fails to 1e-12, stop and report NOT REPRODUCED.
CHANGE: score one frozen tail calibrator by forward-only walk-forward and symmetric CPCV.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Print RSS before/after; a scorer above 500 MB runs via ~/bin/pod_run <aN> --fetch <outputs> --
  <command> (B5 NOTE). Never write data/ or docs/research/; never rewrite an existing artifact (new dated names).
ACCEPTANCE RULE:
  metric = all-tick/tail Brier, tail log-loss/ECE, and paired design differences with CIs.
  before = S272 candidate improvement -0.000037 and tail ECE change -0.000248.
  bar = no promotion test; label DESIGN-SENSITIVE if any primary score CI excludes 0.
  n = 465,249 ticks / 1,593 games, with one prediction per game-tick per design.
  eye check = n/a; reproduction = replay both designs and paired differences.
  must not move = source, S272 artifacts, split constants, or +0.004 bar.
NON-TAUTOLOGY: forward-only is the deployment headline; CPCV is a robustness companion.
EVIDENCE: docs/evidence/harness/S299_forward_vs_cpcv_2026-09-04.md plus CSV/JSON.
REQUIRED EVIDENCE DURABILITY: archive fold membership, fitted parameters, and tick losses.
RE-EMITTED TABLES: retain all state ids, timestamps, split ids, and training date bounds.
TEST: one per-file test proving future blocks never enter the forward fit.
REPORT: premise counts, the metric table with CIs, RSS, test line, SHA. No push. NEVER PARK.
