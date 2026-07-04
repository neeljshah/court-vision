"""Percentile normalization + pillar scoring for shooter/scorer_quality_v1.

Companion to quality_indices.py (data loading / factor extraction). Kept
separate to stay under the 300-LOC/file cap. Implements spec Section 2.1
(percentile normalization) and Section 2.5 (fallback / pillar-dropout
renormalization + coverage reporting).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from domains.basketball_nba.quality_indices import (
    PILLAR_FACTORS,
    QUALIFY_SEASON,
    SCORER_WEIGHTS,
    SHOOTER_WEIGHTS,
    load_qualifying_factor_table,
)

RAW_PERCENTILE_FACTORS = [
    "ts_pct", "efg_pct", "shot_quality_ts",
    "pullup_combined_freq", "pullup_pnr_ppp", "late_clock_shots_pg",
    "unassisted_share_3pm", "off_dribble_3_proxy",
    "gravity_score", "cs_gravity_efg", "spotup_ppp",
    "fg3a_per_game", "fga_per_game",
    "usage_rate", "drives_per_game", "minutes_pg",
    "unassisted_share_2pm", "iso_poss_pg", "pnr_handler_pg", "and_one_rate",
    "clutch_scoring_pts_per36",
]

# (raw column, inverted percentile column name) -- smaller raw = better
INVERTED_FACTOR_PAIRS = [
    ("scheme_robustness", "scheme_robustness_inv"),
    ("score_margin_consistency", "score_margin_consistency_inv"),
    ("blowout_gt_pct", "blowout_gt_pct_inv"),
]


def percentile_rank(series: pd.Series, invert: bool = False) -> pd.Series:
    """rank / (n-1) over non-null values (spec 2.1); NaN stays NaN (dropped
    from the pillar mean downstream, never imputed)."""
    s = series.astype(float)
    valid = s.dropna()
    n = len(valid)
    if n <= 1:
        return pd.Series([float("nan")] * len(s), index=s.index)
    ranks = valid.rank(method="average", ascending=not invert)
    pct = (ranks - 1) / (n - 1)
    out = pd.Series([float("nan")] * len(s), index=s.index)
    out.loc[pct.index] = pct
    return out


def build_percentile_table(t: pd.DataFrame) -> pd.DataFrame:
    """Percentile-rank every raw factor referenced by either index."""
    pct = pd.DataFrame(index=t.index)
    for f in RAW_PERCENTILE_FACTORS:
        pct[f] = percentile_rank(t[f])
    for raw_col, inv_col in INVERTED_FACTOR_PAIRS:
        pct[inv_col] = percentile_rank(t[raw_col], invert=True)
    return pct


def _pillar_score(pct: pd.DataFrame, factors: list[str], row_idx) -> float:
    vals = [pct.loc[row_idx, f] for f in factors if f in pct.columns]
    vals = [v for v in vals if pd.notna(v)]
    if not vals:
        return float("nan")
    return sum(vals) / len(vals)


def score_index(t: pd.DataFrame, pct: pd.DataFrame, index: str) -> pd.DataFrame:
    """Compute shooter_quality_v1 or scorer_quality_v1 with per-player
    pillar-dropout renormalization + coverage reporting (spec Section 2.5):
    a pillar missing for a player is dropped and the remaining pillar
    weights renormalized; `coverage` = fraction of total pillar weight
    retained, reported so a thinly-covered score is never presented as
    equal-confidence."""
    weights = SHOOTER_WEIGHTS if index == "shooter" else SCORER_WEIGHTS
    pillars = PILLAR_FACTORS[index]
    total_weight = sum(weights.values())

    scores, coverages, pillar_cols = [], [], {p: [] for p in weights}
    for idx in t.index:
        available_weight = 0.0
        weighted_sum = 0.0
        for pillar, w in weights.items():
            pv = _pillar_score(pct, pillars[pillar], idx)
            pillar_cols[pillar].append(pv)
            if pd.notna(pv):
                weighted_sum += w * pv
                available_weight += w
        if available_weight <= 0:
            scores.append(float("nan"))
            coverages.append(0.0)
        else:
            scores.append(weighted_sum / available_weight)
            coverages.append(available_weight / total_weight)

    out = t[["player_id", "player_name", "games", "naive_comp"]].copy()
    for pillar, vals in pillar_cols.items():
        out[f"pillar_{pillar}"] = vals
    out[f"{index}_quality_v1"] = scores
    out["coverage"] = coverages
    return out


@dataclass
class QualityIndexResult:
    factor_table: pd.DataFrame
    percentile_table: pd.DataFrame
    shooter: pd.DataFrame
    scorer: pd.DataFrame


def run(season: str = QUALIFY_SEASON) -> QualityIndexResult:
    t = load_qualifying_factor_table(season=season)
    pct = build_percentile_table(t)
    shooter = score_index(t, pct, "shooter").sort_values(
        "shooter_quality_v1", ascending=False, na_position="last"
    ).reset_index(drop=True)
    scorer = score_index(t, pct, "scorer").sort_values(
        "scorer_quality_v1", ascending=False, na_position="last"
    ).reset_index(drop=True)
    return QualityIndexResult(factor_table=t, percentile_table=pct, shooter=shooter, scorer=scorer)


if __name__ == "__main__":
    res = run()
    print(f"qualifying pool n={len(res.factor_table)}")
    print("--- shooter_quality_v1 top 10 ---")
    print(res.shooter[["player_name", "shooter_quality_v1", "coverage", "naive_comp"]].head(10).to_string(index=False))
    print("--- scorer_quality_v1 top 10 ---")
    print(res.scorer[["player_name", "scorer_quality_v1", "coverage", "naive_comp"]].head(10).to_string(index=False))
