"""scripts.platformkit.props.props_pred_tick_runner -- supervised M13 entry.

MEASUREMENT-ONLY daemon: every 300 s re-scores prop lines -> props_snapshot.json.
HONEST RAILS: UNITS not $; UNAVAILABLE only when genuinely no pregame games;
CALIBRATION not edge; no flag flip; no data/registry/ write; no real-money action.
ANTI-FLICKER: transient-empty tick with pregame games -> model-only synth fill.
HEARTBEAT: start beat + background 300 s beater during slow scoring (700+ props
can exceed the 660 s supervisor fresh threshold without the background thread).
Injectable clock/sleep/score_fn/synth_fill_fn/pregame_fn/max_ticks for tests.

Heartbeat: m13_props_pred_tick -> data/cache/daemon_heartbeats/m13_props_pred_tick.txt
Cadence: DEFAULT_INTERVAL_SEC = 300 s. Output: data/frontend/props_snapshot.json.
stdlib + repo-internal; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("props_pred_tick_runner")

HEARTBEAT_COMPONENT = "m13_props_pred_tick"

_REPO = pathlib.Path(__file__).resolve().parents[3]
_OUTPUT_PATH = _REPO / "data" / "frontend" / "props_snapshot.json"

DEFAULT_INTERVAL_SEC = 300.0


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M13 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("props_pred_tick heartbeat skipped: %s", exc)


def _beat_during_scoring(stop_event: threading.Event, now_epoch: float,
                         interval: float = 300.0) -> None:
    """Daemon thread: beat every interval s until stop_event set."""
    while not stop_event.wait(timeout=interval):
        _beat(now_epoch)


def _strip_dollar(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip any dollar P&L field that could ever appear. UNITS not $."""
    banned = ("dollar_pnl", "pnl_usd", "usd", "pnl", "roi")
    return [{k: v for k, v in r.items() if k not in banned} for r in rows]


