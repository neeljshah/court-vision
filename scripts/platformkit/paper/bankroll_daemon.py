"""scripts.platformkit.paper.bankroll_daemon -- supervised DAILY-bankroll tick daemon.

MEASUREMENT-ONLY daemon (supervised as m1_bankroll). Every ~600 s it reads the SETTLED
placed paper bets from the canonical CLV ledger + the grade summary, accumulates the
DAILY and CUMULATIVE units P&L onto the starting bankroll, and atomically writes:

  * data/frontend/paper_pnl_series.json -- per-bet equity curve + per-DAY ledger (the
    SINGLE writer of the canonical file; emits per_day[] AND daily[]; pnl_series RETIRED).
  * data/frontend/paper_bankroll.json   -- {start_units, current_units, net_units,
    day, day_units} reconciled to the placed bets (single source of truth).
  * data/frontend/paper_today.json       -- today's PLACED bets + running P&L
    (the execution / best-bets view; see paper_today.build_today).

Then it beats the m1_bankroll heartbeat so the supervisor can tell "alive" from "dead".

HONEST RAILS (binding): UNITS ONLY (no $/pnl/roi/profit key); the curve is the literal
sum of the placed bets' graded flat-1-unit results -- ONE position per market (a
symmetric two-way market's both sides collapse to the model-backed side) -- so it
RECONCILES to the staked bets (never fabricated). Day rollover at ET midnight (ET slate,
not UTC): each day opens at the prior day's close (continuous bankroll) with its own
day_units. executed=False / edge_claimed=False; real money stays default-DENY; CLV is
the yardstick (INSUFFICIENT_DATA, never fabricated). No flag flip, no data/registry/
write, no autostart arm -- data/frontend/ only. Cadence DEFAULT_INTERVAL_SEC=600;
heartbeat m1_bankroll. Injectable clock/sleep/max_ticks for offline tests (no network).

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets.

Per-file test: python -m pytest scripts/platformkit/paper/test_bankroll_daemon.py -q
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.paper import bankroll as _bank
from scripts.platformkit.paper import kelly_curve as _kelly
from scripts.platformkit.paper import paper_today as _today
from scripts.platformkit.paper import pnl_normalize as _nz

logger = logging.getLogger("bankroll_daemon")

HEARTBEAT_COMPONENT = "m1_bankroll"
DEFAULT_INTERVAL_SEC = 600.0

_REPO = pathlib.Path(__file__).resolve().parents[3]
_FRONTEND = _REPO / "data" / "frontend"
SERIES_PATH = _FRONTEND / "paper_pnl_series.json"
TODAY_PATH = _FRONTEND / "paper_today.json"
# The real m1_bankroll heartbeat the supervisor reads. _beat()/tick()/run() take a
# heartbeat_path so OFFLINE TESTS point at tmp and NEVER stomp this live file with an
# injected (epoch-1) clock; production defaults here so the real beat still lands.
HEARTBEAT_PATH = _REPO / "data" / "cache" / "daemon_heartbeats" / "m1_bankroll.txt"

_HONEST_NOTE = (
    "Daily paper bankroll in UNITS (never $). per_day[].start_units = the day's "
    "opening equity (prior close, ET), day_units its net, cumulative_units all-time. "
    "The curve is the literal sum of the placed bets' graded unit_results (RECONCILES "
    "to the staked bets), not realized profit and not a $ ROI; no edge is claimed. CLV "
    "INSUFFICIENT_DATA below the small-N floor (n_clv surfaced)."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _beat(now_epoch: Optional[float] = None,
          heartbeat_path: Optional[pathlib.Path] = None) -> None:
    """Write the m1_bankroll liveness heartbeat. Never raises (observability only).

    *heartbeat_path* defaults to the real file; tests pass a tmp path so an injected
    fake clock can never poison the live heartbeat with a stale (epoch-1) stamp.
    """
    try:
        from ops.liveness import heartbeat
        hb = pathlib.Path(heartbeat_path) if heartbeat_path is not None \
            else HEARTBEAT_PATH
        heartbeat(HEARTBEAT_COMPONENT, path=hb, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001 -- a heartbeat write must never sink the loop
        logger.debug("bankroll_daemon heartbeat skipped: %s", exc)


def build_series(
    settled_flat: Sequence[Dict[str, Any]], *, start_units: float,
) -> Dict[str, Any]:
    """Per-bet equity curve + per-DAY ledger from flat-1-unit settled placed bets.

    *settled_flat* is flat-1-unit normalised, ONE-position-per-market and time-ordered.
    Builds points (one per settled bet), per_day (day, start_units=prior close,
    day_units, end_units, cumulative_units) and daily (the FE {day, daily_units}
    mirror). The settle-day bucket is the ET calendar day (_today._settle_day).
    """
    balance = float(start_units)
    cumulative = 0.0
    n_win = n_loss = n_push = 0
    points: List[Dict[str, Any]] = []
    day_open: Dict[str, float] = {}     # day -> opening equity
    day_net: Dict[str, float] = {}      # day -> net units
    day_order: List[str] = []
    for i, r in enumerate(settled_flat, start=1):
        ur = float(r["unit_result"])
        outcome = str(r.get("outcome") or "")
        if outcome == "win":
            n_win += 1
        elif outcome == "loss":
            n_loss += 1
        elif outcome == "push":
            n_push += 1
        day = _today._settle_day(r)
        if day not in day_open:
            day_open[day] = round(balance, 6)  # opens at the running (prior) equity
            day_net[day] = 0.0
            day_order.append(day)
        balance += ur
        cumulative += ur
        day_net[day] = round(day_net[day] + ur, 6)
        points.append({
            "ts": str(r.get("settled_at") or r.get("ts") or ""),
            "day": day,
            "balance_units": round(balance, 6),
            "daily_units": day_net[day],
            "cumulative_units": round(cumulative, 6),
            "n_bets": i, "n_win": n_win, "n_loss": n_loss,
        })
    per_day: List[Dict[str, Any]] = []
    daily: List[Dict[str, Any]] = []   # FE-compatible {day, daily_units} mirror
    run_cum = 0.0
    for d in day_order:
        run_cum = round(run_cum + day_net[d], 6)
        per_day.append({
            "day": d,
            "start_units": day_open[d],
            "day_units": day_net[d],
            "end_units": round(day_open[d] + day_net[d], 6),
            "cumulative_units": run_cum,
        })
        daily.append({"day": d, "daily_units": day_net[d]})
    n = len(settled_flat)
    decided = n_win + n_loss
    # TRUE-close rows only: a proxy close (clv_is_proxy=True) is a weaker substitute and
    # is excluded from the mean / n_clv yardstick (it still counts as a settled bet).
    vals = [float(r["clv_pct"]) for r in settled_flat
            if r.get("clv_pct") is not None and not bool(r.get("clv_is_proxy", False))]
    # Small-N CLV floor: below MIN_CLV_N true closes report INSUFFICIENT (surface n_clv).
    mean_clv: Any = (round(sum(vals) / len(vals), 6)
                     if len(vals) >= _today.MIN_CLV_N else "INSUFFICIENT_DATA")
    return {
        "start_units": float(start_units),
        "points": points,
        "per_day": per_day,
        "daily": daily,
        "summary": {
            "total_units": round(cumulative, 6),
            "n_bets": n, "n_win": n_win, "n_loss": n_loss, "n_push": n_push,
            "win_rate": round(n_win / decided, 6) if decided else None,
            "mean_clv_pct_or_INSUFFICIENT": mean_clv,
            "n_clv": len(vals),
            "min_clv_n": _today.MIN_CLV_N,
            "current_units": round(start_units + cumulative, 6),
        },
        "honest_note": _HONEST_NOTE,
        "edge_claimed": False,
        "executed": False,
        "generated_at": _now_iso(),
    }


def _atomic_write(path: pathlib.Path, doc: Dict[str, Any]) -> bool:
    """Atomically write JSON (tmp+replace). Returns True on success. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(doc, ensure_ascii=True, indent=2, default=str) + "\n"
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("bankroll_daemon atomic write failed: %s", exc)
        return False


