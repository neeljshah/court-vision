"""fit_validity_gate_ingredients -- ingredient construction (archetype / team
scheme identity / role vacancy) for the V2 fit-validity gate. Split out of
fit_validity_gate_impl.py purely to keep that file under the 300-LOC cap; all
formulas here mirror fit_validity_gate_prereg_v2.json's `ingredient_formulas`
section verbatim (see that file for the authoritative spec text).

No independent authorization logic lives here -- this module is pure data
transformation, imported and called only by fit_validity_gate_impl.py after
that module has already validated run authorization.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ARCHETYPE_COLS = ["usg_pct", "ts_pct", "three_par", "ast_pct"]
SCHEME_COLS = ["usg_pct", "three_par", "ast_pct", "orb_pct"]
DOT_PRODUCT_COLS = ["usg_pct", "three_par", "ast_pct"]  # shared dims only, per V2 spec


def zscore_archetype(clean_season_rows: pd.DataFrame) -> pd.DataFrame:
    """(i) player archetype proxy: z-score ARCHETYPE_COLS within this
    season's OWN clean-player population (no cross-season leakage)."""
    raw = clean_season_rows[ARCHETYPE_COLS].astype(float)
    return (raw - raw.mean()) / raw.std(ddof=0).replace(0, np.nan)


def team_scheme_identity(clean_season_rows: pd.DataFrame) -> pd.DataFrame:
    """(ii) team scheme/style identity: mean of SCHEME_COLS per team,
    computed over the SAME clean-season row population."""
    return clean_season_rows.groupby("team")[SCHEME_COLS].mean()


def usage_tier_incumbent_counts(clean_season_rows: pd.DataFrame) -> tuple[pd.Series, dict[tuple[str, str], int]]:
    """(iii) role-vacancy scaffolding: per-team median usg_pct (the
    high/low usage-tier cutoff) and incumbent counts per (team, tier)."""
    usg_median_by_team = clean_season_rows.groupby("team")["usg_pct"].median()
    incumbents: dict[tuple[str, str], int] = {}
    for team, team_rows in clean_season_rows.groupby("team"):
        med = usg_median_by_team.loc[team]
        incumbents[(team, "high_usage")] = int((team_rows["usg_pct"] >= med).sum())
        incumbents[(team, "low_usage")] = int((team_rows["usg_pct"] < med).sum())
    return usg_median_by_team, incumbents


def compute_fit_score_for_mover(
    player_archetype_row: pd.Series,
    dest_scheme_vec: pd.Series,
    mover_usg_pct: float,
    dest_team: str,
    usg_median_by_team: pd.Series,
    incumbents: dict[tuple[str, str], int],
) -> float:
    """fit_score = dot(archetype[DOT_PRODUCT_COLS], scheme[DOT_PRODUCT_COLS])
    + vacancy_bonus, per the V2 spec's fit_score_composition formula.
    Vacancy is already bounded to (0, 1] by construction (1/(1+n)), so the
    spec's min-max rescaling step is an identity operation here -- see
    fit_validity_gate_impl.py's _min_max_scale_vacancy_component for the
    literal code anchor."""
    dot = float(sum(
        player_archetype_row[c] * dest_scheme_vec[c]
        for c in DOT_PRODUCT_COLS if pd.notna(player_archetype_row[c])
    ))
    dest_median = usg_median_by_team.get(dest_team, np.nan)
    tier = "high_usage" if pd.notna(mover_usg_pct) and pd.notna(dest_median) and mover_usg_pct >= dest_median else "low_usage"
    n_incumbents = incumbents.get((dest_team, tier), 0)
    vacancy = 1.0 / (1.0 + n_incumbents)
    return dot + vacancy
