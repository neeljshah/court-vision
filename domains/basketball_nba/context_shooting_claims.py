"""NBA CONTEXT-ADJUSTED SHOOTING claims (LANE nba-context-shooting).

User thesis: "a player can be a good shooter on a bad shooting team" -- raw
3P% lies without context. Makes that context adjustment a MEASURABLE
descriptive claim dimension, same SHARED CLAIMS CONTRACT shape as
scripts/platformkit/intel_validation/basketball_claims.py (validator-
independent, mechanically recomputable).

DATA SOURCE (read-only): data/domains/basketball_nba/player_boxscores.parquet
-- the SAME per-player-per-game rows basketball_claims_dims.py + player_
intel_shooting.py already use. Season frozen to 2024-25 (full season on
disk, 26186 rows), matching the existing spec's frozen population window.
This parquet IS the player-game log (has `date`), so the rest-split
dimension needs no separate table -- no CORPUS_ABSENT case applies here.

WHY SNAPSHOT-WITH-PLAIN-COLUMNS, not criteria.aggregate: safe_formula's
aggregate grammar (evaluate_group_formula) computes sum()/mean()/count()
WITHIN one group_by grain only -- no cross-grain subtraction primitive
(team total minus this-player's-own-rows; player-grain ratio over
team-grain denominator). Following basketball_claims_dims.py's precedent
(nested-struct leaf flatten), this module derives the value here, writes it
as a PLAIN scalar column on a snapshot parquet, and cites
`criteria.formula = <that column>` with `aggregate: null` -- the
validator's plain-formula path then re-derives it independently off the
snapshot's plain columns and re-sorts/re-floors on its own.

THREE DIMENSIONS:
  1. fg3_pct_vs_team_context: player 3P% MINUS his team-excluding-player 3P%
     (same team STINT -- a traded player gets one row PER team, never
     blended across two shooting environments). floor: player fg3a>=100 AND
     team-other fg3a>=500. Positive = shoots better than his own environment.
  2. fg3a_share_of_team: player's share of his team's total 3PA on that team
     (volume/role context). floor: player fg3a>=100.
  3. fg3_pct_rest_split: per-player B2B (1-day gap since prior game) vs 2+
     rest-day 3P%, as b2b-minus-rest (plain signed difference, no direction
     claimed). floor: >=30 3PA EACH side.

DESCRIPTIVE ONLY -- no forecasting/model-wiring claim; these become stack
ingredients later ONLY via a sha-pinned prereg amendment (per LANE brief).
NETWORK: zero. Pure pandas over an already-materialized parquet.

CLI: python -m domains.basketball_nba.context_shooting_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa

from scripts.platformkit.intel_validation.basketball_claims_io import atomic_write_parquet
from scripts.platformkit.intel_validation.claims_validator import validate_claim

REPO_ROOT = Path(__file__).resolve().parents[2]
_BOXSCORES = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "nba_context_shooting_claims.jsonl"

SEASON = "2024-25"
MIN_PLAYER_FG3A = 100
MIN_TEAM_OTHER_FG3A = 500
MIN_REST_SIDE_FG3A = 30


def _load_season_rows(season: str = SEASON) -> pd.DataFrame:
    df = pd.read_parquet(
        _BOXSCORES,
        columns=["game_id", "date", "season", "team", "player_id", "player_name", "fg3m", "fg3a"],
    )
    return df[df["season"] == season].copy()


def _name_lookup(rows: pd.DataFrame) -> dict[int, str]:
    dedup = rows.drop_duplicates(subset=["player_id"], keep="last")
    return dict(zip(dedup["player_id"].astype("int64"), dedup["player_name"]))


def build_team_context_snapshot(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per (player_id, team) stint: player_fg3m/fg3a, team_fg3m/fg3a
    (the FULL team-game total, all players), and the two derived plain
    columns fg3_pct_vs_team_context + fg3a_share_of_team. A traded player
    gets one row per team -- team-other is computed within that stint only,
    never blended across two different environments."""
    player_side = rows.groupby(["player_id", "team"], as_index=False).agg(
        player_fg3m=("fg3m", "sum"), player_fg3a=("fg3a", "sum"),
    )
    # team total (includes the player himself, subtracted out below): sum
    # every player-row per (game, team) first so a team-game is counted once
    # regardless of roster size, then sum across the team's games.
    team_side = (
        rows.groupby(["game_id", "team"], as_index=False)
        .agg(game_team_fg3m=("fg3m", "sum"), game_team_fg3a=("fg3a", "sum"))
        .groupby("team", as_index=False)
        .agg(team_fg3m=("game_team_fg3m", "sum"), team_fg3a=("game_team_fg3a", "sum"))
    )
    snap = player_side.merge(team_side, on="team", how="left")
    snap["team_other_fg3m"] = snap["team_fg3m"] - snap["player_fg3m"]
    snap["team_other_fg3a"] = snap["team_fg3a"] - snap["player_fg3a"]
    snap["player_fg3_pct"] = snap["player_fg3m"] / snap["player_fg3a"]
    snap["team_other_fg3_pct"] = snap["team_other_fg3m"] / snap["team_other_fg3a"]
    snap["fg3_pct_vs_team_context"] = snap["player_fg3_pct"] - snap["team_other_fg3_pct"]
    snap["fg3a_share_of_team"] = snap["player_fg3a"] / snap["team_fg3a"]
    return snap


