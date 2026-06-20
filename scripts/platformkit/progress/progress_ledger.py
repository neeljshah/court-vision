"""scripts.platformkit.progress.progress_ledger -- the honest PROGRESS spine.

MEASUREMENT-ONLY aggregation of the existing on-disk artifacts into ONE current
progress SNAPSHOT, appended to an append-only JSONL time series. This is the data
spine for the honest "getting better" story. It NEVER trains, ships, recalibrates
or flips a flag, and it claims NO $ edge anywhere.

What "PROGRESS" honestly means here (and ONLY this):
  * COVERAGE  -- how many ingested data-points now carry a recorded gate VERDICT
                 (#verdicts / (#verdicts + #still-untested-backlog-items)), per sport.
  * COMPLETENESS -- parity grid GREEN + markets/verdicts exposed.
  * ENGINE READY-but-INERT -- the self-improve ratchet is proven-ready on a sealed
                 fixture but stays INERT until a HUMAN creates the PIPELINE_ENABLED
                 sentinel. engine_enabled is False while the sentinel is absent.

The model itself is STATIC: nothing in this module changes a prediction. The trend
that builds over time is COVERAGE / VERDICT-COUNT / BACKLOG-REMAINING, not a live
"accuracy climbing" line. Every snapshot stamps model_static=True so the UI cannot
imply the model is self-improving while the loop is inert.

Sources (all read-only):
  data/frontend/funnel/*.json                      -- recorded gate verdicts (+mtime)
  .planning/product/meta/improvement_backlog.json  -- ranked untested/next items (73)
  scripts.platformkit.parity_matrix                -- the coverage grid GREEN bit
  scripts.platformkit.improve.pipeline_flag        -- the human ENABLE sentinel

Append target: data/frontend/progress/progress_ledger.jsonl (idempotent same-day:
re-running on the same ET date REPLACES that date's row, never duplicates it).

INVARIANTS: build only under scripts/platformkit/; reads only (never writes
data/registry/, never flips a flag); <=300 LOC; ASCII only; no $ key; no secrets.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Any, Dict, List, Optional, Tuple

_REPO = pathlib.Path(__file__).resolve().parents[3]  # .../nba-ai-system
_FUNNEL_DIR = _REPO / "data" / "frontend" / "funnel"
_BACKLOG = _REPO / ".planning" / "product" / "meta" / "improvement_backlog.json"
_LEDGER = _REPO / "data" / "frontend" / "progress" / "progress_ledger.jsonl"

# The four+ tracked sport keys (normalized lower-case). Backlog uses mixed case
# (NBA / basketball_nba / mlb / MLB / soccer / soccer_intl / tennis / platform);
# we normalize so a sport is counted once, consistently with the funnel stems.
_SPORTS = ("nba", "mlb", "soccer", "soccer_intl", "tennis")

# Backlog categories that represent an UNTESTED ingested data-point still owed a
# verdict (the honest coverage DENOMINATOR remainder). Other categories (LOC /
# MISSING_TEST / ORPHAN) are code-hygiene, NOT data-coverage, and are excluded.
_UNTESTED_CATEGORIES = ("UNTESTED_DATA", "TIER3_ACQUISITION", "SURFACE_VALIDATED_PRIOR")

# Verdict -> bucket. Read verbatim from the funnel docs; a REJECT is a SUCCESS.
_SHIP = ("SHIP", "PROMOTE", "PASS", "GREEN", "COHERENCE")
_REJECT = ("REJECT", "REJECTED", "FAIL", "RED")


def _norm_sport(s: Optional[str]) -> Optional[str]:
    """Normalize a backlog/funnel sport token to a tracked key (or None)."""
    if not isinstance(s, str):
        return None
    t = s.strip().lower()
    if t in ("basketball_nba", "nba"):
        return "nba"
    if t in _SPORTS:
        return t
    return None  # 'platform' / unknown -> not a per-sport data point


def _read_json(path: pathlib.Path) -> Optional[Any]:
    try:
        if not path.exists():
            return None
        raw = path.read_text(encoding="ascii", errors="replace")
        return json.loads(raw) if raw.strip() else None
    except Exception:  # noqa: BLE001 -- pure offline read; never raises
        return None


def _verdict_of(doc: Dict[str, Any]) -> str:
    """Recorded gate verdict, read VERBATIM (mirrors funnel_routes._verdict_of)."""
    for key in ("verdict", "gate_verdict", "overall_verdict"):
        v = doc.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    if isinstance(doc.get("parity_overall"), str):
        return doc["parity_overall"].strip().upper()
    if doc.get("coherence") is not None:
        return "COHERENCE" if doc.get("status") == "ok" else "INSUFFICIENT_DATA"
    return "INSUFFICIENT_DATA"


def _sport_from_stem(stem: str) -> str:
    for s in ("soccer_intl", "soccer", "nba", "mlb", "tennis"):
        if stem.startswith(s):
            return s
    return "unknown"


def _bucket(verdict: str) -> str:
    if verdict in _SHIP:
        return "ship"
    if verdict in _REJECT:
        return "reject"
    return "insufficient"


def read_funnel_verdicts() -> List[Dict[str, Any]]:
    """One row {sport, verdict, bucket, at} per funnel/*.json. Torn files skipped.

    `at` is the file mtime (epoch seconds) -- the honest moment the verdict was
    recorded, used to reconstruct the historical time series. Nothing is fabricated.
    """
    rows: List[Dict[str, Any]] = []
    if not _FUNNEL_DIR.exists():
        return rows
    for path in sorted(_FUNNEL_DIR.glob("*.json")):
        doc = _read_json(path)
        if not isinstance(doc, dict):
            continue
        sport = _norm_sport(doc.get("sport")) or _sport_from_stem(path.stem)
        verdict = _verdict_of(doc)
        try:
            at = int(path.stat().st_mtime)
        except Exception:  # noqa: BLE001
            at = 0
        rows.append({"sport": sport, "verdict": verdict,
                     "bucket": _bucket(verdict), "at": at})
    return rows


def read_untested_by_sport() -> Dict[str, int]:
    """#still-untested ingested data-points per sport (coverage remainder).

    Counts ONLY backlog candidates in the UNTESTED data categories; code-hygiene
    items (LOC / MISSING_TEST / ORPHAN) are excluded -- they are not data coverage.
    """
    out: Dict[str, int] = {s: 0 for s in _SPORTS}
    doc = _read_json(_BACKLOG)
    cands = doc.get("candidates") if isinstance(doc, dict) else None
    if not isinstance(cands, list):
        return out
    for c in cands:
        if not isinstance(c, dict):
            continue
        if str(c.get("category", "")).upper() not in _UNTESTED_CATEGORIES:
            continue
        sp = _norm_sport(c.get("sport"))
        if sp is not None:
            out[sp] = out.get(sp, 0) + 1
    return out


def _backlog_totals() -> Tuple[int, int]:
    """(total_backlog_items, untested_data_remaining_across_all_sports)."""
    doc = _read_json(_BACKLOG)
    cands = doc.get("candidates") if isinstance(doc, dict) else None
    if not isinstance(cands, list):
        return (0, 0)
    total = len(cands)
    untested = sum(
        1 for c in cands if isinstance(c, dict)
        and str(c.get("category", "")).upper() in _UNTESTED_CATEGORIES
    )
    return (total, untested)


def _parity_green() -> Optional[bool]:
    """The coverage-grid GREEN bit (None when the matrix can't be built)."""
    try:
        from scripts.platformkit.parity_matrix import (  # noqa: PLC0415
            build_parity_matrix, is_green,
        )
        return bool(is_green(build_parity_matrix()))
    except Exception:  # noqa: BLE001 -- never green-on-error; degrade to unknown
        return None


def _engine_enabled() -> bool:
    """False while the human PIPELINE_ENABLED sentinel is absent (inert loop)."""
    try:
        from scripts.platformkit.improve.pipeline_flag import (  # noqa: PLC0415
            pipeline_enabled,
        )
        return bool(pipeline_enabled())
    except Exception:  # noqa: BLE001 -- absent helper -> inert, never enabled
        return False


def _engine_ready() -> bool:
    """True: the ratchet is proven-ready on a sealed fixture (importable + inert).

    'Ready' means the improvement machinery exists and is wired; it is NOT running
    and changes NOTHING until engine_enabled flips. Degrades to False if absent.
    """
    try:
        import scripts.platformkit.improve.pipeline_flag  # noqa: F401,PLC0415
        return True
    except Exception:  # noqa: BLE001
        return False


def _et_date(ts: float) -> str:
    """ET calendar date (UTC-4, offseason-stable) for same-day idempotency."""
    return _dt.datetime.utcfromtimestamp(ts - 4 * 3600).strftime("%Y-%m-%d")


def build_snapshot(now: Optional[float] = None) -> Dict[str, Any]:
    """Aggregate the live artifacts into ONE honest progress snapshot.

    Coverage = #verdicts / (#verdicts + #untested-data-remaining), per sport. The
    model is STATIC (model_static=True); engine_enabled mirrors the sentinel (False
    while absent). NO $ field is ever emitted.
    """
    now = float(now) if now is not None else _dt.datetime.utcnow().timestamp()
    verdicts = read_funnel_verdicts()
    untested = read_untested_by_sport()
    per_sport: Dict[str, Dict[str, Any]] = {}
    for sp in _SPORTS:
        v = [r for r in verdicts if r["sport"] == sp]
        n_tested = len(v)
        n_ship = sum(1 for r in v if r["bucket"] == "ship")
        n_reject = sum(1 for r in v if r["bucket"] == "reject")
        n_insuf = n_tested - n_ship - n_reject
        remaining = int(untested.get(sp, 0))
        denom = n_tested + remaining
        cov = round(100.0 * n_tested / denom, 2) if denom else 0.0
        per_sport[sp] = {
            "coverage_pct": cov,
            "n_tested": n_tested,
            "n_ship": n_ship,
            "n_reject": n_reject,
            "n_insufficient": n_insuf,
            "n_untested_remaining": remaining,
        }
    backlog_total, backlog_remaining = _backlog_totals()
    snap = {
        "ts": int(now),
        "date_et": _et_date(now),
        "per_sport": per_sport,
        "parity_green": _parity_green(),
        "backlog_total": backlog_total,
        "backlog_remaining": backlog_remaining,
        "engine_ready": _engine_ready(),
        "engine_enabled": _engine_enabled(),
        "model_static": True,
        "edge_claimed": False,
        "honest_note": (
            "PROGRESS = validation COVERAGE (verdicts / ingested), COMPLETENESS "
            "(parity green, markets exposed), and an improvement ENGINE that is "
            "proven-READY but INERT. The MODEL ITSELF IS STATIC: no prediction "
            "changes until a human creates the PIPELINE_ENABLED sentinel "
            "(engine_enabled=%s). Units only, never currency; no edge is claimed."
            % str(_engine_enabled()).lower()
        ),
    }
    return snap


def reconstruct_history(now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Reconstruct a coarse coverage time series from funnel verdict mtimes.

    Each distinct verdict-record timestamp becomes a point: the running count of
    verdicts recorded up to and including that moment (the honest 'verdicts over
    time' trend). This is REAL history (recorded-at mtimes), never interpolated.
    """
    now = float(now) if now is not None else _dt.datetime.utcnow().timestamp()
    verdicts = sorted(read_funnel_verdicts(), key=lambda r: r["at"])
    backlog_total, _ = _backlog_totals()
    pts: List[Dict[str, Any]] = []
    for i, r in enumerate(verdicts, start=1):
        if r["at"] <= 0:
            continue
        pts.append({
            "ts": r["at"],
            "date_et": _et_date(r["at"]),
            "n_verdicts_cumulative": i,
            "backlog_total": backlog_total,
            "model_static": True,
            "edge_claimed": False,
        })
    return pts


def append_snapshot(snap: Optional[Dict[str, Any]] = None,
                    now: Optional[float] = None) -> Dict[str, Any]:
    """Append today's snapshot to the JSONL ledger (idempotent same ET date).

    Re-running on the same ET date REPLACES that date's row rather than appending a
    duplicate, so the trend grows once per cadence-day. Returns the written snap.
    """
    snap = snap if snap is not None else build_snapshot(now=now)
    _LEDGER.parent.mkdir(parents=True, exist_ok=True)
    kept: List[Dict[str, Any]] = []
    if _LEDGER.exists():
        for line in _LEDGER.read_text(encoding="ascii", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict) and obj.get("date_et") != snap.get("date_et"):
                kept.append(obj)
    kept.append(snap)
    kept.sort(key=lambda o: o.get("ts", 0))
    body = "\n".join(json.dumps(o, ensure_ascii=True) for o in kept) + "\n"
    _LEDGER.write_text(body, encoding="ascii")
    return snap


def read_series() -> List[Dict[str, Any]]:
    """The persisted append-only ledger as a chronological list (or [])."""
    if not _LEDGER.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in _LEDGER.read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict):
            out.append(obj)
    out.sort(key=lambda o: o.get("ts", 0))
    return out


def progress_payload(now: Optional[float] = None) -> Dict[str, Any]:
    """The /api/progress envelope: latest snapshot + the time series + flags.

    The series prefers the persisted ledger; if empty it falls back to the
    REAL reconstructed (verdict-mtime) history so the trend is never fabricated.
    """
    snap = build_snapshot(now=now)
    series = read_series()
    reconstructed = reconstruct_history(now=now)
    return {
        "status": "ok",
        "snapshot": snap,
        "series": series,
        "reconstructed_history": reconstructed,
        "model_static": True,
        "model_static_note": (
            "Trend lines are COVERAGE / VERDICTS / BACKLOG over time -- NOT a live "
            "accuracy/edge climb. The model is STATIC until the self-improve gate "
            "is enabled by a human."
        ),
        "engine_enabled": snap["engine_enabled"],
        "edge_claimed": False,
    }


if __name__ == "__main__":  # pragma: no cover -- manual cadence entry point
    written = append_snapshot()
    print("progress_ledger: appended snapshot for %s (%d sports, engine_enabled=%s)"
          % (written["date_et"], len(written["per_sport"]),
             str(written["engine_enabled"]).lower()))
