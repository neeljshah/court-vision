"""Absence-swing OFFENSE validity harness (2026-07-19): the offense mirror of
absence_swing.py -- a JUDGE, never an ingredient.

Recomputes per-player "team points SCORED IN vs OUT" from raw box scores
(same source, same IN/OUT definition, same n floors, same bootstrap machinery
as absence_swing.py -- reused via import, not copied) and scores offensive
impact indexes (gravity, shooter composites) against it.

SIGN CONVENTION: swing is POSITIVE when the team scores MORE points with the
player IN -- i.e. more positive = better individual offensive impact by this
measure. This is the opposite sign of absence_swing.py's defensive swing
(which is negative-is-better), because that one measures points ALLOWED.

JUDGE-OVERLAP DISCLOSURE (binding, per index):
  - shooter composites (shot-making skill: 3PA rate, 3P%, FT%, pull-up freq)
    are judge_independence="full" -- nothing about team on/off scoring feeds
    their construction.
  - nba_gravity_v2 is CONSTRUCTED from teammates' on/off eFG%/net-rating/
    scoring lifts -- i.e. from the same family of on/off-with-player splits
    this judge uses (team points scored on/off). It is only PARTIALLY
    independent, judge_independence="partial_overlap", and its verdict is
    VALID_SIGNAL_PARTIAL_JUDGE (never plain VALID_SIGNAL) when its CI
    excludes 0.

CLI: python -m scripts.platformkit.predictive_validity.absence_swing_offense
     [--index-file PATH --index-name NAME --value-col value]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.platformkit.predictive_validity.absence_swing import (
    _BOX_PATH,
    MIN_GAMES,
    MIN_IN_MINUTES,
    REPO_ROOT,
    score_index,
)

_ARTIFACT_PATH = REPO_ROOT / "data" / "cache" / "benchmarks" / "absence_swing_offense_validity.json"

# name -> (snapshot path relative to REPO_ROOT, value column, judge_independence)
KNOWN_INDEXES: dict[str, tuple[str, str, str]] = {
    "nba_gravity_v2": (
        "data/cache/intel_claims/nba_gravity_v2_snapshot.parquet", "nba_gravity_v2", "partial_overlap",
    ),
    "shooter_composite_v2": (
        "data/cache/intel_claims/shooter_composite_v2_snapshot.parquet", "shooter_composite_v2", "full",
    ),
    "shooter_composite_v2_asof_approx": (
        "data/cache/intel_claims/shooter_composite_v2_asof_approx_snapshot.parquet",
        "shooter_composite_v2_asof_approx", "full",
    ),
}


def compute_swing_offense(box: pd.DataFrame | None = None) -> pd.DataFrame:
    """Recompute per-(player_id, season) offensive absence swing: mean(own
    team points scored, IN games) - mean(own team points scored, OUT games).
    Same IN/OUT definition and n_in/n_out floors as absence_swing.compute_swing."""
    if box is None:
        box = pd.read_parquet(_BOX_PATH, columns=[
            "game_id", "date", "season", "team", "opp", "player_id", "min", "pts",
        ])
    team_ps = box.groupby(["game_id", "team", "season"])["pts"].sum().reset_index()
    team_ps = team_ps.rename(columns={"pts": "pts_scored"})

    team_games = box[["game_id", "team", "season"]].drop_duplicates()
    team_games = team_games.merge(team_ps, on=["game_id", "team", "season"], how="left")

    player_team = (
        box.groupby(["player_id", "season", "team"])["min"].sum().reset_index()
        .sort_values("min").groupby(["player_id", "season"]).last().reset_index()
        [["player_id", "season", "team"]]
    )
    player_min = box.groupby(["player_id", "season", "game_id"])["min"].sum().reset_index()

    rows = []
    for (pid, season, team), _ in player_team.groupby(["player_id", "season", "team"]):
        games = team_games[(team_games["team"] == team) & (team_games["season"] == season)]
        pm = player_min[(player_min["player_id"] == pid) & (player_min["season"] == season)]
        pm_by_game = pm.set_index("game_id")["min"]
        in_mask = games["game_id"].map(pm_by_game).fillna(0.0) >= MIN_IN_MINUTES
        in_ps = games.loc[in_mask, "pts_scored"].dropna()
        out_ps = games.loc[~in_mask, "pts_scored"].dropna()
        if len(in_ps) < MIN_GAMES or len(out_ps) < MIN_GAMES:
            continue
        rows.append({
            "player_id": int(pid), "season": season,
            "swing": float(in_ps.mean() - out_ps.mean()),
            "n_in": int(len(in_ps)), "n_out": int(len(out_ps)),
        })
    return pd.DataFrame(rows)


def score_offense_index(name: str, series: dict[int, float], judge_independence: str,
                         swing: pd.DataFrame | None = None) -> dict[str, Any]:
    """score_index() plus judge-overlap-aware verdict relabeling: a
    partial_overlap index whose CI excludes 0 is VALID_SIGNAL_PARTIAL_JUDGE,
    never plain VALID_SIGNAL."""
    result = score_index(name, series, swing)
    if judge_independence == "partial_overlap" and result["verdict"] == "VALID_SIGNAL":
        result["verdict"] = "VALID_SIGNAL_PARTIAL_JUDGE"
    result["judge_independence"] = judge_independence
    return result


def build_artifact(index_results: list[dict[str, Any]], n_swing_players: int) -> dict[str, Any]:
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "method": (
            "team points SCORED IN (player logged >= %.0f min) vs OUT (0 min or absent "
            "from boxscore), floor n_in/n_out >= %d, derived from player_boxscores.parquet "
            "team/season/pts columns only (offense mirror of absence_swing.py)"
            % (MIN_IN_MINUTES, MIN_GAMES)
        ),
        "swing": {
            "n_players": n_swing_players,
            "sign_convention": "positive = team scores MORE points with player IN (better individual offense)",
        },
        "indexes": {
            r["name"]: {
                "rho": r["rho"], "ci": r["ci"], "n": r["n"], "verdict": r["verdict"],
                "judge_independence": r["judge_independence"],
            }
            for r in index_results
        },
        "edge_claimed": False,
        "honest_note": (
            "gravity_v2 is CONSTRUCTED from teammate on/off scoring-family lifts, so this "
            "on/off-team-points judge is only partially independent for it -- see per-index "
            "judge_independence and the VALID_SIGNAL_PARTIAL_JUDGE verdict. Shooter composites "
            "are shot-making-skill metrics, fully independent of this judge."
        ),
    }


def write_artifact(doc: dict[str, Any], path: Path = _ARTIFACT_PATH) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(path)
    return str(path)


def main() -> dict[str, Any]:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index-file", default=None)
    ap.add_argument("--index-name", default=None)
    ap.add_argument("--value-col", default="value")
    ap.add_argument("--judge-independence", default="full", choices=["full", "partial_overlap"])
    args = ap.parse_args()

    swing = compute_swing_offense()
    results = []
    if args.index_file:
        df = pd.read_parquet(args.index_file) if args.index_file.endswith(".parquet") \
            else pd.read_json(args.index_file)
        series = dict(zip(df["player_id"].astype(int), df[args.value_col]))
        results.append(score_offense_index(
            args.index_name or Path(args.index_file).stem, series, args.judge_independence, swing))
    else:
        for name, (rel_path, value_col, judge_independence) in KNOWN_INDEXES.items():
            p = REPO_ROOT / rel_path
            if not p.exists():
                continue
            df = pd.read_parquet(p, columns=["player_id", value_col])
            series = dict(zip(df["player_id"].astype(int), df[value_col]))
            results.append(score_offense_index(name, series, judge_independence, swing))

    doc = build_artifact(results, n_swing_players=int(swing["player_id"].nunique()) if not swing.empty else 0)
    out_path = write_artifact(doc)
    print(f"absence_swing_offense_validity: swing_players={doc['swing']['n_players']} "
          f"indexes={list(doc['indexes'].keys())} -> {out_path}")
    return doc


if __name__ == "__main__":
    main()
