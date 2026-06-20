"""heartbeat_sla_matrix.py -- per-service heartbeat SLA matrix (BE8-6).

Reads supervisor.stack_specs.base_specs() HEARTBEAT-kind specs + fresh_sec,
computes age_sec and pct_of_sla per daemon, writes
data/cache/ops/heartbeat_sla_matrix.json worst-first + overall rollup.
stale when age_sec >= sla_sec OR heartbeat absent (stale-never-green).
READ-ONLY; no $ field; no process started; no flag flip; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

_REPO = pathlib.Path(__file__).resolve().parents[3]
_DEFAULT_REPORT = _REPO / "data" / "cache" / "ops" / "heartbeat_sla_matrix.json"

_HONEST_NOTE = (
    "BE8-6 per-service heartbeat SLA matrix. "
    "READ-ONLY observability snapshot; stale-never-green: absent or unreadable "
    "heartbeat = stale, never ok. CALIBRATION not edge; UNITS not $; no dollar "
    "P&L field. overall=stale if any service is stale."
)

_STALE_PCT = 100.0  # age_sec >= sla_sec -> stale (tighter than warn/stale split)


# ---------------------------------------------------------------------------
# Heartbeat reading
# ---------------------------------------------------------------------------

def _parse_iso(ts: str) -> Optional[datetime]:
    """Parse ISO-8601 string to UTC datetime. Returns None on failure."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _read_age(path: Optional[pathlib.Path], now: float) -> Optional[float]:
    """Return age_sec or None (absent/corrupt -> None -> stale-never-green)."""
    if path is None or not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not raw:
        return None

    stamp: Optional[float] = None
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                val = data.get("updated_at")
                if isinstance(val, (int, float)):
                    stamp = float(val)
                elif isinstance(val, str):
                    dt = _parse_iso(val)
                    stamp = dt.timestamp() if dt else None
                if stamp is None:
                    ao = data.get("as_of")
                    if isinstance(ao, str):
                        dt = _parse_iso(ao)
                        stamp = dt.timestamp() if dt else None
        except (json.JSONDecodeError, ValueError):
            stamp = None
    if stamp is None:
        dt = _parse_iso(raw)
        if dt is not None:
            stamp = dt.timestamp()
    if stamp is None:
        return None
    return max(0.0, now - stamp)


# ---------------------------------------------------------------------------
# SLA row builder
# ---------------------------------------------------------------------------

def _build_row(name: str, sla_sec: float, hb_path_raw: Optional[str], now: float) -> Dict[str, Any]:
    """Build one SLA matrix row. Never raises."""
    path: Optional[pathlib.Path] = None
    if hb_path_raw is not None:
        p = pathlib.Path(str(hb_path_raw))
        path = p if p.is_absolute() else _REPO / p

    age = _read_age(path, now)
    pct_of_sla: Optional[float] = (
        round((age / sla_sec) * 100.0, 2) if (age is not None and sla_sec > 0) else None
    )
    # stale when age >= sla or heartbeat absent (stale-never-green)
    stale = (age is None) or (age >= sla_sec)

    return {
        "name": name,
        "sla_sec": sla_sec,
        "age_sec": round(age, 1) if age is not None else None,
        "pct_of_sla": pct_of_sla,
        "stale": stale,
        "hb_path": str(path) if path is not None else None,
    }


# stale first; within stale, absent (inf) before measurable worst-pct
def _sort_key(row: Dict[str, Any]) -> tuple:
    pct = row["pct_of_sla"]
    return (0 if row["stale"] else 1, -(pct if pct is not None else float("inf")))


def _load_specs_from_stack() -> List[Dict[str, Any]]:
    """Return HEARTBEAT-kind specs from stack_specs.base_specs() or []."""
    try:
        from supervisor.stack_specs import base_specs  # type: ignore
        from supervisor.manifest import HEARTBEAT  # type: ignore
        result: List[Dict[str, Any]] = []
        for spec in base_specs():
            rd = getattr(spec, "readiness", None)
            if rd is None:
                continue
            if getattr(rd, "kind", None) != HEARTBEAT:
                continue
            hb = getattr(rd, "heartbeat_path", None)
            fresh = getattr(rd, "fresh_sec", 120.0)
            if hb is None:
                continue
            result.append({
                "name": spec.name,
                "sla_sec": float(fresh),
                "hb_path": str(hb),
            })
        return result
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Atomic write helper
# ---------------------------------------------------------------------------

