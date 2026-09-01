"""Audit settled win-probability tick stores by raw probability series."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from scripts.platformkit.ingame_replay_scoreboard import (_OUTCOME_KEYS, _normalise, _value,
                                                          candidate_dirs)

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = Path(os.environ.get(
    "NBA_CACHE_ROOT",
    os.path.join(os.environ.get("NBA_DATA_ROOT", "data"), "cache")))
_TOKENS = ("prob", "price", "mid", "blend")
_PREFIX_SPORTS = {"KXWCGAME": "soccer_wc", "KXMLBGAME": "mlb", "KXNBAGAME": "nba",
                  "KXNFLGAME": "nfl", "KXNCAABGAME": "ncaab", "KXNCAAWGAME": "ncaaw"}


def _prob(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0.0 <= number <= 1.0 else None


def _sport(raw: Dict[str, Any], game: str) -> str:
    value = raw.get("sport")
    if value not in (None, ""):
        return str(value).lower()
    return next((sport for prefix, sport in _PREFIX_SPORTS.items() if game.startswith(prefix)), "unknown")


def _date(value: str) -> Optional[str]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def load_records(store: Path) -> List[Dict[str, Any]]:
    """Load the same settled records accepted by the replay-scoreboard normalizer."""
    records: List[Dict[str, Any]] = []
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
                        records.append({"raw": raw, **tick,
                                        "outcome": float(_value(raw, _OUTCOME_KEYS))})
        except OSError:
            continue
    return records


def _quantiles(values: Iterable[float]) -> Dict[str, Optional[float]]:
    ordered = sorted(values)
    def at(q: float) -> Optional[float]:
        if not ordered:
            return None
        position = (len(ordered) - 1) * q
        low, high = int(position), math.ceil(position)
        return ordered[low] + (ordered[high] - ordered[low]) * (position - low)
    return {str(int(q * 100)): at(q) for q in (0.5, 0.75, 0.9, 0.95)}


def _distribution(counts: List[int]) -> Dict[str, Optional[float]]:
    return {"min": min(counts) if counts else None, "median": _quantiles(counts)["50"],
            "max": max(counts) if counts else None}


def _summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_game: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_game[record["game"]].append(record)
    dates = sorted(date for record in records if (date := _date(record["timestamp"])) is not None)
    sports: Dict[str, int] = defaultdict(int)
    peaks: List[float] = []
    eligible = 0
    for game, group in by_game.items():
        sports[_sport(group[0]["raw"], game)] += 1
        if len(group) >= 20:
            eligible += 1
            loser_values = [record["probability"] for record in group if record["outcome"] == 0.0]
            if loser_values:
                peaks.append(max(loser_values))
    return {"n_games": len(by_game), "ticks_per_game": _distribution([len(group) for group in by_game.values()]),
            "capture_date_range": {"first": dates[0] if dates else None, "last": dates[-1] if dates else None},
            "sports_breakdown": dict(sorted(sports.items())), "n_games_at_least_20_ticks": eligible,
            "max_loser_wp": {"n_games": len(peaks), "quantiles": _quantiles(peaks),
                             "above_0_8": sum(value > .8 for value in peaks),
                             "above_0_9": sum(value > .9 for value in peaks)}}


def audit(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Split all numeric raw probability-like fields into series and sport audits."""
    fields = sorted({key for record in records for key, value in record["raw"].items()
                     if any(token in key.lower() for token in _TOKENS) and _prob(value) is not None})
    series: Dict[str, Dict[str, Any]] = {}
    for field in fields:
        rows = [{**record, "probability": _prob(record["raw"].get(field))} for record in records
                if _prob(record["raw"].get(field)) is not None]
        by_sport: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_sport[_sport(row["raw"], row["game"])].append(row)
        series[field] = {"overall": _summary(rows),
                         "by_sport": {sport: _summary(group) for sport, group in sorted(by_sport.items())}}
    return {"raw_probability_fields": fields, "series": series}


def render(report: Dict[str, Any]) -> str:
    lines = ["RAW PROBABILITY FIELDS: " + (", ".join(report["raw_probability_fields"]) or "NONE"),
             "SERIES | SPORT | GAMES | TICKS_MIN | TICKS_MED | TICKS_MAX | DENSE | LOSER_GAMES | P50 | P75 | P90 | P95 | DATE_RANGE",
             "-------|-------|-------|-----------|-----------|-----------|-------|-------------|-----|-----|-----|-----|-----------"]
    for field, detail in report["series"].items():
        for sport, summary in [("ALL", detail["overall"]), *detail["by_sport"].items()]:
            ticks, loser, dates = summary["ticks_per_game"], summary["max_loser_wp"], summary["capture_date_range"]
            quantiles = loser["quantiles"]
            lines.append("%s | %s | %d | %s | %s | %s | %d | %d | %s | %s | %s | %s | %s..%s" %
                         (field, sport, summary["n_games"], _num(ticks["min"]), _num(ticks["median"]),
                          _num(ticks["max"]), summary["n_games_at_least_20_ticks"], loser["n_games"],
                          *[_num(quantiles[str(q)]) for q in (50, 75, 90, 95)],
                          dates["first"] or "-", dates["last"] or "-"))
    return "\n".join(lines)


def _num(value: Optional[float]) -> str:
    return "-" if value is None else ("%d" % value if value == int(value) else "%.2f" % value)


def write_report(report: Dict[str, Any], stores: List[Path], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / ("wp_series_audit_%s.json" % stamp)
    path.write_text(json.dumps({"generated_at": stamp, "stores": [str(store) for store in stores], **report},
                               indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit max-loser WP by source probability series.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--output-dir", type=Path, default=_REPO / "data" / "ab_reports")
    args = parser.parse_args(argv)
    stores, records = [], []
    for store in candidate_dirs(args.cache_root):
        loaded = load_records(store)
        if loaded:
            stores.append(store)
            records.extend(loaded)
    if not stores:
        print("NO PARSEABLE TICK STORE")
        return 0
    report = audit(records)
    print("STORES: " + ", ".join(str(store) for store in stores))
    print(render(report))
    print("REPORT: %s" % write_report(report, stores, args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
