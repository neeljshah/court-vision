"""Tests for signals/usage_seesaw.py — UsageSeesawSignal.

Tests verified:
1. Leak-safety: build() with a future atlas record returns a result that does NOT
   include the future-stamped learned coefficient (the store's as-of guard holds).
2. Value-sanity: with a known DNP excess and usage baseline the composite
   seesaw_score matches the expected formula output.
3. None-path: missing context fields (no team / no player_id) returns None.
4. Zero-excess path: when dnp_excess <= 0 the seesaw_score is exactly 0.0.
"""
from __future__ import annotations

import datetime as _dt
import sys
import os

# Make project root importable (NBA_OFFLINE=1 suppresses live fetches)
os.environ.setdefault("NBA_OFFLINE", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from signals.usage_seesaw import (  # noqa: E402
    UsageSeesawSignal,
    _DNP_LOOKUP_CACHE,
    _ADV_LOOKUP_CACHE,
    _LEAGUE_MEAN_USAGE,
    _MAX_DNP_EXCESS,
    _ATLAS_BLEND,
)
from src.loop.signal import AsOfContext  # noqa: E402
from src.loop.store import PointInTimeStore, entity_key  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    *,
    player_id: int = 1628983,
    team: str = "OKC",
    game_date: str = "2026-01-15",
    decision_time: _dt.datetime | None = None,
) -> AsOfContext:
    """Build a minimal pregame context for testing."""
    if decision_time is None:
        decision_time = _dt.datetime(2026, 1, 15, 10, 0, 0)
    return AsOfContext(
        decision_time=decision_time,
        player_id=player_id,
        team=team,
        game_date=game_date,
        scope="pregame",
    )


def _inject_dnp_cache(
    team: str,
    date_iso: str,
    dnp_count: float,
    dnp_l5: float,
) -> None:
    """Directly inject a DNP row into the module-level cache for isolation."""
    import signals.usage_seesaw as _mod

    if _mod._DNP_LOOKUP_CACHE is None:
        _mod._DNP_LOOKUP_CACHE = {}
    _mod._DNP_LOOKUP_CACHE[(date_iso, team)] = {
        "dnp_count_in_game": dnp_count,
        "dnp_count_l5_avg":  dnp_l5,
    }


def _inject_adv_cache(player_id: int, date_iso: str, usage: float) -> None:
    """Directly inject an advanced-splits usage row into the module-level cache."""
    import signals.usage_seesaw as _mod

    if _mod._ADV_LOOKUP_CACHE is None:
        _mod._ADV_LOOKUP_CACHE = {}
    _mod._ADV_LOOKUP_CACHE[(player_id, date_iso)] = usage


# ---------------------------------------------------------------------------
# Test 1: Leak-safety assertion
# ---------------------------------------------------------------------------

