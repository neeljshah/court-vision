"""Synthetic, leak-free checks for MLB in-game state features."""
import pandas as pd

from scripts.platformkit.mlb_state_features import (coverage_summary, drop_unparsed,
                                                     game_state_features, parse_state)


def _summary(home=0, away=0, inning=1, half="top", outs=0, base=0, count="0-1", pitch=2, tto=1):
    return ("home_score=%s away_score=%s inning=%s half=%s outs=%s base=%s bos=0 re=0.481 "
            "count=%s pitch_count=%s tto=%s" % (home, away, inning, half, outs, base, count, pitch, tto))


def test_parse_state_is_exact_for_valid_summary_and_tolerant_of_malformed_input():
    state = parse_state(_summary(home=3, away=2, inning=7, half="bottom", outs=2, base=5,
                                 count="2-1", pitch=91.5, tto=2.25))
    assert state == {"home_score": 3.0, "away_score": 2.0, "inning": 7, "half": "bottom",
                     "outs": 2, "base_state": 5, "run_expectancy": 0.481, "balls": 2,
                     "strikes": 1, "pitch_count": 91.5, "times_through_order": 2.25}
    broken = parse_state("home_score=x count=what inning=two")
    assert broken["home_score"] is None and broken["inning"] is None
    assert broken["balls"] is None and broken["pitch_count"] is None


def test_backward_features_are_truncation_invariant_and_use_no_future_ticks():
    base = pd.DataFrame({"game": ["G"] * 3,
                         "timestamp": ["2026-08-01T12:00:00Z", "2026-08-01T12:00:10Z", "2026-08-01T12:00:30Z"],
                         "state_summary": [_summary(), _summary(pitch=6), _summary(home=1, pitch=10)]})
    future = pd.concat([base, pd.DataFrame({"game": ["G"], "timestamp": ["2026-08-01T12:02:00Z"],
                                             "state_summary": [_summary(home=4, pitch=90)]})], ignore_index=True)
    columns = ["pitch_tempo_seconds", "score_change_recency", "score_diff", "leverage_proxy"]
    assert game_state_features(base)[columns].equals(game_state_features(future).iloc[:len(base)][columns])
    features = game_state_features(base)
    assert features["pitch_tempo_seconds"].tolist() == [0.0, 10.0, 15.0]
    assert features["score_change_recency"].tolist() == [0.0, 1.0, 0.0]


def test_pitch_count_and_tto_remain_continuous_not_binned():
    ticks = pd.DataFrame({"game": ["G", "G"], "timestamp": ["2026-08-01T12:00:00Z", "2026-08-01T12:00:05Z"],
                          "state_summary": [_summary(pitch=23.5, tto=1.25), _summary(pitch=24.5, tto=1.35)]})
    features = game_state_features(ticks)
    assert features["pitch_count"].tolist() == [23.5, 24.5]
    assert features["times_through_order"].tolist() == [1.25, 1.35]
    assert features["batters_faced_continuous"].tolist() == [5.875, 6.125]
    assert not any("tto_" in column or "pitch_count_" in column for column in features.columns)


def test_unparseable_ticks_are_nan_and_census_is_exact():
    ticks = pd.DataFrame({"game": ["G1", "G1", "G2", "G2", "G3"],
                          "timestamp": ["2026-08-01T12:00:00Z", "2026-08-01T12:00:10Z",
                                        "2026-08-01T12:00:20Z", "2026-08-01T12:00:30Z",
                                        "2026-08-01T12:00:40Z"],
                          "state_summary": [_summary(), "not a state", {"home_score": 2},
                                             "not a state", None]})
    features = game_state_features(ticks)

    assert features["parse_quality"].tolist() == ["full", "none", "partial", "none", "none"]
    assert features["state_parsed"].tolist() == [True, False, True, False, False]
    assert pd.isna(features.loc[1, "score_diff"])
    assert pd.isna(features.loc[1, "base_out_0"])
    assert len(drop_unparsed(features)) == 2

    census = coverage_summary(ticks, features)
    assert "PARSE_QUALITY_FULL_ROWS: 1" in census
    assert "PARSE_QUALITY_FULL_SHARE: 0.200000" in census
    assert "PARSE_QUALITY_PARTIAL_ROWS: 1" in census
    assert "PARSE_QUALITY_PARTIAL_SHARE: 0.200000" in census
    assert "PARSE_QUALITY_NONE_ROWS: 3" in census
    assert "PARSE_QUALITY_NONE_SHARE: 0.600000" in census
    assert "GAMES_100_PCT_UNPARSEABLE: 1" in census
