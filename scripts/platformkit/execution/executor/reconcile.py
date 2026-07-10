"""scripts.platformkit.execution.executor.reconcile -- honest slippage check:
dry-run simulated fills (data/frontend/ops/dryrun_orders.jsonl) vs what the
CAPTURED tape later shows was achievable. Reuses the fill_model discipline:
book_replay's load_jsonl/_epoch/half_spread parsing and fill_realism's
marketability verdict (plausible = the claimed fill sat inside the later
displayed book; optimistic = it claims a better price than the book showed).

MEASUREMENT ONLY: price/probability units, no $/ROI/edge claim; a
NOT_TESTABLE verdict (no later snapshot inside the window) is reported
honestly, never faked. Landmine honored: this is within-venue only (Kalshi
dry-run vs Kalshi tape) -- cross-venue comparisons are basis, not edge.

INVARIANTS: <=300 LOC; ASCII; stdlib only; never writes data/registry/;
never flips a flag.
Test: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/executor/test_dryrun_reconcile.py -q
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.execution.book_replay import _epoch, half_spread, load_jsonl
from scripts.platformkit.execution.fill_model.fill_realism import marketability

_REPO = Path(__file__).resolve().parents[4]
DEFAULT_ORDERS = _REPO / "data" / "frontend" / "ops" / "dryrun_orders.jsonl"
DEFAULT_OUT = _REPO / "data" / "frontend" / "ops" / "dryrun_reconcile.json"
BOOK_DEPTH_DIR = _REPO / "data" / "cache" / "book_depth" / "kalshi"
LATER_WINDOW_S = 900.0  # a confirming later snapshot must land within 15min


def load_depth_by_ticker(depth_dir: Path = BOOK_DEPTH_DIR) -> Dict[str, List[Dict[str, Any]]]:
    """{ticker: rows sorted ASC by ts} across every captured day."""
    by_ticker: Dict[str, List[Dict[str, Any]]] = {}
    for p in sorted(glob.glob(str(depth_dir / "*.jsonl"))):
        for r in load_jsonl(Path(p)):
            if r.get("ticker") and r.get("ts"):
                by_ticker.setdefault(r["ticker"], []).append(r)
    for tk in by_ticker:
        by_ticker[tk].sort(key=lambda r: str(r["ts"]))
    return by_ticker


def later_snapshot(snaps: List[Dict[str, Any]], t0: float,
                   window_s: float = LATER_WINDOW_S) -> Optional[Dict[str, Any]]:
    """FIRST snapshot at/after t0 within window_s (what the tape showed
    next), else None. snaps sorted ASC by ts."""
    for r in snaps:
        t = _epoch(r.get("ts"))
        if t is None or t < t0:
            continue
        return r if t - t0 <= window_s else None
    return None


def reconcile_row(row: Dict[str, Any], depth_by_ticker: Dict[str, List[Dict[str, Any]]],
                  window_s: float = LATER_WINDOW_S) -> Dict[str, Any]:
    """One dry-run fill vs the later tape: marketability verdict + drift."""
    out: Dict[str, Any] = {"idempotency_key": row.get("idempotency_key"),
                           "ticker": row.get("ticker"), "verdict": "NOT_TESTABLE"}
    try:
        fill_prob = float(row["avg_fill_price_cents"]) / 100.0
    except (KeyError, TypeError, ValueError):
        return out
    if not row.get("filled_qty") or not 0.0 < fill_prob < 1.0:
        return out
    t0 = _epoch(row.get("asof_ts"))
    snaps = depth_by_ticker.get(row.get("ticker"), [])
    snap = later_snapshot(snaps, t0, window_s) if t0 is not None else None
    if snap is None:
        return out
    verdict = marketability({"implied_prob": fill_prob}, snap)
    out["verdict"] = verdict if verdict is not None else "NOT_TESTABLE"
    hs = half_spread(snap.get("best_bid"), snap.get("best_ask"))
    if hs is not None:
        mid = (float(snap["best_bid"]) + float(snap["best_ask"])) / 2.0
        out["post_fill_drift_price_units"] = round(mid - fill_prob, 4)
    out["later_book_ts"] = snap.get("ts")
    return out


def _stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0}
    vs = sorted(values)
    return {"n": len(vs), "median": round(statistics.median(vs), 5),
            "p25": round(vs[len(vs) // 4], 5), "p75": round(vs[(3 * len(vs)) // 4], 5)}


def run_reconcile(orders_path: Path = DEFAULT_ORDERS,
                  depth_dir: Path = BOOK_DEPTH_DIR,
                  window_s: float = LATER_WINDOW_S) -> Dict[str, Any]:
    rows = load_jsonl(orders_path)
    depth = load_depth_by_ticker(depth_dir)
    fills = [r for r in rows if r.get("filled_qty")]
    results = [reconcile_row(r, depth, window_s) for r in fills]
    n_tested = sum(1 for r in results if r["verdict"] in ("plausible", "optimistic"))
    n_plaus = sum(1 for r in results if r["verdict"] == "plausible")
    drift = [r["post_fill_drift_price_units"] for r in results
             if "post_fill_drift_price_units" in r]
    sim_slip = [float(r["slippage_cents"]) / 100.0 for r in fills
                if r.get("slippage_cents") is not None]
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "edge_claimed": False,
        "orders_path": str(orders_path),
        "n_dryrun_rows": len(rows),
        "n_fills": len(fills),
        "vs_later_tape": {
            "verdict": "measured" if n_tested else
                       "NOT_TESTABLE -- no later snapshot within window for any fill",
            "n_tested": n_tested,
            "pct_plausible": round(100.0 * n_plaus / n_tested, 2) if n_tested else None,
            "pct_optimistic": round(100.0 * (n_tested - n_plaus) / n_tested, 2) if n_tested else None,
            "post_fill_drift_price_units": _stats(drift),
        },
        "sim_fill_vs_limit_price_units": _stats(sim_slip),
        "honesty_notes": [
            "Within-venue (Kalshi dry-run vs Kalshi tape) only -- cross-venue "
            "comparisons are basis, not edge.",
            "plausible/optimistic reuses fill_model.fill_realism.marketability "
            "against the FIRST later captured snapshot; queue position unknown, "
            "so 'plausible' is necessary, not sufficient, for a real fill.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Dry-run fills vs later captured tape (slippage honesty "
                    "report; price units only, no $/edge claim)")
    ap.add_argument("--orders", default=str(DEFAULT_ORDERS))
    ap.add_argument("--depth-dir", default=str(BOOK_DEPTH_DIR))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--window", type=float, default=LATER_WINDOW_S)
    args = ap.parse_args()
    report = run_reconcile(Path(args.orders), Path(args.depth_dir), args.window)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


__all__ = ["load_depth_by_ticker", "later_snapshot", "reconcile_row",
           "run_reconcile", "LATER_WINDOW_S"]

if __name__ == "__main__":
    raise SystemExit(main())
