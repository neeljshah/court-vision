"""scripts.platformkit.econ.historical_backtest_scoreboard -- surface the existing
leak-free RETROSPECTIVE backtest verdicts (already-built machinery, this module adds
NO new modeling) as one clean, clearly-labeled artifact separate from the LIVE paper
ledger the 8.1 edge_greenlight evaluator scores.

WHY THIS EXISTS: on 2026-07-02 the user asked whether the system can use OLD
historical odds/lines data to help prove an edge faster. It largely already can --
scripts.platformkit.market_coverage.edge_finder.hunt() already replays the model
leak-free, walk-forward, against ~15 months of captured MLB closes (2,326 states)
and a domestic-soccer corpus (2,497 states) -- but that result was buried inside a
~40-market internal enumeration dominated by NBA offseason NEEDS_FORWARD_CLV noise,
with no standalone report a human could read in one glance. This module filters
hunt()'s output down to the markets that actually HAVE a real historical-close
verdict, and separately probes the World Cup corpus (which is NOT yet wired into
edge_finder.enumerate_markets()) via oddsapi_close_corpus directly.

HONESTY RAIL (the reason this is a SEPARATE module, never merged into
edge_greenlight.py): a backtest replay is RETROSPECTIVE evidence about the MODEL's
calibration. It is not, and can never become, a substitute for the 8.1(a) LIVE
"n>=300 settled paper bets" criterion -- that criterion exists specifically to
require PROSPECTIVE (real-time decision) proof, which a replay against already-known
history cannot provide (researcher-degrees-of-freedom risk: the model's design may
have been implicitly informed by having seen this window's outcomes, even though the
walk-forward mechanics are leak-free at the row level). Every row of output here
carries is_retrospective=True so a caller can never accidentally count it toward a
live criterion.

Run:  python -m scripts.platformkit.econ.historical_backtest_scoreboard
Per-file test: scripts/platformkit/econ/test_historical_backtest_scoreboard.py
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[3]
_OUT_PATH = _REPO / "data" / "frontend" / "ops" / "historical_backtest_scoreboard.json"

MIN_N_FOR_VERDICT = 200  # mirrors edge_finder.MIN_N -- the same leak-free-DM floor

HONEST_NOTE = (
    "RETROSPECTIVE backtest of the model against ALREADY-CAPTURED historical closes "
    "(leak-free walk-forward). This is calibration evidence about the MODEL, not a "
    "count of live paper bets -- it does NOT and cannot contribute toward the 8.1(a) "
    "n>=300 live-settled-bets criterion. No $ edge claimed; MATCH is the expected, "
    "honest result under market efficiency."
)


def _from_edge_finder() -> List[Dict[str, Any]]:
    """Pull the markets that actually ran against a real historical corpus (n>0,
    not the NEEDS_FORWARD_CLV/no-data rows that dominate hunt()'s NBA-heavy output)."""
    try:
        from scripts.platformkit.market_coverage import edge_finder as ef  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [{"name": "edge_finder", "status": "error",
                "reason": "import failed (%s: %s)" % (type(exc).__name__, exc)}]
    try:
        results = ef.hunt()
    except Exception as exc:  # noqa: BLE001
        return [{"name": "edge_finder", "status": "error",
                "reason": "hunt() failed (%s: %s)" % (type(exc).__name__, exc)}]
    out: List[Dict[str, Any]] = []
    for r in results:
        if r.n <= 0 or r.verdict == "NEEDS_FORWARD_CLV":
            continue  # no real historical close behind this row -- not a backtest
        d = r.as_dict() if hasattr(r, "as_dict") else dict(r.__dict__)
        d.pop("meta", None)
        d["is_retrospective"] = True
        out.append(d)
    return out


def _soccer_intl_probe() -> Optional[Dict[str, Any]]:
    """World Cup is NOT wired into edge_finder.enumerate_markets() yet -- probe its
    corpus directly so its (thin) coverage is visible rather than silently absent."""
    try:
        from scripts.platformkit.odds_provider import oddsapi_close_corpus as occ  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return {"name": "soccer_intl_moneyline", "status": "error",
                "reason": "import failed (%s: %s)" % (type(exc).__name__, exc),
                "is_retrospective": True}
    try:
        states = occ.build_states("soccer_intl")
    except Exception as exc:  # noqa: BLE001
        return {"name": "soccer_intl_moneyline", "status": "error",
                "reason": "build_states failed (%s: %s)" % (type(exc).__name__, exc),
                "is_retrospective": True}
    n = len(states) if states else 0
    if n < MIN_N_FOR_VERDICT:
        return {
            "name": "soccer_intl_moneyline", "sport": "soccer_intl",
            "verdict": "INSUFFICIENT_DATA", "n": n,
            "reason": ("only %d leak-free states with a joinable outcome+close (need >= %d "
                      "for a trustworthy DM test) -- most of the 2,187 raw captured WC odds "
                      "rows are either not-yet-decided or 2-way-excluded draws; not wired "
                      "into edge_finder.enumerate_markets() (n too thin to be worth a full "
                      "gate wiring yet -- revisit once more WC games decide)." % (n, MIN_N_FOR_VERDICT)),
            "is_retrospective": True,
        }
    # Enough states exist now to be worth a real gate -- caller should wire this
    # sport into edge_finder.enumerate_markets() properly rather than hand-rolling
    # a second gate implementation here.
    return {
        "name": "soccer_intl_moneyline", "sport": "soccer_intl",
        "verdict": "READY_TO_WIRE", "n": n,
        "reason": ("%d states now available (>= the %d floor) -- wire a MarketSpec into "
                  "edge_finder.enumerate_markets() to get a real gated verdict instead of "
                  "this placeholder." % (n, MIN_N_FOR_VERDICT)),
        "is_retrospective": True,
    }


def build() -> Dict[str, Any]:
    """Assemble the full historical-backtest scoreboard. Never raises."""
    rows = _from_edge_finder()
    soccer_row = _soccer_intl_probe()
    if soccer_row is not None:
        rows.append(soccer_row)
    return {
        "component": "m_historical_backtest_scoreboard",
        "generated_at": time.time(),
        "rows": rows,
        "n_rows": len(rows),
        "honest_note": HONEST_NOTE,
        "counts_toward_live_criteria": False,
    }


def write_status(doc: Optional[Dict[str, Any]] = None, *,
                  out_path: Optional[Path] = None) -> bool:
    """Atomically write build()'s output (tmp + os.replace). Never raises."""
    try:
        doc = doc if doc is not None else build()
        path = Path(out_path) if out_path is not None else _OUT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True,
                                  default=float), encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001 -- a write failure must never crash the caller
        return False


def render(doc: Dict[str, Any]) -> str:
    lines = ["=" * 78,
             "HISTORICAL BACKTEST SCOREBOARD -- retrospective, does NOT count toward",
             "the live 8.1(a) n>=300 criterion (see honest_note)",
             "=" * 78]
    for r in doc.get("rows", []):
        name = r.get("name", "?")
        verdict = r.get("verdict") or r.get("status", "?")
        n = r.get("n", 0)
        bss = r.get("bss")
        extra = (" bss=%+.4f dm_p=%s" % (bss, r.get("dm_p"))) if bss is not None else ""
        lines.append("  %-22s %-18s n=%-6d%s" % (name, verdict, n, extra))
        if r.get("reason"):
            lines.append("      %s" % r["reason"])
    lines.append("-" * 78)
    lines.append(doc.get("honest_note", ""))
    lines.append("=" * 78)
    return "\n".join(lines)


def main() -> int:
    doc = build()
    print(render(doc))
    write_status(doc)
    print("\nwrote %s" % _OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build", "write_status", "render", "HONEST_NOTE", "MIN_N_FOR_VERDICT"]
