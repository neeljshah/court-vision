"""Per-file tests for claims_index.py (spec sec 4, LANE L-D).

Covers: index build correctness (byte_offset seeks the right row, verdict
copied from validation summary), atomicity (no .tmp left behind), and the
staleness guard (is_index_fresh flips False the instant either source file
is touched after the index was built).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from scripts.platformkit.intel_query.claims_index import (
    IndexError_,
    build_index,
    discover_families,
    is_index_fresh,
)

FAMILY = "test_fam"


def _write_claims(claims_dir: Path, rows: list[dict]) -> Path:
    path = claims_dir / f"{FAMILY}.jsonl"
    with open(path, "w", encoding="ascii") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path


def _write_validation(claims_dir: Path, verdicts: dict[str, str]) -> Path:
    path = claims_dir / f"{FAMILY}_validation.json"
    payload = {
        "component": "test", "generated_at": "2026-07-06T00:00:00+00:00",
        "n_claims": len(verdicts), "n_verified": sum(1 for v in verdicts.values() if v == "VERIFIED"),
        "n_mismatch": 0, "n_unverifiable": 0, "edge_claimed": False,
        "details": [{"claim_id": cid, "verdict": v, "reason": "test"} for cid, v in verdicts.items()],
    }
    with open(path, "w", encoding="ascii") as f:
        json.dump(payload, f)
    return path


def _sample_rows() -> list[dict]:
    return [
        {"claim_id": "a1", "kind": "ranking", "criteria": {"metric": "pts", "window": "season", "entity_key": "player_id"},
         "computed_at": "2026-07-06T00:00:00+00:00", "ranking": [{"rank": 1, "player_id": 1, "value": 10.0}]},
        {"claim_id": "a2", "kind": "ranking", "criteria": {"metric": "ast", "window": "season", "entity_key": "player_id"},
         "computed_at": "2026-07-06T00:00:00+00:00", "ranking": [{"rank": 1, "player_id": 2, "value": 5.0}]},
    ]


def test_build_index_basic_fields(tmp_path):
    rows = _sample_rows()
    _write_claims(tmp_path, rows)
    _write_validation(tmp_path, {"a1": "VERIFIED", "a2": "MISMATCH"})

    result = build_index(FAMILY, tmp_path)
    assert result["n_indexed"] == 2
    assert result["n_verified"] == 1

    index_path = tmp_path / f"{FAMILY}.index.jsonl"
    assert index_path.exists()
    with open(index_path, "r", encoding="ascii") as f:
        idx_rows = [json.loads(line) for line in f]
    by_id = {r["claim_id"]: r for r in idx_rows}
    assert by_id["a1"]["verdict"] == "VERIFIED"
    assert by_id["a1"]["metric"] == "pts"
    assert by_id["a2"]["verdict"] == "MISMATCH"


def test_byte_offset_seeks_correct_row(tmp_path):
    rows = _sample_rows()
    claims_path = _write_claims(tmp_path, rows)
    _write_validation(tmp_path, {"a1": "VERIFIED", "a2": "VERIFIED"})
    build_index(FAMILY, tmp_path)

    index_path = tmp_path / f"{FAMILY}.index.jsonl"
    with open(index_path, "r", encoding="ascii") as f:
        idx_rows = [json.loads(line) for line in f]
    a2_offset = next(r["byte_offset"] for r in idx_rows if r["claim_id"] == "a2")

    with open(claims_path, "rb") as f:
        f.seek(a2_offset)
        line = f.readline()
    seeked_row = json.loads(line)
    assert seeked_row["claim_id"] == "a2"
    assert seeked_row["criteria"]["metric"] == "ast"


def test_atomic_no_tmp_left_behind(tmp_path):
    _write_claims(tmp_path, _sample_rows())
    _write_validation(tmp_path, {"a1": "VERIFIED", "a2": "VERIFIED"})
    build_index(FAMILY, tmp_path)
    leftovers = list(tmp_path.glob("*.tmp*"))
    assert leftovers == []


def test_missing_claims_file_raises(tmp_path):
    _write_validation(tmp_path, {"a1": "VERIFIED"})
    with pytest.raises(IndexError_):
        build_index(FAMILY, tmp_path)


def test_missing_validation_file_raises(tmp_path):
    _write_claims(tmp_path, _sample_rows())
    with pytest.raises(IndexError_):
        build_index(FAMILY, tmp_path)


def test_malformed_claims_line_raises_no_index_written(tmp_path):
    claims_path = tmp_path / f"{FAMILY}.jsonl"
    with open(claims_path, "w", encoding="ascii") as f:
        f.write('{"claim_id": "a1", "criteria": {}}\n')
        f.write("NOT VALID JSON\n")
    _write_validation(tmp_path, {"a1": "VERIFIED"})
    with pytest.raises(IndexError_):
        build_index(FAMILY, tmp_path)
    assert not (tmp_path / f"{FAMILY}.index.jsonl").exists()


def test_staleness_guard_fresh_immediately_after_build(tmp_path):
    _write_claims(tmp_path, _sample_rows())
    _write_validation(tmp_path, {"a1": "VERIFIED", "a2": "VERIFIED"})
    build_index(FAMILY, tmp_path)
    assert is_index_fresh(FAMILY, tmp_path) is True


def test_staleness_guard_flips_false_on_claims_rewrite(tmp_path):
    _write_claims(tmp_path, _sample_rows())
    _write_validation(tmp_path, {"a1": "VERIFIED", "a2": "VERIFIED"})
    build_index(FAMILY, tmp_path)
    assert is_index_fresh(FAMILY, tmp_path) is True

    time.sleep(0.05)  # ensure a distinguishable mtime tick on this filesystem
    _write_claims(tmp_path, _sample_rows())  # regen claims WITHOUT rebuilding the index
    assert is_index_fresh(FAMILY, tmp_path) is False


def test_staleness_guard_missing_index_is_not_fresh(tmp_path):
    _write_claims(tmp_path, _sample_rows())
    _write_validation(tmp_path, {"a1": "VERIFIED", "a2": "VERIFIED"})
    assert is_index_fresh(FAMILY, tmp_path) is False


def test_discover_families_requires_paired_validation(tmp_path):
    _write_claims(tmp_path, _sample_rows())  # no validation json yet
    assert discover_families(tmp_path) == []
    _write_validation(tmp_path, {"a1": "VERIFIED", "a2": "VERIFIED"})
    assert discover_families(tmp_path) == [FAMILY]


def test_discover_families_excludes_index_files_themselves(tmp_path):
    _write_claims(tmp_path, _sample_rows())
    _write_validation(tmp_path, {"a1": "VERIFIED", "a2": "VERIFIED"})
    build_index(FAMILY, tmp_path)
    # A glob for "*.jsonl" would also match test_fam.index.jsonl -- must not
    # be mistaken for its own separate family.
    assert discover_families(tmp_path) == [FAMILY]


def test_empty_family_is_vacuously_fresh(tmp_path):
    _write_claims(tmp_path, [])
    _write_validation(tmp_path, {})
    build_index(FAMILY, tmp_path)
    assert is_index_fresh(FAMILY, tmp_path) is True
