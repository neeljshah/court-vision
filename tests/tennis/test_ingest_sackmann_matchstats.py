"""tests.tennis.test_ingest_sackmann_matchstats — offline tests for the
Sackmann per-match serve/return stats sidecar capture.

ALL OFFLINE.  A tiny synthetic raw CSV (4 rows, player IDs >= 900000) is written
into a tmp ``_raw/sackmann/`` dir; the module is pointed at it via ``raw_dir`` /
``out_path`` so the real CC BY-NC-SA corpus is never touched.  No src.* / torch imports.
"""
from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import pandas as pd
import pytest

from domains.tennis.ingest_sackmann_matchstats import OUT_COLS, build_match_stats

# Header mirrors the real Sackmann ATP CSV columns the capture reads.
_HEADER = (
    "tourney_id,tourney_name,surface,draw_size,tourney_level,tourney_date,match_num,"
    "winner_id,winner_seed,winner_name,winner_age,winner_rank_points,"
    "loser_id,loser_seed,loser_name,loser_age,loser_rank_points,"
    "score,best_of,round,minutes,"
    "w_ace,w_df,w_svpt,w_1stIn,w_1stWon,w_2ndWon,w_SvGms,w_bpSaved,w_bpFaced,"
    "l_ace,l_df,l_svpt,l_1stIn,l_1stWon,l_2ndWon,l_SvGms,l_bpSaved,l_bpFaced"
)

# Row A: winner_id(900001) <= loser_id(900002) -> winner maps to p1.
#        svpt=100, 1stIn=60 -> p1_1st_in_pct = 0.60.  bpSaved=5/bpFaced=8.
_ROW_A = (
    "test-t,Test,Hard,32,G,20240601,1,"
    "900001,1,Alpha,28,8000,"
    "900002,2,Beta,30,5000,"
    "6-3 6-4,3,F,80,"
    "10,2,100,60,45,20,12,5,8,"
    "4,3,90,50,40,18,11,3,6"
)
# Row B: winner_id(900050) > loser_id(900020) -> winner maps to p2.
#        winner svpt=120,1stIn=90 -> as p2 -> p2_1st_in_pct = 90/120 = 0.75.
_ROW_B = (
    "test-t,Test,Hard,32,G,20240601,2,"
    "900050,3,BigWin,25,7000,"
    "900020,4,SmallLose,27,4000,"
    "7-6 6-4,3,SF,95,"
    "20,1,120,90,70,25,14,2,3,"
    "6,5,80,40,30,15,10,4,9"
)
# Row C: blank serve stats (older-style row) -> stats coerce to NaN, no crash.
_ROW_C = (
    "test-t,Test,Clay,32,G,20240602,3,"
    "900003,5,Gamma,22,3000,"
    "900004,6,Delta,24,2000,"
    "6-2 6-2,3,QF,60,"
    ",,,,,,,,,"
    ",,,,,,,,"
)
# Row D: svpt=0 -> every rate with svpt denom is NaN (no divide-by-zero).
_ROW_D = (
    "test-t,Test,Grass,32,G,20240603,4,"
    "900005,7,Eps,29,1500,"
    "900006,8,Zeta,31,1200,"
    "6-0 6-0,3,R16,40,"
    "0,0,0,0,0,0,1,0,0,"
    "1,1,0,0,0,0,1,0,0"
)


