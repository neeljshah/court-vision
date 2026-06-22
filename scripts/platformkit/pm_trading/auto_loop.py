"""scripts.platformkit.pm_trading.auto_loop -- the always-on self-improving paper loop.

One honest cycle = (1) PAPER-trade today's real games -> CLV ledger (executed=False),
(2) GRADE finished games (win/loss + CLV vs close), (3) SELF-IMPROVE: recalibrate on
the accumulated REAL outcomes, gated by the eval-gate (only ever improve or hold) --
this IS the live self-improvement ratchet (scripts.platformkit.self_improve.improve_all),
(4) LINE TICK: capture a line/close snapshot via line_snapshot_daemon.poll_once for
each active sport, (5) SCOREBOARD: write grade_summary.json atomically so the UI and
the real-money gate always have a fresh view.

Steps (4) and (5) are independently guarded: one failing step never blocks the others.

This is measurement, not money: PAPER only, no network orders, no $-edge claimed. The
loop gets smarter strictly as real games settle. Run one cycle or --forever.

Usage:
  python -m scripts.platformkit.pm_trading.auto_loop                 # one cycle
  python -m scripts.platformkit.pm_trading.auto_loop --forever --interval 1200

INVARIANTS: build only under scripts/platformkit/; paper-only; ASCII; no edge claims.
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

# Make the loop cwd-independent: add the repo root to sys.path so `python -m ...`
# works even if launched from a different directory (the bash cwd is flaky).
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.pm_trading.run_paper_today import run_paper_cycle
from scripts.platformkit.grade_paper import grade_open_bets, grade_summary
from scripts.platformkit.self_improve import improve_all

import logging

logger = logging.getLogger("auto_loop")

# Active sports for the line/close capture tick (matches odds_provider defaults).
_LINE_SPORTS: tuple = ("nba", "mlb", "soccer", "tennis")

# Per-tick cap on NEW prop placements per sport (highest-EV first). Bounds the daily
# prop volume so the loop never floods the ledger; dedup keeps it idempotent within a day.
_PROP_MAX_PER_SPORT: int = 8


def _place_props() -> Dict[str, Any]:
    """Paper-place today's priced player props into the unified ledger (UNITS, capped).
    Guarded + lazy import so a prop-feed error never sinks the loop. Idempotent per day."""
    try:
        from scripts.platformkit.bestbets.props_paper_placer import run as _place
        return _place(max_per_sport=_PROP_MAX_PER_SPORT)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def _settle_props() -> Dict[str, Any]:
    """Settle OPEN props on their real post-game stat outcome (UNITS). Guarded."""
    try:
        from scripts.platformkit.bestbets.prop_settler import settle_open_props as _settle
        return _settle()
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def _prop_improve() -> Dict[str, Any]:
    """Run the leak-free PROP CALIBRATION ratchet on the accumulated settled props -- the
    props 'gets better' loop, the prop twin of the game self-improve ratchet (step 3).

    SHIP only when the eval-gate passes, the planted-null rejects, AND the walk-forward
    isotonic recal beats held-out Brier; else HOLD/REJECT; cold start = INSUFFICIENT_DATA.
    PROPOSE/RECORD ONLY: appends to prop_improve_ledger.jsonl, NEVER arms serving / flips
    a flag / writes data/registry/. Guarded so a ratchet error never sinks the loop."""
    try:
        from scripts.platformkit.improve.prop_calibration_ratchet import improve_all as _pi
        return _pi()
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def _prop_history_improve() -> Dict[str, Any]:
    """Run ONE historical prop-calibration fold from the on-disk gamelogs (leak-free) so
    props get better from OLD games -- no live games needed. A FRESH random player sample
    each cycle (rotating seed) -> accumulating independent folds = honest replication
    (single-fold lifts are artifacts). PROPOSE/RECORD only (own corpus file + tagged verdict
    in prop_improve_ledger; never the units ledger / a flag / data/registry/). Guarded."""
    try:
        from scripts.platformkit.improve.prop_history_backtest import run_history_fold
        return run_history_fold(seed=int(time.time()) % 100000)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}

# Liveness heartbeat (RB-P0-03): this loop is supervised as m1_paper. It MUST beat
# its declared heartbeat every cycle so the supervisor's HEARTBEAT readiness reads
# this service not-ready when the heartbeat is absent (fresh boot) OR stale (a hung
# cycle) -- never a stale-green NONE that reads READY forever. Mirrors the
# inplay_runner / selfimprove_runner / m7 pattern (ops.liveness.heartbeat).
HEARTBEAT_COMPONENT = "m1_paper"


def _beat(now_epoch=None) -> None:
    """Write the m1_paper liveness heartbeat. Never raises (observability only)."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001 -- a heartbeat write must never sink the loop
        logger.debug("auto_loop heartbeat skipped: %s", exc)


def _line_tick(sports: tuple = _LINE_SPORTS) -> Dict[str, Any]:
    """Capture one line/close snapshot tick for each active sport.

    Calls line_snapshot_daemon.poll_once per sport; isolated per-sport so a feed
    error on one sport never blocks the others. Import is lazy+guarded so a missing
    dependency never crashes the loop.
    """
    result: Dict[str, Any] = {"status": "ok", "sports": []}
    try:
        from scripts.platformkit.odds_provider.line_snapshot_daemon import poll_once
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": "%s: %s" % (type(exc).__name__, exc)}
    for sport in sports:
        try:
            rep = poll_once(sport)
        except Exception as exc:  # noqa: BLE001 -- per-sport isolation
            rep = {"sport": sport, "status": "error: %s" % type(exc).__name__}
        result["sports"].append(rep)
    return result


