"""tests/test_signal_clutch_regime.py — unit tests for the ClutchRegimeSignal.

Tests:
  1. Leak-safety assertion: build() never reads store records stamped after
     ctx.decision_time.
  2. Value-sanity assertions: clutch_prob in [0, 1], clutch_usage_prior in [0, 1],
     both finite floats; validate_output() passes.
  3. Live snapshot path: clutch_prob near 1.0 for clear clutch situation.
  4. Live snapshot path: clutch_prob near 0.0 for blowout / early Q4.
  5. Null path (no data): returns a dict (not None) with neutral defaults.
  6. hypothesis() contract: correct name/target/scope and non-empty statement.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

# Ensure repo root is on the path (SAFETY rule: sys.path.insert from repo root)
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

import pytest

from src.loop.signal import AsOfContext
from src.loop.store import PointInTimeStore, entity_key
from signals.clutch_regime import ClutchRegimeSignal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ctx(
    decision_time: _dt.datetime,
    player_id: int = 1628983,
    team: str = "OKC",
    opp: str = "DAL",
    game_id: str = "0022400999",
    game_date: str = "2025-01-15",
    scope: str = "live",
    live: dict = None,
    extra: dict = None,
) -> AsOfContext:
    return AsOfContext(
        decision_time=decision_time,
        player_id=player_id,
        team=team,
        opp=opp,
        game_id=game_id,
        game_date=game_date,
        season="2024-25",
        is_home=True,
        scope=scope,
        snapshot="endQ4",
        live=live,
        extra=extra or {},
    )


def _make_signal(store: PointInTimeStore = None) -> ClutchRegimeSignal:
    return ClutchRegimeSignal(store=store)


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY ASSERTION
#    Writes a record AFTER decision_time into the store; confirms build() does
#    NOT return that value (the store's read_atlas is leak-safe by contract, but
#    we verify the signal's read_atlas call respects the as_of boundary).
# ---------------------------------------------------------------------------

def test_leak_safety(tmp_path: Path) -> None:
    """build() must not return values written AFTER ctx.decision_time."""
    decision_time = _dt.datetime(2025, 1, 15, 18, 0, 0)
    future_time = _dt.datetime(2025, 1, 16, 0, 0, 0)  # AFTER decision_time

    store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)

    # Write a future clutch atlas value with a VERY high pts_per36 (would shift prior)
    future_clutch_data = {
        "clutch_pts_per36": 999.0,  # obviously wrong; only appears if leak
        "clutch_gp": 100,
        "clutch_min": 5.0,
    }
    store.write_atlas(
        entity_type="player",
        entity_id=1628983,
        section="clutch",
        as_of=future_time,          # FUTURE record
        data=future_clutch_data,
        provenance={"source": "test_future", "n": 100, "confidence": "high"},
    )

    sig = _make_signal(store=store)
    ctx = _make_ctx(
        decision_time=decision_time,
        live={"period": 4, "clock": "2:30", "home_score": 98, "away_score": 97,
              "home_team": "OKC", "away_team": "DAL", "players": []},
    )
    result = sig.build(ctx)

    # Must return a valid dict
    assert isinstance(result, dict), "Expected dict output"
    # clutch_usage_prior must NOT reflect the future 999.0 pts_per36 value
    # (if it did, the prior would be >= 1.0 ≈ 999/60; neutral would be ~0.182)
    # We cannot read the future record, so the prior should be ≤ 1.0 and NOT
    # derived from 999/60 = 16.6 which would be clipped to 1.0 — but the store
    # guarantees the future record is invisible, so the value comes from the
    # neutral default (~0.182) or PBP L5 (which has no data here).
    prior = result["clutch_usage_prior"]
    assert prior is not None
    # Verify the future-stamped atlas value was NOT used: if it had been used,
    # atlas_prior = min(1.0, 999/60) = 1.0, and with no pbp_prior the avg = 1.0.
    # The real result should be the league average (0.182).
    assert prior < 0.5, (
        f"Prior {prior} suggests a future atlas record leaked into the build. "
        "Expected ~0.182 (league average) since no past atlas data exists."
    )


# ---------------------------------------------------------------------------
# 2. VALUE-SANITY ASSERTION (clutch_prob and clutch_usage_prior in [0, 1])
# ---------------------------------------------------------------------------

def test_value_sanity_clear_clutch() -> None:
    """For a clear clutch situation, clutch_prob should be close to 1 and prior in [0,1]."""
    sig = _make_signal()
    decision_time = _dt.datetime(2025, 1, 15, 22, 45, 0)
    live = {
        "period": 4,
        "clock": "1:30",          # 1.5 min left — definitely clutch
        "home_score": 102,
        "away_score": 101,         # 1-pt margin — textbook clutch
        "home_team": "OKC",
        "away_team": "DAL",
        "players": [],
    }
    ctx = _make_ctx(decision_time=decision_time, live=live)
    result = sig.build(ctx)

    assert result is not None
    assert isinstance(result, dict)
    assert sig.validate_output(result), "validate_output() must pass"

    # clutch_prob should be near 1 for clear clutch
    cp = result["clutch_prob"]
    assert isinstance(cp, float), "clutch_prob must be float"
    assert 0.0 <= cp <= 1.0, f"clutch_prob={cp} out of [0,1]"
    assert cp > 0.7, f"Expected high clutch_prob for close/late situation, got {cp}"

    # clutch_usage_prior must be in [0, 1]
    cup = result["clutch_usage_prior"]
    assert isinstance(cup, float), "clutch_usage_prior must be float"
    assert 0.0 <= cup <= 1.0, f"clutch_usage_prior={cup} out of [0,1]"


def test_value_sanity_blowout() -> None:
    """For a blowout situation, clutch_prob should be near 0."""
    sig = _make_signal()
    decision_time = _dt.datetime(2025, 1, 15, 22, 45, 0)
    live = {
        "period": 4,
        "clock": "2:00",
        "home_score": 120,
        "away_score": 95,          # 25-pt margin — garbage time
        "home_team": "OKC",
        "away_team": "DAL",
        "players": [],
    }
    ctx = _make_ctx(decision_time=decision_time, live=live)
    result = sig.build(ctx)

    assert result is not None
    cp = result["clutch_prob"]
    assert 0.0 <= cp <= 1.0
    assert cp < 0.1, f"Expected near-zero clutch_prob for blowout, got {cp}"


def test_value_sanity_q1() -> None:
    """Clutch_prob should be 0.0 for Q1 (not a clutch period)."""
    sig = _make_signal()
    decision_time = _dt.datetime(2025, 1, 15, 20, 0, 0)
    live = {
        "period": 1,
        "clock": "8:00",
        "home_score": 10,
        "away_score": 10,
        "home_team": "OKC",
        "away_team": "DAL",
        "players": [],
    }
    ctx = _make_ctx(decision_time=decision_time, live=live)
    result = sig.build(ctx)

    assert result is not None
    cp = result["clutch_prob"]
    assert cp == 0.0, f"Expected 0.0 for Q1, got {cp}"


def test_value_sanity_overtime() -> None:
    """Clutch_prob should be 1.0 for OT (always clutch)."""
    sig = _make_signal()
    decision_time = _dt.datetime(2025, 1, 15, 23, 0, 0)
    live = {
        "period": 5,               # OT
        "clock": "3:00",
        "home_score": 110,
        "away_score": 109,
        "home_team": "OKC",
        "away_team": "DAL",
        "players": [],
    }
    ctx = _make_ctx(decision_time=decision_time, live=live)
    result = sig.build(ctx)

    assert result is not None
    cp = result["clutch_prob"]
    assert cp == 1.0, f"Expected 1.0 for OT, got {cp}"


# ---------------------------------------------------------------------------
# 3. NULL / NO DATA PATH
#    When there is no live snapshot, no game_id match, and no pregame win prob,
#    the signal should still return a dict (not None) with valid defaults.
# ---------------------------------------------------------------------------

def test_null_data_path() -> None:
    """Signal returns a valid dict (not None) when no data sources are available."""
    sig = _make_signal()
    decision_time = _dt.datetime(2025, 1, 15, 12, 0, 0)
    ctx = AsOfContext(
        decision_time=decision_time,
        player_id=9999999,          # unknown player
        team="ZZZ",
        game_id=None,
        game_date=None,
        scope="live",
    )
    result = sig.build(ctx)

    # Must return a dict with neutral defaults (not None)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "clutch_prob" in result
    assert "clutch_usage_prior" in result
    cp = result["clutch_prob"]
    cup = result["clutch_usage_prior"]
    assert 0.0 <= cp <= 1.0
    assert 0.0 <= cup <= 1.0
    assert sig.validate_output(result)


# ---------------------------------------------------------------------------
# 4. HYPOTHESIS CONTRACT
# ---------------------------------------------------------------------------

def test_hypothesis_contract() -> None:
    """hypothesis() returns a well-formed Hypothesis with correct metadata."""
    sig = _make_signal()
    h = sig.hypothesis()

    assert h.name == "clutch_regime"
    assert h.target == "usage"
    assert h.scope == "live"
    assert len(h.statement) > 20, "Statement must be non-trivial"
    assert "clutch" in h.atlas_fields
    assert h.expected_verdict == "SHIP"
    assert h.priority == "P1"


# ---------------------------------------------------------------------------
# 5. FEATURE NAMES CONTRACT
# ---------------------------------------------------------------------------

def test_feature_names() -> None:
    """feature_names() returns the two namespaced sub-feature names."""
    sig = _make_signal()
    names = sig.feature_names()
    assert "clutch_regime__clutch_prob" in names
    assert "clutch_regime__clutch_usage_prior" in names
    assert len(names) == 2


# ---------------------------------------------------------------------------
# 6. ATLAS-WRITE-BACK ROUND TRIP (reinforcement loop sanity)
#    Confirms that a shipped signal's values can be written back to the store
#    and read by a future build() call (the write_signal_field / read pattern).
# ---------------------------------------------------------------------------

def test_atlas_writeback_roundtrip(tmp_path: Path) -> None:
    """write_signal_field + build confirms reinforcement write-back reads correctly."""
    store = PointInTimeStore(store_dir=tmp_path / "store2", autoload=False)
    ship_date = _dt.datetime(2025, 1, 10)
    # Simulate a SHIPPED signal writing a clutch-usage learned value back
    store.write_signal_field(
        entity_type="player",
        entity_id=1628983,
        signal_name="clutch_regime",
        as_of=ship_date,
        value={"clutch_usage_prior": 0.42},
    )

    # Confirm the value is readable at a LATER decision_time
    later = _dt.datetime(2025, 1, 15)
    val = store.read_signal_field("player", 1628983, "clutch_regime", later)
    assert val is not None
    assert isinstance(val, dict)
    assert abs(val.get("clutch_usage_prior", 0) - 0.42) < 1e-6

    # And NOT readable at an EARLIER decision_time (leak-safety)
    earlier = _dt.datetime(2025, 1, 9)
    val_early = store.read_signal_field("player", 1628983, "clutch_regime", earlier)
    assert val_early is None, "Should not see a future write at earlier decision_time"
