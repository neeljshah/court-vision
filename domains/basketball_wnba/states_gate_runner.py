"""domains.basketball_wnba.states_gate_runner -- LANE 5 states gate entry point.

Wires states_gate.py's pure computation (Row/build_rows/fit_coef/crossfit/
descriptive_stats) to the on-disk corpora (espn_scoreboard.parquet,
linescores.parquet, cdn_backfill_states.parquet) via states_gate_join.py's
CDN game_id <-> ESPN event_id crosswalk, then layers states_gate_ci.py's
game-clustered bootstrap CIs + v2 SUPPORTED survival verdict on top (LANE 4).
See states_gate.py's docstring for the full pre-declared question + method;
this module is I/O + assembly only.

Output: data/domains/wnba/states_gate_validation.json (now includes v2
delta_ci95_eval_h0/h1, ci_excludes_zero_h0/h1, verdict_v2 per cell).

INVARIANTS: <=300 LOC; ASCII only; pandas + stdlib only; no network at import
time (parquet reads only; states_gate_join reads already-backfilled JSON off
disk); no $/roi/edge fields; never mutates ingame_blend.py.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_states_gate_runner.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from domains.basketball_wnba.ingame_blend import ANCHORED_K, ANCHORED_W0
from domains.basketball_wnba.ingame_blend_families import build_corpus_with_p0
from domains.basketball_wnba.states_gate import (
    CHECKPOINTS,
    FEATURES,
    build_rows,
    crossfit_checkpoint_feature,
    descriptive_stats,
)
from domains.basketball_wnba.states_gate import _MIN_N_PER_HALF
from domains.basketball_wnba.states_gate_ci import crossfit_with_ci
from domains.basketball_wnba.states_gate_join import build_join_map

EDGE_CLAIMED = False

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GAMES_PARQUET = _REPO_ROOT / "data" / "domains" / "wnba" / "espn_scoreboard.parquet"
_LINESCORES_PARQUET = _REPO_ROOT / "data" / "domains" / "wnba" / "linescores.parquet"
_STATES_PARQUET = _REPO_ROOT / "data" / "domains" / "wnba" / "cdn_backfill_states.parquet"
_OUT = _REPO_ROOT / "data" / "domains" / "wnba" / "states_gate_validation.json"


def run_gate(
    games_df: Optional[pd.DataFrame] = None,
    linescores_df: Optional[pd.DataFrame] = None,
    states_df: Optional[pd.DataFrame] = None,
) -> Dict[str, object]:
    """Full LANE 5 states gate. Returns the dict written to
    data/domains/wnba/states_gate_validation.json."""
    games = games_df if games_df is not None else pd.read_parquet(_GAMES_PARQUET)
    games = games.copy()
    games["season"] = games["season"].astype(str)
    lines = linescores_df if linescores_df is not None else pd.read_parquet(_LINESCORES_PARQUET)
    lines = lines.copy()
    lines["event_id"] = lines["event_id"].astype(str)
    states = states_df if states_df is not None else pd.read_parquet(_STATES_PARQUET)
    states = states.copy()
    states["game_id"] = states["game_id"].astype(str)

    game_ids = sorted(states["game_id"].unique().tolist())
    join = build_join_map(game_ids, linescores_df=lines)

    # p0 needs the FULL walk-forward corpus (ratings accumulate cross-season);
    # this gate's overlap is 2026 games only, per the pre-declared brief.
    games_with_p0 = build_corpus_with_p0(games, "2026")

    rows = build_rows(games_with_p0, lines, states, join["game_id_to_event_id"])

    per_feature: Dict[str, List[Dict[str, object]]] = {}
    for feature in FEATURES:
        cell_results = []
        for cp in CHECKPOINTS:
            base = crossfit_checkpoint_feature(rows, cp, feature)
            with_ci = crossfit_with_ci(rows, cp, feature, base)
            cell_results.append(with_ci.to_dict())
        per_feature[feature] = cell_results

    supported_cells = [
        {"feature": feature, "checkpoint": r["checkpoint"]}
        for feature, feature_results in per_feature.items()
        for r in feature_results if r["verdict_v2"] == "SUPPORTED"
    ]
    any_improved = bool(supported_cells)

    result: Dict[str, object] = {
        "edge_claimed": False,
        "provenance": "cdn_backfill_validation",
        "question": (
            "Does adding run_last_3min / in_bonus as a single logit-additive "
            "term to the frozen ANCHORED blend improve checkpoint Brier, "
            "cross-fitted md5 halves (fit h0 eval h1 and vice versa)?"
        ),
        "anchored_blend_frozen_params": {"ANCHORED_K": ANCHORED_K, "ANCHORED_W0": ANCHORED_W0},
        "join": {
            "n_cdn_games": len(game_ids),
            "n_matched_to_linescores": join["matched"],
            "n_unmatched": len(join["unmatched"]),
            "unmatched_reasons": sorted({u["reason"] for u in join["unmatched"]}),
        },
        "n_rows_total": len(rows),
        "min_n_per_half_floor": _MIN_N_PER_HALF,
        "crossfit_results": per_feature,
        "descriptive_stats": descriptive_stats(rows),
        "supported_cells_v2": supported_cells,
        "overall_verdict": (
            "AT_LEAST_ONE_FEATURE_SUPPORTED_V2" if any_improved
            else "NO_FEATURE_SUPPORTED_V2__HONEST_NULL"
        ),
        "note": (
            "Validation only. The anchored blend (domains.basketball_wnba."
            "ingame_blend.blend_prob) stays UNTOUCHED regardless of this "
            "gate's verdict; any adoption is a future human-queue item. v2 "
            "SUPPORTED requires LOWER_BRIER_BOTH_DIRECTIONS AND both "
            "directions' bootstrap delta CI95 excluding 0 (see "
            "states_gate_ci.py); the v1 point-estimate verdict alone (see "
            "crossfit_results[*].verdict) is NOT sufficient for SUPPORTED."
        ),
    }
    return result


def write_gate(result: Dict[str, object], out_path: Optional[Path] = None) -> Path:
    out = out_path or _OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(result, fh, indent=2)
    return out


def _main() -> int:
    result = run_gate()
    out = write_gate(result)
    print(json.dumps(result, indent=2))
    print(f"Wrote {out}")
    print(f"OVERALL VERDICT: {result['overall_verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["run_gate", "write_gate"]
