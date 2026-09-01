"""Regime-specific isotonic calibration with conservative global fallback."""
from __future__ import annotations

import argparse
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.platformkit.brier_decomposition import decompose
from scripts.platformkit.ingame_replay_scoreboard import discover_store, load_ticks
from scripts.platformkit.serving_calibration import ServingCalibrator

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = Path(os.environ.get(
    "NBA_CACHE_ROOT",
    os.path.join(os.environ.get("NBA_DATA_ROOT", "data"), "cache")))
_GLOBAL = "GLOBAL"


def _records(df: Any) -> list[Mapping[str, Any]]:
    if hasattr(df, "to_dict"):
        return list(df.to_dict("records"))
    return list(df)


def _first(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    return next((row[name] for name in names if row.get(name) not in (None, "")), None)


def _month(row: Mapping[str, Any]) -> str | None:
    value = _first(row, ("season_month", "month"))
    if value is not None:
        return str(value)
    stamp = _first(row, ("timestamp", "ts", "date", "game_date"))
    if stamp is None:
        return None
    try:
        return "%02d" % datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).month
    except ValueError:
        return None


def buckets(df: Any) -> list[str]:
    """Assign stable combined regime keys from every available regime field."""
    rows = _records(df)
    probabilities = [float(_first(row, ("model_prob", "pred", "prediction"))) for row in rows]
    order = sorted(range(len(rows)), key=lambda index: probabilities[index])
    terciles = [0] * len(rows)
    for rank, index in enumerate(order):
        terciles[index] = min(2, 3 * rank // max(1, len(rows))) + 1
    keys: list[str] = []
    for index, row in enumerate(rows):
        parts = []
        phase = _first(row, ("game_phase", "phase", "period", "quarter", "inning"))
        if phase is not None:
            parts.append("phase=%s" % phase)
        b2b = _first(row, ("b2b", "is_b2b", "back_to_back"))
        rest = _first(row, ("rest_state", "rest_days", "days_rest"))
        if b2b is not None and str(b2b).lower() in ("1", "true", "yes", "b2b"):
            parts.append("rest=B2B")
        elif rest is not None:
            try:
                parts.append("rest=%s" % ("RESTED" if float(rest) >= 2 else "NORMAL"))
            except (TypeError, ValueError):
                parts.append("rest=%s" % rest)
        month = _month(row)
        if month is not None:
            parts.append("month=%s" % month)
        parts.append("confidence=T%d" % terciles[index])
        keys.append("|".join(parts))
    return keys


def fit_per_regime(preds: Sequence[float], outcomes: Sequence[float], keys: Sequence[str],
                   min_n: int = 200) -> dict[str, ServingCalibrator]:
    """Fit a global map and use it for regime buckets below ``min_n``."""
    if len(preds) != len(outcomes) or len(preds) != len(keys) or not preds:
        raise ValueError("preds, outcomes, and keys must be non-empty equal-length vectors")
    global_fit = ServingCalibrator()
    global_fit.fit(preds, outcomes)
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, key in enumerate(keys):
        grouped[str(key)].append(index)
    fits = {_GLOBAL: global_fit}
    for key, indices in grouped.items():
        if len(indices) < min_n:
            fits[key] = global_fit
            continue
        calibrator = ServingCalibrator()
        calibrator.fit([preds[index] for index in indices], [outcomes[index] for index in indices])
        fits[key] = calibrator
    return fits


def heterogeneity(preds: Sequence[float], outcomes: Sequence[float], keys: Sequence[str],
                  min_n: int = 200) -> dict[str, Any]:
    """Compare bucket reliability to global-only reliability and flag residual bias."""
    if len(preds) != len(outcomes) or len(preds) != len(keys) or not preds:
        raise ValueError("preds, outcomes, and keys must be non-empty equal-length vectors")
    global_stats = decompose(preds, outcomes)
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, key in enumerate(keys):
        grouped[str(key)].append(index)
    rows = []
    for key, indices in sorted(grouped.items()):
        bucket_preds = [float(preds[index]) for index in indices]
        bucket_outcomes = [float(outcomes[index]) for index in indices]
        stats = decompose(bucket_preds, bucket_outcomes)
        residual = sum(bucket_outcomes) / len(indices) - sum(bucket_preds) / len(indices)
        variance = sum(value * (1.0 - value) for value in bucket_preds) / len(indices) ** 2
        z_score = residual / math.sqrt(variance) if variance else 0.0
        significant = len(indices) >= min_n and abs(z_score) >= 1.959963984540054
        rows.append({"bucket": key, "n": len(indices), "reliability": stats["reliability"],
                     "global_reliability": global_stats["reliability"],
                     "reliability_gap": stats["reliability"] - global_stats["reliability"],
                     "mean_residual": residual, "z_score": z_score,
                     "status": "SIGNIFICANT" if significant else "OK"})
    return {"global_reliability": global_stats["reliability"], "buckets": rows}


def report(rows: Sequence[Mapping[str, Any]], min_n: int = 200) -> dict[str, Any]:
    """Fit all available regimes and return serializable diagnostics."""
    keys = buckets(rows)
    preds = [float(_first(row, ("model_prob", "pred", "prediction"))) for row in rows]
    outcomes = [float(_first(row, ("outcome", "label", "result"))) for row in rows]
    fits = fit_per_regime(preds, outcomes, keys, min_n=min_n)
    result = heterogeneity(preds, outcomes, keys, min_n=min_n)
    result["tick_count"] = len(rows)
    result["min_n"] = min_n
    result["fit_source"] = {key: (_GLOBAL if fit is fits[_GLOBAL] else key) for key, fit in fits.items() if key != _GLOBAL}
    return result


def render(result: Mapping[str, Any]) -> str:
    lines = ["REGIME | N | RELIABILITY_GAP | Z | STATUS"]
    for row in result["buckets"]:
        lines.append("%s | %d | %.6f | %.3f | %s" %
                     (row["bucket"], row["n"], row["reliability_gap"], row["z_score"], row["status"]))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report regime calibration heterogeneity.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--min-n", type=int, default=200)
    parser.add_argument("--output", type=Path, default=_REPO / "data" / "ab_reports" / "regime_calibration.json")
    args = parser.parse_args(argv)
    store = discover_store(args.cache_root)
    if store is None:
        print("NO PARSEABLE TICK STORE")
        return 0
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), "store": str(store),
              **report(load_ticks(store), min_n=args.min_n)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(render(result))
    print("REPORT: %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
