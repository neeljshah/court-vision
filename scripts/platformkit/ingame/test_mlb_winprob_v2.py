"""Per-file tests for mlb_winprob_v2.py + mlb_winprob_v2_features.py -- state-conditioned
MLB win-prob model vs pooled-model baseline vs market.

OFFLINE + deterministic: synthetic pitch-state parquets + grade files under tmp_path,
outcome resolver injected via MlbOutcomeResolver(box_df=...) (no parquet, no network).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_mlb_winprob_v2.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.platformkit.ingame.mlb_winprob_v2 as wp
import scripts.platformkit.ingame.mlb_winprob_v2_features as feat
from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver


def _synthetic_pitch_states(season: int, n_games: int = 40, seed: int = 0) -> pd.DataFrame:
    """A tiny, self-consistent pitch_states frame: home_win is a step function of the
    final score_margin sign, so a model that reads margin should separate cleanly."""
    rng = np.random.RandomState(seed)
    rows = []
    for g in range(n_games):
        gid = "%d-01-%02d-AAA-BBB-1" % (season, 1 + (g % 28))
        margin = rng.choice([-3.0, -1.0, 0.0, 1.0, 3.0])
        home_win = 1 if margin > 0 else 0
        for i in range(6):
            inning = 1 + i
            half = "top" if i % 2 == 0 else "bottom"
            rows.append({
                "game_id": gid, "half_inning_label": "%s%d" % (half, inning),
                "outs": i % 3, "runners": i % 8, "count_balls": i % 4, "count_strikes": i % 3,
                "state_diff": margin, "frac_elapsed": (i + 1) / 6.0,
                "outcome": home_win, "season": season,
            })
    return pd.DataFrame(rows)


def _write_train_parquets(tmp_path: Path, seasons, n_games: int = 40) -> Path:
    d = tmp_path / "pitch_states"
    d.mkdir(parents=True, exist_ok=True)
    for yr in seasons:
        _synthetic_pitch_states(yr, n_games=n_games).to_parquet(
            d / ("mlb_pitch_states__%d.parquet" % yr))
    return d


def _ts(i: int) -> str:
    return (datetime(2026, 6, 1, tzinfo=timezone.utc)
           + timedelta(seconds=30 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_grade_game(grade_dir: Path, gid: str, rows: list) -> None:
    p = grade_dir / "mlb" / ("%s.jsonl" % gid)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for i, (model_p, market_p, hs, aws, inning, half, outs, base, count) in enumerate(rows):
            summary = ("home_score=%s away_score=%s inning=%s half=%s outs=%s base=%s "
                      "count=%s" % (hs, aws, inning, half, outs, base, count))
            fh.write(json.dumps({
                "sport": "mlb", "game_id": gid, "ts": _ts(i), "side": "home",
                "model_prob": model_p, "market_prob": market_p, "state_summary": summary,
            }) + "\n")


def _box_df(n_games: int, home_win: bool = True) -> pd.DataFrame:
    rows = []
    for n in range(n_games):
        rows.append({
            "event_id": str(1000 + n), "home_abbr": "BOS", "away_abbr": "NYY",
            "home_score": 5 if home_win else 2, "away_score": 2 if home_win else 5,
            "status": "STATUS_FINAL", "date": "2026-06-%02d" % (1 + (n % 28)), "start_time": "",
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------- #
def test_no_2026_in_train_guard(tmp_path: Path) -> None:
    d = _write_train_parquets(tmp_path, [2024])
    with pytest.raises(ValueError):
        feat.load_training_seasons([2026], data_dir=d)
    with pytest.raises(ValueError):
        feat.load_training_seasons([2024, 2026], data_dir=d)


def test_load_training_seasons_skips_missing(tmp_path: Path) -> None:
    d = _write_train_parquets(tmp_path, [2024])
    df, missing = feat.load_training_seasons([2022, 2024], data_dir=d)
    assert missing == [2022]
    assert not df.empty
    assert set(df["season"]) == {2024}


def test_train_xy_encodes_half_and_base_state(tmp_path: Path) -> None:
    d = _write_train_parquets(tmp_path, [2024], n_games=5)
    df, _ = feat.load_training_seasons([2024], data_dir=d)
    X, y, n_dropped = feat.train_xy(df)
    assert n_dropped == 0
    assert X.shape[1] == len(feat.FEATURE_NAMES)
    # half_bottom column (index 1) is 0/1 only
    assert set(np.unique(X[:, 1])) <= {0.0, 1.0}
    # base_state column (index 3) matches the `runners` % 8 encoding used in the fixture
    assert set(np.unique(X[:, 3])) <= set(range(8))
    assert set(np.unique(y)) <= {0.0, 1.0}


def test_parse_tick_state_requires_deep_fields() -> None:
    deep = ("home_score=3.0 away_score=1.0 inning=5 half=bottom outs=1 base=3 count=2-1")
    st = feat.parse_tick_state(deep)
    assert st is not None
    assert st["score_margin"] == pytest.approx(2.0)
    assert st["base_state"] == 3.0
    assert 0.0 <= st["frac_elapsed"] <= 1.0
    # shallow (pre-deep-state) capture: no outs/base/count -> dropped, never guessed
    shallow = "home_score=3.0 away_score=1.0 inning=5 half=bottom"
    assert feat.parse_tick_state(shallow) is None
    assert feat.parse_tick_state("") is None
    assert feat.parse_tick_state(None) is None


def test_calibration_bounds_after_isotonic(tmp_path: Path) -> None:
    d = _write_train_parquets(tmp_path, [2022, 2023, 2024], n_games=60)
    clf, iso, meta = wp.train_model(train_seasons=[2022, 2023, 2024], val_season=2023,
                                    data_dir=d)
    X, y, _ = feat.train_xy(_synthetic_pitch_states(2024, n_games=20))
    probs = wp.predict_proba(clf, iso, X)
    assert probs.shape[0] == X.shape[0]
    assert np.all(probs >= 0.0) and np.all(probs <= 1.0)
    assert meta["n_features"] == len(feat.FEATURE_NAMES)


def test_build_eval_ticks_and_benchmark_end_to_end(tmp_path: Path) -> None:
    train_dir = _write_train_parquets(tmp_path, [2022, 2023, 2024], n_games=60)
    clf, iso, meta = wp.train_model(train_seasons=[2022, 2023, 2024], val_season=2023,
                                    data_dir=train_dir)
    grade_dir = tmp_path / "ingame_grade"
    n_games = wp.sb.MIN_GAMES + 4
    for n in range(n_games):
        gid = "KXMLBGAME-26JUN%02d1200NYYBOS" % (1 + (n % 28))
        rows = [(0.5, 0.5, 3.0, 1.0, 5, "bottom", 1, 3, "2-1")] * 10
        _write_grade_game(grade_dir, gid, rows)
    resolver = MlbOutcomeResolver(box_df=_box_df(n_games, home_win=True))
    ticks, counts = wp.build_eval_ticks(grade_dir, resolver)
    assert counts["n_games_resolved"] == n_games
    assert counts["n_ticks_missing_state"] == 0
    assert len(ticks) == n_games * 10
    doc = wp.build_benchmark(clf, iso, grade_dir, resolver)
    assert doc["edge_claimed"] is False
    assert doc["pooled"]["n_ticks"] == n_games * 10
    assert "new_model" in doc["pooled"] and "old_model" in doc["pooled"] and "market" in doc["pooled"]


def test_save_model_meta_feature_count_matches_pkl(tmp_path: Path) -> None:
    d = _write_train_parquets(tmp_path, [2022, 2023, 2024], n_games=30)
    clf, iso, meta = wp.train_model(train_seasons=[2022, 2023, 2024], val_season=2023,
                                    data_dir=d)
    pkl_path = tmp_path / "model.pkl"
    meta_path = tmp_path / "meta.json"
    wp.save_model(clf, iso, meta, model_path=pkl_path, meta_path=meta_path)
    assert pkl_path.is_file() and meta_path.is_file()
    reloaded_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert reloaded_meta["n_features"] == clf.n_features_in_
