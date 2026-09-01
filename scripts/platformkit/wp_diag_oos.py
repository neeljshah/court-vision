"""Out-of-sample win-probability calibration diagnostics by sport."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.platformkit.ingame_replay_scoreboard import discover_store, load_ticks
from scripts.platformkit.brier_decomposition import decompose

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = Path(os.environ.get(
    "NBA_CACHE_ROOT",
    os.path.join(os.environ.get("NBA_DATA_ROOT", "data"), "cache")))
_Z_95 = 1.959963984540054


def _brier(pairs: Iterable[Tuple[float, float]]) -> Optional[float]:
    values = list(pairs)
    return (sum((prob - outcome) ** 2 for prob, outcome in values) / len(values)
            if values else None)


def _date(tick: Dict[str, Any]) -> str:
    """Return the UTC capture day from the normalized loader timestamp."""
    value = str(tick["timestamp"])
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10]


def _sport(tick: Dict[str, Any]) -> str:
    """Derive sport from the ticker/game prefix without a sport-specific registry."""
    value = str(tick.get("ticker") or tick["game"])
    for separator in (":", "_", "-", "/"):
        if separator in value:
            return value.split(separator, 1)[0].upper() or "UNKNOWN"
    return "UNKNOWN"


def _game_dates(ticks: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    dates: Dict[str, str] = {}
    for tick in ticks:
        dates[tick["game"]] = min(dates.get(tick["game"], _date(tick)), _date(tick))
    return dates


def _folds(dates: Sequence[str]) -> List[Tuple[List[str], List[str]]]:
    """Make at least three expanding-window folds when enough capture days exist."""
    ordered = sorted(set(dates))
    if len(ordered) < 4:
        return []
    fold_count = min(5, len(ordered) - 1)
    first_test = max(1, len(ordered) // (fold_count + 1))
    remaining = ordered[first_test:]
    folds: List[Tuple[List[str], List[str]]] = []
    for index in range(fold_count):
        start = index * len(remaining) // fold_count
        end = (index + 1) * len(remaining) // fold_count
        test = remaining[start:end]
        if test:
            train = ordered[:first_test + start]
            assert max(train) < min(test), "walk-forward date ordering violated"
            folds.append((train, test))
    return folds


def walk_forward_isotonic(ticks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Fit only past game ticks and score isotonic calibration on future games."""
    game_dates = _game_dates(ticks)
    folds = _folds(list(game_dates.values()))
    rows: List[Dict[str, Any]] = []
    pooled: List[Tuple[float, float, float]] = []
    for index, (train_dates, test_dates) in enumerate(folds, 1):
        train_games = {game for game, date in game_dates.items() if date in train_dates}
        test_games = {game for game, date in game_dates.items() if date in test_dates}
        train = [tick for tick in ticks if tick["game"] in train_games]
        test = [tick for tick in ticks if tick["game"] in test_games]
        row: Dict[str, Any] = {
            "fold": index, "train_date_max": max(train_dates), "test_date_min": min(test_dates),
            "train_games": len(train_games), "test_games": len(test_games), "test_ticks": len(test),
            "date_ordering_asserted": True,
        }
        outcomes = {tick["outcome"] for tick in train}
        if not train or not test or len(outcomes) < 2:
            row.update({"status": "INSUFFICIENT", "brier_before": None,
                        "brier_after": None, "delta": None})
        else:
            from sklearn.isotonic import IsotonicRegression
            model = IsotonicRegression(out_of_bounds="clip")
            model.fit([tick["model_prob"] for tick in train], [tick["outcome"] for tick in train])
            before = _brier((tick["model_prob"], tick["outcome"]) for tick in test)
            calibrated = model.predict([tick["model_prob"] for tick in test])
            after = _brier(zip(calibrated, (tick["outcome"] for tick in test)))
            row.update({"status": "OK", "brier_before": before, "brier_after": after,
                        "delta": before - after if before is not None and after is not None else None})
            pooled.extend((tick["model_prob"], prediction, tick["outcome"])
                          for tick, prediction in zip(test, calibrated))
        rows.append(row)
    before = _brier((raw, outcome) for raw, _, outcome in pooled)
    after = _brier((calibrated, outcome) for _, calibrated, outcome in pooled)
    return {"fold_count": len(rows), "folds": rows,
            "pooled": {"test_ticks": len(pooled), "brier_before": before, "brier_after": after,
                       "delta": before - after if before is not None and after is not None else None},
            "note": "ONLY OOS DELTAS COUNT; no isotonic model is scored on its fit ticks."}


