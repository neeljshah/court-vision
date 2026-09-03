GAP S202 | sport all (harness) | worktree aXX | log cx_s202_two_way_neff
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: docs/evidence/harness/REDTEAM_SIGNAL_FACTORY_2026-09-03.md:163 and :165, verbatim: "- The ICC table
uses `(y - p_base)**2` as a stand-in for a real paired Brier differential. The true design effect under a
fitted candidate is unmeasured and may differ." and "- Two-way (crossed home/away team) cluster-robust
variance was NOT computed; the NBA and MLB team-clustered n_eff figures are one-way and are a LOWER bound on
the correction." Every clustered CI and n_eff on a pregame corpus rests on that one table.
PREMISE (step 0): re-measure and print the ICC table (one-way random effects, n_eff = n/(1 + ICC*(mbar-1)),
via scripts/platformkit/ingame/gap_effective_n): NBA n 1,814 away_team 30 clusters ICC 0.0238 deff 2.41
n_eff 752; NBA home_team ICC 0.0035 deff 1.21 n_eff 1,502; MLB n 38,800 away_team 32 clusters ICC 0.0022
deff 3.67 n_eff 10,580; soccer n 25,834 div 6 clusters ICC 0.0004 deff 2.65 n_eff 9,733; tennis n 41,886
p1_id 1,613 clusters ICC 0.0041 deff 1.10 n_eff 37,962; on raw y, NBA home_team ICC 0.0808 deff 5.81 n_eff
312. Print MLB denominator drift (S05: 39,162 vs 38,800). If falsified, STOP, memo, commit, report FALSIFIED.
LIMIT (step 1): before changing anything, state which corpora can carry a crossed estimator -- it needs both
labels present, and soccer div (6) and NBA season (2) have too few clusters. Print the usable set with its
cluster counts; if fewer than two qualify, report CLOSED AT LIMIT and do not fix.
CHANGE (step 2): the smallest additive change -- one new module under scripts/platformkit/eval_gate/ that
(a) recomputes n_eff by a row-level bootstrap resampling BOTH team labels (crossed, >= 1,000 resamples, seed
recorded) and (b) re-runs the table on a REAL paired loss differential (the S05 recalibrated arm minus
p_base, per row) beside the stand-in. gap_effective_n.py read-only and byte-identical; new helper <= 300 lines,
inside test_loc_rail_scope.py counts; one corpus at a time; never write under data/.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = n_eff per corpus under (a) the existing one-way key and (b) the two-way bootstrap, each on
                  both the stand-in loss and the real paired differential, over the FIXED denominators 1,814 /
                  38,800 (or the re-measured MLB count, stated) / 25,834 / 41,886 rows
  before        = one-way n_eff 752 (NBA away_team), 10,580 (MLB away_team), 9,733 (soccer div), 37,962 (tennis)
  bar           = 4/4 corpora print a two-way n_eff beside the one-way one; the one-way figures reproduce
                  within 1 pct; >= 1,000 resamples with the seed recorded; the memo states plainly whether
                  the one-way figure is an upper bound on n_eff, and says so when it is not
  n             = 4 corpora on 1,814 / 38,800 / 25,834 / 41,886 rows (sampled metric, >= 30 satisfied)
  eye check     = n/a (S-row); reproduction = the verifier reruns the bootstrap at the recorded seed and
                  recomputes each n_eff from the emitted per-row loss series and cluster labels alone (Q9)
  must not move = gap_effective_n.py byte-identical; every published n_eff (S161/S196 re-quotes) and every
                  landed verdict untouched; backtest_fwer.jsonl untouched with K unread
NON-TAUTOLOGY: every row of each corpus stays in the denominator and no cluster is dropped for being small.
If a size filter is used, name it and the dropped count; if it is what makes n_eff look better, REJECT.
EVIDENCE: docs/evidence/harness/S202_two_way_neff_2026-09-04.md -- the one-way vs two-way table on both loss
definitions, cluster counts, the seed, a NOT VERIFIED list, and a summary JSON copied under docs/evidence/.
TEST: scripts/platformkit/eval_gate/test_s202_two_way_neff.py -- one new per-file test; run only that file.
REPORT: the eight n_eff values, seed, diff stat, test line, SHA. Commit by pathspec, no push. NEVER PARK.
