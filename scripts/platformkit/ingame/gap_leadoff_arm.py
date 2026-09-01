"""Prior-only MLB leadoff conditioning arm with a fail-closed gate.

The table is fit only from completed historical half innings.  At runtime, the
condition is available when the second as-of state in a clean half inning shows
whether the leadoff batter reached base or made an out; it is absent at the next
half inning.  This module is offline and does not register or enable an arm.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import pandas as pd

from scripts.platformkit.ingame.ingame_gate_generic import gate_cross

_CACHE = Path(r"C:\Users\neelj\nba-ai-system\data\cache\ingame")
_OUTPUT = Path(r"C:\Users\neelj\nba-ai-system\data\frontend\ingame\leadoff_arm_gate_mlb.json")
_TRAIN_SEASONS = (2022, 2023)
_EVAL_SEASONS = (2024, 2025)
_LOCKED_BASELINE = {"delta_brier": -0.0343, "n_eff": 268}


def _number(row: Mapping[str, Any], name: str) -> Optional[float]:
    try:
        value = float(row[name])
    except (KeyError, TypeError, ValueError):
        return None
    return value


def _blocks(rows: Iterable[Mapping[str, Any]]) -> Iterable[list[dict[str, Any]]]:
    by_game: dict[str, list[dict[str, Any]]] = {}
    for raw in rows:
        row = dict(raw)
        game = str(row.get("game_id", ""))
        if game:
            by_game.setdefault(game, []).append(row)
    for game_rows in by_game.values():
        game_rows.sort(key=lambda row: _number(row, "asof_idx") or -1.0)
        block: list[dict[str, Any]] = []
        label = None
        for row in game_rows:
            current = row.get("half_inning_label")
            if current != label:
                if block:
                    yield block
                block, label = [], current
            block.append(row)
        if block:
            yield block


def _leadoff_kind(block: list[Mapping[str, Any]]) -> Optional[str]:
    """Classify a clean leadoff PA from its as-of resolution state only."""
    if len(block) < 2:
        return None
    start, resolved = block[0], block[1]
    if _number(start, "outs") != 0.0 or _number(start, "runners") != 0.0:
        return None
    outs, runners = _number(resolved, "outs"), _number(resolved, "runners")
    if outs is None or runners is None:
        return None
    if outs > 0.0:
        return "out"
    if runners > 0.0:
        return "on_base"
    return None


def _batting_runs(block: list[Mapping[str, Any]], next_block: list[Mapping[str, Any]]) -> Optional[float]:
    start = _number(block[0], "state_diff")
    end = _number(next_block[0], "state_diff")
    label = str(block[0].get("half_inning_label", "")).lower()
    if start is None or end is None or not (label.startswith("top") or label.startswith("bottom")):
        return None
    return start - end if label.startswith("top") else end - start


def fit_table(rows: Iterable[Mapping[str, Any]], cutoff_season: int = 2023) -> dict[str, Any]:
    """Fit P(3+ runs this half | leadoff result) using no rows after cutoff."""
    games: dict[str, list[dict[str, Any]]] = {}
    for raw in rows:
        row = dict(raw)
        try:
            season = int(row.get("season"))
        except (TypeError, ValueError):
            continue
        if season <= cutoff_season:
            games.setdefault(str(row.get("game_id", "")), []).append(row)
    hits = {"on_base": 0, "out": 0}
    totals = {"on_base": 0, "out": 0}
    source_seasons: set[int] = set()
    for game_rows in games.values():
        blocks = list(_blocks(game_rows))
        for index, block in enumerate(blocks[:-1]):
            kind = _leadoff_kind(block)
            runs = _batting_runs(block, blocks[index + 1])
            if kind is None or runs is None:
                continue
            totals[kind] += 1
            hits[kind] += int(runs >= 3.0)
            source_seasons.add(int(block[0]["season"]))
    on_base = hits["on_base"] / totals["on_base"] if totals["on_base"] else None
    out = hits["out"] / totals["out"] if totals["out"] else None
    return {"cutoff_season": cutoff_season, "source_seasons": sorted(source_seasons),
            "on_base": on_base, "out": out, "counts": totals, "hits": hits,
            "monotonic": bool(on_base is not None and out is not None and on_base > out)}


def attach_conditioner(row: Mapping[str, Any], condition: Mapping[str, Any],
                       table: Mapping[str, Any]) -> Optional[float]:
    """Return the prior only inside the triggered half inning; otherwise decay."""
    if (str(row.get("game_id")) != str(condition.get("game_id")) or
            row.get("half_inning_label") != condition.get("half_inning_label")):
        return None
    value = table.get(str(condition.get("kind")))
    return float(value) if value is not None else None


def conditioned_states(rows: Iterable[Mapping[str, Any]], table: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Attach the fixed prior from the resolved leadoff tick through that half only."""
    states: list[dict[str, Any]] = []
    for block in _blocks(rows):
        kind = _leadoff_kind(block)
        if kind is None or table.get(kind) is None:
            continue
        condition = {"game_id": block[0].get("game_id"),
                     "half_inning_label": block[0].get("half_inning_label"), "kind": kind}
        for row in block[1:]:
            prior = attach_conditioner(row, condition, table)
            if prior is None:
                continue
            required = ("game_id", "state_diff", "frac_elapsed", "outcome")
            if any(row.get(name) is None for name in required):
                continue
            states.append({"game_id": str(row["game_id"]), "state_diff": float(row["state_diff"]),
                           "frac_elapsed": float(row["frac_elapsed"]), "p0": prior,
                           "outcome": int(row["outcome"])})
    return states


