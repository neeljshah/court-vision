"""scripts.platformkit.ingame.ingame_pred_tick_runner -- supervised M11 entry.

MEASUREMENT-ONLY daemon: per-live-game in-game prediction refresh tick.
Every 20 s (live) / 120 s (idle) writes live_pred_<game_id>.json per game.

HONEST RAILS:
  - CLV is INSUFFICIENT_DATA when fewer than MIN_CLV_PAIRS (5) graded in-play
    pairs exist; never fabricated.
  - Absent live games -> live_pred_UNAVAILABLE.json sentinel (stale-never-green).
  - UNITS not $: no dollar P&L field anywhere.
  - No flag flip; no data/registry/ write; no real-money action.
  - Injectable clock/sleep/max_ticks for offline tests.

Heartbeat: m11_ingame_pred_tick -> data/cache/daemon_heartbeats/m11_ingame_pred_tick.txt
Output  : data/frontend/ingame/live_pred_<game_id>.json (one per live game).
          data/frontend/ingame/live_pred_UNAVAILABLE.json (when slate is quiet).

stdlib + repo-internal; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("ingame_pred_tick_runner")

HEARTBEAT_COMPONENT = "m11_ingame_pred_tick"
_REPO = pathlib.Path(__file__).resolve().parents[3]
_INGAME_DIR = _REPO / "data" / "frontend" / "ingame"
_GRADE_DIR = _REPO / "data" / "cache" / "ingame_grade"

LIVE_INTERVAL_SEC = 20.0
IDLE_INTERVAL_SEC = 120.0
MIN_CLV_PAIRS = 5   # below this: clv_status=INSUFFICIENT_DATA, never fabricated

_HONEST_NOTE = (
    "MEASUREMENT-ONLY ingame_pred_tick M11. "
    "clv_status=INSUFFICIENT_DATA when <5 graded in-play pairs exist. "
    "UNITS not $; calibration not edge; real-money default-DENY."
)
_BAD_KEYS = ("dollar_pnl", "pnl_usd", "roi_usd", "stake_usd")


# -- heartbeat ----------------------------------------------------------------

def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M11 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_pred_tick heartbeat skipped: %s", exc)


# -- CLV pair counting --------------------------------------------------------

def _count_grade_pairs(game_id: str, sport: str = "nba",
                       grade_dir: Optional[pathlib.Path] = None) -> int:
    """Count rows with both model_prob+market_prob from grade JSONL. 0 on error."""
    base = pathlib.Path(grade_dir) if grade_dir is not None else _GRADE_DIR
    p = base / sport / ("%s.jsonl" % game_id)
    if not p.exists():
        return 0
    n = 0
    try:
        with p.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict) and (
                        rec.get("model_prob") is not None
                        and rec.get("market_prob") is not None):
                    n += 1
    except Exception as exc:  # noqa: BLE001
        logger.debug("_count_grade_pairs(%s): %s", game_id, exc)
    return n


def clv_status_from_pairs(n_pairs: int) -> str:
    """INSUFFICIENT_DATA below MIN_CLV_PAIRS; never a fabricated verdict."""
    return "INSUFFICIENT_DATA" if n_pairs < MIN_CLV_PAIRS else "graded"


# -- live-game discovery ------------------------------------------------------

def _live_game_ids() -> List[str]:
    """game_ids currently live from ingame snapshot _latest.json files. Never raises."""
    ids: List[str] = []
    try:
        if not _INGAME_DIR.exists():
            return ids
        for sport_dir in _INGAME_DIR.iterdir():
            if not sport_dir.is_dir():
                continue
            latest = sport_dir / "_latest.json"
            if not latest.exists():
                continue
            try:
                doc = json.loads(latest.read_text(encoding="utf-8"))
                gid = doc.get("game_id") or doc.get("gameId") or ""
                st = str(doc.get("status", "")).lower()
                if gid and st in ("live", "in_progress", "inprogress"):
                    ids.append(str(gid))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        logger.debug("live_game_ids scan failed: %s", exc)
    return ids


# -- compose + atomic write ---------------------------------------------------

def _compose_game(game_id: str, now: float) -> Dict[str, Any]:
    """Compose prediction for one game. Degrades to DEGRADED envelope on error."""
    doc: Dict[str, Any] = {}
    try:
        from predict_service.ingame_compose import compose_default  # type: ignore
        doc = dict(compose_default("nba", game_id))
    except Exception as exc:  # noqa: BLE001
        logger.debug("compose_default(%s) failed: %s", game_id, exc)
        doc = {"game_id": game_id, "generated_at": now,
               "status": "degraded", "win_prob": None}

    doc.update({"game_id": game_id, "generated_at": now,
                "honest_note": _HONEST_NOTE, "edge_claimed": False})

    n = _count_grade_pairs(game_id)
    doc["n_grade_pairs"] = n
    # HONESTY: INSUFFICIENT_DATA if either compose or pair-count says so.
    compose_clv = str(doc.get("clv_status") or "INSUFFICIENT_DATA")
    clv = clv_status_from_pairs(n)
    doc["clv_status"] = "INSUFFICIENT_DATA" if (
        compose_clv == "INSUFFICIENT_DATA" or clv == "INSUFFICIENT_DATA") else clv
    for k in _BAD_KEYS:
        doc.pop(k, None)
    try:
        from scripts.platformkit.ingame.aci_stream_shim import apply_to_document
        doc = apply_to_document(doc, "nba")
    except Exception as exc:  # noqa: BLE001
        logger.debug("ACI serve shim skipped: %s", exc)
    return doc


def _output_path(game_id: str) -> pathlib.Path:
    return _INGAME_DIR / ("live_pred_%s.json" % game_id)


def _atomic_write(path: pathlib.Path, doc: Dict[str, Any]) -> bool:
    """Atomically write JSON. Returns True on success. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("atomic write failed: %s", exc)
        return False


