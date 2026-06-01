"""tests/test_snapshot_lines_archive.py — unit tests for the nightly archiver.

Covers:
  (a) Idempotency: running snapshot twice for the same date does NOT duplicate rows.
  (b) Accumulation: a second snapshot_date APPENDS without dropping the first date's rows.
  (c) Leak-safety: output parquet carries snapshot_date + captured_at columns usable
      as a cutoff for training-time filtering.
  (d) Mainline files are excluded; stale files are excluded.
  (e) Missing optional columns (player_id, game_id) are handled gracefully.

All tests use synthetic in-memory fixtures — no dependency on live data/lines/ files.
"""
from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

import pandas as pd
import pytest

# We need to inject a fake _LINES_DIR + _ROTOWIRE_PATH into the module under
# test so it reads our synthetic data rather than the real data/lines/ directory.
# We do this by monkey-patching the module-level constants after import.
import importlib
import sys

# ---------------------------------------------------------------------------
# Fixtures — synthetic CSV + JSON in a tmp directory
# ---------------------------------------------------------------------------

_PROP_CSV_DAY1 = textwrap.dedent("""\
    captured_at,book,game_id,player_id,player_name,stat,line,over_price,under_price,start_time
    2026-05-28T05:00+00:00,dk,999001,111,LeBron James,pts,24.5,-110,-115,2026-05-29T00:30:00Z
    2026-05-28T06:00+00:00,dk,999001,111,LeBron James,pts,25.0,-108,-118,2026-05-29T00:30:00Z
    2026-05-28T05:00+00:00,pin,999001,,Anthony Davis,reb,12.5,-105,-120,2026-05-29T00:30:00Z
""")

_PROP_CSV_DAY2 = textwrap.dedent("""\
    captured_at,book,game_id,player_id,player_name,stat,line,over_price,under_price,start_time
    2026-05-29T05:00+00:00,dk,999002,222,Steph Curry,pts,28.5,-112,-112,2026-05-30T00:30:00Z
    2026-05-29T06:00+00:00,pin,999002,,Steph Curry,ast,5.5,110,-145,2026-05-30T00:30:00Z
""")

# Mainline file — should be silently skipped
_MAINLINE_CSV = textwrap.dedent("""\
    captured_at,book,game_id,market_type,side,line,price,home_team,away_team,start_time
    2026-05-28T05:00+00:00,pin,999001,moneyline,home,,-195,Lakers,Celtics,2026-05-29T00:30:00Z
""")

# Rotowire JSON — day 1
_ROTOWIRE_DAY1: dict = {
    "as_of_date": "2026-05-28",
    "game_date": "2026-05-29",
    "teams": {
        "LAL": [
            {"player_name": "LeBron James",  "position": "SF", "status": "C",
             "is_starter": True,  "lineup_order": 0},
            {"player_name": "Anthony Davis", "position": "C",  "status": "C",
             "is_starter": True,  "lineup_order": 1},
        ],
        "BOS": [
            {"player_name": "Jayson Tatum",  "position": "SF", "status": "C",
             "is_starter": True,  "lineup_order": 0},
        ],
    },
}

# Rotowire JSON — day 2
_ROTOWIRE_DAY2: dict = {
    "as_of_date": "2026-05-29",
    "game_date": "2026-05-30",
    "teams": {
        "GSW": [
            {"player_name": "Steph Curry", "position": "PG", "status": "C",
             "is_starter": True,  "lineup_order": 0},
        ],
    },
}


# ---------------------------------------------------------------------------
# Helper to wire the module against a temp directory
# ---------------------------------------------------------------------------

def _make_lines_dir(tmp: Path, date_str: str, csv_body: str, suffix: str = "dk") -> Path:
    """Write a synthetic prop CSV into a fake lines/ dir."""
    lines_dir = tmp / "lines"
    lines_dir.mkdir(parents=True, exist_ok=True)
    (lines_dir / f"{date_str}_{suffix}.csv").write_text(csv_body, encoding="utf-8")
    return lines_dir


def _make_rotowire(tmp: Path, data: dict) -> Path:
    """Write a synthetic rotowire JSON."""
    cache_dir = tmp / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "rotowire_lineups_parsed.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _patch_and_snapshot(mod, lines_dir: Path, rotowire_path: Path,
                        snapshot_date: str, out_dir: Path) -> dict:
    """Monkey-patch module paths and call snapshot()."""
    mod._LINES_DIR = lines_dir
    mod._ROTOWIRE_PATH = rotowire_path
    return mod.snapshot(as_of=snapshot_date, out_dir=out_dir)


