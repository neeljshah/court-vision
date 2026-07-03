"""scripts.platformkit.odds_provider.inplay_capture_quality -- per-day IN-PLAY
capture-quality scoreboard (sibling of capture_quality.py, in-play instead of
pregame).

THE GAP: capture_quality.py measures the PREGAME line_history write path.
Nothing measures whether IN-PLAY ticks (the live conditional-probability feed
that drives in-game grading) land in
data/cache/inplay_history/<sport>/<date>.jsonl at a healthy rate/coverage. A
capture bug here silently starves the in-game layer while pregame looks fine.
COVERAGE MEASUREMENT ONLY -- no $ field, no ROI, no edge claim, no flag flip,
no data/registry/ write. A quiet/offseason day is NO_DATA, not a failure.

Row schema (confirmed live, 2026-07-03): sport, game_id, market_type, phase,
prob, side, source_ts, ticker, ts, venue. "prob" IS a probability in [0, 1]
already (Kalshi contract price), NOT American/decimal odds -- no conversion
applied. Newer rows (once the concurrent market-type widening lands) may ALSO
carry market_type in {"total", "spread", "team_total"} plus a "line" field;
both old (moneyline-only) and new rows are handled -- unknown market_types
are counted, never dropped.

TAIL_SHARE is computed over market_type == "moneyline" rows ONLY: a
total/spread "prob" is not a win probability, mixing it into a
prob<0.20-or->0.80 tail count would be a category error, not a signal.

MAX_GAP_MIN is the largest gap between CONSECUTIVE DISTINCT "ts" values
inside the file's own first_ts..last_ts span, i.e. gaps while the file has
rows at all, which for this feed only exist while a market is open+live.
Overnight/no-live-games spans never appear in the file, so they are excluded
from the gap calc BY CONSTRUCTION (not detected as an outage); a genuine
capture stall DURING a live window still shows up as a big in-span gap.

Run:  python -m scripts.platformkit.odds_provider.inplay_capture_quality
Per-file test: scripts/platformkit/odds_provider/test_inplay_capture_quality.py
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from scripts.platformkit.odds_provider.capture_quality import (
    GREEN, NO_DATA, REGRESSION, _hourly_rate, _now, _parse_ts)

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_HISTORY_DIR = _REPO / "data" / "cache" / "inplay_history"
_OUT_PATH = _REPO / "data" / "frontend" / "ops" / "inplay_capture_quality.json"
DEFAULT_SPORTS = ("nba", "mlb", "soccer", "soccer_intl", "tennis")
_MONEYLINE = "moneyline"
# Same regression thresholds as the pregame sibling -- see capture_quality.py
# for the elapsed-normalization rationale (reused verbatim here).
_MIN_GAMES_FOR_SIGNAL = 3
_RATE_FLOOR_FRACTION = 0.5


def measure_inplay(sport: str, date_str: str, *, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """In-play capture-quality metrics for one (sport, date) from its jsonl
    history file. Missing file -> zeros with "no_file": true. A corrupt/
    unparseable line is skipped and counted in "n_corrupt". Never raises.
    tail_share/max_gap_min semantics: see module docstring.
    """
    base = Path(base_dir) if base_dir is not None else DEFAULT_HISTORY_DIR
    path = base / sport / ("%s.jsonl" % date_str)
    out: Dict[str, Any] = {
        "sport": sport, "date": date_str, "n_rows": 0, "n_games": 0, "n_venues": 0,
        "n_market_types": 0, "rows_by_market_type": {}, "tail_share": 0.0,
        "max_gap_min": None, "first_ts": None, "last_ts": None,
        "median_ticks_per_game": 0.0, "n_corrupt": 0, "no_file": False,
    }
    if not path.exists():
        out["no_file"] = True
        return out
    try:
        game_ticks: Dict[str, int] = {}
        venues: Set[str] = set()
        market_types: Dict[str, int] = {}
        distinct_ts: Set[str] = set()
        n_rows = n_tail = n_ml_priced = 0
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    out["n_corrupt"] += 1
                    continue
                if not isinstance(row, dict):
                    out["n_corrupt"] += 1
                    continue
                n_rows += 1
                game_id = str(row.get("game_id") or "")
                if game_id:
                    game_ticks[game_id] = game_ticks.get(game_id, 0) + 1
                venue = str(row.get("venue") or "")
                if venue:
                    venues.add(venue)
                mtype = str(row.get("market_type") or "unknown")
                market_types[mtype] = market_types.get(mtype, 0) + 1
                if row.get("ts"):
                    distinct_ts.add(str(row.get("ts")))
                if mtype == _MONEYLINE:
                    try:
                        prob = float(row.get("prob"))
                    except (TypeError, ValueError):
                        prob = None
                    if prob is not None and 0.0 < prob < 1.0:
                        n_ml_priced += 1
                        if prob < 0.20 or prob > 0.80:
                            n_tail += 1
        out["n_rows"] = n_rows
        out["n_games"] = len(game_ticks)
        out["n_venues"] = len(venues)
        out["n_market_types"] = len(market_types)
        out["rows_by_market_type"] = dict(sorted(market_types.items()))
        out["tail_share"] = (n_tail / n_ml_priced) if n_ml_priced else 0.0
        if game_ticks:
            ticks = sorted(game_ticks.values())
            mid = len(ticks) // 2
            out["median_ticks_per_game"] = (
                float(ticks[mid]) if len(ticks) % 2 == 1
                else (ticks[mid - 1] + ticks[mid]) / 2.0)
        ts_list = sorted(t for t in (_parse_ts(x) for x in distinct_ts) if t is not None)
        if ts_list:
            out["first_ts"] = ts_list[0].isoformat()
            out["last_ts"] = ts_list[-1].isoformat()
        if len(ts_list) >= 2:
            gaps = [(ts_list[i + 1] - ts_list[i]).total_seconds() / 60.0
                    for i in range(len(ts_list) - 1)]
            out["max_gap_min"] = max(gaps)
    except Exception as exc:  # noqa: BLE001 -- measure_inplay() must never raise
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    return out


def completeness(sport: str, date_str: str, *,
                  scoreboard_game_ids: Optional[Set[str]] = None,
                  base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """"Did we capture every game we COULD" -- a COUNT ratio, not an id join.
    Kalshi tickers/game_ids and ESPN scoreboard game ids are different id
    namespaces (the known landmine), so ids are never joined. When
    scoreboard_game_ids is given, compares COUNTS ONLY: n_games captured
    today vs len(scoreboard_game_ids), ratio capped at 1.0. When omitted
    (None), this feed's own _freshness.json sibling tracks capture ticks, not
    a scoreboard game count, so n_available/count_ratio are left None rather
    than guessed.
    """
    day = measure_inplay(sport, date_str, base_dir=base_dir)
    out: Dict[str, Any] = {
        "sport": sport, "date": date_str, "n_captured": day.get("n_games", 0) or 0,
        "n_available": None, "count_ratio": None,
        "note": ("count comparison only -- Kalshi/ESPN id namespaces differ, "
                  "so games are never id-joined, only counted"),
    }
    if scoreboard_game_ids is not None:
        n_available = len(scoreboard_game_ids)
        out["n_available"] = n_available
        out["count_ratio"] = min(1.0, out["n_captured"] / n_available) if n_available > 0 else None
    return out


def _mtypes(day: Dict[str, Any]) -> Set[str]:
    return set((day.get("rows_by_market_type") or {}).keys()) - {_MONEYLINE, "unknown"}


def _verdict(today: Dict[str, Any], yesterday: Dict[str, Any], *, now: datetime) -> str:
    """GREEN / REGRESSION / NO_DATA. Mirrors capture_quality's elapsed-
    normalized rate-collapse rule, PLUS an in-play-only trigger: yesterday had
    non-moneyline rows (total/spread/team_total) while today has none despite
    live rows -- a market-type coverage drop the pregame sibling can't see.
    """
    today_empty = (today.get("n_rows", 0) or 0) == 0
    if today_empty and (yesterday.get("n_rows", 0) or 0) == 0:
        return NO_DATA
    if (yesterday.get("n_games", 0) or 0) < _MIN_GAMES_FOR_SIGNAL:
        return GREEN if not today_empty else NO_DATA  # no baseline to regress against
    if _mtypes(yesterday) and not _mtypes(today) and not today_empty:
        return REGRESSION
    today_rate = _hourly_rate(today, full_day=False, now=now)
    yest_rate = _hourly_rate(yesterday, full_day=True, now=now)
    if yest_rate > 0 and today_rate < (_RATE_FLOOR_FRACTION * yest_rate):
        return REGRESSION
    return GREEN


def scoreboard_inplay(sports: Sequence[str] = DEFAULT_SPORTS, *,
                       now: Optional[datetime] = None,
                       base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Measure today + yesterday per sport (in-play feed) and assign a
    verdict. Never raises. See _verdict() for the rule.
    """
    nowdt = now if now is not None else _now()
    today_str = nowdt.date().isoformat()
    yest_str = (nowdt - timedelta(days=1)).date().isoformat()
    by_sport: Dict[str, Any] = {}
    n_regression = 0
    n_no_data = 0
    for sport in sports:
        try:
            today = measure_inplay(sport, today_str, base_dir=base_dir)
            yesterday = measure_inplay(sport, yest_str, base_dir=base_dir)
            verdict = _verdict(today, yesterday, now=nowdt)
        except Exception as exc:  # noqa: BLE001 -- one bad sport must not sink the board
            today = {"sport": sport, "date": today_str, "error": "%s: %s" % (
                type(exc).__name__, exc)}
            yesterday = {"sport": sport, "date": yest_str}
            verdict = NO_DATA
        if verdict == REGRESSION:
            n_regression += 1
        elif verdict == NO_DATA:
            n_no_data += 1
        by_sport[sport] = {"today": today, "yesterday": yesterday, "verdict": verdict}

    overall = REGRESSION if n_regression else (
        NO_DATA if n_no_data == len(sports) else GREEN)
    return {
        "sports": list(sports),
        "by_sport": by_sport,
        "n_regression": n_regression,
        "n_no_data": n_no_data,
        "overall": overall,
        "honest_note": (
            "reads back data/cache/inplay_history/<sport>/<date>.jsonl (the live "
            "in-play tick feed). Coverage measurement only -- no $ field, no ROI, "
            "no edge claim. tail_share is moneyline-only. REGRESSION fires on an "
            "elapsed-normalized rate collapse OR a market-type coverage drop -- "
            "see module docstring."
        ),
    }


