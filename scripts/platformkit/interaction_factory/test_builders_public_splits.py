"""Per-file test for interaction_factory.builders_public_splits (B6).
Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_public_splits.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.platformkit.interaction_factory import builders_public_splits as bps
from scripts.platformkit.interaction_factory import generator as GEN


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


COMMENCE = _ts("2026-07-10T22:40:00Z")


def _fixture_snaps() -> pd.DataFrame:
    """One game: open snapshot (tickets 55/45 home/away, odds -120/+100) ->
    close snapshot (tickets 65/35, odds -140/+120, majority shifts further
    toward home) -> a POISONED post-commence snapshot (tickets 90, odds
    -500) that must never be used."""
    rows = [
        {"fetched_dt": _ts("2026-07-10T05:00:00Z"), "side": "home",
         "tickets_pct": 55, "money_pct": 48, "odds": -120},
        {"fetched_dt": _ts("2026-07-10T05:00:00Z"), "side": "away",
         "tickets_pct": 45, "money_pct": 52, "odds": 100},
        {"fetched_dt": _ts("2026-07-10T18:00:00Z"), "side": "home",
         "tickets_pct": 65, "money_pct": 40, "odds": -140},
        {"fetched_dt": _ts("2026-07-10T18:00:00Z"), "side": "away",
         "tickets_pct": 35, "money_pct": 60, "odds": 120},
        {"fetched_dt": _ts("2026-07-10T23:00:00Z"), "side": "home",
         "tickets_pct": 90, "money_pct": 10, "odds": -500},  # POISON
    ]
    df = pd.DataFrame(rows)
    df["commence_dt"] = COMMENCE
    return df


# --------------------------------------------------------------------------
# 1. Pre-commence leak trap + divergence math fixture.
def test_leak_trap_and_divergence_math_on_fixture():
    out = bps.compute_public_splits_game_features(_fixture_snaps())
    assert abs(out["public_bet_pct_home"] - 65.0) < 1e-9
    assert abs(out["public_money_pct_home"] - 40.0) < 1e-9
    assert abs(out["bet_money_divergence"] - 25.0) < 1e-9
    # implied_prob(-140) - implied_prob(-120) = 140/240 - 120/220, sign=+1 (majority home)
    expected_gap = (140.0 / 240.0) - (120.0 / 220.0)
    assert abs(out["public_line_gap"] - expected_gap) < 1e-9


def test_poison_snapshot_does_not_change_result_vs_pre_poison_truth():
    poisoned = _fixture_snaps()
    clean = poisoned[poisoned["fetched_dt"] <= poisoned["commence_dt"]].copy()
    assert bps.compute_public_splits_game_features(poisoned) == bps.compute_public_splits_game_features(clean)


# --------------------------------------------------------------------------
# 2. Single-snapshot honesty: bet%/money%/divergence compute, line_gap NaN.
def test_single_pregame_snapshot_gives_nan_line_gap_not_a_guess():
    rows = [
        {"fetched_dt": _ts("2026-07-10T18:00:00Z"), "side": "home",
         "tickets_pct": 60, "money_pct": 55, "odds": -130},
        {"fetched_dt": _ts("2026-07-10T18:00:00Z"), "side": "away",
         "tickets_pct": 40, "money_pct": 45, "odds": 110},
    ]
    df = pd.DataFrame(rows)
    df["commence_dt"] = COMMENCE
    out = bps.compute_public_splits_game_features(df)
    assert abs(out["public_bet_pct_home"] - 60.0) < 1e-9
    assert abs(out["bet_money_divergence"] - 5.0) < 1e-9
    assert pd.isna(out["public_line_gap"])


def test_no_pregame_snapshots_all_nan():
    rows = [{"fetched_dt": _ts("2026-07-10T23:30:00Z"), "side": "home",
             "tickets_pct": 60, "money_pct": 55, "odds": -130}]
    df = pd.DataFrame(rows)
    df["commence_dt"] = COMMENCE
    out = bps.compute_public_splits_game_features(df)
    assert all(pd.isna(v) for v in out.values())


def test_tie_split_gives_nan_line_gap_no_majority_to_sign_by():
    rows = [
        {"fetched_dt": _ts("2026-07-10T05:00:00Z"), "side": "home",
         "tickets_pct": 50, "money_pct": 50, "odds": -110},
        {"fetched_dt": _ts("2026-07-10T18:00:00Z"), "side": "home",
         "tickets_pct": 50, "money_pct": 50, "odds": -120},
    ]
    df = pd.DataFrame(rows)
    df["commence_dt"] = COMMENCE
    out = bps.compute_public_splits_game_features(df)
    assert abs(out["bet_money_divergence"] - 0.0) < 1e-9
    assert pd.isna(out["public_line_gap"])


# --------------------------------------------------------------------------
# 3. Frame shape on a synthetic corpus.
def _synthetic_corpus() -> pd.DataFrame:
    return pd.DataFrame([
        {"game_id": "291677", "venue": "Truist Park", "home_win": 0.0, "event_id": "401816084",
         "public_bet_pct_home": 65.0, "public_money_pct_home": 40.0,
         "bet_money_divergence": 25.0, "public_line_gap": 0.05},
        {"game_id": "291678", "venue": "Yankee Stadium", "home_win": 1.0, "event_id": "401816087",
         "public_bet_pct_home": 50.0, "public_money_pct_home": 50.0,
         "bet_money_divergence": 0.0, "public_line_gap": float("nan")},
    ])


def test_frame_shape():
    attrs = list(bps.PUBLIC_SPLITS_POOL_ATTRS)
    frame = bps.build_public_splits_game_frame(_synthetic_corpus(), attrs)
    assert list(frame.columns) == [
        "game_id", "venue", "y", "asof__public_bet_pct_home", "asof__public_money_pct_home",
        "asof__bet_money_divergence", "asof__public_line_gap"]
    assert len(frame) == 2
    assert frame.loc[frame["game_id"] == "291678", "y"].iloc[0] == 1.0


def test_unrequested_attr_dropped_without_crash():
    frame = bps.build_public_splits_game_frame(_synthetic_corpus(), ["not_a_real_attr"])
    assert list(frame.columns) == ["game_id", "venue", "y"]
    assert len(frame) == 2


# --------------------------------------------------------------------------
# 4. Template + STATIC_POOL registration shape.
def test_self_cross_template_registered_with_expected_shape():
    tpl = GEN.TEMPLATES["mlb_public_splits_self_cross"]
    assert tpl["sport"] == "mlb"
    assert tpl["pairing"] == "self_cross"
    assert tpl["atomic_unit"] == "game"
    assert tpl["outcome"] == "home_win"
    assert tpl["left_pool"] == {"static_pool": "mlb_public_splits_asof"}
    assert tpl["feature_builder"] == "mlb_public_splits_totals_asof"
    assert GEN.STATIC_POOLS["mlb_public_splits_asof"] == list(bps.PUBLIC_SPLITS_POOL_ATTRS)


def test_cross_template_registered_with_expected_shape():
    tpl = GEN.TEMPLATES["mlb_public_splits_market_micro_cross"]
    assert tpl["sport"] == "mlb"
    assert tpl["pairing"] == "cross"
    assert tpl["atomic_unit"] == "game"
    assert tpl["outcome"] == "home_win"
    assert tpl["left_pool"] == {"static_pool": "mlb_public_splits_asof"}
    assert tpl["right_pool"] == {"static_pool": "mlb_market_micro_asof"}
    assert tpl["feature_builder"] == "mlb_public_splits_market_micro_cross_asof"


def test_builders_registered_in_runner():
    from scripts.platformkit.interaction_factory import runner as RUN
    assert RUN._BUILDERS["mlb_public_splits_totals_asof"] is bps._mlb_public_splits_asof_builder
    assert (RUN._BUILDERS["mlb_public_splits_market_micro_cross_asof"]
            is bps._mlb_public_splits_market_micro_cross_builder)


def test_enumeration_nonempty_self_cross():
    cands = GEN.enumerate_candidates("mlb_public_splits_self_cross")
    assert len(cands) > 0
    pairs = {(c.attr_a, c.attr_b) for c in cands}
    assert ("bet_money_divergence", "public_bet_pct_home") in pairs


def test_enumeration_nonempty_cross():
    cands = GEN.enumerate_candidates("mlb_public_splits_market_micro_cross")
    assert len(cands) > 0
    pairs = {(c.attr_a, c.attr_b) for c in cands}
    assert ("public_bet_pct_home", "line_move_velocity_pregame") in pairs


# --------------------------------------------------------------------------
# 5. Missing-source -> None, no crash.
def test_self_cross_builder_returns_none_when_source_missing(monkeypatch):
    monkeypatch.setattr(bps, "_PUBLIC_SPLITS_DIR", Path("/does/not/exist"))
    assert bps._mlb_public_splits_asof_builder(list(bps.PUBLIC_SPLITS_POOL_ATTRS), {}) is None


def test_cross_builder_returns_none_when_source_missing(monkeypatch):
    monkeypatch.setattr(bps, "_ESPN_BOX", Path("/does/not/exist.parquet"))
    assert bps._mlb_public_splits_market_micro_cross_builder(
        ["public_bet_pct_home", "line_move_velocity_pregame"], {}) is None
