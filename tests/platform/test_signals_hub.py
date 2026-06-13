"""test_signals_hub.py — Unit tests for signals_hub.build_signals_hub.

Uses a synthetic vault/Sports tree in tmp_path so no real vault is touched.
Single-process; safe for --timeout=120.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from scripts.platform.atlas.signals_hub import build_signals_hub

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_catalog(base: pathlib.Path, sport: str, table_rows: list[tuple[str, str]]) -> None:
    """Create vault/Sports/<sport>/Signals/_Catalog.md with given (signal, actual) rows."""
    sport_signals_dir = base / sport / "Signals"
    sport_signals_dir.mkdir(parents=True, exist_ok=True)

    rows = "\n".join(
        f"| {sig} | REJECT | {actual} | YES | 1000 | 1.0 | reason |"
        for sig, actual in table_rows
    )
    content = textwrap.dedent(f"""\
        # Honest signal catalog — markets are efficient; expected and observed verdicts are REJECT/DEFER. NO edge claimed.

        Generated: 2026-06-13T00:00:00Z  Signals: {len(table_rows)}

        ## Verdict table

        | Signal | Expected | Actual | Passed | N | Coverage | Reason |
        |--------|----------|--------|--------|---|----------|--------|
        {rows}

        ## Gate detail

        ---
        _PRIVATE research. No edge claimed. REJECT = honest success._
    """)
    (sport_signals_dir / "_Catalog.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def synthetic_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    """Two sports with catalogs; one sport dir without a catalog (graceful-skip)."""
    # Tennis: 7 REJECT
    _make_catalog(tmp_path, "Tennis", [
        ("tennis_abs_rest_diff", "REJECT"),
        ("tennis_surf_vs_overall_elo", "REJECT"),
        ("tennis_elo_gap_magnitude", "REJECT"),
        ("tennis_best_of_5", "REJECT"),
        ("tennis_rest_surface_interaction", "REJECT"),
        ("tennis_surf_specialist_flag", "REJECT"),
        ("tennis_signed_rest_diff", "REJECT"),
    ])
    # Soccer: 3 REJECT, 1 DEFER, 1 VARIANCE_ONLY
    _make_catalog(tmp_path, "Soccer", [
        ("soccer_goal_diff_elo", "REJECT"),
        ("soccer_home_advantage", "REJECT"),
        ("soccer_league_strength", "REJECT"),
        ("soccer_form_streak", "DEFER"),
        ("soccer_shot_volume", "VARIANCE_ONLY"),
    ])
    # Basketball_NBA: directory exists but NO Signals/_Catalog.md → graceful-skip
    (tmp_path / "Basketball_NBA").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture()
def vault_with_ship(tmp_path: pathlib.Path) -> pathlib.Path:
    """Sport with a SHIP verdict to test the artifact-hunt warning."""
    _make_catalog(tmp_path, "MLB", [
        ("mlb_run_diff", "REJECT"),
        ("mlb_starter_elo", "SHIP"),
    ])
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildSignalsHub:

    def test_output_file_created(self, synthetic_vault: pathlib.Path) -> None:
        out = build_signals_hub(synthetic_vault)
        assert out.exists(), "_Signals_Hub.md was not created"
        assert out.name == "_Signals_Hub.md"
        assert out.parent == synthetic_vault

    def test_per_sport_reject_counts_correct(self, synthetic_vault: pathlib.Path) -> None:
        build_signals_hub(synthetic_vault)
        text = (synthetic_vault / "_Signals_Hub.md").read_text(encoding="utf-8")

        # Tennis row: 7 candidates, 7 REJECT
        assert "Tennis" in text
        lines = text.splitlines()
        tennis_row = next((l for l in lines if l.startswith("| Tennis")), None)
        assert tennis_row is not None, "Tennis row missing from table"
        cells = [c.strip() for c in tennis_row.split("|") if c.strip()]
        # cells: [Sport, #Candidates, #REJECT, #DEFER, #VARIANCE_ONLY, #SHIP, Catalog]
        assert cells[1] == "7", f"Tennis candidates wrong: {tennis_row}"
        assert cells[2] == "7", f"Tennis REJECT count wrong: {tennis_row}"
        assert cells[3] == "0", f"Tennis DEFER count wrong: {tennis_row}"

    def test_per_sport_defer_and_variance_only(self, synthetic_vault: pathlib.Path) -> None:
        build_signals_hub(synthetic_vault)
        text = (synthetic_vault / "_Signals_Hub.md").read_text(encoding="utf-8")
        lines = text.splitlines()
        soccer_row = next((l for l in lines if l.startswith("| Soccer")), None)
        assert soccer_row is not None, "Soccer row missing from table"
        cells = [c.strip() for c in soccer_row.split("|") if c.strip()]
        assert cells[1] == "5", f"Soccer candidates wrong: {soccer_row}"
        assert cells[2] == "3", f"Soccer REJECT count wrong: {soccer_row}"
        assert cells[3] == "1", f"Soccer DEFER count wrong: {soccer_row}"
        assert cells[4] == "1", f"Soccer VARIANCE_ONLY count wrong: {soccer_row}"

    def test_grand_total_row(self, synthetic_vault: pathlib.Path) -> None:
        build_signals_hub(synthetic_vault)
        text = (synthetic_vault / "_Signals_Hub.md").read_text(encoding="utf-8")
        lines = text.splitlines()
        total_row = next((l for l in lines if "TOTAL" in l), None)
        assert total_row is not None, "Grand TOTAL row missing"
        # 7 Tennis + 5 Soccer = 12 candidates total
        assert "12" in total_row, f"Grand total 12 not found in: {total_row}"
        # 7+3 = 10 REJECT total
        cells = [c.strip() for c in total_row.split("|") if c.strip()]
        assert cells[2] == "**10**", f"Grand REJECT count wrong: {total_row}"

    def test_missing_catalog_sport_skipped(self, synthetic_vault: pathlib.Path) -> None:
        """Basketball_NBA has no Signals/_Catalog.md — must be silently skipped."""
        build_signals_hub(synthetic_vault)
        text = (synthetic_vault / "_Signals_Hub.md").read_text(encoding="utf-8")
        lines = text.splitlines()
        # No table row should start with "| Basketball_NBA"
        nba_rows = [l for l in lines if l.startswith("| Basketball_NBA")]
        assert not nba_rows, f"Basketball_NBA should be skipped but found: {nba_rows}"

    def test_no_exception_on_missing_catalog(self, tmp_path: pathlib.Path) -> None:
        """Directory with no sports at all should not raise, just write an empty hub."""
        (tmp_path / "EmptySport").mkdir()
        out = build_signals_hub(tmp_path)
        assert out.exists()
        text = out.read_text(encoding="utf-8")
        assert "0" in text or "No per-sport" in text

    def test_frontmatter_tags(self, synthetic_vault: pathlib.Path) -> None:
        build_signals_hub(synthetic_vault)
        text = (synthetic_vault / "_Signals_Hub.md").read_text(encoding="utf-8")
        assert "signals" in text
        assert "edge-discovery" in text
        assert "meta" in text
        assert "honest" in text

    def test_hub_uplink(self, synthetic_vault: pathlib.Path) -> None:
        build_signals_hub(synthetic_vault)
        text = (synthetic_vault / "_Signals_Hub.md").read_text(encoding="utf-8")
        assert "[[_Hub]]" in text

    def test_wikilinks_to_catalogs(self, synthetic_vault: pathlib.Path) -> None:
        build_signals_hub(synthetic_vault)
        text = (synthetic_vault / "_Signals_Hub.md").read_text(encoding="utf-8")
        assert "[[Tennis/Signals/_Catalog]]" in text
        assert "[[Soccer/Signals/_Catalog]]" in text

    def test_honest_framing_present(self, synthetic_vault: pathlib.Path) -> None:
        build_signals_hub(synthetic_vault)
        text = (synthetic_vault / "_Signals_Hub.md").read_text(encoding="utf-8")
        assert "markets are efficient" in text.lower() or "efficient" in text
        assert "NO edge" in text or "No edge" in text or "no edge" in text.lower()
        assert "REJECT" in text

    def test_no_ship_warning_when_no_ship(self, synthetic_vault: pathlib.Path) -> None:
        """No SHIP verdicts → no artifact-hunt warning."""
        build_signals_hub(synthetic_vault)
        text = (synthetic_vault / "_Signals_Hub.md").read_text(encoding="utf-8")
        assert "ARTIFACT-HUNT REQUIRED" not in text

    def test_ship_warning_shown(self, vault_with_ship: pathlib.Path) -> None:
        """A SHIP verdict triggers the prominent artifact-hunt caveat."""
        build_signals_hub(vault_with_ship)
        text = (vault_with_ship / "_Signals_Hub.md").read_text(encoding="utf-8")
        assert "ARTIFACT-HUNT REQUIRED" in text
        assert "single-fold" in text.lower() or "Single-fold" in text

    def test_idempotent(self, synthetic_vault: pathlib.Path) -> None:
        """Running twice produces the same output without error."""
        out1 = build_signals_hub(synthetic_vault)
        out2 = build_signals_hub(synthetic_vault)
        assert out1 == out2
        text = out1.read_text(encoding="utf-8")
        assert text.count("## Per-Sport Signal Counts") == 1

    def test_missing_dir_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_signals_hub(tmp_path / "does_not_exist")
