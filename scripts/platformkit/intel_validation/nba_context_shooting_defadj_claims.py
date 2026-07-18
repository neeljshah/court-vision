"""NBA context-shooting defense-adjusted claim producer (axis 1 of the
nba_context_shooting_defadj family -- see nba_context_defadj_asof.py for the
leak-free opponent-strength/tercile machinery this module consumes).

MISSION: context-blindness is the enemy. A player's raw TS%/FG3% says
nothing about how hard the shots were to get; this module reports, per
qualifying player-season, the SAME metric split by opponent-defense tercile
plus one defense-adjusted composite.

PREREGISTERED FLOORS (see nba_context_defadj_asof.py for the shared ones):
  defadj_ts_pct claim   : games>=MIN_GAMES(20) AND fga>=MIN_FGA(200), plus a
                           non-null expected_ts_pct (opponent read cleared
                           MIN_PRIOR_GAMES for enough of the player's games).
  tercile_gap_ts_pct     : n_games_tough>=MIN_GAMES_TERCILE(5) AND
                           n_games_weak>=MIN_GAMES_TERCILE(5).
  tercile_gap_fg3_pct    : fg3a_tough>=MIN_FG3A_TERCILE(15) AND
                           fg3a_weak>=MIN_FG3A_TERCILE(15).
These floors are declared here BEFORE the scoring functions below and never
tuned after seeing results.

Claims are DESCRIPTIVE ranking claims (kind="ranking", formula="raw_value"
identity read of a precomputed snapshot parquet column -- same
tautological-by-construction contract as nba_venue_split_claims.py), one
snapshot per (season, claim-kind). Axis 2 (vs-scheme) and axis 3
(score-margin) claims live in sibling modules and are folded into this same
family's single JSONL store by build_all_claims() below.

CLI:
    python -m scripts.platformkit.intel_validation.nba_context_shooting_defadj_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/nba_context_shooting_defadj_claims.jsonl \
        --output data/cache/intel_claims/nba_context_shooting_defadj_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.platformkit.intel_validation import nba_context_defadj_asof as asof
from scripts.platformkit.intel_validation import nba_context_margin_claims as margin_mod
from scripts.platformkit.intel_validation import nba_context_scheme_claims as scheme_mod

REPO_ROOT = Path(__file__).resolve().parents[3]
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "nba_context_shooting_defadj_claims.jsonl"

SEASONS = ["2024-25", "2025-26"]


def player_season_table(season: str, box: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-player-season aggregate: overall TS%/FG3%, defense-adjusted TS%
    (possession-weighted expected TS% given opponents faced, minus actual),
    and the tough/weak tercile splits. See module docstring for floors."""
    if box is None:
        box = asof.load_raw_boxscores()
    rows = asof.build_player_game_rows(box)
    season_rows = rows[rows["season"] == season].copy()

    g = season_rows.groupby(["player_id", "player_name"], as_index=False).agg(
        games=("game_id", "nunique"), fga=("fga", "sum"), fta=("fta", "sum"),
        pts=("pts", "sum"), fg3m=("fg3m", "sum"), fg3a=("fg3a", "sum"),
    )
    g["ts_pct"] = g["pts"] / (2 * (g["fga"] + 0.44 * g["fta"])).replace(0, pd.NA)
    g["fg3_pct"] = g["fg3m"] / g["fg3a"].replace(0, pd.NA)

    valid = season_rows.dropna(subset=["opp_def_strength_asof"]).copy()
    valid["poss"] = valid["fga"] + 0.44 * valid["fta"]
    valid["w_num"] = valid["opp_def_strength_asof"] * valid["poss"]
    exp = valid.groupby("player_id", as_index=False).agg(w_num=("w_num", "sum"), w_den=("poss", "sum"))
    exp["expected_ts_pct"] = exp["w_num"] / exp["w_den"].replace(0, pd.NA)
    g = g.merge(exp[["player_id", "expected_ts_pct"]], on="player_id", how="left")
    g["def_adj_ts_pct"] = g["ts_pct"] - g["expected_ts_pct"]

    for tier, suffix in (("tough", "tough"), ("weak", "weak")):
        t = season_rows[season_rows["defense_tier"] == tier].groupby("player_id", as_index=False).agg(
            **{f"n_games_{suffix}": ("game_id", "nunique"), f"fga_{suffix}": ("fga", "sum"),
               f"fta_{suffix}": ("fta", "sum"), f"pts_{suffix}": ("pts", "sum"),
               f"fg3m_{suffix}": ("fg3m", "sum"), f"fg3a_{suffix}": ("fg3a", "sum")}
        )
        t[f"ts_pct_{suffix}"] = t[f"pts_{suffix}"] / (2 * (t[f"fga_{suffix}"] + 0.44 * t[f"fta_{suffix}"])).replace(0, pd.NA)
        t[f"fg3_pct_{suffix}"] = t[f"fg3m_{suffix}"] / t[f"fg3a_{suffix}"].replace(0, pd.NA)
        g = g.merge(t, on="player_id", how="left")

    return g


