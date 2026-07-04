"""Per-file tests for scripts.platformkit.clv_ledger_backfill_report.

Acceptance criteria (LANE-4 ledger hygiene):
  1. A settled row with a Kalshi-ticker game_id (off ESPN id-space) is counted
       unresolvable with cause="off_id_space", never silently dropped.
  2. A settled row on a prop market is counted unresolvable with
       cause="prop_market_out_of_scope".
  3. A settled row already carrying closing_decimal_home/away (resolvable via
       the existing enrich path with NO line_store lookup needed) is backfilled:
       backfilled_rows has an entry with clv_pct not None.
  4. write_sidecar() is idempotent: running it twice on the same report does
       not duplicate rows (second run's written=0, skipped=written_first_time).
  5. write_report() never mutates the source ledger file (byte-identical).
  6. Missing/empty ledger -> status INSUFFICIENT_DATA, zero counts.
  7. No banned $ key anywhere in the report or sidecar rows.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_backfill_report.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.platformkit.clv_ledger_backfill_report import (
    build_report, write_sidecar, write_report,
)

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


def test_off_id_space_kalshi_ticker(tmp_path):
    rows = [
        {"sport": "mlb", "status": "settled", "side": "home",
         "game_id": "KXMLBGAME-26JUL011310TEXCLE", "market": "win_home",
         "taken_decimal": 1.94, "clv_pct": None},
    ]
    p = _write_ledger(tmp_path, rows)
    res = build_report(p)
    assert res["total_settled_without_clv"] == 1
    assert res["backfilled"] == 0
    assert res["unresolvable"] == 1
    assert res["unresolvable_by_cause"].get("off_id_space") == 1


def test_prop_market_out_of_scope(tmp_path):
    rows = [
        {"sport": "mlb", "status": "settled", "side": "under",
         "game_id": "401815964", "market": "prop|Colby Thomas|Hits|0.5|under",
         "taken_decimal": 1.8, "clv_pct": None},
    ]
    p = _write_ledger(tmp_path, rows)
    res = build_report(p)
    assert res["unresolvable_by_cause"].get("prop_market_out_of_scope") == 1


def test_backfilled_when_closing_line_embedded(tmp_path):
    rows = [
        {"sport": "mlb", "status": "settled", "side": "home",
         "game_id": "401815964", "market": "moneyline",
         "taken_decimal": 1.90, "clv_pct": None,
         "closing_decimal_home": 1.80, "closing_decimal_away": 2.10},
    ]
    p = _write_ledger(tmp_path, rows)
    res = build_report(p)
    assert res["backfilled"] == 1
    assert res["unresolvable"] == 0
    assert len(res["backfilled_rows"]) == 1
    assert res["backfilled_rows"][0]["clv_pct"] is not None


def test_sidecar_idempotent(tmp_path):
    rows = [
        {"sport": "mlb", "status": "settled", "side": "home",
         "game_id": "401815964", "market": "moneyline",
         "taken_decimal": 1.90, "clv_pct": None,
         "closing_decimal_home": 1.80, "closing_decimal_away": 2.10},
    ]
    p = _write_ledger(tmp_path, rows)
    res = build_report(p)
    sidecar_path = tmp_path / "clv_backfill.jsonl"
    first = write_sidecar(res, sidecar_path)
    assert first["written"] == 1
    second = write_sidecar(res, sidecar_path)
    assert second["written"] == 0
    assert second["skipped"] == 1


def test_write_report_never_mutates_ledger(tmp_path):
    rows = [
        {"sport": "mlb", "status": "settled", "side": "home",
         "game_id": "KXMLBGAME-1", "market": "win_home",
         "taken_decimal": 1.5, "clv_pct": None},
    ]
    p = _write_ledger(tmp_path, rows)
    before = p.read_bytes()
    out = tmp_path / "ops" / "clv_backfill_report.json"
    sidecar = tmp_path / "clv_backfill.jsonl"
    write_report(p, out, sidecar)
    after = p.read_bytes()
    assert before == after
    assert out.exists()


def test_missing_ledger_insufficient_data(tmp_path):
    p = tmp_path / "absent.jsonl"
    res = build_report(p)
    assert res["status"] == "INSUFFICIENT_DATA"
    assert res["total_settled_without_clv"] == 0


def test_no_banned_keys(tmp_path):
    rows = [
        {"sport": "mlb", "status": "settled", "side": "home",
         "game_id": "401815964", "market": "moneyline",
         "taken_decimal": 1.90, "clv_pct": None,
         "closing_decimal_home": 1.80, "closing_decimal_away": 2.10},
        {"sport": "mlb", "status": "settled", "side": "home",
         "game_id": "KXMLBGAME-1", "market": "win_home",
         "taken_decimal": 1.5, "clv_pct": None},
    ]
    p = _write_ledger(tmp_path, rows)
    res = build_report(p)
    _assert_no_banned(res)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
