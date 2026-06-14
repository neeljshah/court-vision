"""tests.platform.test_ingest_espn_tennis — unit tests for domains.tennis.ingest_espn.

All tests use injected http_get; NO network calls are made.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from domains.tennis.ingest_espn import (
    _parse_linescores,
    _sets_won,
    _parse_competition,
    parse_scoreboard,
    fetch_scoreboard,
    ingest_range,
)


# ---------------------------------------------------------------------------
# Synthetic payload helpers
# ---------------------------------------------------------------------------

def _make_comp(comp_id: str = "999", best_of: int = 3, players: list | None = None) -> dict:
    if players is None:
        players = [
            {"name": "Player A", "linescores": [{"value": 6, "period": 1, "winner": True}, {"value": 6, "period": 2, "winner": True}], "winner": True},
            {"name": "Player B", "linescores": [{"value": 3, "period": 1, "winner": False}, {"value": 4, "period": 2, "winner": False}], "winner": False},
        ]
    competitors = []
    for p in players:
        lsc = [
            {"value": item["value"], "period": item["period"], "winner": item.get("winner", False),
             **( {"tiebreak": item["tiebreak"]} if "tiebreak" in item else {})}
            for item in p["linescores"]
        ]
        competitors.append({"athlete": {"displayName": p["name"]}, "winner": p.get("winner", False), "linescores": lsc})
    return {
        "id": comp_id, "date": "2026-06-10T09:00Z", "startDate": "2026-06-10T09:00Z",
        "status": {"type": {"name": "STATUS_FINAL"}},
        "round": {"id": "1", "displayName": "Round 1"},
        "format": {"regulation": {"periods": best_of}},
        "competitors": competitors,
    }


def _make_scoreboard(league: str = "atp", discipline: str = "Men's Singles",
                     major: bool = False, comps: list | None = None) -> dict:
    if comps is None:
        comps = [_make_comp()]
    return {
        "events": [{
            "id": "49-2026", "name": "Boss Open", "major": major,
            "season": {"year": 2026},
            "groupings": [{"grouping": {"id": "1", "displayName": discipline}, "competitions": comps}],
        }]
    }


def _base_kwargs() -> dict:
    return dict(league="atp", tournament_id="49-2026", tournament_name="Boss Open",
                major=False, season_year=2026, discipline="Men's Singles")


# ---------------------------------------------------------------------------
# _parse_linescores
# ---------------------------------------------------------------------------

class TestParseLinescores:
    def test_straight_sets(self) -> None:
        lsc = [{"value": 6.0, "period": 1, "winner": True}, {"value": 6.0, "period": 2, "winner": True}]
        r = _parse_linescores(lsc)
        assert r["s1"] == 6.0 and r["s2"] == 6.0 and r["s3"] is None and r["tb1"] is None

    def test_tiebreak_captured(self) -> None:
        lsc = [{"value": 7.0, "period": 1, "winner": True, "tiebreak": 7},
               {"value": 6.0, "period": 2, "winner": False, "tiebreak": 3}]
        r = _parse_linescores(lsc)
        assert r["tb1"] == 7.0 and r["tb2"] == 3.0

    def test_empty_all_none(self) -> None:
        r = _parse_linescores([])
        assert all(r[f"s{i}"] is None for i in range(1, 6))
        assert all(r[f"tb{i}"] is None for i in range(1, 6))

    def test_out_of_range_period_ignored(self) -> None:
        r = _parse_linescores([{"value": 6, "period": 99, "winner": True}])
        assert all(r[f"s{i}"] is None for i in range(1, 6))

    def test_missing_period_uses_index(self) -> None:
        # Scoreboard endpoint omits period — falls back to 1-based list index
        r = _parse_linescores([{"value": 6, "winner": True}, {"value": 4, "winner": False}])
        assert r["s1"] == 6.0 and r["s2"] == 4.0 and r["s3"] is None

    def test_non_numeric_value_none(self) -> None:
        r = _parse_linescores([{"value": "N/A", "period": 1, "winner": False}])
        assert r["s1"] is None

    def test_three_sets(self) -> None:
        lsc = [{"value": 6, "period": i, "winner": True} for i in range(1, 4)]
        r = _parse_linescores(lsc)
        assert r["s3"] == 6.0 and r["s4"] is None


# ---------------------------------------------------------------------------
# _sets_won
# ---------------------------------------------------------------------------

class TestSetsWon:
    def test_two_won(self) -> None:
        lsc = [{"value": 6, "period": i, "winner": True} for i in range(1, 3)]
        assert _sets_won(lsc) == 2

    def test_zero_won(self) -> None:
        lsc = [{"value": 3, "period": 1, "winner": False}, {"value": 4, "period": 2, "winner": False}]
        assert _sets_won(lsc) == 0

    def test_split(self) -> None:
        lsc = [{"value": 6, "period": 1, "winner": True}, {"value": 3, "period": 2, "winner": False},
               {"value": 6, "period": 3, "winner": True}]
        assert _sets_won(lsc) == 2

    def test_empty(self) -> None:
        assert _sets_won([]) == 0


# ---------------------------------------------------------------------------
# _parse_competition
# ---------------------------------------------------------------------------

class TestParseCompetition:
    def test_two_rows(self) -> None:
        assert len(_parse_competition(_make_comp(), **_base_kwargs())) == 2

    def test_winner_and_loser(self) -> None:
        rows = _parse_competition(_make_comp(), **_base_kwargs())
        assert {r["winner"] for r in rows} == {True, False}

    def test_sets_won(self) -> None:
        rows = _parse_competition(_make_comp(), **_base_kwargs())
        winner_row = next(r for r in rows if r["winner"])
        loser_row = next(r for r in rows if not r["winner"])
        assert winner_row["sets_won"] == 2 and loser_row["sets_won"] == 0

    def test_best_of_5(self) -> None:
        rows = _parse_competition(_make_comp(best_of=5), **_base_kwargs())
        assert all(r["best_of"] == 5 for r in rows)

    def test_missing_id_empty(self) -> None:
        comp = _make_comp()
        comp.pop("id")
        assert _parse_competition(comp, **_base_kwargs()) == []

    def test_no_competitors_empty(self) -> None:
        comp = _make_comp()
        comp["competitors"] = []
        assert _parse_competition(comp, **_base_kwargs()) == []

    def test_missing_athlete_empty_name(self) -> None:
        comp = _make_comp()
        for c in comp["competitors"]:
            c.pop("athlete", None)
        rows = _parse_competition(comp, **_base_kwargs())
        assert all(r["player_name"] == "" for r in rows)

    def test_tiebreak_in_row(self) -> None:
        players = [
            {"name": "A", "linescores": [{"value": 7, "period": 1, "winner": True, "tiebreak": 7}], "winner": True},
            {"name": "B", "linescores": [{"value": 6, "period": 1, "winner": False, "tiebreak": 3}], "winner": False},
        ]
        rows = _parse_competition(_make_comp(players=players), **_base_kwargs())
        assert next(r for r in rows if r["player_name"] == "A")["tb1"] == 7.0

    def test_league_propagated(self) -> None:
        rows = _parse_competition(_make_comp(), **_base_kwargs())
        assert all(r["league"] == "atp" for r in rows)


# ---------------------------------------------------------------------------
# parse_scoreboard
# ---------------------------------------------------------------------------

class TestParseScoreboard:
    def test_basic(self) -> None:
        assert len(parse_scoreboard(_make_scoreboard(), "atp")) == 2

    def test_empty_payload(self) -> None:
        assert parse_scoreboard({}, "atp") == []

    def test_none_payload(self) -> None:
        assert parse_scoreboard(None, "atp") == []  # type: ignore[arg-type]

    def test_no_events(self) -> None:
        assert parse_scoreboard({"events": []}, "atp") == []

    def test_major_flag(self) -> None:
        rows = parse_scoreboard(_make_scoreboard(major=True), "atp")
        assert all(r["major"] is True for r in rows)

    def test_discipline_propagated(self) -> None:
        rows = parse_scoreboard(_make_scoreboard(discipline="Women's Singles"), "wta")
        assert all(r["discipline"] == "Women's Singles" for r in rows)

    def test_multiple_competitions(self) -> None:
        comps = [_make_comp(comp_id="1"), _make_comp(comp_id="2")]
        assert len(parse_scoreboard(_make_scoreboard(comps=comps), "atp")) == 4

    def test_garbage_events_field(self) -> None:
        assert parse_scoreboard({"events": "not_a_list"}, "atp") == []


# ---------------------------------------------------------------------------
# fetch_scoreboard (injected http_get)
# ---------------------------------------------------------------------------

class TestFetchScoreboard:
    def test_inject_payload(self) -> None:
        def fake_get(url: str) -> dict:
            assert "atp" in url
            return _make_scoreboard()
        assert len(fetch_scoreboard("20260610", "atp", http_get=fake_get)) == 2

    def test_empty_response(self) -> None:
        assert fetch_scoreboard("20260610", "atp", http_get=lambda u: {}) == []

    def test_error_response(self) -> None:
        assert fetch_scoreboard("20260610", "atp", http_get=lambda u: {"__error__": "500"}) == []


# ---------------------------------------------------------------------------
# ingest_range (no network, temp parquet)
# ---------------------------------------------------------------------------

class TestIngestRange:
    def test_writes_parquet(self, tmp_path: Path) -> None:
        out = tmp_path / "espn_matches.parquet"
        ingest_range(["20260610"], leagues=["atp"], http_get=lambda u: _make_scoreboard(), out_path=out)
        assert out.exists()
        df = pd.read_parquet(out)
        assert len(df) == 2

    def test_dedup(self, tmp_path: Path) -> None:
        out = tmp_path / "espn_matches.parquet"
        ingest_range(["20260610"], leagues=["atp"], http_get=lambda u: _make_scoreboard(), out_path=out)
        ingest_range(["20260610"], leagues=["atp"], http_get=lambda u: _make_scoreboard(), out_path=out)
        assert len(pd.read_parquet(out)) == 2

    def test_empty_dates_no_file(self, tmp_path: Path) -> None:
        out = tmp_path / "espn_matches.parquet"
        ingest_range([], http_get=lambda u: {}, out_path=out)
        assert not out.exists()

    def test_all_errors_no_file(self, tmp_path: Path) -> None:
        out = tmp_path / "espn_matches.parquet"
        ingest_range(["20260610"], leagues=["atp"], http_get=lambda u: {}, out_path=out)
        assert not out.exists()

    def test_schema_columns(self, tmp_path: Path) -> None:
        out = tmp_path / "espn_matches.parquet"
        ingest_range(["20260610"], leagues=["atp"], http_get=lambda u: _make_scoreboard(), out_path=out)
        df = pd.read_parquet(out)
        for col in ["comp_id", "date", "league", "tournament_id", "tournament_name",
                    "major", "season_year", "best_of", "discipline", "round_name",
                    "status", "player_name", "winner", "sets_won",
                    "s1", "s2", "s3", "s4", "s5", "tb1", "tb2", "tb3", "tb4", "tb5"]:
            assert col in df.columns, f"Missing column: {col}"

    def test_wta_league(self, tmp_path: Path) -> None:
        out = tmp_path / "espn_matches.parquet"
        wta = _make_scoreboard(league="wta", discipline="Women's Singles")
        ingest_range(["20260610"], leagues=["wta"], http_get=lambda u: wta, out_path=out)
        df = pd.read_parquet(out)
        assert (df["league"] == "wta").all()
