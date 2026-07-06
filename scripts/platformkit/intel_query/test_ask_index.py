"""Per-file tests for ask_index.py (spec sec 4, LANE L-D).

Direct unit tests for the module extracted out of ask.py to respect the
<=300 LOC/file rail (test_ask.py already covers the SAME behavior end-to-end
through the public ask() surface -- these tests target index_top_n_lookup /
seek_claim_row directly: metric/window filtering, VERIFIED-only, most-recent
computed_at tie-break, and the "no matching family -> None" contract that
callers rely on to fall back).
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.intel_query import ask_index
from scripts.platformkit.intel_query.claims_index import build_index
from scripts.platformkit.intel_query.families import ParsedQuestion

REPO_ROOT = Path(__file__).resolve().parents[3]


def _ranking_row(claim_id: str, metric: str, window: str, computed_at: str, ranking: list[dict]) -> dict:
    return {
        "claim_id": claim_id, "kind": "ranking",
        "question": f"{metric} leaderboard ({window})?",
        "criteria": {"metric": metric, "window": window, "entity_key": "player_id"},
        "ranking": ranking, "source_files": ["data/fake/source.parquet"],
        "computed_at": computed_at, "n_considered": 100, "n_excluded_below_floor": 5,
        "caveats": ["test caveat"],
    }


def _write_family(claims_dir: Path, family: str, rows: list[dict], verdicts: dict[str, str]) -> None:
    claims_path = claims_dir / f"{family}.jsonl"
    with open(claims_path, "w", encoding="ascii") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    payload = {
        "component": "test", "generated_at": "2026-07-06T00:00:00+00:00",
        "n_claims": len(rows), "n_verified": sum(1 for v in verdicts.values() if v == "VERIFIED"),
        "n_mismatch": 0, "n_unverifiable": 0, "edge_claimed": False,
        "details": [{"claim_id": cid, "verdict": v, "reason": "test"} for cid, v in verdicts.items()],
    }
    (claims_dir / f"{family}_validation.json").write_text(json.dumps(payload), encoding="ascii")


def test_seek_claim_row_reads_correct_line(tmp_path):
    rows = [
        _ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00", [{"rank": 1, "player_id": 1, "value": 10.0}]),
        _ranking_row("a2", "ast", "season", "2026-01-01T00:00:00+00:00", [{"rank": 1, "player_id": 2, "value": 5.0}]),
    ]
    _write_family(tmp_path, "fam", rows, {"a1": "VERIFIED", "a2": "VERIFIED"})
    claims_path = tmp_path / "fam.jsonl"
    with open(claims_path, "rb") as f:
        line1 = f.readline()
    offset2 = len(line1)

    row = ask_index.seek_claim_row(claims_path, offset2)
    assert row["claim_id"] == "a2"


def test_seek_claim_row_returns_none_on_bad_offset(tmp_path):
    _write_family(tmp_path, "fam", [_ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00", [])],
                   {"a1": "VERIFIED"})
    claims_path = tmp_path / "fam.jsonl"
    row = ask_index.seek_claim_row(claims_path, 99999)
    assert row is None


def test_index_top_n_lookup_returns_none_with_no_families(tmp_path):
    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["pts"], window_hint="season")
    assert ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT) is None


def test_index_top_n_lookup_finds_verified_metric_window_match(tmp_path):
    rows = [_ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00",
                          [{"rank": 1, "player_id": 1, "player_name": "Alpha", "value": 10.0}])]
    _write_family(tmp_path, "fam", rows, {"a1": "VERIFIED"})
    build_index("fam", tmp_path)

    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["pts"], window_hint="season")
    row = ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT)
    assert row is not None
    assert row["claim_id"] == "a1"
    assert row["_producer_source"] is not None


def test_index_top_n_lookup_skips_non_verified(tmp_path):
    rows = [_ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00",
                          [{"rank": 1, "player_id": 1, "value": 10.0}])]
    _write_family(tmp_path, "fam", rows, {"a1": "MISMATCH"})
    build_index("fam", tmp_path)

    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["pts"], window_hint="season")
    assert ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT) is None


def test_index_top_n_lookup_respects_metric_hint_mismatch(tmp_path):
    rows = [_ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00",
                          [{"rank": 1, "player_id": 1, "value": 10.0}])]
    _write_family(tmp_path, "fam", rows, {"a1": "VERIFIED"})
    build_index("fam", tmp_path)

    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["ast"], window_hint="season")
    assert ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT) is None


def test_index_top_n_lookup_picks_most_recent_computed_at(tmp_path):
    rows = [
        _ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00",
                      [{"rank": 1, "player_id": 1, "player_name": "Old", "value": 1.0}]),
        _ranking_row("a2", "pts", "season", "2026-02-01T00:00:00+00:00",
                      [{"rank": 1, "player_id": 2, "player_name": "New", "value": 2.0}]),
    ]
    _write_family(tmp_path, "fam", rows, {"a1": "VERIFIED", "a2": "VERIFIED"})
    build_index("fam", tmp_path)

    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["pts"], window_hint="season")
    row = ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT)
    assert row["claim_id"] == "a2"


def test_index_top_n_lookup_skips_stale_family_without_error(tmp_path):
    rows = [_ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00",
                          [{"rank": 1, "player_id": 1, "value": 10.0}])]
    _write_family(tmp_path, "fam", rows, {"a1": "VERIFIED"})
    # No build_index() call -- family is discoverable (jsonl+validation
    # pair exists) but has NO index at all -- is_index_fresh must be False.
    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["pts"], window_hint="season")
    assert ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT) is None
