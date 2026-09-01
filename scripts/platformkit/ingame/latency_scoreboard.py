"""ASCII venue-clock latency scoreboard; callers provide scratch grade directories."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.platformkit.ingame import inplay_tick_latency as latency

# Pre-registered 2026-09-01 operational eligibility gates.
EVENT_REACTIVE_LAG_P90_SEC = 5.0
EVENT_REACTIVE_COVERAGE_PCT = 95.0
SLOW_STATE_TICK_P90_SEC = 120.0
HEADER = "sport venue tick_p50 tick_p90 lag_p50 lag_p90 ticks_per_live_hour src_ts_coverage_pct event_reactive slow_state"


def build_rows(grade_dir: Path) -> List[Dict[str, Any]]:
    """Measure each sport/venue from a caller-owned scratch corpus. Never writes it."""
    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    for path in grade_dir.glob("*/*.jsonl"):
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if isinstance(row, dict):
                    grouped.setdefault((str(row.get("sport", "unknown")),
                                        str(row.get("venue", "unknown"))), []).append(row)
        except (OSError, ValueError):
            continue
    out: List[Dict[str, Any]] = []
    for (sport, venue), rows in sorted(grouped.items()):
        # The latency module accepts its normal corpus layout; use a caller-created scratch
        # sibling only in tests, never a production/default archive path.
        tmp = grade_dir / "_scoreboard_scratch" / sport
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / (venue + ".jsonl")).write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        m = latency.measure_sport(sport, grade_dir=tmp.parent)
        lag90, coverage, tick90 = m.get("lag_p90_sec"), m.get("src_ts_coverage_pct"), m.get("gap_p90_sec")
        out.append({"sport": sport, "venue": venue, "tick_p50": m.get("gap_p50_sec"),
                    "tick_p90": tick90, "lag_p50": m.get("lag_p50_sec"), "lag_p90": lag90,
                    "ticks_per_live_hour": m.get("ticks_per_live_game_hour"),
                    "src_ts_coverage_pct": coverage,
                    "event_reactive": bool(lag90 is not None and coverage is not None and lag90 <= EVENT_REACTIVE_LAG_P90_SEC and coverage >= EVENT_REACTIVE_COVERAGE_PCT),
                    "slow_state": bool(tick90 is not None and tick90 <= SLOW_STATE_TICK_P90_SEC)})
    return out


def render(rows: List[Dict[str, Any]]) -> str:
    return "\n".join([HEADER] + [
        "{sport} {venue} {tick_p50} {tick_p90} {lag_p50} {lag_p90} {ticks_per_live_hour} {src_ts_coverage_pct} {event_reactive} {slow_state}".format(**r)
        for r in rows])



def event_reactive_supported(sport: str, grade_dir: Path = None) -> bool:
    """MEASURED-latency eligibility for an event-reactive entry. FAIL-CLOSED: an
    unmeasured, slow, or low-coverage feed never supports reacting to events.
    Same gates the scoreboard rows use (lag_p90 <= EVENT_REACTIVE_LAG_P90_SEC and
    src_ts coverage >= EVENT_REACTIVE_COVERAGE_PCT). Never raises.

    ponytail: re-measures the corpus per call; add a per-sport cache if a caller
    ever sets event_reactive on a hot tick path."""
    try:
        m = latency.measure_sport(sport, grade_dir=grade_dir)
        lag90 = m.get("lag_p90_sec")
        cov = m.get("src_ts_coverage_pct")
        return bool(lag90 is not None and cov is not None
                    and float(lag90) <= EVENT_REACTIVE_LAG_P90_SEC
                    and float(cov) >= EVENT_REACTIVE_COVERAGE_PCT)
    except Exception:  # noqa: BLE001 -- eligibility check must never sink a tick
        return False
