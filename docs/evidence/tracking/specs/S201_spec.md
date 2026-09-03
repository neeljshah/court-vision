GAP S201 | sport nba (in-game) | worktree a14 | log cx_s201_nba_fatigue_conditioned
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: docs/evidence/harness/S92_nba_lineup_dynamic_2026-09-03.md:205, verbatim: "* Fatigue is entered as a
raw home-minus-away minutes difference with no interaction (period, remaining time, margin, rest days,
back-to-back). A conditioned form was NOT screened; only this construction is refuted." A re-screen only.
PREMISE (step 0): re-measure and print from the S92 archive: ALL frame 79,554 ticks / 661 game clusters, 194
date folds (191 scored) 2024-10-25..2026-04-06; market 0.142877, S94 recal null 0.144293, incumbent ladder
BASE 0.146850, +fatigue_share 0.146948, +fatigue_min 0.147061, +unit_onoff 0.147247; improvements vs
incumbent fatigue_min -0.000212 (DM p 0.4899, CI [-0.000814, +0.000390]), fatigue_share -0.000098 (0.7920,
[-0.000828, +0.000632]), unit_onoff -0.000397 (0.2380, [-0.001058, +0.000263]), all three SCREEN_NULL;
n / n_informative / n_eff 79,554 / 72,555 / 3,185.1 (fatigue_min). One store only:
data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv plus _rated.csv (33,713 rows). If a headline
is falsified, STOP, write the memo, commit, report FALSIFIED.
LIMIT (step 1): reproduce the three S92 improvements from the archive to 1e-9 with NO refit before fitting any
new form; if they do not, the archive is unusable -- report CLOSED AT LIMIT and name the failing columns.
CHANGE (step 2): the smallest additive change -- one new module under scripts/platformkit/eval_gate/ that
screens EXACTLY THREE conditioned forms, fixed before the run and all reported win or lose: (a) fatigue_min
x period, (b) x remaining time, (c) x absolute margin, from columns already in the CSV -- same rows, folds,
clusters and incumbent as S92. Additive: new module plus new CSV/JSON under docs/evidence/; S92 archives
byte-identical; new helper <= 300 lines, inside test_loc_rail_scope.py counts; never write under data/.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = tick-weighted Brier improvement of each conditioned form vs the S92 incumbent 0.146850, with
                  DM p, game-clustered 95 pct CI and n_eff, over the FIXED denominator 79,554 ticks / 661 clusters
  before        = fatigue_min -0.000212, fatigue_share -0.000098, unit_onoff -0.000397 (all SCREEN_NULL)
  bar           = the three S92 improvements reproduce from the archive at max abs diff <= 1e-9; all three new
                  forms reported with improvement, DM p, clustered CI and n_eff; a form is a prereg DRAFT
                  candidate ONLY at improvement >= +0.004 with a CI excluding zero, else SCREEN_NULL (the
                  expected honest outcome, published as such). The +0.004 bar never moves
  n             = 661 (game clusters, >= 30)
  eye check     = n/a (S-row); reproduction = the verifier recomputes each improvement and CI from the emitted
                  per-tick loss differential series and cluster ids alone (Q9)
  must not move = the two S92 archive CSVs byte-identical; the S92 verdicts and the +0.004 bar;
                  data/cache/eval_gate/backtest_fwer.jsonl untouched with K unread -- a SCREEN charges nothing
NON-TAUTOLOGY: rows, folds and clusters are S92's exactly, only the form differs; the dead-clock ticks S92
excluded (58.3 pct) stay excluded and the memo says so. Dropping a losing form after the fact is circular
-- report REJECT yourself. A SCREEN is a non-finding: no prereg, no charge, no AHEAD.
EVIDENCE: docs/evidence/harness/S201_nba_fatigue_conditioned_2026-09-04.md -- reproduction table, the three new
rows with CIs and n_eff, the per-tick differential series copied under docs/evidence/, a NOT VERIFIED list.
TEST: scripts/platformkit/eval_gate/test_s201_fatigue_forms.py -- one new per-file test; run only that file.
REPORT: three improvements with CIs, reproduction diff, test line, SHA. Commit by pathspec, no push. NEVER PARK.