def _write_fixture(tmp_path: Path, rows: list[str]) -> str:
    """Write a synthetic atp_matches_2024.csv into tmp_path/_raw/sackmann/."""
    raw = tmp_path / "_raw" / "sackmann"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "atp_matches_2024.csv").write_text(_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return str(tmp_path / "_raw")


def _build(tmp_path: Path, rows: list[str]) -> pd.DataFrame:
    raw_dir = _write_fixture(tmp_path, rows)
    out_path = tmp_path / "match_stats.parquet"
    dest = build_match_stats(raw_dir=raw_dir, out_path=str(out_path), tours=["atp"],
                             start_year=2024, end_year=2024)
    return pd.read_parquet(dest)


def _expected_event_id(date: str, tour: str, tid: str, p1: int, p2: int, mnum: int) -> str:
    """Replicate ingest_sackmann._make_event_id for the fixture."""
    return f"{date}-{tour}-{tid}-{p1}-{p2}-{mnum}"


# ---------------------------------------------------------------------------
# orientation
# ---------------------------------------------------------------------------

class TestOrientation:
    def test_lower_id_winner_maps_to_p1(self, tmp_path: Path) -> None:
        df = _build(tmp_path, [_ROW_A])
        r = df.iloc[0]
        # Row A: winner(900001) is the lower id -> winner stats become p1.
        assert r["p1_ace"] == 10.0 and r["p2_ace"] == 4.0
        assert r["p1_seed"] == 1.0 and r["p2_seed"] == 2.0
        assert r["p1_rank_points"] == 8000.0 and r["p2_rank_points"] == 5000.0

    def test_higher_id_winner_maps_to_p2(self, tmp_path: Path) -> None:
        df = _build(tmp_path, [_ROW_B])
        r = df.iloc[0]
        # Row B: winner(900050) > loser(900020) -> winner stats become p2.
        assert r["p2_ace"] == 20.0 and r["p1_ace"] == 6.0
        assert r["p2_seed"] == 3.0 and r["p1_seed"] == 4.0
        assert r["p2_rank_points"] == 7000.0 and r["p1_rank_points"] == 4000.0


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

class TestSchema:
    def test_all_expected_columns_present(self, tmp_path: Path) -> None:
        df = _build(tmp_path, [_ROW_A, _ROW_B])
        for col in OUT_COLS:
            assert col in df.columns, f"missing {col}"
        assert list(df.columns) == OUT_COLS

    def test_expected_columns_explicit(self, tmp_path: Path) -> None:
        df = _build(tmp_path, [_ROW_A])
        for c in ("event_id", "p1_ace", "p2_bpFaced", "p1_seed", "p2_age",
                  "p1_rank_points", "draw_size", "p1_1st_in_pct", "p2_df_rate"):
            assert c in df.columns


# ---------------------------------------------------------------------------
# rates
# ---------------------------------------------------------------------------

class TestRates:
    def test_1st_in_pct(self, tmp_path: Path) -> None:
        df = _build(tmp_path, [_ROW_A])
        r = df.iloc[0]
        assert r["p1_1st_in_pct"] == pytest.approx(60.0 / 100.0)   # 0.60
        assert r["p2_1st_in_pct"] == pytest.approx(50.0 / 90.0)

    def test_other_rates(self, tmp_path: Path) -> None:
        df = _build(tmp_path, [_ROW_A])
        r = df.iloc[0]
        assert r["p1_1st_win_pct"] == pytest.approx(45.0 / 60.0)
        assert r["p1_2nd_win_pct"] == pytest.approx(20.0 / (100.0 - 60.0))
        assert r["p1_bp_saved_pct"] == pytest.approx(5.0 / 8.0)
        assert r["p1_ace_rate"] == pytest.approx(10.0 / 100.0)
        assert r["p1_df_rate"] == pytest.approx(2.0 / 100.0)

    def test_rate_nan_when_svpt_zero(self, tmp_path: Path) -> None:
        df = _build(tmp_path, [_ROW_D])
        r = df.iloc[0]
        # svpt=0 -> divide-by-zero guarded to NaN, no crash.
        assert math.isnan(r["p1_1st_in_pct"])
        assert math.isnan(r["p1_ace_rate"])
        assert math.isnan(r["p1_df_rate"])


# ---------------------------------------------------------------------------
# join_key — event_id format matches the main ingest
# ---------------------------------------------------------------------------

class TestJoinKey:
    def test_event_id_matches_main_ingest_rule(self, tmp_path: Path) -> None:
        df = _build(tmp_path, [_ROW_A, _ROW_B])
        # Row A: p1=900001, p2=900002, match_num=1.
        a = df[df["p1_ace"] == 10.0].iloc[0]
        assert a["event_id"] == _expected_event_id("20240601", "atp", "test-t", 900001, 900002, 1)
        # Row B: oriented p1=900020 (loser), p2=900050 (winner), match_num=2.
        b = df[df["p2_ace"] == 20.0].iloc[0]
        assert b["event_id"] == _expected_event_id("20240601", "atp", "test-t", 900020, 900050, 2)

    def test_event_ids_unique(self, tmp_path: Path) -> None:
        df = _build(tmp_path, [_ROW_A, _ROW_B, _ROW_C, _ROW_D])
        assert df["event_id"].is_unique


# ---------------------------------------------------------------------------
# missing_cols — blank serve stats -> NaN, no crash
# ---------------------------------------------------------------------------

class TestMissingCols:
    def test_blank_serve_stats_yield_nan(self, tmp_path: Path) -> None:
        df = _build(tmp_path, [_ROW_C])
        r = df.iloc[0]
        for col in ("p1_ace", "p1_svpt", "p1_1stIn", "p2_bpSaved", "p1_1st_in_pct"):
            assert math.isnan(r[col]), f"{col} should be NaN"
        # contextual cols that ARE present still parse.
        assert r["p1_seed"] == 5.0 and r["draw_size"] == 32.0

    def test_absent_stat_column_does_not_crash(self, tmp_path: Path) -> None:
        # Drop the w_bpFaced/l_bpFaced columns entirely from the header.
        header = ",".join(c for c in _HEADER.split(",") if c not in ("w_bpFaced", "l_bpFaced"))
        # Rebuild row A without its last (bpFaced) field on each side.
        a = _ROW_A.split(",")
        # w_* block is the last 9 fields then l_* block last 9; drop index of bpFaced.
        # Simpler: just emit a minimal row aligned to the trimmed header.
        raw = tmp_path / "_raw" / "sackmann"
        raw.mkdir(parents=True, exist_ok=True)
        ncols = len(header.split(","))
        vals = ["test-t", "Test", "Hard", "32", "G", "20240601", "1",
                "900001", "1", "Alpha", "28", "8000",
                "900002", "2", "Beta", "30", "5000",
                "6-3 6-4", "3", "F", "80"]
        vals += ["10", "2", "100", "60", "45", "20", "12", "5"]   # w_* without bpFaced
        vals += ["4", "3", "90", "50", "40", "18", "11", "3"]     # l_* without bpFaced
        assert len(vals) == ncols, (len(vals), ncols)
        (raw / "atp_matches_2024.csv").write_text(header + "\n" + ",".join(vals) + "\n", encoding="utf-8")
        dest = build_match_stats(raw_dir=str(tmp_path / "_raw"),
                                 out_path=str(tmp_path / "ms.parquet"),
                                 tours=["atp"], start_year=2024, end_year=2024)
        df = pd.read_parquet(dest)
        # bpFaced column absent -> all-NaN, bp_saved_pct NaN, no crash.
        assert math.isnan(df.iloc[0]["p1_bpFaced"])
        assert math.isnan(df.iloc[0]["p1_bp_saved_pct"])


# ---------------------------------------------------------------------------
# 1:1 — N input rows -> N output rows
# ---------------------------------------------------------------------------

class TestOneToOne:
    def test_row_count_preserved(self, tmp_path: Path) -> None:
        df = _build(tmp_path, [_ROW_A, _ROW_B, _ROW_C, _ROW_D])
        assert len(df) == 4

    def test_single_row(self, tmp_path: Path) -> None:
        assert len(_build(tmp_path, [_ROW_A])) == 1


# ---------------------------------------------------------------------------
# no forbidden imports (F5 — adapter must not reach into src.* / nba / torch)
# ---------------------------------------------------------------------------

class TestNoForbiddenImports:
    def test_no_src_or_cross_adapter_import(self) -> None:
        import ast
        path = Path(__file__).parents[2] / "domains" / "tennis" / "ingest_sackmann_matchstats.py"
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("src."), alias.name
                    assert not alias.name.startswith("torch"), alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("src."), node.module
                assert not node.module.startswith("domains.basketball_nba"), node.module
                assert not node.module.startswith("torch"), node.module
