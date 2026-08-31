"""Track OOS signal decay; McLean-Pontiff framing treats OOS decay as the rule.

This is evidence monitoring, not an edge claim.  Foundry trial lifts are grouped
by signal and dated from their ledger timestamps.  The fitted curve is only a
compact description of observed OOS lift history, never a shipping exemption.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
from scipy.optimize import curve_fit


FOUNDRY_LEDGER = Path(os.environ.get("SIGNAL_FOUNDRY_LEDGER", "data/ab_reports/foundry_ledger.jsonl"))
DECAY_LEDGER = Path(os.environ.get("ALPHA_DECAY_LEDGER", "data/ab_reports/decay_ledger.jsonl"))
MIN_POINTS = 6


def _when(item: dict[str, object]) -> datetime | None:
    for key in ("ts", "timestamp", "date", "gameDate"):
        value = item.get(key)
        if value is not None:
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                continue
    return None


def load_history(path: Path = FOUNDRY_LEDGER) -> dict[str, list[tuple[datetime, float]]]:
    """Load dated numeric lifts from a Signal Foundry JSONL ledger."""
    result: dict[str, list[tuple[datetime, float]]] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line); stamp = _when(item); lift = float(item["lift"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        signal = item.get("signal")
        if stamp is not None and isinstance(signal, str) and np.isfinite(lift):
            result.setdefault(signal, []).append((stamp, lift))
    for values in result.values():
        values.sort(key=lambda item: item[0])
    return result


def _curve(weeks: np.ndarray, amplitude: float, rate: float, floor: float) -> np.ndarray:
    return amplitude * np.exp(-rate * weeks) + floor


def _weekly(values: Iterable[tuple[datetime, float]]) -> tuple[np.ndarray, np.ndarray]:
    buckets: dict[datetime, list[float]] = {}
    for stamp, lift in values:
        start = stamp - timedelta(days=stamp.weekday())
        buckets.setdefault(start.replace(hour=0, minute=0, second=0, microsecond=0), []).append(lift)
    ordered = sorted(buckets.items())
    origin = ordered[0][0]
    return (np.asarray([(stamp - origin).days / 7.0 for stamp, _ in ordered]),
            np.asarray([np.mean(lifts) for _, lifts in ordered]))


def analyze_signal(signal: str, values: list[tuple[datetime, float]]) -> dict[str, object]:
    """Fit an exponential OOS lift curve and return a conservative status."""
    weeks, lifts = _weekly(values)
    result: dict[str, object] = {"signal": signal, "points": len(lifts)}
    if len(lifts) < MIN_POINTS:
        return {**result, "status": "INSUFFICIENT", "trend_4w": None, "half_life_weeks": None,
                "zero_crossing_weeks": None}
    recent_x, recent_y = weeks[-4:], lifts[-4:]
    trend = float(np.polyfit(recent_x, recent_y, 1)[0])
    guess = [float(lifts[0] - lifts[-1]), 0.1, float(lifts[-1])]
    try:
        params, _ = curve_fit(_curve, weeks, lifts, p0=guess,
                              bounds=([-np.inf, 0.0, -np.inf], [np.inf, np.inf, np.inf]), maxfev=20000)
        amplitude, rate, floor = (float(value) for value in params)
    except (RuntimeError, ValueError):
        return {**result, "status": "INSUFFICIENT", "trend_4w": trend, "half_life_weeks": None,
                "zero_crossing_weeks": None}
    half_life = float(np.log(2.0) / rate) if rate > 1e-8 else None
    ratio = -floor / amplitude if amplitude else -1.0
    crossing = float(-np.log(ratio) / rate) if rate > 1e-8 and 0.0 < ratio <= 1.0 else None
    status = "RETIRE" if crossing is not None and crossing < 8.0 else (
        "DECAYING" if trend < -1e-6 and rate > 1e-6 else "ACTIVE")
    return {**result, "status": status, "trend_4w": trend, "half_life_weeks": half_life,
            "zero_crossing_weeks": crossing, "fitted_lift": float(_curve(weeks[-1], amplitude, rate, floor))}


def append_reports(reports: Iterable[dict[str, object]], path: Path = DECAY_LEDGER) -> None:
    """Append one timestamped decay assessment per signal to the JSONL ledger."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for report in reports:
            handle.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **report}, allow_nan=False) + "\n")


def print_table(reports: Iterable[dict[str, object]]) -> None:
    """Print a compact ASCII table suitable for the Windows console."""
    rows = list(reports)
    print("signal                         points trend_4w half_life zero_cross status")
    for row in rows:
        def number(name: str) -> str:
            value = row.get(name)
            return "-" if value is None else "{0:.3f}".format(float(value))
        print("{0:<30} {1:>6} {2:>8} {3:>9} {4:>10} {5}".format(
            str(row["signal"])[:30], row["points"], number("trend_4w"), number("half_life_weeks"),
            number("zero_crossing_weeks"), row["status"]))


def main() -> None:
    """Assess every signal in the Foundry ledger and append the resulting snapshot."""
    reports = [analyze_signal(signal, values) for signal, values in sorted(load_history().items())]
    append_reports(reports)
    print_table(reports)


if __name__ == "__main__":
    main()
