"""scripts.platformkit.ingame.ingame_clv_verdict_daemon -- compute the honest IN-GAME
CLV verdict continuously, on the flywheel, with NO Claude in the loop.

THE GAP IT CLOSES: m11 already logs, every ~2 min for every live game, a point-in-time
model_prob + the live market_prob (data/cache/ingame_grade/<sport>/<game>.jsonl).
ingame_clv_grade.grade_sport() replays those series leak-free and asks "did the engine's
live repriced number ANTICIPATE where the in-play market CLOSED?" -- the one honest test
of whether we are catching the small in-game gaps.  But that verdict was only ever
computed by a MANUAL CLI run.  This daemon runs it every ~10 min so the in-game gap-hunt
produces a continuously-updating, leak-free verdict the ops surface can read.

Each tick: grade_sport(sport) for the in-season sports -> resolve_clv_status -> write one
compact verdict doc (data/frontend/ops/ingame_clv_verdict.json) + log a line.

HONEST RAILS: the verdict is CLV in PROBABILITY space (anticipation of the in-play
close), explicitly NOT a $ edge and NOT a claim of beating a sharp pregame market.
INSUFFICIENT_DATA / MATCH are honest successes.  Reads only captured series; flips NO
flag; places NO bet; writes NO data/registry/; no real-money action.  Injectable
(grade_fn/clock/sleep/should_stop/max_ticks) for offline tests.  ASCII; never raises out.

CLI:
    python -m scripts.platformkit.ingame.ingame_clv_verdict_daemon            # ~10min loop
    python -m scripts.platformkit.ingame.ingame_clv_verdict_daemon --once
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

_REPO = Path(__file__).resolve().parents[3]
VERDICT_PATH = _REPO / "data" / "frontend" / "ops" / "ingame_clv_verdict.json"
DEFAULT_INTERVAL_SEC = 600.0          # in-game series grow during live games
DEFAULT_SPORTS = ("mlb", "soccer_intl")
COMPONENT = "m_ingame_clv_verdict"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _grade_one(sport: str) -> Dict[str, Any]:
    """Run the honest grade for one sport; normalize to a compact verdict row."""
    from scripts.platformkit.improve import ingame_clv_grade as G
    summ = G.grade_sport(sport) or {}
    status, msg = G.resolve_clv_status(sport, summ)
    row: Dict[str, Any] = {"sport": sport, "verdict": status, "msg": str(msg)[:240]}
    # surface whatever honest figures the summary exposes (never fabricate)
    for k in ("mean_clv", "n_scored_ticks", "n_ticks", "n_markets", "n_games",
              "beat", "behind", "hit_rate", "brier_model", "brier_close", "bss"):
        if k in summ:
            row[k] = summ[k]
    return row


def collect(sports: Sequence[str] = DEFAULT_SPORTS,
            grade_fn: Optional[Callable[[str], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Grade every sport (each isolated) and assemble the verdict doc."""
    gf = grade_fn or _grade_one
    rows: List[Dict[str, Any]] = []
    for sp in sports:
        try:
            rows.append(gf(sp))
        except Exception as exc:  # robust: one sport must not kill the sweep
            rows.append({"sport": sp, "verdict": "ERROR", "error": str(exc)[:200]})
    return {"updated_at": _utc(), "component": COMPONENT,
            "note": "in-game CLV = anticipation of the in-play close (probability "
                    "space); calibration, NOT a $ edge.",
            "sports": rows}


def write_verdict(doc: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = Path(path) if path is not None else VERDICT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=0), encoding="ascii")
    tmp.replace(p)


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        sports: Sequence[str] = DEFAULT_SPORTS,
        grade_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
        verdict_path: Optional[Path] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the verdict loop forever (or ``max_ticks``).  Survives any tick failure;
    returns ticks executed."""
    import time as _time
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                break
        try:
            doc = collect(sports, grade_fn=grade_fn)
            write_verdict(doc, verdict_path)
            verds = " ".join("%s=%s" % (r["sport"], r.get("verdict"))
                             for r in doc["sports"])
            print("%s | tick=%d %s" % (COMPONENT, ticks, verds), flush=True)
        except Exception as exc:  # noqa: BLE001 - survive any failure
            print("%s | tick=%d ERROR %s" % (COMPONENT, ticks, str(exc)[:160]),
                  flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def _main() -> int:  # pragma: no cover
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Autonomous in-game CLV verdict daemon: every ~10min replays the "
                    "captured M11 model/market series -> honest in-play-close "
                    "anticipation verdict. Calibration only; no edge ever claimed.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between verdict sweeps (default: %(default)s).")
    p.add_argument("--once", action="store_true", help="Run a single sweep and exit.")
    a = p.parse_args()
    print("%s | started interval=%ss once=%s" % (COMPONENT, a.interval, a.once),
          flush=True)
    try:
        run(interval_sec=a.interval, max_ticks=1 if a.once else None)
    except KeyboardInterrupt:
        print("%s | stopped by KeyboardInterrupt" % COMPONENT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
