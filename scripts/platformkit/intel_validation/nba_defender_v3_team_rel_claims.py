"""nba_defender_v3_team_rel -- TEAM-RELATIVE defender composite, validated
against the absence experiment (2025-26).

v2's remaining lie, fixed: its schedule adjustment was TEAM defense while
he played, so elite-team players (Queta/BOS) inherited team credit. v3
measures every player ABOVE HIS OWN TEAM'S BASELINE:

  team_rel_sched   mean over his 15+min games of
                   (game def_delta - his team's season-mean def_delta)
                   where def_delta = opp season ppg - actual allowed.
                   A Celtic must beat BOSTON's +8.1, not the league's 0.

  partner_resid_rim / rim_deter / rim_pressure_def / stocks_per36
                   unchanged from v2 (partner-adjusted, luck-weighted).

Equal-weight percentile mean, >=3/5 present; unfiltered population in the
snapshot so the validator re-derives floors.

VALIDATION RECEIPT (the analytics-validated-by-prediction loop, measured):
Spearman rho of index vs ABSENCE SWING (def_delta in games played minus
games missed; >=30 played, >=8 missed; n=236):
  v1 naive        rho +0.307
  v2 context      rho +0.324
  v3 team-rel     rho +0.499
Each generation predicts what actually happens when players sit BETTER --
the number that justifies this module's existence. Absence swing is kept
OUT of the index (it is the judge, never an ingredient -- no circularity).

HONEST LIMITS: matchup/tracking data absent; absence games carry roster
confound (other absences correlate); season aggregates -> DESCRIPTIVE, the
rho above is a cross-sectional validity score, not a forward receipt.
No market claim.

CLI: python -m scripts.platformkit.intel_validation.nba_defender_v3_team_rel_claims
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

from scripts.platformkit.predictive_validity.validity_ladder import ladder_caveat

from scripts.platformkit.intel_validation.shooter_composite_v2_claims import (
    REPO_ROOT,
    _CLAIMS_DIR,
    _rel,
)

_BOX_PATH = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_V2_SNAPSHOT = _CLAIMS_DIR / "nba_defender_v2_context_snapshot.parquet"
_SNAPSHOT_PATH = _CLAIMS_DIR / "nba_defender_v3_team_rel_snapshot.parquet"
_CLAIMS_OUT = _CLAIMS_DIR / "nba_defender_v3_team_rel_claims.jsonl"

MIN_GAME_MINUTES = 15.0
MIN_REL_GAMES = 20
_PARTS = ["pctl_team_rel_sched", "pctl_partner_resid_rim", "pctl_rim_deter",
           "pctl_rim_pressure_def", "pctl_stocks_per36"]
MIN_PARTS_PRESENT = 3

VALIDATION_CAVEAT = (
    "DESCRIPTIVE team-relative composite. Validity receipt: Spearman rho +0.499 (n=236, "
    "2026-07-18) against the absence-swing experiment (def-vs-expectation in games played "
    "minus games missed) -- vs +0.307 (v1) and +0.324 (v2); absence swing is the judge, "
    "never an ingredient. Matchup/tracking data absent; absence games carry roster "
    "confound; no forward receipt. No market claim."
)


def _team_rel(season: str = "2025-26") -> pd.DataFrame:
    box = pd.read_parquet(_BOX_PATH, columns=["game_id", "season", "team", "opp",
                                                "player_id", "min", "pts"])
    s = box[box["season"] == season]
    tg = s.groupby(["game_id", "team", "opp"], as_index=False)["pts"].sum() \
          .rename(columns={"pts": "team_pts"})
    opp_ppg = tg.groupby("team")["team_pts"].mean()
    al = tg.merge(tg[["game_id", "team", "team_pts"]]
                   .rename(columns={"team": "opp", "team_pts": "pts_allowed"}),
                   on=["game_id", "opp"])
    al["def_delta"] = al["opp"].map(opp_ppg) - al["pts_allowed"]
    team_base = al.groupby("team")["def_delta"].mean()
    pg = s[s["min"] >= MIN_GAME_MINUTES][["game_id", "team", "player_id"]] \
        .merge(al[["game_id", "team", "def_delta"]], on=["game_id", "team"])
    pg["rel"] = pg["def_delta"] - pg["team"].map(team_base)
    agg = pg.groupby("player_id").agg(rel_games=("rel", "size"),
                                       team_rel_sched=("rel", "mean")).reset_index()
    agg.loc[agg["rel_games"] < MIN_REL_GAMES, "team_rel_sched"] = float("nan")
    return agg


def compute_snapshot(season: str = "2025-26") -> pd.DataFrame:
    v2 = pd.read_parquet(_V2_SNAPSHOT)
    df = v2[["player_id", "player_name", "partner_resid_rim", "rim_deter",
              "rim_pressure_def", "stocks_per36"]].copy()
    df = df.merge(_team_rel(season), on="player_id", how="left")
    df["player_id"] = df["player_id"].astype("int64")
    for col in ("team_rel_sched", "partner_resid_rim", "rim_deter",
                "rim_pressure_def", "stocks_per36"):
        df[f"pctl_{col}"] = df[col].rank(pct=True) * 100.0
    df["n_present"] = df[_PARTS].notna().sum(axis=1)
    df["nba_defender_v3_team_rel"] = df[_PARTS].mean(axis=1, skipna=True).round(4)
    df.loc[df["n_present"] < MIN_PARTS_PRESENT,
           "nba_defender_v3_team_rel"] = float("nan")
    return df


def build_claim(snap: pd.DataFrame, snapshot_path: Path = _SNAPSHOT_PATH) -> dict[str, Any]:
    n_considered = len(snap)
    survivors = snap[snap["n_present"] >= MIN_PARTS_PRESENT].sort_values(
        "nba_defender_v3_team_rel", ascending=False).reset_index(drop=True)
    ranking = [
        {"rank": i, "player_id": int(r.player_id), "player_name": str(r.player_name),
         "value": round(float(r.nba_defender_v3_team_rel), 4),
         "n": int(r.rel_games) if pd.notna(r.rel_games) else 0,
         "n_present": int(r.n_present)}
        for i, r in enumerate(survivors.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": "nba_defender_v3_team_rel_2025_26",
        "kind": "ranking",
        "question": "Who is the best defender measured ABOVE his own team's baseline, "
                     "validated against the absence experiment?",
        "criteria": {
            "metric": "nba_defender_v3_team_rel",
            "formula": "nba_defender_v3_team_rel",
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
        "caveats": [VALIDATION_CAVEAT, ladder_caveat("nba_defender_v3_team_rel")],
    }


def main() -> dict[str, Any]:
    snap = compute_snapshot()
    _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(snap, preserve_index=False), _SNAPSHOT_PATH)
    claim = build_claim(snap)
    _CLAIMS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_CLAIMS_OUT, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(claim, ensure_ascii=True) + "\n")
    top = claim["ranking"][0]["player_name"] if claim["ranking"] else "NONE"
    print(f"nba_defender_v3_team_rel: considered={claim['n_considered']} "
          f"excluded={claim['n_excluded_below_floor']} top={top} -> {_CLAIMS_OUT}")
    return claim


if __name__ == "__main__":
    main()
