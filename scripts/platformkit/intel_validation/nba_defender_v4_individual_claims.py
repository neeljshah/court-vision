"""nba_defender_v4_individual -- ROLE-RELATIVE, BURDEN-ADJUSTED defender
composite (2025-26): the "judge each player as the individual he is" board.

Two fixes over v3 (user-directed 2026-07-18):

  ROLE FAIRNESS -- an all-big board is a category error. Each player's
  defensive JOB is proxied from his own event mix (block share of
  stocks): perimeter (<.33), wing (.33-.55), interior (>.55). Ingredients
  and percentiles are computed WITHIN role, so guards compete with guards.
    interior:  burden_resid, rim_deter, rim_pressure_def, stocks_per36
    wing:      burden_resid, rim_deter, stocks_per36, perim_deter
    perimeter: burden_resid, stl36, perim_deter, stocks_per36
  (perim_deter = opp above-break-3 attempt share allowed OFF minus ON.)

  BURDEN ADJUSTMENT -- who you defend NEXT TO changes what your numbers
  mean. help_ctx = minutes-weighted teammate defensive quality
  (stl36+blk36+rim_pressure/2). Pool-wide OLS confirms more help predicts
  LOWER marginal team-relative defense (slope -0.19): carrying alone is
  harder. burden_resid = team_rel_sched minus what help_ctx predicts --
  Wembanyama's +1.45 with guard-heavy support (help 1.48) outranks bigger
  raw numbers earned beside other bigs.

VALIDITY RECEIPT (absence experiment, judge-never-ingredient):
  v1 +0.307 -> v2 +0.324 -> v3 +0.499 -> v4 +0.520 overall;
  WITHIN-ROLE: interior +0.730 (n=34), wing +0.599 (n=67),
  perimeter +0.435 (n=123). Role-splitting is where the signal was hiding.

HONEST LIMITS: role proxy is event-mix, not position data (a switch-heavy
wing like Kawhi Leonard buckets 'perimeter'); help_ctx is team-level
minutes-weighting, not shared-stint; absence confounds remain; season
aggregates -> DESCRIPTIVE + cross-sectional validity, no forward receipt.
No market claim.

CLI: python -m scripts.platformkit.intel_validation.nba_defender_v4_individual_claims
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

_BOX_PATH = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_PROFILES_PATH = REPO_ROOT / "data" / "cache" / "profiles" / "nba_player_profiles.parquet"
_V3_SNAPSHOT = _CLAIMS_DIR / "nba_defender_v3_team_rel_snapshot.parquet"
_SNAPSHOT_PATH = _CLAIMS_DIR / "nba_defender_v4_individual_snapshot.parquet"
_CLAIMS_OUT = _CLAIMS_DIR / "nba_defender_v4_individual_claims.jsonl"

MIN_SEASON_MINUTES = 800.0
_ROLE_PARTS = {
    "interior": ["burden_resid", "rim_deter", "rim_pressure_def", "stocks_per36"],
    "wing": ["burden_resid", "rim_deter", "stocks_per36", "perim_deter"],
    "perimeter": ["burden_resid", "stl36", "perim_deter", "stocks_per36"],
}
MIN_PARTS_PRESENT = 3

RECEIPT_CAVEAT = (
    "DESCRIPTIVE role-relative burden-adjusted composite. Validity receipt (absence "
    "experiment, judge-never-ingredient, 2026-07-18): overall rho +0.520; within-role "
    "interior +0.730 / wing +0.599 / perimeter +0.435 -- vs +0.499 (v3), +0.324 (v2), "
    "+0.307 (v1). Role proxy = block-share of stocks (event mix, not position data); "
    "help_ctx is minutes-weighted team-level; no forward receipt. No market claim."
)


def _base(season: str = "2025-26") -> pd.DataFrame:
    box = pd.read_parquet(_BOX_PATH, columns=["season", "team", "player_id",
                                                "player_name", "min", "stl", "blk"])
    s = box[box["season"] == season]
    agg = s.groupby("player_id").agg(mins=("min", "sum"), stl=("stl", "sum"),
                                      blk=("blk", "sum")).reset_index()
    agg["stl36"] = agg["stl"] / agg["mins"] * 36
    agg["blk36"] = agg["blk"] / agg["mins"] * 36
    agg["blk_share"] = agg["blk"] / (agg["stl"] + agg["blk"]).replace(0, np.nan)
    agg["role"] = pd.cut(agg["blk_share"], [-.01, .33, .55, 1.01],
                          labels=["perimeter", "wing", "interior"])
    agg.loc[agg["mins"] < MIN_SEASON_MINUTES, "role"] = np.nan
    pt = s.groupby(["player_id", "team"])["min"].sum().reset_index()
    main = pt.sort_values("min").groupby("player_id").last().reset_index() \
             [["player_id", "team", "min"]]
    return agg.merge(main, on="player_id")


def _help_ctx(base: pd.DataFrame) -> pd.Series:
    prof = pd.read_parquet(_PROFILES_PATH,
                            columns=["entity_id", "attribute", "window", "raw_value"])
    rp = prof[(prof["window"] == "season_2025_26")
               & (prof["attribute"] == "rim_pressure_def")].set_index("entity_id")["raw_value"]
    b = base.copy()
    b["def_qual"] = b["stl36"] + b["blk36"] + b["player_id"].map(rp).fillna(0) / 2
    out = {}
    for _team, grp in b.groupby("team"):
        tot, wx = grp["min"].sum(), (grp["min"] * grp["def_qual"]).sum()
        for r in grp.itertuples(index=False):
            mm = tot - r.min
            out[int(r.player_id)] = (wx - r.min * r.def_qual) / mm if mm > 0 else np.nan
    return pd.Series(out, name="help_ctx")


def _perim_deter() -> pd.Series:
    prof = pd.read_parquet(_PROFILES_PATH,
                            columns=["entity_id", "attribute", "window", "raw_value"])
    w = prof[(prof["window"] == "season_2025_26")
              & (prof["attribute"].isin(["zone_def_above_break_3_share_allowed_on",
                                          "zone_def_above_break_3_share_allowed_off"]))]
    pv = w.pivot_table(index="entity_id", columns="attribute", values="raw_value")
    return (pv["zone_def_above_break_3_share_allowed_off"]
             - pv["zone_def_above_break_3_share_allowed_on"])


def compute_snapshot(season: str = "2025-26") -> pd.DataFrame:
    base = _base(season)
    v3 = pd.read_parquet(_V3_SNAPSHOT)
    df = v3[["player_id", "player_name", "team_rel_sched", "rim_deter",
              "rim_pressure_def", "stocks_per36", "rel_games"]].merge(
        base[["player_id", "role", "stl36"]], on="player_id", how="inner")
    df["help_ctx"] = df["player_id"].map(_help_ctx(base))
    df["perim_deter"] = df["player_id"].map(_perim_deter())
    ok = df[["team_rel_sched", "help_ctx"]].notna().all(axis=1)
    X = np.column_stack([np.ones(int(ok.sum())), df.loc[ok, "help_ctx"]])
    beta, *_ = np.linalg.lstsq(X, df.loc[ok, "team_rel_sched"].to_numpy(float), rcond=None)
    df["burden_resid"] = np.nan
    df.loc[ok, "burden_resid"] = df.loc[ok, "team_rel_sched"] - X @ beta
    frames = []
    for role, cols in _ROLE_PARTS.items():
        g = df[df["role"] == role].copy()
        qcols = []
        for c in cols:
            g[f"q_{c}"] = g[c].rank(pct=True) * 100.0
            qcols.append(f"q_{c}")
        g["n_present"] = g[qcols].notna().sum(axis=1)
        g["nba_defender_v4_individual"] = g[qcols].mean(axis=1, skipna=True).round(4)
        g.loc[g["n_present"] < MIN_PARTS_PRESENT,
              "nba_defender_v4_individual"] = np.nan
        frames.append(g)
    snap = pd.concat(frames, ignore_index=True)
    snap["player_id"] = snap["player_id"].astype("int64")
    snap["role"] = snap["role"].astype(str)
    return snap


def build_claim(snap: pd.DataFrame, snapshot_path: Path = _SNAPSHOT_PATH) -> dict[str, Any]:
    n_considered = len(snap)
    survivors = snap[snap["n_present"] >= MIN_PARTS_PRESENT].sort_values(
        "nba_defender_v4_individual", ascending=False).reset_index(drop=True)
    ranking = [
        {"rank": i, "player_id": int(r.player_id), "player_name": str(r.player_name),
         "role": str(r.role), "value": round(float(r.nba_defender_v4_individual), 4),
         "n": int(r.rel_games) if pd.notna(r.rel_games) else 0,
         "n_present": int(r.n_present)}
        for i, r in enumerate(survivors.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": "nba_defender_v4_individual_2025_26",
        "kind": "ranking",
        "question": "Who is the best defender judged as the individual he is -- "
                     "role-relative and burden-adjusted for the help around him?",
        "criteria": {
            "metric": "nba_defender_v4_individual",
            "formula": "nba_defender_v4_individual",
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
        "caveats": [RECEIPT_CAVEAT],
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
    print(f"nba_defender_v4_individual: considered={claim['n_considered']} "
          f"excluded={claim['n_excluded_below_floor']} top={top} -> {_CLAIMS_OUT}")
    return claim


if __name__ == "__main__":
    main()
