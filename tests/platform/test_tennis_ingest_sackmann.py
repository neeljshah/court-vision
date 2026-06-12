"""tests.platform.test_tennis_ingest_sackmann — Offline tests for ingest_sackmann.py.

ALL tests are OFFLINE. urllib.request.urlopen is monkeypatched to RAISE in every test
so any live network call causes immediate failure. No src.* imports. No torch.
Fixtures are synthetic rows (player IDs >= 900000) — nothing from the CC BY-NC-SA corpus.
"""
from __future__ import annotations

import datetime as dt
import io
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from domains.tennis.ingest_sackmann import (
    MATCHES_REQUIRED_COLS, PLAYERS_REQUIRED_COLS, ROUND_ORDER,
    _retirement_flag, _normalize_surface,
    _transform_matches, _transform_players,
    build_matches, build_players, load_matches,
)

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "tennis"
_MATCHES_CSV = _FIXTURES / "sackmann_matches_sample.csv"
_PLAYERS_CSV = _FIXTURES / "sackmann_players_sample.csv"


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raise unconditionally on any urllib.request.urlopen call (network firewall)."""
    import urllib.request

    def _no_network(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Live network call in test — forbidden. urlopen monkeypatched.")

    monkeypatch.setattr(urllib.request, "urlopen", _no_network)


def _load_atp_raw() -> pd.DataFrame:
    df = pd.read_csv(_MATCHES_CSV, dtype=str, low_memory=False)
    atp = df[~df["tourney_id"].str.startswith("wta", na=False)].copy()
    atp["_tour"] = "atp"
    return atp


def _load_all_raw() -> pd.DataFrame:
    df = pd.read_csv(_MATCHES_CSV, dtype=str, low_memory=False)
    atp = df[~df["tourney_id"].str.startswith("wta", na=False)].copy()
    atp["_tour"] = "atp"
    wta = df[df["tourney_id"].str.startswith("wta", na=False)].copy()
    wta["_tour"] = "wta"
    return pd.concat([atp, wta], ignore_index=True)


def _setup_raw_dir(tmp_path: Path) -> str:
    raw = tmp_path / "_raw" / "sackmann"
    raw.mkdir(parents=True)
    shutil.copy(_MATCHES_CSV, raw / "atp_matches_2024.csv")
    shutil.copy(_MATCHES_CSV, raw / "wta_matches_2024.csv")
    shutil.copy(_PLAYERS_CSV, raw / "atp_players.csv")
    shutil.copy(_PLAYERS_CSV, raw / "wta_players.csv")
    return str(tmp_path / "_raw")


# ---------------------------------------------------------------------------
# 1. Column contract + dtypes
# ---------------------------------------------------------------------------

class TestMatchesContract:
    def test_required_columns_present(self) -> None:
        out = _transform_matches(_load_all_raw(), "/tmp/_unused")
        for col in MATCHES_REQUIRED_COLS:
            assert col in out.columns, f"Missing: {col}"

    def test_no_leak_columns(self) -> None:
        out = _transform_matches(_load_all_raw(), "/tmp/_unused")
        for leaked in ("winner_id", "loser_id", "winner_name", "loser_name"):
            assert leaked not in out.columns, f"Leak column in output: {leaked}"

    def test_dtypes(self) -> None:
        out = _transform_matches(_load_all_raw(), "/tmp/_unused")
        assert out["winner"].dtype == "int8"
        assert out["best_of"].dtype == "int8"
        assert out["retirement"].dtype == bool
        assert out["minutes"].dtype == "float32"
        assert pd.api.types.is_integer_dtype(out["p1_id"])

    def test_surface_valid(self) -> None:
        out = _transform_matches(_load_all_raw(), "/tmp/_unused")
        valid = {"Hard", "Clay", "Grass", "Carpet", "Unknown"}
        assert set(out["surface"].unique()).issubset(valid)

    def test_winner_values_1_or_2(self) -> None:
        out = _transform_matches(_load_all_raw(), "/tmp/_unused")
        assert set(out["winner"].unique()).issubset({1, 2})


class TestPlayersContract:
    def test_required_columns(self) -> None:
        raw = pd.read_csv(_PLAYERS_CSV, dtype=str)
        raw["tour"] = "atp"
        out = _transform_players(raw, "/tmp/_unused")
        for col in PLAYERS_REQUIRED_COLS:
            assert col in out.columns

    def test_full_name_concat(self) -> None:
        raw = pd.read_csv(_PLAYERS_CSV, dtype=str)
        raw["tour"] = "atp"
        out = _transform_players(raw, "/tmp/_unused")
        row = out[out["player_id"] == 900001].iloc[0]
        assert row["full_name"] == "Alpha A"

    def test_height_float32(self) -> None:
        raw = pd.read_csv(_PLAYERS_CSV, dtype=str)
        raw["tour"] = "atp"
        out = _transform_players(raw, "/tmp/_unused")
        assert out["height"].dtype == "float32"


# ---------------------------------------------------------------------------
# 2. Orientation rule: p1_id = min(winner_id, loser_id) — outcome-blind
# ---------------------------------------------------------------------------

class TestOrientationRule:
    def test_p1_always_leq_p2(self) -> None:
        out = _transform_matches(_load_all_raw(), "/tmp/_unused")
        valid = out.dropna(subset=["p1_id", "p2_id"])
        assert (valid["p1_id"].astype(int) <= valid["p2_id"].astype(int)).all()

    def test_winner_1_when_lower_id_won(self) -> None:
        out = _transform_matches(_load_atp_raw(), "/tmp/_unused")
        # match_num=1: winner=900001, loser=900002 → p1=900001(winner) → winner=1
        row = out[(out["p1_id"] == 900001) & (out["p2_id"] == 900002)]
        assert len(row) >= 1
        assert (row["winner"] == 1).all()

    def test_winner_2_when_higher_id_won(self) -> None:
        """When loser_id < winner_id, p1=loser and winner=2."""
        csv_data = (
            "tourney_id,tourney_name,surface,draw_size,tourney_level,tourney_date,"
            "match_num,winner_id,winner_name,winner_hand,winner_ht,winner_ioc,"
            "winner_age,winner_rank,winner_rank_points,loser_id,loser_name,"
            "loser_hand,loser_ht,loser_ioc,loser_age,loser_rank,loser_rank_points,"
            "score,best_of,round,minutes\n"
            "test-t,Test,Hard,32,G,20240601,1,900050,Big Player,R,185,USA,28,2,8000,"
            "900020,Small Player,L,175,GBR,30,1,9000,6-3 6-4,3,F,80\n"
        )
        df_raw = pd.read_csv(io.StringIO(csv_data), dtype=str)
        df_raw["_tour"] = "atp"
        out = _transform_matches(df_raw, "/tmp/_unused")
        assert out.iloc[0]["p1_id"] == 900020
        assert out.iloc[0]["p2_id"] == 900050
        assert out.iloc[0]["winner"] == 2


# ---------------------------------------------------------------------------
# 3. Event ID uniqueness + retirement flagging
# ---------------------------------------------------------------------------

class TestEventIdAndRetirement:
    def test_event_ids_unique(self) -> None:
        out = _transform_matches(_load_all_raw(), "/tmp/_unused")
        assert out["event_id"].is_unique

    def test_retirement_detected(self) -> None:
        assert _retirement_flag("6-3 7-5 RET") is True
        assert _retirement_flag("W/O") is True
        assert _retirement_flag("6-3 6-4") is False
        assert _retirement_flag("") is False

    def test_fixture_has_retirement_and_walkover(self) -> None:
        out = _transform_matches(_load_atp_raw(), "/tmp/_unused")
        assert out["retirement"].sum() >= 1
        assert out["score"].str.upper().str.contains("W/O", na=False).sum() >= 1


# ---------------------------------------------------------------------------
# 4. Surface normalization + missing surface → Unknown
# ---------------------------------------------------------------------------

class TestSurface:
    def test_na_becomes_unknown(self) -> None:
        assert _normalize_surface(None) == "Unknown"
        assert _normalize_surface(float("nan")) == "Unknown"
        assert _normalize_surface("") == "Unknown"

    def test_ao_missing_surface_unknown(self) -> None:
        out = _transform_matches(_load_atp_raw(), "/tmp/_unused")
        ao = out[out["tourney_id"].str.contains("australian", na=False)]
        if len(ao) > 0:
            assert (ao["surface"] == "Unknown").all()


# ---------------------------------------------------------------------------
# 5. Pinned chronological sort
# ---------------------------------------------------------------------------

class TestSort:
    def test_dates_non_decreasing(self) -> None:
        out = _transform_matches(_load_all_raw(), "/tmp/_unused")
        dates = list(out.dropna(subset=["date"])["date"])
        assert dates == sorted(dates)

    def test_round_order_within_tourney(self) -> None:
        out = _transform_matches(_load_atp_raw(), "/tmp/_unused")
        wimb = out[out["tourney_id"] == "2024-wimbledon"].copy()
        if len(wimb) > 1:
            ords = [ROUND_ORDER.get(r, 6) for r in wimb["round"]]
            assert ords == sorted(ords)


# ---------------------------------------------------------------------------
# 6. Idempotent rebuild + parquet roundtrip
# ---------------------------------------------------------------------------

class TestIdempotentAndParquet:
    def test_rebuild_identical(self, tmp_path: Path) -> None:
        raw_dir = _setup_raw_dir(tmp_path)
        out_dir = str(tmp_path / "out")
        df1 = build_matches(raw_dir=raw_dir, out_dir=out_dir, tours=["atp"])
        df2 = build_matches(raw_dir=raw_dir, out_dir=out_dir, tours=["atp"])
        pd.testing.assert_frame_equal(df1, df2)

    def test_two_independent_builds_identical(self, tmp_path: Path) -> None:
        r1, r2 = _setup_raw_dir(tmp_path / "a"), _setup_raw_dir(tmp_path / "b")
        d1 = build_matches(raw_dir=r1, out_dir=str(tmp_path / "o1"), tours=["atp"])
        d2 = build_matches(raw_dir=r2, out_dir=str(tmp_path / "o2"), tours=["atp"])
        pd.testing.assert_frame_equal(d1.reset_index(drop=True), d2.reset_index(drop=True))

    def test_parquet_readable_via_load_matches(self, tmp_path: Path) -> None:
        raw_dir = _setup_raw_dir(tmp_path)
        out_dir = str(tmp_path / "out")
        df = build_matches(raw_dir=raw_dir, out_dir=out_dir, tours=["atp"])
        reloaded = load_matches(str(tmp_path / "out" / "matches.parquet"))
        assert len(reloaded) == len(df)
        for col in MATCHES_REQUIRED_COLS:
            assert col in reloaded.columns

    def test_players_parquet_roundtrip(self, tmp_path: Path) -> None:
        raw_dir = _setup_raw_dir(tmp_path)
        out_dir = str(tmp_path / "out")
        df = build_players(raw_dir=raw_dir, out_dir=out_dir)
        assert len(df) >= 20
        reloaded = pd.read_parquet(str(tmp_path / "out" / "players.parquet"))
        assert len(reloaded) == len(df)


# ---------------------------------------------------------------------------
# 7. No src.* / domains.nba / torch imports (static AST check)
# ---------------------------------------------------------------------------

class TestNoForbiddenImports:
    def test_no_src_or_cross_adapter_import(self) -> None:
        import ast
        src = (Path(__file__).parents[2] / "domains" / "tennis" / "ingest_sackmann.py").read_text("utf-8")
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("src."), f"Forbidden: import {alias.name}"
                    assert not alias.name.startswith("torch"), f"Forbidden: import {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("src."), f"Forbidden: from {node.module}"
                assert not node.module.startswith("domains.basketball_nba"), f"F5: from {node.module}"
                assert not node.module.startswith("torch"), f"Forbidden: from {node.module}"
