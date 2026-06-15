"""tests/platform/test_ingest_espn_box.py — no network; http_get injected everywhere."""
from __future__ import annotations

from typing import Callable, Optional

import pandas as pd
import pytest

from domains.mlb.ingest_espn_box import (
    _BATTING_FIELDS,
    _parse_summary,
    fetch_box,
    fetch_scoreboard,
    ingest_range,
)


# ---------------------------------------------------------------------------
# Synthetic ESPN payload builders
# ---------------------------------------------------------------------------

def _se(name: str, value, display: str = "") -> dict:
    return {"name": name, "value": value, "displayValue": display or str(value)}


def _sg(group: str, stats: list) -> dict:
    return {"name": group, "stats": stats}


def _bat_stats(runs: int, hits: int) -> list:
    fixed = {
        "homeRuns": 2, "doubles": 1, "triples": 0, "atBats": 30,
        "plateAppearances": 33, "walks": 3, "strikeouts": 7, "stolenBases": 1,
        "caughtStealing": 0, "hitByPitch": 0, "sacFlies": 1, "sacHits": 0,
        "runnersLeftOnBase": 6, "groundBalls": 5, "flyBalls": 3,
        "totalBases": 14, "extraBaseHits": 3, "pitches": 120, "GIDPs": 1,
    }
    return ([_se("runs", runs), _se("hits", hits), _se("RBIs", runs)]
            + [_se(k, v) for k, v in fixed.items()])


def _pit_stats(er: int) -> list:
    fixed = {
        "wins": 1, "losses": 0, "saves": 0, "hits": 8, "homeRuns": 1,
        "walks": 2, "strikeouts": 9, "battersFaced": 32, "pitches": 130,
        "strikes": 86, "wildPitches": 0, "balks": 0, "groundBalls": 8,
        "flyBalls": 7, "qualityStarts": 1, "completeGames": 0, "shutouts": 0,
    }
    return ([_se("earnedRuns", er), _se("runs", er), _se("innings", 9.0, "9.0")]
            + [_se(k, v) for k, v in fixed.items()])


def _fld_stats(errors: int) -> list:
    fixed = {"putouts": 27, "assists": 9, "doublePlays": 2,
             "passedBalls": 0, "outfieldAssists": 0, "triplePlays": 0}
    return [_se("errors", errors)] + [_se(k, v) for k, v in fixed.items()]


def _team_block(side: str, abbr: str, bat_runs: int = 5, bat_hits: int = 8,
                pit_er: int = 3, fld_errors: int = 1) -> dict:
    return {
        "homeAway": side, "team": {"id": "1", "abbreviation": abbr, "displayName": abbr},
        "statistics": [_sg("batting", _bat_stats(bat_runs, bat_hits)),
                       _sg("pitching", _pit_stats(pit_er)),
                       _sg("fielding", _fld_stats(fld_errors))],
    }


def _summary(eid: str = "999", ha: str = "NYM", aa: str = "CHC",
             hs: int = 4, as_: int = 2, status: str = "STATUS_FINAL") -> dict:
    return {
        "boxscore": {"teams": [
            _team_block("away", aa, bat_runs=as_, bat_hits=6, pit_er=hs),
            _team_block("home", ha, bat_runs=hs, bat_hits=9, pit_er=as_),
        ]},
        "header": {"competitions": [{"competitors": [
            {"homeAway": "home", "team": {"abbreviation": ha}, "score": str(hs)},
            {"homeAway": "away", "team": {"abbreviation": aa}, "score": str(as_)},
        ], "status": {"type": {"name": status}}}]},
        "gameInfo": {"venue": {"fullName": "Citi Field"}, "attendance": 28000},
    }


def _board(eids: list) -> dict:
    return {"events": [{"id": str(e), "name": f"Game {e}"} for e in eids]}


def _mock_get(eids: list) -> Callable:
    """Build an injected http_get serving a scoreboard + summaries for eids."""
    board = _board(eids)
    sums = {str(e): _summary(str(e), "HOM", "AWY", hs=4, as_=3) for e in eids}

    def _get(url: str) -> dict:
        if "scoreboard" in url:
            return board
        for eid, s in sums.items():
            if eid in url:
                return s
        return {}
    return _get


# ---------------------------------------------------------------------------
# _parse_summary tests
# ---------------------------------------------------------------------------

