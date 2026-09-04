GAP S207 | sport all (in-game) | worktree a16 | log cx_s207_ingame_gap_decomposition
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: docs/evidence/calibration-decomposition.md decomposes the in-game gap for two corpora only -- "mlb | 78,986 |
0.237684 | 0.206653 | +0.0310 | +0.0066 | -0.0235" and "soccer_intl | 9,003 | 0.227887 | 0.142726 | +0.0852 | +0.0394
| -0.0446", both "driven mainly by resolution". NBA (465,249 ticks / 1,593 games, S86) and WNBA (18,650 ticks / 85
games) were never decomposed, so no lane knows whether recalibration can pay there. Item 10 of
docs/research/model_quality_methods_2026-09-04.md adds the tick-age axis.
PREMISE (step 0): re-measure and print the two decomposition rows above and the two n-weighted ECE rows ("mlb | 78,986
| 0.079 | 0.0591" and "soccer_intl | 9,003 | 0.3609 | 0.2511"), and confirm by a named grep that no docs/evidence
artifact carries a Murphy decomposition or a max-loser-WP path statistic for nba or wnba. If falsified, STOP, memo,
commit, report FALSIFIED.
LIMIT (step 1): count game PATHS (games with at least one scored tick) per corpus -- mlb, soccer_intl, nba, wnba --
and print them before anything is decomposed. A corpus under 30 paths is descriptive only and labelled UNDERPOWERED;
never dropped.
CHANGE (step 2): smallest additive change -- a read-only reporter under scripts/platformkit/analytics_showcase/
running the EXISTING Murphy decomposition and state-conditioned bucketing over all four tick corpora, adding a
tick-age axis and the per-path max-loser-WP; the two landed JSONs are not regenerated. Additive only, nothing renamed;
helper <= 300 lines within test_loc_rail_scope.py; never write data/; no flag on; no edits in src/ kernel/ api/ intel/
scripts/team_system/; one store at a time, never > 300 MB; never touch register or ledger.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per corpus: model Brier, market Brier, Brier gap, reliability gap, resolution gap, n-weighted ECE
                  both sides, and the per-path max-loser-WP share above 0.8 both sides; denominators = the printed
                  scored-tick counts (mlb 78,986; soccer_intl 9,003; nba and wnba from step 1)
  before        = 2 of 4 corpora decomposed (mlb, soccer_intl, numbers above); 0 of 4 carry a tick-age axis; 0 of 4
                  carry a per-path max-loser-WP (S43: degenerate on the pregame corpora)
  bar           = 4 of 4 corpora with all nine quantities, the mlb and soccer_intl reliability and resolution gaps
                  reproducing at max abs diff <= 1e-6, each corpus labelled RELIABILITY-DOMINATED or
                  RESOLUTION-DOMINATED by its own gaps. A resolution-dominated corpus is the expected valid result
  n             = game paths per corpus, printed; >= 30 for a non-UNDERPOWERED label
  eye check     = n/a (S-row); reproduction = the verifier recomputes both Murphy terms and the ECE for two corpora
                  from the new artifact's own bins and confirms the two published rows reproduce
  must not move = murphy_decomposition.json and state_conditioned_calibration.json byte-identical (write NEW
                  artifacts); every eval_gate threshold; backtest_fwer.jsonl untouched, K unread
NON-TAUTOLOGY: every scored tick stays in its denominator; held ticks (S87: mlb 74.97 pct held market, 91.71 pct held
model) are counted beside the raw n, never removed. Informative-tick only, without the raw denominator, is circular --
REJECT.
EVIDENCE: docs/evidence/harness/S207_ingame_gap_decomposition_2026-09-04.md -- the 4-corpus table, the tick-age axis,
the max-loser-WP table, a NOT VERIFIED list, summary JSON and per-bin counts (Q9).
TEST: scripts/platformkit/analytics_showcase/test_s207_gap_decomposition.py -- one new per-file test; run only it.
REPORT: the 4-corpus table, the two reproduction diffs, test line, SHA. Commit by pathspec, no push. NEVER PARK.
