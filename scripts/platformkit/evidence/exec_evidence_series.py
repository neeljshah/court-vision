"""scripts.platformkit.evidence.exec_evidence_series -- M44 append-only evidence series.

Every measurement daemon that exists today (m42 exec-quality, circuit_breaker,
ingame_realized_clv) writes into data/frontend/paper_today.json, which m1_bankroll
OVERWRITES every ~600s. There is no history: yesterday's execution quality is
gone the moment today's digest lands. This module is the fix -- an APPEND-ONLY
JSONL time series, one line per hour, so improvement (or regression) in
execution quality is provable over weeks, not just visible "right now".

snapshot() builds ONE as-of vintage: per market_type median_clv_pct (true-close
preferred, via execution.circuit_breaker -- never reimplemented) + breaker
state, execution-quality aggregates (gated/ungated counts, avg expected CLV,
median placement latency) over ledger rows carrying exec_gate, the realized
in-game CLV summary (clv_grading.ingame_realized_clv.summarize, imported
defensively), and prop calibration evidence by (sport, stat): for props
SETTLED in the trailing 30d, n, hit rate of the taken side (win/(win+loss),
push excluded), and median model_prob at placement -- the forward record that
will justify (or refute) any proposed recalibration. Every field is HONEST
NULL when the source data/module is absent; nothing is fabricated.

append_snapshot() is idempotent per UTC hour (snapshot_hour = "YYYY-MM-DDTHH"):
a re-run within the same hour is a no-op. The file is NEVER rewritten or
truncated -- only ever appended to (via io_atomic.append_jsonl_atomic, so a
crash mid-write can never leave a torn line).

MEASUREMENT ONLY: no bet/decision path touched, no flag flipped, no
data/registry/ write, no $ field, no edge claim.

INVARIANTS: scripts/platformkit/evidence/ only; <=300 LOC; ASCII; stdlib +
existing platformkit modules only (IMPORT, never reimplement).
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/evidence/test_exec_evidence_series.py -q
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.io_atomic import append_jsonl_atomic

ROOT = Path(__file__).resolve().parents[3]
SERIES_PATH = ROOT / "data" / "frontend" / "exec_evidence_series.jsonl"
PROP_LOOKBACK_DAYS = 30

try:
    from scripts.platformkit.clv_summary_cache import cached_load_ledger
except ImportError:  # concurrent lane not landed -- degrade honestly
    cached_load_ledger = None  # type: ignore[assignment]

try:
    from scripts.platformkit.execution import circuit_breaker as _breaker
except ImportError:
    _breaker = None  # type: ignore[assignment]

try:
    from scripts.platformkit.clv_grading.ingame_realized_clv import summarize as _summarize_ingame
except ImportError:
    _summarize_ingame = None  # type: ignore[assignment]


def _now_iso(now: Optional[datetime] = None) -> str:
    dt = now if now is not None else datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _hour_bucket(now_iso: str) -> str:
    return now_iso[:13]  # "YYYY-MM-DDTHH"


def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else round((s[mid - 1] + s[mid]) / 2.0, 6)


def _market_types(rows: List[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for r in rows:
        mt = str(r.get("market_type") or r.get("market") or "unknown")
        if mt not in seen:
            seen.append(mt)
    return seen


def _clv_by_market(rows: List[Dict[str, Any]], now_iso: str) -> Dict[str, Dict[str, Any]]:
    """Per market_type median_clv_pct + breaker state, imported from circuit_breaker."""
    out: Dict[str, Dict[str, Any]] = {}
    for mt in _market_types(rows):
        if _breaker is None:
            out[mt] = {"median_clv_pct": None, "n": 0, "n_proxy": 0,
                       "breaker_state": "UNKNOWN", "placed_today": None}
            continue
        roll = _breaker.rolling_clv(rows, mt, now_iso)
        st = _breaker.state(rows, mt, now_iso)
        allow = _breaker.allow_placement(rows, mt, now_iso)
        out[mt] = {"median_clv_pct": roll["median_clv_pct"], "n": roll["n"],
                   "n_proxy": roll["n_proxy"], "breaker_state": st["state"],
                   "placed_today": allow["placed_today"]}
    return out


def _exec_quality(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregates over rows carrying exec_gate / placement_latency_ms only."""
    gated = [r for r in rows if isinstance(r.get("exec_gate"), dict)]
    expected = [float(r["exec_gate"]["expected_clv_pct"]) for r in gated
                if r["exec_gate"].get("expected_clv_pct") is not None]
    latencies = [float(r["placement_latency_ms"]) for r in rows
                 if r.get("placement_latency_ms") is not None]
    return {"n_gated": len(gated), "n_ungated": len(rows) - len(gated),
            "avg_expected_clv_pct": round(sum(expected) / len(expected), 6) if expected else None,
            "median_latency_ms": _median(latencies)}


