"""End-to-end smoke test: real captured book -> intents -> fills -> reconcile.
cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/test_smoke_e2e.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.execution import smoke_e2e


def _write_book(d: Path) -> None:
    rows = [
        {"ts": "2026-07-15T00:00:00Z", "venue": "kalshi", "sport": "mlb",
         "ticker": "KXMLBGAME-26JUL171940ABCDEF-ABC", "best_bid": 0.40, "best_ask": 0.60},
        {"ts": "2026-07-15T00:00:01Z", "venue": "kalshi", "sport": "mlb",
         "ticker": "KXMLBGAME-26JUL171940ABCDEF-DEF", "best_bid": 0.35, "best_ask": 0.55},
    ]
    (d / "2026-07-15.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_intents_carry_real_captured_tickers(tmp_path: Path) -> None:
    depth = tmp_path / "book"; depth.mkdir()
    _write_book(depth)
    intents = smoke_e2e.build_intents(depth, n=10)
    assert len(intents) == 2
    tickers = {i["ticker"] for i in intents}
    assert tickers == {"KXMLBGAME-26JUL171940ABCDEF-ABC", "KXMLBGAME-26JUL171940ABCDEF-DEF"}
    # mid of 0.40/0.60 book = 0.50; parse_intent needs a strict 0<p<1 prob.
    assert all(0.0 < i["model_prob"] < 1.0 for i in intents)


def test_chain_runs_and_produces_orders(tmp_path: Path) -> None:
    depth = tmp_path / "book"; depth.mkdir()
    _write_book(depth)
    out = smoke_e2e.run_smoke(depth_dir=depth, n_intents=10, work_dir=tmp_path / "w")
    assert out["edge_claimed"] is False
    assert out["n_intents_seeded"] == 2
    # every seeded intent resolves to an order (fill or cancel) -- the chain
    # never silently drops a real captured ticker.
    assert out["dryrun"]["n_written"] == 2
    assert out["reconcile"]["n_dryrun_rows"] == 2


def test_empty_book_is_honest_not_a_crash(tmp_path: Path) -> None:
    depth = tmp_path / "empty"; depth.mkdir()
    out = smoke_e2e.run_smoke(depth_dir=depth, n_intents=5, work_dir=tmp_path / "w")
    assert out["n_intents_seeded"] == 0
    assert out["dryrun"]["n_written"] == 0


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
