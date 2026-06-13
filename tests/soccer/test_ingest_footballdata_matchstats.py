"""tests.soccer.test_ingest_footballdata_matchstats — OFFLINE fixture tests.

Exercises domains.soccer.ingest_footballdata_matchstats against a SMALL synthetic
CSV fixture written into tmp_path.  The real cached corpus is NEVER loaded (fast,
low-RAM).  The module performs ZERO network I/O; tests do not monkeypatch sockets
because the module never imports urllib.

Covered:
  - schema     : every MATCH_STATS_COLS column present;
  - mapping    : HS/AS/HST/AST land in the right home/away columns;
  - event_id   : matches the main ingest's id rule for the fixture;
  - ratios     : sot_ratio = sot/shots, NaN when shots == 0;
  - missing    : a row lacking HST yields NaN home_sot (no crash);
  - 1:1 count  : output row count == input match count (valid-date rows);
  - parquet    : build_match_stats(raw_dir, out_path) writes the sidecar.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from domains.soccer import ingest_footballdata as main_ingest
from domains.soccer.ingest_footballdata_matchstats import (
    MATCH_STATS_COLS,
    build_match_stats,
    build_match_stats_frame,
)

# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

# E0 rows: full stats, plus a shots=0 row to exercise the NaN ratio.
_E0_CSV = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,Referee,"
    "HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR\n"
    "E0,15/08/2024,Arsenal,Chelsea,3,1,H,2,0,H,M Oliver,"
    "18,7,9,3,11,13,8,2,1,2,0,0\n"
    "E0,15/08/2024,Man United,Liverpool,0,0,D,0,0,D,A Taylor,"
    "0,20,0,8,9,7,0,6,3,1,1,0\n"
)

# E1 (Championship) row deliberately MISSING the HST column entirely.
_E1_CSV = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,Referee,"
    "HS,AS,AST,HF,AF,HC,AC,HY,AY,HR,AR\n"
    "E1,16/08/2024,Leeds,Norwich City,2,2,D,1,1,D,J Smith,"
    "14,11,5,10,12,6,4,2,3,0,1\n"
)


@pytest.fixture()
def raw_dir(tmp_path: Path) -> Path:
    """Write season-coded CSVs (2425 season) into tmp_path; never the real cache."""
    d = tmp_path / "footballdata"
    d.mkdir()
    (d / "2425_E0.csv").write_text(_E0_CSV, encoding="utf-8")
    (d / "2425_E1.csv").write_text(_E1_CSV, encoding="utf-8")
    return d


def _frames():
    """In-memory (div, season_start_year, raw_df) tuples for transform tests."""
    import io
    return [
        ("E0", 2024, pd.read_csv(io.StringIO(_E0_CSV))),
        ("E1", 2024, pd.read_csv(io.StringIO(_E1_CSV))),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_schema_all_columns_present():
    df = build_match_stats_frame(_frames())
    assert list(df.columns) == list(MATCH_STATS_COLS)
    for col in MATCH_STATS_COLS:
        assert col in df.columns


def test_mapping_home_away_correct():
    df = build_match_stats_frame(_frames())
    arsenal = df[df["home_team"] == "Arsenal"].iloc[0]
    # HS=18,AS=7,HST=9,AST=3 -> home_shots=18, away_shots=7, home_sot=9, away_sot=3
    assert arsenal["home_shots"] == 18.0
    assert arsenal["away_shots"] == 7.0
    assert arsenal["home_sot"] == 9.0
    assert arsenal["away_sot"] == 3.0
    assert arsenal["home_corners"] == 8.0
    assert arsenal["away_corners"] == 2.0
    assert arsenal["home_red"] == 0.0
    # half-time + referee captured
    assert arsenal["hthg"] == 2.0
    assert arsenal["htag"] == 0.0
    assert arsenal["htr"] == "H"
    assert arsenal["referee"] == "M Oliver"


def test_event_id_matches_main_ingest():
    df = build_match_stats_frame(_frames())
    arsenal = df[df["home_team"] == "Arsenal"].iloc[0]
    expected = main_ingest._make_event_id(
        pd.Timestamp("2024-08-15"), "E0", "Arsenal", "Chelsea")
    assert arsenal["event_id"] == expected
    assert expected == "20240815-E0-arsenal-chelsea"

    leeds = df[df["home_team"] == "Leeds"].iloc[0]
    expected_e1 = main_ingest._make_event_id(
        pd.Timestamp("2024-08-16"), "E1", "Leeds", "Norwich City")
    assert leeds["event_id"] == expected_e1
    # slug replaces the space in "Norwich City"
    assert expected_e1 == "20240816-E1-leeds-norwich_city"


def test_ratios_and_nan_on_zero_shots():
    df = build_match_stats_frame(_frames())
    arsenal = df[df["home_team"] == "Arsenal"].iloc[0]
    # home_sot_ratio = 9/18 = 0.5
    assert arsenal["home_sot_ratio"] == pytest.approx(0.5)
    # away_sot_ratio = 3/7
    assert arsenal["away_sot_ratio"] == pytest.approx(3.0 / 7.0)
    # total_shots = 18+7 = 25 ; total_sot = 9+3 = 12
    assert arsenal["total_shots"] == 25.0
    assert arsenal["total_sot"] == 12.0

    # Man United: home_shots=0 -> home_sot_ratio NaN (no div-by-zero crash)
    mufc = df[df["home_team"] == "Man United"].iloc[0]
    assert mufc["home_shots"] == 0.0
    assert math.isnan(mufc["home_sot_ratio"])
    # away side still computes: 8/20 = 0.4
    assert mufc["away_sot_ratio"] == pytest.approx(0.4)


def test_missing_column_yields_nan_no_crash():
    df = build_match_stats_frame(_frames())
    # E1 fixture has NO HST column -> home_sot must be NaN (and not crash)
    leeds = df[df["home_team"] == "Leeds"].iloc[0]
    assert math.isnan(leeds["home_sot"])
    # AST present (=5) -> away_sot captured
    assert leeds["away_sot"] == 5.0
    # ratio with NaN numerator -> NaN
    assert math.isnan(leeds["home_sot_ratio"])
    # away ratio = 5/11
    assert leeds["away_sot_ratio"] == pytest.approx(5.0 / 11.0)


def test_one_to_one_row_count():
    df = build_match_stats_frame(_frames())
    # 2 E0 rows + 1 E1 row = 3 matches, all with valid dates
    assert len(df) == 3
    # event_ids unique (1:1 keying)
    assert df["event_id"].is_unique


def test_build_match_stats_writes_parquet(raw_dir: Path, tmp_path: Path):
    out_path = tmp_path / "match_stats.parquet"
    result = build_match_stats(raw_dir=str(raw_dir), out_path=str(out_path))
    assert result == out_path
    assert out_path.exists()
    df = pd.read_parquet(out_path)
    assert list(df.columns) == list(MATCH_STATS_COLS)
    assert len(df) == 3
    # spot-check a mapped value survived the round-trip
    arsenal = df[df["home_team"] == "Arsenal"].iloc[0]
    assert arsenal["home_shots"] == 18.0
    assert arsenal["event_id"] == "20240815-E0-arsenal-chelsea"


def test_empty_frames_returns_empty_contract():
    df = build_match_stats_frame([])
    assert list(df.columns) == list(MATCH_STATS_COLS)
    assert len(df) == 0
