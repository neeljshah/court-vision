"""Per-file test for tip_capture.ingame_features. Synthetic rows only -- no
real parquet load (load_top_usage_names is called with a monkeypatched
pd_reader everywhere the star list matters).

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/tip_capture/test_ingame_features.py -q
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.tip_capture import ingame_features as fx  # noqa: E402


def _isnan(v) -> bool:
    return isinstance(v, float) and math.isnan(v)


# --------------------------------------------------------------------------- #
# score_margin
# --------------------------------------------------------------------------- #

def test_score_margin_and_honest_nan():
    assert fx.score_margin({"score_home": 58, "score_away": 55}) == 3.0
    assert _isnan(fx.score_margin({"score_home": None, "score_away": 55}))
    assert _isnan(fx.score_margin({}))


# --------------------------------------------------------------------------- #
# market matching + devig + winprob_market_gap
# --------------------------------------------------------------------------- #

def _market_ok(events):
    return {"kalshi": {"status": "ok", "events": events}, "polymarket": {"status": "unavailable"}}


def test_devig_home_prob_two_way():
    ev = {"prices": {"kalshi": {"home": 1.5, "away": 3.0, "draw": None}}}
    p = fx._devig_home_prob(ev)
    # raw: 1/1.5=.667, 1/3=.333, total=1.0 -> already normalized here
    assert abs(p - (1 / 1.5) / (1 / 1.5 + 1 / 3.0)) < 1e-9


def test_match_market_event_handles_swapped_sides():
    events = [{"home": "Los Angeles Lakers", "away": "Boston Celtics",
              "prices": {"kalshi": {"home": 2.0, "away": 2.0}}}]
    # our feed says home=Celtics/away=Lakers -- swapped vs the event -- still matches
    ev = fx._match_market_event(events, "Boston Celtics", "Los Angeles Lakers")
    assert ev is not None


def test_market_home_prob_no_match_is_none():
    events = [{"home": "New York Knicks", "away": "Miami Heat", "prices": {}}]
    assert fx.market_home_prob(_market_ok(events), "Boston Celtics", "Los Angeles Lakers") is None
    assert fx.market_home_prob(None, "BOS", "LAL") is None


def test_winprob_market_gap_ok_and_honest_nan():
    events = [{"home": "Boston Celtics", "away": "Los Angeles Lakers",
              "prices": {"kalshi": {"home": 1.6667, "away": 2.5}}}]  # implies ~.6/.4 pre-devig
    row = {"home": "Boston Celtics", "away": "Los Angeles Lakers",
          "payload": {"winprob": {"status": "ok", "p_home_win": 0.65},
                      "market": _market_ok(events)}}
    gap = fx.winprob_market_gap(row)
    p_mkt = fx.market_home_prob(row["payload"]["market"], row["home"], row["away"])
    assert abs(gap - (0.65 - p_mkt)) < 1e-9

    # winprob not ok -> NaN
    row2 = {"home": "BOS", "away": "LAL", "payload": {"winprob": {"status": "error"}, "market": None}}
    assert _isnan(fx.winprob_market_gap(row2))

    # winprob ok but no matching market event -> NaN
    row3 = {"home": "BOS", "away": "LAL",
           "payload": {"winprob": {"status": "ok", "p_home_win": 0.5}, "market": None}}
    assert _isnan(fx.winprob_market_gap(row3))


# --------------------------------------------------------------------------- #
# pbp-tail features: recent_scoring_run / foul_count_tail / star_on_floor
# --------------------------------------------------------------------------- #

def _pbp(events, status="ok"):
    return {"pbp_tail": {"status": status, "events": events}}


def test_recent_scoring_run_net_swing_and_nan_cases():
    events = [{"home_score": 50, "away_score": 48}, {"home_score": 58, "away_score": 50}]
    row = {"payload": _pbp(events)}
    assert fx.recent_scoring_run(row) == 6.0  # home +8, away +2 -> net +6

    # unavailable tail -> NaN
    assert _isnan(fx.recent_scoring_run({"payload": _pbp([], status="unavailable")}))
    # ok status but empty tail -> NaN (no two endpoints)
    assert _isnan(fx.recent_scoring_run({"payload": _pbp([])}))


def test_foul_count_tail_counts_and_honest_nan_when_unavailable():
    events = [{"text": "Shooting foul on Player A"}, {"text": "Layup"}, {"text": "Personal foul"}]
    assert fx.foul_count_tail({"payload": _pbp(events)}) == 2.0
    assert fx.foul_count_tail({"payload": _pbp([])}) == 0.0  # tail ok, genuinely zero fouls
    assert _isnan(fx.foul_count_tail({"payload": _pbp([], status="unavailable")}))


def test_star_on_floor_true_false_and_honest_none():
    stars = {fx._norm_name("Jayson Tatum")}
    events = [{"on_floor": ["Jayson Tatum", "Jaylen Brown"]}]
    assert fx.star_on_floor({"payload": _pbp(events)}, stars) is True

    events_no_star = [{"on_floor": ["Some Bench Guy"]}]
    assert fx.star_on_floor({"payload": _pbp(events_no_star)}, stars) is False

    # feed omitted on_floor entirely -> honest None, not False
    events_no_participants = [{"text": "Layup"}]
    assert fx.star_on_floor({"payload": _pbp(events_no_participants)}, stars) is None

    # tail unavailable -> None
    assert fx.star_on_floor({"payload": _pbp([], status="unavailable")}, stars) is None

    # no star list for this sport -> None, even with on_floor present
    assert fx.star_on_floor({"payload": _pbp(events)}, set()) is None


# --------------------------------------------------------------------------- #
# load_day_rows: tolerant of a torn trailing line
# --------------------------------------------------------------------------- #

def test_load_day_rows_tolerates_torn_line(tmp_path):
    d = tmp_path / "nba"
    d.mkdir()
    p = d / "ingame_2026-07-18.jsonl"
    good = {"game_id": "1", "sport": "nba"}
    p.write_text(json.dumps(good) + "\n" + '{"broken":' + "\n", encoding="utf-8")
    rows = fx.load_day_rows("nba", "2026-07-18", in_dir=tmp_path)
    assert rows == [good]
    assert fx.load_day_rows("nba", "2099-01-01", in_dir=tmp_path) == []


# --------------------------------------------------------------------------- #
# load_top_usage_names: monkeypatched reader, no real parquet touched
# --------------------------------------------------------------------------- #

def test_load_top_usage_names_picks_latest_window_top_n():
    fake_df = pd.DataFrame([
        {"entity_name": "Player A", "attribute": "pts_per36", "window": "season_2023_24", "raw_value": 20.0},
        {"entity_name": "Player A", "attribute": "pts_per36", "window": "season_2024_25", "raw_value": 30.0},
        {"entity_name": "Player B", "attribute": "pts_per36", "window": "season_2024_25", "raw_value": 10.0},
        {"entity_name": "Player C", "attribute": "other_attr", "window": "season_2024_25", "raw_value": 99.0},
    ])
    names = fx.load_top_usage_names("nba", top_n=1, pd_reader=lambda path, columns=None: fake_df)
    # Player A's LATEST window (30.0) beats Player B (10.0); Player C excluded (wrong attribute)
    assert names == {fx._norm_name("Player A")}


def test_load_top_usage_names_missing_file_is_empty_set():
    def boom(path, columns=None):
        raise FileNotFoundError(path)
    assert fx.load_top_usage_names("nba", pd_reader=boom) == set()


# --------------------------------------------------------------------------- #
# build_features_frame: end-to-end wiring + margin_velocity across ticks
# --------------------------------------------------------------------------- #

def test_build_features_frame_margin_velocity_across_ticks():
    rows = [
        {"game_id": "1", "sport": "nba", "capture_ts": "2026-07-18T20:00:00+00:00",
         "home": "BOS", "away": "LAL", "score_home": 50, "score_away": 48,
         "payload": {"winprob": {"status": "error"}, "market": None, "pbp_tail": {"status": "unavailable"}}},
        {"game_id": "1", "sport": "nba", "capture_ts": "2026-07-18T20:01:00+00:00",
         "home": "BOS", "away": "LAL", "score_home": 58, "score_away": 50,
         "payload": {"winprob": {"status": "error"}, "market": None, "pbp_tail": {"status": "unavailable"}}},
    ]
    df = fx.build_features_frame(rows, star_names=set())
    assert list(df["score_margin"]) == [2.0, 8.0]
    assert _isnan(df["margin_velocity"].iloc[0])  # first tick for this game -- no prior
    assert df["margin_velocity"].iloc[1] == 6.0    # 8.0 - 2.0


def test_build_features_frame_empty_rows_returns_empty_df():
    df = fx.build_features_frame([])
    assert df.empty
