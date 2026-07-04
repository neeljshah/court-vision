"""Tests for domains/mlb/props_eval_shootout2_mlb.py + _families.py (LANE 4,
PROPS BASELINE SHOOTOUT #2, queue item 4).

Covers: shrinkage math (shrink_rate), fit-window-only k (no-leak property --
k fit on 2022-2023 data cannot change when holdout-only rows are added/removed),
and family determinism (same inputs -> same lam candidates, run to run).

Per-file pytest only:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_props_eval_shootout2_mlb.py -q
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from domains.mlb.props_eval_shootout2_mlb import (
    build_shootout_opportunities,
    score_prop_shootout,
    standing_baseline_for_prop,
)
from domains.mlb.props_eval_shootout2_mlb_families import (
    FAMILIES,
    fit_shrinkage_k,
    shrink_rate,
)


# ---------------------------------------------------------------------------
# Shrinkage math
# ---------------------------------------------------------------------------

def test_shrink_rate_hand_check():
    # n=10 player starts at rate 0.30, k=10, league=0.20 -> exact midpoint.
    out = shrink_rate(0.30, 10, 0.20, 10.0)
    assert out == pytest.approx((10 * 0.30 + 10 * 0.20) / 20)
    assert out == pytest.approx(0.25)


def test_shrink_rate_zero_n_falls_to_league():
    out = shrink_rate(0.30, 0, 0.20, 10.0)
    assert out == pytest.approx(0.20)


def test_shrink_rate_large_n_approaches_player_rate():
    out = shrink_rate(0.30, 100000, 0.20, 10.0)
    assert out == pytest.approx(0.30, abs=1e-3)


def test_shrink_rate_none_propagation():
    assert shrink_rate(None, 0, None, 10.0) is None
    assert shrink_rate(None, 0, 0.2, 10.0) == pytest.approx(0.2)
    assert shrink_rate(0.3, 5, None, 10.0) == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# Fit-window-only k: no-leak property.
# ---------------------------------------------------------------------------

def _synthetic_gamelogs_and_probables(n_starts: int, start_date: str = "2022-04-01",
                                       player_id: int = 100, k_val: float = 0.0):
    game_pks = list(range(1, n_starts + 1))
    dates = pd.date_range(start_date, periods=n_starts, freq="5D")
    rows = []
    for i, (gpk, d) in enumerate(zip(game_pks, dates)):
        rows.append(dict(
            game_pk=gpk, date=d, player_id=player_id, is_pitcher=True,
            battersFaced=25.0, pitch_strikeOuts=float(4 + (i % 4)),
            hits_allowed=5.0, baseOnBalls_allowed=2.0, inningsPitched=6.0,
            earnedRuns=2.0,
        ))
        rows.append(dict(
            game_pk=gpk, date=d, player_id=900 + i, is_pitcher=True,
            battersFaced=24.0, pitch_strikeOuts=3.0,
            hits_allowed=6.0, baseOnBalls_allowed=1.0, inningsPitched=6.0,
            earnedRuns=2.0,
        ))
    gamelogs = pd.DataFrame(rows)
    probables = pd.DataFrame({
        "game_pk": game_pks,
        "home_sp_id": [player_id] * n_starts,
        "away_sp_id": [900 + i for i in range(n_starts)],
    })
    return gamelogs, probables


def test_fit_shrinkage_k_unaffected_by_holdout_only_rows():
    """Adding MORE 2025-2026 (holdout) rows must not change k fit on
    fit_2022_2023 -- the no-leak property for the shrinkage hyperparameter."""
    gl_base, pr_base = _synthetic_gamelogs_and_probables(30, start_date="2022-04-01")
    k_base = fit_shrinkage_k(gl_base, pr_base, "sp_strikeouts")

    gl_extra, pr_extra = _synthetic_gamelogs_and_probables(10, start_date="2025-04-01",
                                                             player_id=200)
    gl_combined = pd.concat([gl_base, gl_extra], ignore_index=True)
    pr_combined = pd.concat([pr_base, pr_extra], ignore_index=True)
    k_combined = fit_shrinkage_k(gl_combined, pr_combined, "sp_strikeouts")

    assert k_base["k"] == k_combined["k"]
    assert k_base["n_fit"] == k_combined["n_fit"]
    assert k_base["grid_crps"] == k_combined["grid_crps"]


def test_fit_shrinkage_k_degrades_gracefully_on_empty():
    empty = pd.DataFrame(columns=["game_pk", "date", "player_id", "is_pitcher",
                                   "battersFaced", "pitch_strikeOuts",
                                   "hits_allowed", "baseOnBalls_allowed",
                                   "inningsPitched", "earnedRuns"])
    empty_prob = pd.DataFrame(columns=["game_pk", "home_sp_id", "away_sp_id"])
    out = fit_shrinkage_k(empty, empty_prob, "sp_strikeouts")
    assert out["n_fit"] == 0
    assert isinstance(out["k"], float)


# ---------------------------------------------------------------------------
# Family determinism + no-leak on the opportunity builder.
# ---------------------------------------------------------------------------

def test_build_shootout_opportunities_deterministic():
    gl, pr = _synthetic_gamelogs_and_probables(20)
    recs1 = build_shootout_opportunities(gl, pr, "sp_strikeouts", k=10.0)
    recs2 = build_shootout_opportunities(gl, pr, "sp_strikeouts", k=10.0)
    assert len(recs1) == len(recs2)
    for r1, r2 in zip(recs1, recs2):
        assert r1["game_pk"] == r2["game_pk"]
        for lam_key in ("lam_season_mean", "lam_league_shrunk", "lam_ew_alpha", "lam_prev_season"):
            assert r1[lam_key] == pytest.approx(r2[lam_key], nan_ok=True)


def test_build_shootout_opportunities_no_leak_future_does_not_change_past():
    gl_full, pr_full = _synthetic_gamelogs_and_probables(10)
    recs_full = build_shootout_opportunities(gl_full, pr_full, "sp_strikeouts", k=10.0)

    keep_pks = set(range(1, 7))
    gl_trunc = gl_full[gl_full["game_pk"].isin(keep_pks)].copy()
    pr_trunc = pr_full[pr_full["game_pk"].isin(keep_pks)].copy()
    recs_trunc = build_shootout_opportunities(gl_trunc, pr_trunc, "sp_strikeouts", k=10.0)

    by_pk_full = {r["game_pk"]: r for r in recs_full if r["player_id"] == 100}
    by_pk_trunc = {r["game_pk"]: r for r in recs_trunc if r["player_id"] == 100}
    shared = set(by_pk_full) & set(by_pk_trunc)
    assert len(shared) >= 2
    for pk in shared:
        rf, rt = by_pk_full[pk], by_pk_trunc[pk]
        for lam_key in ("lam_season_mean", "lam_league_shrunk", "lam_ew_alpha", "lam_prev_season"):
            assert rf[lam_key] == pytest.approx(rt[lam_key], nan_ok=True)


def test_prev_season_family_anchors_across_season_boundary():
    """A pitcher's first start of season 2 should NOT be NaN/blank if they had
    >=MIN_PRIOR_STARTS starts in season 1 -- it should anchor on the
    prior-season rate shrunk to league, distinct from season_mean (which
    resets to nothing meaningful) at that exact opportunity. We only assert
    prev_season is RESOLVED (not NaN) at the season-2 opener when season_mean's
    own within-season count is 0 -- the anchoring behavior under test."""
    gl_s1, pr_s1 = _synthetic_gamelogs_and_probables(10, start_date="2022-04-01", player_id=100)
    gl_s2, pr_s2 = _synthetic_gamelogs_and_probables(5, start_date="2023-04-01", player_id=100)
    # de-duplicate the synthetic "rotating away starter" ids across seasons
    gl_s2["player_id"] = gl_s2["player_id"].where(gl_s2["player_id"] == 100, gl_s2["player_id"] + 10000)
    pr_s2["away_sp_id"] = pr_s2["away_sp_id"] + 10000
    pr_s2["game_pk"] = pr_s2["game_pk"] + 100
    gl_s2["game_pk"] = gl_s2["game_pk"] + 100

    gl = pd.concat([gl_s1, gl_s2], ignore_index=True)
    pr = pd.concat([pr_s1, pr_s2], ignore_index=True)
    recs = build_shootout_opportunities(gl, pr, "sp_strikeouts", k=10.0)
    own = sorted([r for r in recs if r["player_id"] == 100], key=lambda r: r["date"])
    season2_first = [r for r in own if r["date"].startswith("2023")][0]
    assert not math.isnan(season2_first["lam_prev_season"])


# ---------------------------------------------------------------------------
# Standing baseline verdict logic
# ---------------------------------------------------------------------------

def test_standing_baseline_defaults_to_season_mean_on_disagreement():
    scoreboard = {
        "status": "ok",
        "corpora": {
            "holdout_2024": {
                "season_mean": {"n": 100, "crps": 1.0},
                "league_shrunk": {"n": 100, "crps": 1.2},
                "ew_alpha": {"n": 100, "crps": 1.3},
                "prev_season": {"n": 100, "crps": 1.4},
            },
            "holdout_2025_2026": {
                "season_mean": {"n": 100, "crps": 1.2},
                "league_shrunk": {"n": 100, "crps": 1.0},
                "ew_alpha": {"n": 100, "crps": 1.3},
                "prev_season": {"n": 100, "crps": 1.4},
            },
        },
    }
    v = standing_baseline_for_prop(scoreboard)
    assert v["standing_baseline"] == "season_mean"
    assert v["per_holdout_winner"]["holdout_2024"] == "season_mean"
    assert v["per_holdout_winner"]["holdout_2025_2026"] == "league_shrunk"


def test_standing_baseline_agrees_on_a_winner():
    scoreboard = {
        "status": "ok",
        "corpora": {
            "holdout_2024": {
                "season_mean": {"n": 100, "crps": 1.2},
                "league_shrunk": {"n": 100, "crps": 0.9},
                "ew_alpha": {"n": 100, "crps": 1.3},
                "prev_season": {"n": 100, "crps": 1.4},
            },
            "holdout_2025_2026": {
                "season_mean": {"n": 100, "crps": 1.2},
                "league_shrunk": {"n": 100, "crps": 0.95},
                "ew_alpha": {"n": 100, "crps": 1.3},
                "prev_season": {"n": 100, "crps": 1.4},
            },
        },
    }
    v = standing_baseline_for_prop(scoreboard)
    assert v["standing_baseline"] == "league_shrunk"


def test_standing_baseline_insufficient_n_excluded():
    scoreboard = {
        "status": "ok",
        "corpora": {
            "holdout_2024": {
                "season_mean": {"n": 5, "crps": 0.5},
                "league_shrunk": {"n": 100, "crps": 1.0},
                "ew_alpha": {"n": 100, "crps": 1.3},
                "prev_season": {"n": 100, "crps": 1.4},
            },
            "holdout_2025_2026": {
                "season_mean": {"n": 5, "crps": 0.5},
                "league_shrunk": {"n": 100, "crps": 1.0},
                "ew_alpha": {"n": 100, "crps": 1.3},
                "prev_season": {"n": 100, "crps": 1.4},
            },
        },
    }
    v = standing_baseline_for_prop(scoreboard)
    # season_mean has n<30 in both holdouts -> excluded from winner pool both times
    assert v["per_holdout_winner"]["holdout_2024"] == "league_shrunk"
    assert v["standing_baseline"] == "league_shrunk"


def test_standing_baseline_status_not_ok():
    v = standing_baseline_for_prop({"status": "empty"})
    assert v["standing_baseline"] == "season_mean"
    assert v["reason"] == "empty"


# ---------------------------------------------------------------------------
# score_prop_shootout end-to-end on synthetic data
# ---------------------------------------------------------------------------

def test_score_prop_shootout_empty_on_no_data():
    empty = pd.DataFrame(columns=["game_pk", "date", "player_id", "is_pitcher",
                                   "battersFaced", "pitch_strikeOuts",
                                   "hits_allowed", "baseOnBalls_allowed",
                                   "inningsPitched", "earnedRuns"])
    empty_prob = pd.DataFrame(columns=["game_pk", "home_sp_id", "away_sp_id"])
    out = score_prop_shootout(empty, empty_prob, "sp_strikeouts")
    assert out["status"] == "empty"


def test_score_prop_shootout_end_to_end_synthetic():
    game_pks = list(range(1, 41))
    dates = pd.date_range("2022-01-01", periods=40, freq="30D")  # spans 2022-2025
    rows = []
    for i, (gpk, d) in enumerate(zip(game_pks, dates)):
        rows.append(dict(
            game_pk=gpk, date=d, player_id=100, is_pitcher=True,
            battersFaced=25.0, pitch_strikeOuts=float(5 + (i % 3)),
            hits_allowed=5.0, baseOnBalls_allowed=2.0, inningsPitched=6.0,
            earnedRuns=2.0,
        ))
    gamelogs = pd.DataFrame(rows)
    probables = pd.DataFrame({
        "game_pk": game_pks, "home_sp_id": [100] * 40, "away_sp_id": [None] * 40,
    })
    out = score_prop_shootout(gamelogs, probables, "sp_strikeouts")
    assert out["status"] == "ok"
    assert "fit_2022_2023" in out["corpora"]
    for fam in FAMILIES:
        assert fam in out["corpora"]["fit_2022_2023"]
    v = standing_baseline_for_prop(out)
    assert v["standing_baseline"] in FAMILIES