def test_leak_safety_future_atlas_not_used() -> None:
    """A future-stamped atlas record MUST NOT influence the build result.

    The store's read is gated by as_of <= decision_time. We write a
    ``absence_impact`` record stamped one day AFTER the decision_time and
    verify that the returned seesaw_score equals the parquet-only calculation
    (no atlas blend applied).
    """
    import tempfile, pathlib
    import signals.usage_seesaw as _mod

    DATE = "2025-11-01"
    PID = 9001
    TEAM = "TST"

    # Set up the in-memory caches with controlled values
    _inject_dnp_cache(TEAM, DATE, dnp_count=2.0, dnp_l5=0.5)   # excess = 1.5
    _inject_adv_cache(PID, DATE, usage=0.20)

    # Build a temporary store
    with tempfile.TemporaryDirectory() as tmp:
        store = PointInTimeStore(store_dir=tmp, autoload=False)

        # Write a FUTURE atlas record with a large learned lift
        future_time = _dt.datetime(2025, 11, 2, 12, 0, 0)  # one day AFTER
        store.write_atlas(
            "player", PID, "absence_impact", future_time,
            data={"usage_lift_per_dnp": 0.99},   # huge value; must be ignored
            provenance={"source": "test", "n": 100, "confidence": "high"},
        )

        # Decision time is before the future write
        decision_time = _dt.datetime(2025, 11, 1, 10, 0, 0)
        ctx = _make_ctx(
            player_id=PID, team=TEAM, game_date=DATE,
            decision_time=decision_time,
        )
        signal = UsageSeesawSignal(store=store)
        result = signal.build(ctx)

    assert result is not None, "build() returned None unexpectedly"
    assert isinstance(result, dict)

    # The FUTURE atlas was NOT applied, so seesaw_score must match pure parquet math.
    # dnp_excess = 2.0 - 0.5 = 1.5 → clipped to min(1.5, 4.0) = 1.5
    # usage_baseline (no atlas) = 0.20
    # seesaw_score = 1.5 * 0.20 = 0.30
    expected_score = round(min(1.5, _MAX_DNP_EXCESS) * 0.20, 4)
    assert abs(result["seesaw_score"] - expected_score) < 1e-6, (
        f"Expected seesaw_score {expected_score}, got {result['seesaw_score']}. "
        f"Future atlas value appears to have leaked into build()."
    )


# ---------------------------------------------------------------------------
# Test 2: Value-sanity assertion
# ---------------------------------------------------------------------------

def test_value_sanity_known_inputs() -> None:
    """With controlled DNP excess and usage, the seesaw_score is deterministic.

    dnp_count_in_game=3, dnp_l5_avg=1.0 → dnp_excess=2.0
    usage_baseline=0.25
    seesaw_score = clip(2.0, 0, 4) * 0.25 = 0.5
    """
    DATE = "2025-12-10"
    PID = 9002
    TEAM = "VAL"

    _inject_dnp_cache(TEAM, DATE, dnp_count=3.0, dnp_l5=1.0)   # excess = 2.0
    _inject_adv_cache(PID, DATE, usage=0.25)

    ctx = _make_ctx(
        player_id=PID, team=TEAM, game_date=DATE,
        decision_time=_dt.datetime(2025, 12, 10, 10, 0, 0),
    )
    signal = UsageSeesawSignal(store=None)  # no store → no atlas blend
    result = signal.build(ctx)

    assert result is not None, "build() returned None for valid context"
    assert isinstance(result, dict)
    assert set(result.keys()) == {"dnp_excess", "usage_baseline", "seesaw_score"}

    assert abs(result["dnp_excess"] - 2.0) < 1e-6, (
        f"dnp_excess expected 2.0, got {result['dnp_excess']}"
    )
    assert abs(result["usage_baseline"] - 0.25) < 1e-6, (
        f"usage_baseline expected 0.25, got {result['usage_baseline']}"
    )
    expected_score = round(2.0 * 0.25, 4)
    assert abs(result["seesaw_score"] - expected_score) < 1e-6, (
        f"seesaw_score expected {expected_score}, got {result['seesaw_score']}"
    )

    # Validate_output should also pass
    assert signal.validate_output(result), "validate_output failed for known-good dict"


# ---------------------------------------------------------------------------
# Test 3: None-path — missing required context fields
# ---------------------------------------------------------------------------

def test_none_when_team_missing() -> None:
    """Returns None when ctx.team is absent."""
    ctx = AsOfContext(
        decision_time=_dt.datetime(2025, 12, 1, 10, 0, 0),
        player_id=1234,
        team=None,          # missing
        game_date="2025-12-01",
    )
    result = UsageSeesawSignal(store=None).build(ctx)
    assert result is None, f"Expected None, got {result}"


def test_none_when_player_id_missing() -> None:
    """Returns None when ctx.player_id is absent."""
    ctx = AsOfContext(
        decision_time=_dt.datetime(2025, 12, 1, 10, 0, 0),
        player_id=None,     # missing
        team="BOS",
        game_date="2025-12-01",
    )
    result = UsageSeesawSignal(store=None).build(ctx)
    assert result is None, f"Expected None, got {result}"


