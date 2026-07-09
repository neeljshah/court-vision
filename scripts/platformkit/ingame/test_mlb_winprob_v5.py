"""Per-file tests for mlb_winprob_v5.py + mlb_winprob_v5_composite.py -- rung 5 of the
MLB in-game win-prob ladder (matched-OOS protocol + team-level PA-composition).

OFFLINE + deterministic: synthetic pitch-state parquets + grade files under tmp_path,
outcome resolver injected via MlbOutcomeResolver(box_df=...) (no parquet, no network).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_mlb_winprob_v5.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.platformkit.ingame.mlb_winprob_v2_features as feat
import scripts.platformkit.ingame.mlb_winprob_v5 as v5
import scripts.platformkit.ingame.mlb_winprob_v5_composite as comp
from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver


def _synthetic_pitch_states(season: int, n_games: int = 40, home: str = "BOS",
                            away: str = "NYY", seed: int = 0) -> pd.DataFrame:
    """Self-consistent pitch_states frame WITH team/date/pitch_type (needed by both
    the state model and the composite builder), home_win a step function of margin."""
    rng = np.random.RandomState(seed)
    rows = []
    for g in range(n_games):
        day = 1 + (g % 27)
        gid = "%d-06-%02d-%s-%s-1" % (season, day, home, away)
        date = "%d-06-%02d" % (season, day)
        margin = rng.choice([-3.0, -1.0, 0.0, 1.0, 3.0])
        home_win = 1 if margin > 0 else 0
        for i in range(6):
            inning = 1 + i
            half = "top" if i % 2 == 0 else "bottom"
            rows.append({
                "game_id": gid, "half_inning_label": "%s%d" % (half, inning),
                "outs": i % 3, "runners": i % 8, "count_balls": i % 4, "count_strikes": i % 3,
                "state_diff": margin, "frac_elapsed": (i + 1) / 6.0, "outcome": home_win,
                "season": season, "home_team": home, "away_team": away, "date": date,
                "pitch_type": "SL" if i % 2 == 0 else "FF",
            })
    return pd.DataFrame(rows)


def _write_train_parquets(tmp_path: Path, seasons, n_games: int = 40) -> Path:
    d = tmp_path / "pitch_states"
    d.mkdir(parents=True, exist_ok=True)
    for yr in seasons:
        _synthetic_pitch_states(yr, n_games=n_games, seed=yr).to_parquet(
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
def test_train_seasons_constant_never_includes_2025_or_2026() -> None:
    """Matched-OOS guard: the fixed constant a classifier's own .fit() may use."""
    assert set(v5.TRAIN_SEASONS) == {2022, 2023, 2024}
    assert v5.VAL_SEASON == 2025
    with pytest.raises(ValueError):
        feat.load_training_seasons(list(v5.TRAIN_SEASONS) + [2026])


def test_build_team_daily_asof_is_strictly_prior(tmp_path: Path) -> None:
    """Leak guard for the composite: a date's share reflects ONLY earlier dates, and a
    team's first date on file has no prior data (NaN, never a guess)."""
    d = tmp_path / "pitch_states"
    d.mkdir()
    df = pd.DataFrame([
        # day1: BOS pitches (top half) all-breaking-ahead; day2: BOS pitches all-fastball-ahead
        {"home_team": "BOS", "away_team": "NYY", "date": "2024-06-01", "half_inning_label": "top1",
         "count_balls": 0, "count_strikes": 2, "pitch_type": "SL"},
        {"home_team": "BOS", "away_team": "NYY", "date": "2024-06-02", "half_inning_label": "top1",
         "count_balls": 0, "count_strikes": 2, "pitch_type": "FF"},
    ])
    df.to_parquet(d / "mlb_pitch_states__2024.parquet")
    daily = comp.build_team_daily_asof((2024,), data_dir=d)
    row1 = daily[(daily["team"] == "BOS") & (daily["date"] == pd.Timestamp("2024-06-01"))].iloc[0]
    row2 = daily[(daily["team"] == "BOS") & (daily["date"] == pd.Timestamp("2024-06-02"))].iloc[0]
    assert pd.isna(row1["share_asof"])          # no prior date at all
    assert row2["share_asof"] == pytest.approx(1.0)  # day1 was 100% breaking-ahead, day2 excluded


