"""LANE B -- schedule_context_resolver tests. Synthetic 3-game calendar
(monkeypatched _CALENDAR_PATHS, no real linescores.parquet dependency) --
pins the rest_days/is_b2b boundary convention (game yesterday -> rest_days=0
-> is_b2b=True) and the fail-closed no_data / not_supported paths.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/answers/test_schedule_context_resolver.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.answers import schedule_context_resolver as R
from scripts.platformkit.intel_query import ask as ask_mod

# captured BEFORE the autouse _synthetic_calendar fixture (below) stubs the
# module attribute R._schedule_claims out for every other test in this file
# -- the FIX 1 proof test needs the REAL function, not the stub.
_REAL_SCHEDULE_CLAIMS = R._schedule_claims

# AAA: games 2025-01-01, 2025-01-03, 2025-01-04 (last two are a real b2b).
_CAL = pd.DataFrame([
    {"home_abbr": "AAA", "away_abbr": "BBB", "date": pd.Timestamp("2025-01-01")},
    {"home_abbr": "BBB", "away_abbr": "AAA", "date": pd.Timestamp("2025-01-03")},
    {"home_abbr": "AAA", "away_abbr": "CCC", "date": pd.Timestamp("2025-01-04")},
])


@pytest.fixture(autouse=True)
def _synthetic_calendar(tmp_path, monkeypatch):
    path = tmp_path / "cal.parquet"
    _CAL.to_parquet(path)
    monkeypatch.setitem(R._CALENDAR_PATHS, "nba", (str(path), "home_abbr", "away_abbr"))
    monkeypatch.setattr(R, "_schedule_claims", lambda sport, team: [])  # isolate from real claims store
    return path


def test_game_yesterday_is_b2b_rest_days_zero():
    # boundary case: prior game 2025-01-01, as_of 2025-01-02 -> delta=1 day -> rest_days=0
    r = R.resolve("nba", "AAA", "2025-01-02")
    assert r["status"] == "ok"
    assert r["rest_days"] == 0
    assert r["is_b2b"] is True
    assert r["prior_game_date"] == "2025-01-01"


def test_two_days_rest_is_not_b2b():
    # prior game 2025-01-04, as_of 2025-01-06 -> delta=2 days -> rest_days=1
    r = R.resolve("nba", "AAA", "2025-01-06")
    assert r["rest_days"] == 1
    assert r["is_b2b"] is False
    assert r["prior_game_date"] == "2025-01-04"


def test_games_in_last_7_excludes_as_of_own_game():
    # as_of=2025-01-08 -> trailing window [2025-01-01, 2025-01-08) catches all 3 games
    r = R.resolve("nba", "AAA", "2025-01-08")
    assert r["games_in_last_7"] == 3


def test_no_prior_game_before_as_of():
    r = R.resolve("nba", "AAA", "2024-12-31")
    assert r["status"] == "ok"
    assert r["rest_days"] is None
    assert r["is_b2b"] is False
    assert r["prior_game_date"] is None


def test_unmatched_team_is_no_data_not_fabricated():
    r = R.resolve("nba", "ZZZ", "2025-01-08")
    assert r["status"] == "no_data"
    assert r["category"] == "schedule_context"


def test_unsupported_sport_is_not_supported():
    r = R.resolve("soccer", "ARS")
    assert r["status"] == "not_supported"


def test_missing_artifact_is_no_data(monkeypatch):
    monkeypatch.setitem(R._CALENDAR_PATHS, "nba", ("data/does/not/exist.parquet", "home_abbr", "away_abbr"))
    r = R.resolve("nba", "AAA")
    assert r["status"] == "no_data"
    assert r["source_artifact"] == "data/does/not/exist.parquet"


def test_nba_claims_code_convention_accepted():
    # GSW (claims convention) must resolve against the calendar's "GS" code
    cal = pd.DataFrame([
        {"home_abbr": "GS", "away_abbr": "BBB", "date": pd.Timestamp("2025-01-01")},
    ])
    path_gs = R._CALENDAR_PATHS["nba"][0]
    cal.to_parquet(path_gs)
    r = R.resolve("nba", "GSW", "2025-01-02")
    assert r["status"] == "ok"
    assert r["team"] == "GSW"  # echoed back in claims convention
    assert r["is_b2b"] is True


def test_mlb_free_text_team_name_resolves_via_canonicalizer(tmp_path, monkeypatch):
    """2026-07-17 pod coverage-stress defect 1: mlb had ZERO free-text
    team-name -> calendar-code resolution (only nba's branch resolved
    names), and the leading-article strip was nba-only too -- 'the Astros'/
    'Yankees'/'the Red Sox' must resolve to the calendar's own codes
    (HOU/NYY/BOS) via the shared team_resolver.canonical, not fail with the
    literal free text as the team column value."""
    cal = pd.DataFrame([
        {"home_team": "HOU", "away_team": "NYY", "date": pd.Timestamp("2025-01-01")},
        {"home_team": "NYY", "away_team": "BOS", "date": pd.Timestamp("2025-01-03")},
    ])
    path = tmp_path / "mlb_cal.parquet"
    cal.to_parquet(path)
    monkeypatch.setitem(R._CALENDAR_PATHS, "mlb", (str(path), "home_team", "away_team"))

    r = R.resolve("mlb", "the Astros", "2025-01-02")
    assert r["status"] == "ok" and r["team"] == "HOU"

    r = R.resolve("mlb", "Yankees", "2025-01-04")
    assert r["status"] == "ok" and r["team"] == "NYY"

    r = R.resolve("mlb", "the Red Sox", "2025-01-04")
    assert r["status"] == "ok" and r["team"] == "BOS"

    # a code that's ALREADY a direct match skips the canonicalizer fallback
    # entirely (no behavior change for the already-working exact-code path)
    r = R.resolve("mlb", "HOU", "2025-01-02")
    assert r["status"] == "ok" and r["team"] == "HOU"


def test_schedule_claims_never_reads_other_stores(tmp_path, monkeypatch):
    """FIX 1 (P0) proof: a bare load_verified_claims() whole-loads every
    *.jsonl under data/cache/intel_claims/ (GB-scale bulk rate stores
    included) just to keep this one 15KB nba_schedule_claims family.
    _schedule_claims must route through pairs_for_claim_stores so a decoy
    'fat' store sitting right next to it is NEVER opened."""
    schedule_claims_path = tmp_path / "nba_schedule_claims.jsonl"
    schedule_validation_path = tmp_path / "nba_schedule_claims_validation.json"
    decoy_claims_path = tmp_path / "nba_player_box_rate_claims.jsonl"
    decoy_validation_path = tmp_path / "nba_player_box_rate_claims_validation.json"

    schedule_claims_path.write_text(
        json.dumps({"claim_id": "nba_schedule_rest_days_rank",
                    "criteria": {"metric": "rest_days"},
                    "ranking": [{"team": "LAL", "value": 1.5, "rank": 3, "n": 82, "n_games": 82}]}) + "\n",
        encoding="ascii")
    schedule_validation_path.write_text(json.dumps(
        {"details": [{"claim_id": "nba_schedule_rest_days_rank", "verdict": "VERIFIED"}]}), encoding="ascii")

    decoy_claims_path.write_text(
        json.dumps({"claim_id": "decoy_fat_claim", "ranking": []}) + "\n", encoding="ascii")
    decoy_validation_path.write_text(json.dumps(
        {"details": [{"claim_id": "decoy_fat_claim", "verdict": "VERIFIED"}]}), encoding="ascii")

    monkeypatch.setattr(ask_mod, "CLAIM_SOURCE_PAIRS", (
        (schedule_validation_path, schedule_claims_path),
        (decoy_validation_path, decoy_claims_path),
    ))

    opened = []
    real_load_jsonl = ask_mod._load_jsonl

    def _tracking_load_jsonl(path, max_lines=None):
        opened.append(path)
        return real_load_jsonl(path, max_lines)

    monkeypatch.setattr(ask_mod, "_load_jsonl", _tracking_load_jsonl)

    out = _REAL_SCHEDULE_CLAIMS("nba", "LAL")

    assert schedule_claims_path in opened
    assert decoy_claims_path not in opened  # the declared-store scope, proven
    assert out and out[0]["claim_id"] == "nba_schedule_rest_days_rank"


# ---------------------------------------------------------------------------
# home_road_split (Family 3 extension) -- home/road balance, 1st/2nd half,
# longest stand/trip, remaining-given-as_of. Each test overwrites the
# fixture's synthetic calendar with its own richer season, same pattern
# test_nba_claims_code_convention_accepted already uses above.
# ---------------------------------------------------------------------------

def _season_cal(pairs):
    """pairs: list of (date_str, is_home) for team AAA vs a filler opponent."""
    rows = []
    for d, is_home in pairs:
        if is_home:
            rows.append({"home_abbr": "AAA", "away_abbr": "ZZZ", "date": pd.Timestamp(d)})
        else:
            rows.append({"home_abbr": "ZZZ", "away_abbr": "AAA", "date": pd.Timestamp(d)})
    return pd.DataFrame(rows)


def test_home_road_split_season_totals_and_halves(tmp_path, monkeypatch):
    # NBA-style season straddling the calendar-year boundary (Oct-Apr):
    # 4 home then 4 road games, evenly split for a clean median.
    pairs = [(f"2024-10-{10+i:02d}", True) for i in range(4)] + \
            [(f"2025-01-{10+i:02d}", False) for i in range(4)]
    cal = _season_cal(pairs)
    path = tmp_path / "season.parquet"
    cal.to_parquet(path)
    monkeypatch.setitem(R._CALENDAR_PATHS, "nba", (str(path), "home_abbr", "away_abbr"))

    r = R.home_road_split("nba", "AAA")
    assert r["status"] == "ok"
    assert r["season"] == "2024"  # season label = the year it STARTS
    assert r["season_totals"] == {"home": 4, "road": 4, "total": 8}
    assert r["first_half"]["home"] == 4 and r["first_half"]["road"] == 0
    assert r["second_half"]["home"] == 0 and r["second_half"]["road"] == 4
    assert r["longest_home_stand"] == 4
    assert r["longest_road_trip"] == 4
    assert r["career_totals"] == {"home": 4, "road": 4, "total": 8}


def test_home_road_split_remaining_given_as_of(tmp_path, monkeypatch):
    pairs = [("2024-10-10", True), ("2024-10-15", False), ("2024-11-01", True), ("2024-11-05", False)]
    cal = _season_cal(pairs)
    path = tmp_path / "season2.parquet"
    cal.to_parquet(path)
    monkeypatch.setitem(R._CALENDAR_PATHS, "nba", (str(path), "home_abbr", "away_abbr"))

    r = R.home_road_split("nba", "AAA", as_of="2024-10-20")
    assert r["status"] == "ok"
    assert r["remaining"] == {"home": 1, "road": 1, "total": 2}  # the two Nov games


def test_home_road_split_picks_season_containing_as_of(tmp_path, monkeypatch):
    # two distinct seasons on file; as_of names the EARLIER one
    pairs = [("2023-10-10", True), ("2023-11-10", False), ("2024-10-10", True), ("2024-11-10", False)]
    cal = _season_cal(pairs)
    path = tmp_path / "season3.parquet"
    cal.to_parquet(path)
    monkeypatch.setitem(R._CALENDAR_PATHS, "nba", (str(path), "home_abbr", "away_abbr"))

    r = R.home_road_split("nba", "AAA", as_of="2023-12-01")
    assert r["season"] == "2023"
    assert r["season_totals"] == {"home": 1, "road": 1, "total": 2}
    assert r["career_totals"] == {"home": 2, "road": 2, "total": 4}  # both seasons combined


def test_home_road_split_mlb_season_is_calendar_year(tmp_path, monkeypatch):
    cal = pd.DataFrame([
        {"home_team": "HOU", "away_team": "NYY", "date": pd.Timestamp("2024-04-01")},
        {"home_team": "NYY", "away_team": "HOU", "date": pd.Timestamp("2024-08-01")},
    ])
    path = tmp_path / "mlb_season.parquet"
    cal.to_parquet(path)
    monkeypatch.setitem(R._CALENDAR_PATHS, "mlb", (str(path), "home_team", "away_team"))

    r = R.home_road_split("mlb", "HOU")
    assert r["status"] == "ok"
    assert r["season"] == "2024"  # calendar-year season, no Aug-Jul straddle for mlb


def test_home_road_split_unmatched_team_is_no_data():
    r = R.home_road_split("nba", "ZZZZZ")
    assert r["status"] == "no_data"


def test_home_road_split_unsupported_sport_is_not_supported():
    r = R.home_road_split("soccer", "ARS")
    assert r["status"] == "not_supported"
