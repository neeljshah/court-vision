"""Per-file test for settlement_correctness_audit.py (B2 sweep).

Hermetic synthetic ledger fixtures; no network; does not touch the real
data/frontend/clv_ledger.jsonl (gitignored, machine-specific).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/paper/test_settlement_correctness_audit.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.paper.settlement_correctness_audit import (
    audit_ingame_channel,
    close_source_coverage,
    dedup_check,
    audit_pregame_channels,
    run,
)


def _ledger(tmp_path, rows):
    p = tmp_path / "clv_ledger.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def test_close_source_coverage_splits_real_vs_fallback():
    rows = [
        {"status": "settled", "sport": "mlb", "close_source": "draftkings"},
        {"status": "settled", "sport": "mlb", "close_source": "cross_venue_fallback"},
        {"status": "settled", "sport": "mlb", "close_source": None},
        {"status": "settled", "sport": "mlb", "close_source": "none_available"},
        {"status": "open", "sport": "mlb", "close_source": "draftkings"},  # ignored, not settled
    ]
    out = close_source_coverage(rows)
    assert out["mlb"]["n_settled"] == 4
    assert out["mlb"]["pct_real_book_close"] == 25.0


def test_dedup_check_flags_real_duplicates():
    rows = [
        {"status": "open", "channel": "paper_ingame", "edge_key": "a"},
        {"status": "open", "channel": "paper_ingame", "edge_key": "a"},  # duplicate open
        {"status": "settled", "settle_key": "s1"},
        {"status": "settled", "settle_key": "s1"},  # duplicate settled
        {"status": "settled", "settle_key": "s2"},
    ]
    out = dedup_check(rows)
    assert out["duplicate_open_edge_keys"] == {"paper_ingame|a": 2}
    assert out["duplicate_settled_identities"] == {"s1": 2}


def test_pregame_consistency_catches_outcome_drift():
    # Stored outcome disagrees with a fresh recompute from the row's OWN
    # stored home_score/away_score/side -- must be flagged, not silently trusted.
    rows = [{
        "channel": "paper", "status": "settled", "sport": "mlb",
        "side": "home", "home_score": 5, "away_score": 2,
        "outcome": "loss",  # WRONG -- home won 5-2, side=home should be "win"
        "taken_decimal": 1.9, "stake_units": 1.0, "unit_result": -1.0,
        "matchup": "Boston Red Sox @ New York Yankees", "ts": "2026-07-01T00:00:00Z",
    }]
    out = audit_pregame_channels(rows)
    assert out["by_sport"]["mlb"]["outcome_mismatch"] == 1


def test_pregame_consistency_passes_clean_row():
    rows = [{
        "channel": "paper", "status": "settled", "sport": "mlb",
        "side": "home", "home_score": 5, "away_score": 2, "outcome": "win",
        "taken_decimal": 1.9, "stake_units": 1.0, "unit_result": 0.9,
        "matchup": "Boston Red Sox @ New York Yankees", "ts": "2026-07-01T00:00:00Z",
    }]
    out = audit_pregame_channels(rows)
    assert out["by_sport"]["mlb"]["consistent"] == 1
    assert "outcome_mismatch" not in out["by_sport"]["mlb"]


def test_ingame_orphan_duplicate_open_separated_from_genuinely_pending():
    # edge_key "a" has BOTH an open row and a settled twin -- the live settle
    # daemon's own dedup guard would skip it forever (never "stuck", just
    # orphaned). edge_key "b" is a genuinely standalone open row.
    rows = [
        {"channel": "paper_ingame", "status": "open", "sport": "mlb",
         "game_id": "g1", "edge_key": "a"},
        {"channel": "paper_ingame", "status": "settled", "sport": "mlb",
         "game_id": "g1", "edge_key": "a", "home_score": 5, "away_score": 2},
        {"channel": "paper_ingame", "status": "open", "sport": "mlb",
         "game_id": "g2", "edge_key": "b"},
    ]
    fresh_scores = {"g1": (5, 2), "g2": (3, 1)}  # both now resolvable
    out = audit_ingame_channel(rows, score_fn=lambda gid: fresh_scores.get(gid))
    c = out["by_sport"]["mlb"]
    assert c["orphan_duplicate_open"] == 1
    assert c["unsettled_but_final"] == 1
    assert c["score_match"] == 1


def test_run_end_to_end_never_raises_on_empty_ledger(tmp_path):
    p = _ledger(tmp_path, [])
    out = run(ledger_path=p)
    assert out["n_rows"] == 0
    assert out["dedup"]["duplicate_open_edge_keys"] == {}
