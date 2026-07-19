"""nba_defender_v2_context -- CONTEXT-ADJUSTED defender composite (2025-26).

nba_defender_v1's declared confounds, now measured and adjusted instead of
just declared:

  WHO YOU FACED (schedule adjustment)
    sched_adj_def: for every game the player logged >=15 min, take the
    opponent's SEASON scoring average minus what they actually scored that
    night -- positive means offenses underperform their own norm when he
    plays. Minutes-share-weighted mean over his games. A player feasting on
    bad offenses stops looking elite here.

  WHO DEFENDED NEXT TO YOU (partner adjustment)
    partner_resid_rim: OLS residual of his rim-protection on/off delta on
    his teammates' minutes-weighted rim_pressure_def -- rim numbers earned
    next to another elite rim protector get discounted; rim numbers earned
    alone get credited.

  WHAT DEFENSE CONTROLS (luck weighting)
    rim DETERRENCE (opponents stop attempting rim shots) is kept over raw
    3-point eFG allowed: opponent 3P% is the noisiest defensive result and
    v1's three_contest ingredient is dropped for it.

  Plus the two direct signals: rim_pressure_def, stocks_per36.

Score = equal-weight mean of 5 percentiles (>=3 present); zone deltas floor
at 500+ minutes, schedule adjustment floors at 20+ games of >=15 min.

HONEST LIMITS (still declared): matchup data (who he PERSONALLY guarded)
does not exist for 2025-26 -- schedule adjustment is team-level while he
played, so individual attribution is partial; partner adjustment covers rim
partners, not full 5-man scheme; season aggregates -> no forward receipt.
DESCRIPTIVE, validator-VERIFIED, no market claim.

CLI: python -m scripts.platformkit.intel_validation.nba_defender_v2_context_claims
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

from scripts.platformkit.intel_validation.shooter_composite_v2_claims import (
    REPO_ROOT,
    _CLAIMS_DIR,
    _rel,
)
from scripts.platformkit.intel_validation.nba_defender_v1_claims import load_raw as _v1_raw

_BOX_PATH = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_SNAPSHOT_PATH = _CLAIMS_DIR / "nba_defender_v2_context_snapshot.parquet"
_CLAIMS_OUT = _CLAIMS_DIR / "nba_defender_v2_context_claims.jsonl"

MIN_GAME_MINUTES = 15.0
MIN_SCHED_GAMES = 20
_PARTS = ["pctl_sched_adj_def", "pctl_partner_resid_rim", "pctl_rim_deter",
           "pctl_rim_pressure_def", "pctl_stocks_per36"]
MIN_PARTS_PRESENT = 3

ATTRIBUTION_CAVEAT = (
    "DESCRIPTIVE context-adjusted composite: schedule adjustment is TEAM defense while he "
    "played (individual attribution partial -- no matchup/tracking data exists for "
    "2025-26); partner adjustment residualizes rim numbers on teammates' rim_pressure_def "
    "only, not full 5-man scheme; opponent-3P%-based results dropped as luck-heavy by "
    "declared design. Season aggregates -> no as-of variant -> no forward receipt. "
    "No market claim."
)


def _sched_adj(season: str = "2025-26") -> pd.DataFrame:
    box = pd.read_parquet(_BOX_PATH, columns=["game_id", "season", "team", "opp",
                                                "player_id", "min", "pts"])
    s = box[box["season"] == season]
    tg = s.groupby(["game_id", "team", "opp"], as_index=False)["pts"].sum() \
          .rename(columns={"pts": "team_pts"})
    opp_ppg = tg.groupby("team")["team_pts"].mean()
    allowed = tg.merge(tg[["game_id", "team", "team_pts"]]
                        .rename(columns={"team": "opp", "team_pts": "pts_allowed"}),
                        on=["game_id", "opp"], how="left")
    allowed["opp_season_ppg"] = allowed["opp"].map(opp_ppg)
    allowed["def_delta"] = allowed["opp_season_ppg"] - allowed["pts_allowed"]
    pg = s[s["min"] >= MIN_GAME_MINUTES][["game_id", "team", "player_id", "min"]]
    pg = pg.merge(allowed[["game_id", "team", "def_delta"]], on=["game_id", "team"],
                   how="left")
    agg = pg.groupby("player_id").agg(
        sched_games=("def_delta", "size"),
        sched_adj_def=("def_delta", "mean"))
    agg.loc[agg["sched_games"] < MIN_SCHED_GAMES, "sched_adj_def"] = float("nan")
    return agg.reset_index()


def _teammate_rim_ctx(raw: pd.DataFrame, season: str = "2025-26") -> pd.Series:
    """Minutes-weighted mean rim_pressure_def of TEAMMATES (same team, self
    excluded). Team from each player's modal 2025-26 team in boxscores."""
    box = pd.read_parquet(_BOX_PATH, columns=["season", "team", "player_id", "min"])
    s = box[box["season"] == season]
    pt = s.groupby(["player_id", "team"])["min"].sum().reset_index()
    main = pt.sort_values("min").groupby("player_id").last().reset_index()
    m = main.merge(raw[["player_id", "rim_pressure_def"]], on="player_id", how="left")
    out = {}
    for team, grp in m.groupby("team"):
        g = grp.dropna(subset=["rim_pressure_def"])
        tot_min = g["min"].sum()
        tot_wx = (g["min"] * g["rim_pressure_def"]).sum()
        for r in grp.itertuples(index=False):
            if pd.notna(r.rim_pressure_def):
                mm, wx = tot_min - r.min, tot_wx - r.min * r.rim_pressure_def
            else:
                mm, wx = tot_min, tot_wx
            out[int(r.player_id)] = wx / mm if mm > 0 else float("nan")
    return pd.Series(out, name="teammate_rim_ctx")


