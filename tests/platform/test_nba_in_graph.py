"""tests.platform.test_nba_in_graph — Guard: NBA wired into graph machinery.

Asserts:
  1. base_rates._SPORT_SPECS includes "nba_espn" entry.
  2. calibration_segments._SPORT_SPECS includes "nba_espn" entry.
  3. adapter_interface_spec.ADAPTER_REGISTRY includes "basketball_nba" key.

Design: import-only (no corpus reads, no vault rebuild).  F5-clean.  < 50 LOC.
"""
from __future__ import annotations


def _sport_ids(spec_list: list) -> list:
    """Extract sport_id (first element) from each tuple in _SPORT_SPECS."""
    return [entry[0] for entry in spec_list]


# ---------------------------------------------------------------------------
# Test 1 — base_rates wiring
# ---------------------------------------------------------------------------

def test_base_rates_includes_nba_espn() -> None:
    """base_rates._SPORT_SPECS must contain nba_espn so NBA can't silently drop out."""
    from scripts.platformkit.atlas.base_rates import _SPORT_SPECS
    ids = _sport_ids(_SPORT_SPECS)
    assert "nba_espn" in ids, (
        f"nba_espn missing from base_rates._SPORT_SPECS; found: {ids}"
    )


# ---------------------------------------------------------------------------
# Test 2 — calibration_segments wiring
# ---------------------------------------------------------------------------

def test_calibration_segments_includes_nba_espn() -> None:
    """calibration_segments._SPORT_SPECS must contain nba_espn."""
    from scripts.platformkit.atlas.calibration_segments import _SPORT_SPECS
    ids = _sport_ids(_SPORT_SPECS)
    assert "nba_espn" in ids, (
        f"nba_espn missing from calibration_segments._SPORT_SPECS; found: {ids}"
    )


# ---------------------------------------------------------------------------
# Test 3 — adapter registry wiring
# ---------------------------------------------------------------------------

def test_adapter_registry_includes_basketball_nba() -> None:
    """ADAPTER_REGISTRY must carry basketball_nba so the NBAAdapter stays in scope."""
    from scripts.platformkit.adapter_interface_spec import ADAPTER_REGISTRY
    assert "basketball_nba" in ADAPTER_REGISTRY, (
        f"basketball_nba missing from ADAPTER_REGISTRY; found: {list(ADAPTER_REGISTRY.keys())}"
    )


# ---------------------------------------------------------------------------
# Test 4 — adapter entry points to correct module + class
# ---------------------------------------------------------------------------

def test_adapter_registry_nba_entry_points_to_nba_adapter() -> None:
    """ADAPTER_REGISTRY['basketball_nba'] must resolve to NBAAdapter."""
    from scripts.platformkit.adapter_interface_spec import ADAPTER_REGISTRY
    module_path, class_name = ADAPTER_REGISTRY["basketball_nba"]
    assert "basketball_nba" in module_path, (
        f"Expected basketball_nba in module path; got {module_path!r}"
    )
    assert class_name == "NBAAdapter", (
        f"Expected class_name='NBAAdapter'; got {class_name!r}"
    )
