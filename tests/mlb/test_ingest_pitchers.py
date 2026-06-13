"""tests/mlb/test_ingest_pitchers.py — offline tests for domains/mlb/ingest_pitchers.py.

Network hard-blocked. Every test builds a TINY synthetic SBR fixture in tmp_path
(a handful of fake V/H rows) — it never loads the real corpus and never touches
the network. The fixture mirrors the SBR CSV shape used by ingest_sbro.

Run: python -m pytest tests/mlb/test_ingest_pitchers.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Network hard-block — before any ingest import
# ---------------------------------------------------------------------------

def _block_network(*args, **kwargs):
    raise RuntimeError("Network access is forbidden in tests")

import urllib.request  # noqa: E402
urllib.request.urlopen = _block_network  # type: ignore[assignment]

from domains.mlb.ingest_pitchers import (  # noqa: E402
    PITCHERS_COLS, _norm_pitcher, build_pitchers, build_pitchers_parquet,
)

# SBR CSV column order (matches the real cached files).
_COLS = ["Date", "Rot", "VH", "Team", "Pitcher",
         "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th",
         "Final", "Open", "Close", "season"]


def _row(date, rot, vh, team, pitcher, innings, final, season=2012):
    """Build one SBR-shaped row dict. ``innings`` = list of 9 inning tokens."""
    d = {"Date": date, "Rot": rot, "VH": vh, "Team": team, "Pitcher": pitcher,
         "Final": final, "Open": -110, "Close": -110, "season": season}
    for col, val in zip(("1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th"), innings):
        d[col] = val
    return d


def _write_fixture(tmp_path: Path, rows: List[dict], year: int = 2012) -> Path:
    """Write rows to {tmp}/mlb-odds-{year}.csv and return the raw_dir."""
    raw_dir = tmp_path / "sbro"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=_COLS).to_csv(str(raw_dir / f"mlb-odds-{year}.csv"), index=False)
    return raw_dir


# A standard two-game fixture: NYY@BOS and STL@CIN, both 2012.
def _two_game_rows() -> List[dict]:
    z = [0] * 9
    return [
        _row(401, 101, "V", "NYY", "CSABATHIA-L", [0, 1, 0, 0, 0, 0, 1, 0, 1], 3),
        _row(401, 102, "H", "BOS", "JBECKETT-R", [0, 0, 1, 0, 1, 0, 0, 0, "x"], 2),
        _row(401, 103, "V", "STL", "AWAINWRIGHT-R", z, 1),
        _row(401, 104, "H", "CIN", "JCUETO-R", [0, 0, 2, 0, 1, 0, 0, 0, "x"], 3),
    ]


# ---------------------------------------------------------------------------
# 1. Pairing — V-row → away, H-row → home
# ---------------------------------------------------------------------------

class TestPairing:
    def test_vh_pairing(self, tmp_path):
        raw = _write_fixture(tmp_path, _two_game_rows())
        from domains.mlb.ingest_pitchers import _load_frames
        df = build_pitchers(iter(_load_frames(raw, [2012])))
        row = df[df["event_id"] == "20120401-BOS-NYY-1"].iloc[0]
        # away pitcher comes from the V row (NYY), home from the H row (BOS)
        assert row["away_team"] == "NYY"
        assert row["home_team"] == "BOS"
        assert row["away_sp_name"] == "CSABATHIA-L"
        assert row["home_sp_name"] == "JBECKETT-R"


# ---------------------------------------------------------------------------
# 2. event_id matches the main ingest's rule exactly
# ---------------------------------------------------------------------------

class TestEventIdParity:
    def test_event_id_matches_build_games(self, tmp_path):
        """For the same fixture, pitchers event_ids == build_games event_ids (1:1)."""
        from domains.mlb.ingest_sbro import build_games
        from domains.mlb.ingest_pitchers import _load_frames
        raw = _write_fixture(tmp_path, _two_game_rows())
        frames = _load_frames(raw, [2012])
        g = build_games(iter(frames))
        p = build_pitchers(iter(frames))
        assert set(p["event_id"]) == set(g["event_id"])
        assert "20120401-BOS-NYY-1" in set(p["event_id"])
        assert "20120401-CIN-STL-1" in set(p["event_id"])


# ---------------------------------------------------------------------------
# 3. Coverage flag — blank / 'Undecided' → NaN + present=False
# ---------------------------------------------------------------------------

class TestCoverageFlag:
    def test_blank_and_undecided_are_absent(self, tmp_path):
        z = [0] * 9
        rows = [
            _row(401, 201, "V", "NYM", "", z, 1),            # blank visitor pitcher
            _row(401, 202, "H", "PHI", "Undecided", z, 4),   # undecided home pitcher
        ]
        raw = _write_fixture(tmp_path, rows)
        from domains.mlb.ingest_pitchers import _load_frames
        df = build_pitchers(iter(_load_frames(raw, [2012])))
        row = df.iloc[0]
        assert row["away_sp_present"] is False or bool(row["away_sp_present"]) is False
        assert row["home_sp_present"] is False or bool(row["home_sp_present"]) is False
        assert pd.isna(row["away_sp_name"])
        assert pd.isna(row["home_sp_name"])

    def test_present_true_for_real_names(self, tmp_path):
        raw = _write_fixture(tmp_path, _two_game_rows())
        from domains.mlb.ingest_pitchers import _load_frames
        df = build_pitchers(iter(_load_frames(raw, [2012])))
        assert bool(df["home_sp_present"].all())
        assert bool(df["away_sp_present"].all())

    def test_norm_pitcher_unit(self):
        assert _norm_pitcher("  CSABATHIA-L ") == ("CSABATHIA-L", True)
        assert _norm_pitcher("") == (None, False)
        assert _norm_pitcher("Undecided") == (None, False)
        assert _norm_pitcher("-") == (None, False)
        assert _norm_pitcher("TBD") == (None, False)
        assert _norm_pitcher(None) == (None, False)


# ---------------------------------------------------------------------------
# 4. 1:1 — N valid games → N rows
# ---------------------------------------------------------------------------

class TestOneToOne:
    def test_n_games_n_rows(self, tmp_path):
        raw = _write_fixture(tmp_path, _two_game_rows())
        from domains.mlb.ingest_pitchers import _load_frames
        df = build_pitchers(iter(_load_frames(raw, [2012])))
        assert len(df) == 2
        assert df["event_id"].nunique() == 2

    def test_tied_game_dropped_like_build_games(self, tmp_path):
        """A tied final must be dropped (and not consume a game_seq) — matching build_games."""
        z = [0] * 9
        rows = _two_game_rows() + [
            _row(402, 105, "V", "OAK", "GCOLE-R", z, 5),
            _row(402, 106, "H", "SEA", "MSCHERZER-R", z, 5),  # tie → dropped
        ]
        raw = _write_fixture(tmp_path, rows)
        from domains.mlb.ingest_sbro import build_games
        from domains.mlb.ingest_pitchers import _load_frames
        frames = _load_frames(raw, [2012])
        p = build_pitchers(iter(frames))
        g = build_games(iter(frames))
        assert len(p) == len(g) == 2  # tie excluded from both
        assert not any(e.startswith("20120402-SEA-OAK") for e in p["event_id"])


# ---------------------------------------------------------------------------
# 5. Robustness — malformed rows do not crash
# ---------------------------------------------------------------------------

class TestRobustness:
    def test_malformed_pair_skipped(self, tmp_path):
        """Two V rows in a row (bad pairing) are skipped, valid game still emitted."""
        z = [0] * 9
        rows = [
            _row(401, 301, "V", "ATL", "PITCHER-A", z, 2),
            _row(401, 302, "V", "WAS", "PITCHER-B", z, 1),  # should be H → invalid pair
        ] + _two_game_rows()
        raw = _write_fixture(tmp_path, rows)
        from domains.mlb.ingest_pitchers import _load_frames
        df = build_pitchers(iter(_load_frames(raw, [2012])))
        # only the 2 valid games survive; malformed pair absent
        assert len(df) == 2
        assert not any(e.startswith("20120401-WAS") or e.startswith("20120401-ATL")
                       for e in df["event_id"])

    def test_unparseable_final_skipped(self, tmp_path):
        z = [0] * 9
        rows = [
            _row(401, 401, "V", "TEX", "PITCHER-C", z, "PPD"),  # non-int final
            _row(401, 402, "H", "LAA", "PITCHER-D", z, 3),
        ] + _two_game_rows()
        raw = _write_fixture(tmp_path, rows)
        from domains.mlb.ingest_pitchers import _load_frames
        df = build_pitchers(iter(_load_frames(raw, [2012])))
        assert len(df) == 2  # postponed game skipped, no crash

    def test_empty_frames_empty_df(self):
        df = build_pitchers(iter([]))
        assert len(df) == 0
        assert list(df.columns) == list(PITCHERS_COLS)


# ---------------------------------------------------------------------------
# 6. Schema + innings capture + parquet round-trip
# ---------------------------------------------------------------------------

class TestSchemaAndOutput:
    def test_schema_columns(self, tmp_path):
        raw = _write_fixture(tmp_path, _two_game_rows())
        from domains.mlb.ingest_pitchers import _load_frames
        df = build_pitchers(iter(_load_frames(raw, [2012])))
        assert list(df.columns) == list(PITCHERS_COLS)

    def test_innings_captured(self, tmp_path):
        raw = _write_fixture(tmp_path, _two_game_rows())
        from domains.mlb.ingest_pitchers import _load_frames
        df = build_pitchers(iter(_load_frames(raw, [2012])))
        row = df[df["event_id"] == "20120401-BOS-NYY-1"].iloc[0]
        # away (NYY) innings 0,1,0,0,0,0,1,0,1 ; home (BOS) ends with 'x'
        assert row["away_innings"].split(",")[1] == "1"
        assert row["home_innings"].split(",")[-1] == "x"

    def test_parquet_roundtrip(self, tmp_path):
        raw = _write_fixture(tmp_path, _two_game_rows())
        out = tmp_path / "pitchers.parquet"
        p = build_pitchers_parquet(raw_dir=str(raw), out_path=str(out), years=[2012])
        assert p == out and out.exists()
        back = pd.read_parquet(str(out))
        assert len(back) == 2
        assert list(back.columns) == list(PITCHERS_COLS)
