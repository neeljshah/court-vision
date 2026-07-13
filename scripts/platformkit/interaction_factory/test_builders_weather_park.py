"""Per-file test for interaction_factory.builders_weather_park (B4).
Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_weather_park.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.platformkit.interaction_factory import builders_weather_park as bwp
from scripts.platformkit.interaction_factory import generator as GEN


# --------------------------------------------------------------------------
# 1. Template + STATIC_POOL registration shape.
def test_self_cross_template_registered_with_expected_shape():
    tpl = GEN.TEMPLATES["mlb_weather_park_self_cross"]
    assert tpl["sport"] == "mlb"
    assert tpl["pairing"] == "self_cross"
    assert tpl["atomic_unit"] == "game"
    assert tpl["outcome"] == "total_runs"
    assert tpl["left_pool"] == {"static_pool": "mlb_weather_park_asof"}
    assert tpl["feature_builder"] == "mlb_weather_park_totals_asof"
    assert GEN.STATIC_POOLS["mlb_weather_park_asof"] == [
        "wind_out_mph_raw", "temp_above_park_norm_asof", "park_runs_factor_asof"]


def test_cross_template_registered_with_expected_shape():
    tpl = GEN.TEMPLATES["mlb_weather_park_umpire_cross"]
    assert tpl["sport"] == "mlb"
    assert tpl["pairing"] == "cross"
    assert tpl["atomic_unit"] == "game"
    assert tpl["outcome"] == "total_runs"
    assert tpl["left_pool"] == {"static_pool": "mlb_weather_park_asof"}
    assert tpl["right_pool"] == {"static_pool": "mlb_umpire_asof"}
    assert tpl["feature_builder"] == "mlb_weather_park_umpire_cross_asof"


def test_builders_registered_in_runner():
    from scripts.platformkit.interaction_factory import runner as RUN
    assert RUN._BUILDERS["mlb_weather_park_totals_asof"] is bwp._mlb_weather_park_asof_builder
    assert RUN._BUILDERS["mlb_weather_park_umpire_cross_asof"] is bwp._mlb_weather_park_umpire_cross_builder


def test_enumeration_nonempty_self_cross():
    cands = GEN.enumerate_candidates("mlb_weather_park_self_cross")
    assert len(cands) > 0
    pairs = {(c.attr_a, c.attr_b) for c in cands}
    assert ("temp_above_park_norm_asof", "wind_out_mph_raw") in pairs


def test_enumeration_nonempty_cross():
    cands = GEN.enumerate_candidates("mlb_weather_park_umpire_cross")
    assert len(cands) > 0
    pairs = {(c.attr_a, c.attr_b) for c in cands}
    # ordered product of left (weather/park) x right (umpire) pools.
    assert ("wind_out_mph_raw", "ump_total_runs_tendency_asof") in pairs


# --------------------------------------------------------------------------
# 2. Frame shape + values on a small synthetic corpus: 3 chronological games,
# venue A hosts games 1 and 3, venue B hosts game 2.
def _synthetic_corpus():
    return pd.DataFrame([
        {"date": pd.Timestamp("2023-04-01"), "game_pk": 1, "temp_f": 70.0,
         "wind_speed": 10.0, "wind_out": 10.0, "wind_in": 0.0, "total_runs": 10.0, "venue": "A"},
        {"date": pd.Timestamp("2023-04-02"), "game_pk": 2, "temp_f": 60.0,
         "wind_speed": 5.0, "wind_out": 0.0, "wind_in": 5.0, "total_runs": 6.0, "venue": "B"},
        {"date": pd.Timestamp("2023-04-03"), "game_pk": 3, "temp_f": 80.0,
         "wind_speed": 8.0, "wind_out": 8.0, "wind_in": 0.0, "total_runs": 4.0, "venue": "A"},
    ])


def test_frame_shape_and_first_prior_values():
    attrs = list(bwp.WEATHER_POOL_ATTRS)
    frame = bwp.build_weather_park_game_frame(_synthetic_corpus(), attrs, min_prior=1)
    assert list(frame.columns) == [
        "game_pk", "venue", "y", "asof__wind_out_mph_raw",
        "asof__temp_above_park_norm_asof", "asof__park_runs_factor_asof"]
    row1 = frame[frame["game_pk"] == 1].iloc[0]
    # venue A's own first game has 0 prior games -> park-norm attrs undefined below floor.
    assert pd.isna(row1["asof__temp_above_park_norm_asof"])
    assert pd.isna(row1["asof__park_runs_factor_asof"])
    # wind is NOT as-of -- today's own raw value, present on the very first game.
    assert row1["asof__wind_out_mph_raw"] == 10.0
    row3 = frame[frame["game_pk"] == 3].iloc[0]
    # venue A's 1 prior game (game_pk=1) mean temp_f = 70.0 -> 80.0 - 70.0 = 10.0.
    assert abs(row3["asof__temp_above_park_norm_asof"] - 10.0) < 1e-9
    # venue A's 1 prior game mean total_runs = 10.0; league prior mean
    # (games 1+2) = (10+6)/2 = 8.0 -> factor = 10.0 - 8.0 = 2.0.
    assert abs(row3["asof__park_runs_factor_asof"] - 2.0) < 1e-9
    assert row3["y"] == 4.0


def test_unrequested_attr_dropped_without_crash():
    frame = bwp.build_weather_park_game_frame(_synthetic_corpus(), ["not_a_real_attr"], min_prior=1)
    assert list(frame.columns) == ["game_pk", "venue", "y"]
    assert len(frame) == 3


# --------------------------------------------------------------------------
# 3. LEAK-GUARD (mandatory trap): a game's own park-norm asof value must be
# unchanged no matter what that SAME game's own total_runs/temp_f is
# tampered to -- built ONLY from strictly-prior games at that venue.
def test_trap_todays_own_outcome_never_leaks_into_todays_park_norm():
    base = _synthetic_corpus()
    tampered = base.copy()
    # tamper ONLY the outcome (total_runs) -- temp_f is exogenous/pregame-
    # knowable, not an outcome, so tampering it would legitimately change
    # asof__temp_above_park_norm_asof (it uses TODAY's own temp_f by design,
    # see the module's EXOGENOUS-WEATHER LEAK NUANCE), which is not a leak.
    tampered.loc[tampered["game_pk"] == 3, "total_runs"] = 999.0

    attrs = ["temp_above_park_norm_asof", "park_runs_factor_asof"]
    frame_a = bwp.build_weather_park_game_frame(base, attrs, min_prior=1).set_index("game_pk")
    frame_b = bwp.build_weather_park_game_frame(tampered, attrs, min_prior=1).set_index("game_pk")
    for col in ["asof__temp_above_park_norm_asof", "asof__park_runs_factor_asof"]:
        a, b = frame_a.loc[3, col], frame_b.loc[3, col]
        assert (pd.isna(a) and pd.isna(b)) or abs(a - b) < 1e-9


# --------------------------------------------------------------------------
# 4. EXOGENOUS-WEATHER documentation test: today's own weather is present
# (not shifted away) while today's own outcome is absent from that same
# game's weather-derived attr -- the wind attr legitimately uses TODAY's
# value (it is not an as-of/strictly-prior stat), unlike total_runs.
def test_exogenous_weather_present_today_outcome_not_reused_as_input():
    corpus = _synthetic_corpus()
    frame = bwp.build_weather_park_game_frame(corpus, ["wind_out_mph_raw"], min_prior=1)
    row1 = frame[frame["game_pk"] == 1].iloc[0]
    # today's own wind reading is directly visible (pregame-knowable, exogenous).
    assert row1["asof__wind_out_mph_raw"] == corpus.loc[corpus["game_pk"] == 1, "wind_out"].iloc[0]
    # but total_runs (the outcome) never appears anywhere on the RHS of the
    # wind attr's computation -- changing it changes only y, never the attr.
    tampered = corpus.copy()
    tampered.loc[tampered["game_pk"] == 1, "total_runs"] = -1.0
    frame_t = bwp.build_weather_park_game_frame(tampered, ["wind_out_mph_raw"], min_prior=1)
    assert frame_t.loc[frame_t["game_pk"] == 1, "asof__wind_out_mph_raw"].iloc[0] == row1["asof__wind_out_mph_raw"]


# --------------------------------------------------------------------------
# 5. Missing-source -> None, no crash.
def test_self_cross_builder_returns_none_when_source_missing(monkeypatch):
    monkeypatch.setattr(bwp, "_WEATHER_SOURCES", (
        Path("/does/not/exist_probables.parquet"),
        Path("/does/not/exist_games_current.parquet"),
    ))
    assert bwp._mlb_weather_park_asof_builder(list(bwp.WEATHER_POOL_ATTRS), {}) is None


def test_cross_builder_returns_none_when_umpire_source_missing(monkeypatch):
    monkeypatch.setattr(bwp, "_UMPIRE_SOURCES", (Path("/does/not/exist.parquet"),))
    assert bwp._mlb_weather_park_umpire_cross_builder(
        ["wind_out_mph_raw", "ump_total_runs_tendency_asof"], {}) is None


def test_self_cross_builder_builds_when_sources_present(monkeypatch):
    monkeypatch.setattr(bwp, "_WEATHER_SOURCES", (Path(__file__),))
    monkeypatch.setattr(bwp, "build_weather_park_corpus", lambda: _synthetic_corpus())
    out = bwp._mlb_weather_park_asof_builder(list(bwp.WEATHER_POOL_ATTRS), {})
    assert out is not None
    assert out["cluster"] == "venue"
    assert out["kind"] == "ols"
    assert "asof__wind_out_mph_raw" in out["frame"].columns
