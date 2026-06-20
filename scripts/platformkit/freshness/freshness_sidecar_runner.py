"""scripts.platformkit.freshness.freshness_sidecar_runner -- per-sport freshness writer.

W-FRESHNESS-SIDECAR (backend lane, QA iter5 2026-06-20). Fixes /api/freshness
all-missing P1: feed_status reads data/frontend/<sport>/_freshness.json which is
never written, so every sport reads status=down/missing.

Each tick:
  1. Reads the latest capture per sport from:
       data/cache/line_history/<sport>/_freshness.json  (line snapshot daemon)
       data/frontend/predict_service/<sport>/latest.json (predict service store)
  2. Picks the freshest source_ts; writes data/frontend/<sport>/_freshness.json
     atomically (tmp + os.replace) with {status, generated_at, age_sec, source_ts,
     runner_heartbeat_ts, sources, ok, honest_note}.
  3. Degrades to status=unavailable when a sport has no feed.

HONESTY: no $ field; calibration not edge; MEASUREMENT only; no flag flip.
STALE-NEVER-GREEN: missing/old source_ts -> status unavailable/stale, never fresh.
ok=True ONLY when status=='fresh'.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_freshness_sidecar_runner.py -q
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

DEFAULT_SPORTS: tuple = ("nba", "mlb", "soccer", "soccer_intl", "tennis")
DEFAULT_MAX_AGE_SEC: float = 900.0   # 15 min -- matches line_snapshot_daemon SLA
DEFAULT_INTERVAL_SEC: int = 60
HEARTBEAT_KEY = "runner_heartbeat_ts"
HONEST_NOTE = (
    "Feed freshness sidecar. status=fresh ONLY when source_ts is recent. "
    "Missing/absent source -> status=unavailable (never fresh). "
    "No $ edge is claimed; calibration not edge."
)

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
_DEFAULT_LINE_ROOT = _REPO_ROOT / "data" / "cache" / "line_history"
_DEFAULT_PREDICT_ROOT = _REPO_ROOT / "data" / "frontend" / "predict_service"
_DEFAULT_OUT_ROOT = _REPO_ROOT / "data" / "frontend"


def _utcnow(now: Optional[datetime] = None) -> datetime:
    if now is not None:
        dt = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _parse_iso(ts: Any) -> Optional[datetime]:
    """ISO-8601 -> UTC datetime, or None. Never raises."""
    if not ts:
        return None
    try:
        s = str(ts).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON file as a dict, or None. Never raises."""
    try:
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as fh:
            obj = json.load(fh)
        return obj if isinstance(obj, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    """Write payload as JSON atomically (tmp + os.replace). Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(str(tmp), str(path))
    except Exception as exc:  # noqa: BLE001
        logger.warning("freshness_sidecar_runner: write %s failed: %s", path, exc)


def _line_ts(line_root: Path, sport: str) -> Optional[str]:
    """source_as_of from line-snapshot sidecar, or None."""
    d = _read_json(line_root / sport.lower() / "_freshness.json")
    if d is None:
        return None
    return d.get("source_as_of") or d.get("poll_at") or None


def _predict_ts(predict_root: Path, sport: str) -> Optional[str]:
    """generated_at from predict-service latest.json (ok status only), or None."""
    d = _read_json(predict_root / sport.lower() / "latest.json")
    if d is None:
        return None
    if str(d.get("status", "")).lower() != "ok":
        return None
    return d.get("generated_at") or None


def measure_sport(
    sport: str,
    *,
    now: Optional[datetime] = None,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    line_root: Optional[Path] = None,
    predict_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Measure one sport's freshness from both capture sources. NEVER raises.

    Returns: {status, generated_at, age_sec, source_ts, sources, ok, honest_note}
    status = 'fresh' | 'stale' | 'unavailable'
    ok = True ONLY when status == 'fresh'.
    """
    nowdt = _utcnow(now)
    lr = line_root if line_root is not None else _DEFAULT_LINE_ROOT
    pr = predict_root if predict_root is not None else _DEFAULT_PREDICT_ROOT

    lt: Optional[str] = None
    pt: Optional[str] = None
    try:
        lt = _line_ts(lr, sport)
    except Exception as exc:  # noqa: BLE001
        logger.debug("measure_sport(%s) line failed: %s", sport, exc)
    try:
        pt = _predict_ts(pr, sport)
    except Exception as exc:  # noqa: BLE001
        logger.debug("measure_sport(%s) predict failed: %s", sport, exc)

    # Pick the most recent timestamp across both sources.
    best_ts: Optional[str] = None
    best_dt: Optional[datetime] = None
    for ts in (lt, pt):
        if ts is None:
            continue
        dt = _parse_iso(ts)
        if dt is None:
            continue
        if best_dt is None or dt > best_dt:
            best_dt, best_ts = dt, ts

    age_sec: Optional[float] = (
        max(0.0, (nowdt - best_dt).total_seconds()) if best_dt is not None else None
    )

    if best_ts is None or age_sec is None:
        status = "unavailable"
    elif age_sec <= max_age_sec:
        status = "fresh"
    else:
        status = "stale"

    return {
        "status": status,
        "generated_at": nowdt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "age_sec": round(age_sec, 1) if age_sec is not None else None,
        "source_ts": best_ts,
        "sources": {"line": lt, "predict": pt},
        "ok": status == "fresh",
        "honest_note": HONEST_NOTE,
    }


def tick(
    sports: Sequence[str] = DEFAULT_SPORTS,
    *,
    now: Optional[datetime] = None,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    line_root: Optional[Path] = None,
    predict_root: Optional[Path] = None,
    out_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Measure all sports and atomically write data/frontend/<sport>/_freshness.json.

    Adds a heartbeat key so the supervisor can detect a hung runner.
    NEVER raises; per-sport failures degrade to unavailable.
    Returns list of per-sport measurement dicts.
    """
    nowdt = _utcnow(now)
    heartbeat = nowdt.strftime("%Y-%m-%dT%H:%M:%SZ")
    outr = out_root if out_root is not None else _DEFAULT_OUT_ROOT

    results: List[Dict[str, Any]] = []
    for sport in sports:
        sport_s = str(sport).lower()
        try:
            m = measure_sport(sport_s, now=nowdt, max_age_sec=max_age_sec,
                              line_root=line_root, predict_root=predict_root)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tick: measure_sport(%s) failed: %s", sport_s, exc)
            m = {"status": "unavailable", "generated_at": heartbeat,
                 "age_sec": None, "source_ts": None,
                 "sources": {"line": None, "predict": None},
                 "ok": False, "honest_note": HONEST_NOTE}

        m[HEARTBEAT_KEY] = heartbeat
        _atomic_write(outr / sport_s / "_freshness.json", m)
        results.append({"sport": sport_s, **m})
        logger.debug("tick: %s -> %s age=%s", sport_s, m["status"], m.get("age_sec"))

    return results


def serve_forever(
    interval: int = DEFAULT_INTERVAL_SEC,
    *,
    sports: Sequence[str] = DEFAULT_SPORTS,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    line_root: Optional[Path] = None,
    predict_root: Optional[Path] = None,
    out_root: Optional[Path] = None,
    sleep_fn=None,
    max_ticks: Optional[int] = None,
    now: Optional[datetime] = None,
) -> None:
    """Run tick on a fixed interval. NEVER raises out of a tick.

    Inject sleep_fn, max_ticks, and now for testing (no real sleep, no real clock).
    """
    _sleep = sleep_fn if sleep_fn is not None else time.sleep
    n = 0
    while True:
        try:
            tick(sports=sports, now=now, max_age_sec=max_age_sec,
                 line_root=line_root, predict_root=predict_root, out_root=out_root)
        except Exception as exc:  # noqa: BLE001
            logger.error("serve_forever: tick failed: %s", exc)
        n += 1
        if max_ticks is not None and n >= max_ticks:
            return
        try:
            _sleep(max(1, int(interval)))
        except Exception:  # noqa: BLE001
            pass


def _main() -> int:
    import argparse
    p = argparse.ArgumentParser(
        description="Freshness sidecar runner -- writes per-sport _freshness.json")
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SEC)
    p.add_argument("--sports", default=",".join(DEFAULT_SPORTS))
    p.add_argument("--max-age", type=float, default=DEFAULT_MAX_AGE_SEC)
    a = p.parse_args()
    sport_list = [s.strip() for s in a.sports.split(",") if s.strip()]
    print("freshness_sidecar_runner | started sports=%s interval=%ds"
          % (",".join(sport_list), a.interval), flush=True)
    try:
        serve_forever(interval=a.interval, sports=sport_list, max_age_sec=a.max_age)
    except KeyboardInterrupt:
        print("freshness_sidecar_runner | stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