def _wilson(successes: float, n: int) -> Tuple[Optional[float], Optional[float]]:
    if not n:
        return None, None
    proportion = successes / n
    denominator = 1.0 + _Z_95 ** 2 / n
    center = (proportion + _Z_95 ** 2 / (2 * n)) / denominator
    margin = _Z_95 * math.sqrt((proportion * (1 - proportion) + _Z_95 ** 2 / (4 * n)) / n) / denominator
    return center - margin, center + margin


def phase_reliability(ticks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Return phase-level reliability bins with Wilson 95 percent intervals."""
    phases: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for tick in ticks:
        phases[str(tick.get("phase") or "UNKNOWN")].append(tick)
    result: Dict[str, List[Dict[str, Any]]] = {}
    for phase, phase_ticks in sorted(phases.items()):
        bins: List[List[Dict[str, Any]]] = [[] for _ in range(10)]
        for tick in phase_ticks:
            bins[min(9, int(tick["model_prob"] * 10))].append(tick)
        rows = []
        for index, group in enumerate(bins):
            n = len(group)
            observed = sum(tick["outcome"] for tick in group) / n if n else None
            low, high = _wilson(sum(tick["outcome"] for tick in group), n)
            rows.append({"bin": "%0.1f-%0.1f" % (index / 10, (index + 1) / 10), "n": n,
                         "mean_predicted_prob": (sum(t["model_prob"] for t in group) / n if n else None),
                         "observed_win_freq": observed, "wilson_95_low": low,
                         "wilson_95_high": high, "status": "OK" if n >= 50 else "INSUFFICIENT"})
        result[phase] = rows
    return result


def diagnose(ticks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Split honest OOS calibration diagnostics by ticker-prefix sport."""
    sports: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for tick in ticks:
        sports[_sport(tick)].append(tick)
    return {"sports": {sport: {"tick_count": len(group),
                                "walk_forward_isotonic": walk_forward_isotonic(group),
                                "murphy_decomposition": decompose(
                                    (tick["model_prob"] for tick in group),
                                    (tick["outcome"] for tick in group)),
                                "phase_reliability": phase_reliability(group)}
                       for sport, group in sorted(sports.items())}}


def _number(value: Optional[float]) -> str:
    return "-" if value is None else "%.4f" % value


def render(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    for sport, section in report["sports"].items():
        iso = section["walk_forward_isotonic"]
        lines.extend(["SPORT: %s TICKS: %d" % (sport, section["tick_count"]), iso["note"],
                      "MURPHY: BRIER=%s REL=%s RES=%s UNC=%s" % tuple(
                          _number(section["murphy_decomposition"][key])
                          for key in ("brier", "reliability", "resolution", "uncertainty")),
                      "FOLD | TRAIN_MAX | TEST_MIN | N | BEFORE | AFTER | DELTA | STATUS"])
        for fold in iso["folds"]:
            lines.append("%d | %s | %s | %d | %s | %s | %s | %s" %
                         (fold["fold"], fold["train_date_max"], fold["test_date_min"], fold["test_ticks"],
                          _number(fold["brier_before"]), _number(fold["brier_after"]),
                          _number(fold["delta"]), fold["status"]))
        pooled = iso["pooled"]
        lines.append("POOLED OOS: N=%d BEFORE=%s AFTER=%s DELTA=%s" %
                     (pooled["test_ticks"], _number(pooled["brier_before"]),
                      _number(pooled["brier_after"]), _number(pooled["delta"])))
        for phase, rows in section["phase_reliability"].items():
            lines.extend(["PHASE: %s" % phase,
                          "BIN | N | MEAN_PRED | OBSERVED | WILSON_95 | STATUS"])
            for row in rows:
                lines.append("%s | %d | %s | %s | %s-%s | %s" %
                             (row["bin"], row["n"], _number(row["mean_predicted_prob"]),
                              _number(row["observed_win_freq"]), _number(row["wilson_95_low"]),
                              _number(row["wilson_95_high"]), row["status"]))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run OOS WP calibration diagnostics.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--output-dir", type=Path, default=_REPO / "data" / "ab_reports")
    args = parser.parse_args(argv)
    store = discover_store(args.cache_root)
    if store is None:
        print("NO PARSEABLE TICK STORE")
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {"generated_at": stamp, "store": str(store), **diagnose(load_ticks(store))}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / ("wp_oos_%s.json" % stamp)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(render(report))
    print("REPORT: %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