def test_none_when_game_date_missing() -> None:
    """Returns None when ctx.game_date is absent."""
    ctx = AsOfContext(
        decision_time=_dt.datetime(2025, 12, 1, 10, 0, 0),
        player_id=1234,
        team="BOS",
        game_date=None,     # missing
    )
    result = UsageSeesawSignal(store=None).build(ctx)
    assert result is None, f"Expected None, got {result}"


# ---------------------------------------------------------------------------
# Test 4: Zero-excess path — no unusual absences → seesaw_score == 0.0
# ---------------------------------------------------------------------------

def test_zero_seesaw_when_no_excess() -> None:
    """When dnp_excess <= 0 (fewer absences than usual), seesaw_score is 0.

    dnp_count_in_game=1, dnp_l5_avg=2.0 → dnp_excess=-1.0 → clipped to 0.
    seesaw_score = 0 * usage = 0.0
    """
    DATE = "2025-11-20"
    PID = 9003
    TEAM = "ZRX"

    _inject_dnp_cache(TEAM, DATE, dnp_count=1.0, dnp_l5=2.0)   # excess = -1.0
    _inject_adv_cache(PID, DATE, usage=0.22)

    ctx = _make_ctx(
        player_id=PID, team=TEAM, game_date=DATE,
        decision_time=_dt.datetime(2025, 11, 20, 10, 0, 0),
    )
    result = UsageSeesawSignal(store=None).build(ctx)

    assert result is not None
    assert result["seesaw_score"] == 0.0, (
        f"Expected seesaw_score 0.0 on negative excess, got {result['seesaw_score']}"
    )
    assert result["dnp_excess"] < 0, (
        f"Expected negative dnp_excess, got {result['dnp_excess']}"
    )


# ---------------------------------------------------------------------------
# Test 5: hypothesis() returns the correct Hypothesis metadata
# ---------------------------------------------------------------------------

def test_hypothesis_metadata() -> None:
    """hypothesis() returns a well-formed Hypothesis for the gate."""
    from src.loop.signal import Hypothesis, TARGETS, SCOPES

    sig = UsageSeesawSignal(store=None)
    h = sig.hypothesis()

    assert isinstance(h, Hypothesis)
    assert h.name == "usage_seesaw"
    assert h.target in TARGETS
    assert h.scope in SCOPES
    assert h.target == "pts"
    assert h.scope == "pregame"
    assert "absence_impact" in h.atlas_fields
    assert h.source == "seed"
    assert h.statement and len(h.statement) > 20
    assert h.rationale and len(h.rationale) > 20


# ---------------------------------------------------------------------------
# Test 6: feature_names() contract
# ---------------------------------------------------------------------------

def test_feature_names() -> None:
    """feature_names() returns the three namespaced sub-feature columns."""
    sig = UsageSeesawSignal(store=None)
    names = sig.feature_names()
    assert names == [
        "usage_seesaw__dnp_excess",
        "usage_seesaw__usage_baseline",
        "usage_seesaw__seesaw_score",
    ], f"Unexpected feature_names: {names}"


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_leak_safety_future_atlas_not_used()
    print("PASS test_leak_safety_future_atlas_not_used")

    test_value_sanity_known_inputs()
    print("PASS test_value_sanity_known_inputs")

    test_none_when_team_missing()
    test_none_when_player_id_missing()
    test_none_when_game_date_missing()
    print("PASS None-path tests")

    test_zero_seesaw_when_no_excess()
    print("PASS test_zero_seesaw_when_no_excess")

    test_hypothesis_metadata()
    print("PASS test_hypothesis_metadata")

    test_feature_names()
    print("PASS test_feature_names")

    print("\nAll tests passed.")
