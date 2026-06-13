"""
tests/platform/test_nba_ingest_espn_odds.py
Unit + smoke tests for domains/basketball_nba/ingest_espn_odds.py.
Covers: extraction, alias map, malformed-skip, schema, determinism, provider priority.
"""
from __future__ import annotations

import json
import pathlib

import pandas as pd
import pytest

from domains.basketball_nba.ingest_espn_odds import build_odds

_REAL_SPREADS = pathlib.Path("data/cache/spreads")
_COLS = ["date", "home_team", "away_team", "home_ml", "away_ml", "total", "spread"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ev(home, away, spread, ou, hml, aml, provider="ESPN BET"):
    return {
        "id": "1",
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "team": {"abbreviation": home}},
                {"homeAway": "away", "team": {"abbreviation": away}},
            ],
            "odds": [{
                "provider": {"name": provider},
                "spread": spread, "overUnder": ou,
                "homeTeamOdds": {"moneyLine": hml},
                "awayTeamOdds": {"moneyLine": aml},
            }],
        }],
    }


def _file(events):
    return {"leagues": [], "provider": {}, "events": events}


def _build(tmp_path, files_events: dict) -> pd.DataFrame:
    """Write {filename: [events]} and run build_odds; return dataframe."""
    for fname, evs in files_events.items():
        (tmp_path / fname).write_text(json.dumps(_file(evs)), encoding="utf-8")
    out = build_odds(spreads_dir=tmp_path, out_path=tmp_path / "odds.parquet")
    return pd.read_parquet(out)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def test_basic_extraction(tmp_path):
    df = _build(tmp_path, {"20251021.json": [_ev("OKC", "HOU", -6.5, 224.5, -240, 200)]})
    assert len(df) == 1
    r = df.iloc[0]
    assert r["date"] == "2025-10-21"
    assert r["home_team"] == "OKC"
    assert r["away_team"] == "HOU"
    assert r["home_ml"] == pytest.approx(-240.0)
    assert r["away_ml"] == pytest.approx(200.0)
    assert r["total"] == pytest.approx(224.5)
    assert r["spread"] == pytest.approx(-6.5)


def test_alias_map_applied(tmp_path):
    aliases = [("NY", "NYK"), ("SA", "SAS"), ("GS", "GSW"),
               ("NO", "NOP"), ("UTAH", "UTA"), ("WSH", "WAS")]
    evs = [_ev(espn, "OKC", 5.0, 220.0, 180, -220) for espn, _ in aliases]
    df = _build(tmp_path, {"20251022.json": evs})
    assert len(df) == len(aliases)
    homes = df["home_team"].tolist()
    for _, canonical in aliases:
        assert canonical in homes, f"Missing {canonical} in {homes}"


def test_pass_through_unknown_abbr(tmp_path):
    df = _build(tmp_path, {"20251023.json": [_ev("LAL", "BOS", -3.0, 230.0, -150, 130)]})
    assert df.iloc[0]["home_team"] == "LAL"
    assert df.iloc[0]["away_team"] == "BOS"


# ---------------------------------------------------------------------------
# Skip-on-bad-input (no crash)
# ---------------------------------------------------------------------------

def test_event_no_odds_skipped(tmp_path):
    ev_no_odds = {"id": "9", "competitions": [{"competitors": [
        {"homeAway": "home", "team": {"abbreviation": "LAL"}},
        {"homeAway": "away", "team": {"abbreviation": "BOS"}},
    ], "odds": []}]}
    df = _build(tmp_path, {"20251024.json": [ev_no_odds, _ev("MIA", "CHI", -2.0, 215.0, -120, 100)]})
    assert len(df) == 1
    assert df.iloc[0]["home_team"] == "MIA"


def test_malformed_event_skipped(tmp_path):
    df = _build(tmp_path, {"20251025.json": [
        {"id": "x"},  # no competitions key
        _ev("PHX", "DEN", 1.5, 228.0, 130, -155),
    ]})
    assert len(df) == 1
    assert df.iloc[0]["home_team"] == "PHX"


def test_invalid_json_file_skipped(tmp_path):
    (tmp_path / "20251020.json").write_text("{not valid json", encoding="utf-8")
    df = _build(tmp_path, {"20251021.json": [_ev("ATL", "CHA", -4.0, 235.0, -175, 150)]})
    assert len(df) == 1


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_schema_exact(tmp_path):
    df = _build(tmp_path, {"20251026.json": [_ev("BKN", "NYK", 3.0, 222.0, 130, -150)]})
    assert list(df.columns) == _COLS