def test_attach_composite_train_flags_missing_as_neutral(tmp_path: Path) -> None:
    d = _write_train_parquets(tmp_path, [2022, 2023, 2024], n_games=20)
    daily = comp.build_team_daily_asof((2022, 2023, 2024), data_dir=d)
    train_df, _ = feat.load_training_seasons([2024], data_dir=d)
    out = comp.attach_composite_train(train_df, daily)
    assert "pa_composite" in out.columns and "has_composite" in out.columns
    missing = out[~out["has_composite"]]
    assert (missing["pa_composite"] == 0.0).all()


def test_attach_composite_eval_parses_ticker_and_defaults_neutral() -> None:
    daily = pd.DataFrame({"team": ["BOS", "NYY"], "date": [pd.Timestamp("2026-06-01")] * 2,
                          "share_asof": [0.6, 0.4]})
    ticks = [{"game_id": "KXMLBGAME-26JUN011200NYYBOS"},   # away=NYY, home=BOS, matches daily's date
            {"game_id": "not-a-real-ticker"}]
    out = comp.attach_composite_eval(ticks, daily)
    assert out[0]["has_composite"] is True
    assert out[0]["pa_composite"] == pytest.approx(0.6 - 0.4)
    assert out[1]["has_composite"] is False and out[1]["pa_composite"] == 0.0


def test_train_specs_and_build_benchmark_end_to_end(tmp_path: Path) -> None:
    d = _write_train_parquets(tmp_path, [2022, 2023, 2024, 2025], n_games=60)
    bundle = v5.train_specs(data_dir=d)
    assert bundle["winner"] in ("a", "b")
    assert bundle["best_w"] in v5.W_GRID
    assert not np.isnan(bundle["val_game_brier_state_alone"])

    grade_dir = tmp_path / "ingame_grade"
    n_games = 12
    for n in range(n_games):
        gid = "KXMLBGAME-26JUN%02d1200NYYBOS" % (1 + (n % 27))
        rows = [(0.5, 0.5, 3.0, 1.0, 5, "bottom", 1, 3, "2-1")] * 10
        _write_grade_game(grade_dir, gid, rows)
    resolver = MlbOutcomeResolver(box_df=_box_df(n_games, home_win=True))
    doc = v5.build_benchmark(bundle, grade_dir, resolver)
    assert doc["edge_claimed"] is False
    assert "composition_beat_state_alone_on_val" in doc["spec_selection"]
    for key in ("new_model", "old_pooled_model", "v2_state_model", "market"):
        assert key in doc["pooled"]


def test_save_model_feature_count_matches_pkl_for_both_specs(tmp_path: Path) -> None:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.isotonic import IsotonicRegression

    X9 = np.random.RandomState(0).uniform(size=(20, len(v5.FEATURE_NAMES_V5)))
    y = (X9[:, 0] > 0.5).astype(int)
    clf_a = HistGradientBoostingClassifier(random_state=0)
    clf_a.fit(X9, y)
    iso_a = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso_a.fit(clf_a.predict_proba(X9)[:, 1], y)
    bundle_a = {"clf_a": clf_a, "iso_a": iso_a, "clf_state": None, "iso_state": None,
               "best_w": 0.0, "winner": "a", "meta": {}}
    pkl_a, meta_a = v5.save_model(bundle_a, model_path=tmp_path / "a.pkl", meta_path=tmp_path / "a.json")
    assert json.loads(meta_a.read_text(encoding="utf-8"))["n_features"] == len(v5.FEATURE_NAMES_V5)
    assert pkl_a.is_file()

    X8 = np.random.RandomState(0).uniform(size=(20, len(feat.FEATURE_NAMES)))
    clf_b = HistGradientBoostingClassifier(random_state=0)
    clf_b.fit(X8, y)
    iso_b = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso_b.fit(clf_b.predict_proba(X8)[:, 1], y)
    bundle_b = {"clf_a": None, "iso_a": None, "clf_state": clf_b, "iso_state": iso_b,
               "best_w": 0.15, "winner": "b", "meta": {}}
    pkl_b, meta_b = v5.save_model(bundle_b, model_path=tmp_path / "b.pkl", meta_path=tmp_path / "b.json")
    assert json.loads(meta_b.read_text(encoding="utf-8"))["n_features"] == len(feat.FEATURE_NAMES)
    assert pkl_b.is_file()
