"""shooter_isolated_v4 -- CONTEXT-ISOLATED individual shooting skill.

The question this answers: strip away WHO CREATES YOUR LOOKS and HOW EASY
YOUR SHOT DIET IS -- how good is the individual shooter? (The "Curry next
to a superstar passer would post prettier raw numbers" problem: raw
efficiency rewards received context; this index residualizes it out.)

METHOD (declared, cross-sectional, own-store 2025-26 data only):
  outcome   fg3_pct (season makes/attempts)
  context X (all per player, same pool):
    assisted_3_share   attempt-share-weighted assisted share across
                       corner3 + above-break-3 (the HELP axis -- an elite
                       teammate creator raises this)
    corner_diet_share  corner3A / (corner3A + ab3A) attempt mix (corner
                       threes are the easiest three -- shot-DIET axis)
    gravity            lineup-derived defensive-attention proxy (the
                       ATTENTION axis -- more warp = harder looks)
  fit      OLS (numpy lstsq, intercept) of fg3_pct on X across the pool
  residual = actual fg3_pct - context-expected fg3_pct
  score    = equal-weight mean of 3 percentiles (>=2 present):
    pctl(residual)             shot-making beyond context
    pctl(ft_pct)               pure stroke, zero context by construction
    pctl(self_created_volume)  fg3a_per_game * (1 - assisted_3_share) --
                               the difficulty burden actually carried

HONEST LIMITS (declared, not hidden): openness is PROXIED by assisted
share (no defender-distance/contest feed exists for 2025-26 -- source
blocked); teammate-creator quality enters only through assisted share, not
a named-teammate term; cross-sectional OLS residuals are DESCRIPTIVE --
season-aggregate inputs have no as-of variant, so no leak-free forward
receipt is possible (see shooter_composite_v2_asof_approx for the
forecasting-grade index). Validator-VERIFIED via identity recompute on the
snapshot. No market/edge claim.

CLI: python -m scripts.platformkit.intel_validation.shooter_isolated_v4_claims
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.basketball_nba.quality_claim_builders import rank_of
from domains.basketball_nba.quality_indices import (
    QUALIFY_MIN_FGA,
    QUALIFY_MIN_GAMES,
    aggregate_season,
    load_boxscores,
    qualifying_pool,
)
from scripts.platformkit.intel_validation.shooter_composite_v2_claims import (
    REPO_ROOT,
    _CLAIMS_DIR,
    _rel,
)

_SNAPSHOT_PATH = _CLAIMS_DIR / "shooter_isolated_v4_snapshot.parquet"
_CLAIMS_OUT = _CLAIMS_DIR / "shooter_isolated_v4_claims.jsonl"
_PROFILES_PATH = REPO_ROOT / "data" / "cache" / "profiles" / "nba_player_profiles.parquet"

_ATTRS = ["zone_assisted_share_above_break_3", "zone_assisted_share_corner3",
           "zone_attempt_share_above_break_3", "zone_attempt_share_corner3",
           "gravity"]
_X_COLS = ["assisted_3_share", "corner_diet_share", "gravity"]
_SCORE_PARTS = ["pctl_context_resid", "pctl_ft_pct", "pctl_self_created_volume"]
MIN_PARTS_PRESENT = 2

CONTEXT_CAVEAT = (
    "DESCRIPTIVE context-adjusted index: cross-sectional OLS residual of fg3_pct on "
    "assisted-share/corner-diet/gravity. Openness is PROXIED by assisted share (no "
    "defender-distance feed for 2025-26); teammate-creator quality enters only via "
    "assisted share. Season-aggregate inputs -> no as-of variant -> no forward receipt "
    "possible; forecasting-grade shooting lives in shooter_composite_v2_asof_approx. "
    "No market/edge claim."
)


def _profile_wide(season: str, path: Path = _PROFILES_PATH) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=["entity_id", "attribute", "window", "raw_value"])
    df = df[(df["window"] == "season_" + season.replace("-", "_"))
            & (df["attribute"].isin(_ATTRS))]
    wide = df.pivot_table(index="entity_id", columns="attribute",
                           values="raw_value", aggfunc="first").reset_index()
    return wide.rename(columns={"entity_id": "player_id"})


def load_raw(season: str) -> pd.DataFrame:
    box = load_boxscores()
    pool = qualifying_pool(aggregate_season(box, season=season),
                            min_games=QUALIFY_MIN_GAMES, min_fga=QUALIFY_MIN_FGA)
    out = pool[["player_id", "player_name", "games"]].copy()
    out["fg3a_per_game"] = pool["fg3a_pg"]
    out["fg3_pct"] = (pool["fg3m"] / pool["fg3a"]).replace(
        [float("inf"), float("-inf")], float("nan"))
    out["ft_pct"] = pool["ft_pct"]
    out = out.merge(_profile_wide(season), on="player_id", how="left")
    out["player_id"] = out["player_id"].astype("int64")
    ab_a = out["zone_attempt_share_above_break_3"]
    c_a = out["zone_attempt_share_corner3"]
    tot = (ab_a.fillna(0) + c_a.fillna(0)).replace(0, float("nan"))
    out["corner_diet_share"] = c_a.fillna(0) / tot
    out["assisted_3_share"] = (
        out["zone_assisted_share_above_break_3"].fillna(0) * ab_a.fillna(0)
        + out["zone_assisted_share_corner3"].fillna(0) * c_a.fillna(0)) / tot
    out["self_created_volume"] = out["fg3a_per_game"] * (1.0 - out["assisted_3_share"])
    return out


def fit_context_residual(df: pd.DataFrame) -> pd.Series:
    """OLS residual of fg3_pct on the context features, pool-wide."""
    ok = df[_X_COLS + ["fg3_pct"]].notna().all(axis=1)
    X = df.loc[ok, _X_COLS].to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(X)), X])
    y = df.loc[ok, "fg3_pct"].to_numpy(dtype=float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = pd.Series(float("nan"), index=df.index)
    resid.loc[ok] = y - X @ beta
    return resid


def compute_snapshot(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["context_resid"] = fit_context_residual(df)
    for col in ("context_resid", "ft_pct", "self_created_volume"):
        df[f"pctl_{col}"] = df[col].rank(pct=True) * 100.0
    df["n_present"] = df[_SCORE_PARTS].notna().sum(axis=1)
    df["shooter_isolated_v4"] = df[_SCORE_PARTS].mean(axis=1, skipna=True).round(4)
    df.loc[df["n_present"] < MIN_PARTS_PRESENT, "shooter_isolated_v4"] = float("nan")
    return df


def build_claim(snap: pd.DataFrame, season: str,
                snapshot_path: Path = _SNAPSHOT_PATH) -> dict[str, Any]:
    n_considered = len(snap)
    survivors = snap[snap["n_present"] >= MIN_PARTS_PRESENT].sort_values(
        "shooter_isolated_v4", ascending=False).reset_index(drop=True)
    ranking = [
        {"rank": i, "player_id": int(r.player_id), "player_name": str(r.player_name),
         "value": round(float(r.shooter_isolated_v4), 4),
         "n": int(r.games), "n_present": int(r.n_present)}
        for i, r in enumerate(survivors.itertuples(index=False), start=1)
    ]
    season_id = season.replace("-", "_")
    return {
        "claim_id": f"shooter_isolated_v4_full_season_{season_id}",
        "kind": "ranking",
        "question": "Who is the best INDIVIDUAL shooter once context (assisted looks, "
                     "shot diet, defensive attention) is adjusted away?",
        "criteria": {
            "metric": "shooter_isolated_v4",
            "formula": "shooter_isolated_v4",
            "min_sample": {"n_present": MIN_PARTS_PRESENT},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
            "window": season,
        },
        "ranking": ranking,
        "face_validity_diagnostic": {
            "type": "reported_never_a_fitting_target",
            "stephen_curry_rank": rank_of(
                snap.rename(columns={"shooter_isolated_v4": "_rk"}), "_rk", "Stephen Curry"),
            "n_qualifying": n_considered,
        },
        "source_files": [_rel(snapshot_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_considered - len(survivors),
        "edge_claimed": False,
        "caveats": [CONTEXT_CAVEAT],
    }


def write_claims(claim: dict[str, Any], path: Path = _CLAIMS_OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(claim, ensure_ascii=True) + "\n")
    return path


def main(season: str = "2025-26") -> dict[str, Any]:
    snap = compute_snapshot(load_raw(season))
    path = _SNAPSHOT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(snap, preserve_index=False), path)
    claim = build_claim(snap, season, path)
    out = write_claims(claim)
    print(f"shooter_isolated_v4: n_considered={claim['n_considered']} "
          f"excluded={claim['n_excluded_below_floor']} "
          f"top={claim['ranking'][0]['player_name'] if claim['ranking'] else 'NONE'} "
          f"curry_rank={claim['face_validity_diagnostic']['stephen_curry_rank']} -> {out}")
    return claim


if __name__ == "__main__":
    main()
