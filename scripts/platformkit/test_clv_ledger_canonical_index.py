"""Per-file tests for scripts.platformkit.clv_ledger_canonical_index.

Acceptance criteria (LANE-4 ledger hygiene):
  1. Two rows sharing bet_id+status (true collision) -> 1 canonical cluster,
       dup_row_to_canonical maps the non-canonical index to the canonical one.
  2. Two rows with DIFFERENT bet_id but the SAME coarse (matchup-fallback) key
       -> coarse_report counts it as n_false_positive, NOT a canonical cluster.
  3. completeness rule: when the first-written row has no CLV and a later row
       in the same true cluster has clv_pct set, the LATER (more complete) row
       is picked as canonical (rule="more_complete_row").
  4. Missing/empty ledger -> status INSUFFICIENT_DATA, zero clusters.
  5. write_index() persists valid JSON to the given --out path; never writes to
       the source ledger path (file is byte-identical after the call).
  6. No banned $ key anywhere in the output.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_canonical_index.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.platformkit.clv_ledger_canonical_index import build_index, write_index

_BANNED = frozenset({
    "pnl", "profit", "bankroll", "roi", "dollars", "total_pnl", "total_stake",
    "paper_roi", "stake", "net_profit", "return",
})


def _assert_no_banned(obj: Any) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert str(k).lower() not in _BANNED, "banned key %r found" % k
            _assert_no_banned(v)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_banned(item)


def _write_ledger(tmp_path: Path, rows) -> Path:
    p = tmp_path / "clv_ledger.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def test_true_collision_same_bet_id_status(tmp_path):
    rows = [
        {"sport": "mlb", "bet_id": "mlb|1|moneyline|home|fd|2026-07-01",
         "status": "open", "side": "home", "game_id": "401815964"},
        {"sport": "mlb", "bet_id": "mlb|1|moneyline|home|fd|2026-07-01",
         "status": "open", "side": "home", "game_id": "401815964"},
    ]
    p = _write_ledger(tmp_path, rows)
    res = build_index(p)
    assert res["status"] == "ok"
    assert res["canonical_clusters"] == 1
    assert len(res["dup_row_to_canonical"]) == 1
    # the surviving value must point at index 0 (first-written, equally complete)
    assert list(res["dup_row_to_canonical"].values()) == [0]
    assert list(res["dup_row_to_canonical"].keys()) == ["1"]


def test_false_positive_distinct_bet_id_same_coarse_key(tmp_path):
    # Same recurring matchup label, different real games (different bet_id),
    # both missing game_date -> coarse key collides but canonical identity differs.
    rows = [
        {"sport": "mlb", "bet_id": "mlb|401815952|moneyline|home|kalshi|2026-06-29",
         "status": "open", "side": "home", "matchup": "NYY vs DET",
         "taken_book": "kalshi"},
        {"sport": "mlb", "bet_id": "mlb|401815980|moneyline|home|kalshi|2026-07-01",
         "status": "open", "side": "home", "matchup": "NYY vs DET",
         "taken_book": "kalshi"},
    ]
    p = _write_ledger(tmp_path, rows)
    res = build_index(p)
    assert res["canonical_clusters"] == 0
    assert res["dup_row_to_canonical"] == {}
    cr = res["coarse_report"]
    assert cr["n_coarse_clusters"] == 1
    assert cr["n_false_positive"] == 1
    assert cr["n_true_collision"] == 0


def test_more_complete_row_wins_canonical(tmp_path):
    rows = [
        {"sport": "mlb", "edge_key": "mlb|GAME1|win_home|home|2026-06-30",
         "status": "settled", "side": "home",
         "clv_pct": None, "clv_status": "no_close"},
        {"sport": "mlb", "edge_key": "mlb|GAME1|win_home|home|2026-06-30",
         "status": "settled", "side": "home",
         "clv_pct": 3.5, "clv_status": "clv_real"},
    ]
    p = _write_ledger(tmp_path, rows)
    res = build_index(p)
    assert res["canonical_clusters"] == 1
    cluster = res["clusters"][0]
    assert cluster["canonical_idx"] == 1
    assert cluster["rule"] == "more_complete_row"
    assert res["dup_row_to_canonical"] == {"0": 1}


def test_missing_ledger_insufficient_data(tmp_path):
    p = tmp_path / "absent.jsonl"
    res = build_index(p)
    assert res["status"] == "INSUFFICIENT_DATA"
    assert res["canonical_clusters"] == 0
    assert res["dup_row_to_canonical"] == {}


def test_write_index_persists_and_never_touches_source(tmp_path):
    rows = [
        {"sport": "mlb", "bet_id": "a", "status": "open", "side": "home"},
    ]
    ledger = _write_ledger(tmp_path, rows)
    before = ledger.read_bytes()
    out = tmp_path / "out" / "index.json"
    res = write_index(ledger, out)
    after = ledger.read_bytes()
    assert before == after, "source ledger must never be mutated"
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["version"] == res["version"]


def test_no_banned_dollar_keys(tmp_path):
    rows = [
        {"sport": "mlb", "bet_id": "a", "status": "open", "side": "home"},
        {"sport": "mlb", "bet_id": "a", "status": "open", "side": "home"},
    ]
    p = _write_ledger(tmp_path, rows)
    res = build_index(p)
    _assert_no_banned(res)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
