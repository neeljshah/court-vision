"""scripts.platformkit.paper.pnl_series -- model-view UNITS P&L equity curve (builders).

"How much I would have made" as an HONEST PAPER curve in UNITS (never $). Reads the
GRADED settled rows across the CLV ledger (data/frontend/clv_ledger.jsonl) and the
graded-predictions ledger (paper_predictions_graded.jsonl), orders them by settle
time, accumulates each ``unit_result`` onto the starting bankroll.

RETIRED AS A CANONICAL WRITER: the supervised bankroll_daemon is now the SINGLE
writer of data/frontend/paper_pnl_series.json (it emits BOTH per_day[] AND daily[]
reconciled to the PLACED bets). This module keeps its builders (collect_settled /
build_series) for reuse, but build_and_write only emits a NON-canonical shadow file
(paper_pnl_series_modelview.json) and HARD-REFUSES to clobber the canonical path --
the dual-writer schema split (per_day[] vs daily[]) can never recur.

HONESTY (binding):
  * UNITS ONLY -- BANNED_KEYS never read into the curve; no $ / pnl / roi field out.
  * edge_claimed=False. Real money stays default-DENY.
  * CLV is the honest yardstick: if every settled row has no captured close
    (clv_status all 'no_close'), mean CLV is reported as "INSUFFICIENT_DATA",
    NEVER a fabricated number.
  * Nothing is fabricated: only rows with a real unit_result move the curve.

Schema (paper_pnl_series.json):
  {start_units, points:[{ts, day, balance_units, daily_units, cumulative_units,
                         n_bets, n_win, n_loss}],
   summary:{total_units, n_bets, n_win, n_loss, n_push, win_rate,
            mean_clv_pct_or_INSUFFICIENT, current_units},
   honest_note, edge_claimed:false}

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/paper/test_pnl_series.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.paper import bankroll as _bank
from scripts.platformkit.paper import et_day as _et
from scripts.platformkit.paper import paper_today as _today
from scripts.platformkit.paper import pnl_normalize as _nz
from scripts.platformkit.paper.grade_predictions import DEFAULT_GRADED

_HERE = Path(__file__).resolve().parent
_FRONTEND = _HERE.parents[2] / "data" / "frontend"
# RETIRED as a writer of the CANONICAL file: the supervised bankroll_daemon is now
# the SINGLE writer of data/frontend/paper_pnl_series.json (it emits BOTH per_day[]
# AND daily[] reconciled to the PLACED bets). This module's builders are kept for
# reuse, but build_and_write only emits to a NON-canonical shadow file so the two
# writers can never split the schema again. CANONICAL_OUTPUT names the file this
# module must NOT clobber; DEFAULT_OUTPUT is the harmless shadow it writes instead.
CANONICAL_OUTPUT = _FRONTEND / "paper_pnl_series.json"
DEFAULT_OUTPUT = _FRONTEND / "paper_pnl_series_modelview.json"

_HONEST_NOTE = (
    "Paper units P&L (never $). Cumulative_units is 'how much I would have made' as "
    "a paper track record, not realized profit; executed=False on every bet and no "
    "edge is claimed. One position per market (the model's highest-prob pick) -- "
    "contradictory both-sides model views are NOT both staked. ALL bets are "
    "normalised to a flat 1-unit stake (legacy dollar-Kelly stakes are not used), at "
    "the model's FAIR price, so this curve carries no book vig and is a calibration "
    "proxy, not a realizable edge. CLV (better-than-close) is the honest yardstick -- "
    "INSUFFICIENT_DATA here means no closing line was captured, not a result."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settle_ts(row: Dict[str, Any]) -> str:
    """Best available settle timestamp for ordering. Falls back to ts / logged_at."""
    for k in ("settled_at", "ts", "logged_at"):
        v = row.get(k)
        if v:
            return str(v)
    return ""


def _day(ts: str) -> str:
    """ET calendar day of a settle timestamp (the slate is ET, not UTC)."""
    return _et.et_day_of(ts) if ts else "unknown"


def collect_settled(
    clv_path: Optional[Path] = None, graded_pred_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """All settled rows with a numeric unit_result, from both ledgers, time-ordered.

    Uses clv_ledger.load_ledger (which already drops synthetic/test rows) for the CLV
    ledger (real placed paper bets). The CLV ledger is NOT already one-sided: a
    symmetric two-way market (home ML AND away ML) records BOTH sides whenever both
    clear the EV floor, so it is collapsed to ONE position per market via
    pnl_normalize.select_clv_positions (the model-backed side) before it reaches the
    curve. Graded-prediction rows are deduped to ONE model position per (event, group,
    line) via select_model_positions so contradictory both-sides model views do not both
    flat-stake. Rows with unit_result None (void/undecided) are excluded -- no movement.
    """
    cpath = Path(clv_path) if clv_path else _clv.DEFAULT_LEDGER
    gpath = Path(graded_pred_path) if graded_pred_path else DEFAULT_GRADED

    def _keep(r: Dict[str, Any]) -> bool:
        if r.get("status") != "settled":
            return False
        ur = r.get("unit_result")
        if ur is None:
            return False
        try:
            float(ur)
        except (TypeError, ValueError):
            return False
        return True

    clv_rows = [r for r in _clv.load_ledger(cpath) if _keep(r)]
    clv_rows = _nz.select_clv_positions(clv_rows)
    pred_rows = [r for r in _nz.load_jsonl(gpath) if _keep(r)]
    pred_rows = _nz.select_model_positions(pred_rows)
    settled = clv_rows + pred_rows
    # Normalise EVERY row to a flat 1-unit stake so the equity curve is a clean,
    # comparable unit track record (removes legacy dollar-Kelly stake contamination
    # from the CLV ledger without mutating it or changing any win/loss).
    out = _nz.normalize_flat(settled)
    out.sort(key=_settle_ts)
    return out


def _mean_clv(settled: Sequence[Dict[str, Any]]) -> Any:
    """Mean clv_pct over true-close rows, but INSUFFICIENT below the small-N floor.

    A few true closes beside a large n_bets is small-N noise painted as a result, so
    report INSUFFICIENT_DATA until at least MIN_CLV_N true closes; n_clv is surfaced in
    the summary so the sample size is visible.
    """
    vals = [float(r["clv_pct"]) for r in settled
            if r.get("clv_pct") is not None and not bool(r.get("clv_is_proxy", False))]
    if len(vals) < _today.MIN_CLV_N:
        return "INSUFFICIENT_DATA"
    return round(sum(vals) / len(vals), 6)


def build_series(
    settled: Sequence[Dict[str, Any]], *, start_units: float,
) -> Dict[str, Any]:
    """Build the {start_units, points, summary, ...} payload from settled rows.

    Points are per-bet equity-curve samples (balance after each settled bet) carrying
    the running cumulative units and the per-DAY P&L bucket they belong to.
    """
    balance = float(start_units)
    cumulative = 0.0
    n_win = n_loss = n_push = 0
    day_totals: Dict[str, float] = {}
    points: List[Dict[str, Any]] = []
    for i, r in enumerate(settled, start=1):
        ur = float(r["unit_result"])
        outcome = str(r.get("outcome") or "")
        if outcome == "win":
            n_win += 1
        elif outcome == "loss":
            n_loss += 1
        elif outcome == "push":
            n_push += 1
        balance += ur
        cumulative += ur
        ts = _settle_ts(r)
        day = _day(ts)
        day_totals[day] = round(day_totals.get(day, 0.0) + ur, 6)
        points.append({
            "ts": ts, "day": day,
            "balance_units": round(balance, 6),
            "daily_units": day_totals[day],
            "cumulative_units": round(cumulative, 6),
            "n_bets": i, "n_win": n_win, "n_loss": n_loss,
        })
    n = len(settled)
    decided = n_win + n_loss
    win_rate = round(n_win / decided, 6) if decided else None
    daily = [{"day": d, "daily_units": day_totals[d]}
             for d in sorted(day_totals)]
    n_clv = sum(1 for r in settled if r.get("clv_pct") is not None
                and not bool(r.get("clv_is_proxy", False)))
    summary = {
        "total_units": round(cumulative, 6),
        "n_bets": n, "n_win": n_win, "n_loss": n_loss, "n_push": n_push,
        "win_rate": win_rate,
        "mean_clv_pct_or_INSUFFICIENT": _mean_clv(settled),
        "n_clv": n_clv,
        "min_clv_n": _today.MIN_CLV_N,
        "current_units": round(start_units + cumulative, 6),
    }
    return {
        "start_units": float(start_units),
        "points": points,
        "daily": daily,
        "summary": summary,
        "honest_note": _HONEST_NOTE,
        "edge_claimed": False,
        "executed": False,
        "generated_at": _now_iso(),
    }


def build_and_write(
    *,
    clv_path: Optional[Path] = None,
    graded_pred_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    bankroll_path: Optional[Path] = None,
    update_bankroll: bool = True,
) -> Dict[str, Any]:
    """Collect settled rows, build the series, write the JSON, sync the bankroll.

    Returns the written payload. When *update_bankroll* is True the bankroll JSON's
    current_units is recomputed from the same settled set (single source of truth).
    """
    out = Path(output_path) if output_path else DEFAULT_OUTPUT
    if out.resolve() == CANONICAL_OUTPUT.resolve():
        # The bankroll_daemon is the SINGLE writer of the canonical file; refuse to
        # clobber it (a second schema here is what split per_day[] vs daily[]).
        raise ValueError(
            "pnl_series is RETIRED as a writer of the canonical paper_pnl_series.json "
            "(the supervised bankroll_daemon is the single writer); write a shadow "
            "path or use its builders directly.")
    settled = collect_settled(clv_path, graded_pred_path)
    start_units = float(_bank.read_config(bankroll_path)["start_units"])
    payload = build_series(settled, start_units=start_units)
    if update_bankroll:
        _bank.apply_settled(settled, start_units=start_units, path=bankroll_path,
                            persist=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(out)
    return payload


def _main(argv: Optional[List[str]] = None) -> int:
    payload = build_and_write()
    s = payload["summary"]
    print("PAPER P&L (units, executed=False, edge_claimed=False):")
    print("  start_units=%s current_units=%s total_units=%s"
          % (payload["start_units"], s["current_units"], s["total_units"]))
    print("  n_bets=%s win=%s loss=%s push=%s win_rate=%s mean_clv=%s"
          % (s["n_bets"], s["n_win"], s["n_loss"], s["n_push"],
             s["win_rate"], s["mean_clv_pct_or_INSUFFICIENT"]))
    print("  wrote %s" % DEFAULT_OUTPUT)
    return 0


__all__ = ["collect_settled", "build_series", "build_and_write",
           "DEFAULT_OUTPUT", "CANONICAL_OUTPUT"]


if __name__ == "__main__":
    raise SystemExit(_main())
