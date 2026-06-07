"""Smoke + sanity + anti-leak tests for the v2 MATCHUP-AWARE player-line head.

src/ingame/continuous_projection.py adds a matchup-aware variant
(``train_player_lines_v2_matchup`` / ``project_player_lines_v2_matchup``,
persisting to ``data/models/ingame/sbs_v2_matchup/``). It is identical to the
base v2 clock-conditioned head EXCEPT the feature list is the base v2 vector with
the leak-free opponent/matchup columns from ``src.ingame.matchup_features``
appended.

Asserted here:
  * smoke train: the matchup trainer fits one head per stat, save/load roundtrips,
    and persists to a SEPARATE dir (base v2 untouched).
  * the matchup columns ACTUALLY enter the model -- the returned feature list and
    every booster's feature list contain the ``mu_`` columns, and the trainer
    REFUSES a frame that is missing them (so a matchup-less frame can't pretend).
  * finite + current-floored predictions from the served projector.
  * matchup features are LEAK-FREE: the matchup vector for (opp, as_of) is a pure
    function of (opponent identity, games strictly before as_of) -- the as-of
    invariance self-check holds, and a v2-matchup prediction depends only on the
    passed state_row (mutating a future-only / non-feature key cannot change it).
  * the matchup signal is genuinely USED, not ignored: two otherwise-identical
    state rows that differ ONLY in their opponent (different ``mu_`` block) can
    produce different projections (the model can read the matchup block).

Synthetic data is deliberately learnable & leak-free: final_<stat> is a fixed
per-player latent shifted by a per-OPPONENT matchup effect; accumulation =
final * played_share + noise. Dates strictly increase across games so the
walk-forward folds are well defined.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingame.continuous_projection import (  # noqa: E402
    UnifiedPlayerLineProjector,
    train_player_lines_v2_matchup,
    project_player_lines_v2_matchup,
    build_matchup_feature_list,
    matchup_feature_columns,
    FEATURES_PLAYER_V2,
    V2_CLOCK_FEATURES,
    PLAYER_STATS,
)
from src.ingame.matchup_features import (  # noqa: E402
    feature_columns as mf_feature_columns,
    matchup_feature_row,
    self_check_as_of_invariance,
)

_OPPS = ["BOS", "DEN", "MIA", "OKC"]


def _synth(n_games=64, players_per_game=8, snaps_per_game=4, seed=11):
    rng = np.random.default_rng(seed)
    feats = build_matchup_feature_list()  # base v2 + matchup cols
    # a fixed per-opponent scalar effect on production (leak-free: opponent ID)
    opp_effect = {o: float(rng.uniform(-2.0, 2.0)) for o in _OPPS}
    rows = []
    for g in range(n_games):
        date = 20240101 + g
        own, opp = "XXX", _OPPS[g % len(_OPPS)]
        mu = matchup_feature_row(own, opp, f"2024-01-{(g % 27) + 1:02d}",
                                 is_home=(g % 2 == 0))
        for _ in range(players_per_game):
            base_final = {
                s: float(rng.uniform(0, 28 if s == "pts" else 7))
                for s in PLAYER_STATS
            }
            # opponent shifts the final line (so matchup carries real signal)
            finals = {s: max(0.0, base_final[s] + 0.15 * opp_effect[opp])
                      for s in PLAYER_STATS}
            for k in range(snaps_per_game):
                share = float((k + 1) / (snaps_per_game + 1))
                gem = 48.0 * share
                period = int(min(4, gem // 12 + 1))
                rem = max(0.0, 48.0 - gem)
                prow = {f: 0.0 for f in feats}
                prow.update(mu)  # opponent/matchup block
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
                        0.0, finals[s] * share + rng.normal(0, 0.3))
                    prow[f"p_prior_{s}"] = finals[s] * rng.uniform(0.85, 1.15)
                    prow[f"final_{s}"] = finals[s]
                prow["game_date"] = date
                prow["_opp"] = opp
                rows.append(prow)
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    df = _synth()
    mdir = tmp_path_factory.mktemp("sbs_v2_matchup_models")
    proj, metrics, mu_cols = train_player_lines_v2_matchup(
        df, walk_forward=True, num_boost_round=60,
        device="cpu", save=True, model_dir=mdir,
    )
    return proj, metrics, mu_cols, df, mdir


def test_matchup_columns_defined_and_appended():
    cols = matchup_feature_columns()
    assert cols, "no matchup columns defined"
    # the module function mirrors the matchup_features module
    assert tuple(cols) == tuple(mf_feature_columns())
    feats = build_matchup_feature_list()
    # base v2 columns survive (clock conditioning preserved)
    for c in V2_CLOCK_FEATURES:
        assert c in feats
    for c in FEATURES_PLAYER_V2:
        assert c in feats
    # matchup columns appended exactly once
    for c in cols:
        assert feats.count(c) == 1, f"{c} not appended exactly once"


def test_smoke_train_all_stats(trained):
    proj, metrics, mu_cols, _, _ = trained
    for s in PLAYER_STATS:
        assert f"final_{s}" in proj.models, f"missing matchup head for {s}"
        folds = metrics[f"final_{s}"]
        assert len(folds) >= 1
        assert all(np.isfinite(v) for v in folds)
    assert mu_cols, "trainer reported no matchup columns used"


def test_matchup_cols_actually_in_the_model(trained):
    """The matchup columns must be in the returned feature list AND in every
    persisted booster's feature list -- proof they entered the trained model."""
    proj, _, mu_cols, _, _ = trained
    mu = set(matchup_feature_columns())
    assert mu.issubset(set(mu_cols))
    for s in PLAYER_STATS:
        _, feats = proj.models[f"final_{s}"]
        assert mu.issubset(set(feats)), f"{s} head missing matchup cols"


