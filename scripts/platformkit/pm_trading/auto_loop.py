"""scripts.platformkit.pm_trading.auto_loop -- the always-on self-improving paper loop.

One honest cycle = (1) PAPER-trade today's real games -> CLV ledger (executed=False),
(2) GRADE finished games (win/loss + CLV vs close), (3) SELF-IMPROVE: recalibrate on
the accumulated REAL outcomes, gated by the eval-gate (only ever improve or hold).

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
from typing import Any, Dict

# Make the loop cwd-independent: add the repo root to sys.path so `python -m ...`
# works even if launched from a different directory (the bash cwd is flaky).
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.pm_trading.run_paper_today import run_paper_cycle
from scripts.platformkit.grade_paper import grade_open_bets, grade_summary
from scripts.platformkit.self_improve import improve_all


def run_once() -> Dict[str, Any]:
    """Run one full cycle. Each step is guarded so one failure never sinks the loop."""
    out: Dict[str, Any] = {}
    for name, fn in (("paper", run_paper_cycle),
                     ("grade", grade_open_bets),
                     ("improve", improve_all)):
        try:
            out[name] = fn()
        except Exception as exc:  # noqa: BLE001 -- a step must never crash the loop
            out[name] = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
            traceback.print_exc()
    try:
        out["summary"] = grade_summary()
    except Exception as exc:  # noqa: BLE001
        out["summary"] = {"status": "error", "reason": str(exc)}
    return out


def _print_cycle(out: Dict[str, Any]) -> None:
    s = out.get("summary") or {}
    paper = out.get("paper") or {}
    n = s.get("n", 0)
    print("[auto_loop] cycle done | "
          f"paper_recorded={paper.get('recorded', paper.get('status', '?'))} | "
          f"graded_n={n} hit_rate={s.get('hit_rate')} paper_roi={s.get('paper_roi')} "
          f"mean_clv={s.get('mean_clv_pct')} | improve={_improve_brief(out.get('improve'))}")
    print("HONEST: paper only (executed=False); calibration/CLV is the yardstick, NOT a $ edge.")


def _improve_brief(imp: Any) -> str:
    if not isinstance(imp, dict):
        return str(imp)
    verds = imp.get("verdicts") or imp.get("by_sport") or imp
    if isinstance(verds, dict):
        return ",".join(f"{k}={v.get('verdict', v) if isinstance(v, dict) else v}"
                        for k, v in verds.items())
    return str(verds)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Always-on self-improving paper loop.")
    ap.add_argument("--forever", action="store_true", help="loop until stopped")
    ap.add_argument("--interval", type=int, default=1200,
                    help="seconds between cycles in --forever mode (default 1200 = 20 min)")
    a = ap.parse_args(argv)
    while True:
        _print_cycle(run_once())
        if not a.forever:
            return 0
        time.sleep(max(60, a.interval))


if __name__ == "__main__":
    raise SystemExit(main())