def _atomic_write_json(path: pathlib.Path, doc: Dict[str, Any]) -> bool:
    """Write *doc* as ASCII JSON to *path* atomically. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_sla_matrix(
    specs: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    report_path: Optional[pathlib.Path] = None,
    clock: Optional[Callable[[], float]] = None,
    write_report: bool = True,
) -> Dict[str, Any]:
    """SLA matrix: per-service age+pct_of_sla, worst-first, overall rollup.

    specs: list of {"name","sla_sec","hb_path"} or None (loads from stack_specs).
    Returns dict with scanned_at, rows, n_stale, n_ok, overall, stale_names,
    stale_never_green, honest_note. Never raises.
    """
    try:
        return _compute_inner(
            specs=specs,
            report_path=report_path,
            clock=clock,
            write_report=write_report,
        )
    except Exception:  # noqa: BLE001
        # Absolute fallback; never raises.
        doc: Dict[str, Any] = {
            "scanned_at": (clock() if clock is not None else time.time()),
            "rows": [],
            "n_stale": 0,
            "n_ok": 0,
            "overall": "stale",
            "stale_names": [],
            "stale_never_green": True,
            "honest_note": _HONEST_NOTE,
            "_error": "unexpected error in compute_sla_matrix",
        }
        return doc


def _compute_inner(
    specs: Optional[Sequence[Dict[str, Any]]],
    *,
    report_path: Optional[pathlib.Path],
    clock: Optional[Callable[[], float]],
    write_report: bool,
) -> Dict[str, Any]:
    now = float(clock() if clock is not None else time.time())
    out_path = report_path if report_path is not None else _DEFAULT_REPORT

    raw_specs: List[Dict[str, Any]]
    if specs is None:
        raw_specs = _load_specs_from_stack()
    else:
        raw_specs = [s for s in specs if isinstance(s, dict)]

    rows: List[Dict[str, Any]] = []
    for sp in raw_specs:
        name = str(sp.get("name") or "unknown")
        sla_sec = float(sp.get("sla_sec") or 300.0)
        hb_path_raw = sp.get("hb_path")
        rows.append(_build_row(name, sla_sec, hb_path_raw, now))

    rows.sort(key=_sort_key)

    stale_names = [r["name"] for r in rows if r["stale"]]
    n_stale = len(stale_names)
    n_ok = len(rows) - n_stale
    overall = "stale" if n_stale > 0 else "ok"

    doc: Dict[str, Any] = {
        "scanned_at": now,
        "rows": rows,
        "n_stale": n_stale,
        "n_ok": n_ok,
        "overall": overall,
        "stale_names": stale_names,
        "stale_never_green": True,
        "honest_note": _HONEST_NOTE,
    }

    if write_report:
        _atomic_write_json(out_path, doc)

    return doc


# ---------------------------------------------------------------------------
# CLI shim
# ---------------------------------------------------------------------------

def _main() -> int:  # pragma: no cover -- thin CLI wrapper
    import argparse as _ap
    p = _ap.ArgumentParser(
        description=(
            "BE8-6 per-service heartbeat SLA matrix. "
            "READ-ONLY -- never mutates heartbeat or spec files."
        )
    )
    p.add_argument(
        "--report",
        default=str(_DEFAULT_REPORT),
        help="Output JSON report path (default: %(default)s)",
    )
    a = p.parse_args()
    doc = compute_sla_matrix(report_path=pathlib.Path(a.report))
    print(
        "heartbeat_sla_matrix: overall=%s n_stale=%d n_ok=%d | report -> %s"
        % (doc["overall"], doc["n_stale"], doc["n_ok"], a.report),
        flush=True,
    )
    if doc["stale_names"]:
        for name in doc["stale_names"]:
            print("  STALE: %s" % name, flush=True)
    return 1 if doc["overall"] == "stale" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["compute_sla_matrix"]
