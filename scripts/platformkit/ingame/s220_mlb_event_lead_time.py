"""Read-only S220 MLB event-to-line lead-time measurement."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

FROZEN_MOVE_THRESHOLD = 0.004
WINDOW_SEC = 120.0
MAX_FILE_BYTES = 300 * 1024 * 1024
EVENT_CLASSES = ("run_scored", "out_recorded", "pitching_change")
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVENT_DIR = ROOT / "data" / "domains" / "mlb" / "gumbo_live"
DEFAULT_TICK_DIR = ROOT / "data" / "cache" / "ingame_grade" / "mlb"


def _stamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        point = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        for pattern in ("%Y%m%d_%H%M%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                point = datetime.strptime(value, pattern).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                point = None
        if point is None:
            return None
    return point if point.tzinfo else point.replace(tzinfo=timezone.utc)


def _jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        return []
    def rows() -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    yield item
    return rows()


def _quantile(values: Sequence[float], fraction: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(int(fraction * len(ordered)), len(ordered) - 1)], 3)


def cadence(tick_dir: Path) -> Dict[str, Any]:
    """Measure all MLB tick gaps without loading more than one file at once."""
    gaps: List[float] = []
    n_ticks = n_games = 0
    for path in sorted(tick_dir.glob("*.jsonl")) if tick_dir.is_dir() else []:
        points = [point for point in (_stamp(row.get("ts")) for row in _jsonl(path))
                  if point is not None]
        points.sort()
        if points:
            n_games += 1
            n_ticks += len(points)
        gaps.extend((b - a).total_seconds() for a, b in zip(points, points[1:])
                    if 0.0 < (b - a).total_seconds() <= 900.0)
    return {"n_games": n_games, "n_ticks": n_ticks, "gap_p50_sec": _quantile(gaps, 0.5),
            "gap_p90_sec": _quantile(gaps, 0.9), "gap_max_sec": round(max(gaps), 3) if gaps else None}


def events_from_gumbo(rows: Iterable[Dict[str, Any]]) -> List[Tuple[str, datetime]]:
    """Derive the three frozen event classes from adjacent compact GUMBO states."""
    states = sorted(rows, key=lambda row: str(row.get("captured_at") or row.get("ts") or ""))
    events: List[Tuple[str, datetime]] = []
    prior: Optional[Dict[str, Any]] = None
    for row in states:
        event_ts = _stamp(row.get("ts"))
        if prior is not None and event_ts is not None:
            old_runs = int(prior.get("score_home", 0) or 0) + int(prior.get("score_away", 0) or 0)
            new_runs = int(row.get("score_home", 0) or 0) + int(row.get("score_away", 0) or 0)
            if new_runs > old_runs:
                events.append(("run_scored", event_ts))
            if int(row.get("outs", 0) or 0) > int(prior.get("outs", 0) or 0):
                events.append(("out_recorded", event_ts))
            if row.get("pitcher_id") and prior.get("pitcher_id") and row["pitcher_id"] != prior["pitcher_id"]:
                events.append(("pitching_change", event_ts))
        prior = row
    return events


def _lead(anchor: datetime, ticks: Sequence[Tuple[datetime, float]]) -> Tuple[Optional[float], bool]:
    before = [price for stamp, price in ticks if stamp <= anchor]
    if not before:
        return None, False
    baseline = before[-1]
    for stamp, price in ticks:
        seconds = (stamp - anchor).total_seconds()
        if 0.0 < seconds <= WINDOW_SEC and abs(price - baseline) > FROZEN_MOVE_THRESHOLD:
            return round(seconds, 3), False
    return None, True


def _placebo_anchor(event_ts: datetime, all_events: Sequence[datetime],
                    ticks: Sequence[Tuple[datetime, float]]) -> Optional[datetime]:
    for stamp, _ in reversed(ticks):
        if stamp >= event_ts - timedelta(seconds=WINDOW_SEC):
            continue
        if all(abs((stamp - other).total_seconds()) > WINDOW_SEC for other in all_events):
            return stamp
    return None


def _tick_rows(path: Path) -> List[Tuple[datetime, float]]:
    out = []
    for row in _jsonl(path):
        stamp = _stamp(row.get("ts"))
        value = row.get("market_prob")
        if stamp is not None and isinstance(value, (int, float)) and 0.0 <= value <= 1.0:
            out.append((stamp, float(value)))
    return sorted(out)


def analyze(event_dir: Path = DEFAULT_EVENT_DIR, tick_dir: Path = DEFAULT_TICK_DIR) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Join matching game files and retain every event, including right-censored rows."""
    floor = cadence(tick_dir)
    records: List[Dict[str, Any]] = []
    clusters = set()
    for event_path in sorted(event_dir.glob("*.jsonl")) if event_dir.is_dir() else []:
        tick_path = tick_dir / event_path.name
        ticks = _tick_rows(tick_path)
        if not ticks:
            continue
        events = events_from_gumbo(_jsonl(event_path))
        all_times = [stamp for _, stamp in events]
        for kind, event_ts in events:
            lead, censored = _lead(event_ts, ticks)
            records.append({"event_class": kind, "series": "event", "game_id": event_path.stem,
                            "event_ts": event_ts.isoformat(), "lead_time_sec": lead,
                            "right_censored": censored, "observation_floor_sec": floor["gap_p50_sec"]})
            clusters.add(event_path.stem)
            placebo = _placebo_anchor(event_ts, all_times, ticks)
            if placebo is not None:
                lead, censored = _lead(placebo, ticks)
                records.append({"event_class": kind, "series": "placebo", "game_id": event_path.stem,
                                "event_ts": placebo.isoformat(), "lead_time_sec": lead,
                                "right_censored": censored, "observation_floor_sec": floor["gap_p50_sec"]})
    classes = {}
    for kind in EVENT_CLASSES:
        event_rows = [row for row in records if row["event_class"] == kind and row["series"] == "event"]
        placebo_rows = [row for row in records if row["event_class"] == kind and row["series"] == "placebo"]
        def summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
            seen = [float(row["lead_time_sec"]) for row in rows if row["lead_time_sec"] is not None]
            return {"n": len(rows), "right_censored": sum(bool(row["right_censored"]) for row in rows),
                    "p50_sec": _quantile(seen, 0.5), "p90_sec": _quantile(seen, 0.9),
                    "max_sec": round(max(seen), 3) if seen else None}
        classes[kind] = {"event": summary(event_rows), "placebo": summary(placebo_rows),
                         "observation_floor_sec": floor["gap_p50_sec"]}
    report = {"component": "s220_mlb_event_lead_time", "frozen_move_threshold": FROZEN_MOVE_THRESHOLD,
              "window_sec": WINDOW_SEC, "cadence": floor, "game_clusters": len(clusters),
              "classes": classes, "verdict": "CLOSED AT LIMIT" if len(clusters) < 30 else "MEASURED"}
    return report, records


def write(report: Dict[str, Any], records: List[Dict[str, Any]], out_json: Path, out_csv: Path) -> None:
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    with out_csv.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["event_class", "series", "game_id", "event_ts", "lead_time_sec", "right_censored", "observation_floor_sec"])
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="S220 read-only MLB lead-time measurement")
    parser.add_argument("--event-dir", type=Path, default=DEFAULT_EVENT_DIR)
    parser.add_argument("--tick-dir", type=Path, default=DEFAULT_TICK_DIR)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    args = parser.parse_args()
    report, records = analyze(args.event_dir, args.tick_dir)
    write(report, records, args.out_json, args.out_csv)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
