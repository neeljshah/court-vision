GAP S248 | sport nba (in-game) | worktree aXX | log cx_s248_nba_fatigue_conditioned_v2
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S201 CLOSED AT LIMIT (S201_VERIFY) because the two S92 archive CSVs were absent from that worktree, not
  because the fatigue premise was wrong. S216 attempt 2 independently re-opened the _all archive and reconfirmed its
  denominator and Brier order. Re-issue with the archive present, hard-linked into the worktree by the dispatcher.
PREMISE (step 0): re-measure and print from the two archives, now present at data/cache/eval_gate/: ALL frame
  79,554 ticks / 661 game clusters, 194 date folds (191 scored), 2024-10-25..2026-04-06; market 0.142876712852,
  recal_null 0.144293050901, ladder BASE 0.146849530547 (S216 attempt 2 independently confirmed this order);
  +fatigue_share 0.146948, +fatigue_min 0.147061, +unit_onoff 0.147247; improvements vs incumbent fatigue_min
  -0.000212 (DM p 0.4899, CI [-0.000814,+0.000390]), fatigue_share -0.000098 (0.7920,[-0.000828,+0.000632]),
  unit_onoff -0.000397 (0.2380,[-0.001058,+0.000263]), all SCREEN_NULL; n/n_informative/n_eff 79,554/72,555/3,185.1
  (fatigue_min). _rated.csv companion = 33,713 rows. If any headline is falsified, STOP, write the memo, FALSIFIED.
LIMIT (step 1): reproduce the three S92 improvements from the archive to max abs diff <= 1e-9 with NO refit before
  fitting any new form; if they do not reproduce, CLOSED AT LIMIT, name the failing column(s).
CHANGE (step 2): smallest additive change -- one new module under scripts/platformkit/eval_gate/ that screens
  EXACTLY THREE conditioned forms, fixed before the run, all reported win or lose: (a) fatigue_min x period, (b) x
  remaining time, (c) x absolute margin, from columns already in the CSV -- same rows, folds, clusters, incumbent
  as S92. Additive only; S92 archives byte-identical; helper <= 300 lines (test_loc_rail_scope.py); never write
  data/; no flag on; no edits under src/ kernel/ api/ intel/ scripts/team_system/.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = tick-weighted Brier improvement of each conditioned form vs incumbent 0.146850, with DM p,
                  game-clustered 95 pct CI and n_eff, over the fixed 79,554 ticks / 661 clusters
  before        = fatigue_min -0.000212, fatigue_share -0.000098, unit_onoff -0.000397 (all SCREEN_NULL)
  bar           = the three S92 improvements reproduce at max abs diff <= 1e-9; all three new forms reported with
                  improvement, DM p, CI, n_eff; a form is prereg DRAFT ONLY at improvement >= +0.004 with CI
                  excluding zero, else SCREEN_NULL (expected honest outcome). The +0.004 bar never moves
  n             = 661 (game clusters, >= 30)
  eye check     = n/a (S-row); reproduction = the verifier recomputes each improvement and CI from the emitted
                  per-tick loss differential series and cluster ids alone (Q9)
  must not move = the two S92 archive CSVs byte-identical; the S92 verdicts and the +0.004 bar; backtest_fwer.jsonl
                  untouched, K unread -- a SCREEN charges nothing
NON-TAUTOLOGY: rows, folds and clusters are S92's exactly, only the form differs; excluded dead-clock ticks (58.3
  pct) stay excluded. Dropping a losing form after the fact is circular -- report REJECT yourself.
EVIDENCE: docs/evidence/harness/S248_nba_fatigue_conditioned_v2_2026-09-04.md -- reproduction table, the three new
  rows with CIs and n_eff, the per-tick differential series under docs/evidence/, a NOT VERIFIED list.
TEST: scripts/platformkit/eval_gate/test_s248_fatigue_forms_v2.py -- one new per-file test; run only that file.
REPORT: three improvements with CIs, reproduction diff, test line, SHA. Commit by pathspec, no push. NEVER PARK.