def _load(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_parquet(path)
    rows = frame.to_dict("records")
    del frame
    return rows


def _direction_pass(report: Mapping[str, Any]) -> bool:
    return bool(report.get("brier_delta", 0.0) > 0.0 and report.get("dm_p", 1.0) < 0.05)


def run(cache_dir: Path = _CACHE, output: Path = _OUTPUT) -> dict[str, Any]:
    """Load each parquet serially, evaluate held-out years, and persist a verdict."""
    train_rows: list[dict[str, Any]] = []
    missing = []
    for season in _TRAIN_SEASONS:
        path = cache_dir / ("mlb_atbat_states__%d.parquet" % season)
        if not path.exists():
            missing.append(str(path))
            continue
        train_rows.extend(_load(path))
    table = fit_table(train_rows, cutoff_season=max(_TRAIN_SEASONS))
    evaluations: dict[str, list[dict[str, Any]]] = {}
    for season in _EVAL_SEASONS:
        path = cache_dir / ("mlb_atbat_states__%d.parquet" % season)
        if not path.exists():
            missing.append(str(path))
            continue
        evaluations[str(season)] = conditioned_states(_load(path), table)
    report: dict[str, Any] = {
        "arm": "mlb_leadoff_half_inning_prior", "verdict": "REJECT",
        "locked_settled_tick_baseline": _LOCKED_BASELINE, "table": table,
        "evaluation_seasons": list(_EVAL_SEASONS), "missing_required_files": missing,
        "pre_registered_bar": "DM p<0.05 and sign-consistent across both held-out season corpora",
        "flags": {"enabled": False},
    }
    if not missing and table["monotonic"]:
        gate = gate_cross(evaluations["2024"], evaluations["2025"], sport="mlb_leadoff")
        gate_report = gate.to_dict()
        report["gate_cross"] = gate_report
        directions = (gate_report.get("a_to_b", {}), gate_report.get("b_to_a", {}))
        if all(_direction_pass(direction) for direction in directions):
            report["verdict"] = "PASS"
        else:
            report["reason"] = "pre_registered_dm_or_sign_bar_not_met"
    elif missing:
        report["reason"] = "missing_pre_registered_atbat_evaluation_corpora"
    else:
        report["reason"] = "training_table_not_monotonic"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return report


def main() -> int:
    """Run the fixed offline evaluation without enabling a runtime arm."""
    parser = argparse.ArgumentParser(description="Gate an MLB leadoff conditional prior.")
    parser.add_argument("--cache-dir", type=Path, default=_CACHE)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(run(args.cache_dir, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
