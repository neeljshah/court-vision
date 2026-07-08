"""Tests for domains.tennis.sackmann_pbp_ingest -- synthetic-CSV fixtures only, zero network."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from domains.tennis.sackmann_pbp_ingest import (
    build_charting_points,
    build_slam_points,
    parse_charting_file,
    parse_slam_file,
)

_SLAM_POINTS_FULL = (
    "match_id,SetNo,GameNo,PointNumber,PointServer,PointWinner,P1GamesWon,P2GamesWon,"
    "P1Score,P2Score,Rally,P1Ace,P2Ace,P1DoubleFault,P2DoubleFault,Speed_KMH\n"
    "2015-wimbledon-1101,1,1,1,1,1,0,0,15,0,3,0,0,0,0,180\n"
    "2015-wimbledon-1101,1,1,2,1,2,0,0,15,15,1,0,0,0,0,175\n"
)
# Missing optional cols (Rally, Speed_KMH, aces, faults) -- schema-drift case.
_SLAM_POINTS_SPARSE = (
    "match_id,SetNo,GameNo,PointNumber,PointServer,PointWinner,P1GamesWon,P2GamesWon\n"
    "2014-ausopen-2201,1,1,1,2,2,0,0\n"
)
_SLAM_MATCHES_NO_DATE = (
    "match_id,year,slam,match_num,player1,player2\n"
    "2015-wimbledon-1101,2015,wimbledon,1101,A Player,B Player\n"
)
_SLAM_MATCHES_WITH_DATE = (
    "match_id,year,slam,match_num,date\n"
    "2015-wimbledon-1101,2015,wimbledon,1101,2015-07-01\n"
)

_CHARTING_POINTS = (
    "match_id,Pt,Set1,Set2,Gm1,Gm2,Pts,Gm#,TbSet,Svr,1st,2nd,Notes,PtWinner\n"
    "20150701-M-Wimbledon-F-A-B,1,0,0,0,0,0-0,1,False,1,4b37y1r3n#,,,1\n"
    "20150701-M-Wimbledon-F-A-B,2,0,0,0,0,0-15,1,False,1,6n,5f18f1f1f3s3f-1l3*,,2\n"
)
_CHARTING_MATCHES = (
    "match_id,Player 1,Player 2,Date,Tournament\n"
    "20150701-M-Wimbledon-F-A-B,A,B,20150701,Wimbledon\n"
)


def test_slam_points_score_state(tmp_path: Path) -> None:
    p = tmp_path / "2015-wimbledon-points.csv"
    m = tmp_path / "2015-wimbledon-matches.csv"
    p.write_text(_SLAM_POINTS_FULL, encoding="utf-8")
    m.write_text(_SLAM_MATCHES_NO_DATE, encoding="utf-8")

    out = parse_slam_file(p, m)
    assert len(out) == 2
    assert out.iloc[0]["set_no"] == 1
    assert out.iloc[0]["game_no"] == 1
    assert out.iloc[1]["point_number"] == 2
    assert out.iloc[1]["p1_score"] == "15"
    assert out.iloc[1]["p2_score"] == "15"
    assert out.iloc[0]["rally"] == 3
    assert out.iloc[0]["speed_kmh"] == 180.0
    assert out["tourney"].iloc[0] == "wimbledon"
    assert out["year"].iloc[0] == 2015


def test_slam_schema_drift_missing_optional_cols(tmp_path: Path) -> None:
    p = tmp_path / "2014-ausopen-points.csv"
    m = tmp_path / "2014-ausopen-matches.csv"
    p.write_text(_SLAM_POINTS_SPARSE, encoding="utf-8")
    m.write_text(_SLAM_MATCHES_NO_DATE, encoding="utf-8")  # wrong match_id on purpose -> all-missing join

    out = parse_slam_file(p, m)
    assert len(out) == 1
    assert pd.isna(out.iloc[0]["rally"])
    assert pd.isna(out.iloc[0]["speed_kmh"])
    assert pd.isna(out.iloc[0]["p1_ace"])

    # Full pipeline (build_slam_points) must still write a parquet, not crash.
    out_path = tmp_path / "out" / "slam_points.parquet"
    built = build_slam_points(str(tmp_path), str(out_path))
    assert out_path.exists()
    assert len(built) >= 1


def test_date_source_flag_logic(tmp_path: Path) -> None:
    p = tmp_path / "2015-wimbledon-points.csv"
    p.write_text(_SLAM_POINTS_FULL, encoding="utf-8")

    # Case 1: matches.csv has no date-like column -> fallback to tourney start, flagged.
    m_no_date = tmp_path / "2015-wimbledon-matches.csv"
    m_no_date.write_text(_SLAM_MATCHES_NO_DATE, encoding="utf-8")
    out_no_date = parse_slam_file(p, m_no_date)
    assert (out_no_date["date_source"] == "tourney_start_approx").all()
    assert (out_no_date["date"] == pd.Timestamp(2015, 6, 25).date()).all()

    # Case 2: matches.csv HAS a real date column -> use it, flagged as match_date.
    m_with_date = tmp_path / "2015-wimbledon-matches-alt.csv"
    m_with_date.write_text(_SLAM_MATCHES_WITH_DATE, encoding="utf-8")
    out_with_date = parse_slam_file(p, m_with_date)
    assert (out_with_date["date_source"] == "match_date").all()
    assert (out_with_date["date"] == pd.Timestamp(2015, 7, 1).date()).all()


def test_charting_points_core_columns(tmp_path: Path) -> None:
    p = tmp_path / "charting-m-points-test.csv"
    m = tmp_path / "charting-m-matches.csv"
    p.write_text(_CHARTING_POINTS, encoding="utf-8")
    m.write_text(_CHARTING_MATCHES, encoding="utf-8")

    out = parse_charting_file(p, m, tour="m")
    assert len(out) == 2
    assert out.iloc[0]["server"] == 1
    assert out.iloc[0]["point_winner"] == 1
    assert bool(out.iloc[0]["is_second_serve"]) is False  # "2nd" column empty
    assert bool(out.iloc[1]["is_second_serve"]) is True   # "2nd" column populated
    assert out.iloc[0]["date"] == pd.Timestamp(2015, 7, 1).date()
    assert out["rally_length"].isna().all()  # deliberately not parsed (ponytail upgrade path)

    out_path = tmp_path / "out" / "charting_points.parquet"
    built = build_charting_points(str(tmp_path), str(out_path))
    assert out_path.exists()
    assert len(built) == 2


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