def build_rest_split_snapshot(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per player: b2b_fg3m/fg3a (games with a 1-day gap since that
    player's PRIOR game, same season) vs rest_fg3m/fg3a (2+ day gap), plus
    the derived plain column fg3_pct_rest_split = b2b_pct - rest_pct. A
    player's very first game of the season has no prior gap and is dropped
    from BOTH sides (neither B2B nor rested is knowable for it)."""
    per_game = rows.groupby(["player_id", "game_id", "date"], as_index=False).agg(
        fg3m=("fg3m", "sum"), fg3a=("fg3a", "sum"),
    )
    per_game = per_game.sort_values(["player_id", "date"])
    per_game["gap_days"] = per_game.groupby("player_id")["date"].diff().dt.days
    b2b = per_game[per_game["gap_days"] == 1].groupby("player_id", as_index=False).agg(
        b2b_fg3m=("fg3m", "sum"), b2b_fg3a=("fg3a", "sum"),
    )
    rest = per_game[per_game["gap_days"] >= 2].groupby("player_id", as_index=False).agg(
        rest_fg3m=("fg3m", "sum"), rest_fg3a=("fg3a", "sum"),
    )
    snap = b2b.merge(rest, on="player_id", how="inner")
    snap["b2b_fg3_pct"] = snap["b2b_fg3m"] / snap["b2b_fg3a"]
    snap["rest_fg3_pct"] = snap["rest_fg3m"] / snap["rest_fg3a"]
    snap["fg3_pct_rest_split"] = snap["b2b_fg3_pct"] - snap["rest_fg3_pct"]
    return snap


def _write_snapshot(df: pd.DataFrame, name: str) -> Path:
    path = _OUT_DIR / f"nba_{name}_snapshot.parquet"
    atomic_write_parquet(pa.Table.from_pandas(df, preserve_index=False), path)
    return path


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _assemble_claim(
    write_cols: pd.DataFrame, path: Path, metric_col: str, min_sample: dict[str, float],
    names: dict[int, str], question: str, caveats: list[str], has_team: bool, season: str = SEASON,
) -> dict[str, Any]:
    """Shared claim-assembly: floor-filter, rank desc, build ranking rows +
    the SHARED CLAIMS CONTRACT dict. All three dims here are a plain-column
    snapshot (aggregate=None) ranked desc on their own metric_col -- only
    the floor set / question / caveats / presence of a `team` field differ."""
    n_considered = len(write_cols)
    mask = pd.Series(True, index=write_cols.index)
    for col, floor in min_sample.items():
        mask &= write_cols[col] >= floor
    qualifiers = write_cols[mask].sort_values(metric_col, ascending=False).reset_index(drop=True)
    n_excluded = n_considered - len(qualifiers)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        pid = int(row.player_id)
        entry = {
            "rank": i, "player_id": pid,
            "player_name": names.get(pid, "Unknown"),
            "value": round(float(getattr(row, metric_col)), 4),
            "n": int(min(getattr(row, c) for c in min_sample)) if min_sample else 0,
        }
        if has_team:
            entry["team"] = row.team
        ranking.append(entry)

    return {
        "claim_id": f"nba_{metric_col}_{season}",
        "kind": "ranking",
        "question": question,
        "criteria": {
            "metric": metric_col,
            "formula": metric_col,
            "window": f"season_{season}_nba",
            "window_spec": None,
            "aggregate": None,
            "min_sample": min_sample,
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [_rel(path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": caveats + [f"floor: {min_sample} ({len(qualifiers)}/{n_considered} qualify).",
                              "DESCRIPTIVE ranking only -- no forecasting/market/$ edge claimed."],
    }


def build_team_context_claim(rows: pd.DataFrame, names: dict[int, str]) -> dict[str, Any]:
    snap = build_team_context_snapshot(rows)
    keep = ["player_id", "team", "fg3_pct_vs_team_context", "player_fg3a", "team_other_fg3a"]
    write_cols = snap[keep].dropna(subset=["fg3_pct_vs_team_context"])
    path = _write_snapshot(write_cols, "fg3_pct_vs_team_context")
    return _assemble_claim(
        write_cols, path, "fg3_pct_vs_team_context",
        {"player_fg3a": MIN_PLAYER_FG3A, "team_other_fg3a": MIN_TEAM_OTHER_FG3A}, names,
        "Which qualifying NBA players shoot 3s better than their own team's "
        f"shooting environment ({SEASON})?",
        ["fg3_pct_vs_team_context = player 3P% MINUS his team-excluding-player 3P% "
         "(the literal 'good shooter on a bad shooting team' number); positive means "
         "he shoots better than his own team's other players.",
         "One row PER (player, team) STINT within the season -- a player traded "
         "mid-season gets a SEPARATE value for each team, never blended across two "
         "different shooting environments."],
        has_team=True,
    )


def build_team_share_claim(rows: pd.DataFrame, names: dict[int, str]) -> dict[str, Any]:
    snap = build_team_context_snapshot(rows)
    keep = ["player_id", "team", "fg3a_share_of_team", "player_fg3a"]
    write_cols = snap[keep].dropna(subset=["fg3a_share_of_team"])
    path = _write_snapshot(write_cols, "fg3a_share_of_team")
    return _assemble_claim(
        write_cols, path, "fg3a_share_of_team", {"player_fg3a": MIN_PLAYER_FG3A}, names,
        "Which qualifying NBA players take the largest share of their team's "
        f"3-point attempts while on the roster ({SEASON})?",
        ["fg3a_share_of_team = player's total 3PA divided by his team's total 3PA, "
         "for the games he was actually on that team (volume/role context, not "
         "efficiency).",
         "One row PER (player, team) STINT within the season -- see "
         "fg3_pct_vs_team_context's caveat for the same trade-handling rule."],
        has_team=True,
    )


def build_rest_split_claim(rows: pd.DataFrame, names: dict[int, str]) -> dict[str, Any]:
    snap = build_rest_split_snapshot(rows)
    keep = ["player_id", "fg3_pct_rest_split", "b2b_fg3a", "rest_fg3a"]
    write_cols = snap[keep].dropna(subset=["fg3_pct_rest_split"])
    path = _write_snapshot(write_cols, "fg3_pct_rest_split")
    return _assemble_claim(
        write_cols, path, "fg3_pct_rest_split",
        {"b2b_fg3a": MIN_REST_SIDE_FG3A, "rest_fg3a": MIN_REST_SIDE_FG3A}, names,
        "Which qualifying NBA players shoot a different 3P% on the second night of "
        f"a back-to-back vs 2+ days rest ({SEASON})?",
        ["fg3_pct_rest_split = B2B 3P% MINUS 2+ rest-day 3P% (built straight off "
         "player_boxscores.parquet's own game-log `date` column -- no separate "
         "game-level table needed, no CORPUS_ABSENT case applies). Positive = "
         "shoots better on a back-to-back; sign is descriptive only, no direction "
         "of causation or edge implied.",
         "B2B = exactly a 1-day gap since that player's own PRIOR game this "
         "season; rest = 2+ day gap; a player's first game of the season has no "
         "prior gap and is excluded from both sides."],
        has_team=False,
    )


def build_all_claims() -> list[dict[str, Any]]:
    rows = _load_season_rows()
    names = _name_lookup(rows)
    claims = [
        build_team_context_claim(rows, names),
        build_team_share_claim(rows, names),
        build_rest_split_claim(rows, names),
    ]
    claims.sort(key=lambda c: c["claim_id"])
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA context-adjusted shooting claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = build_all_claims()
    out_path = write_claims(claims, Path(args.output))

    n_pass, n_fail = 0, 0
    for c in claims:
        verdict = validate_claim(c)
        status = "PASS" if verdict.verdict == "VERIFIED" else "FAIL"
        n_pass += status == "PASS"
        n_fail += status == "FAIL"
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} "
              f"validator={status} ({verdict.reason})")
    print(f"wrote {len(claims)} claims -> {out_path} (validator_pass={n_pass} validator_fail={n_fail})")
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
