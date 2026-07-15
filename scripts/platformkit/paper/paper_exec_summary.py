"""scripts.platformkit.paper.paper_exec_summary -- execution-quality digest block.

Sibling to paper_today.py (kept separate so paper_today.py stays under the
300 LOC rail). Builds the digest's "execution" block: per-market_type rolling
CLV + circuit-breaker state, plus execution-quality aggregates (expected CLV
at placement, placement latency, gated/ungated counts) over ledger rows.

Degrades HONESTLY: scripts.platformkit.execution.circuit_breaker is owned by a
concurrent lane. If it is not yet importable, every market's state is
"UNKNOWN" with null CLV fields rather than raising or fabricating a number.
Rows without exec_gate/placement_latency_ms (pre-existing ledger rows) simply
do not contribute to the quality aggregates -- never zero-filled.

PAPER / UNITS only. No $ figure anywhere.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

try:
    from scripts.platformkit.execution import circuit_breaker as _breaker
except ImportError:  # concurrent lane not landed on disk yet -- degrade honestly
    _breaker = None  # type: ignore[assignment]


def _market_type_of(row: Dict[str, Any]) -> str:
    mt = row.get("market_type") or row.get("market")
    return str(mt) if mt else "unknown"


def _market_types(rows: Sequence[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for r in rows:
        mt = _market_type_of(r)
        if mt not in seen:
            seen.append(mt)
    return seen


def _per_market_clv(rows: List[Dict[str, Any]], now_iso: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for mt in _market_types(rows):
        if _breaker is None:
            out[mt] = {"mean_clv_pct": None, "n": 0, "n_proxy": 0,
                       "state": "UNKNOWN", "cap_per_day": None, "placed_today": None}
            continue
        roll = _breaker.rolling_clv(rows, mt, now_iso)
        st = _breaker.state(rows, mt, now_iso)
        allow = _breaker.allow_placement(rows, mt, now_iso)
        out[mt] = {**roll, "state": st["state"], "cap_per_day": st["cap_per_day"],
                   "placed_today": allow["placed_today"]}
    return out


def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else round((s[mid - 1] + s[mid]) / 2, 3)


def _exec_quality(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregates over rows carrying exec_gate / placement_latency_ms.

    Older ledger rows lack these fields (they predate the gate); they simply
    don't contribute here -- counts/medians never fabricate a value for them.
    """
    gated = [r for r in rows if isinstance(r.get("exec_gate"), dict)]
    expected = [float(r["exec_gate"]["expected_clv_pct"]) for r in gated
                if r["exec_gate"].get("expected_clv_pct") is not None]
    latencies = [float(r["placement_latency_ms"]) for r in rows
                 if r.get("placement_latency_ms") is not None]
    return {
        "n_gated": len(gated),
        "n_ungated": len(rows) - len(gated),
        "avg_expected_clv_pct": round(sum(expected) / len(expected), 6) if expected else None,
        "median_placement_latency_ms": _median(latencies),
    }


def build_execution_block(rows: List[Dict[str, Any]], now_iso: str) -> Dict[str, Any]:
    """The digest 'execution' block: per-market rolling CLV + breaker + exec quality."""
    return {
        "by_market_type": _per_market_clv(rows, now_iso),
        "quality": _exec_quality(rows),
        "breaker_module_loaded": _breaker is not None,
    }


def _demo() -> None:
    """Smallest runnable self-check (assert-based); not a test framework."""
    now = "2026-07-15T12:00:00Z"
    rows = [
        {"market_type": "prop", "ts": "2026-07-10T00:00:00Z", "clv_pct": 2.0,
         "exec_gate": {"expected_clv_pct": 1.5}, "placement_latency_ms": 200},
        {"market_type": "prop", "ts": "2026-07-11T00:00:00Z", "clv_pct": -1.0},
        {"market_type": "moneyline", "ts": "2026-07-12T00:00:00Z"},  # not yet graded
    ]
    block = build_execution_block(rows, now)
    assert "prop" in block["by_market_type"] and "moneyline" in block["by_market_type"]
    q = block["quality"]
    assert q["n_gated"] == 1 and q["n_ungated"] == 2
    assert q["avg_expected_clv_pct"] == 1.5
    assert q["median_placement_latency_ms"] == 200
    print("paper_exec_summary self-check OK")


if __name__ == "__main__":
    _demo()


__all__ = ["build_execution_block"]
