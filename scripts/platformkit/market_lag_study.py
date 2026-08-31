"""Describe how quickly recorded in-play probabilities absorb score changes."""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from scripts.platformkit.ingame_replay_scoreboard import (_OUTCOME_KEYS, _normalise,
                                                          _value, candidate_dirs)

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = Path(r"C:\Users\neelj\nba-ai-system\data\cache")
_PREFIX_SPORTS = {"KXWCGAME": "soccer_wc", "KXMLBGAME": "mlb", "KXNBAGAME": "nba",
                  "KXNFLGAME": "nfl", "KXNCAABGAME": "ncaab", "KXNCAAWGAME": "ncaaw"}
_HORIZON = 10
_WINDOWS = (1, 2, 5, 10)


def _sport(raw: Dict[str, Any], game: str) -> str:
    value = raw.get("sport")
    if value not in (None, ""):
        return str(value).lower()
    return next((name for prefix, name in _PREFIX_SPORTS.items() if game.startswith(prefix)), "unknown")


def _scores(value: Any) -> Optional[Tuple[int, int]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            found = dict(re.findall(r"\b(home_score|away_score)=(-?\d+(?:\.\d+)?)", value))
            if set(found) != {"home_score", "away_score"}:
                return None
            try:
                return int(float(found["home_score"])), int(float(found["away_score"]))
            except ValueError:
                return None
    if not isinstance(value, dict):
        return None
    try:
        return int(value["home_score"]), int(value["away_score"])
    except (KeyError, TypeError, ValueError):
        return None


def _seconds(later: str, earlier: str) -> Optional[float]:
    try:
        def parse(value: str) -> datetime:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (parse(later) - parse(earlier)).total_seconds()
    except ValueError:
        try:
            return float(later) - float(earlier)
        except (TypeError, ValueError):
            return None


def load_records(store: Path) -> List[Dict[str, Any]]:
    """Load settled normalized ticks while preserving each source score state."""
    rows: List[Dict[str, Any]] = []
    for path in sorted(store.rglob("*.jsonl"), key=lambda item: str(item).lower()):
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(raw, dict):
                        continue
                    tick = _normalise(raw)
                    if tick is not None:
                        rows.append({**tick, "outcome": float(_value(raw, _OUTCOME_KEYS)),
                                     "state_summary": raw.get("state_summary"), "raw": raw})
        except OSError:
            continue
    return rows


def _quantile(values: Iterable[float], q: float) -> Optional[float]:
    ordered = sorted(values)
    if not ordered:
        return None
    place = (len(ordered) - 1) * q
    low, high = int(place), math.ceil(place)
    return ordered[low] + (ordered[high] - ordered[low]) * (place - low)


def _event(game: str, ticks: List[Dict[str, Any]], index: int) -> Optional[Dict[str, Any]]:
    before, current = _scores(ticks[index - 1].get("state_summary")), _scores(ticks[index].get("state_summary"))
    if before is None or current is None or before == current or index + _HORIZON >= len(ticks):
        return None
    size = abs(current[0] + current[1] - before[0] - before[1])
    if not size:
        return None
    result: Dict[str, Any] = {"game": game, "sport": _sport(ticks[index]["raw"], game),
                              "event_tick": index, "event_size": size,
                              "event_size_group": "1-run" if size == 1 else "multi-run"}
    for field in ("market_prob", "model_prob"):
        base, settled = ticks[index - 1].get(field), ticks[index + _HORIZON].get(field)
        if base is None or settled is None:
            result[field] = None
            continue
        move = settled - base
        detail: Dict[str, Any] = {"eventual_move": move,
                                  "moves": {str(n): ticks[index + n][field] - base for n in _WINDOWS}}
        if move == 0:
            detail.update({"lag_ticks": None, "lag_seconds": None})
        else:
            direction, threshold = (1 if move > 0 else -1), abs(move) * .70
            lag = next((n for n in range(1, _HORIZON + 1)
                        if (ticks[index + n][field] - base) * direction >= threshold), None)
            detail["lag_ticks"] = lag
            detail["lag_seconds"] = (_seconds(ticks[index + lag]["timestamp"], ticks[index]["timestamp"])
                                   if lag is not None else None)
        result[field] = detail
    return result


def analyze(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Find score events and aggregate descriptive market and model response lags."""
    by_game: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_game[record["game"]].append(record)
    events = []
    for game, ticks in sorted(by_game.items()):
        ordered = sorted(ticks, key=lambda tick: tick["timestamp"])
        events.extend(event for index in range(1, len(ordered))
                      if (event := _event(game, ordered, index)) is not None)
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for event in events:
        for sport in ("all", event["sport"]):
            for size in ("all", event["event_size_group"]):
                groups[(sport, size)].append(event)
    summaries = []
    for (sport, size), group in sorted(groups.items()):
        row: Dict[str, Any] = {"sport": sport, "event_size": size, "events": len(group), "series": {}}
        for field in ("market_prob", "model_prob"):
            details = [event[field] for event in group if event[field] is not None]
            lags = [detail["lag_ticks"] for detail in details if detail["lag_ticks"] is not None]
            secs = [detail["lag_seconds"] for detail in details if detail["lag_seconds"] is not None]
            row["series"][field] = {"usable_events": len(details), "lagged_events": len(lags),
                                     "lag_ticks": {"median": _quantile(lags, .5), "p75": _quantile(lags, .75)},
                                     "lag_seconds": {"median": _quantile(secs, .5), "p75": _quantile(secs, .75)}}
        summaries.append(row)
    return {"horizon_ticks": _HORIZON, "threshold_fraction": .70, "events": events, "summaries": summaries}


def _number(value: Optional[float]) -> str:
    return "-" if value is None else ("%d" % value if value == int(value) else "%.2f" % value)


def render(report: Dict[str, Any]) -> str:
    lines = ["SPORT | EVENT_SIZE | EVENTS | SERIES | LAGGED | MED_TICKS | P75_TICKS | MED_SECONDS | P75_SECONDS",
             "------|------------|--------|--------|--------|-----------|-----------|-------------|------------"]
    for summary in report["summaries"]:
        for field, values in summary["series"].items():
            lines.append("%s | %s | %d | %s | %d | %s | %s | %s | %s" %
                         (summary["sport"], summary["event_size"], summary["events"], field,
                          values["lagged_events"], _number(values["lag_ticks"]["median"]),
                          _number(values["lag_ticks"]["p75"]), _number(values["lag_seconds"]["median"]),
                          _number(values["lag_seconds"]["p75"])))
    lines += ["", "CAVEAT: Tick cadence (often about 30 seconds) bounds time resolution.",
              "CAVEAT: Absorption lag is descriptive of these stored markets and this period, not an edge claim."]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Describe in-play market score-event absorption lag.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=_REPO / "data" / "ab_reports" / "market_lag_study.json")
    args = parser.parse_args(argv)
    stores, records = [], []
    for store in candidate_dirs(args.cache_root):
        loaded = load_records(store)
        if loaded:
            stores.append(store)
            records.extend(loaded)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "stores": [str(path) for path in stores],
              **analyze(records)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("STORES: " + (", ".join(str(path) for path in stores) or "NONE"))
    print(render(report))
    print("REPORT: %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
