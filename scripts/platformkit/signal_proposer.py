"""Mechanical, leak-safe signal grammar for the offline Signal Foundry.

Every grammar input is restricted to the signal_ensemble as-of whitelist.
The history operations use only prior player rows; same-game team means use
only already as-of teammate values.  Therefore no rule can introduce a
post-game value when its base columns satisfy the leak contract.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from scripts.platformkit import signal_foundry as foundry
from scripts.platformkit.signal_ensemble import build_ensemble_features
from scripts.platformkit.teacher_student_ab import expanding_folds


ASOF_SUFFIXES = ("_l5", "_l10", "_asof", "_7d", "_14d")
SAFE_COLUMNS = ("days_rest", "b2b", "speed_decline_ratio")


def asof_columns(matrix: pd.DataFrame, target: str) -> list[str]:
    """Return numeric columns permitted by signal_ensemble's leak contract."""
    blocked = {target, "gameId", "personId", "playerId", "gameDate", "date", "timestamp"}
    return [name for name in matrix if name not in blocked and pd.api.types.is_numeric_dtype(matrix[name])
            and (name.endswith(ASOF_SUFFIXES) or name.startswith("style_embedding_") or name in SAFE_COLUMNS)]


def _order(matrix: pd.DataFrame) -> pd.DataFrame:
    date = next((name for name in ("gameDate", "date", "timestamp") if name in matrix), None)
    if date is None or "personId" not in matrix:
        raise ValueError("matrix needs personId and gameDate for as-of history")
    keys = ["personId", date, *(["gameId"] if "gameId" in matrix else [])]
    return matrix.sort_values(keys, kind="mergesort")


def _history_z(base: str):
    def compute(matrix: pd.DataFrame) -> pd.Series:
        work = _order(matrix); values = pd.to_numeric(work[base], errors="coerce")
        prior = values.groupby(work["personId"], sort=False).shift(1)
        mean = prior.groupby(work["personId"], sort=False).transform(lambda x: x.expanding().mean())
        std = prior.groupby(work["personId"], sort=False).transform(lambda x: x.expanding().std())
        return ((values - mean) / std.replace(0, np.nan)).reindex(matrix.index)
    return compute


def _delta_l10(base: str):
    def compute(matrix: pd.DataFrame) -> pd.Series:
        work = _order(matrix); values = pd.to_numeric(work[base], errors="coerce")
        prior = values.groupby(work["personId"], sort=False).shift(1)
        l10 = prior.groupby(work["personId"], sort=False).transform(lambda x: x.rolling(10, min_periods=1).mean())
        return (values - l10).reindex(matrix.index)
    return compute


def _team_mean(base: str, team: str):
    def compute(matrix: pd.DataFrame) -> pd.Series:
        keys = [team, "gameId"] if "gameId" in matrix else [team, next(x for x in ("gameDate", "date", "timestamp") if x in matrix)]
        values = pd.to_numeric(matrix[base], errors="coerce")
        count = values.notna().groupby([matrix[key] for key in keys], sort=False).transform("sum")
        total = values.fillna(0).groupby([matrix[key] for key in keys], sort=False).transform("sum")
        return ((total - values) / (count - 1).replace(0, np.nan))
    return compute


def _product(left: str, right: str):
    return lambda matrix: pd.to_numeric(matrix[left], errors="coerce") * pd.to_numeric(matrix[right], errors="coerce")


def top_shap_pairs(path: Path, allowed: Sequence[str]) -> list[tuple[str, str]]:
    """Read ranked interaction pairs from newest foundry ledger records."""
    if not path.exists():
        return []
    allowed_set, pairs = set(allowed), []
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        values = record.get("candidate_interactions", record.get("shap_pairs", []))
        for value in values:
            pair = value.get("pair", []) if isinstance(value, dict) else value
            if len(pair) == 2 and pair[0] in allowed_set and pair[1] in allowed_set:
                item = (str(pair[0]), str(pair[1]))
                if item not in pairs:
                    pairs.append(item)
        if pairs:
            return pairs
    return pairs


def propose(matrix: pd.DataFrame, target: str, max_new: int = 20,
            ledger_path: Path | None = None) -> tuple[pd.DataFrame, list[foundry.SignalSpec]]:
    """Materialize and register at most ``max_new`` grammar candidates."""
    if max_new < 0:
        raise ValueError("max_new must be non-negative")
    bases = asof_columns(matrix, target); team = next((x for x in ("teamId", "team_id", "teamTricode", "teamAbbreviation") if x in matrix), None)
    path = ledger_path or foundry.LEDGER_PATH
    recipes: list[tuple[str, str, object]] = []
    for left, right in top_shap_pairs(path, bases):
        recipes.append(("interaction", left + "_x_" + right, _product(left, right)))
    for base in bases:
        recipes.extend([("zscore", base, _history_z(base)), ("delta_l10", base, _delta_l10(base))])
        if team is not None:
            recipes.append(("team_mean", base, _team_mean(base, team)))
    work, specs = matrix.copy(), []
    for rule, base, compute in recipes:
        if len(specs) >= max_new:
            break
        name = "prop_{0}_{1}".format(rule, base)
        if name in foundry.REGISTRY:
            continue
        spec = foundry.register(foundry.SignalSpec(name, "nba", "player_game", "mechanical as-of grammar", compute))
        work[name] = compute(work)
        specs.append(spec)
    return work, specs


def propose_and_battery(matrix: pd.DataFrame, target: str, folds: Sequence[tuple[np.ndarray, np.ndarray]],
                        max_new: int = 20, ledger_path: Path | None = None) -> dict[str, object]:
    """Generate, register, and evaluate capped proposals; every result is ledgered."""
    original_path = foundry.LEDGER_PATH
    if ledger_path is not None:
        foundry.LEDGER_PATH = ledger_path
    try:
        work, specs = propose(matrix, target, max_new, foundry.LEDGER_PATH)
        results = [foundry.evaluate_signal(work, target, foundry.SignalSpec(
            spec.name, spec.sport, spec.grain, spec.story, spec.name), folds) for spec in specs]
    finally:
        foundry.LEDGER_PATH = original_path
    return {"matrix": work, "specs": specs, "results": results}


def main() -> None:
    """Run the grammar against the standard as-of minutes matrix."""
    parser = argparse.ArgumentParser(); parser.add_argument("--max-new", type=int, default=20)
    args = parser.parse_args(); root = Path(os.environ.get("NBA_DATA_ROOT", "data")); nba = root / "nba"
    matrix, _ = build_ensemble_features(pd.read_parquet(nba / "player_tracking_features_asof.parquet"), pd.read_parquet(nba / "player_load_state_asof.parquet"), pd.read_parquet(nba / "player_embeddings_asof.parquet"), pd.read_parquet(root / "ab_reports" / "novel_metrics_players.parquet"))
    matrix = matrix.dropna(subset=["gameDate"]).sort_values(["gameDate", "gameId", "personId"], kind="mergesort").reset_index(drop=True)
    report = propose_and_battery(matrix, "minutes", list(expanding_folds(matrix)), args.max_new)
    print("proposed={0} evaluated={1}".format(len(report["specs"]), len(report["results"])))


if __name__ == "__main__":
    main()
