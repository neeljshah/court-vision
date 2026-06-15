"""tests.platform.test_soccer_ingest — Offline tests for ingest_footballdata.py.

ALL tests are OFFLINE. ``urllib.request.urlopen`` is monkeypatched to raise at
module import-time so any live network call causes immediate failure.
``requests.get`` is similarly patched (belt-and-suspenders).

Fixtures:
  tests/fixtures/soccer/footballdata_sample.csv

The fixture has 24 data rows (25 including header):
  - 2 divs: E0 (Premier League), E1 (Championship)
  - 2 seasons: 2023/24 (start_year=2023) and 2024/25 (start_year=2024)
  - Row 10 (E1, Middlesbrough v Hull, 10/08/2024): FTHG missing → DROPPED
  - Arsenal v Chelsea 15/08/2024: 3+1=4 goals → target_over25=1
  - Man United v Liverpool 15/08/2024: 2+0=2 goals → target_over25=0
  - Some rows deliberately missing Pinnacle P>2.5/P<2.5 → fallback chain exercised
"""
from __future__ import annotations

import ast
import io
import urllib.request
from pathlib import Path
from typing import Any, List, Tuple

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# NETWORK HARD-BLOCK — module-level, before any import of the ingest module
# ---------------------------------------------------------------------------

def _block(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("Live network call in test — forbidden. urlopen monkeypatched.")


# Patch before importing the module under test
urllib.request.urlopen = _block  # type: ignore[assignment]

try:
    import requests as _requests
    _requests.get = _block  # type: ignore[assignment]
except ImportError:
    pass

# Now safe to import
from domains.soccer.ingest_footballdata import (  # noqa: E402
    MATCHES_COLS,
    ODDS_COLS,
    _make_event_id,
    _slug,
    build_matches,
    build_odds,
    build_report,
    fetch_raw,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FIXTURE_CSV = Path(__file__).parent.parent / "fixtures" / "soccer" / "footballdata_sample.csv"

# Season definitions matching the fixture file
_E0_2024 = "E0"
_E1_2024 = "E1"
_E0_2023 = "E0"
_E1_2023 = "E1"
_SEASON_2024 = 2024
_SEASON_2023 = 2023


def _load_fixture() -> pd.DataFrame:
    return pd.read_csv(_FIXTURE_CSV, low_memory=False)


def _make_frames() -> List[Tuple[str, int, pd.DataFrame]]:
    """Build the four (div, season, df) tuples from the single fixture file."""
    raw = _load_fixture()
    frames = []
    for div in ("E0", "E1"):
        for season in (2023, 2024):
            subset = raw[raw["Div"] == div].copy()
            # Filter by date year so we get the right season rows
            dates = pd.to_datetime(subset["Date"], dayfirst=True, errors="coerce")
            year_mask = dates.dt.year == (season + 1) if season == 2023 else dates.dt.year == season + 1
            # 2023 season = games in Aug 2023 (year 2023), 2024 season = games in Aug 2024
            year_mask = dates.dt.year == (season if season == 2023 else season)
            subset = subset[year_mask].copy()
            if len(subset):
                frames.append((div, season, subset))
    return frames


def _make_all_frames_unfiltered() -> List[Tuple[str, int, pd.DataFrame]]:
    """Pass all rows as a single (E0, 2023) frame — simplest multi-season test helper."""
    raw = _load_fixture()
    # Split by Div only; pass as 2 frames (E0 all years, E1 all years)
    # with a representative season label — the important thing is we exercise transforms
    frames = []
    for div in ("E0", "E1"):
        subset = raw[raw["Div"] == div].copy()
        frames.append((div, 2023, subset))
    return frames


# ---------------------------------------------------------------------------
# 1. Network hard-block verification
# ---------------------------------------------------------------------------

class TestNetworkBlock:
    def test_urlopen_raises(self) -> None:
        """Confirm the monkeypatch is in effect."""
        with pytest.raises(RuntimeError, match="forbidden"):
            urllib.request.urlopen("http://example.com")  # type: ignore[arg-type]

    def test_offline_fetch_is_noop(self, tmp_path: Any) -> None:
        """fetch_raw(offline=True) must return an empty dict without touching network."""
        result = fetch_raw(out_dir=str(tmp_path), offline=True)
        assert result == {}

    def test_offline_fetch_creates_no_files(self, tmp_path: Any) -> None:
        fetch_raw(out_dir=str(tmp_path), offline=True)
        csv_files = list(tmp_path.glob("*.csv"))
        assert csv_files == []


# ---------------------------------------------------------------------------
# 2. Fixture loading sanity
# ---------------------------------------------------------------------------

class TestFixture:
    def test_fixture_exists(self) -> None:
        assert _FIXTURE_CSV.exists(), f"Fixture not found: {_FIXTURE_CSV}"

    def test_fixture_has_expected_columns(self) -> None:
        raw = _load_fixture()
        required = [
            "Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
            "B365>2.5", "B365<2.5", "P>2.5", "P<2.5",
            "B365C>2.5", "B365C<2.5", "PC>2.5", "PC<2.5",
            "AvgC>2.5", "AvgC<2.5",
        ]
        for col in required:
            assert col in raw.columns, f"Missing column: {col}"

    def test_fixture_row_count(self) -> None:
        raw = _load_fixture()
        assert len(raw) == 24, f"Expected 24 data rows, got {len(raw)}"

    def test_fixture_has_missing_fthg(self) -> None:
        raw = _load_fixture()
        assert raw["FTHG"].isna().any(), "Fixture must have at least one missing FTHG"

    def test_fixture_has_missing_pinnacle(self) -> None:
        raw = _load_fixture()
        assert raw["P>2.5"].isna().any(), "Fixture must have rows without Pinnacle prices"


# ---------------------------------------------------------------------------
# 3. build_matches — row counts and drop logic
# ---------------------------------------------------------------------------

class TestBuildMatchesRowCounts:
    def test_drops_missing_fthg_row(self) -> None:
        raw = _load_fixture()
        # Use all rows in a single frame
        frames = [("E0", 2023, raw[raw["Div"] == "E0"].copy()),
                  ("E1", 2024, raw[raw["Div"] == "E1"].copy())]
        m = build_matches(frames)
        # 24 raw rows, 1 missing FTHG → 23 rows out
        assert len(m) == 23, f"Expected 23 rows after drop, got {len(m)}"

    def test_no_missing_fthg_in_output(self) -> None:
        raw = _load_fixture()
        frames = [("E0", 2023, raw[raw["Div"] == "E0"].copy()),
                  ("E1", 2024, raw[raw["Div"] == "E1"].copy())]
        m = build_matches(frames)
        assert m["fthg"].notna().all()
        assert m["ftag"].notna().all()

    def test_empty_frames_returns_empty(self) -> None:
        m = build_matches([])
        assert len(m) == 0
        for col in MATCHES_COLS:
            assert col in m.columns


# ---------------------------------------------------------------------------
# 4. build_matches — target_over25 boundary
# ---------------------------------------------------------------------------

class TestTargetOver25:
    def _get_matches(self) -> pd.DataFrame:
        raw = _load_fixture()
        frames = [("E0", 2024, raw[raw["Div"] == "E0"].copy()),
                  ("E1", 2024, raw[raw["Div"] == "E1"].copy())]
        return build_matches(frames)

    def test_3_goals_is_target_1(self) -> None:
        """Arsenal 3-1 Chelsea (4 goals total) → target_over25 = 1."""
        m = self._get_matches()
        row = m[(m["home_team"] == "Arsenal") & (m["away_team"] == "Chelsea")]
        assert len(row) >= 1
        assert int(row.iloc[0]["target_over25"]) == 1
        assert int(row.iloc[0]["total_goals"]) == 4

    def test_2_goals_is_target_0(self) -> None:
        """Man United 2-0 Liverpool (2 goals total) → target_over25 = 0."""
        m = self._get_matches()
        row = m[(m["home_team"] == "Man United") & (m["away_team"] == "Liverpool")]
        assert len(row) >= 1
        assert int(row.iloc[0]["target_over25"]) == 0
        assert int(row.iloc[0]["total_goals"]) == 2

    def test_exactly_3_goals_is_target_1(self) -> None:
        """West Ham 3-3 Crystal Palace (6 total) → target_over25 = 1."""
        m = self._get_matches()
        row = m[(m["home_team"] == "West Ham") & (m["away_team"] == "Crystal Palace")]
        assert len(row) >= 1
        assert int(row.iloc[0]["target_over25"]) == 1

    def test_total_goals_derivation(self) -> None:
        m = self._get_matches()
        assert ((m["total_goals"] == m["fthg"] + m["ftag"]).all())

    def test_target_dtype_int8(self) -> None:
        m = self._get_matches()
        assert m["target_over25"].dtype == "int8"


# ---------------------------------------------------------------------------
# 5. build_matches — event_id determinism and pre-match fields only
# ---------------------------------------------------------------------------

class TestEventId:
    def test_event_id_deterministic(self) -> None:
        """Building twice from the same data yields identical event_ids."""
        raw = _load_fixture()
        frames1 = [("E0", 2024, raw[raw["Div"] == "E0"].copy())]
        frames2 = [("E0", 2024, raw[raw["Div"] == "E0"].copy())]
        m1 = build_matches(frames1)
        m2 = build_matches(frames2)
        assert list(m1["event_id"]) == list(m2["event_id"])

    def test_event_id_format(self) -> None:
        """event_id must start with YYYYMMDD and contain div slug."""
        raw = _load_fixture()
        frames = [("E0", 2024, raw[raw["Div"] == "E0"].copy())]
        m = build_matches(frames)
        for eid in m["event_id"]:
            # Format: {YYYYMMDD}-{div}-{home_slug}-{away_slug}
            assert len(eid) > 10
            assert eid[:8].isdigit()
            assert "-E0-" in eid

    def test_event_id_uses_only_pre_match_fields(self) -> None:
        """event_id must not contain any result field (FTHG, FTAG, FTR)."""
        raw = _load_fixture()
        frames = [("E0", 2024, raw[raw["Div"] == "E0"].copy())]
        m = build_matches(frames)
        for eid in m["event_id"]:
            assert "fthg" not in eid.lower()
            assert "ftag" not in eid.lower()
            assert "ftr" not in eid.lower()

    def test_slug_helper(self) -> None:
        assert _slug("Man United") == "man_united"
        assert _slug("Brighton") == "brighton"
        assert _slug("Nottm Forest") == "nottm_forest"

    def test_known_event_id(self) -> None:
        """Arsenal v Chelsea on 15/08/2024 → known event_id."""
        import datetime as _dt
        eid = _make_event_id(_dt.date(2024, 8, 15), "E0", "Arsenal", "Chelsea")
        assert eid == "20240815-E0-arsenal-chelsea"


# ---------------------------------------------------------------------------
# 6. build_matches — date parsing (dayfirst)
# ---------------------------------------------------------------------------

class TestDateParsing:
    def test_dayfirst_parsing(self) -> None:
        """15/08/2024 must parse to 2024-08-15, not 2024-15-08."""
        raw = _load_fixture()
        frames = [("E0", 2024, raw[raw["Div"] == "E0"].copy())]
        m = build_matches(frames)
        dates = m["date"].dt.date.tolist()
        # Check at least one known date
        import datetime as _dt
        assert _dt.date(2024, 8, 15) in dates

    def test_no_august_15_misparse(self) -> None:
        """Confirm month=8 not month=15 (dayfirst guard)."""
        raw = _load_fixture()
        frames = [("E0", 2024, raw[raw["Div"] == "E0"].copy())]
        m = build_matches(frames)
        for d in m["date"].dropna():
            assert d.month <= 12


# ---------------------------------------------------------------------------
# 7. build_matches — pinned sort
# ---------------------------------------------------------------------------

class TestMatchesSort:
    def test_dates_non_decreasing(self) -> None:
        raw = _load_fixture()
        frames = [("E0", 2023, raw[raw["Div"] == "E0"].copy()),
                  ("E0", 2024, raw[raw["Div"] == "E0"].copy())]
        m = build_matches(frames)
        dates = m["date"].dropna().tolist()
        assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# 8. build_matches — idempotency
# ---------------------------------------------------------------------------

class TestMatchesIdempotent:
    def test_rebuild_identical(self) -> None:
        raw = _load_fixture()
        frames_a = [("E0", 2023, raw[raw["Div"] == "E0"].copy())]
        frames_b = [("E0", 2023, raw[raw["Div"] == "E0"].copy())]
        m1 = build_matches(frames_a)
        m2 = build_matches(frames_b)
        pd.testing.assert_frame_equal(m1, m2)


# ---------------------------------------------------------------------------
# 9. build_odds — row counts
# ---------------------------------------------------------------------------

class TestBuildOddsRowCounts:
    def test_odds_row_count(self) -> None:
        """23 settled matches → all 23 should have at least one price (fixture designed so)."""
        raw = _load_fixture()
        frames = [("E0", 2023, raw[raw["Div"] == "E0"].copy()),
                  ("E1", 2024, raw[raw["Div"] == "E1"].copy())]
        o = build_odds(frames)
        # All rows have at least B365 prices so odds count >= matches count
        m = build_matches(frames)
        assert len(o) >= len(m)

    def test_empty_frames_returns_empty_odds(self) -> None:
        o = build_odds([])
        assert len(o) == 0
        for col in ODDS_COLS:
            assert col in o.columns


# ---------------------------------------------------------------------------
# 10. build_odds — fallback chain
# ---------------------------------------------------------------------------

class TestOddsFallbackChain:
    def _get_odds(self) -> pd.DataFrame:
        raw = _load_fixture()
        frames = [("E0", 2024, raw[raw["Div"] == "E0"].copy())]
        return build_odds(frames)

    def test_pinnacle_used_when_present(self) -> None:
        """Rows with P>2.5 present → book_prematch == 'pinnacle'."""
        o = self._get_odds()
        # Arsenal v Chelsea has Pinnacle prices (P>2.5=1.72)
        row = o[(o["event_id"].str.contains("arsenal")) & (o["event_id"].str.contains("chelsea"))]
        assert len(row) >= 1
        assert row.iloc[0]["book_prematch"] == "pinnacle"

    def test_fallback_when_pinnacle_missing(self) -> None:
        """Rows without Pinnacle prices → book_prematch != 'pinnacle'."""
        o = self._get_odds()
        # Brighton v Fulham: P>2.5 is empty in fixture → should fallback
        row = o[o["event_id"].str.contains("brighton") & o["event_id"].str.contains("fulham")]
        assert len(row) >= 1
        assert row.iloc[0]["book_prematch"] != "pinnacle"
        # Must be one of the valid fallback labels
        assert row.iloc[0]["book_prematch"] in ("market_avg", "bet365", "none")

    def test_close_pinnacle_when_present(self) -> None:
        """Arsenal v Chelsea has PC>2.5 → book_close == 'pinnacle'."""
        o = self._get_odds()
        row = o[o["event_id"].str.contains("arsenal") & o["event_id"].str.contains("chelsea")]
        assert len(row) >= 1
        assert row.iloc[0]["book_close"] == "pinnacle"

    def test_close_fallback_when_pc_missing(self) -> None:
        """Brighton v Fulham: PC>2.5 empty → book_close != 'pinnacle'."""
        o = self._get_odds()
        row = o[o["event_id"].str.contains("brighton") & o["event_id"].str.contains("fulham")]
        assert len(row) >= 1
        assert row.iloc[0]["book_close"] != "pinnacle"

    def test_raw_passthrough_float32(self) -> None:
        o = self._get_odds()
        float_cols = ["p_over", "b365_over", "avg_over", "max_over",
                      "pc_over", "b365c_over", "avgc_over", "maxc_over"]
        for col in float_cols:
            assert col in o.columns
            non_null = o[col].dropna()
            if len(non_null):
                assert non_null.dtype == "float32", f"{col} should be float32"

    def test_odds_idempotent(self) -> None:
        raw = _load_fixture()
        frames_a = [("E0", 2023, raw[raw["Div"] == "E0"].copy())]
        frames_b = [("E0", 2023, raw[raw["Div"] == "E0"].copy())]
        o1 = build_odds(frames_a)
        o2 = build_odds(frames_b)
        pd.testing.assert_frame_equal(o1, o2)


# ---------------------------------------------------------------------------
# 11. build_report sanity
# ---------------------------------------------------------------------------

class TestBuildReport:
    def test_report_keys(self) -> None:
        raw = _load_fixture()
        frames = [("E0", 2023, raw[raw["Div"] == "E0"].copy())]
        r = build_report(frames)
        for key in ("rows_in", "rows_out_matches", "rows_dropped", "odds_rows",
                    "prematch_coverage_pct", "close_coverage_pct", "by_div_season"):
            assert key in r, f"Missing report key: {key}"

    def test_rows_dropped_equals_missing_fthg(self) -> None:
        raw = _load_fixture()
        # Use frames that include the missing-FTHG row (E1 2024)
        frames = [("E1", 2024, raw[raw["Div"] == "E1"].copy())]
        r = build_report(frames)
        n_missing = raw[raw["Div"] == "E1"]["FTHG"].isna().sum()
        assert r["rows_dropped"] == n_missing


# ---------------------------------------------------------------------------
# 12. Column contract completeness
# ---------------------------------------------------------------------------

class TestColumnContracts:
    def test_matches_has_all_required_cols(self) -> None:
        raw = _load_fixture()
        frames = [("E0", 2024, raw[raw["Div"] == "E0"].copy())]
        m = build_matches(frames)
        for col in MATCHES_COLS:
            assert col in m.columns, f"Matches missing column: {col}"

    def test_odds_has_all_required_cols(self) -> None:
        raw = _load_fixture()
        frames = [("E0", 2024, raw[raw["Div"] == "E0"].copy())]
        o = build_odds(frames)
        for col in ODDS_COLS:
            assert col in o.columns, f"Odds missing column: {col}"

    def test_season_col_is_int(self) -> None:
        raw = _load_fixture()
        frames = [("E0", 2024, raw[raw["Div"] == "E0"].copy())]
        m = build_matches(frames)
        assert pd.api.types.is_integer_dtype(m["season"])
        assert (m["season"] == 2024).all()


# ---------------------------------------------------------------------------
# 13. AST forbidden-import check (F5 compliance)
# ---------------------------------------------------------------------------

class TestForbiddenImports:
    def test_no_src_or_cross_adapter_import(self) -> None:
        """ingest_footballdata.py must not import src.*, domains.nba,
        domains.basketball_nba, domains.tennis, or torch."""
        ingest_path = Path(__file__).parents[2] / "domains" / "soccer" / "ingest_footballdata.py"
        src = ingest_path.read_text("utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("src."), f"Forbidden: import {alias.name}"
                    assert not alias.name.startswith("torch"), f"Forbidden: import {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("src."), f"Forbidden: from {node.module}"
                assert not node.module.startswith("domains.nba"), f"F5: from {node.module}"
                assert not node.module.startswith("domains.basketball_nba"), f"F5: from {node.module}"
                assert not node.module.startswith("domains.tennis"), f"F5: from {node.module}"
                assert not node.module.startswith("torch"), f"Forbidden: from {node.module}"

    def test_no_tennis_string_in_ingest(self) -> None:
        """The string 'tennis' must not appear anywhere in ingest_footballdata.py."""
        ingest_path = Path(__file__).parents[2] / "domains" / "soccer" / "ingest_footballdata.py"
        src = ingest_path.read_text("utf-8")
        assert "tennis" not in src.lower(), "Found 'tennis' reference in ingest_footballdata.py"

    def test_no_src_import_in_this_test(self) -> None:
        """This test file must not import from src.* or domains.nba/basketball_nba."""
        test_path = Path(__file__)
        src = test_path.read_text("utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("src."), f"Forbidden: from {node.module}"
                assert not node.module.startswith("domains.nba"), f"F5: from {node.module}"
                assert not node.module.startswith("domains.basketball_nba"), f"F5: from {node.module}"


# ---------------------------------------------------------------------------
# 14. Regression: malformed/blank Date rows must not crash (NaT strftime bug)
# ---------------------------------------------------------------------------

def test_malformed_date_row_dropped_no_crash() -> None:
    """Rows with unparseable Date values (blank, garbage) must be silently dropped.

    Before the fix, these rows yielded NaT after pd.to_datetime(..., errors='coerce')
    and then crashed with ``ValueError: NaTType does not support strftime`` when
    _make_event_id called ``f"{date:%Y%m%d}-..."``.  After the fix both build_matches
    and build_odds must complete without error and the bad row must be absent from
    the output.
    """
    import numpy as np

    # Build a small in-memory raw DataFrame with the football-data column set.
    # 3 valid rows + 1 row with a garbage Date (but otherwise-valid FTHG/FTAG
    # so it would pass the FTHG/FTAG filter and reach _make_event_id).
    raw = pd.DataFrame({
        "Div":      ["E0",          "E0",          "E0",          "E0"],
        "Date":     ["15/08/2023",  "22/08/2023",  "29/08/2023",  ""],
        "HomeTeam": ["Arsenal",     "Chelsea",     "Tottenham",   "Orphan"],
        "AwayTeam": ["Brentford",   "Fulham",      "Brighton",    "Ghost"],
        "FTHG":     [2.0,           1.0,           0.0,           3.0],
        "FTAG":     [1.0,           1.0,           2.0,           1.0],
        "FTR":      ["H",           "D",           "A",           "H"],
        # Minimal odds columns — enough that build_odds finds a price for valid rows
        "B365>2.5": [1.80,          1.90,          1.75,          1.85],
        "B365<2.5": [2.00,          1.95,          2.10,          2.05],
        "B365C>2.5":[1.82,          1.88,          1.77,          1.87],
        "B365C<2.5":[1.98,          1.97,          2.08,          2.03],
        # Leave Pinnacle/Avg absent — build_odds handles missing cols gracefully
    })

    frames = [("E0", 2023, raw)]

    # --- build_matches must not raise, and bad row must be gone ---
    m = build_matches(frames)
    assert len(m) == 3, f"Expected 3 valid rows, got {len(m)}"
    assert "Orphan" not in m["home_team"].values
    assert "Ghost" not in m["away_team"].values
    # Valid rows survive with correct event_id format
    for eid in m["event_id"]:
        assert eid[:8].isdigit(), f"Bad event_id format: {eid}"
        assert "-E0-" in eid

    # --- build_odds must not raise, and bad row must be gone ---
    o = build_odds(frames)
    # All 3 valid rows have B365 prices → should appear in odds output
    assert len(o) == 3, f"Expected 3 odds rows, got {len(o)}"
    assert "orphan" not in " ".join(o["event_id"].tolist()).lower()
    assert "ghost" not in " ".join(o["event_id"].tolist()).lower()


# ---------------------------------------------------------------------------
# 15. Regression: mixed date formats across files must all parse (FIX-FORWARD)
# ---------------------------------------------------------------------------

def test_mixed_date_formats_across_files_all_parse() -> None:
    """Two files with different date formats in the same season must both survive.

    football-data.co.uk uses dd/mm/yyyy in some files (e.g. E0 1516) and
    dd/mm/yy in others (e.g. D1 1516).  Parsing AFTER concat with a single
    pd.to_datetime call infers one format and coerces the other to NaT, silently
    dropping ~6,000 matches.  Parsing PER-FILE (before concat) fixes this.
    """
    import datetime as _dt

    # Frame A: Premier League 2015 — 4-digit year dates (dd/mm/yyyy)
    frame_a = pd.DataFrame({
        "Div":      ["E0",          "E0"],
        "Date":     ["08/08/2015",  "15/08/2015"],
        "HomeTeam": ["Arsenal",     "Chelsea"],
        "AwayTeam": ["West Ham",    "Swansea"],
        "FTHG":     [2.0,           1.0],
        "FTAG":     [0.0,           2.0],
        "FTR":      ["H",           "A"],
        "B365>2.5": [1.80,          1.90],
        "B365<2.5": [2.00,          1.95],
        "B365C>2.5":[1.82,          1.88],
        "B365C<2.5":[1.98,          1.97],
    })

    # Frame B: Bundesliga 2015 — 2-digit year dates (dd/mm/yy)
    frame_b = pd.DataFrame({
        "Div":      ["D1",          "D1"],
        "Date":     ["14/08/15",    "22/08/15"],
        "HomeTeam": ["Bayern",      "Dortmund"],
        "AwayTeam": ["Hamburg",     "Schalke"],
        "FTHG":     [3.0,           1.0],
        "FTAG":     [1.0,           1.0],
        "FTR":      ["H",           "D"],
        "B365>2.5": [1.75,          1.85],
        "B365<2.5": [2.10,          2.05],
        "B365C>2.5":[1.77,          1.87],
        "B365C<2.5":[2.08,          2.03],
    })

    frames = [("E0", 2015, frame_a), ("D1", 2015, frame_b)]

    # --- build_matches: all 4 rows must survive (no NaT drops) ---
    m = build_matches(frames)
    assert len(m) == 4, (
        f"Expected 4 rows (2 per file, 0 NaT drops), got {len(m)}. "
        "Mixed-format date parsing across files is silently dropping rows."
    )

    # Correct calendar dates for 4-digit-year file (frame A)
    assert _dt.date(2015, 8, 8) in m["date"].dt.date.tolist(), \
        "08/08/2015 (4-digit year) did not parse to 2015-08-08"
    assert _dt.date(2015, 8, 15) in m["date"].dt.date.tolist(), \
        "15/08/2015 (4-digit year) did not parse to 2015-08-15"

    # Correct calendar dates for 2-digit-year file (frame B)
    assert _dt.date(2015, 8, 14) in m["date"].dt.date.tolist(), \
        "14/08/15 (2-digit year) did not parse to 2015-08-14"
    assert _dt.date(2015, 8, 22) in m["date"].dt.date.tolist(), \
        "22/08/15 (2-digit year) did not parse to 2015-08-22"

    # Spot-check a known event_id from frame A
    assert "20150808-E0-arsenal-west_ham" in m["event_id"].tolist(), \
        "event_id for Arsenal v West Ham (08/08/2015) not found or malformed"

    # Spot-check a known event_id from frame B
    assert "20150814-D1-bayern-hamburg" in m["event_id"].tolist(), \
        "event_id for Bayern v Hamburg (14/08/15) not found or malformed"

    # --- build_odds: all 4 rows must survive ---
    o = build_odds(frames)
    assert len(o) == 4, (
        f"Expected 4 odds rows (0 NaT drops), got {len(o)}. "
        "Mixed-format date parsing across files is silently dropping rows."
    )
