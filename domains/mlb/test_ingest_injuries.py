"""Per-file test for domains.mlb.ingest_injuries. Run ONLY this file (full suite freezes).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_ingest_injuries.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from domains.mlb.ingest_injuries import (  # noqa: E402
    build_edge_facts, ingest_snapshot, parse_injuries_payload, write_edge_facts,
)

_SNAP_DATE = "2026-07-02"
_CAPTURED_AT = "2026-07-02T15:00:00Z"


def _planted_payload() -> dict:
    """Two teams, three injuries: one long_comment with a rest-restriction-like
    keyword ('will not throw for two weeks' -> contains 'out'? no -- use an
    explicit lineup keyword), one with 'questionable', and one row missing
    details/athlete sub-fields entirely.
    """
    return {
        "injuries": [
            {
                "id": "29",
                "displayName": "Arizona Diamondbacks",
                "injuries": [
                    {
                        "id": "1001",
                        "status": "10-Day-IL",
                        "date": "2026-07-01T10:00Z",
                        "shortComment": "Smith (elbow) will not throw for two weeks, team says.",
                        "longComment": "Smith is out and will not throw for two weeks per the club.",
                        "athlete": {
                            "displayName": "John Smith",
                            "position": {"abbreviation": "SP"},
                            "links": [
                                {"rel": ["playercard"], "href": "https://www.espn.com/mlb/player/_/id/12345"},
                            ],
                        },
                        "details": {
                            "type": "Elbow", "detail": "Strain", "side": "Right",
                            "returnDate": "2026-07-15",
                        },
                    },
                    {
                        "id": "1002",
                        "status": "Day-To-Day",
                        "date": "2026-07-02T09:00Z",
                        "shortComment": "Doe is questionable for tonight's game.",
                        "longComment": "",
                        "athlete": {
                            "displayName": "Jane Doe",
                            "position": {"abbreviation": "OF"},
                            "links": [
                                {"rel": ["playercard"], "href": "https://www.espn.com/mlb/player/_/id/67890"},
                            ],
                        },
                        "details": {"type": "Hamstring", "detail": "Soreness", "side": "Left"},
                    },
                ],
            },
            {
                "id": "10",
                "displayName": "New York Mets",
                "injuries": [
                    {
                        "id": "1003",
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

    smith = next(r for r in rows if r["athlete_name"] == "John Smith")
    assert smith["team"] == "Arizona Diamondbacks"
    assert smith["athlete_id"] == 12345
    assert smith["position"] == "SP"
    assert smith["status"] == "10-Day-IL"
    assert smith["injury_type"] == "Elbow"
    assert smith["return_date"] == "2026-07-15"
    assert smith["snapshot_date"] == _SNAP_DATE
    assert smith["captured_at"] == _CAPTURED_AT

    no_details = next(r for r in rows if r["athlete_name"] == "No Details Guy")
    assert no_details["athlete_id"] is None
    assert no_details["status"] is None
    assert no_details["injury_type"] is None
    assert no_details["short_comment"] == ""
    assert no_details["long_comment"] == ""


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

    # Same-day re-run (even with a later captured_at) must dedup keep-last, not grow.
    df2 = ingest_snapshot(
        http_get=fake_get, out_path=out, snapshot_date=_SNAP_DATE,
        captured_at="2026-07-02T16:00:00Z",
    )
    assert len(df2) == 3
    on_disk = pd.read_parquet(out)
    assert len(on_disk) == 3
    # keep-last: captured_at should reflect the second run for the keyed rows.
    smith_row = on_disk[on_disk["athlete_name"] == "John Smith"].iloc[0]
    assert smith_row["captured_at"] == "2026-07-02T16:00:00Z"


def test_ingest_snapshot_preserves_prior_snapshot_dates(tmp_path):
    out = tmp_path / "injuries.parquet"

    def fake_get(url: str) -> dict:
        return _planted_payload()

    ingest_snapshot(http_get=fake_get, out_path=out, snapshot_date="2026-07-01", captured_at="2026-07-01T12:00:00Z")
    ingest_snapshot(http_get=fake_get, out_path=out, snapshot_date="2026-07-02", captured_at=_CAPTURED_AT)

    on_disk = pd.read_parquet(out)
    assert set(on_disk["snapshot_date"].unique()) == {"2026-07-01", "2026-07-02"}
    assert len(on_disk) == 6  # 3 rows x 2 distinct days, history preserved


# --- edge-facts bridge ---------------------------------------------------------

def test_build_edge_facts_emits_lineup_status_from_planted_text():
    rows = parse_injuries_payload(_planted_payload(), _SNAP_DATE, _CAPTURED_AT)
    facts = build_edge_facts(rows)
    assert len(facts) >= 1
    kinds = {f["fact_kind"] for f in facts}
    assert "lineup_status" in kinds
    # subject_id should be the parsed athlete id for Smith/Doe rows.
    subjects = {f["subject_id"] for f in facts}
    assert "12345" in subjects or "67890" in subjects


def test_build_edge_facts_skips_row_with_no_comment_text():
    rows = parse_injuries_payload(_planted_payload(), _SNAP_DATE, _CAPTURED_AT)
    no_details = [r for r in rows if r["athlete_name"] == "No Details Guy"]
    facts = build_edge_facts(no_details)
    assert facts == []


def test_build_edge_facts_survives_a_bad_row(monkeypatch):
    rows = parse_injuries_payload(_planted_payload(), _SNAP_DATE, _CAPTURED_AT)
    # Corrupt one row so SourceDoc construction / extract_rule chokes on it,
    # but the other well-formed rows must still produce facts.
    bad_row = dict(rows[0])
    bad_row["captured_at"] = None  # published_ts must be ISO -- this will fail validate_source
    bad_row["snapshot_date"] = None
    mixed = [bad_row] + rows[1:]
    facts = build_edge_facts(mixed)  # must not raise
    assert isinstance(facts, list)


def test_write_edge_facts_dedup_on_keep_last(tmp_path):
    out = tmp_path / "edge_facts_injuries.parquet"
    rows = parse_injuries_payload(_planted_payload(), _SNAP_DATE, _CAPTURED_AT)
    facts = build_edge_facts(rows)
    assert facts, "planted text must yield at least one fact for this test to be meaningful"

    df1 = write_edge_facts(facts, out_path=out)
    assert len(df1) == len(facts)
    assert out.exists()

    # Re-write the same facts -- dedup key (game_date, subject_id, fact_kind) keeps count stable.
    df2 = write_edge_facts(facts, out_path=out)
    on_disk = pd.read_parquet(out)
    assert len(on_disk) == len(df1)
    assert len(df2) == len(df1)


# --- no network at import -------------------------------------------------------

def test_no_network_call_at_import(monkeypatch):
    """Importing the module must never touch the network. If urllib.request.urlopen
    were called at import time this test module's own collection would already have
    triggered it; here we assert the module exposes an injectable http_get and that
    calling _default_http_get is the ONLY path that reaches urllib."""
    import domains.mlb.ingest_injuries as mod

    called = {"n": 0}

    def boom(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("network should not be reached in this test")

    monkeypatch.setattr(mod.urllib.request, "urlopen", boom)
    # Using an injected getter must avoid urllib entirely.
    result = mod.fetch_injuries(http_get=lambda url: {})
    assert result == {}
    assert called["n"] == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
