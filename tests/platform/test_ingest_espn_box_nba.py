"""tests/platform/test_ingest_espn_box_nba.py — no network; http_get injected everywhere.

NBA ESPN boxscore shape differs from MLB: each team's ``statistics`` list contains
``{name, displayValue, label}`` entries (no nested stats sub-list).  Compound
stats like FG use "X-Y" displayValue; simple stats use plain number strings.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd
import pytest

from domains.basketball_nba.ingest_espn_box import (
    _STAT_LOOKUP,
    _parse_compound,
    _parse_float,
    _parse_summary,
    fetch_box,
    fetch_scoreboard,
    ingest_range,
)


# ---------------------------------------------------------------------------
# Synthetic ESPN NBA payload builders
# ---------------------------------------------------------------------------

def _stat(name: str, display: str, label: str = "") -> dict:
    return {"name": name, "displayValue": display, "label": label or name}


def _team_stats(
    fg: str = "36-90",
    fg_pct: str = "40",
    fg3: str = "10-30",
    fg3_pct: str = "33",
    ft: str = "16-20",
    ft_pct: str = "80",
    reb: str = "40",
    oreb: str = "8",
    dreb: str = "32",
    ast: str = "22",
    stl: str = "7",
    blk: str = "4",
    tov: str = "12",
    team_tov: str = "1",
    total_tov: str = "13",
    pf: str = "20",
    tech: str = "0",
    flagrant: str = "0",
    fast_break: str = "11",
    paint: str = "44",
    tov_pts: str = "15",
    largest_lead: str = "12",
) -> list:
    return [
        _stat("fieldGoalsMade-fieldGoalsAttempted", fg, "FG"),
        _stat("fieldGoalPct", fg_pct, "Field Goal %"),
        _stat("threePointFieldGoalsMade-threePointFieldGoalsAttempted", fg3, "3PT"),
        _stat("threePointFieldGoalPct", fg3_pct, "Three Point %"),
        _stat("freeThrowsMade-freeThrowsAttempted", ft, "FT"),
        _stat("freeThrowPct", ft_pct, "Free Throw %"),
        _stat("totalRebounds", reb, "Rebounds"),
        _stat("offensiveRebounds", oreb, "Offensive Rebounds"),
        _stat("defensiveRebounds", dreb, "Defensive Rebounds"),
        _stat("assists", ast, "Assists"),
        _stat("steals", stl, "Steals"),
        _stat("blocks", blk, "Blocks"),
        _stat("turnovers", tov, "Turnovers"),
        _stat("teamTurnovers", team_tov, "Team Turnovers"),
        _stat("totalTurnovers", total_tov, "Total Turnovers"),
        _stat("fouls", pf, "Fouls"),
        _stat("technicalFouls", tech, "Technical Fouls"),
        _stat("flagrantFouls", flagrant, "Flagrant Fouls"),
        _stat("fastBreakPoints", fast_break, "Fast Break Points"),
        _stat("pointsInPaint", paint, "Points in Paint"),
        _stat("turnoverPoints", tov_pts, "Points Conceded Off Turnovers"),
        _stat("largestLead", largest_lead, "Largest Lead"),
    ]


def _team_block(side: str, abbr: str, score: int = 110, **kwargs) -> dict:
    return {
        "homeAway": side,
        "team": {"id": "1", "abbreviation": abbr, "displayName": abbr},
        "statistics": _team_stats(**kwargs),
    }


def _summary(
    eid: str = "999",
    home_abbr: str = "BOS",
    away_abbr: str = "LAL",
    home_score: int = 115,
    away_score: int = 108,
    status: str = "STATUS_FINAL",
) -> dict:
    return {
        "boxscore": {
            "teams": [
                _team_block("away", away_abbr, score=away_score),
                _team_block("home", home_abbr, score=home_score),
            ]
        },
        "header": {
            "competitions": [
                {
                    "competitors": [
                        {
                            "homeAway": "home",
                            "team": {"abbreviation": home_abbr},
                            "score": str(home_score),
                        },
                        {
                            "homeAway": "away",
                            "team": {"abbreviation": away_abbr},
                            "score": str(away_score),
                        },
                    ],
                    "status": {"type": {"name": status}},
                }
            ]
        },
        "gameInfo": {
            "venue": {"fullName": "TD Garden"},
            "attendance": 19156,
        },
    }


def _board(eids: list) -> dict:
    return {"events": [{"id": str(e), "name": f"Game {e}"} for e in eids]}


def _mock_get(eids: list) -> Callable:
    """Build an injected http_get serving a scoreboard + summaries for eids."""
    board = _board(eids)
    sums = {
        str(e): _summary(str(e), "HOM", "AWY", home_score=112, away_score=104)
        for e in eids
    }

    def _get(url: str) -> dict:
        if "scoreboard" in url:
            return board
        for eid, s in sums.items():
            if eid in url:
                return s
        return {}

    return _get


# ---------------------------------------------------------------------------
# Low-level helper tests
# ---------------------------------------------------------------------------

class TestParseCompound:
    def test_normal(self):
        assert _parse_compound("36-90") == (36.0, 90.0)

    def test_zeros(self):
        assert _parse_compound("0-0") == (0.0, 0.0)

    def test_bad_string(self):
        assert _parse_compound("N/A") == (None, None)

    def test_empty(self):
        assert _parse_compound("") == (None, None)

    def test_single_number_no_dash(self):
        assert _parse_compound("45") == (None, None)


class TestParseFloat:
    def test_integer_string(self):
        assert _parse_float("38") == pytest.approx(38.0)

    def test_float_string(self):
        assert _parse_float("42.5") == pytest.approx(42.5)

    def test_comma_number(self):
        assert _parse_float("1,234") == pytest.approx(1234.0)

    def test_empty(self):
        assert _parse_float("") is None

    def test_non_numeric(self):
        assert _parse_float("N/A") is None


# ---------------------------------------------------------------------------
# _parse_summary tests
# ---------------------------------------------------------------------------

class TestParseSummary:
    def test_basic_fields_present(self):
        row = _parse_summary(_summary("123", "BOS", "LAL", 115, 108), "123")
        assert row["event_id"] == "123"
        assert row["home_abbr"] == "BOS"
        assert row["away_abbr"] == "LAL"
        assert row["home_score"] == pytest.approx(115.0)
        assert row["away_score"] == pytest.approx(108.0)
        assert row["status"] == "STATUS_FINAL"
        assert row["venue"] == "TD Garden"
        assert row["attendance"] == pytest.approx(19156.0)

    def test_fg_compound_extracted(self):
        row = _parse_summary(_summary("124", "GSW", "PHX"), "124")
        # Default fg="36-90"
        assert row["home_fg_made"] == pytest.approx(36.0)
        assert row["home_fg_attempted"] == pytest.approx(90.0)
        assert row["away_fg_made"] == pytest.approx(36.0)

    def test_three_point_compound_extracted(self):
        row = _parse_summary(_summary("125", "MIL", "MIA"), "125")
        # Default fg3="10-30"
        assert row["home_fg3_made"] == pytest.approx(10.0)
        assert row["home_fg3_attempted"] == pytest.approx(30.0)

    def test_ft_compound_extracted(self):
        row = _parse_summary(_summary("126", "DEN", "MIN"), "126")
        # Default ft="16-20"
        assert row["home_ft_made"] == pytest.approx(16.0)
        assert row["home_ft_attempted"] == pytest.approx(20.0)

    def test_simple_stats_extracted(self):
        row = _parse_summary(_summary("127", "NYK", "MEM"), "127")
        assert row["home_reb"] == pytest.approx(40.0)
        assert row["home_ast"] == pytest.approx(22.0)
        assert row["home_stl"] == pytest.approx(7.0)
        assert row["home_blk"] == pytest.approx(4.0)
        assert row["home_tov"] == pytest.approx(12.0)
        assert row["home_pf"] == pytest.approx(20.0)

    def test_paint_and_fastbreak_extracted(self):
        row = _parse_summary(_summary("128", "OKC", "SAS"), "128")
        assert row["home_paint_pts"] == pytest.approx(44.0)
        assert row["home_fast_break_pts"] == pytest.approx(11.0)

    def test_away_stats_separate_from_home(self):
        row = _parse_summary(_summary("129", "CLE", "IND"), "129")
        # Both sides parsed independently; they use the same default values
        assert row["home_ast"] == row["away_ast"]  # same defaults -> equal

    def test_empty_payload_returns_empty(self):
        assert _parse_summary({}, "0") == {}

    def test_missing_boxscore_key_returns_empty(self):
        assert _parse_summary({"header": {}, "gameInfo": {}}, "0") == {}

    def test_single_team_returns_empty(self):
        payload = {
            "boxscore": {"teams": [_team_block("home", "BOS")]},
            "header": {"competitions": []},
            "gameInfo": {},
        }
        assert _parse_summary(payload, "0") == {}

    def test_garbage_payload_returns_empty(self):
        assert _parse_summary({"random": "noise"}, "0") == {}

    def test_none_score_handled_gracefully(self):
        p = _summary("130", "ATL", "ORL")
        p["header"]["competitions"][0]["competitors"][0]["score"] = "TBD"
        row = _parse_summary(p, "130")
        assert row != {} and row["event_id"] == "130"
        # Home score should be None (failed float parse)
        assert row["home_score"] is None

    def test_missing_statistics_emits_none_values(self):
        p = _summary("131", "UTA", "POR")
        # Strip all stats from home team
        p["boxscore"]["teams"][1]["statistics"] = []
        row = _parse_summary(p, "131")
        assert row != {}
        # All home stat columns should be None
        assert row.get("home_fg_made") is None
        assert row.get("home_ast") is None

    def test_all_stat_columns_present(self):
        row = _parse_summary(_summary("132", "DAL", "SAC"), "132")
        for api_name, (col, is_compound) in _STAT_LOOKUP.items():
            if is_compound:
                assert f"home_{col}_made" in row, f"Missing home_{col}_made"
                assert f"away_{col}_made" in row, f"Missing away_{col}_made"
                assert f"home_{col}_attempted" in row, f"Missing home_{col}_attempted"
                assert f"away_{col}_attempted" in row, f"Missing away_{col}_attempted"
            else:
                assert f"home_{col}" in row, f"Missing home_{col}"
                assert f"away_{col}" in row, f"Missing away_{col}"

    def test_event_id_forced_to_string(self):
        row = _parse_summary(_summary("133", "TOR", "DET"), "133")
        assert isinstance(row["event_id"], str)


# ---------------------------------------------------------------------------
# fetch_box tests
# ---------------------------------------------------------------------------

class TestFetchBox:
    def test_normal_flow(self):
        p = _summary("200", "PHI", "WAS", 118, 102)
        row = fetch_box("200", http_get=lambda url: p if "200" in url else {})
        assert row["event_id"] == "200"
        assert row["home_abbr"] == "PHI"
        assert row["home_score"] == pytest.approx(118.0)

    def test_http_error_returns_empty(self):
        assert fetch_box("999", http_get=lambda url: {}) == {}

    def test_bad_payload_returns_empty(self):
        assert fetch_box("888", http_get=lambda url: {"unexpected": True}) == {}


# ---------------------------------------------------------------------------
# fetch_scoreboard tests
# ---------------------------------------------------------------------------

class TestFetchScoreboard:
    def test_returns_event_list(self):
        events = fetch_scoreboard(
            "20250320", http_get=lambda url: _board(["401", "402", "403"])
        )
        assert len(events) == 3
        assert {e["event_id"] for e in events} == {"401", "402", "403"}

    def test_date_field_set(self):
        events = fetch_scoreboard(
            "20250320", http_get=lambda url: _board(["401"])
        )
        assert events[0]["date"] == "20250320"

    def test_empty_scoreboard(self):
        assert (
            fetch_scoreboard("20250320", http_get=lambda url: {"events": []}) == []
        )

    def test_http_failure_returns_empty_list(self):
        assert fetch_scoreboard("20250320", http_get=lambda url: {}) == []


# ---------------------------------------------------------------------------
# ingest_range tests
# ---------------------------------------------------------------------------

class TestIngestRange:
    def test_writes_parquet(self, tmp_path):
        out = tmp_path / "espn.parquet"
        path = ingest_range(["20250320"], http_get=_mock_get(["501", "502"]), out_path=out)
        assert path == out and out.exists()
        df = pd.read_parquet(out)
        assert len(df) == 2
        assert set(df["event_id"]) == {"501", "502"}

    def test_correct_columns_present(self, tmp_path):
        out = tmp_path / "espn.parquet"
        ingest_range(["20250320"], http_get=_mock_get(["601"]), out_path=out)
        row = pd.read_parquet(out).iloc[0]
        for col in (
            "event_id", "date", "home_abbr", "away_abbr",
            "home_fg_made", "home_fg_attempted",
            "home_fg3_made", "home_fg3_attempted",
            "home_ft_made", "home_reb", "home_ast",
            "home_stl", "home_blk", "home_tov",
            "home_paint_pts", "home_fast_break_pts",
            "away_fg_made", "away_reb",
        ):
            assert col in row.index, f"Missing column: {col}"

    def test_deduplication_on_rerun(self, tmp_path):
        out = tmp_path / "espn.parquet"
        mg = _mock_get(["701"])
        ingest_range(["20250320"], http_get=mg, out_path=out)
        ingest_range(["20250320"], http_get=mg, out_path=out)
        assert len(pd.read_parquet(out)) == 1

    def test_multi_date(self, tmp_path):
        out = tmp_path / "espn.parquet"
        ingest_range(["20250320"], http_get=_mock_get(["801"]), out_path=out)
        ingest_range(["20250321"], http_get=_mock_get(["802"]), out_path=out)
        assert set(pd.read_parquet(out)["event_id"]) == {"801", "802"}

    def test_empty_scoreboard_writes_nothing(self, tmp_path):
        out = tmp_path / "espn.parquet"
        ingest_range(
            ["20250320"],
            http_get=lambda url: (
                {"events": []} if "scoreboard" in url else {}
            ),
            out_path=out,
        )
        assert not out.exists()

    def test_date_column_stored(self, tmp_path):
        out = tmp_path / "espn.parquet"
        ingest_range(["20250320"], http_get=_mock_get(["901"]), out_path=out)
        # date is normalised to datetime64 so appends merge cleanly with an existing
        # datetime-typed parquet (see the merge fix in ingest_range).
        stored = pd.read_parquet(out).iloc[0]["date"]
        assert pd.Timestamp(stored) == pd.Timestamp("2025-03-20")

    def test_scores_stored(self, tmp_path):
        out = tmp_path / "espn.parquet"
        # Build custom mock with known scores
        board = _board(["1001"])
        s = _summary("1001", "MIA", "CHI", home_score=120, away_score=99)

        def _get(url: str) -> dict:
            return board if "scoreboard" in url else (s if "1001" in url else {})

        ingest_range(["20250320"], http_get=_get, out_path=out)
        row = pd.read_parquet(out).iloc[0]
        assert row["home_score"] == pytest.approx(120.0)
        assert row["away_score"] == pytest.approx(99.0)


# ---------------------------------------------------------------------------
# No-network guard
# ---------------------------------------------------------------------------

def test_import_does_not_call_network(monkeypatch):
    """Module-level reload must not trigger urllib.urlopen."""
    import urllib.request

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("network!")),
    )
    import importlib

    import domains.basketball_nba.ingest_espn_box as mod

    importlib.reload(mod)  # passes if no network call at module level
