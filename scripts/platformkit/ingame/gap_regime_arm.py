"""Leak-free per-regime recalibration experiment for the ARM A probabilities."""
from __future__ import annotations

import argparse
import json
import logging
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
_LOGGER = logging.getLogger(__name__)


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


def _fold_date_fn(fit_window: str, ticks: Sequence[Mapping[str, Any]]):
    """tick_date (default, unchanged): each row's own date. game_first_date (S36):
    each row's GAME's earliest tick date across the WHOLE input sequence (not
    just the in-window/required-field subset actually scored), so a game never
    splits across a fold boundary -- removes the UTC-midnight self-leak."""
    if fit_window not in ("tick_date", "game_first_date"):
        raise ValueError("fit_window must be 'tick_date' or 'game_first_date'")
    if fit_window == "tick_date":
        return _date
    game_dates: dict[str, str] = {}
    for row in ticks:
        game, date = str(row["game"]), _date(row)
        if game not in game_dates or date < game_dates[game]:
            game_dates[game] = date
    return lambda row: game_dates[str(row["game"])]


def _check_disjoint(train_games: set[str], test_games: set[str], fit_window: str) -> set[str]:
    """Return the overlapping (leaked) games between a fold's train and test
    sets. fit_window="game_first_date" (the S36 bar): raises AssertionError on
    any overlap -- game-disjointness is enforced, not merely reported.
    fit_window="tick_date" (legacy default): never raises; the caller counts
    the returned leaked games instead so existing default-mode readers keep
    running unbroken (S36 correction, orchestrator decision)."""
    leaked = train_games & test_games
    if fit_window == "game_first_date":
        assert not leaked, "fold games not disjoint (self-leak)"
    return leaked


def evaluate(ticks: Sequence[Mapping[str, Any]], *, min_n: int = 200,
             bootstrap_iterations: int = 300, seed: int = 20260831,
             fit_window: str = "tick_date") -> dict[str, Any]:
    """Walk forward by game date, fitting each calibration map on prior games
    only. fit_window: see _fold_date_fn. Default "tick_date" is byte-identical
    to pre-S36 behavior (its Brier/fold numbers never move); "game_first_date"
    is the opt-in leak-free mode. self_leak_ticks/self_leak_pct: how many
    scored ticks (and what pct) had their own game's outcome already in that
    fold's train set -- always 0 in game_first_date mode (assert-enforced), a
    counted non-fatal warning in tick_date mode (S36 correction)."""
    required = {"game", "model_prob", "market_prob", "outcome"}
    usable = [dict(row) for row in ticks if required.issubset(row) and row.get("in_window", True)]
    if not usable:
        return {"status": "INSUFFICIENT", "folds": [], "bucket_table": [], "acceptance": None}
    fold_date = _fold_date_fn(fit_window, ticks)
    dates = sorted({fold_date(row) for row in usable})
    scored, folds, leak_ticks = [], [], 0
    for test_date in dates[1:]:
        train = [row for row in usable if fold_date(row) < test_date]
        test = [row for row in usable if fold_date(row) == test_date]
        train_games = {str(row["game"]) for row in train}
        test_games = {str(row["game"]) for row in test}
        fold = {"train_date_max": max((fold_date(row) for row in train), default=None),
                "test_date_min": test_date, "train_games": len(train_games), "test_games": len(test_games)}
        if not train or not test:
            fold["status"] = "INSUFFICIENT"
            folds.append(fold)
            continue
        assert fold["train_date_max"] < test_date, "walk-forward date ordering violated"
        leaked_games = _check_disjoint(train_games, test_games, fit_window)
        if leaked_games:
            leak_ticks += sum(1 for row in test if str(row["game"]) in leaked_games)
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
    self_leak_pct = round(100.0 * leak_ticks / len(scored), 2) if scored else 0.0
    if fit_window != "game_first_date" and leak_ticks:
        _LOGGER.warning("gap_regime_arm.evaluate: %d/%d scored ticks (%.2f pct) self-leak in "
                        "fit_window=%r mode; pass fit_window=\"game_first_date\" to remove (S36)",
                        leak_ticks, len(scored), self_leak_pct, fit_window)
    return {"status": "OK", "n_ticks": len(scored), "n_games": len({str(row["game"]) for row in scored}),
            "min_n": min_n, "fit_window": fit_window, "self_leak_ticks": leak_ticks,
            "self_leak_pct": self_leak_pct, "folds": folds, "bucket_table": table,
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
