"""Per-file test for domains.soccer.ingest_espn_athlete (network-free).

Run ONLY this file (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_ingest_espn_athlete.py -q
"""
from __future__ import annotations

from domains.soccer.ingest_espn_athlete import (
    build_club_priors,
    club_prior,
    fetch_athlete_overview,
    parse_club_prior,
)

# Canned OVERVIEW payload. names order must match each split's stats values.
_NAMES = [
    "starts", "foulsCommitted", "foulsSuffered", "yellowCards", "redCards",
    "totalGoals", "goalAssists", "totalShots", "shotsOnTarget", "offsides",
]


def _overview():
    return {
        "statistics": {
            "names": list(_NAMES),
            "splits": [
                # Club league split: 10 starts.
                {"displayName": "LaLiga", "leagueSlug": "esp.1",
                 "stats": [10, 5, 7, 2, 0, 6, 4, 20, 9, 3]},
                # Club cup split: 5 starts.
                {"displayName": "Copa del Rey", "leagueSlug": "esp.copa_del_rey",
                 "stats": [5, 1, 3, 1, 1, 2, 1, 8, 4, 1]},
                # INTERNATIONAL split -- must be EXCLUDED.
                {"displayName": "FIFA World Cup", "leagueSlug": "fifa.world",
                 "stats": [3, 9, 9, 9, 9, 9, 9, 99, 99, 9]},
            ],
        }
    }


def _http_get_factory(payload):
    def _get(url):
        return payload
    return _get


def test_parse_sums_club_splits_only():
    out = parse_club_prior(_overview())
    # starts summed across the two CLUB splits only: 10 + 5 = 15.
    # Shots total = 20 + 8 = 28 -> per_start = 28/15.
    assert abs(out["Shots"]["starts"] - 15.0) < 1e-9
    assert abs(out["Shots"]["total"] - 28.0) < 1e-9
    assert abs(out["Shots"]["per_start"] - 28.0 / 15.0) < 1e-9
    # The international split's 99 shots must NOT be counted.
    assert out["Shots"]["total"] < 99


def test_cards_are_yellow_plus_red():
    out = parse_club_prior(_overview())
    # yellow: 2 + 1 = 3; red: 0 + 1 = 1 -> total 4 (club splits only).
    assert abs(out["Cards"]["total"] - 4.0) < 1e-9
    assert abs(out["Cards"]["per_start"] - 4.0 / 15.0) < 1e-9


def test_goal_plus_assist_combines():
    out = parse_club_prior(_overview())
    # goals 6+2=8, assists 4+1=5 -> 13.
    assert abs(out["Goal+Assist"]["total"] - 13.0) < 1e-9


def test_per_start_none_when_no_starts():
    ov = {
        "statistics": {
            "names": list(_NAMES),
            "splits": [
                {"displayName": "LaLiga", "leagueSlug": "esp.1",
                 "stats": [0, 1, 1, 1, 0, 1, 1, 5, 2, 0]},
            ],
        }
    }
    out = parse_club_prior(ov)
    assert out["Shots"]["starts"] == 0.0
    assert out["Shots"]["per_start"] is None


def test_empty_overview_returns_empty():
    assert parse_club_prior({}) == {}
    assert parse_club_prior({"statistics": {}}) == {}
    assert parse_club_prior(None) == {}


def test_fetch_uses_injected_http_get():
    got = fetch_athlete_overview("362150", http_get=_http_get_factory(_overview()))
    assert "statistics" in got


def test_club_prior_roundtrip(tmp_path):
    out = tmp_path / "club.parquet"
    build_club_priors(
        ["362150"], http_get=_http_get_factory(_overview()), out_path=out
    )
    cp = club_prior("362150", "Shots", priors_path=out)
    assert cp["status"] == "ok"
    assert abs(cp["per90"] - 28.0 / 15.0) < 1e-9
    assert abs(cp["starts"] - 15.0) < 1e-9


def test_club_prior_missing_is_unknown(tmp_path):
    out = tmp_path / "club.parquet"
    build_club_priors(
        ["362150"], http_get=_http_get_factory(_overview()), out_path=out
    )
    # Unknown player -> unknown.
    assert club_prior("999999", "Shots", priors_path=out)["status"] == "unknown"
    # Unknown parquet path -> unknown.
    assert club_prior("362150", "Shots", priors_path=tmp_path / "nope.parquet")[
        "status"] == "unknown"


def test_build_skips_erroring_ids(tmp_path):
    out = tmp_path / "club.parquet"

    def _get(url):
        if "111" in url:
            return {}  # empty -> skipped
        return _overview()

    build_club_priors(["111", "362150"], http_get=_get, out_path=out)
    assert club_prior("111", "Shots", priors_path=out)["status"] == "unknown"
    assert club_prior("362150", "Shots", priors_path=out)["status"] == "ok"
