"""scripts.platformkit.ingame.inplay_tick_latency -- LANE C: capture-cadence /
tick-latency measurement for the in-play capture corpus (all sports).

WHAT THIS MEASURES
------------------
From the captured tick files (data/cache/ingame_grade/<sport>/*.jsonl, the same
layout ingame_tail_scan reads), per sport, over LIVE windows only (ticks whose
consecutive gap is <= LIVE_GAP_MAX_SEC -- a big gap almost always means the
game paused/finished and the next tick belongs to a different live window, not
a slow capture cycle):
  * inter-tick gap distribution: p50 / p90 / max (seconds)
  * ticks per live-game-hour (n_ticks / total live-window hours)
  * capture-cycle LAG vs the venue/exchange's own timestamp -- ONLY if the tick
    payload actually carries one.

HONEST GAP: checked directly against the real on-disk schema
(live_grade.capture_pair_once) -- every tick carries exactly ONE timestamp,
"ts", which is OUR capture wall-clock time (nowdt at write), not a venue/
exchange-supplied timestamp. There is no second timestamp field to diff
against. So "capture-cycle lag vs venue time" is reported as
NOT_AVAILABLE (schema_has_venue_ts=False) rather than silently computed as
0 or fabricated -- this module never claims a lag number it cannot back with
a real venue timestamp on disk.

VERDICT: GREEN if p90 gap <= GAP_P90_THRESHOLD_SEC for a sport with enough
ticks to judge; DEGRADED if p90 exceeds it; INSUFFICIENT_DATA below
MIN_TICKS_SPORT. No $ field; edge_claimed is always False (this is an
operational cadence scoreboard, not a pricing signal).

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network; no data/registry
write; no flag flip.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_inplay_tick_latency.py -q
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"
DEFAULT_OUT = _REPO_ROOT / "data" / "frontend" / "ops" / "inplay_tick_latency.json"

SPORTS: List[str] = ["mlb", "soccer_intl", "soccer", "tennis"]

LIVE_GAP_MAX_SEC: float = 900.0     # >15min gap -> treat as a window break, not lag
GAP_P90_THRESHOLD_SEC: float = 120.0  # documented threshold: healthy p90 gap <= 2min
MIN_TICKS_SPORT: int = 20


def _parse_ts(s: Any) -> Optional[datetime]:
    if not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None


def _load_ticks(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
    except OSError:
        return []
    return out


def _percentile(sorted_vals: List[float], pct: float) -> Optional[float]:
    if not sorted_vals:
        return None
    idx = min(int(pct * len(sorted_vals)), len(sorted_vals) - 1)
    return round(sorted_vals[idx], 2)


_VENUE_TS_KEYS = ("src_ts", "venue_ts")  # venue_ts retained only for legacy corpora/tests


def _venue_ts_field(row: Dict[str, Any]) -> Optional[str]:
    for k in _VENUE_TS_KEYS:
        if k in row:
            return k
    return None


def measure_sport(sport: str, grade_dir: Optional[Path] = None,
                  live_gap_max_sec: float = LIVE_GAP_MAX_SEC) -> Dict[str, Any]:
    """Measure tick cadence for one sport across every captured game file.
    Never raises; a missing/empty dir reads n_ticks=0, verdict INSUFFICIENT_DATA."""
    base = (Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR) / sport.lower()
    files = [f for f in sorted(base.glob("*.jsonl")) if not f.name.startswith("_")] \
        if base.is_dir() else []

    all_gaps: List[float] = []
    live_hours_total = 0.0
    n_ticks_total = 0
    n_games = 0
    schema_has_venue_ts = False
    lag_samples: List[float] = []

    for f in files:
        rows = _load_ticks(f)
        if not rows:
            continue
        n_games += 1
        n_ticks_total += len(rows)
        times: List[datetime] = []
        for r in rows:
            t = _parse_ts(r.get("ts"))
            if t is not None:
                times.append(t)
            vfield = _venue_ts_field(r)
            if vfield is not None:
                schema_has_venue_ts = True
                vt = _parse_ts(r.get(vfield))
                if vt is not None and t is not None:
                    lag_samples.append((t - vt).total_seconds())
        times.sort()
        for a, b in zip(times, times[1:]):
            gap = (b - a).total_seconds()
            if gap <= 0:
                continue
            if gap <= live_gap_max_sec:
                all_gaps.append(gap)
                live_hours_total += gap / 3600.0

    all_gaps.sort()
    n_gaps = len(all_gaps)
    p50 = _percentile(all_gaps, 0.50)
    p90 = _percentile(all_gaps, 0.90)
    p_max = round(all_gaps[-1], 2) if all_gaps else None
    ticks_per_live_hour = (round(n_ticks_total / live_hours_total, 2)
                           if live_hours_total > 0 else None)

    if n_ticks_total < MIN_TICKS_SPORT:
        verdict = "INSUFFICIENT_DATA"
    elif p90 is not None and p90 <= GAP_P90_THRESHOLD_SEC:
        verdict = "GREEN"
    elif p90 is not None:
        verdict = "DEGRADED"
    else:
        verdict = "INSUFFICIENT_DATA"

    return {
        "sport": sport, "n_games": n_games, "n_ticks": n_ticks_total,
        "n_gap_samples": n_gaps,
        "gap_p50_sec": p50, "gap_p90_sec": p90, "gap_max_sec": p_max,
        "ticks_per_live_game_hour": ticks_per_live_hour,
        "gap_p90_threshold_sec": GAP_P90_THRESHOLD_SEC,
        "min_ticks_sport": MIN_TICKS_SPORT,
        "verdict": verdict,
        "schema_has_venue_ts": schema_has_venue_ts,
        "src_ts_coverage_pct": round(100.0 * len(lag_samples) / n_ticks_total, 2) if n_ticks_total else None,
        "lag_p50_sec": _percentile(sorted(lag_samples), 0.50),
        "lag_p90_sec": _percentile(sorted(lag_samples), 0.90),
        "capture_lag_vs_venue_sec_p50": _percentile(sorted(lag_samples), 0.50),
        "capture_lag_note": (
            "tick payload carries no source timestamp field (only our own "
            "capture 'ts') -- capture-cycle lag vs venue time is NOT_AVAILABLE, "
            "reported honestly rather than fabricated"
            if not schema_has_venue_ts else
            "lag computed as capture ts minus explicit source src_ts"
        ),
    }


def measure_all(sports: Optional[List[str]] = None,
                grade_dir: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for sport in (sports or SPORTS):
        try:
            out[sport] = measure_sport(sport, grade_dir=grade_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("inplay_tick_latency measure_sport(%s) failed: %s", sport, exc)
            out[sport] = {"sport": sport, "verdict": "ERROR", "error": str(exc),
                          "n_ticks": 0, "n_games": 0}
    return out


def build_doc(results: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    results = results if results is not None else measure_all()
    overall = "GREEN"
    for r in results.values():
        if r.get("verdict") == "DEGRADED":
            overall = "DEGRADED"
            break
    if overall == "GREEN" and all(r.get("verdict") == "INSUFFICIENT_DATA" for r in results.values()):
        overall = "INSUFFICIENT_DATA"
    return {
        "component": "inplay_tick_latency", "overall_verdict": overall,
        "by_sport": results,
        "note": ("inter-tick gap + ticks-per-live-hour cadence scoreboard; capture-cycle "
                 "lag vs venue time reported only where the payload actually carries a "
                 "venue timestamp (none currently do); operational cadence measurement, "
                 "not a pricing signal"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "edge_claimed": False,
    }


def write_artifact(doc: Dict[str, Any], out_path: Optional[Path] = None) -> Path:
    p = Path(out_path) if out_path is not None else DEFAULT_OUT
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)
    return p


def main() -> None:
    doc = build_doc()
    print("inplay_tick_latency | overall=%s" % doc["overall_verdict"])
    for sport, r in doc["by_sport"].items():
        print("  %-12s verdict=%-16s n_ticks=%-6d p50=%s p90=%s max=%s ticks/hr=%s" % (
            sport, r.get("verdict"), r.get("n_ticks", 0),
            r.get("gap_p50_sec"), r.get("gap_p90_sec"), r.get("gap_max_sec"),
            r.get("ticks_per_live_game_hour")))
    path = write_artifact(doc)
    print("artifact: %s" % path)


if __name__ == "__main__":
    main()
