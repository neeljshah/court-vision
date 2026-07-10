"""Per-file test for scripts.platformkit.ledger_squash.

Run: python -m pytest tests/platformkit/test_ledger_squash.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ledger_squash import squash_ledger


def test_squash_ledger_keeps_first_occurrence_and_backs_up(tmp_path):
    p = tmp_path / "validation_ledger.jsonl"
    rows = [
        {"hypothesis": "a", "verdict": "NULL_LOCAL", "n": 10, "run_ts": "T1"},
        {"hypothesis": "b", "verdict": "CONFIRMED_LOCAL", "n": 20, "run_ts": "T1"},
        {"hypothesis": "a", "verdict": "NULL_LOCAL", "n": 10, "run_ts": "T2"},  # dup of row 0
        {"hypothesis": "a", "verdict": "NULL_LOCAL", "n": 30, "run_ts": "T3"},  # distinct (n differs)
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    before, after = squash_ledger(str(p))
    assert (before, after) == (4, 3)

    kept = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert [r["run_ts"] for r in kept] == ["T1", "T1", "T3"]  # order preserved, T2 dropped

    bak = p.parent / (p.name + ".pre_squash_2026-07-10.bak")
    assert bak.is_file()
    bak_rows = [json.loads(ln) for ln in bak.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(bak_rows) == 4  # backup preserves the pre-squash content


def test_squash_ledger_no_dupes_is_noop_no_backup(tmp_path):
    p = tmp_path / "validation_ledger.jsonl"
    rows = [{"hypothesis": "a", "n": 1}, {"hypothesis": "b", "n": 2}]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    before, after = squash_ledger(str(p))
    assert (before, after) == (2, 2)
    assert not (p.parent / (p.name + ".pre_squash_2026-07-10.bak")).exists()


def test_squash_ledger_missing_file_is_zero_zero(tmp_path):
    assert squash_ledger(str(tmp_path / "nope.jsonl")) == (0, 0)
