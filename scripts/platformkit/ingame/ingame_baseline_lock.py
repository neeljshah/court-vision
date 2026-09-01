"""Emit a paired, game-clustered baseline lock for settled in-game ticks.

Each interval is compared separately to zero (the market) and the stale prior.
``MATCH`` means neither comparison is behind. ``BEHIND`` means either interval
comparison is behind. ``INSUFFICIENT`` means clustered ESS is below the floor,
the DM comparison cannot be computed, or the interval spans both thresholds so
it cannot distinguish the prior from no market difference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size
from scripts.platformkit.ingame_replay_scoreboard import discover_store

_PRIOR_DELTA_BRIER = -0.047
_MIN_ESS = 30
_DEFAULT_CACHE = Path(os.environ.get(
    "NBA_CACHE_ROOT", r"C:\Users\neelj\nba-ai-system\data\cache"))
_MODEL_KEYS = ("model_prob", "model_probability", "probability", "prob")
_MARKET_KEYS = ("market_prob", "market_probability", "implied_prob")
_OUTCOME_KEYS = ("outcome", "settled_outcome", "result", "label")
_GAME_KEYS = ("game_id", "game_key", "market_id", "event_id")
_TIME_KEYS = ("ts", "timestamp", "captured_at", "created_at")


def _value(row: Dict[str, Any], keys: Iterable[str]) -> Any:
    return next((row[key] for key in keys if row.get(key) is not None), None)


def _probability(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0.0 <= number <= 1.0 else None


def _file_hash(paths: List[Path], store: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(store).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _source_rows(paths: Iterable[Path]) -> int:
    count = 0
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            count += sum(1 for _ in handle)
    return count


def _paired_rows(paths: Iterable[Path]) -> tuple[int, int, List[Dict[str, Any]]]:
    """Return settled, market-eligible, and paired rows without hiding misses."""
    settled = eligible = 0
    paired: List[Dict[str, Any]] = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                outcome = _probability(_value(row, _OUTCOME_KEYS))
                game, stamp = _value(row, _GAME_KEYS), _value(row, _TIME_KEYS)
                if outcome not in (0.0, 1.0) or game is None or stamp is None:
                    continue
                settled += 1
                market = _probability(_value(row, _MARKET_KEYS))
                if market is None:
                    continue
                eligible += 1
                model = _probability(_value(row, _MODEL_KEYS))
                if model is not None:
                    paired.append({"game": str(game), "timestamp": str(stamp),
                                   "model_prob": model, "market_prob": market,
                                   "outcome": outcome})
    return settled, eligible, paired


def _interval_comparison(ci95: tuple[float, float], threshold: float) -> str:
    """Classify a monotone loss-differential interval against one threshold."""
    lower, upper = ci95
    if upper < threshold:
        return "BEHIND"
    if lower >= threshold:
        return "MATCH"
    return "INSUFFICIENT"


def _verdict(ess: float, ci95: Optional[tuple[float, float]]) -> str:
    """Combine separate zero and stale-prior interval comparisons."""
    if ess < _MIN_ESS or ci95 is None:
        return "INSUFFICIENT"
    zero = _interval_comparison(ci95, 0.0)
    prior = _interval_comparison(ci95, _PRIOR_DELTA_BRIER)
    if zero == "BEHIND" or prior == "BEHIND":
        return "BEHIND"
    if zero == "INSUFFICIENT" and prior == "INSUFFICIENT":
        return "INSUFFICIENT"
    return "MATCH"


def summarize(store: Path) -> Dict[str, Any]:
    """Score one paired denominator and return its calibration fingerprint."""
    paths = sorted(store.rglob("*.jsonl"), key=lambda path: path.as_posix().lower())
    settled, eligible, paired = _paired_rows(paths)
    stamps = [row["timestamp"] for row in paired]
    losses = [(row["market_prob"] - row["outcome"]) ** 2 -
              (row["model_prob"] - row["outcome"]) ** 2 for row in paired]
    games = [row["game"] for row in paired]
    model_brier = (sum((row["model_prob"] - row["outcome"]) ** 2 for row in paired) /
                   len(paired) if paired else None)
    market_brier = (sum((row["market_prob"] - row["outcome"]) ** 2 for row in paired) /
                    len(paired) if paired else None)
    ess_summary = (effective_sample_size(pd.DataFrame({"game": games,
                                                        "loss_differential": losses}))
                   if paired else {"n_games": 0, "n_eff": 0.0})
    dm = diebold_mariano(losses, games) if len(set(games)) >= 2 else None
    ci95 = dm.ci95 if dm is not None else None
    ess = float(ess_summary["n_eff"])
    vs_market = _interval_comparison(ci95, 0.0) if ci95 is not None else "INSUFFICIENT"
    vs_stale_prior = (_interval_comparison(ci95, _PRIOR_DELTA_BRIER)
                       if ci95 is not None else "INSUFFICIENT")
    return {
        "corpus": {"file_count": len(paths), "source_row_count": _source_rows(paths),
                   "settled_tick_count": settled, "eligible_tick_count": eligible,
                   "paired_tick_count": len(paired),
                   "dropped_missing_model_prob_count": eligible - len(paired),
                   "n_games": int(ess_summary["n_games"]),
                   "date_range": {"min": min(stamps)[:10] if stamps else None,
                                  "max": max(stamps)[:10] if stamps else None},
                   "file_hash": _file_hash(paths, store)},
        "prior_delta_brier": _PRIOR_DELTA_BRIER, "model_brier": model_brier,
        "market_brier": market_brier,
        "delta_brier": market_brier - model_brier if paired else None,
        "n_games": int(ess_summary["n_games"]), "ess": ess,
        "dm_ci95": list(ci95) if ci95 is not None else None,
        "vs_market": vs_market, "vs_stale_prior": vs_stale_prior,
        "verdict": _verdict(ess, ci95),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Lock the paired settled-tick Brier baseline.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    args = parser.parse_args(argv)
    store = discover_store(args.cache_root)
    if store is None:
        report: Dict[str, Any] = {"corpus": {"file_count": 0, "source_row_count": 0,
            "settled_tick_count": 0, "eligible_tick_count": 0, "paired_tick_count": 0,
            "dropped_missing_model_prob_count": 0, "n_games": 0,
            "date_range": {"min": None, "max": None}, "file_hash": None},
            "prior_delta_brier": _PRIOR_DELTA_BRIER, "model_brier": None,
            "market_brier": None, "delta_brier": None, "n_games": 0, "ess": 0.0,
            "dm_ci95": None, "vs_market": "INSUFFICIENT",
            "vs_stale_prior": "INSUFFICIENT", "verdict": "INSUFFICIENT"}
    else:
        report = {"store": str(store), **summarize(store)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
