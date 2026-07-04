"""domains.basketball_nba.states_gate_runner -- LANE 2 NBA states gate entry
point, PORTED from domains.basketball_wnba.states_gate_runner.

Wires states_gate.py's pure computation (Row/build_rows/fit_coef/crossfit/
descriptive_stats) to the on-disk corpora (games.parquet, linescores.parquet,
an NBA CDN checkpoint-states corpus) via states_gate_join.py's CDN game_id
<-> ESPN event_id crosswalk, then layers states_gate_ci.py's game-clustered
bootstrap CIs + v2 SUPPORTED survival verdict on top. See states_gate.py's
docstring for the full pre-declared question + method; this module is I/O +
assembly only.

NO_CORPUS HONEST PATH: the NBA checkpoint-states corpus
(states_gate_join.STATES_PARQUET, i.e. cdn_checkpoint_states.parquet) does
NOT exist on disk yet -- lane 4 backfills it (in_bonus / run_last_3min per
checkpoint, cdn.nba.com-sourced). run_gate() checks for it FIRST and, when
absent, returns a NO_CORPUS result with the full schema shape (empty
crossfit cells, honest note) rather than raising or fabricating rows. Once
lane 4 lands the corpus this same runner produces a real verdict with no
code change.

ANCHORED p SOURCE: NBA has no frozen closed-form blend_prob(p0, LiveState)
yet (see states_gate.py's docstring). This runner uses the walk-forward Elo
p_home_elo (domains.basketball_nba.ratings.walk_forward_elo) AS-OF each
game as p_anchored -- i.e. the pregame prior, unconditioned by the
checkpoint's realized score. This is the same "p0 passthrough" honest
placeholder the pre-declared question tolerates (states_gate.py's
build_rows takes p_anchored as an already-computed column and is agnostic
to its source); when NBA freezes its own ANCHORED_K-style score-conditioned
blend, only _compute_p_anchored below needs to change, not states_gate.py.

Output: data/domains/basketball_nba/states_gate_validation.json (v2
delta_ci95_eval_h0/h1, ci_excludes_zero_h0/h1, verdict_v2 per cell).

INVARIANTS: <=300 LOC; ASCII only; pandas + stdlib only; no network at import
time (parquet reads only; states_gate_join reads already-cached JSON off
disk); no $/roi/edge fields; never mutates ratings.py or
ingame_blend_surface.py.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_states_gate_runner.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from domains.basketball_nba.ratings import walk_forward_elo
from domains.basketball_nba.states_gate import (
    CHECKPOINTS,
    FEATURES,
    REG_SEC,
    build_rows,
    crossfit_checkpoint_feature,
    descriptive_stats,
)
from domains.basketball_nba.states_gate import _MIN_N_PER_HALF
from domains.basketball_nba.states_gate_ci import crossfit_with_ci
from domains.basketball_nba.states_gate_join import build_join_map, STATES_PARQUET

EDGE_CLAIMED = False

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GAMES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_LINESCORES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "linescores.parquet"
_OUT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "states_gate_validation.json"

_QUESTION = (
    "Does adding run_last_3min / in_bonus as a single logit-additive term to "
    "the frozen anchored p (currently: walk-forward pregame Elo passthrough) "
    "improve checkpoint Brier, cross-fitted md5 halves (fit h0 eval h1 and "
    "vice versa)?"
)


def _compute_p_anchored(games_df: pd.DataFrame, game_id_to_event_id: Dict[str, str]) -> pd.DataFrame:
    """games_df (game_id, date, season, home_team, away_team, home_win) ->
    rows restricted to games with a resolved event_id (via
    game_id_to_event_id, the SAME crosswalk states_gate_join.py builds --
    NBA's own game_id IS the cdn game_id, same 10-digit stats.nba.com/
    cdn.nba.com id space) + p_anchored (walk-forward pregame Elo, leak-free,
    computed on the FULL chronological games_df BEFORE filtering, so Elo
    ratings still accumulate correctly across every game, not just the
    joined subset) + event_id (build_rows requires this column name).
    season must be int-coercible; NBA's games.parquet stores season as a
    plain int already (unlike WNBA's string season column)."""
    df = games_df.copy()
    df["season"] = df["season"].astype(int)
    elo = walk_forward_elo(df)  # leak-free walk-forward over the FULL corpus
    elo["p_anchored"] = elo["p_home_elo"]
    elo["event_id"] = elo["game_id"].astype(str).map(game_id_to_event_id)
    return elo[elo["event_id"].notna()].copy()


def _empty_crossfit_cells() -> Dict[str, List[Dict[str, object]]]:
    """Same shape as a real crossfit_results dict but every cell is the
    honest INSUFFICIENT/NO_CORPUS shell -- used only by the NO_CORPUS path
    so downstream readers never have to special-case a missing corpus."""
    shell = {
        "checkpoint": None, "feature": None, "n_h0": 0, "n_h1": 0,
        "coef_fit_on_h0": 0.0, "coef_fit_on_h1": 0.0,
        "brier_anchored_eval_h1": None, "brier_with_term_eval_h1": None,
        "brier_anchored_eval_h0": None, "brier_with_term_eval_h0": None,
        "verdict": "NO_CORPUS", "delta_ci95_eval_h1": None, "delta_ci95_eval_h0": None,
        "ci_excludes_zero_h1": False, "ci_excludes_zero_h0": False,
        "verdict_v2": "NO_CORPUS",
    }
    out: Dict[str, List[Dict[str, object]]] = {}
    for feature in FEATURES:
        out[feature] = []
        for cp in CHECKPOINTS:
            cell = dict(shell)
            cell["checkpoint"] = cp
            cell["feature"] = feature
            out[feature].append(cell)
    return out


def run_gate(
    games_df: Optional[pd.DataFrame] = None,
    linescores_df: Optional[pd.DataFrame] = None,
    states_df: Optional[pd.DataFrame] = None,
    states_parquet_path: Optional[Path] = None,
) -> Dict[str, object]:
    """Full LANE 2 NBA states gate. Returns the dict written to
    data/domains/basketball_nba/states_gate_validation.json.

    When no checkpoint-states corpus is available (states_df is None AND
    the on-disk STATES_PARQUET is absent), returns an honest NO_CORPUS
    result with the full schema shape but zero rows -- never fabricates."""
    corpus_path = states_parquet_path or STATES_PARQUET
    if states_df is None and not corpus_path.exists():
        return {
            "edge_claimed": False,
            "provenance": "cdn_backfill_validation",
            "question": _QUESTION,
            "join": {"n_cdn_games": 0, "n_matched_to_linescores": 0,
                      "n_unmatched": 0, "unmatched_reasons": []},
            "n_rows_total": 0,
            "min_n_per_half_floor": _MIN_N_PER_HALF,
            "reg_sec": REG_SEC,
            "crossfit_results": _empty_crossfit_cells(),
            "descriptive_stats": {cp: {"n": 0} for cp in CHECKPOINTS},
            "supported_cells_v2": [],
            "overall_verdict": "NO_CORPUS",
            "note": (
                "NBA CDN checkpoint-states corpus not found at "
                f"{corpus_path}. Lane 4 backfills this corpus (in_bonus / "
                "run_last_3min per checkpoint); the gate math is fixture-"
                "proven and ready to run the instant it lands. This is an "
                "honest NO_CORPUS report, not a SHIP/REJECT verdict."
            ),
        }

    games = games_df if games_df is not None else pd.read_parquet(_GAMES_PARQUET)
    games = games.copy()
    lines = linescores_df if linescores_df is not None else pd.read_parquet(_LINESCORES_PARQUET)
    lines = lines.copy()
    lines["event_id"] = lines["event_id"].astype(str)
    states = states_df if states_df is not None else pd.read_parquet(corpus_path)
    states = states.copy()
    states["game_id"] = states["game_id"].astype(str)

    game_ids = sorted(states["game_id"].unique().tolist())
    join = build_join_map(game_ids, linescores_df=lines)

    games_with_p0 = _compute_p_anchored(games, join["game_id_to_event_id"])

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
        "question": _QUESTION,
        "join": {
            "n_cdn_games": len(game_ids),
            "n_matched_to_linescores": join["matched"],
            "n_unmatched": len(join["unmatched"]),
            "unmatched_reasons": sorted({u["reason"] for u in join["unmatched"]}),
        },
        "n_rows_total": len(rows),
        "min_n_per_half_floor": _MIN_N_PER_HALF,
        "reg_sec": REG_SEC,
        "crossfit_results": per_feature,
        "descriptive_stats": descriptive_stats(rows),
        "supported_cells_v2": supported_cells,
        "overall_verdict": (
            "AT_LEAST_ONE_FEATURE_SUPPORTED_V2" if any_improved
            else "NO_FEATURE_SUPPORTED_V2__HONEST_NULL"
        ),
        "note": (
            "Validation only. The anchored p source (currently walk-forward "
            "pregame Elo passthrough) stays UNTOUCHED regardless of this "
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
