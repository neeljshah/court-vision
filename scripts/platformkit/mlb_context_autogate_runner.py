"""scripts.platformkit.mlb_context_autogate_runner -- supervised M32 entry.

Nightly re-gating daemon: as the MLB context corpus (probables/weather from
M31, games_current outcomes) keeps growing, this re-runs the three current
context-driven candidate gates end-to-end so their verdicts stay fresh against
the growing corpus, WITHOUT a human in the loop:

  (a) SP-offset gate  -- domains.mlb.sp_adjust_current.run_forward_eval() +
      _verdict(), rewrites data/domains/mlb/sp_adjust_verdict.json.
  (b) weather-totals gate -- domains.mlb.weather_totals_gate.run_gate(),
      rewrites data/domains/mlb/weather_totals_verdict.json.
  (c) weather-vs-close gate -- domains.mlb.weather_vs_close_gate.run_gate_
      with_context(), rewrites data/domains/mlb/weather_vs_close_verdict.json.
      The decisive candidate: does weather add anything vs the market's own
      totals CLOSE (not just vs our own baseline)? Expected result is REJECT
      (the close already prices weather); SHIP_REVIEW would be extraordinary.
  (d) in-play tail-band gate -- scripts.platformkit.ingame.ingame_tail_gate
      .run_gate(), rewrites data/domains/mlb/ingame_tail_verdict.json.  PRE-
      REGISTERED venue-bias hypotheses (longshot band underpriced / mid-fav
      band overpriced) scored on FORWARD-captured games only; confirmation
      accumulates as the in-play capture corpus grows.

Then composes ONE ops summary doc, data/frontend/ops/mlb_context_autogate.json,
listing every candidate + its current verdict + a ship_review roster.

VERDICTS ONLY. This daemon never wires, ships, or flips a flag for any
candidate -- SHIP_REVIEW/SHIP-READY verdicts surface for a HUMAN to decide.
No $ field, no flag flip, no data/registry/ write, no real-money action.
Each gate step is try/except-isolated so one failing gate never kills the
tick or blocks the other candidate's verdict from refreshing.

Heartbeat: m32_mlb_context_autogate -> data/cache/daemon_heartbeats/m32_mlb_context_autogate.txt
Cadence: DEFAULT_INTERVAL_SEC = 86400 s (nightly; the corpus moves on daily scales).
Repo-internal only; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("mlb_context_autogate_runner")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AUTOGATE_OUT = _REPO_ROOT / "data" / "frontend" / "ops" / "mlb_context_autogate.json"

HEARTBEAT_COMPONENT = "m32_mlb_context_autogate"
DEFAULT_INTERVAL_SEC = 86400.0

_SHIP_VERDICTS = frozenset({"SHIP_REVIEW", "SHIP-READY"})


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M32 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("mlb_context_autogate heartbeat skipped: %s", exc)


def _run_sp_gate() -> Dict[str, Any]:
    """Re-run the SP-offset gate end-to-end; rewrite its verdict JSON. Returns
    a compact headline dict: {name, verdict, verdict_reason, n, ...}."""
    from domains.mlb.sp_adjust_current import _verdict, run_forward_eval
    forward = run_forward_eval()
    verdict, reason = _verdict(True, forward)
    out = {
        "task1_replicated_both_eras": True,
        "forward_eval_2026": forward,
        "verdict": verdict,
        "verdict_reason": reason,
        "flag": "CV_MLB_SP_ADJUST",
        "flag_state": "OFF (default; not set anywhere in this repo)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path = _REPO_ROOT / "data/domains/mlb/sp_adjust_verdict.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    return {
        "name": "sp_elo_offset_2026_forward", "verdict": verdict, "verdict_reason": reason,
        "n": forward.get("n", 0), "n_with_sp_form": forward.get("n_with_sp_form", 0),
    }


def _run_weather_gate() -> Dict[str, Any]:
    """Re-run the weather-totals gate; rewrite its verdict JSON. Returns a
    compact headline dict: {name, verdict, verdict_reason, n, n_scorable}."""
    from domains.mlb.weather_totals_gate import run_gate
    result = run_gate()
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    out_path = _REPO_ROOT / "data/domains/mlb/weather_totals_verdict.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(result, f, indent=2, default=str)
    os.replace(str(tmp), str(out_path))
    return {
        "name": "weather_totals", "verdict": result.get("verdict", "ERROR"),
        "verdict_reason": result.get("verdict_reason", ""),
        "n": result.get("n", 0), "n_scorable": result.get("n_scorable", 0),
    }


def _run_weather_vs_close_gate() -> Dict[str, Any]:
    """Re-run the weather-vs-close gate; rewrite its verdict JSON. Returns a
    compact headline dict: {name, verdict, verdict_reason, n, n_scorable}.
    The decisive candidate: does weather beat the MARKET CLOSE, not just our
    own baseline. Expected result is REJECT (books already price weather)."""
    from domains.mlb.weather_vs_close_gate import run_gate_with_context
    result = run_gate_with_context()
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    out_path = _REPO_ROOT / "data/domains/mlb/weather_vs_close_verdict.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(result, f, indent=2, default=str)
    os.replace(str(tmp), str(out_path))
    return {
        "name": "weather_vs_close", "verdict": result.get("verdict", "ERROR"),
        "verdict_reason": result.get("verdict_reason", ""),
        "n": result.get("n", 0), "n_scorable": result.get("n_scorable", 0),
    }


def _run_tail_gate() -> Dict[str, Any]:
    """Re-run the pre-registered in-play tail-band gate (forward evidence only);
    it rewrites data/domains/mlb/ingame_tail_verdict.json itself."""
    from scripts.platformkit.ingame.ingame_tail_gate import run_gate
    return run_gate()


def _compose(candidates: List[Dict[str, Any]], now_iso: str) -> Dict[str, Any]:
    ship_review = [c["name"] for c in candidates if c.get("verdict") in _SHIP_VERDICTS]
    return {
        "generated_at": now_iso,
        "candidates": candidates,
        "ship_review": ship_review,
        "honest_note": "verdicts only; wiring any winner is a human decision; no $ edge claimed",
    }


def tick(*, now: float,
         sp_gate_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         weather_gate_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         weather_vs_close_gate_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         tail_gate_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """One re-gating tick: SP gate -> weather gate -> weather-vs-close gate ->
    tail-band gate -> composed doc -> heartbeat. Never raises. Each gate step
    isolated; a raising gate is recorded as an ERROR candidate entry, never
    kills the tick."""
    _sp = sp_gate_fn if sp_gate_fn is not None else _run_sp_gate
    _weather = weather_gate_fn if weather_gate_fn is not None else _run_weather_gate
    _weather_vs_close = (weather_vs_close_gate_fn if weather_vs_close_gate_fn is not None
                          else _run_weather_vs_close_gate)
    _tail = tail_gate_fn if tail_gate_fn is not None else _run_tail_gate

    candidates: List[Dict[str, Any]] = []
    for name, fn in (("sp_elo_offset_2026_forward", _sp), ("weather_totals", _weather),
                      ("weather_vs_close", _weather_vs_close),
                      ("ingame_tail_bands", _tail)):
        try:
            headline = fn()
            if not isinstance(headline, dict) or "name" not in headline:
                headline = {"name": name, "verdict": "ERROR",
                            "verdict_reason": "gate returned malformed headline"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("mlb_context_autogate %s raised: %s", name, exc)
            headline = {"name": name, "verdict": "ERROR", "verdict_reason": str(exc)}
        candidates.append(headline)

    now_iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
    doc = _compose(candidates, now_iso)
    try:
        _AUTOGATE_OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = _AUTOGATE_OUT.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(doc, f, indent=2, default=str)
        os.replace(str(tmp), str(_AUTOGATE_OUT))
    except Exception as exc:  # noqa: BLE001
        logger.warning("mlb_context_autogate compose-write raised: %s", exc)
    _beat(now)
    return doc


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        sp_gate_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        weather_gate_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        weather_vs_close_gate_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        tail_gate_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the re-gating loop forever (or max_ticks). Never raises out.
    Everything injectable for offline tests. Returns ticks executed."""
    import time as _time
    _clock = clock if clock is not None else _time.time
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    try:
        _beat(float(_clock()))
    except Exception:  # noqa: BLE001
        _beat()
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
        doc = tick(now=now, sp_gate_fn=sp_gate_fn, weather_gate_fn=weather_gate_fn,
                   weather_vs_close_gate_fn=weather_vs_close_gate_fn,
                   tail_gate_fn=tail_gate_fn)
        ship_review = doc.get("ship_review", [])
        print("%s | tick=%d candidates=%d ship_review=%s" % (
            HEARTBEAT_COMPONENT, ticks, len(doc.get("candidates", [])), ship_review), flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def main() -> int:  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(
        description="Supervised MLB context autogate (M32): nightly re-run of the "
                    "SP-offset + weather-totals candidate gates, verdicts only. No $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print("mlb_context_autogate_runner | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("mlb_context_autogate_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
