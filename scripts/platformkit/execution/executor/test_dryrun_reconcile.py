"""Per-file tests: dry-run pass (composed intents -> as-of-stamped simulated
fills, idempotent re-runs, honest input-missing) + tape reconciliation.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/executor/test_dryrun_reconcile.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.platformkit.execution.book_replay import load_jsonl
from scripts.platformkit.execution.executor import dryrun, reconcile
from scripts.platformkit.execution.executor.lifecycle import resolve_exchange


def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _depth_dir(tmp_path: Path, rows) -> Path:
    d = tmp_path / "book_depth"
    _write_jsonl(d / "2026-07-09.jsonl", rows)
    return d


NOW = datetime.now(timezone.utc)
SNAP = {"ticker": "KXDRY-A", "best_bid": 0.40, "best_ask": 0.45,
        "book_thinness": 100.0, "ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sport": "mlb"}
COMPOSED = [
    {"ticker": "KXDRY-A", "side": "yes", "model_prob": 0.50, "sport": "mlb"},
    {"ticker": "KXDRY-A", "side": "no", "market_prob": 0.30, "sport": "mlb"},
    {"note": "row without ticker/price is skipped honestly"},
]


def test_parse_intent_tolerant_and_strict():
    it = dryrun.parse_intent(COMPOSED[0])
    assert it == {"ticker": "KXDRY-A", "side": "yes", "qty": 10,
                  "price_cents": 50, "sport": "mlb"}
    assert dryrun.parse_intent(COMPOSED[2]) is None
    assert dryrun.parse_intent({"ticker": "X", "model_prob": 1.5}) is None


def test_dryrun_writes_asof_stamped_fills_and_is_idempotent(tmp_path):
    inp = tmp_path / "bestbets_composed.jsonl"
    out = tmp_path / "dryrun_orders.jsonl"
    _write_jsonl(inp, COMPOSED)
    depth = _depth_dir(tmp_path, [SNAP])

    rep = dryrun.run_dryrun(inp, out, depth)
    assert rep["n_input_rows"] == 3 and rep["n_intents"] == 2
    assert rep["n_written"] == 2 and rep["n_unparseable"] == 1
    rows = load_jsonl(out)
    assert len(rows) == 2
    yes_row = next(r for r in rows if r["side"] == "yes")
    assert yes_row["state"] == "FILLED" and yes_row["avg_fill_price_cents"] == 45.0
    assert yes_row["asof_ts"] and yes_row["book_ts"] == SNAP["ts"]
    assert yes_row["slippage_cents"] == -5.0  # filled at ask 45 vs limit 50
    assert yes_row["history"][:2] == ["SUBMITTED", "ACKED"]
    # no buy at 30 does not cross (100 - bid 40 = 60) -> immediate cancel
    no_row = next(r for r in rows if r["side"] == "no")
    assert no_row["state"] == "CANCELLED" and no_row["filled_qty"] == 0

    # Re-run: every intent already logged -> skipped, file unchanged.
    rep2 = dryrun.run_dryrun(inp, out, depth)
    assert rep2["n_skipped_idempotent"] == 2 and rep2["n_written"] == 0
    assert len(load_jsonl(out)) == 2


def test_resolve_mlb_ticker_synthetic_row():
    """M13 fix: a composed row with NO ticker/kalshi_ticker/market_id (the
    real-world shape composer emits) still resolves via captured book_depth
    legs + KALSHI_ABBR team-name lookup -- proves the parser seam works even
    when no live board is available to exercise it end-to-end."""
    legs = dryrun.leg_index([
        {"ticker": "KXMLBGAME-26JUL121340CLEMIA-CLE"},
        {"ticker": "KXMLBGAME-26JUL121340CLEMIA-MIA"},
    ])
    row = {"sport": "mlb", "game_id": "KXMLBGAME-26JUL121340CLEMIA",
           "matchup": "Cleveland Guardians vs Miami Marlins", "side": "home"}
    assert dryrun.resolve_mlb_ticker(row, legs) == "KXMLBGAME-26JUL121340CLEMIA-CLE"
    away_row = dict(row, side="away")
    assert dryrun.resolve_mlb_ticker(away_row, legs) == "KXMLBGAME-26JUL121340CLEMIA-MIA"
    # honest misses: wrong sport, no captured legs for this game, unknown side.
    assert dryrun.resolve_mlb_ticker(dict(row, sport="nba"), legs) is None
    assert dryrun.resolve_mlb_ticker(dict(row, game_id="KXMLBGAME-NOPE"), legs) is None
    assert dryrun.resolve_mlb_ticker(dict(row, side="tie"), legs) is None


def test_dryrun_resolves_mlb_ticker_end_to_end(tmp_path):
    """Same fix, exercised through run_dryrun end-to-end: a composer-shaped
    row (game_id + matchup + side, no ticker) parses and fills."""
    inp = tmp_path / "bestbets_composed.jsonl"
    out = tmp_path / "dryrun_orders.jsonl"
    row = {"sport": "mlb", "game_id": "KXMLBGAME-26JUL121340CLEMIA",
           "matchup": "Cleveland Guardians vs Miami Marlins",
           "market_type": "moneyline", "side": "home", "model_prob": 0.55}
    _write_jsonl(inp, [row])
    snap = {"ticker": "KXMLBGAME-26JUL121340CLEMIA-CLE", "best_bid": 0.50,
            "best_ask": 0.56, "book_thinness": 100.0,
            "ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "sport": "mlb"}
    depth = _depth_dir(tmp_path, [snap])

    rep = dryrun.run_dryrun(inp, out, depth)
    assert rep["n_unparseable"] == 0 and rep["n_ticker_resolved"] == 1
    assert rep["n_written"] == 1
    written = load_jsonl(out)[0]
    assert written["ticker"] == "KXMLBGAME-26JUL121340CLEMIA-CLE"


def test_dryrun_missing_input_reports_honestly(tmp_path):
    rep = dryrun.run_dryrun(tmp_path / "absent.jsonl",
                            tmp_path / "out.jsonl", _depth_dir(tmp_path, [SNAP]))
    assert rep["input_missing"] is True and rep["n_written"] == 0
    assert not (tmp_path / "out.jsonl").exists()


def test_load_latest_books_keeps_freshest_per_ticker(tmp_path):
    d = tmp_path / "bd"
    _write_jsonl(d / "2026-07-08.jsonl", [{**SNAP, "ts": "2026-07-08T01:00:00Z",
                                           "best_ask": 0.99}])
    _write_jsonl(d / "2026-07-09.jsonl", [{**SNAP, "ts": "2026-07-09T01:00:00Z",
                                           "best_ask": 0.45}])
    books = dryrun.load_latest_books(d)
    assert len(books) == 1 and books[0]["best_ask"] == 0.45


def test_dryrun_cli_live_flag_raises_without_config(monkeypatch):
    with pytest.raises(RuntimeError, match="not set"):
        resolve_exchange(live=True)  # the gate main() hits first on --live
    monkeypatch.setattr("sys.argv", ["dryrun", "--live"])
    with pytest.raises(RuntimeError, match="No real order was sent"):
        dryrun.main()  # raises BEFORE any input/book work is attempted


def test_reconcile_plausible_optimistic_and_not_testable(tmp_path):
    asof = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    later = (NOW + timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    orders = tmp_path / "dryrun_orders.jsonl"
    _write_jsonl(orders, [
        # fill at 0.45 sits inside the later [0.40, 0.45] book -> plausible
        {"idempotency_key": "a", "ticker": "KXDRY-A", "asof_ts": asof,
         "filled_qty": 5, "avg_fill_price_cents": 45.0, "slippage_cents": -5.0},
        # claims 0.20, later book shows [0.40, 0.45] -> optimistic
        {"idempotency_key": "b", "ticker": "KXDRY-A", "asof_ts": asof,
         "filled_qty": 5, "avg_fill_price_cents": 20.0, "slippage_cents": 0.0},
        # no captured tape for this ticker -> NOT_TESTABLE
        {"idempotency_key": "c", "ticker": "KXDRY-GONE", "asof_ts": asof,
         "filled_qty": 5, "avg_fill_price_cents": 45.0, "slippage_cents": None},
        # unfilled rows are not fills, never tested
        {"idempotency_key": "d", "ticker": "KXDRY-A", "asof_ts": asof,
         "filled_qty": 0, "avg_fill_price_cents": 0.0, "slippage_cents": None},
    ])
    depth = _depth_dir(tmp_path, [{**SNAP, "ts": later}])
    rep = reconcile.run_reconcile(orders, depth)
    assert rep["n_dryrun_rows"] == 4 and rep["n_fills"] == 3
    vt = rep["vs_later_tape"]
    assert vt["n_tested"] == 2
    assert vt["pct_plausible"] == 50.0 and vt["pct_optimistic"] == 50.0
    assert vt["post_fill_drift_price_units"]["n"] == 2
    assert rep["edge_claimed"] is False
    assert rep["sim_fill_vs_limit_price_units"]["n"] == 2


def test_reconcile_skips_stale_smoke_fixture_rows(tmp_path):
    """M13 fix: rows tagged source=smoke_composed.jsonl (the pre-wiring
    smoke fixture) are excluded from stats even if present in the orders
    file, and the honest skip count is reported."""
    orders = tmp_path / "dryrun_orders.jsonl"
    _write_jsonl(orders, [
        {"idempotency_key": "smoke1", "source": "smoke_composed.jsonl",
         "ticker": "KXDRY-A", "filled_qty": 5, "avg_fill_price_cents": 45.0},
        {"idempotency_key": "real1", "source": "bestbets_composed.jsonl",
         "ticker": "KXDRY-A", "filled_qty": 0, "avg_fill_price_cents": 0.0},
    ])
    rep = reconcile.run_reconcile(orders, tmp_path / "no_depth_dir")
    assert rep["n_dryrun_rows"] == 1 and rep["n_stale_smoke_skipped"] == 1
    assert rep["n_fills"] == 0  # the surviving row is unfilled


def test_reconcile_later_snapshot_ignores_earlier_and_windows_out():
    t0 = NOW.timestamp()
    early = {"ts": (NOW - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    far = {"ts": (NOW + timedelta(seconds=9999)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    near = {"ts": (NOW + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert reconcile.later_snapshot([early, far], t0) is None
    assert reconcile.later_snapshot([early, near, far], t0) is near
