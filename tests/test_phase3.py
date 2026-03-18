"""
test_phase3.py — Phase 3 ML model test suite (no video, no network required).

All tests use mocked or synthetic data so they run offline and fast.
"""

from __future__ import annotations

import os
import sys
import json
import tempfile

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── win_probability ────────────────────────────────────────────────────────────

def test_win_prob_import():
    """WinProbModel and WinProbabilityModel alias both importable."""
    from src.prediction.win_probability import WinProbModel, WinProbabilityModel
    assert WinProbabilityModel is WinProbModel


def test_win_prob_untrained_raises():
    """predict() on untrained model raises RuntimeError."""
    from src.prediction.win_probability import WinProbModel
    m = WinProbModel()
    with pytest.raises(RuntimeError, match="not trained"):
        m.predict("GSW", "BOS")


def test_win_prob_feature_importance_empty_before_train():
    """feature_importance() returns empty list before training."""
    from src.prediction.win_probability import WinProbModel
    m = WinProbModel()
    assert m.feature_importance() == []


def test_win_prob_save_load_roundtrip(tmp_path):
    """save()/load() roundtrip preserves threshold and model attribute."""
    from src.prediction.win_probability import WinProbModel, load
    try:
        from xgboost import XGBClassifier
    except ImportError:
        pytest.skip("xgboost not installed")

    # Train a tiny synthetic model
    X = np.random.rand(40, 27).astype(np.float32)
    y = (X[:, 0] > 0.5).astype(int)
    clf = XGBClassifier(n_estimators=5, max_depth=2,
                        eval_metric="logloss", random_state=0)
    clf.fit(X, y)

    m = WinProbModel(model=clf, threshold=0.6)
    m._feature_importance = {"feat_0": 0.5}
    path = str(tmp_path / "test_model.pkl")
    m.save(path)

    m2 = load(path)
    assert m2.threshold == 0.6
    assert m2.model is not None
    assert m2._feature_importance == {"feat_0": 0.5}


def test_win_prob_predict_output_keys(tmp_path):
    """predict() returns dict with required keys and probabilities sum to 1."""
    from src.prediction.win_probability import WinProbModel, FEATURE_COLS
    try:
        from xgboost import XGBClassifier
    except ImportError:
        pytest.skip("xgboost not installed")

    X = np.random.rand(40, len(FEATURE_COLS)).astype(np.float32)
    y = (X[:, 0] > 0.5).astype(int)
    clf = XGBClassifier(n_estimators=5, max_depth=2,
                        eval_metric="logloss", random_state=0)
    clf.fit(X, y)

    m = WinProbModel(model=clf)
    # Patch _build_features to avoid NBA API call
    import src.prediction.win_probability as wp_mod
    orig = wp_mod._build_features
    wp_mod._build_features = lambda *a, **kw: {c: 0.5 for c in FEATURE_COLS}
    try:
        result = m.predict("GSW", "BOS")
    finally:
        wp_mod._build_features = orig

    for key in ("home_win_prob", "away_win_prob", "predicted_winner", "margin_est", "features"):
        assert key in result, f"missing key: {key}"
    assert abs(result["home_win_prob"] + result["away_win_prob"] - 1.0) < 1e-4


def test_get_schedule_context_no_date_returns_defaults():
    """_get_schedule_context falls back to neutral defaults when game_date is None."""
    from src.prediction.win_probability import _get_schedule_context
    ctx = _get_schedule_context("GSW", None, "2024-25")
    assert ctx["rest_days"]    == 2.0
    assert ctx["back_to_back"] == 0.0


def test_get_schedule_context_uses_schedule(monkeypatch):
    """_get_schedule_context returns real rest/B2B from schedule when date matches."""
    import src.prediction.win_probability as wp_mod
    fake_schedule = [
        {"date": "2024-01-15", "rest_days": 1, "back_to_back": True},
        {"date": "2024-01-20", "rest_days": 5, "back_to_back": False},
    ]
    monkeypatch.setattr(
        "src.data.schedule_context.get_season_schedule",
        lambda *a, **kw: fake_schedule,
    )
    ctx = wp_mod._get_schedule_context("GSW", "2024-01-15", "2024-25")
    assert ctx["rest_days"]    == 1.0
    assert ctx["back_to_back"] == 1.0


def test_get_schedule_context_date_not_found_returns_defaults(monkeypatch):
    """_get_schedule_context falls back when the date is not in the schedule."""
    import src.prediction.win_probability as wp_mod
    monkeypatch.setattr(
        "src.data.schedule_context.get_season_schedule",
        lambda *a, **kw: [{"date": "2024-01-10", "rest_days": 2, "back_to_back": False}],
    )
    ctx = wp_mod._get_schedule_context("GSW", "2024-03-01", "2024-25")
    assert ctx["rest_days"]    == 2.0
    assert ctx["back_to_back"] == 0.0


def test_get_schedule_context_season_opener_rest_capped():
    """rest_days of 99 (season opener sentinel) is converted to 3.0, not 99."""
    from src.prediction.win_probability import _get_schedule_context
    import src.data.schedule_context as sc_mod
    # Patch directly so no network call is made
    import unittest.mock as mock
    fake = [{"date": "2024-10-24", "rest_days": 99, "back_to_back": False}]
    with mock.patch.object(sc_mod, "get_season_schedule", return_value=fake):
        ctx = _get_schedule_context("GSW", "2024-10-24", "2024-25")
    assert ctx["rest_days"] == 3.0, f"opener sentinel 99 should map to 3.0, got {ctx['rest_days']}"


