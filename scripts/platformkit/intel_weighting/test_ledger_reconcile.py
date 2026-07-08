"""Per-file test for ledger_reconcile.py.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_weighting/test_ledger_reconcile.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.intel_weighting import ledger_reconcile as lr


def _write(path, rows):
    with open(path, "w", encoding="ascii") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_supersedes_original_when_replication_failed(tmp_path):
    ledger = tmp_path / "claim_weights.jsonl"
    rows = [
        {"family": "ingame_compose_v2", "metric": "endQ1:floor_quality_now",
         "verdict": "MATTERS_PROVISIONAL", "method": "ingame_livestate_v2_walkforward",
         "dm_p": 0.0035},
        {"family": "ingame_compose_v2", "metric": "endQ1:floor_quality_now",
         "verdict": "NULL", "method": "ingame_livestate_v2_replication_2024_25",
         "dm_p": 0.0949},
        # an unrelated row that must be left untouched
        {"family": "ingame_compose_v2", "metric": "half:base",
         "verdict": "NULL", "method": "ingame_livestate_v2_walkforward", "dm_p": 1.0},
    ]
    _write(ledger, rows)

    changed = lr.reconcile(ledger)
    assert len(changed) == 1
    assert changed[0]["verdict"] == "MATTERS_PROVISIONAL_SUPERSEDED"
    assert "ingame_livestate_v2_replication_2024_25" in changed[0]["note"]

    on_disk = lr.read_ledger(ledger)
    by_key = {(r["metric"], r["method"]): r for r in on_disk}
    assert by_key[("endQ1:floor_quality_now", "ingame_livestate_v2_walkforward")]["verdict"] \
        == "MATTERS_PROVISIONAL_SUPERSEDED"
    # the replication row itself and the unrelated row are untouched
    assert by_key[("endQ1:floor_quality_now", "ingame_livestate_v2_replication_2024_25")]["verdict"] == "NULL"
    assert by_key[("half:base", "ingame_livestate_v2_walkforward")]["verdict"] == "NULL"
    assert len(on_disk) == 3  # append-only: no row deleted


def test_no_supersession_when_no_replication_row(tmp_path):
    ledger = tmp_path / "claim_weights.jsonl"
    rows = [{"family": "f", "metric": "m", "verdict": "MATTERS_PROVISIONAL",
             "method": "some_walkforward", "dm_p": 0.01}]
    _write(ledger, rows)

    changed = lr.reconcile(ledger)
    assert changed == []
    on_disk = lr.read_ledger(ledger)
    assert on_disk[0]["verdict"] == "MATTERS_PROVISIONAL"


def test_no_supersession_when_replication_confirms(tmp_path):
    ledger = tmp_path / "claim_weights.jsonl"
    rows = [
        {"family": "f", "metric": "m", "verdict": "MATTERS_PROVISIONAL",
         "method": "some_walkforward", "dm_p": 0.01},
        {"family": "f", "metric": "m", "verdict": "MATTERS_PROVISIONAL",
         "method": "some_replication_2024_25", "dm_p": 0.02},
    ]
    _write(ledger, rows)

    changed = lr.reconcile(ledger)
    assert changed == []


def test_idempotent_second_run_is_a_noop(tmp_path):
    ledger = tmp_path / "claim_weights.jsonl"
    rows = [
        {"family": "f", "metric": "m", "verdict": "MATTERS_PROVISIONAL",
         "method": "some_walkforward", "dm_p": 0.01},
        {"family": "f", "metric": "m", "verdict": "NULL",
         "method": "some_replication_2024_25", "dm_p": 0.09},
    ]
    _write(ledger, rows)

    first = lr.reconcile(ledger)
    assert len(first) == 1
    second = lr.reconcile(ledger)
    assert second == []  # already MATTERS_PROVISIONAL_SUPERSEDED -- not re-matched
