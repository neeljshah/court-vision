"""Per-file test for interaction_factory.builders_market_micro (B5).
Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_market_micro.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.platformkit.interaction_factory import builders_market_micro as bmm
from scripts.platformkit.interaction_factory import generator as GEN


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


COMMENCE = _ts("2026-06-18T20:00:00Z")


def _fixture_snaps() -> pd.DataFrame:
    """One game: open 8.0 (both books) -> 8.25 (DK moves) -> close 8.75 (both
    books again, DK+Pinnacle diverge 9.0/8.5) -> a POISONED post-commence
    snapshot (DK=20.0, 10 min after commence) that must never be used."""
    rows = [
        {"captured_dt": _ts("2026-06-18T17:00:00Z"), "book": "espn:DraftKings", "line": 8.0},
        {"captured_dt": _ts("2026-06-18T17:00:00Z"), "book": "pinnacle", "line": 8.0},
        {"captured_dt": _ts("2026-06-18T18:00:00Z"), "book": "espn:DraftKings", "line": 8.5},
        {"captured_dt": _ts("2026-06-18T18:00:00Z"), "book": "pinnacle", "line": 8.0},
        {"captured_dt": _ts("2026-06-18T19:00:00Z"), "book": "espn:DraftKings", "line": 9.0},
        {"captured_dt": _ts("2026-06-18T19:00:00Z"), "book": "pinnacle", "line": 8.5},
        {"captured_dt": _ts("2026-06-18T20:10:00Z"), "book": "espn:DraftKings", "line": 20.0},  # POISON
    ]
    df = pd.DataFrame(rows)
    df["commence_dt"] = COMMENCE
    return df


# --------------------------------------------------------------------------
# 1. Velocity math + leak trap + divergence, on the hand-computed fixture.
def test_velocity_math_and_leak_trap_and_divergence_on_fixture():
    out = bmm.compute_market_micro_game_features(_fixture_snaps())
    # open=8.0@17:00, close=8.75@19:00 (POISON excluded) -> hours=2.0
    assert abs(out["line_move_velocity_pregame"] - 0.375) < 1e-9
    assert abs(out["line_move_total_abs"] - 0.75) < 1e-9
    # divergence at close (19:00): [9.0, 8.5] -> population std
    assert abs(out["cross_book_divergence_at_close"] - 0.25) < 1e-9
    # line moved at every snapshot up to and including close -> frac 1.0
    assert abs(out["time_of_last_move_frac"] - 1.0) < 1e-9


def test_poison_snapshot_does_not_change_result_vs_pre_poison_truth():
    poisoned = _fixture_snaps()
    clean = poisoned[poisoned["captured_dt"] <= poisoned["commence_dt"]].copy()
    assert bmm.compute_market_micro_game_features(poisoned) == bmm.compute_market_micro_game_features(clean)


# --------------------------------------------------------------------------
# 2. Single-book-at-close -> honest NaN divergence; the other 3 attrs still compute.
def test_single_book_at_close_gives_nan_divergence_not_a_guess():
    rows = [
        {"captured_dt": _ts("2026-06-18T17:00:00Z"), "book": "espn:DraftKings", "line": 8.0},
        {"captured_dt": _ts("2026-06-18T17:00:00Z"), "book": "pinnacle", "line": 8.0},
        {"captured_dt": _ts("2026-06-18T19:00:00Z"), "book": "espn:DraftKings", "line": 8.5},
    ]
    df = pd.DataFrame(rows)
    df["commence_dt"] = COMMENCE
    out = bmm.compute_market_micro_game_features(df)
    assert pd.isna(out["cross_book_divergence_at_close"])
    assert abs(out["line_move_velocity_pregame"] - 0.25) < 1e-9  # (8.5-8.0)/2h


def test_no_pregame_snapshots_all_nan():
    rows = [{"captured_dt": _ts("2026-06-18T20:30:00Z"), "book": "espn:DraftKings", "line": 8.0}]
    df = pd.DataFrame(rows)
    df["commence_dt"] = COMMENCE
    out = bmm.compute_market_micro_game_features(df)
    assert all(pd.isna(v) for v in out.values())


# --------------------------------------------------------------------------
# 3. Frame shape on a synthetic corpus (build_market_micro_game_frame).
def _synthetic_corpus() -> pd.DataFrame:
    return pd.DataFrame([
        {"game_id": "1", "home": "Boston Red Sox", "away": "Toronto Blue Jays",
         "commence_time": "2026-06-18T20:00Z", "venue": "Fenway Park", "total_runs": 7.0,
         "line_move_velocity_pregame": 0.375, "line_move_total_abs": 0.75,
         "cross_book_divergence_at_close": 0.25, "time_of_last_move_frac": 1.0},
        {"game_id": "2", "home": "Milwaukee Brewers", "away": "Cleveland Guardians",
         "commence_time": "2026-06-18T18:10Z", "venue": "American Family Field", "total_runs": 6.0,
         "line_move_velocity_pregame": 0.0, "line_move_total_abs": 0.0,
         "cross_book_divergence_at_close": float("nan"), "time_of_last_move_frac": 0.0},
    ])


def test_frame_shape():
    attrs = list(bmm.MARKET_MICRO_POOL_ATTRS)
    frame = bmm.build_market_micro_game_frame(_synthetic_corpus(), attrs)
    assert list(frame.columns) == [
        "game_id", "venue", "y", "asof__line_move_velocity_pregame", "asof__line_move_total_abs",
        "asof__cross_book_divergence_at_close", "asof__time_of_last_move_frac"]
    assert len(frame) == 2
    assert frame.loc[frame["game_id"] == "1", "y"].iloc[0] == 7.0


def test_unrequested_attr_dropped_without_crash():
    frame = bmm.build_market_micro_game_frame(_synthetic_corpus(), ["not_a_real_attr"])
    assert list(frame.columns) == ["game_id", "venue", "y"]
    assert len(frame) == 2


# --------------------------------------------------------------------------
# 4. Template + STATIC_POOL registration shape.
def test_self_cross_template_registered_with_expected_shape():
    tpl = GEN.TEMPLATES["mlb_market_micro_self_cross"]
    assert tpl["sport"] == "mlb"
    assert tpl["pairing"] == "self_cross"
    assert tpl["atomic_unit"] == "game"
    assert tpl["outcome"] == "total_runs"
    assert tpl["left_pool"] == {"static_pool": "mlb_market_micro_asof"}
    assert tpl["feature_builder"] == "mlb_market_micro_totals_asof"
    assert GEN.STATIC_POOLS["mlb_market_micro_asof"] == list(bmm.MARKET_MICRO_POOL_ATTRS)


def test_cross_template_registered_with_expected_shape():
    tpl = GEN.TEMPLATES["mlb_market_micro_weather_cross"]
    assert tpl["sport"] == "mlb"
    assert tpl["pairing"] == "cross"
    assert tpl["atomic_unit"] == "game"
    assert tpl["outcome"] == "total_runs"
    assert tpl["left_pool"] == {"static_pool": "mlb_market_micro_asof"}
    assert tpl["right_pool"] == {"static_pool": "mlb_weather_park_asof"}
    assert tpl["feature_builder"] == "mlb_market_micro_weather_cross_asof"


def test_builders_registered_in_runner():
    from scripts.platformkit.interaction_factory import runner as RUN
    assert RUN._BUILDERS["mlb_market_micro_totals_asof"] is bmm._mlb_market_micro_asof_builder
    assert RUN._BUILDERS["mlb_market_micro_weather_cross_asof"] is bmm._mlb_market_micro_weather_cross_builder


def test_enumeration_nonempty_self_cross():
    cands = GEN.enumerate_candidates("mlb_market_micro_self_cross")
    assert len(cands) > 0
    pairs = {(c.attr_a, c.attr_b) for c in cands}
    assert ("line_move_total_abs", "line_move_velocity_pregame") in pairs


def test_enumeration_nonempty_cross():
    cands = GEN.enumerate_candidates("mlb_market_micro_weather_cross")
    assert len(cands) > 0
    pairs = {(c.attr_a, c.attr_b) for c in cands}
    assert ("line_move_velocity_pregame", "wind_out_mph_raw") in pairs


# --------------------------------------------------------------------------
# 5. Missing-source -> None, no crash.
def test_self_cross_builder_returns_none_when_source_missing(monkeypatch):
    monkeypatch.setattr(bmm, "_LINE_HISTORY_DIR", Path("/does/not/exist"))
    assert bmm._mlb_market_micro_asof_builder(list(bmm.MARKET_MICRO_POOL_ATTRS), {}) is None


def test_cross_builder_returns_none_when_probables_missing(monkeypatch):
    monkeypatch.setattr(bmm, "_PROBABLES", Path("/does/not/exist.parquet"))
    assert bmm._mlb_market_micro_weather_cross_builder(
        ["line_move_velocity_pregame", "wind_out_mph_raw"], {}) is None