class TestParseSummary:
    def test_basic_fields_present(self):
        row = _parse_summary(_summary("123", "NYM", "CHC", 5, 3), "123")
        assert row["event_id"] == "123"
        assert row["home_abbr"] == "NYM" and row["away_abbr"] == "CHC"
        assert row["home_score"] == pytest.approx(5.0)
        assert row["away_score"] == pytest.approx(3.0)
        assert row["status"] == "STATUS_FINAL"
        assert row["venue"] == "Citi Field"
        assert row["attendance"] == pytest.approx(28000.0)

    def test_batting_stats_extracted(self):
        row = _parse_summary(_summary("124", "LAD", "SF", 7, 2), "124")
        assert row["home_bat_runs"] == pytest.approx(7.0)
        assert row["home_bat_hits"] == pytest.approx(9.0)
        assert row["home_bat_homeRuns"] == pytest.approx(2.0)
        assert row["away_bat_runs"] == pytest.approx(2.0)
        assert row["away_bat_hits"] == pytest.approx(6.0)

    def test_pitching_stats_extracted(self):
        row = _parse_summary(_summary("125", "HOU", "TEX", 4, 1), "125")
        assert row["home_pit_wins"] == pytest.approx(1.0)
        assert row["home_pit_innings"] == pytest.approx(9.0)
        assert row["home_pit_earnedRuns"] == pytest.approx(1.0)

    def test_fielding_stats_extracted(self):
        row = _parse_summary(_summary("126", "BOS", "NYY"), "126")
        assert row["home_fld_putouts"] == pytest.approx(27.0)
        assert row["away_fld_doublePlays"] == pytest.approx(2.0)

    def test_empty_payload_returns_empty(self):
        assert _parse_summary({}, "0") == {}

    def test_missing_boxscore_returns_empty(self):
        assert _parse_summary({"header": {}, "gameInfo": {}}, "0") == {}

    def test_single_team_returns_empty(self):
        payload = {"boxscore": {"teams": [_team_block("home", "NYM")]},
                   "header": {"competitions": []}, "gameInfo": {}}
        assert _parse_summary(payload, "0") == {}

    def test_garbage_payload_returns_empty(self):
        assert _parse_summary({"random": "noise"}, "0") == {}

    def test_none_scores_handled_gracefully(self):
        p = _summary("127", "MIA", "ATL")
        p["header"]["competitions"][0]["competitors"][0]["score"] = "TBD"
        row = _parse_summary(p, "127")
        assert row != {} and row["event_id"] == "127"

    def test_missing_stat_group_ok(self):
        p = _summary("128", "SEA", "OAK")
        home = p["boxscore"]["teams"][1]
        home["statistics"] = [s for s in home["statistics"] if s["name"] != "pitching"]
        row = _parse_summary(p, "128")
        assert row != {} and row["home_bat_runs"] is not None
        assert row.get("home_pit_wins") is None

    def test_all_batting_fields_present(self):
        row = _parse_summary(_summary("129", "COL", "ARI"), "129")
        for f in _BATTING_FIELDS:
            assert f"home_bat_{f}" in row, f"Missing home_bat_{f}"
            assert f"away_bat_{f}" in row, f"Missing away_bat_{f}"


# ---------------------------------------------------------------------------
# fetch_box tests
# ---------------------------------------------------------------------------

class TestFetchBox:
    def test_normal_flow(self):
        p = _summary("200", "MIN", "STL", 6, 9)
        row = fetch_box("200", http_get=lambda url: p if "200" in url else {})
        assert row["event_id"] == "200" and row["home_abbr"] == "MIN"

    def test_http_error_returns_empty(self):
        assert fetch_box("999", http_get=lambda url: {}) == {}

    def test_bad_payload_returns_empty(self):
        assert fetch_box("888", http_get=lambda url: {"unexpected": True}) == {}


# ---------------------------------------------------------------------------
# fetch_scoreboard tests
# ---------------------------------------------------------------------------

class TestFetchScoreboard:
    def test_returns_event_list(self):
        events = fetch_scoreboard("20260101", http_get=lambda url: _board(["401", "402", "403"]))
        assert len(events) == 3
        assert {e["event_id"] for e in events} == {"401", "402", "403"}

    def test_empty_scoreboard(self):
        assert fetch_scoreboard("20260101", http_get=lambda url: {"events": []}) == []

    def test_http_failure_returns_empty_list(self):
        assert fetch_scoreboard("20260101", http_get=lambda url: {}) == []


# ---------------------------------------------------------------------------
# ingest_range tests
# ---------------------------------------------------------------------------

class TestIngestRange:
    def test_writes_parquet(self, tmp_path):
        out = tmp_path / "espn.parquet"
        path = ingest_range(["20260101"], http_get=_mock_get(["501", "502"]), out_path=out)
        assert path == out and out.exists()
        df = pd.read_parquet(out)
        assert len(df) == 2 and set(df["event_id"]) == {"501", "502"}

    def test_correct_columns_present(self, tmp_path):
        out = tmp_path / "espn.parquet"
        ingest_range(["20260101"], http_get=_mock_get(["601"]), out_path=out)
        row = pd.read_parquet(out).iloc[0]
        for col in ("event_id", "home_abbr", "away_abbr", "home_bat_runs",
                    "home_pit_strikeouts", "away_fld_errors"):
            assert col in row.index

    def test_deduplication_on_rerun(self, tmp_path):
        out = tmp_path / "espn.parquet"
        mg = _mock_get(["701"])
        ingest_range(["20260101"], http_get=mg, out_path=out)
        ingest_range(["20260101"], http_get=mg, out_path=out)
        assert len(pd.read_parquet(out)) == 1

    def test_multi_date(self, tmp_path):
        out = tmp_path / "espn.parquet"
        ingest_range(["20260101"], http_get=_mock_get(["801"]), out_path=out)
        ingest_range(["20260102"], http_get=_mock_get(["802"]), out_path=out)
        assert set(pd.read_parquet(out)["event_id"]) == {"801", "802"}

    def test_empty_scoreboard_writes_nothing(self, tmp_path):
        out = tmp_path / "espn.parquet"
        ingest_range(["20260101"], http_get=lambda url: {"events": []} if "scoreboard" in url else {}, out_path=out)
        assert not out.exists()

    def test_date_column_stored(self, tmp_path):
        out = tmp_path / "espn.parquet"
        ingest_range(["20260610"], http_get=_mock_get(["901"]), out_path=out)
        # date normalised to datetime64 so appends merge cleanly (see ingest_range fix)
        assert pd.Timestamp(pd.read_parquet(out).iloc[0]["date"]) == pd.Timestamp("2026-06-10")


# ---------------------------------------------------------------------------
# No-network guard
# ---------------------------------------------------------------------------

def test_import_does_not_call_network(monkeypatch):
    """Module-level reload must not trigger urllib.urlopen."""
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("network!")))
    import importlib
    import domains.mlb.ingest_espn_box as mod
    importlib.reload(mod)  # passes if no network call at module level