def _get_module():
    """Fresh import of the archiver module (avoids cached patches)."""
    mod_name = "scripts.ingest.snapshot_lines_archive"
    # Remove cached version so patches don't bleed between tests
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    # Ensure the scripts package root is on sys.path
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return importlib.import_module(mod_name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIdempotency:
    """(a) Running snapshot twice for the same date must not duplicate rows."""

    def test_prop_lines_no_duplicate(self, tmp_path):
        mod = _get_module()
        lines_dir = _make_lines_dir(tmp_path, "2026-05-28", _PROP_CSV_DAY1, "dk")
        rw = _make_rotowire(tmp_path, _ROTOWIRE_DAY1)
        out = tmp_path / "archive"

        r1 = _patch_and_snapshot(mod, lines_dir, rw, "2026-05-28", out)
        r2 = _patch_and_snapshot(mod, lines_dir, rw, "2026-05-28", out)

        archive = pd.read_parquet(out / "prop_lines_archive.parquet")
        # Total rows after both runs must equal rows after first run
        assert r2["prop_rows_added"] == 0, (
            f"Second run added {r2['prop_rows_added']} rows — should be 0"
        )
        assert r1["prop_total_rows"] == r2["prop_total_rows"], (
            "Total row count changed on second run — rows were duplicated"
        )
        # Verify the dedup key uniqueness directly in the parquet
        dedup_cols = ["snapshot_date", "captured_at", "book", "game_id", "player_name", "stat"]
        dupes = archive.duplicated(subset=dedup_cols).sum()
        assert dupes == 0, f"{dupes} duplicate rows found after idempotent re-run"

    def test_starters_no_duplicate(self, tmp_path):
        mod = _get_module()
        lines_dir = _make_lines_dir(tmp_path, "2026-05-28", _PROP_CSV_DAY1, "dk")
        rw = _make_rotowire(tmp_path, _ROTOWIRE_DAY1)
        out = tmp_path / "archive"

        r1 = _patch_and_snapshot(mod, lines_dir, rw, "2026-05-28", out)
        r2 = _patch_and_snapshot(mod, lines_dir, rw, "2026-05-28", out)

        archive = pd.read_parquet(out / "starters_archive.parquet")
        assert r2["starter_rows_added"] == 0, (
            f"Second starter run added {r2['starter_rows_added']} rows"
        )
        dupes = archive.duplicated(subset=["snapshot_date", "game_date", "team", "player_name"]).sum()
        assert dupes == 0


class TestAccumulation:
    """(b) A second snapshot_date APPENDS without dropping the first date's rows."""

    def test_prop_lines_accumulate(self, tmp_path):
        mod = _get_module()
        out = tmp_path / "archive"

        # Day 1
        lines_dir1 = _make_lines_dir(tmp_path / "d1", "2026-05-28", _PROP_CSV_DAY1, "dk")
        rw1 = _make_rotowire(tmp_path / "d1", _ROTOWIRE_DAY1)
        r1 = _patch_and_snapshot(mod, lines_dir1, rw1, "2026-05-28", out)
        rows_after_day1 = r1["prop_total_rows"]

        # Day 2
        lines_dir2 = _make_lines_dir(tmp_path / "d2", "2026-05-29", _PROP_CSV_DAY2, "dk")
        rw2 = _make_rotowire(tmp_path / "d2", _ROTOWIRE_DAY2)
        r2 = _patch_and_snapshot(mod, lines_dir2, rw2, "2026-05-29", out)

        archive = pd.read_parquet(out / "prop_lines_archive.parquet")
        dates_present = sorted(archive["snapshot_date"].unique())
        assert "2026-05-28" in dates_present, "Day-1 rows were dropped after Day-2 run"
        assert "2026-05-29" in dates_present, "Day-2 rows are missing"
        assert r2["prop_total_rows"] > rows_after_day1, (
            "Total rows did not grow after day-2 snapshot"
        )
        assert r2["prop_rows_added"] > 0, "Day-2 added 0 rows — accumulation broken"

    def test_starters_accumulate(self, tmp_path):
        mod = _get_module()
        out = tmp_path / "archive"

        lines_dir1 = _make_lines_dir(tmp_path / "d1", "2026-05-28", _PROP_CSV_DAY1, "dk")
        rw1 = _make_rotowire(tmp_path / "d1", _ROTOWIRE_DAY1)
        _patch_and_snapshot(mod, lines_dir1, rw1, "2026-05-28", out)

        lines_dir2 = _make_lines_dir(tmp_path / "d2", "2026-05-29", _PROP_CSV_DAY2, "dk")
        rw2 = _make_rotowire(tmp_path / "d2", _ROTOWIRE_DAY2)
        _patch_and_snapshot(mod, lines_dir2, rw2, "2026-05-29", out)

        archive = pd.read_parquet(out / "starters_archive.parquet")
        dates = sorted(archive["snapshot_date"].unique())
        assert "2026-05-28" in dates
        assert "2026-05-29" in dates
        teams_all = set(archive["team"].unique())
        assert "LAL" in teams_all, "LAL (day-1) was dropped"
        assert "GSW" in teams_all, "GSW (day-2) is missing"


class TestLeakSafety:
    """(c) Parquet rows carry snapshot_date + captured_at usable as a leak cutoff."""

    def test_snapshot_date_column_present(self, tmp_path):
        mod = _get_module()
        lines_dir = _make_lines_dir(tmp_path, "2026-05-28", _PROP_CSV_DAY1, "dk")
        rw = _make_rotowire(tmp_path, _ROTOWIRE_DAY1)
        out = tmp_path / "archive"
        _patch_and_snapshot(mod, lines_dir, rw, "2026-05-28", out)

        props = pd.read_parquet(out / "prop_lines_archive.parquet")
        assert "snapshot_date" in props.columns, "snapshot_date column missing from prop archive"
        assert "captured_at" in props.columns, "captured_at column missing from prop archive"
        # All snapshot_date values must equal the date we passed in
        assert (props["snapshot_date"] == "2026-05-28").all()

    def test_captured_at_can_filter_as_cutoff(self, tmp_path):
        """Simulate a walk-forward backtest: filter captured_at < cutoff."""
        mod = _get_module()
        lines_dir = _make_lines_dir(tmp_path, "2026-05-28", _PROP_CSV_DAY1, "dk")
        rw = _make_rotowire(tmp_path, _ROTOWIRE_DAY1)
        out = tmp_path / "archive"
        _patch_and_snapshot(mod, lines_dir, rw, "2026-05-28", out)

        props = pd.read_parquet(out / "prop_lines_archive.parquet")
        # All captured_at values in our synthetic CSV are after 2026-05-28T05:00
        # A cutoff at exactly the first capture should return 0 pre-cutoff rows
        early_cutoff = pd.Timestamp("2026-05-28T04:59:00+00:00")
        pre = props[pd.to_datetime(props["captured_at"], utc=True) < early_cutoff]
        assert len(pre) == 0, "Some rows leaked before the cutoff"

        # A cutoff after the first capture but before the second should return 1 LeBron row
        mid_cutoff = pd.Timestamp("2026-05-28T05:30:00+00:00")
        mid = props[pd.to_datetime(props["captured_at"], utc=True) < mid_cutoff]
        # The 05:00 capture should be visible; the 06:00 capture should not
        lebron_mid = mid[mid["player_name"] == "LeBron James"]
        assert len(lebron_mid) == 1, (
            f"Expected 1 LeBron row before mid_cutoff, got {len(lebron_mid)}"
        )

    def test_starters_snapshot_date_present(self, tmp_path):
        mod = _get_module()
        lines_dir = _make_lines_dir(tmp_path, "2026-05-28", _PROP_CSV_DAY1, "dk")
        rw = _make_rotowire(tmp_path, _ROTOWIRE_DAY1)
        out = tmp_path / "archive"
        _patch_and_snapshot(mod, lines_dir, rw, "2026-05-28", out)

        starters = pd.read_parquet(out / "starters_archive.parquet")
        assert "snapshot_date" in starters.columns
        assert (starters["snapshot_date"] == "2026-05-28").all()
        assert "game_date" in starters.columns


class TestEdgeCases:
    """(d) Mainline files skipped; (e) missing optional columns handled."""

    def test_mainline_file_is_skipped(self, tmp_path):
        mod = _get_module()
        lines_dir = tmp_path / "lines"
        lines_dir.mkdir()
        # Write ONLY a mainline file — no player props at all
        (lines_dir / "2026-05-28_pin_mainline.csv").write_text(_MAINLINE_CSV, encoding="utf-8")
        rw = _make_rotowire(tmp_path, _ROTOWIRE_DAY1)
        out = tmp_path / "archive"

        result = _patch_and_snapshot(mod, lines_dir, rw, "2026-05-28", out)
        # Prop archive should be empty (no prop CSV was present)
        assert result["prop_rows_added"] == 0
        prop_archive = out / "prop_lines_archive.parquet"
        if prop_archive.exists():
            df = pd.read_parquet(prop_archive)
            assert df.empty or len(df) == 0

    def test_stale_file_is_skipped(self, tmp_path):
        mod = _get_module()
        lines_dir = tmp_path / "lines"
        lines_dir.mkdir()
        # Fresh file has only DK rows; stale file (same content as fresh) would
        # double the row count if it were read.
        dk_only_csv = textwrap.dedent("""\
            captured_at,book,game_id,player_id,player_name,stat,line,over_price,under_price,start_time
            2026-05-28T05:00+00:00,dk,999001,111,LeBron James,pts,24.5,-110,-115,2026-05-29T00:30:00Z
            2026-05-28T06:00+00:00,dk,999001,111,LeBron James,pts,25.0,-108,-118,2026-05-29T00:30:00Z
        """)
        (lines_dir / "2026-05-28_dk.csv").write_text(dk_only_csv, encoding="utf-8")
        # .stale extension — must be ignored
        (lines_dir / "2026-05-28_mgm.csv.stale").write_text(dk_only_csv, encoding="utf-8")
        rw = _make_rotowire(tmp_path, _ROTOWIRE_DAY1)
        out = tmp_path / "archive"

        result = _patch_and_snapshot(mod, lines_dir, rw, "2026-05-28", out)
        archive = pd.read_parquet(out / "prop_lines_archive.parquet")
        # Only rows from dk.csv (2 rows). If .stale was read it would be 4.
        assert len(archive) == 2, (
            f"Expected 2 rows (dk only), got {len(archive)} — stale may have leaked"
        )
        assert (archive["book"] == "dk").all(), "Stale file rows leaked into archive"

    def test_missing_player_id_handled(self, tmp_path):
        """Pinnacle CSVs omit player_id — archive must still be written."""
        mod = _get_module()
        pin_csv = textwrap.dedent("""\
            captured_at,book,game_id,player_name,stat,line,over_price,under_price,start_time
            2026-05-28T08:00+00:00,pin,999001,Mikal Bridges,reb,3.5,-102,-130,2026-05-29T00:30:00Z
        """)
        lines_dir = _make_lines_dir(tmp_path, "2026-05-28", pin_csv, "pin")
        rw = _make_rotowire(tmp_path, _ROTOWIRE_DAY1)
        out = tmp_path / "archive"

        result = _patch_and_snapshot(mod, lines_dir, rw, "2026-05-28", out)
        assert result["prop_rows_added"] >= 1
        archive = pd.read_parquet(out / "prop_lines_archive.parquet")
        assert "player_id" in archive.columns  # column present, value may be NaN
        assert "Mikal Bridges" in archive["player_name"].values

    def test_no_lines_files_returns_zero_props(self, tmp_path):
        mod = _get_module()
        lines_dir = tmp_path / "lines"
        lines_dir.mkdir()  # empty directory
        rw = _make_rotowire(tmp_path, _ROTOWIRE_DAY1)
        out = tmp_path / "archive"

        result = _patch_and_snapshot(mod, lines_dir, rw, "2026-05-28", out)
        assert result["prop_rows_added"] == 0

    def test_missing_rotowire_returns_zero_starters(self, tmp_path):
        mod = _get_module()
        lines_dir = _make_lines_dir(tmp_path, "2026-05-28", _PROP_CSV_DAY1, "dk")
        # Don't create rotowire file
        missing_rw = tmp_path / "nonexistent_rotowire.json"
        out = tmp_path / "archive"

        mod._LINES_DIR = lines_dir
        mod._ROTOWIRE_PATH = missing_rw
        result = mod.snapshot(as_of="2026-05-28", out_dir=out)
        assert result["starter_rows_added"] == 0