def compute_snapshot(season: str = "2025-26") -> pd.DataFrame:
    df = _v1_raw(season)  # player_id, rim_protect, rim_deter, rim_pressure_def, stocks..., zone_minutes
    df = df.merge(_sched_adj(season), on="player_id", how="left")
    ctx = _teammate_rim_ctx(df, season)
    df["teammate_rim_ctx"] = df["player_id"].map(ctx)
    # partner residual: rim_protect explained by teammates' rim defense
    ok = df[["rim_protect", "teammate_rim_ctx"]].notna().all(axis=1)
    X = np.column_stack([np.ones(int(ok.sum())), df.loc[ok, "teammate_rim_ctx"]])
    beta, *_ = np.linalg.lstsq(X, df.loc[ok, "rim_protect"].to_numpy(float), rcond=None)
    df["partner_resid_rim"] = float("nan")
    df.loc[ok, "partner_resid_rim"] = df.loc[ok, "rim_protect"] - X @ beta
    for col in ("sched_adj_def", "partner_resid_rim", "rim_deter",
                "rim_pressure_def", "stocks_per36"):
        df[f"pctl_{col}"] = df[col].rank(pct=True) * 100.0
    df["n_present"] = df[_PARTS].notna().sum(axis=1)
    df["nba_defender_v2_context"] = df[_PARTS].mean(axis=1, skipna=True).round(4)
    df.loc[df["n_present"] < MIN_PARTS_PRESENT, "nba_defender_v2_context"] = float("nan")
    return df


def build_claim(snap: pd.DataFrame, snapshot_path: Path = _SNAPSHOT_PATH) -> dict[str, Any]:
    n_considered = len(snap)
    survivors = snap[snap["n_present"] >= MIN_PARTS_PRESENT].sort_values(
        "nba_defender_v2_context", ascending=False).reset_index(drop=True)
    ranking = [
        {"rank": i, "player_id": int(r.player_id), "player_name": str(r.player_name),
         "value": round(float(r.nba_defender_v2_context), 4),
         "n": int(r.sched_games) if pd.notna(r.sched_games) else 0,
         "n_present": int(r.n_present)}
        for i, r in enumerate(survivors.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": "nba_defender_v2_context_2025_26",
        "kind": "ranking",
        "question": "Who is the best defender once schedule faced, rim partners, and "
                     "defensive luck are adjusted for?",
        "criteria": {
            "metric": "nba_defender_v2_context",
            "formula": "nba_defender_v2_context",
            "min_sample": {"n_present": MIN_PARTS_PRESENT},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
            "window": "2025-26",
        },
        "ranking": ranking,
        "source_files": [_rel(snapshot_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_considered - len(survivors),
        "edge_claimed": False,
        "caveats": [ATTRIBUTION_CAVEAT],
    }


def main() -> dict[str, Any]:
    snap = compute_snapshot()
    _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(snap, preserve_index=False), _SNAPSHOT_PATH)
    claim = build_claim(snap)
    path = _CLAIMS_OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(claim, ensure_ascii=True) + "\n")
    top = claim["ranking"][0]["player_name"] if claim["ranking"] else "NONE"
    print(f"nba_defender_v2_context: considered={claim['n_considered']} "
          f"excluded={claim['n_excluded_below_floor']} top={top} -> {path}")
    return claim


if __name__ == "__main__":
    main()
