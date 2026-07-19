"""Absence-swing validity harness (2026-07-18): a JUDGE, never an ingredient.

Recomputes per-player "team points allowed IN vs OUT" from raw box scores and
scores any impact index's Spearman correlation against it. Validated the
defender index ladder v1->v4 (rho +0.307 -> +0.520) in a one-off session
(scratchpad/absence_swing.parquet); this module makes that recomputation
reproducible and adds a generic CLI so any new index can be checked the same
way. The swing value must NEVER feed into an index's own computation -- it
only judges indexes after the fact.

Definition (per player, per season):
  - a team-game is IN for a player if he logged >= MIN_IN_MINUTES in that
    team's boxscore for that game_id.
  - a team-game is OUT if the player logged 0 minutes OR is absent entirely
    from the boxscore for that game_id while his team played (roster churn,
    trades, and DNPs are NOT distinguished -- documented limitation).
  - swing = mean(team points allowed, IN games) - mean(team points allowed,
    OUT games), computed only when n_in >= MIN_GAMES and n_out >= MIN_GAMES.
  - SIGN CONVENTION: swing is NEGATIVE when the team allows FEWER points with
    the player in (defends better with him on the floor) -- i.e. more
    negative = better individual defensive impact by this measure.

Team points allowed per game-team is derived from player_boxscores.parquet
alone: sum(pts) grouped by (game_id, team) gives that team's own points; a
self-join on game_id pairs each team with its opponent's row (using the
per-row 'opp' column already in the box) to get points allowed.

CLI: python -m scripts.platformkit.predictive_validity.absence_swing
     [--index-file PATH --index-name NAME --value-col value]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from domains.basketball_nba.quality_validity_stats import spearman as _spearman

REPO_ROOT = Path(__file__).resolve().parents[3]
_BOX_PATH = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_ARTIFACT_PATH = REPO_ROOT / "data" / "cache" / "benchmarks" / "absence_swing_validity.json"

MIN_IN_MINUTES = 10.0
MIN_GAMES = 15
N_BOOTSTRAP = 2000
RNG_SEED = 20260718  # fixed, declared before any absence-swing result was inspected

# name -> (snapshot path relative to REPO_ROOT, value column). Known shipped
# defender indexes, scored by the CLI when no --index-file is given.
KNOWN_INDEXES: dict[str, tuple[str, str]] = {
    "nba_defender_v1": ("data/cache/intel_claims/nba_defender_v1_snapshot.parquet", "nba_defender_v1"),
    "nba_defender_v2_context": ("data/cache/intel_claims/nba_defender_v2_context_snapshot.parquet", "nba_defender_v2_context"),
    "nba_defender_v3_team_rel": ("data/cache/intel_claims/nba_defender_v3_team_rel_snapshot.parquet", "nba_defender_v3_team_rel"),
    "nba_defender_v4_individual": ("data/cache/intel_claims/nba_defender_v4_individual_snapshot.parquet", "nba_defender_v4_individual"),
}


def _team_points_allowed(box: pd.DataFrame) -> pd.DataFrame:
    """game_id, team, season, pts_allowed -- from box's own team/opp/pts columns."""
    scored = box.groupby(["game_id", "team", "opp", "season"])["pts"].sum().reset_index()
    scored = scored.rename(columns={"pts": "pts_scored"})
    merged = scored.merge(
        scored[["game_id", "team", "pts_scored"]].rename(columns={"team": "opp", "pts_scored": "pts_allowed"}),
        on=["game_id", "opp"], how="inner",
    )
    return merged[["game_id", "team", "season", "pts_allowed"]]


def compute_swing(box: pd.DataFrame | None = None) -> pd.DataFrame:
    """Recompute per-(player_id, season) absence swing. Returns
    player_id, season, swing, n_in, n_out (only rows meeting both floors)."""
    if box is None:
        box = pd.read_parquet(_BOX_PATH, columns=[
            "game_id", "date", "season", "team", "opp", "player_id", "min", "pts",
        ])
    team_pa = _team_points_allowed(box)

    # every (team, season) game the team played
    team_games = box[["game_id", "team", "season"]].drop_duplicates()
    team_games = team_games.merge(team_pa, on=["game_id", "team", "season"], how="left")

    # a player's primary team for a season = team with most minutes logged
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
        in_pa = games.loc[in_mask, "pts_allowed"].dropna()
        out_pa = games.loc[~in_mask, "pts_allowed"].dropna()
        if len(in_pa) < MIN_GAMES or len(out_pa) < MIN_GAMES:
            continue
        rows.append({
            "player_id": int(pid), "season": season,
            "swing": float(in_pa.mean() - out_pa.mean()),
            "n_in": int(len(in_pa)), "n_out": int(len(out_pa)),
        })
    return pd.DataFrame(rows)


