# Cycle 90a (loop 5) — T1-A garbage-time haircut probe

## Spread source
- No `spread` column in any parquet; used `home_srs - away_srs + 2.5` as the implied-margin proxy.
- Source files: `data/nba/season_games_<season>.json` (rows: 4915 games covered, 15607/15662 = 99.6% of holdout matched).
- Holdout |margin| distribution: >=8 13.2%, >=12 2.4%, >=16 0.0%.

## Single-split MAE deltas (best param: spread 6/10/14 -> 0.98/0.95/0.92)

| stat | n | baseline_mae | adjusted_mae | delta_mae | verdict |
|------|---|--------------|--------------|-----------|---------|
| pts | 15662 | 4.5227 | 4.5207 | -0.0020 | BETTER |
| reb | 15662 | 1.9159 | 1.9176 | +0.0017 | worse |
| ast | 15662 | 1.3143 | 1.3136 | -0.0007 | flat |
| fg3m | 15662 | 0.8542 | 0.8542 | +0.0000 | flat |
| stl | 15662 | 0.6617 | 0.6617 | +0.0000 | flat |
| blk | 15662 | 0.4062 | 0.4062 | +0.0000 | flat |
| tov | 15662 | 0.8331 | 0.8331 | +0.0000 | flat |

Aggregate PTS+REB+AST delta: -0.0010

n_improved: 1/7

## Param sweep summary

| thresholds | factors | n_improved | PTS+REB+AST delta |
|------------|---------|------------|-------------------|
| 8/12/16 | 0.97/0.93/0.88 | 1/7 | -0.0003 |
| 8/12/16 | 0.98/0.95/0.92 | 1/7 | -0.0007 |
| 10/14/18 | 0.97/0.93/0.88 | 1/7 | -0.0009 |
| 6/10/14 | 0.98/0.95/0.92 | 1/7 | -0.0010 |
| 8/16 | 0.95/0.88 | 1/7 | -0.0008 |

## Walk-forward 4-fold (best param: spread 6/10/14 -> 0.98/0.95/0.92)

Chronological-split of the holdout (no model retrain — post-prediction adjustment).

| stat | fold1 | fold2 | fold3 | fold4 | mean | folds<0 |
|------|-------|-------|-------|-------|------|---------|
| pts | -0.0113 | -0.0014 | +0.0014 | +0.0034 | -0.0020 | 2/4 |
| reb | +0.0021 | +0.0018 | +0.0020 | +0.0010 | +0.0017 | 0/4 |
| ast | -0.0026 | -0.0008 | -0.0001 | +0.0004 | -0.0007 | 2/4 |

## Data caveat (important)

`season_games_*.json` covers 2021-10 -> 2025-04-13. The default 80/20
holdout (last 20% of all rows) is entirely within the 2025-26 season,
which has NO spread/SRS data. The probe therefore re-split chronologically
WITHIN the spread-coverage window only (effective n=78307, holdout=15662,
all in 2024-25 season). If the haircut is to be re-tested on the canonical
holdout, 2025-26 team-level SRS / pre-game spreads must be backfilled
first (e.g. by aggregating box scores into team net rating + ELO, or
scraping closing spreads from data/lines/).

## Verdict

- Single-split pass: False (n_improved>=4 and PTS+REB+AST delta < 0 with >=1 stat <=-0.005)
- WF pass (PTS/REB/AST 4/4 folds): False

**Effect summary (rejected but directionally informative):**
- PTS: directional theory holds (-0.0020 best, -0.0113 in earliest WF fold) — but signal magnitude is below the 0.005 MAE ship gate by 2-5x, and the effect is non-monotone across WF folds (fold4 actually regresses +0.0034).
- AST: similar direction but smaller magnitude.
- REB: REGRESSES consistently (+0.0014 to +0.0021 single-split, 0/4 WF folds positive). Rebounds may not scale linearly with minutes during blowout sequences — late-game garbage-time bigs still grab rebounds against bench units.
- FG3M/STL/BLK/TOV: explicitly skipped (per cycle 89f T1-A — no minute-driver signal).

**Next-cycle implications:**
- The pre-game implied-margin signal is too weak (only 13% of holdout >= 8pt spread, only 2.4% >= 12pt) to move the holdout MAE noticeably with a multiplicative scaler.
- A SHARPER conditioning is needed: e.g. (margin >= 12) AND (player is starter) AND (game has 3+ stars-rested signal). The probe rejected the BROAD form; a narrower form might still ship.
- REB needs an OPPOSITE-direction adjustment (or pure no-op) — DO NOT couple REB to the same haircut as PTS/AST.

**VERDICT: REJECT**

**Rejection rationale:**
- single-split insufficient (n_improved=1/7, PTS+REB+AST delta=-0.0010, per-stat: PTS -0.0020, REB +0.0017, AST -0.0007; need n_improved>=4 AND at least one of PTS/REB/AST <= -0.005)
- PTS WF only 2/4 folds improved
- REB WF only 0/4 folds improved
- AST WF only 2/4 folds improved