def test_empty_dir_empty_parquet(tmp_path):
    df = pd.read_parquet(build_odds(spreads_dir=tmp_path, out_path=tmp_path / "out.parquet"))
    assert list(df.columns) == _COLS
    assert len(df) == 0


# ---------------------------------------------------------------------------
# Provider priority
# ---------------------------------------------------------------------------

def test_espn_bet_preferred_over_draftkings(tmp_path):
    comp = {
        "competitors": [
            {"homeAway": "home", "team": {"abbreviation": "OKC"}},
            {"homeAway": "away", "team": {"abbreviation": "HOU"}},
        ],
        "odds": [
            {"provider": {"name": "DraftKings"}, "spread": 99.0, "overUnder": 999.0,
             "homeTeamOdds": {"moneyLine": 9999}, "awayTeamOdds": {"moneyLine": -9999}},
            {"provider": {"name": "ESPN BET"}, "spread": -6.5, "overUnder": 224.5,
             "homeTeamOdds": {"moneyLine": -240}, "awayTeamOdds": {"moneyLine": 200}},
        ],
    }
    (tmp_path / "20251027.json").write_text(json.dumps(_file([{"id": "1", "competitions": [comp]}])), encoding="utf-8")
    df = pd.read_parquet(build_odds(spreads_dir=tmp_path, out_path=tmp_path / "out.parquet"))
    assert df.iloc[0]["spread"] == pytest.approx(-6.5)
    assert df.iloc[0]["home_ml"] == pytest.approx(-240.0)


def test_live_odds_skipped_dk_used(tmp_path):
    comp = {
        "competitors": [
            {"homeAway": "home", "team": {"abbreviation": "OKC"}},
            {"homeAway": "away", "team": {"abbreviation": "HOU"}},
        ],
        "odds": [
            {"provider": {"name": "ESPN Bet - Live Odds"}, "spread": 1.5, "overUnder": 247.5,
             "homeTeamOdds": {}, "awayTeamOdds": {}},
            {"provider": {"name": "DraftKings"}, "spread": -6.5, "overUnder": 224.5,
             "homeTeamOdds": {"moneyLine": -240}, "awayTeamOdds": {"moneyLine": 200}},
        ],
    }
    (tmp_path / "20251028.json").write_text(json.dumps(_file([{"id": "2", "competitions": [comp]}])), encoding="utf-8")
    df = pd.read_parquet(build_odds(spreads_dir=tmp_path, out_path=tmp_path / "out.parquet"))
    assert len(df) == 1
    assert df.iloc[0]["spread"] == pytest.approx(-6.5)


# ---------------------------------------------------------------------------
# Determinism + sort
# ---------------------------------------------------------------------------

def test_deterministic(tmp_path):
    evs = [_ev("OKC", "HOU", -6.5, 224.5, -240, 200), _ev("LAL", "BOS", 2.5, 231.0, 120, -140)]
    (tmp_path / "20251021.json").write_text(json.dumps(_file(evs)), encoding="utf-8")
    out1, out2 = tmp_path / "a.parquet", tmp_path / "b.parquet"
    build_odds(spreads_dir=tmp_path, out_path=out1)
    build_odds(spreads_dir=tmp_path, out_path=out2)
    assert out1.read_bytes() == out2.read_bytes()


def test_sorted_by_date(tmp_path):
    df = _build(tmp_path, {
        "20251030.json": [_ev("GSW", "PHX", 1.0, 220.0, -110, -110)],
        "20251022.json": [_ev("MIA", "ORL", -4.0, 218.0, -170, 145)],
    })
    assert df.iloc[0]["date"] == "2025-10-22"
    assert df.iloc[1]["date"] == "2025-10-30"


# ---------------------------------------------------------------------------
# Real-data smoke (skipped if spreads dir absent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _REAL_SPREADS.exists(), reason="data/cache/spreads absent")
def test_real_data_smoke(tmp_path):
    out = build_odds(spreads_dir=_REAL_SPREADS, out_path=tmp_path / "odds.parquet")
    df = pd.read_parquet(out)
    assert len(df) > 100, f"Expected >100 rows, got {len(df)}"
    assert list(df.columns) == _COLS
    assert df["home_ml"].notna().mean() >= 0.80
    assert df["date"].str.match(r"^\d{4}-\d{2}-\d{2}$").all()
    assert "NYK" in df["home_team"].values or "NYK" in df["away_team"].values
