"""Per-file test for domains.basketball_wnba.ingest_espn_injuries. Run ONLY this
file (full suite freezes).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingest_espn_injuries.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from domains.basketball_wnba.ingest_espn_injuries import (  # noqa: E402
    CORPUS_ID, fetch_injuries, ingest_snapshot, parse_injuries_payload,
)

_SNAP_DATE = "2026-07-04"
_CAPTURED_AT = "2026-07-04T15:00:00Z"


def _planted_payload() -> dict:
    """Two teams, three injuries -- mirrors the live-probed shape (2026-07-04):
    injuries[].{id,displayName,injuries[]}, each entry status/date/comments/
    athlete/details. One entry missing details/athlete sub-fields entirely.
    """
    return {
        "timestamp": "2026-07-04T15:00Z",
        "status": "success",
        "season": {"year": 2026, "type": 2, "name": "Regular Season"},
        "injuries": [
            {
                "id": "20",
                "displayName": "Atlanta Dream",
                "injuries": [
                    {
                        "id": "33247",
                        "status": "Out",
                        "date": "2026-07-04T16:06Z",
                        "shortComment": "Sherrod (coach's decision) has been ruled out.",
                        "longComment": "Sherrod signed a developmental contract and has yet to debut.",
                        "athlete": {
                            "displayName": "Jaylyn Sherrod",
                            "position": {"abbreviation": "G"},
                            "links": [
                                {"rel": ["playercard"],
                                 "href": "https://www.espn.com/wnba/player/_/id/4433386/jaylyn-sherrod"},
                            ],
                        },
                        "details": {"type": "Coach's Decision", "returnDate": "2026-07-09"},
                    },
                    {
                        "id": "33300",
                        "status": "Day-To-Day",
                        "date": "2026-07-03T09:00Z",
                        "shortComment": "Jones (ankle) is questionable.",
                        "longComment": "",
                        "athlete": {
                            "displayName": "A. Jones",
                            "position": {"abbreviation": "F"},
                            "links": [
                                {"rel": ["playercard"],
                                 "href": "https://www.espn.com/wnba/player/_/id/5551212/a-jones"},
                            ],
                        },
                        "details": {"type": "Ankle", "detail": "Sprain", "side": "Left"},
                    },
                ],
            },
            {
                "id": "18",
                "displayName": "Seattle Storm",
                "injuries": [
                    {
                        "id": "40001",
                        # missing 'status', 'date', 'details', minimal athlete
                        "athlete": {"displayName": "No Details Guy"},
                    },
                ],
            },
        ],
    }


# --- pure parsing -------------------------------------------------------------

def test_parse_injuries_payload_correctness_and_nullable_handling():
    rows = parse_injuries_payload(_planted_payload(), _SNAP_DATE, _CAPTURED_AT)
    assert len(rows) == 3

    sherrod = next(r for r in rows if r["athlete_name"] == "Jaylyn Sherrod")
    assert sherrod["team"] == "Atlanta Dream"
    assert sherrod["athlete_id"] == 4433386
    assert sherrod["position"] == "G"
    assert sherrod["status"] == "Out"
    assert sherrod["injury_type"] == "Coach's Decision"
    assert sherrod["return_date"] == "2026-07-09"
    assert sherrod["snapshot_date"] == _SNAP_DATE
    assert sherrod["captured_at"] == _CAPTURED_AT
    assert sherrod["as_of"] == _SNAP_DATE
    assert sherrod["corpus_id"] == CORPUS_ID

    no_details = next(r for r in rows if r["athlete_name"] == "No Details Guy")
    assert no_details["athlete_id"] is None
    assert no_details["status"] is None
    assert no_details["injury_type"] is None
    assert no_details["short_comment"] == ""
    assert no_details["long_comment"] == ""
    assert no_details["as_of"] == _SNAP_DATE
    assert no_details["corpus_id"] == CORPUS_ID


def test_parse_injuries_payload_empty_on_missing_injuries_key():
    assert parse_injuries_payload({}, _SNAP_DATE, _CAPTURED_AT) == []


# --- snapshot-append + idempotent re-run --------------------------------------

def test_ingest_snapshot_writes_and_same_day_rerun_is_idempotent(tmp_path):
    out = tmp_path / "injuries.parquet"

    def fake_get(url: str) -> dict:
        return _planted_payload()

    df1 = ingest_snapshot(
        http_get=fake_get, out_path=out, snapshot_date=_SNAP_DATE, captured_at=_CAPTURED_AT,
    )
    assert len(df1) == 3
    assert out.exists()

    df2 = ingest_snapshot(
        http_get=fake_get, out_path=out, snapshot_date=_SNAP_DATE,
        captured_at="2026-07-04T18:00:00Z",
    )
    assert len(df2) == 3
    on_disk = pd.read_parquet(out)
    assert len(on_disk) == 3
    sherrod_row = on_disk[on_disk["athlete_name"] == "Jaylyn Sherrod"].iloc[0]
    assert sherrod_row["captured_at"] == "2026-07-04T18:00:00Z"
    assert set(on_disk["corpus_id"].unique()) == {CORPUS_ID}


def test_ingest_snapshot_preserves_prior_snapshot_dates(tmp_path):
    out = tmp_path / "injuries.parquet"

    def fake_get(url: str) -> dict:
        return _planted_payload()

    ingest_snapshot(http_get=fake_get, out_path=out, snapshot_date="2026-07-03", captured_at="2026-07-03T12:00:00Z")
    ingest_snapshot(http_get=fake_get, out_path=out, snapshot_date="2026-07-04", captured_at=_CAPTURED_AT)

    on_disk = pd.read_parquet(out)
    assert set(on_disk["snapshot_date"].unique()) == {"2026-07-03", "2026-07-04"}
    assert len(on_disk) == 6  # 3 rows x 2 distinct days, history preserved


def test_ingest_snapshot_atomic_write_no_leftover_tmp(tmp_path):
    out = tmp_path / "injuries.parquet"

    def fake_get(url: str) -> dict:
        return _planted_payload()

    ingest_snapshot(http_get=fake_get, out_path=out, snapshot_date=_SNAP_DATE, captured_at=_CAPTURED_AT)
    assert out.exists()
    assert not out.with_suffix(".parquet.tmp").exists()


# --- no network at import -------------------------------------------------------

def test_no_network_call_at_import(monkeypatch):
    """Importing the module must never touch the network. Using an injected
    getter must avoid urllib entirely."""
    import domains.basketball_wnba.ingest_espn_injuries as mod

    called = {"n": 0}

    def boom(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("network should not be reached in this test")

    monkeypatch.setattr(mod.urllib.request, "urlopen", boom)
    result = mod.fetch_injuries(http_get=lambda url: {})
    assert result == {}
    assert called["n"] == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
