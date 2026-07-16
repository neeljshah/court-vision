"""Tests for scripts/platformkit/analytics_verify/contradiction.py

Synthetic families in tmp_path prove each conflict kind plus the schema-skip
path. A separate real-store smoke test is skipped if the store is absent.
"""
import json
import os

import pytest

from scripts.platformkit.analytics_verify.contradiction import run

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _rec(claim_id, metric, window, ranking, computed_at="2026-01-01T00:00:00+00:00", entity_key="player_id"):
    return {
        "claim_id": claim_id, "kind": "ranking",
        "question": "test", "computed_at": computed_at,
        "criteria": {"metric": metric, "window": window, "entity_key": entity_key, "direction": "desc"},
        "ranking": ranking, "edge_claimed": False, "caveats": ["DESCRIPTIVE test fixture only."],
    }


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _build_store(store_dir):
    # SIGN_CONFLICT (+ incidental VALUE_CONFLICT, same entity, opposite sign)
    _write_jsonl(os.path.join(store_dir, "fam_sign_a.jsonl"), [
        _rec("c_sign_a", "k_rate", "w_sign", [{"rank": 1, "player_id": 1, "value": 5.0}]),
    ])
    _write_jsonl(os.path.join(store_dir, "fam_sign_b.jsonl"), [
        _rec("c_sign_b", "k_rate", "w_sign", [{"rank": 1, "player_id": 1, "value": -5.0}]),
    ])

    # RANK_CONFLICT via large rank-gap
    a_rank = [{"rank": i, "player_id": i, "value": 10.0 - i} for i in range(1, 7)]
    b_rank = [{"rank": i, "player_id": p, "value": 10.0 - p}
              for i, p in enumerate([2, 3, 4, 5, 6, 1], start=1)]
    _write_jsonl(os.path.join(store_dir, "fam_rank_a.jsonl"), [_rec("c_rank_a", "gap_metric", "w_rank", a_rank)])
    _write_jsonl(os.path.join(store_dir, "fam_rank_b.jsonl"), [_rec("c_rank_b", "gap_metric", "w_rank", b_rank)])

    # VALUE_CONFLICT only (same rank, same sign, >20% relative diff)
    _write_jsonl(os.path.join(store_dir, "fam_value_a.jsonl"), [
        _rec("c_value_a", "value_metric", "w_value", [{"rank": 1, "player_id": 1, "value": 100.0}]),
    ])
    _write_jsonl(os.path.join(store_dir, "fam_value_b.jsonl"), [
        _rec("c_value_b", "value_metric", "w_value", [{"rank": 1, "player_id": 1, "value": 130.0}]),
    ])

    # STALE_PAIR: same family, same claim key, computed_at spread > 30 days
    _write_jsonl(os.path.join(store_dir, "fam_stale.jsonl"), [
        _rec("c_stale", "stale_metric", "w_stale", [{"rank": 1, "player_id": 1, "value": 1.0}],
             computed_at="2026-01-01T00:00:00+00:00"),
        _rec("c_stale", "stale_metric", "w_stale", [{"rank": 1, "player_id": 1, "value": 1.0}],
             computed_at="2026-03-15T00:00:00+00:00"),
    ])

    # schema-mismatched family (should be skipped, not crash the run)
    _write_jsonl(os.path.join(store_dir, "fam_ledger.jsonl"), [
        {"claim_id": "l1", "kind": "verdict", "computed_at": "2026-01-01T00:00:00+00:00", "verdict": "PASS"},
    ])

    # an .index.jsonl pointer file must be excluded from discovery entirely
    _write_jsonl(os.path.join(store_dir, "fam_sign_a.index.jsonl"), [
        {"claim_id": "c_sign_a", "byte_offset": 0},
    ])


def test_conflict_kinds_and_skip_path(tmp_path):
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    _build_store(str(store_dir))
    out_path = tmp_path / "report.json"

    report = run(store_dir=str(store_dir), out_path=str(out_path))

    assert out_path.exists()
    with open(out_path, encoding="utf-8") as fh:
        on_disk = json.load(fh)
    # JSON round-trip turns entity tuples into lists; compare everything else exactly.
    assert on_disk["n_claims"] == report["n_claims"]
    assert on_disk["n_conflicts_by_kind"] == report["n_conflicts_by_kind"]
    assert on_disk["families_scanned"] == report["families_scanned"]

    assert report["edge_claimed"] is False
    kinds = {c["kind"] for c in report["conflicts"]}
    assert "SIGN_CONFLICT" in kinds
    assert "RANK_CONFLICT" in kinds
    assert "VALUE_CONFLICT" in kinds
    assert "STALE_PAIR" in kinds
    assert report["n_conflicts_by_kind"]["SIGN_CONFLICT"] >= 1
    assert report["n_conflicts_by_kind"]["RANK_CONFLICT"] >= 1
    assert report["n_conflicts_by_kind"]["VALUE_CONFLICT"] >= 1
    assert report["n_conflicts_by_kind"]["STALE_PAIR"] >= 1

    # schema-mismatch skip path
    skipped_names = {s["family"] for s in report["families_skipped"]}
    assert "fam_ledger" in skipped_names
    # index pointer files never enter families_scanned or families_skipped
    all_seen = set(report["families_scanned"]) | skipped_names
    assert "fam_sign_a.index" not in all_seen

    # by_family_consistency has an entry per scanned family (score = 1 - conflicts/pairs,
    # per spec; can go below 0 when one comparable pair yields multiple conflict kinds).
    for fam in report["families_scanned"]:
        rec = report["by_family_consistency"][fam]
        assert isinstance(rec["consistency"], float)
        assert rec["consistency"] <= 1.0

    assert report["n_claims"] > 0
    assert report["n_comparable_pairs"] > 0


def test_real_store_smoke():
    store_dir = os.path.join(REPO_ROOT, "data", "cache", "intel_claims")
    if not os.path.isdir(store_dir):
        pytest.skip("data/cache/intel_claims not present in this checkout")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        report = run(store_dir=store_dir, out_path=os.path.join(td, "report.json"), max_lines=200)
    assert report["edge_claimed"] is False
    assert len(report["families_scanned"]) > 0
