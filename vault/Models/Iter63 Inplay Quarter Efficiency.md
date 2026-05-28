# Iter 63 — Inplay Quarter Efficiency Features (REVERT)

**Date:** 2026-05-27
**Probe script:** `scripts/iter63_inplay_quarter_efficiency.py`
**Results JSON:** `data/cache/iter63_inplay_qbox_results.json`
**Status:** REVERT (3/3 snapshots fail both coverage AND Brier gates)

## Hypothesis

At each endQ snapshot, per-team cumulative shooting efficiency and TOV rate are
leading indicators of subsequent quarters' outcomes beyond raw point totals.
The current endQ1 model has zero quality-of-scoring signal — only score_margin,
total_pts, pace, q1_delta, last_q_margin, pregame_wp, home_team_id, season.

## Features added (10)

- `home_ts_pct_cum`, `away_ts_pct_cum` — TS% = PTS / (2 * (FGA + 0.44*FTA))
- `home_efg_pct_cum`, `away_efg_pct_cum` — (FGM + 0.5*3PM) / FGA
- `home_tov_per_poss_cum`, `away_tov_per_poss_cum` — TO / approx possessions
- `home_ft_rate_cum`, `away_ft_rate_cum` — FTA / FGA
- `home_oreb_pct_cum`, `away_oreb_pct_cum` — OREB / (OREB + opp_DREB)

Cumulative through end of last completed quarter (endQ1 = Q1 only, endQ2 =
Q1+Q2, endQ3 = Q1+Q2+Q3). Built from `data/cache/quarter_box/*.json`.

## Coverage

`data/cache/quarter_box/` contains 1,299 game files. After joining to the
inplay training table (3,685 games), only **1,180 games** carry the new
efficiency features — 32% coverage. **Coverage gate fail** (threshold 1,500).

This is the same sample-bias concern the roadmap calls out: training on
3,685 rows where 68% have NaN for the new features means LightGBM splits
that fire on real efficiency values only fire for one slice of seasons,
introducing distribution shift.

## WF Results (4-fold expanding, same split as `oos_validate_inplay_2026_05_27.py`)

| Snapshot | v1 Mean Brier | v2_qbox Mean Brier | Delta    | Folds Improved | Verdict |
|----------|---------------|--------------------|----------|----------------|---------|
| endQ1    | 0.2221        | 0.2376             | +0.0155  | 0/4            | REVERT  |
| endQ2    | 0.1860        | 0.1944             | +0.0084  | 0/4            | REVERT  |
| endQ3    | 0.1354        | 0.1403             | +0.0049  | 0/4            | REVERT  |

Baseline values exactly reproduce the OOS validator from 2026-05-27.

Per-fold deltas (all positive = all worse):

- endQ1: [+0.0000, +0.0269, +0.0250, +0.0100]
- endQ2: [+0.0000, +0.0073, +0.0215, +0.0046]
- endQ3: [+0.0000, +0.0032, +0.0033, +0.0132]

Fold 0 is identical to v1 because all 2,211 training rows in the earliest
fold sit in the NaN region (qbox data started later in the season set), so
LightGBM never picked the new features. Folds 1–3 progressively include
qbox-covered rows and all regress.

## Why it failed

1. **Sample bias.** The qbox-covered rows aren't a random sample — they
   cluster in specific seasons. The model learns split rules that don't
   generalize across the full row distribution.
2. **NaN-handling noise.** LightGBM's default NaN routing pushed uncovered
   rows down whichever branch was statistically optimal on covered rows,
   propagating the bias.
3. **Information overlap.** TS%, eFG%, TOV rate at endQ1 are largely a
   function of `total_pts`, `score_margin`, and `pace_so_far` after 12
   minutes. The model may already extract this implicitly. At endQ3 the
   margin has converged enough that efficiency residuals don't help.

## Decision

REVERT. No new models saved. New artifacts kept (parquet + JSON) for audit
and to enable a future re-run once quarter_box coverage exceeds 80% of
the training set.

## Files

- NEW `scripts/iter63_inplay_quarter_efficiency.py`
- NEW `data/cache/inplay_qbox_efficiency.parquet` (3,757 rows / 1,253 games)
- NEW `data/cache/iter63_inplay_qbox_results.json`
- NEW `vault/Models/Iter63 Inplay Quarter Efficiency.md` (this file)
- DID NOT TOUCH `data/models/inplay_winprob_endq{1,2,3}.lgb` or `_meta.json`
- DID NOT CREATE `*_v2_qbox.lgb` / `*_v2_qbox_meta.json` (ship gate failed)

## Next builds

- Backfill `quarter_box/` for the missing 2,432 games (need a fetcher
  against `boxscoretraditionalv2`/`boxscoresummaryv2` per quarter).
- Once coverage >= 80%, re-run this iter directly — script is idempotent.
- Alternative: try **opponent-efficiency-allowed** features at the
  pregame level (rolling per-quarter L10 def-eff splits) since those
  have full historical coverage from `season_games` + advanced boxscores.
