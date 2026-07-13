"""Per-file test for interaction_factory.builders_umpire (B3).
Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_umpire.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.platformkit.interaction_factory import builders_umpire as bu
from scripts.platformkit.interaction_factory import generator as GEN


# --------------------------------------------------------------------------
# 1. Template + STATIC_POOL registration shape.
def test_template_registered_with_expected_shape():
    tpl = GEN.TEMPLATES["mlb_umpire_self_cross"]
    assert tpl["sport"] == "mlb"
    assert tpl["pairing"] == "self_cross"
    assert tpl["atomic_unit"] == "game"
    assert tpl["outcome"] == "total_runs"
    assert tpl["left_pool"] == {"static_pool": "mlb_umpire_asof"}
    assert tpl["feature_builder"] == "mlb_umpire_totals_asof"
    assert GEN.STATIC_POOLS["mlb_umpire_asof"] == [
        "ump_total_runs_tendency_asof", "ump_called_strike_proxy_asof"]


def test_builder_registered_in_runner():
    from scripts.platformkit.interaction_factory import runner as RUN
    assert RUN._BUILDERS["mlb_umpire_totals_asof"] is bu._mlb_umpire_asof_builder


def test_enumeration_nonempty():
    cands = GEN.enumerate_candidates("mlb_umpire_self_cross")
    assert len(cands) > 0
    assert all(isinstance(c, GEN.Candidate) for c in cands)
    pairs = {(c.attr_a, c.attr_b) for c in cands}
    assert ("ump_called_strike_proxy_asof", "ump_total_runs_tendency_asof") in pairs


# --------------------------------------------------------------------------
# 2. Frame shape + values on a small synthetic corpus: 3 chronological games,
# umpire A works games 1 and 3, umpire B works game 2.
def _synthetic_corpus():
    return pd.DataFrame([
        {"game_pk": 1, "date": "2023-04-01", "home_team": "PIT", "hp_umpire_id": 1,
         "total_runs": 10.0, "n_ooz": 100, "ooz_strikes": 30},
        {"game_pk": 2, "date": "2023-04-02", "home_team": "NYM", "hp_umpire_id": 2,
         "total_runs": 6.0, "n_ooz": 80, "ooz_strikes": 20},
        {"game_pk": 3, "date": "2023-04-03", "home_team": "PIT", "hp_umpire_id": 1,
         "total_runs": 4.0, "n_ooz": 90, "ooz_strikes": 45},
    ])


def test_frame_shape_and_first_prior_values():
    attrs = ["ump_total_runs_tendency_asof", "ump_called_strike_proxy_asof"]
    frame = bu.build_umpire_game_frame(_synthetic_corpus(), attrs, min_prior=1)
    assert list(frame.columns) == [
        "game_pk", "hp_umpire_id", "y", "asof__ump_total_runs_tendency_asof",
        "asof__ump_called_strike_proxy_asof"]
    row1 = frame[frame["game_pk"] == 1].iloc[0]
    row2 = frame[frame["game_pk"] == 2].iloc[0]
    # each umpire's own FIRST appearance has 0 prior games -> undefined below floor.
    assert pd.isna(row1["asof__ump_total_runs_tendency_asof"])
    assert pd.isna(row2["asof__ump_total_runs_tendency_asof"])
    row3 = frame[frame["game_pk"] == 3].iloc[0]
    # ump 1's 1 prior game (game_pk=1) mean total_runs = 10.0; league prior
    # mean (games 1+2) = (10+6)/2 = 8.0 -> tendency = 10.0 - 8.0 = 2.0.
    assert abs(row3["asof__ump_total_runs_tendency_asof"] - 2.0) < 1e-9
    # ump 1's 1 prior game ooz_strikes/n_ooz = 30/100 = 0.30.
    assert abs(row3["asof__ump_called_strike_proxy_asof"] - 0.30) < 1e-9
    assert row3["y"] == 4.0


def test_unrequested_attr_dropped_without_crash():
    frame = bu.build_umpire_game_frame(_synthetic_corpus(), ["not_a_real_attr"], min_prior=1)
    assert list(frame.columns) == ["game_pk", "hp_umpire_id", "y"]
    assert len(frame) == 3


# --------------------------------------------------------------------------
# 3. LEAK-GUARD (mandatory trap): a game's own asof value must be unchanged
# no matter what that SAME game's own total_runs/ooz outcome is tampered to
# -- the value is built ONLY from strictly-prior games.
def test_trap_todays_own_outcome_never_leaks_into_todays_asof():
    base = _synthetic_corpus()
    tampered = base.copy()
    tampered.loc[tampered["game_pk"] == 3, ["total_runs", "n_ooz", "ooz_strikes"]] = [999.0, 1, 1]

    attrs = ["ump_total_runs_tendency_asof", "ump_called_strike_proxy_asof"]
    frame_a = bu.build_umpire_game_frame(base, attrs, min_prior=1).set_index("game_pk")
    frame_b = bu.build_umpire_game_frame(tampered, attrs, min_prior=1).set_index("game_pk")
    for col in ["asof__ump_total_runs_tendency_asof", "asof__ump_called_strike_proxy_asof"]:
        a, b = frame_a.loc[3, col], frame_b.loc[3, col]
        assert (pd.isna(a) and pd.isna(b)) or abs(a - b) < 1e-9


# --------------------------------------------------------------------------
# 4. Missing-source -> None, no crash.
def test_builder_returns_none_when_source_missing(monkeypatch):
    monkeypatch.setattr(bu, "_UMPIRE_SOURCES", (
        Path("/does/not/exist_2022.parquet"),
        Path("/does/not/exist_2023.parquet"),
        Path("/does/not/exist_probables.parquet"),
    ))
    assert bu._mlb_umpire_asof_builder(
        ["ump_total_runs_tendency_asof", "ump_called_strike_proxy_asof"], {}) is None


def test_builder_builds_when_sources_present(monkeypatch):
    monkeypatch.setattr(bu, "_UMPIRE_SOURCES", (Path(__file__),))
    monkeypatch.setattr(bu, "build_umpire_totals_corpus", lambda: _synthetic_corpus())
    out = bu._mlb_umpire_asof_builder(
        ["ump_total_runs_tendency_asof", "ump_called_strike_proxy_asof"], {})
    assert out is not None
    assert out["cluster"] == "hp_umpire_id"
    assert out["kind"] == "ols"
    assert "asof__ump_total_runs_tendency_asof" in out["frame"].columns
