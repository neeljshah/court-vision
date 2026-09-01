"""Leak-free per-regime recalibration experiment for the ARM A probabilities."""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.platformkit.regime_calibration import buckets, fit_per_regime
from scripts.platformkit.serving_calibration import ServingCalibrator

_GLOBAL = "GLOBAL"
_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_CACHE = Path(r"C:\Users\neelj\nba-ai-system\data\cache")


def _date(row: Mapping[str, Any]) -> str:
    value = row.get("game_date") or row.get("date") or row.get("timestamp") or row.get("ts")
    if value is None:
        raise ValueError("each tick requires game_date, date, timestamp, or ts")
    return str(value)[:10]


def _brier(probabilities: Sequence[float], outcomes: Sequence[float]) -> float:
    if not probabilities:
        raise ValueError("Brier score requires at least one value")
    return sum((float(probability) - float(outcome)) ** 2
               for probability, outcome in zip(probabilities, outcomes)) / len(probabilities)


def _month_confidence_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Keep the existing regime key builder to the E2 month/confidence fields."""
    return [{"model_prob": float(row["model_prob"]),
             "season_month": row.get("season_month") or row.get("month") or _date(row)[5:7]}
            for row in rows]


def _apply(fits: Mapping[str, ServingCalibrator], keys: Sequence[str],
           probabilities: Sequence[float]) -> tuple[list[float], list[str]]:
    calibrated, sources = [], []
    global_fit = fits[_GLOBAL]
    for key, probability in zip(keys, probabilities):
        fit = fits.get(key, global_fit)
        calibrated.extend(fit.apply([float(probability)]))
        sources.append(_GLOBAL if fit is global_fit else str(key))
    return calibrated, sources


def _bootstrap_movement(rows: Sequence[Mapping[str, Any]], iterations: int, seed: int) -> list[float] | None:
    games: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        games[str(row["game"])].append(row)
    groups = list(games.values())
    if not groups:
        return None
    rng, values = random.Random(seed), []
    for _ in range(iterations):
        sample = [row for _ in groups for row in rng.choice(groups)]
        before = _brier([row["model_prob"] for row in sample], [row["outcome"] for row in sample])
        after = _brier([row["arm_b_prob"] for row in sample], [row["outcome"] for row in sample])
        values.append(before - after)
    values.sort()
    return [values[int(.05 * (len(values) - 1))], values[int(.95 * (len(values) - 1))]]


def _bucket_table(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["regime"])] .append(row)
    table = []
    for regime, group in sorted(grouped.items()):
        arm_a = _brier([row["model_prob"] for row in group], [row["outcome"] for row in group])
        arm_b = _brier([row["arm_b_prob"] for row in group], [row["outcome"] for row in group])
        sources = sorted(set(str(row["fit_source"]) for row in group))
        table.append({"regime": regime, "n_ticks": len(group),
                      "n_games": len({str(row["game"]) for row in group}),
                      "arm_a_brier": arm_a, "arm_b_brier": arm_b,
                      "movement": arm_a - arm_b, "fit_source": ",".join(sources)})
    return table


def _acceptance(rows: Sequence[Mapping[str, Any]], table: Sequence[Mapping[str, Any]], ci: list[float] | None) -> dict[str, Any]:
    arm_b = _brier([row["arm_b_prob"] for row in rows], [row["outcome"] for row in rows])
    market = _brier([row["market_prob"] for row in rows], [row["outcome"] for row in rows])
    gap = arm_b - market
    no_bucket_regression = all(float(row["arm_b_brier"]) - float(row["arm_a_brier"]) <= .005 for row in table)
    ci_excludes_zero = ci is not None and ci[0] > 0.0
    passed = gap <= .042 and ci_excludes_zero and no_bucket_regression
    return {"gap": gap, "market_brier": market, "arm_b_brier": arm_b,
            "movement_ci_90": ci, "ci_excludes_zero": ci_excludes_zero,
            "no_bucket_regression": no_bucket_regression,
            "status": "PASS" if passed else "REJECT"}


def evaluate(ticks: Sequence[Mapping[str, Any]], *, min_n: int = 200,
             bootstrap_iterations: int = 300, seed: int = 20260831) -> dict[str, Any]:
    """Walk forward by game date, fitting each calibration map on prior games only."""
    required = {"game", "model_prob", "market_prob", "outcome"}
    usable = [dict(row) for row in ticks if required.issubset(row) and row.get("in_window", True)]
    if not usable:
        return {"status": "INSUFFICIENT", "folds": [], "bucket_table": [], "acceptance": None}
    dates = sorted({_date(row) for row in usable})
    scored, folds = [], []
    for test_date in dates[1:]:
        train = [row for row in usable if _date(row) < test_date]
        test = [row for row in usable if _date(row) == test_date]
        train_games = {str(row["game"]) for row in train}
        test_games = {str(row["game"]) for row in test}
        fold = {"train_date_max": max((_date(row) for row in train), default=None),
                "test_date_min": test_date, "train_games": len(train_games), "test_games": len(test_games)}
        if not train or not test:
            fold["status"] = "INSUFFICIENT"
            folds.append(fold)
            continue
        assert fold["train_date_max"] < test_date, "walk-forward date ordering violated"
        train_keys = buckets(_month_confidence_rows(train))
        test_keys = buckets(_month_confidence_rows(test))
        fits = fit_per_regime([float(row["model_prob"]) for row in train],
                              [float(row["outcome"]) for row in train], train_keys, min_n=min_n)
        probabilities, sources = _apply(fits, test_keys, [float(row["model_prob"]) for row in test])
        for row, key, probability, source in zip(test, test_keys, probabilities, sources):
            scored.append({**row, "regime": key, "arm_b_prob": probability, "fit_source": source})
        fold.update({"status": "OK", "scored_ticks": len(test), "fitted_on_prior_games": True})
        folds.append(fold)
    if not scored:
        return {"status": "INSUFFICIENT", "folds": folds, "bucket_table": [], "acceptance": None}
    table = _bucket_table(scored)
    ci = _bootstrap_movement(scored, bootstrap_iterations, seed)
    return {"status": "OK", "n_ticks": len(scored), "n_games": len({str(row["game"]) for row in scored}),
            "min_n": min_n, "folds": folds, "bucket_table": table,
            "acceptance": _acceptance(scored, table, ci)}


def render(report: Mapping[str, Any]) -> str:
    """Render the required per-bucket calibration comparison in ASCII."""
    lines = ["REGIME | N_GAMES | N_TICKS | ARM_A | ARM_B | MOVEMENT | FIT_SOURCE"]
    for row in report.get("bucket_table", []):
        lines.append("%s | %d | %d | %.6f | %.6f | %.6f | %s" %
                     (row["regime"], row["n_games"], row["n_ticks"], row["arm_a_brier"],
                      row["arm_b_brier"], row["movement"], row["fit_source"]))
    acceptance = report.get("acceptance")
    if acceptance is not None:
        ci = acceptance["movement_ci_90"]
        interval = "-" if ci is None else "[%.6f, %.6f]" % (ci[0], ci[1])
        lines.append("GAP | %.6f | MOVEMENT_CI90 | %s | STATUS | %s" %
                     (acceptance["gap"], interval, acceptance["status"]))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate per-regime ARM A recalibration.")
    parser.add_argument("input", type=Path, help="ASCII JSON list of normalized ticks")
    parser.add_argument("--min-n", type=int, default=200)
    parser.add_argument("--output", type=Path, default=_REPO / ".planning" / "ingame" / "gap_regime_arm.json")
    args = parser.parse_args(argv)
    ticks = json.loads(args.input.read_text(encoding="ascii"))
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              **evaluate(ticks, min_n=args.min_n)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
