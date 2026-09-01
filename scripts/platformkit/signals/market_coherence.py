"""Backward-looking overround, Shin and related-market coherence features."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import timedelta
from typing import Any, Iterable, Mapping

from scripts.platformkit.signals.market_micro_asof import (
    HORIZON_SECONDS, MAX_CROSS_LEG_AGE_SECONDS, _normalise, _timestamp,
)

OUTPUT_COLUMNS = ("overround_level", "shin_z_estimate", "related_market_coherence")
DEFAULT_SPREAD_SD = 13.86


def _nan() -> float:
    return float("nan")


def _raw_implied(record: Mapping[str, Any]) -> float | None:
    for key in ("implied_prob", "raw_implied_prob", "market_prob"):
        try:
            value = float(record[key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value) and 0.0 < value <= 1.0:
            return value
    try:
        odds = float(record["decimal_odds"])
    except (KeyError, TypeError, ValueError):
        return None
    return 1.0 / odds if odds > 1.0 else None


def estimate_shin_z(implied_probabilities: Iterable[float]) -> float:
    """Estimate Shin's insider parameter by bisection; invalid books return NaN."""
    values: list[float] = []
    for value in implied_probabilities:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if 0.0 < parsed <= 1.0 and math.isfinite(parsed):
            values.append(parsed)
    booksum = sum(values)
    if len(values) < 2 or not math.isfinite(booksum):
        return _nan()
    if booksum <= 1.0:
        return 0.0

    def fair_sum(z: float) -> float:
        if z == 0.0:
            return booksum
        return sum((math.sqrt(z * z + 4.0 * (1.0 - z) * value * value / booksum) - z)
                   / (2.0 * (1.0 - z)) for value in values)

    lo, hi = 0.0, 0.5
    if fair_sum(hi) > 1.0:
        return 0.5
    for _ in range(60):
        middle = (lo + hi) / 2.0
        if fair_sum(middle) > 1.0:
            lo = middle
        else:
            hi = middle
    return (lo + hi) / 2.0


def _latest(records: list[dict[str, Any]], reference) -> dict[str, Any] | None:
    eligible = [record for record in records if record["captured_at"] <= reference]
    return max(eligible, key=lambda record: record["captured_at"]) if eligible else None


def _spread_probability(record: Mapping[str, Any]) -> float | None:
    for key in ("spread_implied_prob", "spread_win_prob"):
        try:
            probability = float(record[key])
        except (KeyError, TypeError, ValueError):
            continue
        if 0.0 <= probability <= 1.0:
            return probability
    try:
        line = float(record["line"])
        deviation = float(record.get("spread_sd", DEFAULT_SPREAD_SD))
    except (KeyError, TypeError, ValueError):
        return None
    if deviation <= 0.0 or not math.isfinite(line):
        return None
    return statistics.NormalDist().cdf(-line / deviation)


def build_features(records: Iterable[Mapping[str, Any]], *, horizon_seconds: int = HORIZON_SECONDS) -> list[dict[str, Any]]:
    """Return frozen market-level rows; stale legs remain explicit NaNs."""
    raw_records = list(records)
    normalised = _normalise(raw_records)
    raw_by_key: dict[tuple[str, str, str, str, str, object], list[dict[str, Any]]] = defaultdict(list)
    for raw in raw_records:
        captured, commence, game_id = _timestamp(raw.get("captured_at")), _timestamp(raw.get("commence_time")), raw.get("game_id")
        if captured is not None and commence is not None and game_id not in (None, "") and captured < commence:
            parsed_raw = dict(raw)
            parsed_raw["captured_at"] = captured
            raw_by_key[(str(raw.get("sport", "")), str(game_id), str(raw.get("market_type", "")), str(raw.get("side", "")), str(raw.get("book", "")), commence)].append(parsed_raw)
    market_groups: dict[tuple[str, str, str, str, object], list[dict[str, Any]]] = defaultdict(list)
    for record in normalised:
        market_groups[(record["sport"], record["game_id"], record["market_type"], record["book"], record["commence_time"])].append(record)
    output: list[dict[str, Any]] = []
    for (sport, game_id, market, book, commence), legs in sorted(market_groups.items()):
        reference = commence - timedelta(seconds=horizon_seconds)
        latest_legs = [_latest([leg for leg in legs if leg["side"] == side], reference)
                       for side in sorted({leg["side"] for leg in legs})]
        if not any(latest_legs):
            continue
        freshest = max(leg["captured_at"] for leg in latest_legs if leg is not None)
        stale = any(leg is None or (reference - leg["captured_at"]).total_seconds() > MAX_CROSS_LEG_AGE_SECONDS
                    for leg in latest_legs)
        implied: list[float] = []
        for leg in latest_legs:
            if leg is None:
                continue
            source = _latest(raw_by_key[(sport, game_id, market, leg["side"], book, commence)], reference)
            value = _raw_implied(source or {})
            if value is not None:
                implied.append(value)
        overround = sum(implied) if len(implied) == len(latest_legs) and not stale else _nan()
        row: dict[str, Any] = {
            "sport": sport, "game_id": game_id, "market_type": market, "book": book,
            "commence_time": commence.isoformat(), "as_of": reference.isoformat(),
            "overround_level": overround,
            "shin_z_estimate": estimate_shin_z(implied) if math.isfinite(overround) else _nan(),
            "related_market_coherence": _nan(),
        }
        output.append(row)
    by_game_book: dict[tuple[str, str, str, object], list[dict[str, Any]]] = defaultdict(list)
    for record in normalised:
        by_game_book[(record["sport"], record["game_id"], record["book"], record["commence_time"])].append(record)
    for row in output:
        key = (row["sport"], row["game_id"], row["book"], _timestamp(row["commence_time"]))
        market_rows = by_game_book[key]
        reference = _timestamp(row["as_of"])
        if reference is None:
            continue
        money = _latest([record for record in market_rows if record["market_type"] == "moneyline" and record["side"] == "home"], reference)
        spread = _latest([record for record in market_rows if record["market_type"] == "spread" and record["side"] == "home"], reference)
        if money is None or spread is None or abs((money["captured_at"] - spread["captured_at"]).total_seconds()) > MAX_CROSS_LEG_AGE_SECONDS:
            continue
        source = _latest(raw_by_key[(row["sport"], row["game_id"], "spread", "home", row["book"], key[3])], reference)
        probability = _spread_probability(source or {})
        if probability is not None:
            row["related_market_coherence"] = probability - money["devigged_prob"]
    return output


__all__ = ["OUTPUT_COLUMNS", "DEFAULT_SPREAD_SD", "estimate_shin_z", "build_features"]
