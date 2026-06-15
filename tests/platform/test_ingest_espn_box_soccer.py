"""tests/platform/test_ingest_espn_box_soccer.py — no network; http_get injected everywhere.

Synthetic soccer summary payloads mirror the real ESPN shape confirmed 2026-06-14:
  boxscore.teams[].statistics: flat list [{name, displayValue, value}]
  value is always null for soccer — parser must use displayValue.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd
import pytest

from domains.soccer.ingest_espn_box import (
    _STAT_FIELDS,
    _parse_summary,
    fetch_match,
    fetch_scoreboard,
    ingest_range,
)


# ---------------------------------------------------------------------------
# Synthetic payload builders
# ---------------------------------------------------------------------------

def _se(name: str, display_value) -> dict:
    """Single ESPN soccer stat entry; value always null per real API."""
    return {"name": name, "value": None, "displayValue": str(display_value)}


def _soccer_stats(shots: int = 12, shots_on: int = 4, possession: float = 55.0,
                  fouls: int = 10, corners: int = 5, yellow: int = 1, red: int = 0) -> list:
    return [
        _se("foulsCommitted", fouls), _se("yellowCards", yellow), _se("redCards", red),
        _se("offsides", 2), _se("wonCorners", corners), _se("saves", 3),
        _se("possessionPct", possession), _se("totalShots", shots),
        _se("shotsOnTarget", shots_on), _se("shotPct", round(shots_on / max(shots, 1), 1)),
        _se("penaltyKickGoals", 0), _se("penaltyKickShots", 0),
        _se("accuratePasses", 380), _se("totalPasses", 430), _se("passPct", 0.9),
        _se("accurateCrosses", 3), _se("totalCrosses", 11), _se("crossPct", 0.3),
        _se("totalLongBalls", 45), _se("accurateLongBalls", 20), _se("longballPct", 0.4),
        _se("blockedShots", 2), _se("effectiveTackles", 8), _se("totalTackles", 14),
        _se("tacklePct", 0.6), _se("interceptions", 5),
        _se("effectiveClearance", 12), _se("totalClearance", 12),
    ]


def _team_block(side: str, abbr: str, **kwargs) -> dict:
    return {
        "homeAway": side,
        "team": {"id": "1", "abbreviation": abbr, "displayName": abbr},
        "statistics": _soccer_stats(**kwargs),
    }


def _summary(eid: str = "999", home: str = "ARS", away: str = "BUR",
             hs: int = 1, as_: int = 0, league: str = "eng.1",
             status: str = "STATUS_FULL_TIME") -> dict:
    return {
        "boxscore": {"teams": [
            _team_block("home", home, shots=13, shots_on=3, possession=60.0),
            _team_block("away", away, shots=5, shots_on=0, possession=40.0),
        ]},
        "header": {"competitions": [{"competitors": [
            {"homeAway": "home", "team": {"abbreviation": home}, "score": str(hs)},
            {"homeAway": "away", "team": {"abbreviation": away}, "score": str(as_)},
        ], "status": {"type": {"name": status}}}]},
        "gameInfo": {"venue": {"fullName": "Emirates Stadium"}, "attendance": 60274},
    }


def _board(eids: list) -> dict:
    return {"events": [{"id": str(e), "name": f"Match {e}"} for e in eids]}


def _mock_get(eids: list, league: str = "eng.1") -> Callable:
    board = _board(eids)
    sums = {str(e): _summary(str(e), league=league) for e in eids}

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
    def test_basic_identity_and_score_fields(self):
        row = _parse_summary(_summary("123", "ARS", "BUR", 1, 0, "eng.1"), "123", "eng.1")
        assert row["event_id"] == "123" and row["league"] == "eng.1"
        assert row["home_abbr"] == "ARS" and row["away_abbr"] == "BUR"
        assert row["home_score"] == pytest.approx(1.0) and row["away_score"] == pytest.approx(0.0)
        assert row["status"] == "STATUS_FULL_TIME"
        assert row["venue"] == "Emirates Stadium"
        assert row["attendance"] == pytest.approx(60274.0)

    def test_all_28_stat_fields_both_sides(self):
        row = _parse_summary(_summary("124"), "124", "eng.1")
        for field in _STAT_FIELDS:
            assert f"home_{field}" in row, f"Missing home_{field}"
            assert f"away_{field}" in row, f"Missing away_{field}"

    def test_shot_and_possession_values(self):
        row = _parse_summary(_summary("125"), "125", "eng.1")
        assert row["home_totalShots"] == pytest.approx(13.0)
        assert row["home_shotsOnTarget"] == pytest.approx(3.0)
        assert row["away_totalShots"] == pytest.approx(5.0)
        assert row["away_shotsOnTarget"] == pytest.approx(0.0)
        total_poss = (row["home_possessionPct"] or 0.0) + (row["away_possessionPct"] or 0.0)
        assert abs(total_poss - 100.0) < 1.0

    def test_display_value_used_when_value_null(self):
        """Real API has value=null; parser must read displayValue."""
        p = _summary("126")
        assert p["boxscore"]["teams"][0]["statistics"][0]["value"] is None
        row = _parse_summary(p, "126", "eng.1")
        assert row["home_foulsCommitted"] is not None

    def test_league_field_stored(self):
        row = _parse_summary(_summary("127", league="ita.1"), "127", "ita.1")
        assert row["league"] == "ita.1"

    def test_empty_payload_returns_empty(self):
        assert _parse_summary({}, "0", "eng.1") == {}

    def test_missing_boxscore_returns_empty(self):
        assert _parse_summary({"header": {}, "gameInfo": {}}, "0", "eng.1") == {}

    def test_single_team_block_returns_empty(self):
        payload = {"boxscore": {"teams": [_team_block("home", "ARS")]},
                   "header": {"competitions": []}, "gameInfo": {}}
        assert _parse_summary(payload, "0", "eng.1") == {}

    def test_garbage_payload_returns_empty(self):
        assert _parse_summary({"random": "noise"}, "0", "eng.1") == {}

    def test_non_numeric_score_graceful(self):
        p = _summary("128")
        p["header"]["competitions"][0]["competitors"][0]["score"] = "TBD"
        row = _parse_summary(p, "128", "eng.1")
        assert row != {} and row["home_score"] is None and row["away_score"] == pytest.approx(0.0)

    def test_missing_attendance_is_none(self):
        p = _summary("129")
        del p["gameInfo"]["attendance"]
        row = _parse_summary(p, "129", "eng.1")
        assert row != {} and row["attendance"] is None

    def test_extra_unknown_stat_ignored(self):
        p = _summary("130")
        p["boxscore"]["teams"][0]["statistics"].append(
            {"name": "unknownStat", "value": None, "displayValue": "99"}
        )
        row = _parse_summary(p, "130", "eng.1")
        assert "home_unknownStat" not in row

    def test_partial_stats_produce_none_for_missing_fields(self):
        p = _summary("131")
        p["boxscore"]["teams"][0]["statistics"] = p["boxscore"]["teams"][0]["statistics"][:3]
        row = _parse_summary(p, "131", "eng.1")
        assert row != {} and row["home_totalShots"] is None


# ---------------------------------------------------------------------------
# fetch_match + fetch_scoreboard tests
# ---------------------------------------------------------------------------

class TestFetchMatch:
    def test_normal_flow(self):
        p = _summary("200", "ARS", "BUR")
        row = fetch_match("200", "eng.1", http_get=lambda url: p if "200" in url else {})
        assert row["event_id"] == "200" and row["home_abbr"] == "ARS" and row["league"] == "eng.1"

    def test_http_error_returns_empty(self):
        assert fetch_match("999", "eng.1", http_get=lambda url: {}) == {}

    def test_bad_payload_returns_empty(self):
        assert fetch_match("888", "eng.1", http_get=lambda url: {"unexpected": True}) == {}


class TestFetchScoreboard:
    def test_returns_event_list_with_league_and_date(self):
        events = fetch_scoreboard("20260518", "eng.1",
                                  http_get=lambda url: _board(["401", "402"]))
        assert len(events) == 2
        assert events[0]["league"] == "eng.1" and events[0]["date"] == "20260518"

    def test_empty_and_http_failure_return_empty(self):
        assert fetch_scoreboard("20260101", "eng.1",
                                http_get=lambda url: {"events": []}) == []
        assert fetch_scoreboard("20260101", "eng.1",
                                http_get=lambda url: {}) == []

    def test_off_season_graceful(self):
        events = fetch_scoreboard("20260614", "ger.1",
                                  http_get=lambda url: {"events": []})
        assert events == []


# ---------------------------------------------------------------------------
# ingest_range tests
# ---------------------------------------------------------------------------

class TestIngestRange:
    def test_writes_parquet_with_correct_rows(self, tmp_path):
        out = tmp_path / "soccer.parquet"
        ingest_range(["20260518"], leagues=["eng.1"],
                     http_get=_mock_get(["501", "502"]), out_path=out)
        df = pd.read_parquet(out)
        assert len(df) == 2 and set(df["event_id"]) == {"501", "502"}
        assert all(df["league"] == "eng.1")

    def test_key_columns_present(self, tmp_path):
        out = tmp_path / "soccer.parquet"
        ingest_range(["20260518"], leagues=["eng.1"],
                     http_get=_mock_get(["601"]), out_path=out)
        row = pd.read_parquet(out).iloc[0]
        for col in ("event_id", "league", "home_abbr", "away_abbr",
                    "home_totalShots", "home_possessionPct", "away_yellowCards",
                    "home_foulsCommitted", "home_wonCorners", "away_redCards"):
            assert col in row.index, f"Missing: {col}"

    def test_deduplication_on_rerun(self, tmp_path):
        out = tmp_path / "soccer.parquet"
        mg = _mock_get(["701"])
        ingest_range(["20260518"], leagues=["eng.1"], http_get=mg, out_path=out)
        ingest_range(["20260518"], leagues=["eng.1"], http_get=mg, out_path=out)
        assert len(pd.read_parquet(out)) == 1

    def test_same_event_id_different_leagues_stored_separately(self, tmp_path):
        out = tmp_path / "soccer.parquet"

        def _multi(url: str) -> dict:
            if "scoreboard" in url:
                return {"events": [{"id": "901", "name": "M"}]}
            if "901" in url and "eng.1" in url:
                return _summary("901", league="eng.1")
            if "901" in url and "esp.1" in url:
                return _summary("901", league="esp.1")
            return {}

        ingest_range(["20260518"], leagues=["eng.1", "esp.1"],
                     http_get=_multi, out_path=out)
        df = pd.read_parquet(out)
        assert len(df) == 2 and set(df["league"]) == {"eng.1", "esp.1"}

    def test_multi_date_accumulates(self, tmp_path):
        out = tmp_path / "soccer.parquet"
        ingest_range(["20260511"], leagues=["eng.1"],
                     http_get=_mock_get(["801"]), out_path=out)
        ingest_range(["20260518"], leagues=["eng.1"],
                     http_get=_mock_get(["802"]), out_path=out)
        assert set(pd.read_parquet(out)["event_id"]) == {"801", "802"}

    def test_date_column_stored(self, tmp_path):
        out = tmp_path / "soccer.parquet"
        ingest_range(["20260518"], leagues=["eng.1"],
                     http_get=_mock_get(["901"]), out_path=out)
        # date normalised to datetime64 so appends merge cleanly (see ingest_range fix)
        assert pd.Timestamp(pd.read_parquet(out).iloc[0]["date"]) == pd.Timestamp("2026-05-18")

    def test_all_leagues_off_season_no_parquet(self, tmp_path):
        out = tmp_path / "soccer.parquet"
        ingest_range(["20260614"],
                     leagues=["eng.1", "esp.1", "ita.1", "ger.1", "fra.1"],
                     http_get=lambda url: {"events": []} if "scoreboard" in url else {},
                     out_path=out)
        assert not out.exists()


# ---------------------------------------------------------------------------
# No-network guard
# ---------------------------------------------------------------------------

def test_import_does_not_call_network(monkeypatch):
    """Module-level reload must not trigger urllib.urlopen."""
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("network!")))
    import importlib
    import domains.soccer.ingest_espn_box as mod
    importlib.reload(mod)
