"""Tests for domains.mlb.ingest_umpire_assignments.

Network-free canned-payload tests + one live-data join test (skipped on a
clean clone) proving the store's umpire_id joins the existing umpire zone
claims ledger (data/cache/intel_claims/umpire_zone_claims.jsonl).
Run per-file (NEVER full pytest):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_ingest_umpire_assignments.py -q
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from domains.mlb.ingest_umpire_assignments import (
    _DEFAULT_OUT,
    fetch_date,
    ingest_range,
    parse_game_officials,
    parse_schedule_officials,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLAIMS = _REPO_ROOT / "data" / "cache" / "intel_claims" / "umpire_zone_claims.jsonl"

_CREW_GAME = {
    "gamePk": 824818,
    "officialDate": "2026-07-09",
    "teams": {
        "away": {"team": {"id": 145, "name": "Chicago White Sox"}},
        "home": {"team": {"id": 110, "name": "Baltimore Orioles"}},
    },
    "officials": [
        {"official": {"id": 547380, "fullName": "Carlos Torres"}, "officialType": "Home Plate"},
        {"official": {"id": 608158, "fullName": "Nate Tomlinson"}, "officialType": "First Base"},
        {"official": {"id": 427344, "fullName": "Bill Miller"}, "officialType": "Second Base"},
        {"official": {"id": 427113, "fullName": "Laz Diaz"}, "officialType": "Third Base"},
    ],
}

_NO_CREW_GAME = {
    "gamePk": 824252,
    "officialDate": "2026-07-10",
    "teams": {
        "away": {"team": {"id": 111, "name": "Boston Red Sox"}},
        "home": {"team": {"id": 147, "name": "New York Yankees"}},
    },
    "officials": [],
}

_PAYLOAD = {"dates": [{"games": [_CREW_GAME, _NO_CREW_GAME]}]}


def test_full_crew_parsed():
    rows = parse_game_officials(_CREW_GAME, "2026-07-09", "2026-07-09T20:00:00Z")
    assert len(rows) == 4
    by_type = {r["official_type"]: r for r in rows}
    assert by_type["Home Plate"]["umpire_id"] == 547380
    assert by_type["Home Plate"]["umpire_name"] == "Carlos Torres"
    assert by_type["Third Base"]["umpire_id"] == 427113
    for r in rows:
        assert r["game_pk"] == 824818
        assert r["home_team"] == "Baltimore Orioles"
        assert r["snapshot_date"] == "2026-07-09"


def test_no_crew_game_yields_no_rows():
    assert parse_game_officials(_NO_CREW_GAME, "d", "t") == []
    assert parse_game_officials({}, "d", "t") == []
    assert parse_game_officials(None, "d", "t") == []


def test_parse_schedule_officials():
    rows = parse_schedule_officials(_PAYLOAD, "2026-07-09", "t")
    assert len(rows) == 4  # only the crewed game contributes
    assert parse_schedule_officials({}, "d", "t") == []
    assert parse_schedule_officials(None, "d", "t") == []


def test_fetch_date_injected():
    rows = fetch_date("2026-07-09", http_get=lambda u: _PAYLOAD)
    assert len(rows) == 4


def test_ingest_range_dedup_idempotent(tmp_path):
    out = tmp_path / "umpire_assignments.parquet"
    getter = lambda u: _PAYLOAD  # noqa: E731
    p1 = ingest_range(["2026-07-09"], http_get=getter, out_path=out, sleep_s=0.0)
    df1 = pd.read_parquet(p1)
    assert len(df1) == 4
    assert str(df1["game_pk"].dtype) == "int64"
    assert str(df1["umpire_id"].dtype) == "int64"
    # re-ingest same date -> same (game_pk, official_type, snapshot_date) -> stable
    p2 = ingest_range(["2026-07-09"], http_get=getter, out_path=out, sleep_s=0.0)
    assert len(pd.read_parquet(p2)) == 4


@pytest.mark.skipif(
    not (_DEFAULT_OUT.exists() and _CLAIMS.exists()),
    reason="live store or claims ledger absent (clean clone)",
)
def test_live_join_to_umpire_zone_claims():
    """The store's umpire_id namespace joins the existing umpire zone claims
    (ranking entity_key umpire_id = MLB person id)."""
    store = pd.read_parquet(_DEFAULT_OUT)
    assert len(store) > 0
    claim_ids = set()
    with open(_CLAIMS, encoding="utf-8") as f:
        for line in f:
            claim = json.loads(line)
            claim_ids |= {int(e["umpire_id"]) for e in claim.get("ranking", [])}
    assert claim_ids
    store_ids = set(store["umpire_id"].astype("int64"))
    overlap = store_ids & claim_ids
    assert overlap, "no umpire_id overlap between assignment store and claims ledger"
