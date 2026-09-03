"""Provenance-document rail for the NBA wall-clock join."""
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[3]
_MODULE = _ROOT / "scripts/platformkit/venue_history/nba_wallclock_join.py"
_PROVENANCE = _ROOT / "docs/evidence/harness/nba_wallclock_join_PROVENANCE.md"
_ITEMS = (
    "cdn.nba.com's liveData feed is WAF-BLOCKED here",
    "split is always at position 3",
    "outcome_home_win comes from the HOME-side ticker's own settled ``result`` field",
    "LATEST state with ts<=T, never future state (no leak)",
    "OUTPUT: data/cache/inplay_odds/nba_checkpoints_2025_26_playoffs.parquet",
)


def test_nba_wallclock_join_provenance_is_present_and_linked() -> None:
    provenance = _PROVENANCE.read_text(encoding="utf-8")
    module = _MODULE.read_text(encoding="utf-8")

    assert "333af3149fde92cca7b0b8dd95dae94fde97bafa" in provenance
    for item in _ITEMS:
        assert item in provenance
    assert "Provenance and invariants: docs/evidence/harness/nba_wallclock_join_PROVENANCE.md" in module