def test_trainer_refuses_frame_without_matchup_cols():
    """A frame lacking the matchup columns cannot masquerade as matchup-aware."""
    df = _synth(n_games=12)
    df = df.drop(columns=[c for c in matchup_feature_columns() if c in df.columns])
    with pytest.raises(ValueError):
        train_player_lines_v2_matchup(
            df, walk_forward=False, num_boost_round=5, device="cpu", save=False,
        )


def test_predicts_finite_and_floored(trained):
    proj, _, _, df, _ = trained
    for i in range(min(15, len(df))):
        row = df.iloc[i].to_dict()
        out = proj.project(row)
        for s in PLAYER_STATS:
            assert np.isfinite(out[s])
            cur = float(row[f"p_{s}_so_far"])
            assert out[s] >= cur - 1e-6, f"{s} projected below current"


def test_save_load_roundtrip_separate_dir(trained):
    proj, _, _, df, mdir = trained
    # persisted to its own dir, with the matchup features in the manifest
    assert (Path(mdir) / "manifest.json").exists()
    row = df.iloc[0].to_dict()
    a = proj.project(row)
    b = project_player_lines_v2_matchup(row, projector=proj)
    for s in PLAYER_STATS:
        assert abs(a[s] - b[s]) < 1e-9
    reloaded = UnifiedPlayerLineProjector.load(mdir)
    for c in matchup_feature_columns():
        assert c in reloaded.features
    c = reloaded.project(row)
    for s in PLAYER_STATS:
        assert abs(a[s] - c[s]) < 1e-3


def test_matchup_features_are_leak_free():
    """Anti-leak: the matchup vector is a pure function of (opp, games < as_of).

    For the leak-safe identity baseline this is date-free, so an earlier and a
    later cutoff yield the IDENTICAL vector (no game-date info leaked in); the
    self-check enforces this. Also: determinism across calls."""
    assert self_check_as_of_invariance("BOS") is True
    assert self_check_as_of_invariance("DEN") is True
    a = matchup_feature_row("XXX", "BOS", "2025-11-01")
    b = matchup_feature_row("XXX", "BOS", "2025-11-01")
    assert a == b
    # different opponents -> different (non-degenerate) matchup blocks
    other = matchup_feature_row("XXX", "MIA", "2025-11-01")
    assert any(abs(a[k] - other[k]) > 1e-9 for k in a if k != "mu_is_home")


def test_prediction_depends_only_on_state_row(trained):
    """A v2-matchup prediction is a pure function of the passed state_row: the
    SAME row predicts identically, and mutating a non-feature/future key cannot
    change a past prediction."""
    proj, _, _, df, _ = trained
    row = df.iloc[5].to_dict()
    p1 = proj.project(dict(row))
    row_future = dict(row)
    row_future["game_date"] = 29991231
    row_future["_opp"] = "ZZZ"          # not a feature column
    row_future["some_future_only_key"] = 999.0
    p2 = proj.project(row_future)
    for s in PLAYER_STATS:
        assert p1[s] == p2[s], f"{s} prediction leaked non-feature state"


def test_matchup_block_is_readable_by_model(trained):
    """The model CAN read the matchup block: swapping ONLY the mu_ columns to a
    different opponent can change the projection (proof the columns are live,
    not inert). NULL is acceptable in the real eval; here the synthetic target
    depends on opponent so at least one stat must move for at least one swap."""
    proj, _, _, df, _ = trained
    base = df.iloc[0].to_dict()
    moved = False
    out_base = proj.project(dict(base))
    for opp in _OPPS:
        swapped = dict(base)
        mu = matchup_feature_row("XXX", opp, "2024-02-01", is_home=True)
        swapped.update(mu)
        out = proj.project(swapped)
        if any(abs(out[s] - out_base[s]) > 1e-6 for s in PLAYER_STATS):
            moved = True
            break
    assert moved, "matchup block had zero effect -> columns inert / not in model"
