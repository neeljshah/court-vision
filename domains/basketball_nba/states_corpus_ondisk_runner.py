"""domains.basketball_nba.states_corpus_ondisk_runner -- runs states_gate.py's
crossfit + states_gate_ci.py's bootstrap CI on the ON-DISK corpus
(states_corpus_ondisk.py), the honest substitute for the CDN-blocked path
(states_gate_runner.py). Wave-22 lane 5.

WHY A SEPARATE RUNNER: states_gate_runner.py stays wired to the
cdn_checkpoint_states.parquet path (states_gate_join.STATES_PARQUET) so it
activates unchanged the instant lane 4's blocked CDN backfill ever lands --
this module does NOT touch that runner. It reuses the SAME p_anchored
(walk-forward pregame Elo passthrough) construction so the two runners are
directly comparable once both have real corpora.

SCOPE: only run_last_3min is scored (states_corpus_ondisk.FEATURES_AVAILABLE);
in_bonus is honestly absent from this on-disk source (see that module's
docstring) and is NOT run here -- never silently reported as REJECT/NULL for
a feature that was never actually tested.

Output: data/domains/basketball_nba/states_gate_ondisk_validation.json

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_states_corpus_ondisk_runner.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from domains.basketball_nba.adapter import _season_to_int
from domains.basketball_nba.ratings import walk_forward_elo
from domains.basketball_nba.states_gate import CHECKPOINTS, _MIN_N_PER_HALF, crossfit_checkpoint_feature, descriptive_stats
from domains.basketball_nba.states_gate_ci import crossfit_with_ci
from domains.basketball_nba.states_corpus_ondisk import (
    FEATURES_AVAILABLE,
    build_rows_from_ondisk,
    load_default_corpus,
)

EDGE_CLAIMED = False

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GAMES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_OUT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "states_gate_ondisk_validation.json"

_QUESTION = (
    "Does adding run_last_3min (ESPN-summary-derived margin-trajectory "
    "approximation, on-disk corpus, no CDN) as a single logit-additive term "
    "to the frozen anchored p (walk-forward pregame Elo passthrough) improve "
    "checkpoint Brier, cross-fitted md5 halves (fit h0 eval h1 and vice "
    "versa)? in_bonus is NOT tested here -- unavailable from this source."
)


def _compute_p_anchored(games_df: pd.DataFrame, event_ids: set) -> pd.DataFrame:
    """Same construction as states_gate_runner._compute_p_anchored, but
    restricted directly to ESPN event_ids (this corpus's own id space --
    no CDN game_id crosswalk needed since linescores/pbp_states are already
    ESPN-event_id-keyed). games_df must ALREADY carry a real event_id column
    (from build_games_event_crosswalk) -- unlike the CDN path, this event_id
    is NEVER overwritten from game_id (games.parquet's game_id is NBA's own
    10-digit id, a different space entirely)."""
    df = games_df.copy()
    df["season"] = df["season"].apply(_season_to_int)
    elo = walk_forward_elo(df)  # leak-free walk-forward over the FULL corpus; preserves event_id
    elo["p_anchored"] = elo["p_home_elo"]
    elo["event_id"] = elo["event_id"].astype(str)
    return elo[elo["event_id"].isin(event_ids)].copy()


def run_gate_with_crosswalk(
    games_with_event_id: pd.DataFrame,
    linescores_df: Optional[pd.DataFrame] = None,
    pbp_states_df: Optional[pd.DataFrame] = None,
) -> Dict[str, object]:
    """Same as run_gate but takes games_with_event_id directly: a DataFrame
    with columns [event_id, date, season, home_team, away_team, home_win]
    already carrying ESPN event_id (e.g. built by joining games.parquet to
    linescores.parquet on (date, home_team, away_team) -- see
    build_games_event_crosswalk in the per-file test / CLI for the concrete
    join). Never mutates games.parquet or linescores.parquet."""
    corpus = None
    if linescores_df is None or pbp_states_df is None:
        corpus = load_default_corpus()
    lines = linescores_df if linescores_df is not None else corpus["linescores"]
    pbp = pbp_states_df if pbp_states_df is not None else corpus["pbp_states"]

    event_ids = set(pbp["event_id"].astype(str).unique())
    games_with_p0 = _compute_p_anchored(games_with_event_id, event_ids)

    rows = build_rows_from_ondisk(games_with_p0, lines, pbp)

    per_feature: Dict[str, list] = {}
    for feature in FEATURES_AVAILABLE:
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

    result: Dict[str, object] = {
        "edge_claimed": False,
        "provenance": "ondisk_espn_pbp_no_cdn",
        "question": _QUESTION,
        "features_tested": list(FEATURES_AVAILABLE),
        "features_unavailable": ["in_bonus"],
        "n_events_in_corpus": len(event_ids),
        "n_events_with_p_anchored": len(games_with_p0),
        "n_rows_total": len(rows),
        "min_n_per_half_floor": _MIN_N_PER_HALF,
        "crossfit_results": per_feature,
        "descriptive_stats": descriptive_stats(rows),
        "supported_cells_v2": supported_cells,
        "overall_verdict": (
            "AT_LEAST_ONE_FEATURE_SUPPORTED_V2" if supported_cells
            else "NO_FEATURE_SUPPORTED_V2__HONEST_NULL"
        ),
        "note": (
            "On-disk corpus (ESPN summary plays[] margin trajectory), no "
            "cdn.nba.com backfill (confirmed BLOCKED, see cdn_probe.py). "
            "run_last_3min uses a 240s (2-grid-step) trailing window as the "
            "closest fit to the CDN's exact 180s definition -- see "
            "states_corpus_ondisk.py docstring; NOT the same statistic as "
            "the CDN path's. in_bonus is not tested (no foul-state source "
            "here). Anchored p stays UNTOUCHED regardless of verdict."
        ),
    }
    return result


def write_gate(result: Dict[str, object], out_path: Optional[Path] = None) -> Path:
    out = out_path or _OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(result, fh, indent=2)
    return out


# games.parquet's team codes are NOT all identical to linescores.parquet's
# ESPN abbr (verified this wave: 30/30 teams match except these 6) -- e.g.
# games has "GSW", linescores has ESPN's shorter "GS" for the same team.
_GAMES_TO_LINESCORES_ABBR = {
    "GSW": "GS", "NOP": "NO", "NYK": "NY", "SAS": "SA", "UTA": "UTAH", "WAS": "WSH",
}


def _to_linescores_abbr(code: str) -> str:
    return _GAMES_TO_LINESCORES_ABBR.get(code, code)


def build_games_event_crosswalk(
    games_df: pd.DataFrame, linescores_df: pd.DataFrame,
) -> pd.DataFrame:
    """games.parquet (game_id, date, season, home_team, away_team, home_win)
    joined to linescores.parquet (event_id, date, home_abbr, away_abbr) on
    (date, home_abbr, away_abbr) after normalizing games.parquet's 6
    mismatched team codes to linescores' ESPN abbreviations (see
    _GAMES_TO_LINESCORES_ABBR; verified this wave: 24/30 codes already match
    directly). Returns games rows with an added event_id column (unmatched
    rows dropped, never fabricated); this is the one join this module
    performs, done in the open (not hidden in run_gate_with_crosswalk) so it
    is inspectable/testable on its own.
    """
    g = games_df.copy()
    g["date_str"] = pd.to_datetime(g["date"]).dt.strftime("%Y-%m-%d")
    ls = linescores_df.copy()
    ls["date_str"] = pd.to_datetime(ls["date"]).dt.strftime("%Y-%m-%d")
    key_map = {
        (r["date_str"], str(r["home_abbr"]), str(r["away_abbr"])): str(r["event_id"])
        for _, r in ls.iterrows()
    }
    g["event_id"] = g.apply(
        lambda r: key_map.get((
            r["date_str"],
            _to_linescores_abbr(str(r["home_team"])),
            _to_linescores_abbr(str(r["away_team"])),
        )),
        axis=1,
    )
    return g[g["event_id"].notna()].drop(columns=["date_str"]).copy()


def _main() -> int:
    games = pd.read_parquet(_GAMES_PARQUET)
    lines = pd.read_parquet(
        Path(__file__).resolve().parents[2] / "data" / "domains" / "basketball_nba" / "linescores.parquet"
    )
    games_with_event_id = build_games_event_crosswalk(games, lines)
    result = run_gate_with_crosswalk(games_with_event_id)
    out = write_gate(result)
    print(json.dumps(result, indent=2))
    print(f"Wrote {out}")
    print(f"OVERALL VERDICT: {result['overall_verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "run_gate_with_crosswalk", "write_gate", "build_games_event_crosswalk",
]
