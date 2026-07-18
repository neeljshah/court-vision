"""Per-file tests for quality_validity_gate_claims_2025_26.py (2025-26
atlas-degraded sibling of quality_validity_gate_claims.py). Fully synthetic
factor table -- no disk I/O, no real atlas/boxscore parquet needed.
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba import quality_validity_gate_claims_2025_26 as q26
from domains.basketball_nba.quality_indices import QUALIFY_SEASON, SCORER_WEIGHTS, SHOOTER_WEIGHTS

# every raw column build_percentile_table/score_index touch, ATLAS_DERIVED_COLS
# among them (see quality_indices_score.RAW_PERCENTILE_FACTORS + inverted pairs).
_RAW_COLS = [
    "ts_pct", "efg_pct", "shot_quality_ts",
    "pullup_combined_freq", "pullup_pnr_ppp", "late_clock_shots_pg",
    "unassisted_share_3pm", "off_dribble_3_proxy",
    "gravity_score", "cs_gravity_efg", "spotup_ppp",
    "fg3a_per_game", "fga_per_game",
    "usage_rate", "drives_per_game", "minutes_pg",
    "unassisted_share_2pm", "iso_poss_pg", "pnr_handler_pg", "and_one_rate",
    "clutch_scoring_pts_per36",
    "scheme_robustness", "score_margin_consistency", "blowout_gt_pct",
]


def _synthetic_factor_table(n: int = 5) -> pd.DataFrame:
    df = pd.DataFrame({c: [float(i + 1) for i in range(n)] for c in _RAW_COLS})
    df["player_id"] = list(range(1, n + 1))
    df["player_name"] = [f"Player {i}" for i in range(1, n + 1)]
    df["games"] = 70
    df["naive_comp"] = 0.55
    return df


def test_run_indices_for_season_nulls_atlas_cols_for_non_qualify_season(monkeypatch):
    monkeypatch.setattr(q26, "load_qualifying_factor_table", lambda season: _synthetic_factor_table())
    result = q26.run_indices_for_season("2025-26")
    for col in q26.ATLAS_DERIVED_COLS:
        if col in result.factor_table.columns:
            assert result.factor_table[col].isna().all()
    # boxscore-derived cols must survive untouched
    assert not result.factor_table["fg3a_per_game"].isna().any()


def test_run_indices_for_season_is_pass_through_at_qualify_season(monkeypatch):
    """QUALIFY_SEASON must go through quality_indices_score.run() unmodified
    -- byte-stable, no nulling."""
    calls = []
    monkeypatch.setattr(
        "domains.basketball_nba.quality_validity_gate_claims_2025_26.run_indices",
        lambda season: calls.append(season) or "SENTINEL",
    )
    out = q26.run_indices_for_season(QUALIFY_SEASON)
    assert out == "SENTINEL"
    assert calls == [QUALIFY_SEASON]


def test_degraded_ranking_claim_renormalizes_present_pillars_only(monkeypatch):
    monkeypatch.setattr(q26, "load_qualifying_factor_table", lambda season: _synthetic_factor_table())
    result = q26.run_indices_for_season("2025-26")
    claim = q26.degraded_ranking_claim(
        "test_claim_id", "test question?", SHOOTER_WEIGHTS, result.shooter,
        "shooter_quality_v1", "shooter", "2025-26", "2026-01-01T00:00:00+00:00", len(result.factor_table),
    )
    present = [p for p in SHOOTER_WEIGHTS if p not in q26.ATLAS_ONLY_PILLARS["shooter"]]
    assert set(claim["criteria"]["weights"].keys()) == set(present)
    assert abs(sum(claim["criteria"]["weights"].values()) - 1.0) < 1e-6
    assert claim["criteria"]["window"] == "2025-26"
    assert claim["edge_claimed"] is False
    joined = " ".join(claim["caveats"])
    assert "ATLAS-UNAVAILABLE-2025-26" in joined
    assert "DIFFICULTY" in joined and "GRAVITY" in joined


def test_build_season_claims_shape(monkeypatch):
    monkeypatch.setattr(q26, "load_qualifying_factor_table", lambda season: _synthetic_factor_table())
    claims = q26.build_season_claims({"shooter": SHOOTER_WEIGHTS, "scorer": SCORER_WEIGHTS}, "2025-26")
    assert len(claims) == 2
    ids = {c["claim_id"] for c in claims}
    assert ids == {
        "nba_shooter_quality_v1_full_season_2025_26",
        "nba_scorer_quality_v1_full_season_2025_26",
    }
    for c in claims:
        assert c["criteria"]["window"] == "2025-26"
        assert c["kind"] == "ranking"
