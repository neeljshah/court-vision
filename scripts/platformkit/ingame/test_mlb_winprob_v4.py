"""Per-file tests for mlb_winprob_v4.py + mlb_winprob_v4_blend.py -- rung 4 of the MLB
in-game win-prob ladder (2024/2025 train band, prior-as-feature vs regularized per-phase
logit-blend).

OFFLINE + deterministic: synthetic pitch-state parquets + PM/Kalshi jsonl under tmp_path,
no network, no real corpus reads.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_mlb_winprob_v4.py -q
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.platformkit.ingame.mlb_winprob_v2_features as feat
import scripts.platformkit.ingame.mlb_winprob_v4 as v4
import scripts.platformkit.ingame.mlb_winprob_v4_blend as blend_mod


# --------------------------------------------------------------------------------------- #
def test_no_2026_in_train_guard(tmp_path: Path) -> None:
    """v4's train band (2024/2025) relies on feat.load_training_seasons's shared guard."""
    with pytest.raises(ValueError):
        feat.load_training_seasons([2026], data_dir=tmp_path)
    with pytest.raises(ValueError):
        feat.load_training_seasons(v4.TRAIN_SEASONS_B + (2026,), data_dir=tmp_path)


def test_game_level_brier_averages_per_game_not_per_tick() -> None:
    # game g1 has 1 tick at squared-error 1.0, game g2 has 3 ticks all at 0.0 --
    # game-level Brier must be mean(1.0, 0.0) == 0.5, NOT mean over 4 ticks (== 0.25).
    probs = [1.0, 0.5, 0.5, 0.5]
    y = [0.0, 0.5, 0.5, 0.5]
    game_ids = ["g1", "g2", "g2", "g2"]
    assert blend_mod.game_level_brier(probs, y, game_ids) == pytest.approx(0.5)
    assert blend_mod.game_level_brier([], [], []) != blend_mod.game_level_brier([], [], [])  # nan


def test_select_phase_weights_grid_bounded_and_blend_in_unit_interval() -> None:
    rng = np.random.RandomState(0)
    n = 300
    p_state = rng.uniform(0.2, 0.8, size=n)
    prior_home = rng.uniform(0.2, 0.8, size=n)
    y = (rng.uniform(size=n) < prior_home).astype(float)  # prior is the informative signal
    game_id = np.array(["g%d" % (i % 30) for i in range(n)])
    phase = np.array([blend_mod.PHASES[i % 3] for i in range(n)])
    has_prior = np.ones(n, dtype=bool)

    w_by_phase = blend_mod.select_phase_weights(p_state, y, game_id, phase, prior_home, has_prior)
    assert set(w_by_phase) == set(blend_mod.PHASES)
    for w in w_by_phase.values():
        assert w in blend_mod.W_GRID

    probs = blend_mod.blend(p_state, prior_home, has_prior, w_by_phase, phase)
    assert probs.shape == p_state.shape
    assert np.all(probs >= 0.0) and np.all(probs <= 1.0)
    # since y was generated FROM prior_home, weighting toward the prior should not be
    # forced to 0 everywhere (a sanity check the grid search actually engages).
    assert any(w > 0.0 for w in w_by_phase.values())


def test_blend_never_moves_rows_without_a_prior() -> None:
    p_state = np.array([0.3, 0.7, 0.5])
    prior_home = np.array([0.9, 0.9, 0.9])
    has_prior = np.array([True, False, False])
    w_by_phase = {"early": 1.0, "mid": 1.0, "late": 1.0}
    phase = np.array(["early", "mid", "late"])
    out = blend_mod.blend(p_state, prior_home, has_prior, w_by_phase, phase)
    assert out[0] == pytest.approx(0.9, abs=1e-3)   # has_prior -> fully blended to prior
    assert out[1] == pytest.approx(0.7)              # no prior -> untouched p_state
    assert out[2] == pytest.approx(0.5)              # no prior -> untouched p_state
    assert blend_mod.blend(np.zeros(0), np.zeros(0), np.zeros(0, dtype=bool), {}, np.zeros(0)).shape == (0,)


def _synthetic_pitch_states_with_date(season: int, n_games: int, home_abbr: str,
                                      away_abbr: str, seed: int) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    rows = []
    for g in range(n_games):
        gid = "%d-06-%02d-%s-%s-1" % (season, 1 + (g % 27), home_abbr, away_abbr)
        margin = rng.choice([-3.0, -1.0, 1.0, 3.0])
        home_win = 1 if margin > 0 else 0
        for i in range(6):
            rows.append({
                "game_id": gid, "half_inning_label": "%s%d" % ("top" if i % 2 == 0 else "bottom", 1 + i),
                "outs": i % 3, "runners": i % 8, "count_balls": i % 4, "count_strikes": i % 3,
                "state_diff": margin, "frac_elapsed": (i + 1) / 6.0, "outcome": home_win,
                "season": season,
            })
    return pd.DataFrame(rows)


def test_train_specs_picks_a_winner_and_reports_prior_coverage_2024_vs_2025(tmp_path: Path) -> None:
    data_dir = tmp_path / "pitch_states"
    data_dir.mkdir()
    _synthetic_pitch_states_with_date(2024, 30, "BOS", "NYY", seed=1).to_parquet(
        data_dir / "mlb_pitch_states__2024.parquet")
    _synthetic_pitch_states_with_date(2025, 30, "BOS", "NYY", seed=2).to_parquet(
        data_dir / "mlb_pitch_states__2025.parquet")

    pm_dir = tmp_path / "pm"
    pm_dir.mkdir()
    # PM prior only exists for 2025 (mirrors the real mlb_2024plus corpus starting 2025-04-02)
    doc_lines = []
    import json as _json
    for g in range(27):
        doc_lines.append(_json.dumps({
            "date": "2025-06-%02d" % (1 + g), "home": "Boston Red Sox", "away": "New York Yankees",
            "prices": [{"ts": "2025-06-%02dT10:00:00Z" % (1 + g), "prob_home": 0.6}],
        }))
    (pm_dir / "2025.jsonl").write_text("\n".join(doc_lines), encoding="utf-8")

    bundle = v4.train_specs(data_dir=data_dir, pm_dirs=[pm_dir])
    assert bundle["winner"] in ("a", "b")
    assert bundle["meta"]["prior_coverage_2024"]["n_games_with_prior"] == 0
    assert bundle["meta"]["prior_coverage_2025"]["n_games_with_prior"] > 0
    assert set(bundle["w_by_phase"]) == set(blend_mod.PHASES)


def test_save_model_meta_feature_count_matches_pkl_for_both_specs(tmp_path: Path) -> None:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.isotonic import IsotonicRegression
    import scripts.platformkit.ingame.mlb_winprob_v3 as v3

    X = np.random.RandomState(0).uniform(size=(20, len(v3.FEATURE_NAMES_V3)))
    y = (X[:, 0] > 0.5).astype(int)
    clf = HistGradientBoostingClassifier(random_state=0)
    clf.fit(X, y)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(clf.predict_proba(X)[:, 1], y)

    bundle_a = {"clf_a": clf, "iso_a": iso, "clf_state": None, "iso_state": None,
               "w_by_phase": {}, "winner": "a", "val_game_brier_spec_a": 0.2,
               "val_game_brier_spec_b": 0.25, "meta": {}}
    pkl_a, meta_a = v4.save_model(bundle_a, model_path=tmp_path / "a.pkl", meta_path=tmp_path / "a.json")
    import json
    meta = json.loads(meta_a.read_text(encoding="utf-8"))
    assert meta["n_features"] == clf.n_features_in_ == len(v3.FEATURE_NAMES_V3)
    assert pkl_a.is_file()

    X8 = np.random.RandomState(0).uniform(size=(20, len(feat.FEATURE_NAMES)))
    clf8 = HistGradientBoostingClassifier(random_state=0)
    clf8.fit(X8, y)
    iso8 = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso8.fit(clf8.predict_proba(X8)[:, 1], y)
    bundle_b = {"clf_a": None, "iso_a": None, "clf_state": clf8, "iso_state": iso8,
               "w_by_phase": {"early": 0.3, "mid": 0.5, "late": 0.7}, "winner": "b",
               "val_game_brier_spec_a": 0.25, "val_game_brier_spec_b": 0.2, "meta": {}}
    pkl_b, meta_b = v4.save_model(bundle_b, model_path=tmp_path / "b.pkl", meta_path=tmp_path / "b.json")
    meta_b_doc = json.loads(meta_b.read_text(encoding="utf-8"))
    assert meta_b_doc["n_features"] == clf8.n_features_in_ == len(feat.FEATURE_NAMES)
    assert pkl_b.is_file()
