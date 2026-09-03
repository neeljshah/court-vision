"""scripts.platformkit.ingame.ingame_enrichment_runner -- LANE 2 combined WAVE-10
enrichment tick (m37): fotmob (soccer live) + gumbo (mlb live) + book-depth
(live in-play markets), ticked on ONE supervised cadence.

Every tick (default 30s, the fastest of the three source cadences -- fotmob's
own ~60s pace is honored internally via its own poll_once sleep_s pacing, not by
skipping ticks here, so this stays a SINGLE simple cadence rather than a
per-source scheduler; EXCEPTION, latency-audit fix 2026-07-07: when the last
tick saw >=1 live MLB game, the inter-tick wait is spent inside
gumbo_mlb_poller.run_live_window(), fast-polling GUMBO diffPatch at
CV_GUMBO_LIVE_SEC (default 10s) instead of sleeping idle -- fotmob/book-depth
keep their 30s cadence, idle behavior unchanged):
  (a) domains.soccer.ingame_fotmob.poll_once()        -- soccer live snapshots
  (b) scripts.platformkit.ingame.gumbo_mlb_poller.run_once() -- MLB GUMBO ticks,
      using game_pk_bridge_live for id-join context (best-effort, additive)
  (c) scripts.platformkit.ingame.ingame_book_depth_poller.poll_once() -- live
      in-play book-depth snapshots (kalshi + polymarket), BOUNDED (no internal
      serve_bounded loop -- this runner's own tick cadence IS the pacing)

PER-SOURCE FAILURE ISOLATION (mirrors ingame_label_refresh's pattern, reused
verbatim in spirit): one source's exception is caught, logged, and degrades to
an {"error": str} entry for THAT source only -- it never sinks the tick or
blocks a sibling source from running.

MEASUREMENT / CAPTURE ONLY: this runner touches no bet/decision path, flips no
flag, writes no data/registry/. It only appends to each source's OWN existing
sidecar (gumbo_live/<pk>.jsonl, book_depth/<venue>/<date>.jsonl, fotmob's own
sidecar) and composes ONE small ops summary doc for visibility.

NOT YET REGISTERED AS A RUNNING PROCESS -- ProcSpec m37_ingame_enrichment is
added to supervisor.stack_specs additively; a supervisor RESTART is required
for it to actually start (restart pending, per the brief).

Heartbeat: m37_ingame_enrichment -> data/cache/daemon_heartbeats/m37_ingame_enrichment.txt
Cadence: DEFAULT_INTERVAL_SEC = 30 s.
Repo-internal only; ASCII only; <=300 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/ingame/test_ingame_enrichment_runner.py -q
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("ingame_enrichment_runner")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SUMMARY_OUT = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_enrichment.json"

HEARTBEAT_COMPONENT = "m37_ingame_enrichment"
DEFAULT_INTERVAL_SEC = 30.0


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M37 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_enrichment heartbeat skipped: %s", exc)


def _run_fotmob() -> Dict[str, Any]:
    """One soccer-live fotmob poll pass. Returns its own summary dict."""
    from domains.soccer.ingame_fotmob import poll_once
    return poll_once()


def _run_gumbo() -> Dict[str, Any]:
    """One MLB GUMBO poll pass over today's live games. Returns its own report
    dict. Best-effort id-join context via game_pk_bridge_live is attached
    additively (never blocks the poll if the bridge build fails)."""
    from scripts.platformkit.ingame.gumbo_mlb_poller import run_once
    report = run_once()
    try:
        from scripts.platformkit.ingame.game_pk_bridge_live import build_bridge, summarize
        from scripts.platformkit.ingame.slate_date import slate_date
        bridge_rows = build_bridge(slate_date())
        report["bridge_summary"] = summarize(bridge_rows)
    except Exception as exc:  # noqa: BLE001 -- bridge context is additive, never fatal
        logger.debug("ingame_enrichment gumbo bridge context failed: %s", exc)
        report["bridge_summary"] = {"error": str(exc)}
    return report


# S105: the poller's cross-tick state lives HERE because this runner is the only
# production caller of poll_once. It used to pass state=None every tick, so the sticky
# active-ticker list, the per-ticker miss counts, the prev snapshots stale_quote_flag is
# computed against and the trade watermarks were all discarded 30 s after being built --
# the 2026-07-11 sticky-retention fix therefore never actually ran in production. Measured
# on the resulting local archive: 98.3 pct of MLB tickers (227 of 231) had their LAST
# capture BEFORE their own first pitch, and the trades sidecar re-persisted the same tape
# 29.2x (1,060,539 rows for 36,369 distinct trades). Bounded by max_active_per_sport.
_BOOK_DEPTH_STATE: Dict[str, Any] = {}


def _run_book_depth() -> Dict[str, Any]:
    """One bounded (single-tick) book-depth poll across mlb+wnba. Returns its
    own {kalshi, polymarket} summary dict. State is threaded across ticks via
    _BOOK_DEPTH_STATE so a ticker stays tracked through its own game day."""
    from scripts.platformkit.ingame.ingame_book_depth_poller import poll_once
    return poll_once(sports=["mlb", "wnba"], state=_BOOK_DEPTH_STATE)


# Retention is a periodic housekeeping pass, not a per-tick one (a directory walk every
# 30s is wasteful for a 30-day active window) -- gated to fire every _RETENTION_EVERY_N
# ticks (default: 1 hour at the 30s cadence). ARCHIVES only (see sidecar_retention.py),
# never deletes; a failure here can never sink the enrichment tick (LANE 1's fotmob/
# gumbo/book_depth sources are unaffected either way).
_RETENTION_EVERY_N_TICKS = 120


def _run_retention() -> Dict[str, Any]:
    """One retention enforcement pass over DEFAULT_POLICY (all 5 sidecar trees).
    Archives stale files (age/byte budget); never deletes. Returns enforce_all's
    summary dict."""
    from scripts.platformkit.ingame.sidecar_retention import enforce_all
    return enforce_all()


def _compose(fotmob: Dict[str, Any], gumbo: Dict[str, Any],
            book_depth: Dict[str, Any], now_iso: str) -> Dict[str, Any]:
    return {
        "component": "ingame_enrichment", "generated_at": now_iso,
        "fotmob": fotmob, "gumbo": gumbo, "book_depth": book_depth,
        "honest_note": ("capture/measurement only; no bet/decision path touched, "
                        "no flag flipped, no data/registry/ write"),
        "edge_claimed": False,
    }


def tick(*, now: float, tick_index: int = 0,
         fotmob_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         gumbo_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         book_depth_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         retention_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """One enrichment tick: fotmob -> gumbo -> book-depth -> composed doc ->
    heartbeat. Each source is try/except-isolated; a raising source degrades to
    an {"error": str} entry for that source only, never kills the tick or blocks
    a sibling source. Never raises.

    Retention is a PERIODIC pass (every _RETENTION_EVERY_N_TICKS, keyed off
    *tick_index*), additive + failure-isolated the same way as the 3 sources: a
    raising retention pass degrades to {"error": str} and never blocks/kills the
    tick. Absent from the doc entirely on ticks it does not run (no "skipped"
    noise every 30s)."""
    _fotmob = fotmob_fn if fotmob_fn is not None else _run_fotmob
    _gumbo = gumbo_fn if gumbo_fn is not None else _run_gumbo
    _book_depth = book_depth_fn if book_depth_fn is not None else _run_book_depth
    _retention = retention_fn if retention_fn is not None else _run_retention

    try:
        fotmob_summary = _fotmob()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_enrichment fotmob step raised: %s", exc)
        fotmob_summary = {"error": str(exc)}
    try:
        gumbo_summary = _gumbo()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_enrichment gumbo step raised: %s", exc)
        gumbo_summary = {"error": str(exc)}
    try:
        book_depth_summary = _book_depth()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_enrichment book_depth step raised: %s", exc)
        book_depth_summary = {"error": str(exc)}

    now_iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
    doc = _compose(fotmob_summary, gumbo_summary, book_depth_summary, now_iso)
    if tick_index >= 0 and tick_index % _RETENTION_EVERY_N_TICKS == 0:
        try:
            doc["retention"] = _retention()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingame_enrichment retention step raised: %s", exc)
            doc["retention"] = {"error": str(exc)}
    try:
        _SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = _SUMMARY_OUT.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
        os.replace(str(tmp), str(_SUMMARY_OUT))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_enrichment summary write failed: %s", exc)
    _beat(now)
    return doc


def _intertick_wait(interval_sec: float, last_doc: Dict[str, Any],
                    sleep_fn: Callable[[float], None]) -> None:
    """Spend the inter-tick wait fast-polling MLB GUMBO (run_live_window, CV_GUMBO_LIVE_SEC
    cadence) when the last tick saw >=1 live MLB game; plain sleep otherwise (idle
    unchanged). A raising live window degrades to a plain sleep -- never raises."""
    try:
        n_live = int(((last_doc or {}).get("gumbo") or {}).get("n_live_games") or 0)
    except (TypeError, ValueError):
        n_live = 0
    if n_live <= 0:
        sleep_fn(float(interval_sec))
        return
    try:
        from scripts.platformkit.ingame.gumbo_mlb_poller import run_live_window
        run_live_window(window_sec=float(interval_sec), sleep_fn=sleep_fn)
    except Exception as exc:  # noqa: BLE001 -- capture-only; degrade, never sink the loop
        logger.warning("ingame_enrichment gumbo live window raised: %s", exc)
        sleep_fn(float(interval_sec))


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the enrichment loop forever (or max_ticks). Never raises out.
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
        doc = tick(now=now, tick_index=ticks)
        errs = [k for k in ("fotmob", "gumbo", "book_depth") if "error" in (doc.get(k) or {})]
        print("%s | tick=%d errors=%s" % (HEARTBEAT_COMPONENT, ticks, ",".join(errs) or "none"),
              flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _intertick_wait(float(interval_sec), doc, _sleep)
        except Exception:  # noqa: BLE001
            break
    return ticks


def _main() -> int:  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(
        description="Supervised combined wave-10 enrichment tick (M37): fotmob + "
                    "gumbo (mlb, id-bridged) + book-depth, every --interval seconds. "
                    "Capture/measurement only, no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    print("ingame_enrichment_runner | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("ingame_enrichment_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
