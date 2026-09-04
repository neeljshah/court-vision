"""S226 clutch-state grammar over as-of foul and possession-state columns."""
from __future__ import annotations

import argparse
import csv
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.foundry.grammar import Hypothesis, semantic_hash
from scripts.platformkit.foundry.ingame_screen import BAR

FAMILY = "ingame_nba_clutch_foul_rotation"
SPORT, HORIZON, MARKET = "nba", "live_tick", "inplay"
EW_HALFLIVES: Tuple[int, ...] = (3, 5, 10, 20)
TRANSFORMS: Tuple[Tuple[str, tuple], ...] = (
    ("raw", ()),
    *tuple(("ew", (("halflife", half_life),)) for half_life in EW_HALFLIVES),
    ("delta_vs_prior", ()),
)
BASE: Tuple[str, ...] = (
    "home_team_pfs_cum", "away_team_pfs_cum", "home_max_player_pfs",
    "away_max_player_pfs", "home_starter_fouled_out_indicator",
    "away_starter_fouled_out_indicator", "pf_imbalance", "seconds_remaining",
    "possessions_elapsed", "pace_so_far", "run_diff", "poss_since_lead_change",
)
REQUIRED = ("game", "ts") + BASE


def _transform_key(transform: str, params: tuple) -> str:
    if transform == "ew":
        return "ew%d" % dict(params)["halflife"]
    return {"raw": "raw", "delta_vs_prior": "dprior"}[transform]


def _column_key(base: str, transform: str, params: tuple) -> str:
    return "%s|%s" % (base, _transform_key(transform, params))


def build_state(src: pd.DataFrame) -> pd.DataFrame:
    """Return source state columns in the original row order without imputation."""
    missing = [column for column in REQUIRED if column not in src.columns]
    if missing:
        raise ValueError("the clutch state frame is missing %s" % missing)
    return src.loc[:, list(BASE)].astype(float).copy()


def build_grid(src: pd.DataFrame) -> pd.DataFrame:
    """Build causal raw, expanding-EW, and prior-delta state columns."""
    state = build_state(src)
    ordered = state.assign(game=src["game"].to_numpy(), ts=src["ts"].to_numpy())
    ordered = ordered.sort_values(["game", "ts"], kind="stable")
    grouped = ordered.groupby("game", sort=False)[list(BASE)]
    grid = pd.DataFrame(index=ordered.index)
    for transform, params in TRANSFORMS:
        if transform == "raw":
            values = ordered.loc[:, list(BASE)]
        elif transform == "ew":
            values = grouped.ewm(halflife=float(dict(params)["halflife"]), ignore_na=True)
            values = values.mean().reset_index(level=0, drop=True)
        else:
            values = grouped.diff(1)
        for base in BASE:
            grid[_column_key(base, transform, params)] = values[base]
    return grid.reindex(src.index)


def enumerate_hypotheses() -> List[Hypothesis]:
    """Enumerate the closed, unconditioned clutch foul/rotation family."""
    seen: Dict[str, Hypothesis] = {}
    for base in BASE:
        for transform, params in TRANSFORMS:
            hypothesis = Hypothesis(SPORT, base, transform, params, frozenset(),
                                    HORIZON, MARKET, FAMILY, True)
            seen.setdefault(semantic_hash(hypothesis), hypothesis)
    return [seen[key] for key in sorted(seen)]


def hypothesis_column(hypothesis: Hypothesis) -> str:
    """Return the deterministic grid column selected by a hypothesis."""
    return _column_key(hypothesis.feature, hypothesis.transform, hypothesis.params)


def _write_hypotheses(path: str) -> None:
    """Write the closed family definition without opening a data store."""
    with open(path, "w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "semantic_hash", "feature", "transform", "params", "column",
        ))
        writer.writeheader()
        for hypothesis in enumerate_hypotheses():
            writer.writerow({
                "semantic_hash": semantic_hash(hypothesis),
                "feature": hypothesis.feature,
                "transform": hypothesis.transform,
                "params": repr(hypothesis.params),
                "column": hypothesis_column(hypothesis),
            })


def main() -> int:
    """Render the deterministic S226 per-hypothesis enumeration CSV."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    _write_hypotheses(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