def _write_scoreboard() -> Dict[str, Any]:
    """Write grade_summary.json via scoreboard.write_scoreboard. Guarded."""
    try:
        from scripts.platformkit.pm_trading.scoreboard import write_scoreboard
        out_path = write_scoreboard()
        return {"status": "ok", "path": str(out_path)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def run_once(line_sports: tuple = _LINE_SPORTS) -> Dict[str, Any]:
    """Run one full cycle. Each step is guarded so one failure never sinks the loop."""
    out: Dict[str, Any] = {}
    for name, fn in (("paper", run_paper_cycle),
                     ("place_props", _place_props),
                     ("grade", grade_open_bets),
                     ("settle_props", _settle_props),
                     ("improve", improve_all),
                     ("prop_improve", _prop_improve),
                     ("prop_history_improve", _prop_history_improve)):
        try:
            out[name] = fn()
        except Exception as exc:  # noqa: BLE001 -- a step must never crash the loop
            out[name] = {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}
            traceback.print_exc()
    try:
        out["summary"] = grade_summary()
    except Exception as exc:  # noqa: BLE001
        out["summary"] = {"status": "error", "reason": str(exc)}
    # Guarded step (4): line/close capture tick
    try:
        out["line_tick"] = _line_tick(line_sports)
    except Exception as exc:  # noqa: BLE001 -- must not stop the loop
        out["line_tick"] = {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}
    # Guarded step (5): scoreboard write
    try:
        out["scoreboard"] = _write_scoreboard()
    except Exception as exc:  # noqa: BLE001 -- must not stop the loop
        out["scoreboard"] = {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}
    # NOTE: there is NO separate "ratchet" step. The live self-improvement ratchet
    # IS step (3) improve_all above (out["improve"]) -- the eval-gate-gated
    # recalibration that only ever improves or holds. An earlier _ratchet_tick that
    # imported a never-built ratchet_candidate.pending_candidate provider was a
    # permanent no-op and has been removed so the cycle's reported steps match what
    # actually runs (honesty: don't advertise a step that never executes).
    return out


def _print_cycle(out: Dict[str, Any]) -> None:
    s = out.get("summary") or {}
    paper = out.get("paper") or {}
    lt = out.get("line_tick") or {}
    sb = out.get("scoreboard") or {}
    pp = out.get("place_props") or {}
    sp = out.get("settle_props") or {}
    n = s.get("n", 0)
    print("[auto_loop] props | placed=%s settled=%s pending=%s"
          % (pp.get("n_placed", pp.get("status", "?")),
             sp.get("n_settled_now", sp.get("status", "?")),
             sp.get("n_pending", "?")))
    # improve=<verdicts> IS the live self-improvement ratchet (step 3, improve_all);
    # there is no separate ratchet field because no separate ratchet step runs.
    print("[auto_loop] cycle done | "
          "paper_recorded=%s | "
          "graded_n=%s hit_rate=%s mean_clv=%s | "
          "improve=%s | prop_improve=%s | line_tick=%s | scoreboard=%s"
          % (paper.get("recorded", paper.get("status", "?")),
             n, s.get("hit_rate"), s.get("mean_clv_pct"),
             _improve_brief(out.get("improve")),
             _improve_brief(out.get("prop_improve")),
             lt.get("status", "?"), sb.get("status", "?")))
    ph = out.get("prop_history_improve") or {}
    print("[auto_loop] prop_history (from old games) | verdict=%s n_rows=%s delta_brier=%s"
          % (ph.get("verdict", ph.get("status", "?")), ph.get("n_rows", "?"),
             ph.get("delta_brier", "?")))
    print("HONEST: paper only (executed=False); calibration/CLV is the yardstick, NOT a $ edge.")


def _improve_brief(imp: Any) -> str:
    if not isinstance(imp, dict):
        return str(imp)
    verds = imp.get("verdicts") or imp.get("by_sport") or imp
    if isinstance(verds, dict):
        return ",".join(f"{k}={v.get('verdict', v) if isinstance(v, dict) else v}"
                        for k, v in verds.items())
    return str(verds)


def main(argv=None, *, run_fn=None, sleep=None, clock=None,
         max_cycles=None) -> int:
    """Run the paper loop, beating the m1_paper heartbeat every cycle.

    Defaults match the CLI (real run_once + time.sleep). Tests inject a fake
    ``run_fn`` / ``sleep`` / ``clock`` and a bounded ``max_cycles`` so the loop
    runs N cycles with NO real sleep and proves the heartbeat lands each cycle.
    """
    ap = argparse.ArgumentParser(description="Always-on self-improving paper loop.")
    ap.add_argument("--forever", action="store_true", help="loop until stopped")
    ap.add_argument("--interval", type=int, default=1200,
                    help="seconds between cycles in --forever mode (default 1200 = 20 min)")
    a = ap.parse_args(argv)
    _run = run_fn if run_fn is not None else run_once
    _sleep = sleep if sleep is not None else time.sleep
    _beat()  # live BEFORE the first (slow) cycle completes
    n = 0
    while True:
        out = _run()
        _beat(float(clock()) if clock is not None else None)
        _print_cycle(out)
        n += 1
        if not a.forever:
            return 0
        if max_cycles is not None and n >= max_cycles:
            return 0
        _sleep(max(60, a.interval))


if __name__ == "__main__":
    raise SystemExit(main())