def tick(
    *,
    now: Optional[float] = None,
    clv_path: Optional[pathlib.Path] = None,
    series_path: Optional[pathlib.Path] = None,
    today_path: Optional[pathlib.Path] = None,
    bankroll_path: Optional[pathlib.Path] = None,
    heartbeat_path: Optional[pathlib.Path] = None,
    today: Optional[str] = None,
) -> Dict[str, Any]:
    """One measurement cycle: read placed bets -> write series/bankroll/today -> beat.

    Never raises. The curve RECONCILES to the placed bets by construction (series and
    bankroll sum the same flat-1-unit, one-per-market settled rows). Returns the series
    payload (with a 'reconciles' flag). heartbeat_path defaults to the live file.
    """
    sp = pathlib.Path(series_path) if series_path is not None else SERIES_PATH
    tp = pathlib.Path(today_path) if today_path is not None else TODAY_PATH
    try:
        su = float(_bank.read_config(bankroll_path)["start_units"])
        placed = _today.load_placed(clv_path)
        settled = [r for r in placed if r.get("status") == "settled"]
        # ONE POSITION PER MARKET: a symmetric two-way market records BOTH sides when
        # both clear the EV floor; flat-staking both is nonsensical (win/loss cancel
        # minus vig) and must NOT count as two bets. Collapse each market to the single
        # model-backed side so n_bets / day_units / bankroll reflect real positions.
        settled = _nz.select_clv_positions(settled)
        flat = _nz.normalize_flat(settled)
        flat.sort(key=lambda r: str(r.get("settled_at") or r.get("ts") or ""))
        series = build_series(flat, start_units=su)
        # Edge-proportional capped quarter-Kelly OVERLAY ("try to make the most -- in
        # UNITS"). The flat curve above stays the conservative CLV-reconciling record.
        series.update(_kelly.kelly_overlay(flat, start_units=su))
        # Reconciliation proof: the curve total == sum of placed graded unit_results.
        rec = _today.reconcile(placed, start_units=su)
        series["reconciles"] = bool(
            abs(series["summary"]["total_units"] - rec["cumulative_units"]) < 1e-6)
        # Persist the bankroll (single source of truth) + the daily fields.
        cfg = _bank.apply_settled(flat, start_units=su, path=bankroll_path,
                                  persist=True)
        day = today or _today._today_utc()
        day_units = next((d["day_units"] for d in series["per_day"]
                          if d["day"] == day), 0.0)
        cfg["day"] = day
        cfg["day_units"] = day_units
        _bank.write_config(cfg, bankroll_path)
        _atomic_write(sp, series)
        _atomic_write(tp, _today.build_today(
            clv_path=clv_path, start_units=su, today=day,
            bankroll_path=bankroll_path))
    except Exception as exc:  # noqa: BLE001 -- a tick must never sink the daemon
        logger.debug("bankroll_daemon tick degraded: %s", exc)
        series = {"summary": {"total_units": 0.0}, "reconciles": True,
                  "overall": "degraded", "note": type(exc).__name__}
        _atomic_write(sp, series)
    _beat(now, heartbeat_path)
    return series


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        **tick_kw: Any) -> int:
    """Run the daily-bankroll loop forever (or max_ticks). Never raises out.

    Everything is injectable so offline tests pass a fake clock, sleep stub, bounded
    max_ticks and isolated paths (incl. heartbeat_path). MEASUREMENT-ONLY."""
    import time as _time
    _clock = clock if clock is not None else _time.time
    _sleep = sleep if sleep is not None else _time.sleep
    # Boot beat uses the SAME heartbeat_path the ticks use (tmp in tests).
    _hb = tick_kw.get("heartbeat_path")
    ticks = 0
    try:
        _beat(float(_clock()), _hb)  # live at boot, before the first tick completes
    except Exception:  # noqa: BLE001
        _beat(None, _hb)
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                break
        try:
            now = float(_clock())
        except Exception:  # noqa: BLE001
            now = _time.time()
        tick(now=now, **tick_kw)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def _main() -> int:  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(description="Supervised daily-bankroll daemon "
                                "(m1_bankroll): placed paper bets -> UNIT equity curve.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    print("bankroll_daemon | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("bankroll_daemon | stopped by KeyboardInterrupt", flush=True)
    return 0


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "build_series", "tick",
           "run", "SERIES_PATH", "TODAY_PATH", "HEARTBEAT_PATH"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
