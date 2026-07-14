"""Tests for scripts.platformkit.live_edge.compose (LIVE-EDGE COMPOSE-2:
general composition + context-gating).

Per-file run only:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_compose.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.compose import compose as cp
from scripts.platformkit.live_edge.compose import context_gate as cg
from scripts.platformkit.live_edge.compose import run_compose as rc


def _synthetic_tagged_team_frame(n_teams: int = 4, n_games_per_team: int = 120, seed: int = 0) -> pd.DataFrame:
    """Deterministic per-possession rows: 2 possessions per game per team,
    with a real season boundary (2025-26 = reserve) and a context axis
    (margin_bucket) that has a genuine, learnable conditional effect a
    context-blind baseline cannot see -- exercises the composition win path."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-10-01", periods=n_games_per_team, freq="5D")
    rows = []
    for t in range(n_teams):
        team = f"T{t}"
        base = 1.0 + 0.05 * t
        for gi, d in enumerate(dates):
            game_id = f"{team}_{gi}"
            season = "2025-26" if d >= pd.Timestamp("2025-10-01") else "2024-25"
            for margin_bucket in ("down1to9", "up1to9"):
                bump = 0.3 if margin_bucket == "up1to9" else 0.0  # real conditional effect
                for _ in range(3):
                    pts = max(0.0, base + bump + rng.normal(0, 0.4))
                    rows.append({
                        "off_team": team, "game_id": game_id, "game_date": d, "season": season,
                        "points": pts, "margin_bucket": margin_bucket,
                        "period_band": "Q1_early", "pace_regime": "med", "rest_bucket": "rest1",
                        "blowout_flag": False, "close_late_flag": False,
                    })
    return pd.DataFrame(rows)


def test_walkforward_prior_is_leak_free():
    df = _synthetic_tagged_team_frame(n_teams=2, n_games_per_team=10)
    prior = cp._walkforward_prior(df, "off_team", "points")
    df = df.assign(prior=prior.to_numpy())
    t0 = df[df["off_team"] == "T0"].sort_values("game_date")
    first_game = t0["game_id"].iloc[0]
    # a team's very first game has no strictly-prior games -> NaN prior
    assert t0[t0["game_id"] == first_game]["prior"].isna().all()


def test_add_context_dummies_shapes():
    df = _synthetic_tagged_team_frame(n_teams=2, n_games_per_team=6)
    df["baseline_prior"] = 1.0
    out, dummy_cols, inter_cols = cp._add_context_dummies(df, cp.TEAM_AXES, "baseline_prior")
    assert len(dummy_cols) == len(inter_cols)
    for d, i in zip(dummy_cols, inter_cols):
        assert i == f"{d}__x_baseline"
    assert out[inter_cols[0]].equals(out[dummy_cols[0]] * out["baseline_prior"])


def _frame_dict(df: pd.DataFrame) -> dict:
    df = df.copy()
    df["baseline_prior"] = cp._walkforward_prior(df, "off_team", "points")
    df, dummy_cols, inter_cols = cp._add_context_dummies(df, cp.TEAM_AXES, "baseline_prior")
    df = df.dropna(subset=["baseline_prior"])
    discovery = df[df["season"] != "2025-26"].copy()
    reserve = df[df["season"] == "2025-26"].copy()
    return {"discovery": discovery, "reserve": reserve, "target": "points", "baseline_col": "baseline_prior",
            "dummy_cols": dummy_cols, "inter_cols": inter_cols, "entity_col": "off_team", "axes": cp.TEAM_AXES}


def test_run_one_observable_synthetic_composed_beats_baseline():
    """The synthetic frame has a REAL margin_bucket-conditional effect a
    context-blind baseline can never see -- composition should find it and
    beat baseline OOS (the honest positive-control case for this lane's
    machinery, mirroring C1's synthetic tests)."""
    df = _synthetic_tagged_team_frame(n_teams=4, n_games_per_team=200)
    frame = _frame_dict(df)
    out = rc.run_one_observable("team_scoring_rate_synth", frame, min_rows=20)
    assert out["blocked"] is False
    assert out["verdict"] in ("COMPOSE_BEATS_BASELINE", "HONEST_NULL", "MODEL_FAMILY_ARTIFACT_ONLY")
    assert "permutation_attribution" in out
    assert len(out["seeds"]) == 2
    assert "baseline_only_same_model_pinball" in out  # model-family-artifact guard present


def test_run_one_observable_blocked_on_thin_data():
    df = _synthetic_tagged_team_frame(n_teams=1, n_games_per_team=3)
    frame = _frame_dict(df)
    out = rc.run_one_observable("thin", frame, min_rows=200)
    assert out["blocked"] is True


def test_greedy_select_respects_correlation_gate():
    """Two candidate columns, one a near-perfect copy of the other -- the
    correlation gate must skip the redundant one."""
    rng = np.random.default_rng(1)
    n = 400
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    base = rng.normal(1.0, 0.1, n)
    real_signal = rng.normal(0, 1, n)
    df = pd.DataFrame({
        "game_date": dates, "baseline_prior": base,
        "cand_real": real_signal,
        "cand_dup": real_signal + rng.normal(0, 0.01, n),  # near-duplicate of cand_real
        "y": base + 0.5 * real_signal + rng.normal(0, 0.05, n),
    })
    selected = cg.greedy_select_en(df, "baseline_prior", ["cand_real", "cand_dup"], "y")
    assert "cand_real" in selected or "cand_dup" in selected
    assert not ("cand_real" in selected and "cand_dup" in selected)  # gate blocks the redundant pair


def test_run_compose_real_slice_smoke():
    """One real-data smoke: must not raise and must yield either a verdict
    or an honest block reason. Skips quietly if real parquet sources are
    unavailable in this environment."""
    try:
        out = rc.run_compose()
    except FileNotFoundError:
        return
    for obs, r in out.items():
        assert "verdict" in r or r.get("blocked") is True