def _realized_ingame() -> Optional[Dict[str, Any]]:
    if _summarize_ingame is None:
        return None
    try:
        return _summarize_ingame()
    except Exception:  # noqa: BLE001 -- never let a sidecar read sink the snapshot
        return None


def _prop_calibration(rows: List[Dict[str, Any]], now_iso: str,
                       days: int = PROP_LOOKBACK_DAYS) -> Dict[str, Dict[str, Any]]:
    """(sport|stat) -> {n, hit_rate, median_model_prob} for props settled in
    the trailing *days*. hit_rate excludes push outcomes from its denominator."""
    now = _parse_ts(now_iso) or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    by_key: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r.get("market_type") != "prop" or r.get("status") != "settled":
            continue
        ts = _parse_ts(r.get("settled_at") or r.get("ts"))
        if ts is None or ts < cutoff or ts > now:
            continue
        key = "%s|%s" % (r.get("sport") or "?", r.get("prop_stat") or "?")
        by_key[key].append(r)
    out: Dict[str, Dict[str, Any]] = {}
    for key, rs in by_key.items():
        decided = [r for r in rs if r.get("outcome") in ("win", "loss")]
        wins = sum(1 for r in decided if r["outcome"] == "win")
        probs = [float(r["model_prob"]) for r in rs if r.get("model_prob") is not None]
        out[key] = {"n": len(rs),
                    "hit_rate": round(wins / len(decided), 4) if decided else None,
                    "median_model_prob": _median(probs)}
    return out


def snapshot(now_iso: Optional[str] = None) -> Dict[str, Any]:
    """One as-of vintage. Never raises -- every source is defensively imported
    and every field falls back to honest null rather than fabricating."""
    now_iso = now_iso or _now_iso()
    rows = cached_load_ledger() if cached_load_ledger is not None else []
    return {
        "ts": now_iso,
        "snapshot_hour": _hour_bucket(now_iso),
        "clv_by_market": _clv_by_market(rows, now_iso),
        "exec_quality": _exec_quality(rows),
        "realized_ingame": _realized_ingame(),
        "prop_calibration": _prop_calibration(rows, now_iso),
        "honest_note": ("measurement only; no bet/decision path touched, no "
                        "flag flipped, no data/registry/ write, no $ field"),
        "edge_claimed": False,
    }


def _hour_exists(path: Path, hour: str) -> bool:
    if not path.exists():
        return False
    try:
        with path.open("r", encoding="ascii") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("snapshot_hour") == hour:
                    return True
    except OSError:
        return False
    return False


def append_snapshot(path: Path = SERIES_PATH, now_iso: Optional[str] = None
                     ) -> Optional[Dict[str, Any]]:
    """Append one snapshot line unless a line for the current UTC hour already
    exists (hourly grain; re-runs within the same hour are a no-op). NEVER
    rewrites/truncates the file -- append-only, crash-safe."""
    doc = snapshot(now_iso)
    if _hour_exists(path, doc["snapshot_hour"]):
        return None
    append_jsonl_atomic(path, doc, encoding="ascii")
    return doc


def summarize_series(path: Path = SERIES_PATH, days: int = 30) -> Dict[str, Any]:
    """Per-market DAILY last-vintage series over the trailing *days* (pure read,
    for a later webapp trend strip). Later lines in the file win their day."""
    rows: List[Dict[str, Any]] = []
    if path.exists():
        with path.open("r", encoding="ascii") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    by_market: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        ts = _parse_ts(r.get("ts"))
        if ts is None or ts < cutoff:
            continue
        day = str(r.get("ts"))[:10]
        for mt, block in (r.get("clv_by_market") or {}).items():
            by_market[mt][day] = block  # last vintage of the day wins
    return {mt: dict(sorted(days_map.items())) for mt, days_map in by_market.items()}


__all__ = ["snapshot", "append_snapshot", "summarize_series", "SERIES_PATH"]
