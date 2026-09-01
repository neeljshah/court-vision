"""Backward-looking market microstructure features from the local tick archive.

Every output is frozen at ``commence_time - horizon_seconds`` (one hour by
default).  No helper searches beyond that point; this is the as-of contract.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

OUTPUT_COLUMNS = (
    "price_drift_T6_to_T1", "cross_book_dispersion", "quote_cadence_seconds",
    "realized_vol_of_prob", "jump_count_pregame",
)
HORIZON_SECONDS = 3600
T6_SECONDS = 6 * 3600
MAX_MEDIAN_CADENCE_SECONDS = 900
MAX_CROSS_LEG_AGE_SECONDS = 300


def _nan() -> float:
    return float("nan")


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _probability(value: Any) -> float | None:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    return probability if math.isfinite(probability) and 0.0 <= probability <= 1.0 else None


def _normalise(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for record in records:
        captured = _timestamp(record.get("captured_at"))
        commence = _timestamp(record.get("commence_time"))
        probability = _probability(record.get("devigged_prob"))
        game_id = record.get("game_id")
        if captured is None or commence is None or probability is None or game_id in (None, ""):
            continue
        if captured >= commence:
            continue
        output.append({
            "game_id": str(game_id), "sport": str(record.get("sport", "")),
            "market_type": str(record.get("market_type", "")),
            "side": str(record.get("side", "")), "book": str(record.get("book", "")),
            "captured_at": captured, "commence_time": commence, "devigged_prob": probability,
        })
    return output


def _latest_at_or_before(points: list[dict[str, Any]], at: datetime) -> dict[str, Any] | None:
    eligible = [point for point in points if point["captured_at"] <= at]
    return max(eligible, key=lambda point: point["captured_at"]) if eligible else None


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else _nan()


def _series_features(points: list[dict[str, Any]], reference: datetime) -> dict[str, float]:
    points = sorted((point for point in points if point["captured_at"] <= reference),
                    key=lambda point: point["captured_at"])
    cadence = [
        (later["captured_at"] - earlier["captured_at"]).total_seconds()
        for earlier, later in zip(points, points[1:])
        if later["captured_at"] > earlier["captured_at"]
    ]
    median_cadence = _median(cadence)
    result = {"quote_cadence_seconds": median_cadence}
    if len(points) < 2 or not math.isfinite(median_cadence) or median_cadence > MAX_MEDIAN_CADENCE_SECONDS:
        result.update({name: _nan() for name in (
            "price_drift_T6_to_T1", "realized_vol_of_prob", "jump_count_pregame")})
        return result
    t6 = _latest_at_or_before(points, reference - timedelta(seconds=T6_SECONDS - HORIZON_SECONDS))
    t1 = _latest_at_or_before(points, reference)
    result["price_drift_T6_to_T1"] = (
        t1["devigged_prob"] - t6["devigged_prob"] if t6 is not None and t1 is not None else _nan()
    )
    moves = [abs(later["devigged_prob"] - earlier["devigged_prob"])
             for earlier, later in zip(points, points[1:])]
    result["realized_vol_of_prob"] = math.sqrt(sum(move * move for move in moves)) / math.sqrt(len(moves))
    jumps = 0
    prior_moves: list[float] = []
    for move in moves:
        threshold = statistics.median(prior_moves) if prior_moves else None
        if threshold is not None and move > threshold:
            jumps += 1
        prior_moves.append(move)
    result["jump_count_pregame"] = float(jumps)
    return result


def build_features(records: Iterable[Mapping[str, Any]], *, horizon_seconds: int = HORIZON_SECONDS) -> list[dict[str, Any]]:
    """Return one frozen feature row per game/market/side at the requested horizon.

    The non-book features are the median of valid book-specific values.  A
    missing or stale cross-book leg produces NaN, never a value carried from a
    later tick.
    """
    groups: dict[tuple[str, str, str, str, str, datetime], list[dict[str, Any]]] = defaultdict(list)
    for point in _normalise(records):
        groups[(point["sport"], point["game_id"], point["market_type"], point["side"], point["book"], point["commence_time"])].append(point)
    collapsed: dict[tuple[str, str, str, str, datetime], list[tuple[str, dict[str, Any], dict[str, float]]]] = defaultdict(list)
    for (sport, game_id, market, side, book, commence), points in groups.items():
        reference = commence - timedelta(seconds=horizon_seconds)
        latest = _latest_at_or_before(points, reference)
        if latest is not None:
            collapsed[(sport, game_id, market, side, commence)].append((book, latest, _series_features(points, reference)))
    output: list[dict[str, Any]] = []
    for (sport, game_id, market, side, commence), book_rows in sorted(collapsed.items()):
        reference = commence - timedelta(seconds=horizon_seconds)
        values = {column: [features[column] for _book, _latest, features in book_rows
                           if math.isfinite(features[column])]
                  for column in OUTPUT_COLUMNS if column != "cross_book_dispersion"}
        book_ages = [(reference - latest["captured_at"]).total_seconds()
                     for _book, latest, _features in book_rows]
        fresh_probs = [latest["devigged_prob"] for _book, latest, _features in book_rows]
        row: dict[str, Any] = {
            "sport": sport, "game_id": game_id, "market_type": market, "side": side,
            "commence_time": commence.isoformat(), "as_of": reference.isoformat(),
            "cross_book_dispersion": (statistics.pstdev(fresh_probs)
                                      if len(fresh_probs) >= 2 and
                                      all(age <= MAX_CROSS_LEG_AGE_SECONDS for age in book_ages)
                                      else _nan()),
        }
        row.update({column: _median(values[column]) for column in values})
        output.append(row)
    return output


def load_archive(root: str | Path, sport: str | None = None) -> list[dict[str, Any]]:
    """Load valid JSONL records from ``line_history/<sport>/<date>.jsonl``."""
    base = Path(root)
    paths = sorted((base / sport).glob("*.jsonl")) if sport else sorted(base.glob("*/*.jsonl"))
    records: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                record.setdefault("sport", path.parent.name)
                records.append(record)
    return records


def build_archive_features(root: str | Path, sport: str | None = None) -> list[dict[str, Any]]:
    """Load the owned archive and apply the one-hour as-of feature contract."""
    return build_features(load_archive(root, sport))


__all__ = ["OUTPUT_COLUMNS", "HORIZON_SECONDS", "MAX_MEDIAN_CADENCE_SECONDS",
           "MAX_CROSS_LEG_AGE_SECONDS", "build_features", "load_archive", "build_archive_features"]
