"""Smoke tests for src/ingame/continuous_projection.py.

Trains on a tiny synthetic, leak-free state set and asserts:
  * predictions are finite
  * team-score / win-prob heads exist and produce sane ranges
  * player heads exist and never project below current accumulation
  * at t=0 (~full game remaining, nothing accumulated) the team-score
    projection is finite and the player projection >= current (~current)
  * walk-forward fold metrics are produced

Synthetic data is deliberately learnable: final score ~ current/played_share
with noise; home_win ~ sign(final margin). No real data files are touched.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingame.continuous_projection import (  # noqa: E402
    ContinuousProjector,
    train,
    FEATURES_TEAM,
    FEATURES_PLAYER,
    TEAM_TARGETS,
    WINPROB_TARGET,
    PLAYER_STATS,
    PLAYER_TARGETS,
)


def _synth(n_games=40, players_per_game=6, seed=0):
    rng = np.random.default_rng(seed)
    team_rows, player_rows = [], []
    for g in range(n_games):
        date = 20240101 + g  # strictly increasing -> chronological
        # one mid-game snapshot per game (enough for smoke)
        period = int(rng.integers(1, 5))
        elapsed = float(rng.uniform(0, 720))
        gem = 12 * (period - 1) + elapsed / 60.0
        rem = max(0.0, 48.0 - gem)
        share = max(0.05, gem / 48.0)
        home_final = float(rng.uniform(95, 125))
        away_final = float(rng.uniform(95, 125))
        home_score = home_final * share + rng.normal(0, 1)
        away_score = away_final * share + rng.normal(0, 1)

        trow = {f: 0.0 for f in FEATURES_TEAM}
        trow.update(
            period=period, elapsed_sec_in_period=elapsed, game_elapsed_min=gem,
            game_remaining_min=rem, played_share=share,
            home_score=home_score, away_score=away_score,
            margin=home_score - away_score, total_so_far=home_score + away_score,
            pace_to_date=rng.uniform(90, 105),
            home_prior_ppg=110.0, away_prior_ppg=108.0,
        )
        trow["game_date"] = date
        trow["home_final_score"] = home_final
        trow["away_final_score"] = away_final
        trow[WINPROB_TARGET] = int(home_final > away_final)
        team_rows.append(trow)

        for _ in range(players_per_game):
            finals = {s: float(rng.uniform(0, 30 if s == "pts" else 8))
                      for s in PLAYER_STATS}
            prow = {f: 0.0 for f in FEATURES_PLAYER}
            prow.update(
                period=period, elapsed_sec_in_period=elapsed, game_elapsed_min=gem,
                game_remaining_min=rem, played_share=share,
                home_score=home_score, away_score=away_score,
                margin=home_score - away_score,
                p_min_so_far=share * 32, p_is_starter=1.0, p_on_court=1.0,
            )
            for s in PLAYER_STATS:
                prow[f"p_{s}_so_far"] = finals[s] * share
                prow[f"p_prior_{s}"] = finals[s] * rng.uniform(0.8, 1.2)
                prow[f"final_{s}"] = finals[s]
            prow["game_date"] = date
            player_rows.append(prow)

    return pd.DataFrame(team_rows), pd.DataFrame(player_rows)


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    df_team, df_player = _synth()
    mdir = tmp_path_factory.mktemp("ingame_models")
    proj, metrics = train(
        df_team=df_team, df_player=df_player,
        walk_forward=True, num_boost_round=40,
        device="cpu", save=True, model_dir=mdir,
    )
    return proj, metrics, df_team, df_player, mdir


def test_heads_trained(trained):
    proj, metrics, _, _, _ = trained
    for tgt in TEAM_TARGETS:
        assert tgt in proj.team_models
    assert proj.winprob_model is not None
    for tgt in PLAYER_TARGETS:
        assert tgt in proj.player_models
    # walk-forward produced fold scores
    assert len(metrics[WINPROB_TARGET]) >= 1
    assert all(np.isfinite(s) for s in metrics["home_final_score"])


def test_predicts_finite(trained):
    proj, _, df_team, df_player, _ = trained
    trow = df_team.iloc[0].to_dict()
    out = proj.project_state(trow)
    assert np.isfinite(out["home_final_score"])
    assert np.isfinite(out["away_final_score"])
    assert 0.0 <= out["home_win_prob"] <= 1.0

    prow = df_player.iloc[0].to_dict()
    pout = proj.project_state(prow)
    assert "player" in pout
    for s in PLAYER_STATS:
        assert np.isfinite(pout["player"][s])


def test_player_never_below_current(trained):
    proj, _, _, df_player, _ = trained
    for i in range(min(10, len(df_player))):
        prow = df_player.iloc[i].to_dict()
        pout = proj.project_state(prow)
        for s in PLAYER_STATS:
            cur = float(prow[f"p_{s}_so_far"])
            assert pout["player"][s] >= cur - 1e-6


def test_t0_finals_near_current(trained):
    """At t=0 nothing has happened: player projection >= current (~current),
    team projection finite. (Exact equality isn't expected from a learner; we
    assert the floor/finiteness invariants the design guarantees.)"""
    proj, _, df_team, df_player, _ = trained
    # t=0 team row: no time elapsed, zero score
    trow = {f: 0.0 for f in FEATURES_TEAM}
    trow.update(period=1, played_share=0.02, game_remaining_min=48.0)
    out = proj.project_state(trow)
    assert np.isfinite(out["home_final_score"]) and out["home_final_score"] >= 0
    assert 0.0 <= out["home_win_prob"] <= 1.0

    prow = {f: 0.0 for f in FEATURES_PLAYER}
    prow.update(period=1, played_share=0.02, game_remaining_min=48.0)
    pout = proj.project_state(prow)
    for s in PLAYER_STATS:
        assert pout["player"][s] >= 0.0  # current is 0, projection >= 0


def test_save_load_roundtrip(trained):
    proj, _, df_team, _, mdir = trained
    reloaded = ContinuousProjector.load(mdir)
    trow = df_team.iloc[0].to_dict()
    a = proj.project_state(trow)
    b = reloaded.project_state(trow)
    assert abs(a["home_final_score"] - b["home_final_score"]) < 1e-3
    assert abs(a["home_win_prob"] - b["home_win_prob"]) < 1e-6


def test_missing_feature_raises():
    """train() must refuse a frame missing a declared feature (no silent drop)."""
    df_team, _ = _synth(n_games=10)
    df_bad = df_team.drop(columns=["pace_to_date"])
    with pytest.raises(ValueError):
        train(df_team=df_bad, walk_forward=False, num_boost_round=5,
              device="cpu", save=False)
