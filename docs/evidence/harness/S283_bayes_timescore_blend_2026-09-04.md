# S283 NBA Bayesian time-score blend

## Verdict: BELOW_FROZEN_BAR

Preregistration: `docs/evidence/harness/S283_bayes_timescore_blend_2026-09-04_prereg.md`

Preregistration SHA-256: `e60457016bc5cb8ba10ed8d460a4593334456bed9a55ea2aedca3bfcd97cf224`

Premise binding re-run before scoring: `load_ticks` returned 465249 ticks / 1593 games. The source search found no empirical NBA time-score table in `scripts/platformkit` or `tests/platformkit`.

| arm | Brier | ECE |
|---|---:|---:|
| recal_null | 0.073453142 | 0.004746441 |
| blended | 0.213836845 | 0.038076661 |

Improvement (recal_null Brier minus blended Brier): -0.140383703 [-0.142998852, -0.137763256]. Frozen bar: +0.004.

## Sparsity and train-only selection

Scored ticks used full cells: 465060; named period_bucket parent fallback: 189.

| split | train ticks | scored ticks | chosen k | train Brier grid | train parent fallback ticks |
|---:|---:|---:|---:|---|---:|
| 0 | 280353 | 183867 | 0.5 | `{"0.5": 0.21193943355936154, "1.0": 0.22129586067544046, "2.0": 0.23114217935542467, "4.0": 0.23837916354455663}` | 157 |
| 1 | 384502 | 75409 | 0.5 | `{"0.5": 0.21199353473491203, "1.0": 0.22175981136434816, "2.0": 0.23195513582011068, "4.0": 0.23941786540385104}` | 45 |
| 2 | 383394 | 77756 | 0.5 | `{"0.5": 0.21099093128511343, "1.0": 0.22084422538046153, "2.0": 0.23125633881347324, "4.0": 0.23897596170076701}` | 184 |
| 3 | 390771 | 66891 | 0.5 | `{"0.5": 0.21367312107469502, "1.0": 0.22278293161002366, "2.0": 0.2323055925499019, "4.0": 0.23926565521001658}` | 189 |
| 4 | 398946 | 61326 | 0.5 | `{"0.5": 0.21599678111217688, "1.0": 0.2249908053269408, "2.0": 0.23432130835327156, "4.0": 0.24107452272117952}` | 181 |

## Method and reproduction

The shared evaluator ran once for each arm on identical per-tick states, with its symmetric purge and one-day embargo. Both callbacks fit only their supplied train membership. The recal_null callback applies the same `_recal` logistic calibration used by `apply_incumbent(kind="recal_null")`; the candidate callback builds the empirical table and selects k from the frozen grid on that membership.

The paired CSV is evaluator records only: each row stores both callback probabilities, losses, stable tick key, cluster id, timestamp, split, and train size. The archive is sufficient to recompute all reported Brier values and the clustered interval.

Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet` (2829826 bytes; tabular tick resolution). Route SHA-256: `861e9d387fbeaf65f78d082734ede26257b240307850e2bf120f16f1f1760bfb`. RSS at write: 1437413376 bytes.

Focused test: `python -m pytest tests/platformkit/ingame/test_s283_bayes_timescore_blend.py -q`.
