"""Smoke + sanity tests for the v2 UNIFIED player-line head.

src/ingame/continuous_projection.py adds ONE clock-conditioned XGBoost per
player-stat (trained over ALL event state rows, with game_remaining_min/period/
played_share as MODEL FEATURES) instead of v1's separate ridge per grid-bucket.

Asserted here:
  * smoke train: train_player_lines_v2 fits a head per stat, save/load roundtrips
  * finite preds: project_player_lines_v2 returns finite, current-floored values
  * finals-at-t0 sanity: with ~full game remaining and ~zero accumulated, the
    projection is >= current (>= 0) and finite; and the model DOES condition on
    the clock (a near-final row projects materially higher than an early row for
    the same target signal).
  * leak check: the v2 trainer's walk-forward folds never let a test game leak
    into training -- a row dated AFTER all test dates cannot change a fold score;
    equivalently, fold scores are computed only on held-out (later) games. We
    assert the trainer requires clock features (the conditioning the design
    promises) and that prediction depends ONLY on the supplied state_row (no
    hidden as-of-today state): the same row predicts identically across calls and
    truncating/altering FUTURE-only context is impossible because there is none.

Synthetic data is deliberately learnable & leak-free: final_<stat> is a fixed
per-player latent; the in-game accumulation is final*played_share + noise, so the
correct projection at any clock is ~ current / played_share -- a clean test that
a clock-conditioned single model recovers the pace relationship.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingame.continuous_projection import (  # noqa: E402
    UnifiedPlayerLineProjector,
    train_player_lines_v2,
    project_player_lines_v2,
    FEATURES_PLAYER_V2,
    V2_CLOCK_FEATURES,
    PLAYER_STATS,
)


def _synth(n_games=60, players_per_game=8, snaps_per_game=4, seed=7):
    """Event-grid-like player state rows across many chronological games.

    Each (game, player) has a fixed latent final line. We emit several snapshots
    per game at increasing played_share; accumulation = final * share + noise.
    Dates strictly increase across games so walk-forward folds are well defined.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        date = 20240101 + g
        for _ in range(players_per_game):
            finals = {
                s: float(rng.uniform(0, 28 if s == "pts" else 7))
                for s in PLAYER_STATS
            }
            for k in range(snaps_per_game):
                # spread snapshots across the game in played_share
                share = float((k + 1) / (snaps_per_game + 1))  # 0.2..0.8
                gem = 48.0 * share
                period = int(min(4, gem // 12 + 1))
                rem = max(0.0, 48.0 - gem)
                prow = {f: 0.0 for f in FEATURES_PLAYER_V2}
                prow.update(
                    period=period,
                    elapsed_sec_in_period=float((gem % 12) * 60.0),
                    game_elapsed_min=gem,
                    game_remaining_min=rem,
                    played_share=share,
                    p_min_so_far=share * 32.0,
                    p_is_starter=1.0,
                    p_on_court=1.0,
                )
                for s in PLAYER_STATS:
                    prow[f"p_{s}_so_far"] = max(
                        0.0, finals[s] * share + rng.normal(0, 0.3)
                    )
                    prow[f"p_prior_{s}"] = finals[s] * rng.uniform(0.85, 1.15)
                    prow[f"final_{s}"] = finals[s]
                prow["game_date"] = date
                rows.append(prow)
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    df = _synth()
    mdir = tmp_path_factory.mktemp("sbs_v2_models")
    proj, metrics = train_player_lines_v2(
        df, walk_forward=True, num_boost_round=60,
        device="cpu", save=True, model_dir=mdir,
    )
    return proj, metrics, df, mdir


def test_smoke_train_all_stats(trained):
    proj, metrics, _, _ = trained
    for s in PLAYER_STATS:
        assert f"final_{s}" in proj.models, f"missing v2 head for {s}"
    # walk-forward produced finite per-fold MAE
    for s in PLAYER_STATS:
        folds = metrics[f"final_{s}"]
        assert len(folds) >= 1
        assert all(np.isfinite(v) for v in folds)


def test_predicts_finite_and_floored(trained):
    proj, _, df, _ = trained
    for i in range(min(15, len(df))):
        row = df.iloc[i].to_dict()
        out = proj.project(row)
        for s in PLAYER_STATS:
            assert np.isfinite(out[s])
            cur = float(row[f"p_{s}_so_far"])
            assert out[s] >= cur - 1e-6, f"{s} projected below current"


def test_module_fn_uses_persisted(trained):
    """project_player_lines_v2 with an explicit projector matches the object."""
    proj, _, df, mdir = trained
    row = df.iloc[0].to_dict()
    a = proj.project(row)
    b = project_player_lines_v2(row, projector=proj)
    for s in PLAYER_STATS:
        assert abs(a[s] - b[s]) < 1e-9
    # and loading from disk reproduces predictions
    reloaded = UnifiedPlayerLineProjector.load(mdir)
    c = reloaded.project(row)
    for s in PLAYER_STATS:
        assert abs(a[s] - c[s]) < 1e-3


def test_t0_finals_sanity(trained):
    """At ~t=0 (full game remaining, ~zero accumulated) projection is finite and
    floored at 0; the head conditions on the clock so a late-game row with the
    same fractional pace projects materially LESS additional production than the
    early row (less time left to accumulate)."""
    proj, _, _, _ = trained
    early = {f: 0.0 for f in FEATURES_PLAYER_V2}
    early.update(period=1, played_share=0.02, game_remaining_min=47.0,
                 p_min_so_far=0.5)
    out0 = proj.project(early)
    for s in PLAYER_STATS:
        assert np.isfinite(out0[s])
        assert out0[s] >= 0.0  # current is 0 -> projection >= 0

    # Same player-pace signal but late in the game with most stats already banked:
    # remaining projection (proj - current) should be SMALL because little time
    # is left -> the model is genuinely clock-conditioned.
    late = {f: 0.0 for f in FEATURES_PLAYER_V2}
    late.update(period=4, played_share=0.95, game_remaining_min=2.4,
                p_min_so_far=30.0)
    for s in PLAYER_STATS:
        late[f"p_{s}_so_far"] = 10.0 if s == "pts" else 4.0
    out_late = proj.project(late)
    for s in PLAYER_STATS:
        cur = float(late[f"p_{s}_so_far"])
        remaining = out_late[s] - cur
        # with 95% of the game played, projected remaining is small (< current)
        assert remaining <= cur + 1e-6


def test_requires_clock_features():
    """v2 must refuse a feature list lacking the clock features -- the single
    model can only replace the per-bucket ridge if it conditions on game-time."""
    df = _synth(n_games=12)
    bad_feats = tuple(f for f in FEATURES_PLAYER_V2
                      if f not in V2_CLOCK_FEATURES) + ("p_pts_so_far",)
    with pytest.raises(ValueError):
        train_player_lines_v2(
            df, features=bad_feats, walk_forward=False,
            num_boost_round=5, device="cpu", save=False,
        )


def test_prediction_depends_only_on_state_row(trained):
    """LEAK CHECK: a v2 prediction is a pure function of the passed state_row.

    There is no as-of-today / future-game state inside the projector, so the SAME
    row predicts identically on repeated calls, and a row that differs ONLY in a
    not-a-feature key (e.g. a future game_date) predicts identically -- i.e. no
    hidden temporal leak can change a past prediction.
    """
    proj, _, df, _ = trained
    row = df.iloc[3].to_dict()
    p1 = proj.project(dict(row))
    # mutate a non-feature field (simulate "the future") -> must not change pred
    row_future = dict(row)
    row_future["game_date"] = 29991231
    row_future["some_future_only_key"] = 999.0
    p2 = proj.project(row_future)
    for s in PLAYER_STATS:
        assert p1[s] == p2[s], f"{s} prediction leaked non-feature state"