def _score_props_bounded(now: float):
    """Build the BOUNDED/RANKED player-prop CARD set + the honest "N more" tally via
    prop_cards.build_bounded_prop_cards (SLOW full board ONCE; ALL priced + top-N
    reliable model-only per sport, cap 50; model-only carry NO edge/CLV; priced carry
    edge_vs_market, a prob diff NOT $; past-dated dropped). Returns (rows, n_more);
    rows == [] ONLY when genuinely nothing live. Never raises; strips any $ field."""
    try:
        from scripts.platformkit.bestbets.prop_cards import (  # noqa: PLC0415
            build_bounded_prop_cards)
        cards, n_more = build_bounded_prop_cards(now=now)
        return _strip_dollar(list(cards)), dict(n_more or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("props_pred_tick build_bounded_prop_cards unavailable: %s", exc)
        return [], {}


def _score_props(now: float) -> List[Dict[str, Any]]:
    """Bounded player-prop card rows (back-compat: drops the "N more" tally)."""
    rows, _n_more = _score_props_bounded(now)
    return rows


def _synth_only_fill(now: float):
    """Model-only synth fill (NO feed): cheap honest recompute for a transient empty
    tick while pregame games exist. Cannot 429. (rows, n_more). Never raises."""
    try:
        from scripts.platformkit.bestbets.prop_cards import (  # noqa: PLC0415
            build_synth_only_prop_cards)
        cards, n_more = build_synth_only_prop_cards(now=now)
        return _strip_dollar(list(cards)), dict(n_more or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("props_pred_tick synth-only fill unavailable: %s", exc)
        return [], {}


def _pregame_games_exist(now: float) -> bool:
    """True when >=1 sport has synthesizable pregame props on disk (cheap NO-FEED
    'board should not be empty' check). Never raises -> False."""
    try:
        from scripts.platformkit.bestbets.prop_cards import (  # noqa: PLC0415
            pregame_games_exist)
        return bool(pregame_games_exist(now=now))
    except Exception as exc:  # noqa: BLE001
        logger.debug("props_pred_tick pregame check unavailable: %s", exc)
        return False


def _make_envelope(rows: List[Dict[str, Any]], now: float, *,
                   ok: bool,
                   n_more: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Wrap prop rows in a standard output envelope."""
    overall = "ok" if (ok and rows) else ("UNAVAILABLE" if not rows else "degraded")
    return {
        "generated_at": now,
        "overall": overall,
        "card_count": len(rows),
        "n_more_model_only": dict(n_more or {}),
        "rows": rows,
        "honest_note": (
            "MEASUREMENT-ONLY props_pred_tick M13. Rows = BOUNDED player-prop "
            "cards (market_type=prop): ALL priced props + top-N reliable model-only "
            "per sport (n_more_model_only = capped count). MODEL-ONLY rows "
            "(model_only=True) carry NO edge/CLV; PRICED rows carry edge_vs_market "
            "(a prob diff, NOT $). UNITS not $; past-dated boards dropped; "
            "UNAVAILABLE only when there are genuinely no pregame games. "
            "calibration not edge."
        ),
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def _atomic_write(path: pathlib.Path, doc: Dict[str, Any]) -> bool:
    """Atomically write JSON to path. Returns True on success. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("props_pred_tick atomic write failed: %s", exc)
        return False


def _write_prop_cards_cache(rows: List[Dict[str, Any]], now: float,
                            n_more: Dict[str, int]) -> None:
    """Write the decoupled prop-card cache the FAST m10 board reads. The slow build
    runs HERE (300 s) and is cached so the 120 s m10 board never recomputes inline
    (which hung >240 s). Never raises."""
    try:
        from scripts.platformkit.bestbets import prop_cards_cache  # noqa: PLC0415
        prop_cards_cache.write(rows, now, n_more_model_only=n_more)
    except Exception as exc:  # noqa: BLE001
        logger.debug("props_pred_tick prop_cards_cache write skipped: %s", exc)


def tick(*, now: float,
         score_fn: Optional[Callable[[float], List[Dict[str, Any]]]] = None,
         output_path: Optional[pathlib.Path] = None,
         write_cache: bool = True,
         synth_fill_fn: Optional[Callable[[float], Any]] = None,
         pregame_fn: Optional[Callable[[float], bool]] = None) -> Dict[str, Any]:
    """One props tick: score (slow, bounded) -> atomic write snapshot + prop-card
    cache -> heartbeat. Never raises. UNAVAILABLE only when genuinely no pregame
    games. Heartbeat advances regardless of score outcome. ALSO writes the decoupled
    prop_cards_cache.json the fast m10 board reads (write_cache off for isolated
    tests). ANTI-FLICKER guard: a 0-card tick with pregame games on disk RECOMPUTES
    a model-only synth-only fill (no feed) and serves it -- see module docstring.
    synth_fill_fn / pregame_fn injectable for tests; the guard is SKIPPED when
    score_fn is injected (raw-path determinism)."""
    path = output_path if output_path is not None else _OUTPUT_PATH
    _synth = synth_fill_fn if synth_fill_fn is not None else _synth_only_fill
    _pregame = pregame_fn if pregame_fn is not None else _pregame_games_exist

    # Start beat + background beater every 300 s during scoring (scoring 700+ props
    # can exceed the 660 s fresh threshold without the extra beats).
    _beat(now)
    _stop_beat = threading.Event()
    _beater = threading.Thread(target=_beat_during_scoring,
                               args=(_stop_beat, now, 300.0), daemon=True)
    _beater.start()

    n_more: Dict[str, int] = {}
    try:
        if score_fn is not None:
            rows = list(score_fn(now))
        else:
            rows, n_more = _score_props_bounded(now)
        ok = True
    except Exception as exc:  # noqa: BLE001
        logger.debug("props_pred_tick score raised: %s", exc)
        rows = []
        n_more = {}
        ok = False
    finally:
        _stop_beat.set()  # stop background beater regardless of outcome

    # ANTI-FLICKER: a transient empty while pregame games exist on disk -> honest
    # model-only synth-only recompute (no feed). Skipped for the injected raw path.
    if not rows and score_fn is None:
        try:
            if _pregame(now):
                fill_rows, fill_more = _synth(now)
                if fill_rows:
                    logger.debug("props_pred_tick: transient empty with pregame "
                                 "games; filled %d model-only synth cards",
                                 len(fill_rows))
                    rows = fill_rows
                    n_more = fill_more
                    ok = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("props_pred_tick synth-only guard skipped: %s", exc)

    envelope = _make_envelope(rows, now, ok=ok, n_more=n_more)
    _atomic_write(path, envelope)
    if write_cache:
        _write_prop_cards_cache(rows, now, n_more)
    _beat(now)
    return envelope


# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------

def run(*, score_fn: Optional[Callable[[float], List[Dict[str, Any]]]] = None,
        output_path: Optional[pathlib.Path] = None,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the props prediction tick loop forever (or max_ticks). Never raises out.
    Everything injectable for offline tests. Returns ticks executed. MEASUREMENT-ONLY:
    props_snapshot.json + cache + heartbeat; no flag flip, no data/registry/ write,
    no $ field, no real-money action."""
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
        tick(now=now, score_fn=score_fn, output_path=output_path)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> int:  # pragma: no cover
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Supervised props prediction tick daemon (M13): every 300 s "
                    "re-scores prop lines -> props_snapshot.json. MEASUREMENT-ONLY; "
                    "UNAVAILABLE only when no pregame games; UNITS not $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between ticks (default: %(default)s).")
    a = p.parse_args()
    print("props_pred_tick_runner | started interval=%ss component=%s out=%s"
          % (a.interval, HEARTBEAT_COMPONENT, _OUTPUT_PATH), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("props_pred_tick_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "tick", "run"]
