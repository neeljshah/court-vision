"""Per-file test: scripts/platformkit/improve/test_prop_history_meta.py
Run: python -m pytest scripts/platformkit/improve/test_prop_history_meta.py -q

Covers the read-only meta-aggregator: source=history filtering, (sport, stat) grouping, the
conservative do-no-harm replication rule (single SHIP -> artifact-suspect, >=2 -> replicated,
any REJECT or planted-null leak -> REJECT), and read-only JSON surface output.
"""
from __future__ import annotations

import json

from scripts.platformkit.improve import prop_history_meta as G


def _fold(sport, verdict, **kw):
    r = {"source": "history", "sport": sport, "verdict": verdict}
    r.update(kw)
    return r


def _write_ledger(tmp_path, recs):
    p = tmp_path / "ledger.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    return p


def test_only_history_rows_loaded(tmp_path):
    led = _write_ledger(tmp_path, [
        _fold("nba", "SHIP"),
        {"source": "live", "sport": "nba", "verdict": "HOLD"},  # not history -> ignored
        {"sport": "nba", "verdict": "SHIP"},                     # no source -> ignored
    ])
    folds = G.load_history_folds(led)
    assert len(folds) == 1 and folds[0]["sport"] == "nba"


def test_single_ship_is_artifact_suspect(tmp_path):
    led = _write_ledger(tmp_path, [_fold("mlb", "SHIP", delta_brier=0.01, null_shipped=False)])
    groups = G.aggregate(G.load_history_folds(led))
    assert len(groups) == 1
    assert groups[0]["replicated_verdict"] == "SHIP_SINGLE_FOLD"
    assert groups[0]["ship_folds"] == 1


def test_two_ships_replicate(tmp_path):
    led = _write_ledger(tmp_path, [
        _fold("mlb", "SHIP", delta_brier=0.011, null_shipped=False),
        _fold("mlb", "SHIP", delta_brier=0.009, null_shipped=False),
    ])
    g = G.aggregate(G.load_history_folds(led))[0]
    assert g["replicated_verdict"] == "SHIP_REPLICATED"
    assert g["ship_folds"] == 2
    assert g["median_delta_brier"] == 0.01


def test_any_reject_blocks_ship(tmp_path):
    led = _write_ledger(tmp_path, [
        _fold("tennis", "SHIP", delta_brier=0.02, null_shipped=False),
        _fold("tennis", "SHIP", delta_brier=0.02, null_shipped=False),
        _fold("tennis", "REJECT"),
    ])
    g = G.aggregate(G.load_history_folds(led))[0]
    assert g["replicated_verdict"] == "REJECT"  # do-no-harm: a reject blocks the group


def test_planted_null_leak_blocks_ship(tmp_path):
    led = _write_ledger(tmp_path, [
        _fold("tennis", "SHIP", delta_brier=0.02, null_shipped=True),
        _fold("tennis", "SHIP", delta_brier=0.02, null_shipped=False),
    ])
    g = G.aggregate(G.load_history_folds(led))[0]
    assert g["any_planted_null_leak"] is True
    assert g["replicated_verdict"] == "REJECT"


def test_insufficient_and_hold(tmp_path):
    led = _write_ledger(tmp_path, [
        _fold("soccer", "INSUFFICIENT_DATA"),
        _fold("soccer", "INSUFFICIENT_DATA"),
    ])
    assert G.aggregate(G.load_history_folds(led))[0]["replicated_verdict"] == "INSUFFICIENT_DATA"
    led2 = _write_ledger(tmp_path, [_fold("nba", "HOLD"), _fold("nba", "HOLD")])
    assert G.aggregate(G.load_history_folds(led2))[0]["replicated_verdict"] == "HOLD"


def test_groups_split_by_stat(tmp_path):
    led = _write_ledger(tmp_path, [
        _fold("mlb", "SHIP", stat="hits", null_shipped=False),
        _fold("mlb", "SHIP", stat="hits", null_shipped=False),
        _fold("mlb", "REJECT", stat="rbi"),
    ])
    groups = {(g["sport"], g["stat"]): g for g in G.aggregate(G.load_history_folds(led))}
    assert groups[("mlb", "hits")]["replicated_verdict"] == "SHIP_REPLICATED"
    assert groups[("mlb", "rbi")]["replicated_verdict"] == "REJECT"


def test_run_writes_readonly_surface(tmp_path):
    led = _write_ledger(tmp_path, [_fold("mlb", "SHIP", null_shipped=False)])
    out = tmp_path / "meta.json"
    report = G.run(ledger_path=led, out_path=out, write=True)
    assert out.exists()
    disk = json.loads(out.read_text())
    assert disk["n_history_folds"] == 1
    assert "calibration != edge" in report["note"]
    # honest: no $ / serving keys in the report
    blob = json.dumps(report).lower()
    assert "dollars" not in blob and "roi" not in blob and "armed" not in blob.replace("no serving armed", "")