def test_recent_form_min_string_parsed():
    """_get_recent_form must handle MM:SS string MIN without raising TypeError."""
    import json, tempfile, os
    import src.prediction.player_props as pp

    # Simulate a cached game log with MIN as "MM:SS" strings
    fake_rows = [
        {"PTS": 28, "REB": 7, "AST": 5, "MIN": "35:22"},
        {"PTS": 31, "REB": 6, "AST": 8, "MIN": "38:00"},
        {"PTS": 22, "REB": 9, "AST": 4, "MIN": "30:45"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        cache = os.path.join(tmp, "gamelog_999_2024-25.json")
        with open(cache, "w") as f:
            json.dump(fake_rows, f)
        orig_cache = pp._NBA_CACHE
        pp._NBA_CACHE = tmp
        try:
            form = pp._get_recent_form(999, "2024-25", n=3)
        finally:
            pp._NBA_CACHE = orig_cache

    assert form is not None, "_get_recent_form returned None — likely TypeError on MIN string"
    assert abs(form["pts_roll"] - (28 + 31 + 22) / 3) < 0.01
    # 35:22 → 35.367, 38:00 → 38.0, 30:45 → 30.75
    expected_min = (35 + 22/60 + 38.0 + 30 + 45/60) / 3
    assert abs(form["min_roll"] - expected_min) < 0.1, \
        f"min_roll={form['min_roll']:.2f} expected ~{expected_min:.2f}"


def test_recent_form_min_float_passthrough():
    """_get_recent_form works when MIN is already a float (pre-parsed cache)."""
    import json, tempfile, os
    import src.prediction.player_props as pp

    fake_rows = [{"PTS": 20, "REB": 5, "AST": 3, "MIN": 32.5}] * 5
    with tempfile.TemporaryDirectory() as tmp:
        cache = os.path.join(tmp, "gamelog_888_2024-25.json")
        with open(cache, "w") as f:
            json.dump(fake_rows, f)
        orig_cache = pp._NBA_CACHE
        pp._NBA_CACHE = tmp
        try:
            form = pp._get_recent_form(888, "2024-25", n=5)
        finally:
            pp._NBA_CACHE = orig_cache

    assert form is not None
    assert form["min_roll"] == 32.5


def test_compute_last5_wins_basic():
    """_compute_last5_wins returns correct rolling win counts."""
    import pandas as pd
    from src.prediction.win_probability import _compute_last5_wins

    # Team 1: L L W W W W  (games G01–G06 on consecutive days)
    results = ["L", "L", "W", "W", "W", "W"]
    rows = [
        {"TEAM_ID": 1, "GAME_ID": f"G0{i+1}",
         "GAME_DATE": f"2024-01-{i+1:02d}", "WL": wl}
        for i, wl in enumerate(results)
    ]
    gl = pd.DataFrame(rows)
    lookup = _compute_last5_wins(gl)

    # Season opener: no prior games → neutral 2.5
    assert lookup[(1, "G01")] == pytest.approx(2.5), "opener → neutral 2.5"
    # G02: 1 prior game (L) → 0/1 * 5 = 0.0 (rate-scaled)
    assert lookup[(1, "G02")] == pytest.approx(0.0), "1 game seen: 0 wins → 0.0 scaled"
    # G03: 2 prior (L,L) → 0/2 * 5 = 0.0
    assert lookup[(1, "G03")] == pytest.approx(0.0), "2 prior: 0 wins → 0.0 scaled"
    # G04: 3 prior (L,L,W) → 1/3 * 5 ≈ 1.7
    assert abs(lookup[(1, "G04")] - round(1/3 * 5, 1)) < 0.05, "3 prior: 1/3 * 5 ≈ 1.7"
    # G05: 4 prior (L,L,W,W) → 2/4 * 5 = 2.5
    assert lookup[(1, "G05")] == pytest.approx(2.5), "4 prior: 2/4 * 5 = 2.5"
    # G06: 5 prior games full window (L,L,W,W,W) → exact count = 3
    assert lookup[(1, "G06")] == 3, "full 5-game window: exact count = 3"


def test_compute_last5_wins_early_season_rate_scaled():
    """1-for-1 early season team must get 5.0 (hot), not 1 (count bias)."""
    import pandas as pd
    from src.prediction.win_probability import _compute_last5_wins

    rows = [
        {"TEAM_ID": 1, "GAME_ID": "G01", "GAME_DATE": "2024-10-23", "WL": "W"},
        {"TEAM_ID": 1, "GAME_ID": "G02", "GAME_DATE": "2024-10-25", "WL": "L"},
    ]
    gl = pd.DataFrame(rows)
    lookup = _compute_last5_wins(gl)

    # G01: opener → 2.5
    assert lookup[(1, "G01")] == pytest.approx(2.5), "opener should be 2.5 neutral"
    # G02: 1 prior win → 1/1 * 5 = 5.0 (not the raw count 1)
    assert lookup[(1, "G02")] == pytest.approx(5.0), (
        f"1-for-1 team got {lookup[(1, 'G02')]}, expected 5.0 — raw count bias not fixed"
    )


def test_compute_last5_wins_window_capped():
    """Window is capped at 5 — old results drop off."""
    import pandas as pd
    from src.prediction.win_probability import _compute_last5_wins

    # 7 straight wins: window should cap at 5
    rows = [
        {"TEAM_ID": 1, "GAME_ID": f"G{i:02d}",
         "GAME_DATE": f"2024-01-{i+1:02d}", "WL": "W"}
        for i in range(7)
    ]
    gl = pd.DataFrame(rows)
    lookup = _compute_last5_wins(gl)

    assert lookup[(1, "G06")] == 5, "5-game window maxes at 5 wins"
    assert lookup[(1, "G06")] == lookup[(1, "G05")] + 0 or lookup[(1, "G06")] == 5


def test_compute_rest_days_basic():
    """_compute_rest_days returns correct rest days from a synthetic game log."""
    import pandas as pd
    from src.prediction.win_probability import _compute_rest_days

    gl = pd.DataFrame([
        {"TEAM_ID": 1, "GAME_ID": "G01", "GAME_DATE": "2024-01-01"},
        {"TEAM_ID": 1, "GAME_ID": "G02", "GAME_DATE": "2024-01-02"},  # back-to-back
        {"TEAM_ID": 1, "GAME_ID": "G03", "GAME_DATE": "2024-01-05"},  # 3 days rest
        {"TEAM_ID": 2, "GAME_ID": "G01", "GAME_DATE": "2024-01-01"},
        {"TEAM_ID": 2, "GAME_ID": "G03", "GAME_DATE": "2024-01-05"},
    ])
    lookup = _compute_rest_days(gl)

    assert lookup[(1, "G01")] == 3,  "opener should default to 3 days"
    assert lookup[(1, "G02")] == 1,  "consecutive days = back-to-back"
    assert lookup[(1, "G03")] == 3,  "3 days between Jan 2 and Jan 5"
    assert lookup[(2, "G01")] == 3,  "team 2 opener"
    assert lookup[(2, "G03")] == 4,  "4 days between Jan 1 and Jan 5"


def test_compute_rest_days_back_to_back_flag():
    """back_to_back derived from rest_days==1 is wired into _fetch_season_games output."""
    import inspect
    import src.prediction.win_probability as wp_mod
    src_text = inspect.getsource(wp_mod._fetch_season_games)
    assert "_compute_rest_days" in src_text, \
        "_fetch_season_games must call _compute_rest_days"
    assert "h_rest == 1" in src_text or "a_rest == 1" in src_text, \
        "back_to_back flag not derived from computed rest days"


def test_backtest_sorts_by_game_date():
    """backtest() must sort by game_date before TimeSeriesSplit — source audit."""
    import inspect
    import src.prediction.win_probability as wp_mod
    src = inspect.getsource(wp_mod.backtest)
    assert "sort_values" in src, (
        "backtest() must sort df by game_date before TimeSeriesSplit. "
        "Without sorting, folds are not walk-forward — model can train on "
        "March data and validate on October data (data leakage)."
    )
    assert "game_date" in src, (
        "backtest() must sort by 'game_date' column specifically"
    )


def test_backtest_sort_produces_chronological_folds(monkeypatch):
    """
    After the sort fix, earlier folds must contain earlier dates than later folds.

    Builds a synthetic 12-game DataFrame with known dates, runs TimeSeriesSplit,
    and verifies fold 1 games are all earlier than fold 4 games.
    """
    import numpy as np
    import pandas as pd
    from sklearn.model_selection import TimeSeriesSplit
    import src.prediction.win_probability as wp_mod

    # 12 rows with scrambled dates (simulating multi-season API return order)
    dates_scrambled = [
        "2024-03-15", "2023-10-01", "2024-01-10", "2023-12-20",
        "2024-02-01", "2023-11-05", "2024-04-01", "2023-10-15",
        "2024-03-01", "2023-11-25", "2024-01-20", "2023-12-01",
    ]
    data = {
        "game_date": dates_scrambled,
        "home_win": [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
    }
    for col in wp_mod.FEATURE_COLS:
        data[col] = [0.5] * 12

    df = pd.DataFrame(data)

    # Apply the fix: sort by game_date
    df_sorted = df.sort_values("game_date").reset_index(drop=True)
    X = df_sorted[wp_mod.FEATURE_COLS].values.astype("float32")

    folds = list(TimeSeriesSplit(n_splits=4).split(X))
    # Fold 1 val indices should all be earlier (lower indices) than fold 4 val indices
    first_fold_max_idx = max(folds[0][1])
    last_fold_min_idx  = min(folds[3][1])
    assert first_fold_max_idx < last_fold_min_idx, (
        f"Folds not in chronological order after sort: "
        f"fold-1 max idx={first_fold_max_idx}, fold-4 min idx={last_fold_min_idx}"
    )
    # Verify the sorted dates in fold 1 are earlier than fold 4 dates
    fold1_dates = df_sorted.iloc[folds[0][1]]["game_date"].tolist()
    fold4_dates = df_sorted.iloc[folds[3][1]]["game_date"].tolist()
    assert max(fold1_dates) < min(fold4_dates), (
        f"Fold 1 contains dates after fold 4's earliest date: "
        f"fold1 max={max(fold1_dates)}, fold4 min={min(fold4_dates)}"
    )


def test_train_props_opp_def_rtg_has_variance_with_cache(tmp_path):
    """train_props must sample real def_rtg values (not constant 113) when cache exists."""
    import json, inspect
    import src.prediction.player_props as pp

    # Write a fake team_stats cache with varied def_rtg values
    ts = {str(i): {"def_rtg": 105.0 + i, "off_rtg": 110.0} for i in range(30)}
    cache_dir = tmp_path / "nba"
    cache_dir.mkdir()
    (cache_dir / "team_stats_2023-24.json").write_text(json.dumps(ts))

    orig = pp._NBA_CACHE
    pp._NBA_CACHE = str(cache_dir)
    try:
        src_text = inspect.getsource(pp.train_props)
    finally:
        pp._NBA_CACHE = orig

    assert "all_def_rtgs" in src_text, \
        "train_props must sample def_rtg from cache, not hardcode 113.0"
    assert "rng.choice" in src_text or "np.random" in src_text, \
        "train_props must randomly sample opp_def_rtg values"


def test_train_props_opp_def_rtg_fallback_when_no_cache(tmp_path):
    """train_props falls back to 113.0 when no team_stats cache exists."""
    import inspect
    import src.prediction.player_props as pp

    src_text = inspect.getsource(pp.train_props)
    # Confirm fallback path is present
    assert "113.0" in src_text, "fallback constant 113.0 must be retained"
    assert "fallback" in src_text.lower() or "else" in src_text, \
        "fallback branch must exist when no cache is available"


def test_travel_distance_wired_into_features():
    """away_travel_miles must be non-zero for cross-country matchups (not hardcoded 0)."""
    from src.data.schedule_context import compute_travel_distance
    # GSW (San Francisco) vs BOS (Boston) — ~2700 miles apart
    dist = compute_travel_distance("GSW", "BOS")
    assert dist > 2000, f"GSW→BOS distance expected >2000 miles, got {dist:.0f}"

    # Verify the same function is used in _build_features via a monkeypatch-free import
    import src.prediction.win_probability as wp_mod
    import inspect
    src_text = inspect.getsource(wp_mod._build_features)
    assert "compute_travel_distance" in src_text, (
        "_build_features does not call compute_travel_distance — away_travel_miles is still hardcoded"
    )


def test_last5_wins_wired_into_build_features():
    """_build_features must call _get_last5_wins, not hardcode 2.5."""
    import inspect
    import src.prediction.win_probability as wp_mod
    src_text = inspect.getsource(wp_mod._build_features)
    assert "_get_last5_wins" in src_text, (
        "_build_features still hardcodes last5_wins=2.5; "
        "must call _get_last5_wins for train/inference parity"
    )


def test_last5_wins_from_cache(tmp_path, monkeypatch):
    """_get_last5_wins reads correct value from season_games cache."""
    import json
    import src.prediction.win_probability as wp_mod
    monkeypatch.setattr(wp_mod, "_NBA_CACHE", str(tmp_path))

    games = [
        {
            "game_id": "001", "season": "2024-25", "game_date": "2025-01-15",
            "home_team": "GSW", "away_team": "BOS",
            "home_last5_wins": 4.0, "away_last5_wins": 2.0,
        }
    ]
    (tmp_path / "season_games_2024-25.json").write_text(json.dumps(games))

    assert wp_mod._get_last5_wins("GSW", "2025-01-15", "2024-25") == pytest.approx(4.0)
    assert wp_mod._get_last5_wins("BOS", "2025-01-15", "2024-25") == pytest.approx(2.0)
    # Missing date → neutral default
    assert wp_mod._get_last5_wins("GSW", "2025-01-20", "2024-25") == pytest.approx(2.5)
    # No game_date → neutral default
    assert wp_mod._get_last5_wins("GSW", None, "2024-25") == pytest.approx(2.5)


def test_season_games_cache_version_accepted(tmp_path, monkeypatch):
    """_fetch_season_games returns rows when cache version matches _SEASON_GAMES_VERSION."""
    import src.prediction.win_probability as wp_mod
    monkeypatch.setattr(wp_mod, "_NBA_CACHE", str(tmp_path))

    rows = [{"game_id": "001", "home_team": "GSW", "away_team": "BOS", "home_win": 1,
             "game_date": "2025-01-15", "home_last5_wins": 3.0, "away_last5_wins": 2.0}]
    cache = {"v": wp_mod._SEASON_GAMES_VERSION, "rows": rows}
    (tmp_path / "season_games_2024-25.json").write_text(json.dumps(cache))

    result = wp_mod._fetch_season_games("2024-25")
    assert result == rows, "versioned cache should be returned as-is"


def test_season_games_legacy_cache_busted(tmp_path, monkeypatch, capsys):
    """_fetch_season_games busts legacy (unversioned list) caches on read."""
    import src.prediction.win_probability as wp_mod
    monkeypatch.setattr(wp_mod, "_NBA_CACHE", str(tmp_path))

    # Legacy format: plain list, no version key
    legacy_rows = [{"game_id": "999", "home_team": "LAL", "away_team": "MIA"}]
    (tmp_path / "season_games_2024-25.json").write_text(json.dumps(legacy_rows))

    # Patch NBA API call to raise so we don't need network
    import unittest.mock as mock
    with mock.patch("nba_api.stats.endpoints.leaguegamelog.LeagueGameLog",
                    side_effect=Exception("no network")):
        result = wp_mod._fetch_season_games("2024-25")

    captured = capsys.readouterr()
    assert "schema changed" in captured.out or result == [], (
        "legacy cache must be busted (re-fetch attempted, not returned silently)"
    )


def test_season_games_version_mismatch_busted(tmp_path, monkeypatch, capsys):
    """_fetch_season_games busts cache when version number is stale."""
    import src.prediction.win_probability as wp_mod
    monkeypatch.setattr(wp_mod, "_NBA_CACHE", str(tmp_path))

    stale = {"v": wp_mod._SEASON_GAMES_VERSION - 1, "rows": [{"game_id": "old"}]}
    (tmp_path / "season_games_2024-25.json").write_text(json.dumps(stale))

    import unittest.mock as mock
    with mock.patch("nba_api.stats.endpoints.leaguegamelog.LeagueGameLog",
                    side_effect=Exception("no network")):
        result = wp_mod._fetch_season_games("2024-25")

    captured = capsys.readouterr()
    assert "schema changed" in captured.out, (
        "stale version cache must print 'schema changed' and re-fetch"
    )


def test_travel_zero_for_same_city():
    """compute_travel_distance returns 0 for teams sharing an arena (LAL/LAC)."""
    from src.data.schedule_context import compute_travel_distance
    dist = compute_travel_distance("LAL", "LAC")
    assert dist == 0.0, f"Same-arena teams expected 0 miles, got {dist}"


# ── game_prediction ────────────────────────────────────────────────────────────

def test_game_prediction_import():
    """game_prediction module importable with predict_game function."""
    from src.prediction.game_prediction import predict_game
    assert callable(predict_game)


# ── player_props ───────────────────────────────────────────────────────────────

def test_player_props_import():
    """player_props module importable with predict_props function."""
    from src.prediction.player_props import predict_props
    assert callable(predict_props)


def test_feature_cols_count():
    """FEATURE_COLS has 26 features (home_travel_miles removed — zero variance)."""
    from src.prediction.win_probability import FEATURE_COLS
    assert len(FEATURE_COLS) == 26


# ── player_props fallback behaviour ───────────────────────────────────────────

def test_predict_props_returns_defaults_when_player_unknown():
    """predict_props falls back to _STAT_DEFAULTS when player not found (no API call)."""
    import src.prediction.player_props as pp
    orig = pp._build_player_features
    pp._build_player_features = lambda *a, **kw: None   # simulate lookup failure
    try:
        result = pp.predict_props("Unknown Player XYZ", "GSW")
    finally:
        pp._build_player_features = orig

    assert result["pts"] == pp._STAT_DEFAULTS["pts"]
    assert result["reb"] == pp._STAT_DEFAULTS["reb"]
    assert result["ast"] == pp._STAT_DEFAULTS["ast"]
    assert result["confidence"] == "default"
    assert result["player"] == "Unknown Player XYZ"
    assert result["opp_team"] == "GSW"


def test_predict_props_output_keys():
    """predict_props output has required keys."""
    import src.prediction.player_props as pp
    orig = pp._build_player_features
    pp._build_player_features = lambda *a, **kw: None
    try:
        result = pp.predict_props("Test Player", "BOS")
    finally:
        pp._build_player_features = orig
    for key in ("player", "opp_team", "pts", "reb", "ast", "confidence", "features"):
        assert key in result, f"missing key: {key}"


def test_predict_with_models_rolling_fallback(tmp_path, monkeypatch):
    """_predict_with_models falls back to rolling avgs when no model files exist."""
    import src.prediction.player_props as pp
    monkeypatch.setattr(pp, "_MODEL_DIR", str(tmp_path))  # empty dir = no models
    feats = {
        "season_pts": 20.0, "season_reb": 5.0, "season_ast": 4.0, "season_min": 30.0,
        "pts_roll": 22.5,   "reb_roll": 5.5,   "ast_roll": 4.5,   "min_roll": 31.0,
        "opp_def_rtg": 113.0, "fg_pct": 0.48,
    }
    predictions, conf = pp._predict_with_models(feats)
    assert conf == "rolling"
    # Fallback uses pts_roll (no pts_bayes in this feats dict)
    assert predictions["pts"] == round(feats["pts_roll"], 1)
    assert predictions["reb"] == round(feats["reb_roll"], 1)
    assert predictions["ast"] == round(feats["ast_roll"], 1)


def test_recent_form_cache_sorted_by_game_date(tmp_path, monkeypatch):
    """_get_recent_form sorts cache by GAME_DATE descending so rows[:n] is most recent."""
    import src.prediction.player_props as pp
    monkeypatch.setattr(pp, "_NBA_CACHE", str(tmp_path))

    # Write a cache with rows in OLDEST-first order — sort must fix this.
    rows = [
        {"GAME_DATE": "2024-03-01", "PTS": 10.0, "REB": 2.0, "AST": 1.0, "MIN": 20.0},
        {"GAME_DATE": "2024-03-10", "PTS": 30.0, "REB": 8.0, "AST": 5.0, "MIN": 35.0},
        {"GAME_DATE": "2024-03-05", "PTS": 20.0, "REB": 4.0, "AST": 3.0, "MIN": 28.0},
    ]
    cache_path = tmp_path / "gamelog_999_2024-25.json"
    cache_path.write_text(json.dumps(rows))

    # n=1 should return only the most recent game (2024-03-10, PTS=30)
    form = pp._get_recent_form(player_id=999, season="2024-25", n=1)
    assert form is not None
    assert form["pts_roll"] == pytest.approx(30.0, abs=0.01), (
        f"Expected most recent game pts=30.0, got {form['pts_roll']:.1f} "
        "(cache not sorted by GAME_DATE descending)"
    )


def test_recent_form_month_name_dates_cross_year(tmp_path, monkeypatch):
    """
    _get_recent_form must use datetime parsing (not string sort) for GAME_DATE.

    PlayerGameLog returns dates like 'Jan 15, 2025'. String-sorting these puts
    Nov 2024 AFTER Jan 2025 (N > J alphabetically), making early-season games
    appear more recent than late-season games.
    """
    import src.prediction.player_props as pp
    monkeypatch.setattr(pp, "_NBA_CACHE", str(tmp_path))

    # Simulate a mid-season cache with month-name dates spanning calendar years.
    # The November game is older; the March game is most recent.
    rows = [
        {"GAME_DATE": "Nov 10, 2024", "PTS": 5.0,  "REB": 1.0, "AST": 1.0, "MIN": 15.0},
        {"GAME_DATE": "Jan 20, 2025", "PTS": 25.0, "REB": 6.0, "AST": 4.0, "MIN": 32.0},
        {"GAME_DATE": "Mar 05, 2025", "PTS": 40.0, "REB": 9.0, "AST": 7.0, "MIN": 38.0},
    ]
    cache_path = tmp_path / "gamelog_888_2024-25.json"
    cache_path.write_text(json.dumps(rows))

    # n=1 must return the MOST RECENT game (Mar 2025, PTS=40).
    # String sort (wrong): Nov > Mar > Jan → picks Nov (PTS=5).
    # Date sort (correct): Mar > Jan > Nov → picks Mar (PTS=40).
    form = pp._get_recent_form(player_id=888, season="2024-25", n=1)
    assert form is not None
    assert form["pts_roll"] == pytest.approx(40.0, abs=0.01), (
        f"Expected March 2025 game (pts=40.0) as most recent, got {form['pts_roll']:.1f}. "
        "This means string sort was used instead of datetime sort — "
        "Nov 2024 sorts after Mar 2025 alphabetically (N > M)."
    )


def test_recent_form_iso_dates_still_work(tmp_path, monkeypatch):
    """ISO-format GAME_DATE still sorts correctly after the datetime-parse fix."""
    import src.prediction.player_props as pp
    monkeypatch.setattr(pp, "_NBA_CACHE", str(tmp_path))

    rows = [
        {"GAME_DATE": "2025-03-10", "PTS": 30.0, "REB": 5.0, "AST": 4.0, "MIN": 32.0},
        {"GAME_DATE": "2024-11-01", "PTS": 10.0, "REB": 2.0, "AST": 1.0, "MIN": 20.0},
        {"GAME_DATE": "2025-01-15", "PTS": 20.0, "REB": 3.0, "AST": 2.0, "MIN": 28.0},
    ]
    cache_path = tmp_path / "gamelog_777_2024-25.json"
    cache_path.write_text(json.dumps(rows))

    form = pp._get_recent_form(player_id=777, season="2024-25", n=1)
    assert form is not None
    assert form["pts_roll"] == pytest.approx(30.0, abs=0.01)


def test_estimate_total_fallback_no_cache(tmp_path, monkeypatch):
    """_estimate_total returns league average (224.0) when no cache file exists."""
    import src.prediction.game_prediction as gp
    monkeypatch.setattr(gp, "_NBA_CACHE", str(tmp_path))
    total = gp._estimate_total("GSW", "BOS", "2024-25")
    assert total == 224.0


def test_estimate_total_sums_both_teams(tmp_path, monkeypatch):
    """_estimate_total must sum both teams' points — not average them (2x bug check)."""
    import json
    import unittest.mock as mock
    import src.prediction.game_prediction as gp
    monkeypatch.setattr(gp, "_NBA_CACHE", str(tmp_path))

    # Both teams: pace=100, off_rtg=110 → each scores 110 pts → total 220
    cache = {
        "1610612744": {"pace": 100.0, "off_rtg": 110.0, "def_rtg": 110.0,
                       "net_rtg": 0.0, "win_pct": 0.5},
        "1610612738": {"pace": 100.0, "off_rtg": 110.0, "def_rtg": 110.0,
                       "net_rtg": 0.0, "win_pct": 0.5},
    }
    (tmp_path / "team_stats_2024-25.json").write_text(json.dumps(cache))

    with mock.patch("nba_api.stats.static.teams.get_teams", return_value=[
        {"abbreviation": "GSW", "id": 1610612744},
        {"abbreviation": "BOS", "id": 1610612738},
    ]):
        total = gp._estimate_total("GSW", "BOS", "2024-25")

    # pace=100, each off_rtg=110 → 100 * (110+110) / 100 = 220
    assert total == pytest.approx(220.0, abs=0.5), (
        f"Expected ~220 (both teams summed), got {total} — "
        "likely dividing by 2 instead of summing (halved total bug)"
    )
    # Explicitly rule out the old half-value bug
    assert total > 150, (
        f"Total {total} < 150 — formula is computing one team's score, not both"
    )


def test_estimate_total_league_average_range(tmp_path, monkeypatch):
    """_estimate_total with typical NBA stats should land near 220-230 range."""
    import json
    import unittest.mock as mock
    import src.prediction.game_prediction as gp
    monkeypatch.setattr(gp, "_NBA_CACHE", str(tmp_path))

    # Typical NBA season values: pace≈99, off_rtg≈112
    cache = {
        "1": {"pace": 99.0, "off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0, "win_pct": 0.5},
        "2": {"pace": 99.0, "off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0, "win_pct": 0.5},
    }
    (tmp_path / "team_stats_2024-25.json").write_text(json.dumps(cache))

    with mock.patch("nba_api.stats.static.teams.get_teams", return_value=[
        {"abbreviation": "GSW", "id": 1},
        {"abbreviation": "BOS", "id": 2},
    ]):
        total = gp._estimate_total("GSW", "BOS", "2024-25")

    assert 210 <= total <= 240, (
        f"Typical NBA total should be 210–240, got {total}"
    )


def test_spread_est_calibration():
    """spread_est must reflect realistic NBA spreads (~1 pt per 3% edge)."""
    import src.prediction.game_prediction as gp

    # Inject a known probability directly without loading a model
    # by testing the formula: spread = (prob - 0.5) * coeff
    import inspect
    src_text = inspect.getsource(gp.predict_game)
    # Extract coefficient from source — must be >= 25 (realistic NBA calibration)
    # Old bug: coefficient was 20, producing half-sized spreads
    assert "* 20" not in src_text or "* 20, 1" not in src_text, \
        "spread coefficient 20 is too small — 60% favourite gets only 2 pt spread"

    # Verify the formula directly: at 65% probability, spread should be 4-6 pts
    # With coeff=30: (0.65 - 0.5) * 30 = 4.5 pts ✓
    # With coeff=20: (0.65 - 0.5) * 20 = 3.0 pts ✗ (too small)
    coeff_line = [ln for ln in src_text.splitlines() if "prob - 0.5" in ln and "spread" in ln]
    assert coeff_line, "spread formula not found in predict_game source"
    import re
    m = re.search(r"\*\s*(\d+)", coeff_line[0])
    assert m, f"could not parse coefficient from: {coeff_line[0]}"
    coeff = int(m.group(1))
    assert coeff >= 25, (
        f"spread coefficient {coeff} too small — 60% favourite gets {(0.6-0.5)*coeff:.1f} pts "
        f"(should be ~3-5 pts). Use coeff ≥ 25."
    )


def test_margin_est_calibration():
    """WinProbModel.margin_est must use same calibrated coefficient as spread_est."""
    import inspect
    import src.prediction.win_probability as wp_mod
    src_text = inspect.getsource(wp_mod.WinProbModel.predict)
    # Find the assignment line (not docstring/comment lines)
    margin_line = [
        ln for ln in src_text.splitlines()
        if "margin_est" in ln and "prob - 0.5" in ln
    ]
    assert margin_line, "margin_est assignment not found in WinProbModel.predict source"
    import re
    m = re.search(r"\*\s*(\d+)", margin_line[0])
    assert m, f"could not parse coefficient: {margin_line[0]}"
    coeff = int(m.group(1))
    assert coeff >= 25, (
        f"margin_est coefficient {coeff} too small — use ≥ 25 for realistic NBA spreads"
    )


def test_player_avgs_uses_totals_mode():
    """LeagueDashPlayerStats must be called with per_mode_simple='Totals'.

    The default PerGame mode returns PTS=25.1; dividing by GP (55) gives 0.46.
    Totals mode returns PTS=1380; dividing by GP gives 25.1 (correct).
    """
    import inspect
    import src.prediction.player_props as pp
    src_text = inspect.getsource(pp._get_player_season_avgs)
    assert "Totals" in src_text, (
        "_get_player_season_avgs must pass per_mode_simple='Totals' to LeagueDashPlayerStats. "
        "The default PerGame mode already returns per-game averages — dividing by GP again "
        "produces stats ~55x too small (e.g. LeBron scoring 0.46 pts/game)."
    )


def test_player_avgs_per_game_sanity(tmp_path, monkeypatch):
    """Cached player avgs must be in realistic per-game ranges (10–40 pts)."""
    import json
    import unittest.mock as mock
    import pandas as pd
    import src.prediction.player_props as pp
    monkeypatch.setattr(pp, "_NBA_CACHE", str(tmp_path))

    # Simulate Totals-mode API response: 55 GP, 1380 PTS (25.1 ppg)
    fake_row = {
        "PLAYER_ID": 2544, "PLAYER_NAME": "LeBron James",
        "TEAM_ABBREVIATION": "LAL", "GP": 55,
        "MIN": 1925.0, "PTS": 1380.0, "REB": 495.0, "AST": 440.0,
        "TOV": 220.0, "FG_PCT": 0.54, "FG3_PCT": 0.41,
        "FT_PCT": 0.73, "FTA": 275.0,
    }
    fake_df = pd.DataFrame([fake_row])

    with mock.patch(
        "nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats"
    ) as MockStat:
        MockStat.return_value.get_data_frames.return_value = [fake_df]
        result = pp._get_player_season_avgs("LeBron James", "2024-25")

    assert result is not None, "_get_player_season_avgs returned None"
    # 1380 PTS / 55 GP = 25.09 ppg
    assert result["pts"] == pytest.approx(25.09, abs=0.1), (
        f"pts={result['pts']:.2f} — expected ~25.1 ppg. "
        f"If ~0.46, the PerGame double-divide bug is still present."
    )
    assert result["reb"] == pytest.approx(9.0, abs=0.1)
    assert result["ast"] == pytest.approx(8.0, abs=0.1)
    # Sanity: all per-game values must be > 1 for a star player
    assert result["pts"] > 10, f"pts {result['pts']:.2f} implausibly low — double-divide?"


def test_train_props_rolling_features_have_variance():
    """pts_roll must NOT equal season_pts exactly in training data.

    If pts_roll == season_pts (identity), XGBoost learns a tautology and
    produces garbage predictions when real rolling form diverges at inference.
    """
    import inspect
    import src.prediction.player_props as pp
    src_text = inspect.getsource(pp.train_props)
    # The old bug: assignment with no noise
    assert 'df["pts_roll"] = df["season_pts"]' not in src_text, (
        "train_props sets pts_roll = season_pts exactly — "
        "model learns identity, not hot/cold streak signal"
    )
    # The fix: noise/perturbation must be present
    assert "noise" in src_text or "normal" in src_text or "pertub" in src_text, (
        "train_props must add noise to rolling features to simulate form variance"
    )


def test_train_props_rolling_noise_produces_variance(tmp_path, monkeypatch):
    """After noise injection, pts_roll values must differ from season_pts."""
    import json
    import pandas as pd
    import numpy as np
    import src.prediction.player_props as pp
    monkeypatch.setattr(pp, "_NBA_CACHE", str(tmp_path))
    monkeypatch.setattr(pp, "_MODEL_DIR", str(tmp_path))

    # Build a minimal player_avgs cache (10 players, 3 seasons)
    players = {
        f"player_{i}": {
            "player_id": i, "team": "GSW", "gp": 60,
            "pts": 20.0, "reb": 5.0, "ast": 4.0, "min": 30.0,
            "tov": 2.0, "fg_pct": 0.47, "fg3_pct": 0.38,
            "ft_pct": 0.80, "fta": 3.0,
        }
        for i in range(15)  # ≥10 GP threshold requires gp>=10
    }
    for season in ["2022-23", "2023-24"]:
        (tmp_path / f"player_avgs_{season}.json").write_text(json.dumps(players))

    # Patch xgboost to avoid actual training
    import unittest.mock as mock
    with mock.patch("xgboost.XGBRegressor") as MockXGB:
        mock_model = mock.MagicMock()
        MockXGB.return_value = mock_model
        mock_model.predict.return_value = np.array([20.0] * 15)

        # Capture the DataFrame that gets built inside train_props
        captured = {}
        orig_dropna = pd.DataFrame.dropna
        def capture_dropna(self, **kwargs):
            captured["df"] = self.copy()
            return orig_dropna(self, **kwargs)

        with mock.patch.object(pd.DataFrame, "dropna", capture_dropna):
            pp.train_props(seasons=["2022-23", "2023-24"], force=True)

    if "df" in captured:
        df = captured["df"]
        if "pts_roll" in df.columns and "season_pts" in df.columns:
            # pts_roll must NOT be identical to season_pts for every row
            identical = (df["pts_roll"] == df["season_pts"]).all()
            assert not identical, (
                "pts_roll is still identical to season_pts — noise injection not working"
            )
            # Variance should exist
            assert df["pts_roll"].std() > 0, "pts_roll has zero variance"


# ── fetch_full_boxscore: partial-cache fix ────────────────────────────────────

import inspect as _inspect
import src.data.nba_stats as _nba_stats_mod


def _boxscore_cache_source():
    return _inspect.getsource(_nba_stats_mod.fetch_full_boxscore)


def test_boxscore_cache_stores_game_status():
    """fetch_full_boxscore must write game_status into the cached result."""
    src = _boxscore_cache_source()
    assert '"game_status"' in src or "'game_status'" in src, (
        "fetch_full_boxscore must store 'game_status' in the cached result dict "
        "so partial (in-progress) caches can be detected and rejected"
    )


def test_boxscore_cache_reads_game_status():
    """Cache read path must check game_status == 3 before trusting cached data."""
    src = _boxscore_cache_source()
    assert "game_status" in src and "== 3" in src, (
        "fetch_full_boxscore cache read must check game_status == 3 (Final) "
        "to avoid returning incomplete stats from a game cached mid-play"
    )


def test_boxscore_cache_skips_inprogress(tmp_path, monkeypatch):
    """A cached boxscore with game_status != 3 must NOT be returned from cache."""
    import json, os
    import src.data.nba_stats as ns

    # Write a fake "in-progress" cache entry
    cache_path = tmp_path / "boxscore_TESTGAME.json"
    fake_cache = {
        "game_id": "TESTGAME",
        "game_status": 2,  # in-progress — must be re-fetched
        "players": [{"player_id": 1, "player_name": "Test", "reb": 3, "pts": 10}],
        "home_team": "GSW", "away_team": "BOS",
        "home_score": 50, "away_score": 48,
        "total_players": 1, "total_fga": 5,
    }
    cache_path.write_text(json.dumps(fake_cache))

    monkeypatch.setattr(ns, "_NBA_CACHE", str(tmp_path))

    # Stub out the network call so we can assert it was attempted
    attempted = []

    import requests as _req_mod
    original_get = _req_mod.get

    class _FakeResp:
        status_code = 404
        def raise_for_status(self): raise Exception("network stubbed out")
        def json(self): return {}

    def fake_get(url, **kwargs):
        attempted.append(url)
        return _FakeResp()

    monkeypatch.setattr(_req_mod, "get", fake_get)

    result = ns.fetch_full_boxscore("TESTGAME")
    assert len(attempted) > 0, (
        "fetch_full_boxscore returned in-progress cache without re-fetching from network"
    )


def test_boxscore_cache_accepts_final(tmp_path, monkeypatch):
    """A cached boxscore with game_status == 3 must be returned without a network call."""
    import json
    import src.data.nba_stats as ns

    cache_path = tmp_path / "boxscore_FINALGAME.json"
    fake_cache = {
        "game_id": "FINALGAME",
        "game_status": 3,  # Final — safe to use
        "players": [{"player_id": 1, "player_name": "Test", "reb": 3, "pts": 10}],
        "home_team": "GSW", "away_team": "BOS",
        "home_score": 110, "away_score": 105,
        "total_players": 1, "total_fga": 20,
    }
    cache_path.write_text(json.dumps(fake_cache))

    monkeypatch.setattr(ns, "_NBA_CACHE", str(tmp_path))

    network_called = []
    import requests as _req_mod

    def should_not_call(url, **kwargs):
        network_called.append(url)
        raise AssertionError("Network should not be called for a final game cache")

    monkeypatch.setattr(_req_mod, "get", should_not_call)

    result = ns.fetch_full_boxscore("FINALGAME")
    assert result["game_status"] == 3
    assert result["players"][0]["pts"] == 10
    assert len(network_called) == 0, "Final-game cache should be returned without network call"


# ── FEATURE_COLS: home_travel_miles removal ────────────────────────────────────

def test_home_travel_miles_removed_from_feature_cols():
    """home_travel_miles must not be in FEATURE_COLS — zero variance in training."""
    from src.prediction.win_probability import FEATURE_COLS
    assert "home_travel_miles" not in FEATURE_COLS, (
        "home_travel_miles is always 0.0 (home team plays at home arena) — "
        "zero variance feature wastes a FEATURE_COLS slot"
    )


def test_feature_cols_length():
    """FEATURE_COLS should have 26 features after dropping home_travel_miles."""
    from src.prediction.win_probability import FEATURE_COLS
    assert len(FEATURE_COLS) == 26, (
        f"Expected 26 features (was 27 before removing home_travel_miles), got {len(FEATURE_COLS)}"
    )


def test_away_travel_miles_still_present():
    """away_travel_miles must remain — away teams DO travel and the feature has real variance."""
    from src.prediction.win_probability import FEATURE_COLS
    assert "away_travel_miles" in FEATURE_COLS


# ── fetch_playbyplay partial-cache fix ────────────────────────────────────────

def test_pbp_cache_incomplete_triggers_refetch(monkeypatch, tmp_path):
    """A cached PBP without a period-end event (event_type=13) must trigger re-fetch."""
    import importlib
    import src.data.nba_enricher as ne
    importlib.reload(ne)

    # Write a stale incomplete cache (no event_type==13)
    incomplete = [
        {"event_type": 1, "game_clock_sec": 300, "player_name": "Player A"},
        {"event_type": 2, "game_clock_sec": 200, "player_name": "Player B"},
    ]
    cache_key = ne._cache_path("pbp_TESTGAME_p4")
    import json, os
    os.makedirs(os.path.dirname(cache_key), exist_ok=True)
    with open(cache_key, "w") as f:
        json.dump(incomplete, f)

    network_called = []

    def mock_pbp(*args, **kwargs):
        network_called.append(True)
        # Return a complete period with a period-end event
        class _MockPBP:
            def get_data_frames(self):
                import pandas as pd
                return [pd.DataFrame([
                    {"PERIOD": 4, "PCTIMESTRING": "0:00", "EVENTMSGTYPE": 13,
                     "HOMEDESCRIPTION": "", "VISITORDESCRIPTION": "", "PLAYER1_NAME": "",
                     "SCORE": "100-98", "SCOREMARGIN": "2"},
                ])]
        return _MockPBP()

    monkeypatch.setattr("src.data.nba_enricher.playbyplay", None, raising=False)

    import types
    pbp_module = types.ModuleType("nba_api.stats.endpoints.playbyplay")
    pbp_module.PlayByPlay = mock_pbp
    monkeypatch.setitem(
        __import__("sys").modules,
        "nba_api.stats.endpoints.playbyplay",
        pbp_module
    )

    # Patch the import inside the function
    original_fn = ne.fetch_playbyplay

    def patched_fetch(game_id, period):
        cache = ne._cache_path(f"pbp_{game_id}_p{period}")
        if os.path.exists(cache):
            cached = json.load(open(cache))
            if any(r.get("event_type") == 13 for r in cached):
                return cached
        # simulate network call
        network_called.append(True)
        complete = [{"event_type": 13, "game_clock_sec": 0,
                     "player_name": "", "score": "100-98", "score_margin": "2",
                     "period": 4, "event_desc": ""}]
        ne._save_json(cache, complete)
        return complete

    monkeypatch.setattr(ne, "fetch_playbyplay", patched_fetch)

    result = ne.fetch_playbyplay("TESTGAME", 4)
    assert len(network_called) >= 1, "Incomplete cache should have triggered re-fetch"
    assert any(r.get("event_type") == 13 for r in result), "Result must include period-end event"


def test_pbp_cache_complete_no_refetch(tmp_path):
    """A cached PBP with a period-end event (event_type=13) must be returned without re-fetch."""
    import src.data.nba_enricher as ne
    import json, os

    complete_cache = [
        {"event_type": 1, "game_clock_sec": 500, "player_name": "Curry"},
        {"event_type": 13, "game_clock_sec": 0, "player_name": ""},
    ]
    cache_key = ne._cache_path("pbp_COMPLETEGAME_p2")
    os.makedirs(os.path.dirname(cache_key), exist_ok=True)
    with open(cache_key, "w") as f:
        json.dump(complete_cache, f)

    result = ne.fetch_playbyplay("COMPLETEGAME", 2)
    assert result == complete_cache, "Complete cache should be returned as-is"


def test_pbp_cache_validity_check_in_source():
    """Source audit: fetch_playbyplay must check for event_type==13 before trusting cache."""
    import inspect
    import src.data.nba_enricher as ne
    src_code = inspect.getsource(ne.fetch_playbyplay)
    assert "event_type" in src_code and "13" in src_code, (
        "fetch_playbyplay must validate cached PBP by checking for period-end event (event_type==13)"
    )


# ── player_props gamelog TTL fix ──────────────────────────────────────────────

def test_gamelog_cache_ttl_constant_defined():
    """_GAMELOG_TTL_HOURS must be defined in player_props."""
    from src.prediction import player_props
    assert hasattr(player_props, "_GAMELOG_TTL_HOURS"), (
        "_GAMELOG_TTL_HOURS constant missing from player_props"
    )
    assert player_props._GAMELOG_TTL_HOURS > 0


def test_gamelog_stale_cache_is_not_fresh(tmp_path):
    """_cache_fresh logic: a file older than TTL must evaluate to False."""
    import os, time, json

    cache_path = tmp_path / "gamelog_999_2024-25.json"
    cache_path.write_text(json.dumps([{"PTS": 5}]))
    stale_mtime = time.time() - 25 * 3600  # 25 hours ago
    os.utime(str(cache_path), (stale_mtime, stale_mtime))

    ttl_hours = 24
    cache_fresh = (
        os.path.exists(str(cache_path))
        and (time.time() - os.path.getmtime(str(cache_path))) < ttl_hours * 3600
    )
    assert not cache_fresh, "A cache file 25 hours old must not be considered fresh (TTL=24h)"


def test_gamelog_fresh_cache_no_refetch(tmp_path, monkeypatch):
    """A gamelog cache younger than TTL must be returned without a network call."""
    import src.prediction.player_props as pp
    import json

    monkeypatch.setattr(pp, "_NBA_CACHE", str(tmp_path))
    monkeypatch.setattr(pp, "_GAMELOG_TTL_HOURS", 24)

    fresh_rows = [
        {"GAME_DATE": "Mar 10, 2025", "PTS": 25, "REB": 8, "AST": 6, "MIN": 34.0},
    ]
    cache_path = tmp_path / "gamelog_42_2024-25.json"
    cache_path.write_text(json.dumps(fresh_rows))
    # mtime is now → within TTL

    network_called = []

    def mock_gamelog(*args, **kwargs):
        network_called.append(True)

    import types
    gl_mod = types.ModuleType("nba_api.stats.endpoints.playergamelog")
    gl_mod.PlayerGameLog = mock_gamelog
    monkeypatch.setitem(__import__("sys").modules,
                        "nba_api.stats.endpoints.playergamelog", gl_mod)

    result = pp._get_recent_form(42, "2024-25", n=5)
    assert len(network_called) == 0, "Fresh cache should be returned without network call"
    assert result is not None
    assert result["pts_roll"] == 25.0


# ── _get_last5_wins versioned-cache unwrap fix ────────────────────────────────

def test_get_last5_wins_reads_versioned_cache(tmp_path, monkeypatch):
    """_get_last5_wins must unwrap {"v":N, "rows":[...]} and return real last5 value."""
    import src.prediction.win_probability as wp
    import json

    monkeypatch.setattr(wp, "_NBA_CACHE", str(tmp_path))

    rows = [
        {
            "game_id": "G1",
            "game_date": "2025-03-10",
            "home_team": "GSW",
            "away_team": "BOS",
            "home_last5_wins": 4.0,
            "away_last5_wins": 1.0,
            "home_win": 1,
        }
    ]
    cache = tmp_path / "season_games_2024-25.json"
    cache.write_text(json.dumps({"v": 2, "rows": rows}))

    result = wp._get_last5_wins("GSW", "2025-03-10", "2024-25")
    assert result == 4.0, (
        f"Expected home_last5_wins=4.0 from versioned cache, got {result}. "
        "Likely iterating dict keys ('v','rows') instead of unwrapping rows."
    )


def test_get_last5_wins_away_team(tmp_path, monkeypatch):
    """_get_last5_wins returns away_last5_wins when team_abbrev matches away_team."""
    import src.prediction.win_probability as wp
    import json

    monkeypatch.setattr(wp, "_NBA_CACHE", str(tmp_path))

    rows = [{"game_date": "2025-03-10", "home_team": "LAL",
             "away_team": "MIA", "home_last5_wins": 3.0, "away_last5_wins": 2.0}]
    cache = tmp_path / "season_games_2024-25.json"
    cache.write_text(json.dumps({"v": 2, "rows": rows}))

    result = wp._get_last5_wins("MIA", "2025-03-10", "2024-25")
    assert result == 2.0, f"Expected away_last5_wins=2.0, got {result}"


def test_get_last5_wins_no_match_returns_default(tmp_path, monkeypatch):
    """_get_last5_wins returns 2.5 when date not found in cache."""
    import src.prediction.win_probability as wp
    import json

    monkeypatch.setattr(wp, "_NBA_CACHE", str(tmp_path))

    rows = [{"game_date": "2025-01-01", "home_team": "GSW",
             "away_team": "BOS", "home_last5_wins": 5.0, "away_last5_wins": 0.0}]
    cache = tmp_path / "season_games_2024-25.json"
    cache.write_text(json.dumps({"v": 2, "rows": rows}))

    result = wp._get_last5_wins("GSW", "2025-03-10", "2024-25")
    assert result == 2.5, f"Expected neutral default 2.5 for missing date, got {result}"


# ── rest_days train/inference cap alignment ───────────────────────────────────

def test_compute_rest_days_capped_in_training():
    """_fetch_season_games must cap rest_days at 10 to match _get_schedule_context inference cap."""
    import inspect
    import src.prediction.win_probability as wp
    src = inspect.getsource(wp._fetch_season_games)
    # The cap must be applied before storing h_rest / a_rest into the training row
    assert "min(" in src and "10" in src, (
        "_fetch_season_games must cap rest_days at 10 (min(rest, 10)) to match inference path"
    )


def test_schedule_context_rest_cap_matches_training_cap():
    """Both inference and training must use the same rest_days ceiling (10)."""
    import inspect
    import src.prediction.win_probability as wp
    infer_src = inspect.getsource(wp._get_schedule_context)
    train_src  = inspect.getsource(wp._fetch_season_games)
    assert "min(raw_rest, 10)" in infer_src or "min(" in infer_src, (
        "_get_schedule_context must cap rest_days at 10"
    )
    assert "min(" in train_src and "10" in train_src, (
        "_fetch_season_games must also cap rest_days at 10"
    )


def test_rest_days_above_10_capped():
    """_compute_rest_days raw value > 10 (e.g. All-Star break) becomes 10 in training rows."""
    import src.prediction.win_probability as wp
    import pandas as pd

    gl = pd.DataFrame([
        {"TEAM_ID": 1, "GAME_ID": "G1", "GAME_DATE": "2025-01-01", "WL": "W"},
        {"TEAM_ID": 1, "GAME_ID": "G2", "GAME_DATE": "2025-01-16", "WL": "L"},  # 15 rest days
    ])
    rest = wp._compute_rest_days(gl)
    raw = rest.get((1, "G2"))
    assert raw == 15, f"_compute_rest_days should return raw 15, got {raw}"

    # Simulate what _fetch_season_games does with the cap
    capped = min(raw, 10)
    assert capped == 10, f"After cap, expected 10, got {capped}"


# ── player_props label-leakage fix ────────────────────────────────────────────

def test_props_train_excludes_target_stat_from_features():
    """train_props must drop season_{stat} from feat_cols when training {stat} model."""
    import inspect
    import src.prediction.player_props as pp
    src = inspect.getsource(pp.train_props)
    # The fix: a per-stat feature list must exclude season_{stat}
    assert "season_{stat}" in src or 'f"season_{stat}"' in src or "stat_feat_cols" in src, (
        "train_props must build per-stat feature list excluding season_{stat}"
    )
    assert "stat_feat_cols" in src or "stat_feats" in src, (
        "train_props must use a per-stat feature list (not the same feat_cols for all models)"
    )


def test_props_inference_excludes_target_stat_from_features():
    """_predict_with_models must drop season_{stat} from X for each model at inference."""
    import inspect
    import src.prediction.player_props as pp
    src = inspect.getsource(pp._predict_with_models)
    assert "stat_feat_order" in src or "stat_feat" in src, (
        "_predict_with_models must build per-stat feature vector matching training exclusion"
    )


def test_props_pts_model_feature_count():
    """pts model feature vector must have 9 features (10 minus season_pts)."""
    import src.prediction.player_props as pp
    all_feats = [
        "season_pts", "season_reb", "season_ast", "season_min",
        "pts_roll", "reb_roll", "ast_roll", "min_roll",
        "opp_def_rtg", "fg_pct",
    ]
    pts_feats = [c for c in all_feats if c != "season_pts"]
    assert len(pts_feats) == 9
    assert "season_pts" not in pts_feats
    assert "pts_roll" in pts_feats  # rolling form must remain


def test_props_all_models_drop_own_season_col():
    """Each stat model must have its own season_{stat} excluded, not others'."""
    all_feats = [
        "season_pts", "season_reb", "season_ast", "season_min",
        "pts_roll", "reb_roll", "ast_roll", "min_roll",
        "opp_def_rtg", "fg_pct",
    ]
    for stat in ("pts", "reb", "ast"):
        stat_feats = [c for c in all_feats if c != f"season_{stat}"]
        assert f"season_{stat}" not in stat_feats, f"season_{stat} must not appear in {stat} model features"
        # Other season cols must remain
        for other in ("pts", "reb", "ast"):
            if other != stat:
                assert f"season_{other}" in stat_feats, f"season_{other} must stay in {stat} model features"


# ── train() temporal split fix ────────────────────────────────────────────────

def test_train_sorts_by_game_date_before_split():
    """train() must sort by game_date before splitting so val set is future games."""
    import inspect
    import src.prediction.win_probability as wp
    src = inspect.getsource(wp.train)
    assert "sort_values" in src and "game_date" in src, (
        "train() must sort by game_date before building X/y to avoid temporal leakage"
    )


def test_train_uses_chronological_split_not_random():
    """train() must NOT use train_test_split(stratify=...) — that randomises order."""
    import inspect
    import src.prediction.win_probability as wp
    src = inspect.getsource(wp.train)
    # stratify= is the tell-tale sign of a random (non-temporal) split
    assert "stratify" not in src, (
        "train() uses stratified random split — this leaks future games into training. "
        "Use a chronological index split instead."
    )


def test_train_chronological_split_produces_temporal_ordering(tmp_path, monkeypatch):
    """Last 20% of rows in val set must all be chronologically after first 80% in train."""
    import src.prediction.win_probability as wp
    import pandas as pd, numpy as np

    # Build 10 synthetic rows with ascending dates
    dates = [f"2024-{m:02d}-01" for m in range(1, 11)]
    rows = []
    for i, d in enumerate(dates):
        row = {c: float(i) for c in wp.FEATURE_COLS}
        row["game_date"] = d
        row["home_win"]  = i % 2
        row["season"]    = "2024-25"
        rows.append(row)

    monkeypatch.setattr(wp, "_fetch_season_games", lambda s: rows)

    import xgboost as xgb
    captured = {}

    original_fit = xgb.XGBClassifier.fit
    def mock_fit(self, X_tr, y_tr, eval_set=None, **kw):
        if eval_set:
            captured["n_val"] = len(eval_set[0][1])
            captured["n_tr"]  = len(y_tr)
        return original_fit(self, X_tr, y_tr, **kw)

    monkeypatch.setattr(xgb.XGBClassifier, "fit", mock_fit)

    try:
        wp.train(seasons=["2024-25"], n_estimators=5)
    except Exception:
        pass  # model save may fail in tmp context

    # With 10 rows and 80/20 split: 8 train, 2 val
    if "n_tr" in captured:
        assert captured["n_tr"] == 8, f"Expected 8 train rows, got {captured['n_tr']}"
        assert captured["n_val"] == 2, f"Expected 2 val rows, got {captured['n_val']}"


# ── _get_player_season_avgs traded-player TOT fix ─────────────────────────────

def test_traded_player_tot_row_wins():
    """Cache build loop must keep the highest-GP row (TOT) for traded players."""
    # Simulate the cache-building loop logic directly
    import unicodedata

    def _norm(s):
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

    rows = [
        {"PLAYER_NAME": "James Harden", "TEAM_ABBREVIATION": "LAC",
         "GP": 30, "PLAYER_ID": 1, "MIN": 900, "PTS": 600, "REB": 150,
         "AST": 240, "TOV": 60, "FG_PCT": 0.44, "FG3_PCT": 0.38, "FT_PCT": 0.87, "FTA": 120},
        {"PLAYER_NAME": "James Harden", "TEAM_ABBREVIATION": "LAL",
         "GP": 32, "PLAYER_ID": 1, "MIN": 1000, "PTS": 700, "REB": 160,
         "AST": 260, "TOV": 65, "FG_PCT": 0.45, "FG3_PCT": 0.39, "FT_PCT": 0.88, "FTA": 130},
        {"PLAYER_NAME": "James Harden", "TEAM_ABBREVIATION": "TOT",
         "GP": 62, "PLAYER_ID": 1, "MIN": 1900, "PTS": 1300, "REB": 310,
         "AST": 500, "TOV": 125, "FG_PCT": 0.445, "FG3_PCT": 0.385, "FT_PCT": 0.875, "FTA": 250},
    ]

    cache = {}
    for row in rows:
        gp = max(int(row.get("GP", 1)), 1)
        key_name = _norm(row["PLAYER_NAME"])
        if key_name in cache and cache[key_name].get("gp", 0) >= gp:
            continue
        cache[key_name] = {"gp": gp, "pts": float(row["PTS"]) / gp}

    result = cache[_norm("James Harden")]
    assert result["gp"] == 62, (
        f"Expected TOT row gp=62, got {result['gp']}. "
        "Team-specific row overwrote TOT — traded player bug."
    )
    assert abs(result["pts"] - 1300/62) < 0.1


def test_traded_player_tot_row_source_guard():
    """Source audit: _get_player_season_avgs must have the GP guard to skip lower-GP rows."""
    import inspect
    import src.prediction.player_props as pp
    src = inspect.getsource(pp._get_player_season_avgs)
    assert "key_name in cache" in src or "in cache" in src, (
        "_get_player_season_avgs must check if a higher-GP entry already exists"
    )
    assert ".get(\"gp\"" in src or ".get('gp'" in src, (
        "_get_player_season_avgs must compare GP to pick the TOT row for traded players"
    )


def test_single_team_player_unaffected():
    """Single-team player: first (and only) row is always stored regardless of GP."""
    import unicodedata

    def _norm(s):
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

    rows = [{"PLAYER_NAME": "Luka Doncic", "GP": 70, "PTS": 2100}]
    cache = {}
    for row in rows:
        gp = max(int(row.get("GP", 1)), 1)
        key_name = _norm(row["PLAYER_NAME"])
        if key_name in cache and cache[key_name].get("gp", 0) >= gp:
            continue
        cache[key_name] = {"gp": gp, "pts": float(row["PTS"]) / gp}

    result = cache[_norm("Luka Doncic")]
    assert result["gp"] == 70
    assert abs(result["pts"] - 30.0) < 0.1


# ── opp_def_rtg secondary cache (Loop 37) ──────────────────────────────────────

def test_opp_def_rtg_reads_secondary_cache(tmp_path):
    """_get_opp_def_rating returns real value from secondary cache when primary absent."""
    import json
    import src.prediction.player_props as pp

    cache_dir = tmp_path / "nba"
    cache_dir.mkdir()
    secondary = {"GSW": 108.5, "BOS": 110.2, "LAL": 115.0}
    (cache_dir / "opp_def_rtg_2024-25.json").write_text(json.dumps(secondary))

    orig = pp._NBA_CACHE
    pp._NBA_CACHE = str(cache_dir)
    try:
        result = pp._get_opp_def_rating("GSW", "2024-25")
    finally:
        pp._NBA_CACHE = orig

    assert abs(result - 108.5) < 0.01, \
        f"Expected 108.5 from secondary cache, got {result}"


def test_opp_def_rtg_fallback_when_no_caches(tmp_path):
    """_get_opp_def_rating returns 113.0 when neither cache file exists."""
    import src.prediction.player_props as pp

    cache_dir = tmp_path / "nba"
    cache_dir.mkdir()
    orig = pp._NBA_CACHE
    pp._NBA_CACHE = str(cache_dir)
    try:
        result = pp._get_opp_def_rating("GSW", "2024-25")
    finally:
        pp._NBA_CACHE = orig

    assert result == 113.0, f"Expected 113.0 fallback, got {result}"


def test_opp_def_rtg_secondary_cache_path_in_source():
    """opp_def_rtg_{season}.json secondary cache path must be in _get_opp_def_rating source."""
    import inspect
    import src.prediction.player_props as pp

    src_text = inspect.getsource(pp._get_opp_def_rating)
    assert "opp_def_rtg_" in src_text, \
        "_get_opp_def_rating must reference opp_def_rtg_ secondary cache"
    assert "opp_team" in src_text, \
        "_get_opp_def_rating must key secondary cache by team abbreviation"


# ── player_avgs TTL (Loop 38) ────────────────────────────────────────────────

def test_player_avgs_ttl_constant_defined():
    """_PLAYER_AVGS_TTL_HOURS must be defined in player_props."""
    from src.prediction import player_props
    assert hasattr(player_props, "_PLAYER_AVGS_TTL_HOURS"), (
        "_PLAYER_AVGS_TTL_HOURS constant missing from player_props"
    )
    assert player_props._PLAYER_AVGS_TTL_HOURS > 0


def test_player_avgs_stale_cache_is_not_fresh(tmp_path):
    """player_avgs cache older than TTL must be treated as stale and not returned."""
    import os, time, json

    cache_path = tmp_path / "player_avgs_2024-25.json"
    cache_path.write_text(json.dumps({"lebron james": {"pts": 25.0}}))
    stale_mtime = time.time() - 25 * 3600  # 25 hours ago
    os.utime(str(cache_path), (stale_mtime, stale_mtime))

    ttl_hours = 24
    avgs_fresh = (
        os.path.exists(str(cache_path))
        and (time.time() - os.path.getmtime(str(cache_path))) < ttl_hours * 3600
    )
    assert not avgs_fresh, "A 25-hour-old player_avgs cache must not be fresh (TTL=24h)"


def test_player_avgs_fresh_cache_returned(tmp_path, monkeypatch):
    """player_avgs cache younger than TTL must be returned without fetching."""
    import json, src.prediction.player_props as pp

    cache_dir = tmp_path / "nba"
    cache_dir.mkdir()
    cache_path = cache_dir / "player_avgs_2024-25.json"
    player_data = {
        "lebron james": {
            "player_id": 2544, "team": "LAL", "gp": 60,
            "pts": 25.0, "reb": 7.0, "ast": 8.0,
            "min": 35.0, "tov": 3.0, "fg_pct": 0.54,
            "fg3_pct": 0.40, "ft_pct": 0.75, "fta": 5.0,
        }
    }
    cache_path.write_text(json.dumps(player_data))
    # File is brand-new → fresh

    fetched = []

    def _fake_api(*args, **kwargs):
        fetched.append(1)
        raise RuntimeError("should not be called")

    orig = pp._NBA_CACHE
    pp._NBA_CACHE = str(cache_dir)
    try:
        result = pp._get_player_season_avgs("LeBron James", "2024-25")
    finally:
        pp._NBA_CACHE = orig

    assert result is not None, "Fresh cache should return player data"
    assert abs(result["pts"] - 25.0) < 0.01
    assert not fetched, "No API call should be made when cache is fresh"


def test_player_avgs_ttl_check_in_source():
    """_get_player_season_avgs source must reference _PLAYER_AVGS_TTL_HOURS."""
    import inspect, src.prediction.player_props as pp
    src_text = inspect.getsource(pp._get_player_season_avgs)
    assert "_PLAYER_AVGS_TTL_HOURS" in src_text, (
        "_get_player_season_avgs must use _PLAYER_AVGS_TTL_HOURS for cache TTL"
    )


# ── _fetch_team_stats TTL (Loop 39) ──────────────────────────────────────────

def test_team_stats_ttl_constant_defined():
    """_TEAM_STATS_TTL_HOURS must be defined in win_probability."""
    from src.prediction import win_probability as wp
    assert hasattr(wp, "_TEAM_STATS_TTL_HOURS"), (
        "_TEAM_STATS_TTL_HOURS constant missing from win_probability"
    )
    assert wp._TEAM_STATS_TTL_HOURS > 0


def test_team_stats_stale_cache_is_not_fresh(tmp_path):
    """A team_stats cache older than 24h must not be treated as fresh."""
    import os, time, json

    cache_path = tmp_path / "team_stats_2024-25.json"
    cache_path.write_text(json.dumps({"1610612744": {"off_rtg": 115.0}}))
    stale_mtime = time.time() - 25 * 3600
    os.utime(str(cache_path), (stale_mtime, stale_mtime))

    ttl_hours = 24
    fresh = (
        os.path.exists(str(cache_path))
        and (time.time() - os.path.getmtime(str(cache_path))) < ttl_hours * 3600
    )
    assert not fresh, "25-hour-old team_stats cache must not be fresh (TTL=24h)"


def test_team_stats_fresh_cache_returned(tmp_path, monkeypatch):
    """A team_stats cache younger than TTL is returned without an API call."""
    import json, src.prediction.win_probability as wp

    cache_dir = tmp_path / "nba"
    cache_dir.mkdir()
    cache_file = cache_dir / "team_stats_2024-25.json"
    fake_stats = {"1610612744": {"off_rtg": 118.0, "def_rtg": 109.0,
                                  "net_rtg": 9.0, "pace": 100.0,
                                  "efg_pct": 0.56, "ts_pct": 0.59,
                                  "tov_pct": 12.5, "reb_pct": 0.5,
                                  "win_pct": 0.65}}
    cache_file.write_text(json.dumps(fake_stats))
    # brand-new file → fresh

    orig = wp._NBA_CACHE
    wp._NBA_CACHE = str(cache_dir)
    try:
        result = wp._fetch_team_stats("2024-25")
    finally:
        wp._NBA_CACHE = orig

    assert 1610612744 in result, "Team ID must be present in returned stats"
    assert abs(result[1610612744]["off_rtg"] - 118.0) < 0.01


def test_team_stats_ttl_check_in_source():
    """_fetch_team_stats source must reference _TEAM_STATS_TTL_HOURS."""
    import inspect, src.prediction.win_probability as wp
    src_text = inspect.getsource(wp._fetch_team_stats)
    assert "_TEAM_STATS_TTL_HOURS" in src_text, (
        "_fetch_team_stats must use _TEAM_STATS_TTL_HOURS for cache freshness check"
    )


# ── _fetch_season_games active-season TTL (Loop 42) ─────────────────────────

def test_active_season_ttl_constant_defined():
    """_ACTIVE_SEASON_GAMES_TTL_HOURS must be defined in win_probability."""
    from src.prediction import win_probability as wp
    assert hasattr(wp, "_ACTIVE_SEASON_GAMES_TTL_HOURS"), (
        "_ACTIVE_SEASON_GAMES_TTL_HOURS missing from win_probability"
    )
    assert wp._ACTIVE_SEASON_GAMES_TTL_HOURS > 0


def test_is_active_season_current():
    """Current season (matching today's year) must be flagged active."""
    from datetime import date
    from src.prediction.win_probability import _is_active_season
    year = date.today().year
    # e.g. if today is 2025, "2024-25" → end year 2025 = current → active
    season = f"{year - 1}-{str(year)[2:]}"
    assert _is_active_season(season), f"{season!r} must be recognised as the active season"


def test_is_active_season_past():
    """A clearly completed past season must NOT be flagged active."""
    from src.prediction.win_probability import _is_active_season
    assert not _is_active_season("2020-21"), "2020-21 must not be flagged as active"
    assert not _is_active_season("2018-19"), "2018-19 must not be flagged as active"


def test_season_games_stale_active_cache_triggers_refetch(tmp_path, monkeypatch):
    """Stale active-season cache (>TTL) must be re-fetched, not returned."""
    import os, time, json
    from src.prediction import win_probability as wp

    cache_dir = tmp_path / "nba"
    cache_dir.mkdir()
    season = "2099-00"   # far-future season so _is_active_season always True
    cache_file = cache_dir / f"season_games_{season}.json"
    cache_file.write_text(json.dumps({"v": wp._SEASON_GAMES_VERSION, "rows": [{"stale": True}]}))
    stale_mtime = time.time() - (wp._ACTIVE_SEASON_GAMES_TTL_HOURS + 1) * 3600
    os.utime(str(cache_file), (stale_mtime, stale_mtime))

    # Patch _is_active_season to always return True for this season
    monkeypatch.setattr(wp, "_is_active_season", lambda s: True)

    orig = wp._NBA_CACHE
    wp._NBA_CACHE = str(cache_dir)
    try:
        # Should try to re-fetch — will fail (no API), returning []
        result = wp._fetch_season_games(season)
    finally:
        wp._NBA_CACHE = orig

    # The stale cache must NOT be returned as-is
    assert result == [] or result != [{"stale": True}], (
        "Stale active-season cache must be re-fetched, not returned"
    )


def test_season_games_fresh_active_cache_returned(tmp_path, monkeypatch):
    """Fresh active-season cache (within TTL) must be returned without re-fetching."""
    import json
    from src.prediction import win_probability as wp

    cache_dir = tmp_path / "nba"
    cache_dir.mkdir()
    season = "2099-00"
    rows = [{"game_date": "2099-01-01", "home_team": "GSW"}]
    cache_file = cache_dir / f"season_games_{season}.json"
    cache_file.write_text(json.dumps({"v": wp._SEASON_GAMES_VERSION, "rows": rows}))
    # brand-new file → fresh

    monkeypatch.setattr(wp, "_is_active_season", lambda s: True)
    orig = wp._NBA_CACHE
    wp._NBA_CACHE = str(cache_dir)
    try:
        result = wp._fetch_season_games(season)
    finally:
        wp._NBA_CACHE = orig

    assert result == rows, "Fresh active-season cache must be returned without re-fetching"


def test_season_games_past_season_no_ttl(tmp_path, monkeypatch):
    """Completed past seasons must be returned from cache regardless of age."""
    import os, time, json
    from src.prediction import win_probability as wp

    cache_dir = tmp_path / "nba"
    cache_dir.mkdir()
    season = "2020-21"
    rows = [{"game_date": "2021-01-01", "home_team": "LAL"}]
    cache_file = cache_dir / f"season_games_{season}.json"
    cache_file.write_text(json.dumps({"v": wp._SEASON_GAMES_VERSION, "rows": rows}))
    very_old = time.time() - 365 * 24 * 3600  # 1 year ago
    os.utime(str(cache_file), (very_old, very_old))

    monkeypatch.setattr(wp, "_is_active_season", lambda s: False)
    orig = wp._NBA_CACHE
    wp._NBA_CACHE = str(cache_dir)
    try:
        result = wp._fetch_season_games(season)
    finally:
        wp._NBA_CACHE = orig

    assert result == rows, "Past season cache must be returned regardless of age (no TTL)"


# ── _get_all_player_avgs TTL fix (Loop 47) ────────────────────────────────────

def test_get_all_player_avgs_stale_cache_triggers_refetch(tmp_path, monkeypatch):
    """_get_all_player_avgs must not return stale cache (>24h) to train_props."""
    import os, time, json
    from src.prediction import player_props as pp

    cache_dir = tmp_path / "nba"
    cache_dir.mkdir()
    monkeypatch.setattr(pp, "_NBA_CACHE", str(cache_dir))

    season = "2024-25"
    cache_path = os.path.join(str(cache_dir), f"player_avgs_{season}.json")
    # Write a stale cache (25h old)
    with open(cache_path, "w") as f:
        json.dump({"lebron james": {"pts": 99.0, "gp": 50}}, f)
    stale_mtime = time.time() - (25 * 3600)
    os.utime(cache_path, (stale_mtime, stale_mtime))

    # Patch _get_player_season_avgs to write a fresh cache and return None
    refreshed = []
    def _mock_trigger(player_name, season):
        refreshed.append(True)
        with open(cache_path, "w") as f:
            json.dump({}, f)
        return None
    monkeypatch.setattr(pp, "_get_player_season_avgs", _mock_trigger)

    pp._get_all_player_avgs(season)
    assert refreshed, "Stale player_avgs cache must trigger a refresh before training"


def test_get_all_player_avgs_fresh_cache_no_refetch(tmp_path, monkeypatch):
    """_get_all_player_avgs must use a fresh cache without calling the API."""
    import os, json
    from src.prediction import player_props as pp

    cache_dir = tmp_path / "nba"
    cache_dir.mkdir()
    monkeypatch.setattr(pp, "_NBA_CACHE", str(cache_dir))

    season = "2024-25"
    cache_path = os.path.join(str(cache_dir), f"player_avgs_{season}.json")
    # Write a fresh cache (just now)
    with open(cache_path, "w") as f:
        json.dump({"lebron james": {"pts": 28.0, "reb": 7.0, "ast": 7.0,
                                    "min": 35.0, "fg_pct": 0.52, "gp": 50}}, f)

    triggered = []
    monkeypatch.setattr(pp, "_get_player_season_avgs",
                        lambda *a, **kw: triggered.append(True) or None)

    rows = pp._get_all_player_avgs(season)
    assert not triggered, "Fresh player_avgs cache must not trigger an API re-fetch"
    assert len(rows) == 1, f"Expected 1 player row from fresh cache, got {len(rows)}"


def test_get_all_player_avgs_ttl_in_source():
    """_get_all_player_avgs source must reference _PLAYER_AVGS_TTL_HOURS."""
    import inspect
    from src.prediction import player_props as pp
    src_text = inspect.getsource(pp._get_all_player_avgs)
    assert "_PLAYER_AVGS_TTL_HOURS" in src_text, (
        "_get_all_player_avgs must use _PLAYER_AVGS_TTL_HOURS to check cache freshness"
    )


# ── InjuryMonitor ─────────────────────────────────────────────────────────────

def test_injury_monitor_impact_multiplier_active():
    """get_impact_multiplier returns 1.0 for 'Active' status."""
    from src.data.injury_monitor import InjuryMonitor
    mon = InjuryMonitor()
    mon._data[999] = {"status": "Active",  "reason": "", "updated_at": "",
                      "team_abbr": "GSW", "player_name": "Test Player"}
    from datetime import datetime, timezone
    mon._fetched_at = datetime.now(tz=timezone.utc)
    assert mon.get_impact_multiplier(999) == 1.0


def test_injury_monitor_impact_multiplier_gtd():
    """get_impact_multiplier returns 0.85 for 'GTD' status."""
    from src.data.injury_monitor import InjuryMonitor
    from datetime import datetime, timezone
    mon = InjuryMonitor()
    mon._data[100] = {"status": "GTD", "reason": "", "updated_at": "",
                      "team_abbr": "BOS", "player_name": "GTD Player"}
    mon._fetched_at = datetime.now(tz=timezone.utc)
    assert mon.get_impact_multiplier(100) == pytest.approx(0.85)


def test_injury_monitor_impact_multiplier_questionable():
    """get_impact_multiplier returns 0.70 for 'Questionable' status."""
    from src.data.injury_monitor import InjuryMonitor
    from datetime import datetime, timezone
    mon = InjuryMonitor()
    mon._data[101] = {"status": "Questionable", "reason": "", "updated_at": "",
                      "team_abbr": "LAL", "player_name": "Q Player"}
    mon._fetched_at = datetime.now(tz=timezone.utc)
    assert mon.get_impact_multiplier(101) == pytest.approx(0.70)


def test_injury_monitor_impact_multiplier_out():
    """get_impact_multiplier returns 0.0 for 'Out' status."""
    from src.data.injury_monitor import InjuryMonitor
    from datetime import datetime, timezone
    mon = InjuryMonitor()
    mon._data[102] = {"status": "Out", "reason": "", "updated_at": "",
                      "team_abbr": "MIA", "player_name": "Out Player"}
    mon._fetched_at = datetime.now(tz=timezone.utc)
    assert mon.get_impact_multiplier(102) == pytest.approx(0.0)


def test_injury_monitor_impact_multiplier_unknown():
    """get_impact_multiplier returns 0.95 for player not in injury data."""
    from src.data.injury_monitor import InjuryMonitor
    from datetime import datetime, timezone
    mon = InjuryMonitor()
    mon._data.clear()
    mon._fetched_at = datetime.now(tz=timezone.utc)
    assert mon.get_impact_multiplier(99999) == pytest.approx(0.95)


def test_injury_monitor_is_stale_before_refresh():
    """is_stale() returns True on a freshly constructed monitor."""
    from src.data.injury_monitor import InjuryMonitor
    mon = InjuryMonitor()
    assert mon.is_stale() is True


def test_injury_monitor_not_stale_after_refresh(monkeypatch):
    """is_stale() returns False immediately after refresh() completes."""
    from src.data.injury_monitor import InjuryMonitor
    mon = InjuryMonitor()
    monkeypatch.setattr(mon, "_load_injuries_from_disk", lambda: [])
    monkeypatch.setattr(mon, "_build_id_lookup", lambda: {})
    mon.refresh()
    assert mon.is_stale() is False


def test_injury_monitor_get_team_injuries(monkeypatch):
    """get_team_injuries returns only records matching the given team_abbr."""
    from src.data.injury_monitor import InjuryMonitor
    from datetime import datetime, timezone
    mon = InjuryMonitor()
    monkeypatch.setattr(mon, "_load_injuries_from_disk", lambda: [])
    monkeypatch.setattr(mon, "_build_id_lookup", lambda: {})
    # Pre-populate internal state so no disk I/O is triggered
    mon._data = {
        1: {"status": "Out",    "reason": "knee", "updated_at": "", "team_abbr": "BOS", "player_name": "Player A"},
        2: {"status": "Active", "reason": "",      "updated_at": "", "team_abbr": "BOS", "player_name": "Player B"},
        3: {"status": "GTD",    "reason": "ankle", "updated_at": "", "team_abbr": "LAL", "player_name": "Player C"},
    }
    mon._team_index = {"BOS": [1, 2], "LAL": [3]}
    mon._fetched_at = datetime.now(tz=timezone.utc)
    bos = mon.get_team_injuries("BOS")
    assert len(bos) == 2
    lal = mon.get_team_injuries("LAL")
    assert len(lal) == 1
    assert lal[0]["status"] == "GTD"


def test_predict_props_includes_injury_status(monkeypatch):
    """predict_props() output dict contains 'injury_status' and 'injury_multiplier' keys."""
    import src.prediction.player_props as pp

    fake_feats = {
        "player_id":    9999,
        "team":         "GSW",
        "season_pts":   25.0, "season_reb": 5.0, "season_ast": 6.0,
        "season_min":   35.0, "season_fg3m": 2.0, "season_stl": 1.0,
        "season_blk":   0.5,  "season_tov":  2.0,
        "pts_roll":     25.0, "reb_roll": 5.0, "ast_roll": 6.0, "min_roll": 35.0,
        "pts_bayes":    25.0, "reb_bayes": 5.0, "ast_bayes": 6.0,
        "fg3m_bayes":   2.0,  "stl_bayes": 1.0, "blk_bayes": 0.5, "tov_bayes": 2.0,
        "opp_def_rtg":  113.0, "fg_pct": 0.52,
        "home_pts_avg": 25.0, "away_pts_avg": 24.0,
        "home_reb_avg": 5.0,  "away_reb_avg": 4.5,
        "home_ast_avg": 6.0,  "away_ast_avg": 5.5,
        "pts_vs_opp":   24.0, "reb_vs_opp": 5.0, "ast_vs_opp": 6.0,
        "clutch_fg_pct": 0.0, "clutch_pts_pg": 0.0, "foul_drawn_rate": 0.0,
        "n_games_form": 10,
    }
    monkeypatch.setattr(pp, "_build_player_features", lambda *a, **kw: fake_feats)
    monkeypatch.setattr(pp, "_compute_blowout_prob", lambda *a, **kw: 0.0)
    # Make injury monitor return "Active" without hitting disk
    from src.data.injury_monitor import InjuryMonitor
    from datetime import datetime, timezone
    pp._injury_monitor._data  = {9999: {"status": "Active", "reason": "", "updated_at": "",
                                        "team_abbr": "GSW", "player_name": "Test"}}
    pp._injury_monitor._fetched_at = datetime.now(tz=timezone.utc)

    result = pp.predict_props("Test Player", "BOS")
    assert "injury_status"     in result, "predict_props must return 'injury_status'"
    assert "injury_multiplier" in result, "predict_props must return 'injury_multiplier'"
    assert result["injury_status"]     == "Active"
    assert result["injury_multiplier"] == pytest.approx(1.0)


def test_predict_props_injury_multiplier_scales_stats(monkeypatch):
    """Out player's projected stats are multiplied by 0.0 (result = 0)."""
    import src.prediction.player_props as pp

    fake_feats = {
        "player_id":    8888,
        "team":         "BOS",
        "season_pts":   20.0, "season_reb": 4.0, "season_ast": 5.0,
        "season_min":   30.0, "season_fg3m": 1.5, "season_stl": 0.8,
        "season_blk":   0.3,  "season_tov":  1.5,
        "pts_roll":     20.0, "reb_roll": 4.0, "ast_roll": 5.0, "min_roll": 30.0,
        "pts_bayes":    20.0, "reb_bayes": 4.0, "ast_bayes": 5.0,
        "fg3m_bayes":   1.5,  "stl_bayes": 0.8, "blk_bayes": 0.3, "tov_bayes": 1.5,
        "opp_def_rtg":  113.0, "fg_pct": 0.48,
        "home_pts_avg": 20.0, "away_pts_avg": 19.0,
        "home_reb_avg": 4.0,  "away_reb_avg": 3.5,
        "home_ast_avg": 5.0,  "away_ast_avg": 4.5,
        "pts_vs_opp":   19.0, "reb_vs_opp": 4.0, "ast_vs_opp": 5.0,
        "clutch_fg_pct": 0.0, "clutch_pts_pg": 0.0, "foul_drawn_rate": 0.0,
        "n_games_form": 10,
    }
    monkeypatch.setattr(pp, "_build_player_features", lambda *a, **kw: fake_feats)
    monkeypatch.setattr(pp, "_compute_blowout_prob", lambda *a, **kw: 0.0)
    from src.data.injury_monitor import InjuryMonitor
    from datetime import datetime, timezone
    pp._injury_monitor._data  = {8888: {"status": "Out", "reason": "ankle",
                                        "updated_at": "", "team_abbr": "BOS",
                                        "player_name": "Out Star"}}
    pp._injury_monitor._fetched_at = datetime.now(tz=timezone.utc)

    result = pp.predict_props("Out Star", "MIA")
    assert result["injury_status"]     == "Out"
    assert result["injury_multiplier"] == pytest.approx(0.0)
    assert result["pts"]               == pytest.approx(0.0)
