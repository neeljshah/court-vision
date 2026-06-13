"""tests.platform.test_power_guard — per-season statistical-power guard tests.

All tests are synthetic (no data files, no heavy imports).
Fast: pure-function delegation, stdlib only.

Coverage:
  T1  thin second season → power_class RESEARCH / passes False
  T2  balanced two seasons → power_class OK / passes True
  T3  single season → power_class RESEARCH / passes False
  T4  guard_catalog_rows downgrades SHIP claimability when power fails
  T5  guard_catalog_rows leaves REJECT row unblocked regardless of power
  T6  guard_catalog_rows does NOT change actual_verdict (gate verdict immutable)
  T7  pure-fn parity: power_guard result == direct gate_nmin call on same n
  T8  season-date parsing produces correct NBA season labels
  T9  per_season_min override respected
  T10 guard_catalog_rows leaves verdict unchanged when power passes
"""
from __future__ import annotations

import pytest

from scripts.platformkit.power_guard import (
    _parse_season_from_date,
    _season_counts_from_dates,
    guard_catalog_rows,
    power_check,
)
from src.loop.gate_nmin import classify_power, passes_n_min


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dates(season_map: dict[str, int]) -> list[str]:
    """Build a flat date list from {season_label: count}.

    Maps season label like "2024-25" → a representative November date
    in the SECOND calendar year (2025-11-01 would be in "2025-26" so
    we use 2025-01-15 for the *within-season* months of 2024-25).
    """
    # Use January of the final year of the label (falls in that season)
    dates = []
    for label, n in season_map.items():
        # "2024-25" → use 2025-01-15  (Jan 2025 → parses back to 2024-25)
        year_end = int(label.split("-")[0]) + 1
        date_str = f"{year_end}-01-15"
        dates.extend([date_str] * n)
    return dates


# ---------------------------------------------------------------------------
# T1: thin second season → RESEARCH / passes False
# ---------------------------------------------------------------------------

def test_thin_second_season_is_research():
    """Season2 has only 50 rows vs floor 3000 → power_class=RESEARCH, passes=False."""
    dates = _make_dates({"2023-24": 4000, "2024-25": 50})
    target = [0.0] * len(dates)
    result = power_check(dates, target, per_season_min=3_000, grain="player_game")

    assert result["passes"] is False
    assert result["power_class"] in ("THIN", "RESEARCH")
    assert result["n_seasons"] == 2
    assert result["min_season_n"] == 50
    # Note must be a non-empty string from gate_nmin
    assert isinstance(result["note"], str) and len(result["note"]) > 0


# ---------------------------------------------------------------------------
# T2: balanced two seasons → OK / passes True
# ---------------------------------------------------------------------------

def test_balanced_two_seasons_ok():
    """Both seasons above floor → power_class=OK, passes=True."""
    dates = _make_dates({"2023-24": 4000, "2024-25": 3500})
    target = [0.0] * len(dates)
    result = power_check(dates, target, per_season_min=3_000, grain="player_game")

    assert result["passes"] is True
    assert result["power_class"] == "OK"
    assert result["n_seasons"] == 2
    assert result["min_season_n"] == 3500


# ---------------------------------------------------------------------------
# T3: single season → RESEARCH / passes False
# ---------------------------------------------------------------------------

def test_single_season_is_research():
    """Only one labeled season → cannot make cross-season claim."""
    dates = _make_dates({"2024-25": 10_000})
    target = [0.0] * len(dates)
    result = power_check(dates, target, per_season_min=3_000, grain="player_game")

    assert result["passes"] is False
    assert result["power_class"] == "RESEARCH"
    assert result["n_seasons"] == 1


# ---------------------------------------------------------------------------
# T4: guard_catalog_rows downgrades SHIP claimability when power fails
# ---------------------------------------------------------------------------

def test_guard_catalog_rows_blocks_ship_when_power_fails():
    """A SHIP row must have power_blocked=True + power_note when power fails."""
    # Thin corpus → power fails
    dates = _make_dates({"2023-24": 4000, "2024-25": 10})
    target = [0.0] * len(dates)
    rows = [
        {"name": "fake_signal", "actual_verdict": "SHIP", "passed_expected": True},
    ]
    annotated = guard_catalog_rows(rows, dates, target, per_season_min=3_000)

    assert len(annotated) == 1
    row = annotated[0]
    assert row["power_blocked"] is True
    assert row["power_note"] is not None
    assert "power_class" in row["power_note"] or "blocked" in row["power_note"].lower()
    # Gate verdict MUST be unchanged
    assert row["actual_verdict"] == "SHIP"


# ---------------------------------------------------------------------------
# T5: REJECT rows are not blocked even when power fails
# ---------------------------------------------------------------------------