def _bootstrap_rho_ci(x: pd.Series, y: pd.Series, n_boot: int = N_BOOTSTRAP,
                       seed: int = RNG_SEED) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    n = len(x)
    xv, yv = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    rhos = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        r = _spearman(pd.Series(xv[idx]), pd.Series(yv[idx]))
        if not np.isnan(r):
            rhos.append(r)
    if not rhos:
        return {"lo": float("nan"), "hi": float("nan"), "n_boot_effective": 0}
    return {"lo": float(np.percentile(rhos, 2.5)), "hi": float(np.percentile(rhos, 97.5)),
            "n_boot_effective": len(rhos)}


def score_index(name: str, series: dict[int, float], swing: pd.DataFrame | None = None) -> dict[str, Any]:
    """Spearman rho of an index's per-player values against absence swing
    (pooled across seasons -- a player with multiple qualifying seasons
    contributes his most-recent-season swing). Bootstrap CI resamples
    players, 2000 iters, fixed declared seed (RNG_SEED=20260718)."""
    if swing is None:
        swing = compute_swing()
    if swing.empty or not series:
        return {"name": name, "rho": float("nan"), "ci": {"lo": float("nan"), "hi": float("nan")},
                "n": 0, "verdict": "NULL"}
    latest = swing.sort_values("season").groupby("player_id").last().reset_index()
    latest["index_value"] = latest["player_id"].map(series)
    latest = latest.dropna(subset=["index_value"])
    n = len(latest)
    if n < MIN_GAMES:
        return {"name": name, "rho": float("nan"), "ci": {"lo": float("nan"), "hi": float("nan")},
                "n": n, "verdict": "NULL"}
    rho = _spearman(latest["index_value"], latest["swing"])
    ci = _bootstrap_rho_ci(latest["index_value"], latest["swing"])
    verdict = "VALID_SIGNAL" if (ci["lo"] > 0 or ci["hi"] < 0) and ci["n_boot_effective"] > 0 else "WEAK_OR_NULL"
    return {"name": name, "rho": rho, "ci": {"lo": ci["lo"], "hi": ci["hi"]}, "n": n, "verdict": verdict}


def build_artifact(index_results: list[dict[str, Any]], n_swing_players: int) -> dict[str, Any]:
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "method": (
            "team points allowed IN (player logged >= %.0f min) vs OUT (0 min or absent "
            "from boxscore), floor n_in/n_out >= %d, derived from player_boxscores.parquet "
            "team/opp/pts columns only" % (MIN_IN_MINUTES, MIN_GAMES)
        ),
        "swing": {
            "n_players": n_swing_players,
            "sign_convention": "negative = team allows FEWER points with player IN (better individual defense)",
        },
        "indexes": {r["name"]: {"rho": r["rho"], "ci": r["ci"], "n": r["n"], "verdict": r["verdict"]}
                    for r in index_results},
        "edge_claimed": False,
    }


def write_artifact(doc: dict[str, Any], path: Path = _ARTIFACT_PATH) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(path)
    return str(path)


def validity_caveat(index_name: str, path: Path = _ARTIFACT_PATH) -> str:
    """One-line caveat for a claims-file docstring/RECEIPT_CAVEAT, reading the
    artifact written by write_artifact(). Honest fallback when absent."""
    if not path.exists():
        return f"no absence-swing validity receipt on file for {index_name}"
    try:
        doc = json.loads(path.read_text(encoding="ascii"))
    except Exception:
        return f"no absence-swing validity receipt on file for {index_name}"
    entry = doc.get("indexes", {}).get(index_name)
    if not entry or entry.get("n", 0) == 0:
        return f"no absence-swing validity receipt on file for {index_name}"
    return (
        f"absence-swing validity rho {entry['rho']:+.3f} "
        f"CI[{entry['ci']['lo']:+.3f},{entry['ci']['hi']:+.3f}] n={entry['n']} "
        f"as_of {doc.get('as_of', '?')} ({entry['verdict']})"
    )


def main() -> dict[str, Any]:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index-file", default=None)
    ap.add_argument("--index-name", default=None)
    ap.add_argument("--value-col", default="value")
    args = ap.parse_args()

    swing = compute_swing()
    results = []
    if args.index_file:
        df = pd.read_parquet(args.index_file) if args.index_file.endswith(".parquet") \
            else pd.read_json(args.index_file)
        series = dict(zip(df["player_id"].astype(int), df[args.value_col]))
        results.append(score_index(args.index_name or Path(args.index_file).stem, series, swing))
    else:
        for name, (rel_path, value_col) in KNOWN_INDEXES.items():
            p = REPO_ROOT / rel_path
            if not p.exists():
                continue
            df = pd.read_parquet(p, columns=["player_id", value_col])
            series = dict(zip(df["player_id"].astype(int), df[value_col]))
            results.append(score_index(name, series, swing))

    doc = build_artifact(results, n_swing_players=int(swing["player_id"].nunique()) if not swing.empty else 0)
    out_path = write_artifact(doc)
    print(f"absence_swing_validity: swing_players={doc['swing']['n_players']} "
          f"indexes={list(doc['indexes'].keys())} -> {out_path}")
    return doc


if __name__ == "__main__":
    main()
