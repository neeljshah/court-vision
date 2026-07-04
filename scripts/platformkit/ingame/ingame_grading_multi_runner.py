"""scripts.platformkit.ingame.ingame_grading_multi_runner -- supervised entry
point for M36: multi-sport in-game grading (LANE 3). Runs the outcome-gated
verdict (ingame_outcome_verdict_multi) and the cross-corpus segment-trust gate
(ingame_segment_trust_multi) for every CAPTURING sport beyond MLB
(soccer_intl/tennis/wnba), so every capturing sport accrues the same honest
scoreboard MLB already has via m25/m26.

Every tick (default 900s, matching m25's cadence -- this corpus grows slate by
slate, same rationale):
  (a) ingame_outcome_verdict_multi.build_verdict_all() -> per-sport verdict,
      writes data/frontend/ops/ingame_outcome_verdict_multi.json.
  (b) ingame_segment_trust_multi.build_trust_all() -> per-sport cross-corpus
      trust, writes data/frontend/ops/ingame_segment_trust_multi.json.
Each step is try/except-isolated so one failing step never kills the tick or
blocks the other from refreshing.

MEASUREMENT ONLY -- mirrors the MLB m25/m26 pair's framing exactly:
VERDICTS ONLY, no $/roi/pnl field, edge_claimed always False, no bet placed,
no flag flipped. The trust doc here does NOT wire any floor/execution
routing (that stays exclusively with the MLB-only ingame_segment_trust path
pending a human review).

LANE 3 ADDITION (2026-07-03) -- before verdict/trust, each tick also runs a
BOUNDED, failure-isolated refresh of the outcome-label artifacts these
resolvers read (scripts.platformkit.autonomy.label_finals_refresh.refresh_all:
soccer_intl finals + MLB espn_boxscores + WNBA espn_scoreboard, each capped at
10 missing dates/tick). This closes the silent-staleness gap that left 26/32
soccer_intl in-game bets unresolved (espn_finals.parquet was never re-ingested
2026-06-22..28). Wrapped in its own try/except so a refresh failure (network
hiccup, bad HTML) can never block the verdict/trust steps that already run
here.

NOT YET REGISTERED FOR A RUNNING SUPERVISOR TICK -- the ProcSpec added to
supervisor/stack_specs.py requires a restart to take effect (restart already
pending per this lane's brief; new registrations ride it).

LANE 5 ADDITION (2026-07-03) -- FRESHNESS ADJUDICATION AUTO-WIRE (queue item 5,
2nd half). wave-8 ingame_freshness_cross_corpus.py + wave-7
ingame_outcome_verdict_freshness.py were standalone CLIs, nothing kept fresh.
Wall time measured (105-game MLB corpus): build_all()=2.4s, build_report(mlb)
=3.2s -- well under 60s/tick, so cost isn't the gate reason; N matches the
~2-4x/day cadence asked for (slow-growing corpus). Every Nth tick
(N=FRESHNESS_EVERY_N_TICKS=32, 900s*32=8h => 3x/day) also runs:
  (c) ingame_outcome_verdict_freshness.build_all() -> per-sport raw/fresh_only
      pair -> data/frontend/ops/ingame_outcome_verdict_freshness.json.
  (d) ingame_freshness_cross_corpus.build_report(sport='mlb') -> cross-corpus
      WORSE-REPLICATED/NOT-REPLICATED/INSUFFICIENT ->
      data/frontend/ops/ingame_freshness_cross_corpus.json.
Both try/except-isolated (mirrors label-refresh hook); a raise never sinks the
host tick or a sibling step. Module-level tick counter (reset on restart);
off-cadence ticks no-op with skipped_reason. MEASUREMENT ONLY.

Heartbeat: m36_ingame_grading_multi. Cadence: DEFAULT_INTERVAL_SEC=900s.
Freshness: every FRESHNESS_EVERY_N_TICKS(32) ticks = ~8h = ~3x/day.
ASCII only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_grading_multi_runner.py -q
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("ingame_grading_multi_runner")

HEARTBEAT_COMPONENT = "m36_ingame_grading_multi"
DEFAULT_INTERVAL_SEC = 900.0

# LANE 5: run the two freshness adjudications every Nth tick (measurement-only,
# slow-growing corpus -- no value recomputing every 900s tick). N=32 * 900s =
# 8h => 3x/day, inside the brief's 2-4x/day target. Module-level counter, reset
# only by process restart (matches this runner's existing no-persistence style).
FRESHNESS_EVERY_N_TICKS = 32
_tick_counter = 0


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M36 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_grading_multi heartbeat skipped: %s", exc)


def _run_verdict() -> Dict[str, Any]:
    """Re-run the multi-sport outcome-gated verdict; writes ONE ops artifact.
    Returns {sport: {n_labeled, better_segments, worse_segments}}."""
    from scripts.platformkit.ingame.ingame_outcome_verdict_multi import (
        build_verdict_all, write_doc)
    doc = build_verdict_all()
    write_doc(doc)
    return {sport: {"n_labeled": d.get("n_labeled", 0),
                    "better_segments": d.get("better_segments", []),
                    "worse_segments": d.get("worse_segments", [])}
            for sport, d in doc.get("per_sport", {}).items()}


def _run_trust() -> Dict[str, Any]:
    """Re-run the multi-sport cross-corpus segment trust; writes ONE ops
    artifact. MEASUREMENT ONLY -- wires no floor/execution routing."""
    from scripts.platformkit.ingame.ingame_segment_trust_multi import (
        build_trust_all, write_doc)
    doc = build_trust_all()
    write_doc(doc)
    return {sport: {"trusted": d.get("trusted", []), "adverse": d.get("adverse", [])}
            for sport, d in doc.get("per_sport", {}).items()}


def _run_outcome_verdict_freshness() -> Dict[str, Any]:
    """LANE 5: raw-vs-fresh_only quote-freshness control (wave-7), across
    CONTROL_SPORTS (mlb + soccer_intl/tennis/wnba/npb/kbo). Writes ONE ops
    artifact. Returns the headline flipped_segments_by_sport map."""
    from scripts.platformkit.ingame.ingame_outcome_verdict_freshness import (
        build_all, write_doc)
    doc = build_all()
    write_doc(doc)
    return {"flipped_segments_by_sport": doc.get("flipped_segments_by_sport", {})}


def _run_freshness_cross_corpus() -> Dict[str, Any]:
    """LANE 5: MLB-only cross-corpus adjudication of the fresh_only WORSE
    finding (wave-8). Writes ONE ops artifact. Returns the headline overall
    per-segment verdict."""
    from scripts.platformkit.ingame.ingame_freshness_cross_corpus import (
        build_report, write_doc)
    doc = build_report(sport="mlb")
    write_doc(doc)
    return {"overall_segment_verdict": doc.get("overall_segment_verdict", {})}


def _run_label_refresh() -> Dict[str, Any]:
    """LANE 3: bounded, failure-isolated refresh of the outcome-label parquets
    (soccer_intl finals + MLB boxscores + WNBA scoreboard) the resolvers this
    tick's verdict/trust steps depend on. Never raises -- refresh_all already
    isolates per-spec; this wrapper is belt+suspenders against an unexpected
    import-time error."""
    from scripts.platformkit.autonomy.label_finals_refresh import refresh_all
    return refresh_all()


def _compose(verdict_summary: Dict[str, Any], trust_summary: Dict[str, Any],
            now_iso: str, label_refresh_summary: Optional[Dict[str, Any]] = None,
            freshness_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "component": "ingame_grading_multi", "generated_at": now_iso,
        "verdict_summary": verdict_summary,
        "trust_summary": trust_summary,
        "label_refresh_summary": label_refresh_summary or {},
        "freshness_summary": freshness_summary or {"skipped_reason": "not_nth_tick"},
        "measurement_only": True,
        "honest_note": ("verdicts + cross-corpus trust for soccer_intl/tennis/wnba, "
                        "mirroring the MLB m25/m26 pair; INSUFFICIENT_N/NEUTRAL is "
                        "the correct, honest result for a sport whose in-play "
                        "capture corpus is still thin; wires no floor/execution "
                        "routing; no $ edge claimed; label_refresh_summary is the "
                        "LANE-3 bounded finals-freshness self-heal (soccer_intl/mlb/"
                        "wnba), isolated so its failure never blocks a verdict; "
                        "freshness_summary is the LANE-5 every-Nth-tick refresh of "
                        "the quote-freshness control (wave-7) and its MLB "
                        "cross-corpus adjudication (wave-8), isolated the same way"),
        "edge_claimed": False,
    }


def _should_run_freshness(tick_no: int) -> bool:
    """True on every FRESHNESS_EVERY_N_TICKS-th tick (1-indexed: tick 1, 33, 65...
    runs so the very first tick after a restart also refreshes once)."""
    return (tick_no - 1) % FRESHNESS_EVERY_N_TICKS == 0


def _run_freshness_adjudications() -> Dict[str, Any]:
    """LANE 5: both freshness adjudications, each failure-isolated so one
    raising never blocks the other or the host tick."""
    out: Dict[str, Any] = {}
    try:
        out["outcome_verdict_freshness"] = _run_outcome_verdict_freshness()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_grading_multi outcome_verdict_freshness step raised: %s", exc)
        out["outcome_verdict_freshness"] = {"error": str(exc)}
    try:
        out["freshness_cross_corpus"] = _run_freshness_cross_corpus()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_grading_multi freshness_cross_corpus step raised: %s", exc)
        out["freshness_cross_corpus"] = {"error": str(exc)}
    return out


def tick(*, now: float,
         verdict_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         trust_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         label_refresh_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         freshness_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         tick_no: Optional[int] = None) -> Dict[str, Any]:
    """One re-grading tick: label refresh -> verdict -> trust -> (every Nth
    tick) freshness adjudications -> composed doc -> heartbeat. Never raises.
    Each step isolated; a raising step degrades to an empty/ERROR entry, never
    kills the tick or blocks a sibling step.

    tick_no: 1-indexed tick number used for the Nth-tick freshness gate. If
    omitted, uses and advances the module-level _tick_counter (real run() loop
    usage); callers that want deterministic gating in tests should pass it
    explicitly."""
    global _tick_counter
    _verdict = verdict_fn if verdict_fn is not None else _run_verdict
    _trust = trust_fn if trust_fn is not None else _run_trust
    _label_refresh = label_refresh_fn if label_refresh_fn is not None else _run_label_refresh
    _freshness = freshness_fn if freshness_fn is not None else _run_freshness_adjudications

    if tick_no is None:
        _tick_counter += 1
        this_tick_no = _tick_counter
    else:
        this_tick_no = tick_no

    try:
        label_refresh_summary = _label_refresh()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_grading_multi label refresh step raised: %s", exc)
        label_refresh_summary = {"error": str(exc)}
    try:
        verdict_summary = _verdict()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_grading_multi verdict step raised: %s", exc)
        verdict_summary = {"error": str(exc)}
    try:
        trust_summary = _trust()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_grading_multi trust step raised: %s", exc)
        trust_summary = {"error": str(exc)}

    if _should_run_freshness(this_tick_no):
        try:
            freshness_summary = _freshness()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingame_grading_multi freshness step raised: %s", exc)
            freshness_summary = {"error": str(exc)}
    else:
        freshness_summary = {"skipped_reason": "not_nth_tick", "tick_no": this_tick_no,
                             "every_n_ticks": FRESHNESS_EVERY_N_TICKS}

    now_iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
    doc = _compose(verdict_summary, trust_summary, now_iso, label_refresh_summary,
                   freshness_summary)
    _beat(now)
    return doc


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the re-grading loop forever (or max_ticks). Never raises out.
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
        doc = tick(now=now)
        print("%s | tick=%d verdict=%s trust=%s" % (
            HEARTBEAT_COMPONENT, ticks, doc.get("verdict_summary"),
            doc.get("trust_summary")), flush=True)
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
    p = argparse.ArgumentParser(
        description="Supervised multi-sport in-game grading (M36): every 900s "
                    "re-runs the soccer_intl/tennis/wnba outcome-gated verdict "
                    "and cross-corpus segment trust. Verdicts only, no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    print("ingame_grading_multi_runner | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("ingame_grading_multi_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "FRESHNESS_EVERY_N_TICKS",
          "tick", "run"]
