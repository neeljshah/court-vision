# S283 NBA Bayesian time-score blend: fix 1b

## Verdict: BELOW_FROZEN_BAR

Preregistration: `docs/evidence/harness/S283_bayes_timescore_blend_2026-09-04_prereg_attempt2.md`

Preregistration SHA-256: `e60457016bc5cb8ba10ed8d460a4593334456bed9a55ea2aedca3bfcd97cf224`

Seal verification: the LF-normalized content before `Seal SHA-256:` hashes to `e60457016bc5cb8ba10ed8d460a4593334456bed9a55ea2aedca3bfcd97cf224`, equal to the embedded attempt-2 seal.

## Premise census

The archived tick data were loaded with `load_ticks` only; no scorer, selection, or output writer ran for this correction. The archive returned 465249 ticks across 1593 game clusters and all 27 observed `period_bucket x margin_bucket x rem_bucket` cells. The source search found no empirical NBA time-score table in `scripts/platformkit` or `tests/platformkit`.

| period_bucket | margin_bucket | rem_bucket | ticks |
|---|---|---|---:|
| OT | blowout_gt12 | rem_02_06 | 1 |
| OT | blowout_gt12 | rem_le02 | 134 |
| OT | close_le5 | rem_02_06 | 595 |
| OT | close_le5 | rem_le02 | 10481 |
| OT | mid_06_12 | rem_02_06 | 54 |
| OT | mid_06_12 | rem_le02 | 3500 |
| P1 | blowout_gt12 | rem_gt12 | 2563 |
| P1 | close_le5 | rem_gt12 | 28024 |
| P1 | mid_06_12 | rem_gt12 | 13841 |
| P2 | blowout_gt12 | rem_gt12 | 16404 |
| P2 | close_le5 | rem_gt12 | 27078 |
| P2 | mid_06_12 | rem_gt12 | 25343 |
| P3 | blowout_gt12 | rem_06_12 | 1251 |
| P3 | blowout_gt12 | rem_gt12 | 16943 |
| P3 | close_le5 | rem_06_12 | 848 |
| P3 | close_le5 | rem_gt12 | 16050 |
| P3 | mid_06_12 | rem_06_12 | 857 |
| P3 | mid_06_12 | rem_gt12 | 16696 |
| P4 | blowout_gt12 | rem_02_06 | 6742 |
| P4 | blowout_gt12 | rem_06_12 | 10661 |
| P4 | blowout_gt12 | rem_le02 | 102417 |
| P4 | close_le5 | rem_02_06 | 4867 |
| P4 | close_le5 | rem_06_12 | 7369 |
| P4 | close_le5 | rem_le02 | 58786 |
| P4 | mid_06_12 | rem_02_06 | 4981 |
| P4 | mid_06_12 | rem_06_12 | 7943 |
| P4 | mid_06_12 | rem_le02 | 80820 |

## Measured calibration row (frozen; not rerun)

| arm | Brier | ECE |
|---|---:|---:|
| recal_null | 0.073453142 | 0.004746441 |
| blended | 0.213836845 | 0.038076661 |

Sign convention: improvement = baseline loss minus candidate loss; positive = candidate better. Here the baseline is recal_null Brier and the candidate is blended Brier. Improvement: -0.140383703 [-0.142998852, -0.137763256]. Frozen bar: +0.004. This row is BEHIND.

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

Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet` (2829826 bytes; tabular tick resolution). Route SHA-256 before this correction: `861e9d387fbeaf65f78d082734ede26257b240307850e2bf120f16f1f1760bfb`. RSS at write: 1437413376 bytes.

The existing paired CSV and summary JSON were not regenerated. They remain byte-identical. The only script edit corrects its generated preregistration path; its measurement outputs were not rerun and remain unchanged.

Focused test: `python -m pytest tests/platformkit/ingame/test_s283_bayes_timescore_blend.py -q -p no:cacheprovider`.

## NOT VERIFIED

- A1 master rerun is unavailable pre-landing: the focused candidate test is absent on master, so the required master command reports 0 tests.
- Strict chronological-prior train membership is not verified: the CPCV train memberships straddle test blocks. The reported table outcomes are out-of-sample under the evaluator split, but this does not establish strictly chronological-prior training beyond the acceptance rule.