def _write_unavailable(now: float, *, out_path: Optional[pathlib.Path] = None) -> None:
    """Write UNAVAILABLE sentinel when no live games. Stale-never-green. Never raises."""
    path = out_path or (_INGAME_DIR / "live_pred_UNAVAILABLE.json")
    _atomic_write(path, {
        "status": "UNAVAILABLE", "generated_at": now, "n_live_games": 0,
        "clv_status": "INSUFFICIENT_DATA", "edge_claimed": False,
        "honest_note": (
            "No live games found. NBA offseason or between games. "
            "CLV=INSUFFICIENT_DATA -- no liquid in-play prices. "
            "MEASUREMENT-ONLY; UNITS not $; no edge claimed."
        ),
    })


# -- tick ---------------------------------------------------------------------

def tick(*, now: float,
         game_ids_fn: Optional[Callable[[], List[str]]] = None,
         compose_fn: Optional[Callable[[str, float], Dict[str, Any]]] = None,
         out_path_fn: Optional[Callable[[str], pathlib.Path]] = None,
         ) -> Tuple[List[str], bool]:
    """One tick: discover live games -> compose -> write -> heartbeat. Never raises.

    Returns (game_ids_processed, is_live_games_found).
    When no live games, writes live_pred_UNAVAILABLE.json (honest sentinel).
    """
    _ids_fn = game_ids_fn or _live_game_ids
    _compose = compose_fn or _compose_game
    _out = out_path_fn or _output_path
    try:
        from scripts.platformkit.ingame.aci_stream_shim import update_stream
        update_stream("nba")
    except Exception as exc:  # noqa: BLE001
        logger.debug("ACI stream update skipped: %s", exc)

    try:
        game_ids = _ids_fn()
    except Exception as exc:  # noqa: BLE001
        logger.debug("game_ids_fn raised: %s", exc)
        game_ids = []

    if not game_ids:
        _write_unavailable(now)

    for gid in game_ids:
        try:
            doc = _compose(gid, now)
            for k in _BAD_KEYS:         # safety strip regardless of compose source
                doc.pop(k, None)
            _atomic_write(_out(gid), doc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("game %s failed: %s", gid, exc)

    _beat(now)
    return game_ids, bool(game_ids)


# -- run loop -----------------------------------------------------------------

def run(*, game_ids_fn: Optional[Callable[[], List[str]]] = None,
        compose_fn: Optional[Callable[[str, float], Dict[str, Any]]] = None,
        out_path_fn: Optional[Callable[[str], pathlib.Path]] = None,
        live_interval_sec: float = LIVE_INTERVAL_SEC,
        idle_interval_sec: float = IDLE_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run tick loop (forever or max_ticks). Never raises out. Returns tick count.

    Phase-aware: LIVE_INTERVAL_SEC when games are live, IDLE_INTERVAL_SEC otherwise.
    MEASUREMENT-ONLY: writes live_pred_*.json + heartbeat; no flag flip; no $.
    """
    import time as _time
    _clock = clock or _time.time
    _sleep = sleep or _time.sleep
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
        _, has_live = tick(now=now, game_ids_fn=game_ids_fn,
                           compose_fn=compose_fn, out_path_fn=out_path_fn)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(live_interval_sec if has_live else idle_interval_sec)
        except Exception:  # noqa: BLE001
            break
    return ticks


# -- CLI ----------------------------------------------------------------------

def _main() -> int:  # pragma: no cover
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="In-game prediction tick daemon (M11): 20 s live / 120 s idle. "
                    "MEASUREMENT-ONLY: CLV=INSUFFICIENT_DATA <5 pairs; no $ field.")
    p.add_argument("--live-interval", type=float, default=LIVE_INTERVAL_SEC)
    p.add_argument("--idle-interval", type=float, default=IDLE_INTERVAL_SEC)
    a = p.parse_args()
    print("ingame_pred_tick_runner | component=%s out=%s"
          % (HEARTBEAT_COMPONENT, _INGAME_DIR), flush=True)
    try:
        run(live_interval_sec=a.live_interval, idle_interval_sec=a.idle_interval)
    except KeyboardInterrupt:
        print("ingame_pred_tick_runner | stopped", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = [
    "HEARTBEAT_COMPONENT", "LIVE_INTERVAL_SEC", "IDLE_INTERVAL_SEC",
    "MIN_CLV_PAIRS", "clv_status_from_pairs", "_count_grade_pairs",
    "tick", "run",
]