def write_status(doc: Dict[str, Any], *, out_path: Optional[Path] = None,
                  now: Optional[float] = None) -> bool:
    """Atomically write the in-play scoreboard (tmp + os.replace). Never raises."""
    try:
        path = Path(out_path) if out_path is not None else _OUT_PATH
        ts = float(now) if now is not None else time.time()
        full = dict(doc)
        full["generated_at"] = ts
        full["component"] = "m_inplay_capture_quality"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(full, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001 -- write must never crash the caller
        return False


def load_status(*, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Best-effort read of the last written scoreboard. None on any failure/missing."""
    try:
        p = Path(path) if path is not None else _OUT_PATH
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="ascii"))
    except Exception:  # noqa: BLE001
        return None


def render(doc: Dict[str, Any]) -> str:
    """ASCII table summary of an in-play scoreboard doc."""
    lines: List[str] = ["=" * 86,
        "IN-PLAY CAPTURE QUALITY -- per-sport live-tick coverage (%s)" % ",".join(
            doc.get("sports", [])),
        "=" * 86,
        "%-12s %-11s %8s %6s %7s %6s %10s" % (
            "SPORT", "VERDICT", "ROWS", "GAMES", "MTYPES", "TAIL%", "MAXGAP_M")]
    for sport in doc.get("sports", []):
        today = ((doc.get("by_sport", {}) or {}).get(sport, {})).get("today", {}) or {}
        verdict = (doc.get("by_sport", {}) or {}).get(sport, {}).get("verdict", "?")
        gap = today.get("max_gap_min")
        lines.append("%-12s %-11s %8d %6d %7d %6.1f %10s" % (
            sport, verdict, today.get("n_rows", 0) or 0, today.get("n_games", 0) or 0,
            today.get("n_market_types", 0) or 0,
            (today.get("tail_share", 0.0) or 0.0) * 100.0,
            ("%.1f" % gap) if gap is not None else "-"))
    lines += ["-" * 86, "OVERALL: " + doc.get("overall", "?"), "=" * 86]
    return "\n".join(lines)


def main() -> int:
    doc = scoreboard_inplay()
    print(render(doc))
    write_status(doc)
    print("\nwrote %s" % _OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["GREEN", "REGRESSION", "NO_DATA", "DEFAULT_SPORTS", "DEFAULT_HISTORY_DIR",
           "measure_inplay", "completeness", "scoreboard_inplay", "write_status",
           "load_status", "render"]