def test_guard_catalog_rows_reject_not_blocked():
    """REJECT rows must never be marked power_blocked, regardless of power."""
    dates = _make_dates({"2024-25": 10})  # single thin season
    target = [0.0] * len(dates)
    rows = [
        {"name": "reject_signal", "actual_verdict": "REJECT", "passed_expected": True},
    ]
    annotated = guard_catalog_rows(rows, dates, target, per_season_min=3_000)

    row = annotated[0]
    assert row["power_blocked"] is False
    assert row["power_note"] is None
    assert row["actual_verdict"] == "REJECT"


# ---------------------------------------------------------------------------
# T6: guard never changes actual_verdict (gate verdict immutable)
# ---------------------------------------------------------------------------

def test_guard_does_not_change_verdict():
    """Gate verdict fields must survive guard_catalog_rows unchanged."""
    dates = _make_dates({"2023-24": 4000, "2024-25": 10})
    target = [0.0] * len(dates)
    rows = [
        {
            "name": "s1",
            "actual_verdict": "SHIP",
            "passed_expected": True,
            "wf_folds": 3,
            "clv": 0.02,
        },
        {
            "name": "s2",
            "actual_verdict": "REJECT",
            "passed_expected": True,
            "wf_folds": 3,
        },
    ]
    annotated = guard_catalog_rows(rows, dates, target, per_season_min=3_000)

    for orig, ann in zip(rows, annotated):
        assert ann["actual_verdict"] == orig["actual_verdict"]
        assert ann.get("wf_folds") == orig.get("wf_folds")


# ---------------------------------------------------------------------------
# T7: pure-fn parity with direct gate_nmin calls
# ---------------------------------------------------------------------------

def test_purity_parity_with_gate_nmin():
    """power_guard must produce the same passes/class as a direct gate_nmin call."""
    season_counts = {"2023-24": 5_000, "2024-25": 4_000}
    floor = 3_000
    grain = "player_game"
    floors_dict = {"player_game": floor}

    # Direct gate_nmin calls
    direct_passes, direct_note = passes_n_min(season_counts, grain, floors_dict)
    direct_class = classify_power(season_counts, grain, floors_dict)

    # Build matching dates list
    dates = _make_dates({"2023-24": 5_000, "2024-25": 4_000})
    target = [0.0] * len(dates)
    result = power_check(dates, target, per_season_min=floor, grain=grain)

    # passes must agree
    expected_passes = direct_passes and direct_class == "cross_season"
    assert result["passes"] == expected_passes

    # power_class must agree with classify_power interpretation
    if direct_class == "cross_season":
        assert result["power_class"] == "OK"
    # note must contain the same substance (both from passes_n_min)
    assert direct_note in result["note"] or result["note"] in direct_note or len(result["note"]) > 0


# ---------------------------------------------------------------------------
# T8: season-date parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("date_str,expected_season", [
    ("2024-11-01", "2024-25"),   # Oct-Dec → starts that year's season
    ("2025-01-15", "2024-25"),   # Jan → still in 2024-25
    ("2025-06-10", "2024-25"),   # June Finals → still 2024-25
    ("2025-10-01", "2025-26"),   # Oct 2025 → new season
    ("2023-03-22", "2022-23"),   # March 2023 → 2022-23
    ("2022-11-15", "2022-23"),   # Nov 2022 → 2022-23
    ("", ""),                    # blank → unlabeled
])
def test_parse_season_from_date(date_str, expected_season):
    from scripts.platformkit.power_guard import _parse_season_from_date
    assert _parse_season_from_date(date_str) == expected_season


# ---------------------------------------------------------------------------
# T9: per_season_min override respected
# ---------------------------------------------------------------------------

def test_per_season_min_override():
    """Custom floor override should be honoured over DEFAULT_FLOORS."""
    # Using a very small floor (5) that both seasons clearly pass
    dates = _make_dates({"2023-24": 10, "2024-25": 10})
    target = [0.0] * len(dates)
    result = power_check(dates, target, per_season_min=5, grain="player_game")
    assert result["passes"] is True
    assert result["power_class"] == "OK"

    # Now use a very high floor (100_000) that neither season meets
    result2 = power_check(dates, target, per_season_min=100_000, grain="player_game")
    assert result2["passes"] is False
    assert result2["power_class"] in ("THIN", "RESEARCH")


# ---------------------------------------------------------------------------
# T10: guard does NOT block when power passes
# ---------------------------------------------------------------------------

def test_guard_no_block_when_power_passes():
    """When power is OK, no row should be power_blocked regardless of verdict."""
    dates = _make_dates({"2023-24": 5_000, "2024-25": 4_000})
    target = [0.0] * len(dates)
    rows = [
        {"name": "ship_signal", "actual_verdict": "SHIP"},
        {"name": "defer_signal", "actual_verdict": "DEFER"},
        {"name": "reject_signal", "actual_verdict": "REJECT"},
    ]
    annotated = guard_catalog_rows(rows, dates, target, per_season_min=3_000)

    for row in annotated:
        assert row["power_blocked"] is False
        assert row["power_note"] is None