def _write_snapshot(df: pd.DataFrame, name: str) -> Path:
    out_path = _OUT_DIR / name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return out_path


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def build_defadj_ts_claim(season: str, table: pd.DataFrame) -> dict[str, Any]:
    snap = table[["player_id", "player_name", "games", "fga", "def_adj_ts_pct"]].dropna(subset=["def_adj_ts_pct"]).copy()
    snap = snap.rename(columns={"def_adj_ts_pct": "raw_value"})
    snap_path = _write_snapshot(snap, f"nba_context_defadj_ts_snapshot_{season.replace('-', '_')}.parquet")

    n_considered = int(len(snap))
    qualifiers = snap[(snap["games"] >= asof.MIN_GAMES) & (snap["fga"] >= asof.MIN_FGA)].copy()
    qualifiers = qualifiers.sort_values("raw_value", ascending=False).reset_index(drop=True)
    n_excluded = n_considered - int(len(qualifiers))

    ranking = [
        {"rank": i, "player_id": int(r.player_id), "player_name": str(r.player_name),
         "value": round(float(r.raw_value), 4), "n": int(r.games)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"nba_context_shooting_defadj_ts_pct_{season}",
        "kind": "ranking",
        "question": f"NBA {season}: which qualifying players outperform their TS%-given-schedule-of-opponents most?",
        "criteria": {
            "metric": "def_adj_ts_pct", "formula": "raw_value", "window": f"season_{season}_nba",
            "aggregate": None, "min_sample": {"games": asof.MIN_GAMES, "fga": asof.MIN_FGA},
            "direction": "desc", "value_precision": 4, "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [_rel(snap_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            f"min_sample floor games>={asof.MIN_GAMES} AND fga>={asof.MIN_FGA} -- the standard "
            "sibling-claim qualifying pool.",
            "def_adj_ts_pct = actual season TS% minus a possession-weighted expected TS% given the "
            "AS-OF defensive strength of opponents actually faced (opponent strength uses ONLY that "
            "opponent's games strictly before each matchup date -- leak-free by construction).",
            "opponent defensive-strength history is NOT reset at season boundaries (a team's D "
            "identity carries over); this affects only the opponent-side reading, never the target "
            "player's own future games.",
            "DESCRIPTIVE context-adjustment only -- no forecasting/market claim.",
        ],
    }


def _tercile_gap_claim(season: str, table: pd.DataFrame, metric: str, floor_col_prefix: str,
                        floor: int, precision: int, claim_suffix: str, question: str) -> dict[str, Any]:
    tough_col, weak_col = f"{metric}_tough", f"{metric}_weak"
    n_tough_col, n_weak_col = f"{floor_col_prefix}_tough", f"{floor_col_prefix}_weak"
    cols = ["player_id", "player_name", n_tough_col, n_weak_col, tough_col, weak_col]
    snap = table[cols].dropna(subset=[tough_col, weak_col]).copy()
    snap["raw_value"] = snap[weak_col] - snap[tough_col]
    snap = snap.rename(columns={n_tough_col: "n_tough", n_weak_col: "n_weak"})
    snap_path = _write_snapshot(
        snap[["player_id", "player_name", "n_tough", "n_weak", "raw_value"]],
        f"nba_context_{claim_suffix}_snapshot_{season.replace('-', '_')}.parquet",
    )

    n_considered = int(len(snap))
    qualifiers = snap[(snap["n_tough"] >= floor) & (snap["n_weak"] >= floor)].copy()
    qualifiers = qualifiers.sort_values("raw_value", ascending=False).reset_index(drop=True)
    n_excluded = n_considered - int(len(qualifiers))

    ranking = [
        {"rank": i, "player_id": int(r.player_id), "player_name": str(r.player_name),
         "value": round(float(r.raw_value), 4), "n_tough": int(r.n_tough), "n_weak": int(r.n_weak)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"nba_context_shooting_{claim_suffix}_{season}",
        "kind": "ranking",
        "question": question.format(season=season),
        "criteria": {
            "metric": f"{metric}_weak_minus_tough", "formula": "raw_value", "window": f"season_{season}_nba",
            "aggregate": None, "min_sample": {"n_tough": floor, "n_weak": floor},
            "direction": "desc", "value_precision": precision, "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [_rel(snap_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            f"min_sample floor n_tough>={floor} AND n_weak>={floor} (games faced in each opponent-"
            "defense tercile, global qcut(3) on the leak-free AS-OF opponent-strength read).",
            "raw_value = metric vs weakest-defense-tercile opponents minus metric vs toughest-"
            "defense-tercile opponents; a positive value means the player's number rises against "
            "weaker defenses (the ordinary/expected direction), near-zero means matchup-invariant.",
            "DESCRIPTIVE tercile split only -- no forecasting/market claim.",
        ],
    }


def build_tercile_gap_ts_claim(season: str, table: pd.DataFrame) -> dict[str, Any]:
    return _tercile_gap_claim(
        season, table, "ts_pct", "n_games", asof.MIN_GAMES_TERCILE, 4, "tercile_gap_ts_pct",
        "NBA {season}: which qualifying players' TS% swings most between weakest- and toughest-defense opponents?",
    )


def build_tercile_gap_fg3_claim(season: str, table: pd.DataFrame) -> dict[str, Any]:
    return _tercile_gap_claim(
        season, table, "fg3_pct", "fg3a", asof.MIN_FG3A_TERCILE, 4, "tercile_gap_fg3_pct",
        "NBA {season}: which qualifying players' 3P% swings most between weakest- and toughest-defense opponents?",
    )


def build_all_claims() -> list[dict[str, Any]]:
    box = asof.load_raw_boxscores()
    claims: list[dict[str, Any]] = []
    for season in SEASONS:
        table = player_season_table(season, box)
        claims.append(build_defadj_ts_claim(season, table))
        claims.append(build_tercile_gap_ts_claim(season, table))
        claims.append(build_tercile_gap_fg3_claim(season, table))
    claims.extend(scheme_mod.build_claims(box))
    claims.extend(margin_mod.build_claims(box))

    # Honest empty-ranking skip (domains/mlb/profiles/claims.py idiom): claiming
    # nothing is not a claim -- never emit an empty ranking, never lower a floor.
    kept = [c for c in claims if c["ranking"]]
    for c in claims:
        if not c["ranking"]:
            print(f"SKIP {c['claim_id']}: 0 of {c['n_considered']} rows clear min_sample floor -- claim not emitted")
    return kept


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA context-shooting defense-adjusted claims (all 3 axes)")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = build_all_claims()
    out_path = write_claims(claims, Path(args.output))
    print(f"wrote {len(claims)} claims -> {out_path}")
    for c in claims:
        top = c["ranking"][0] if c["ranking"] else None
        print(f"  {c['claim_id']}: n_considered={c['n_considered']} n_excluded={c['n_excluded_below_floor']} "
              f"top={top['player_name'] if top else None}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
