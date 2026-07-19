"""nba_defender_v1 -- triangulated DEFENDER composite (2025-26).

Defense has no single stat: blocks miss deterrence, on/off misses events,
opponent eFG misses shot prevention. This composite triangulates FIVE
independently-computed defensive signals from the 2025-26 profiles store
(all own-data, no blocked sources):

  rim_protect   opp rim eFG allowed OFF minus ON (positive = rim shots get
                harder when he plays)     [zone_def_rim_efg_allowed_*]
  rim_deter     opp rim attempt-share OFF minus ON (positive = opponents
                stop even TRYING the rim) [zone_def_rim_share_allowed_*]
  three_contest opp above-break-3 eFG allowed OFF minus ON
                                          [zone_def_above_break_3_efg_allowed_*]
  rim_pressure_def  the store's own rim-pressure composite (minutes-floored
                    at build time)
  stocks_per36  steals+blocks per 36 (defensive events)

Each -> percentile within players carrying that ingredient in the 2025-26
window; equal-weight skipna mean; requires >=3/5 present. Floors: each
profile attribute already carries its builder's own minutes/volume floor;
this module additionally requires the profile row's n (minutes) >= 500 for
the zone on/off deltas so tiny stints never rank.

HONEST LIMITS (declared): DESCRIPTIVE, not causal -- on/off zone deltas
carry the lineup confound (rim numbers improve if he shares minutes with
another rim protector); no matchup/tracking data (who he actually guarded)
exists for 2025-26; no as-of variant -> no forward receipt. No market claim.

CLI: python -m scripts.platformkit.intel_validation.nba_defender_v1_claims
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.platformkit.intel_validation.shooter_composite_v2_claims import (
    REPO_ROOT,
    _CLAIMS_DIR,
    _rel,
)

_PROFILES_PATH = REPO_ROOT / "data" / "cache" / "profiles" / "nba_player_profiles.parquet"
_SNAPSHOT_PATH = _CLAIMS_DIR / "nba_defender_v1_snapshot.parquet"
_CLAIMS_OUT = _CLAIMS_DIR / "nba_defender_v1_claims.jsonl"

_ZONE_MIN_MINUTES = 500.0
_PARTS = ["pctl_rim_protect", "pctl_rim_deter", "pctl_three_contest",
           "pctl_rim_pressure_def", "pctl_stocks_per36"]
MIN_PARTS_PRESENT = 3

_ATTRS = ["zone_def_rim_efg_allowed_on", "zone_def_rim_efg_allowed_off",
           "zone_def_rim_share_allowed_on", "zone_def_rim_share_allowed_off",
           "zone_def_above_break_3_efg_allowed_on", "zone_def_above_break_3_efg_allowed_off",
           "rim_pressure_def", "stocks_per36"]

LINEUP_CAVEAT = (
    "DESCRIPTIVE triangulated defensive composite -- NOT causal: zone on/off deltas carry "
    "the lineup confound (sharing minutes with another rim protector inflates rim numbers); "
    "no matchup/tracking data exists for 2025-26 (who he actually guarded is unknown); "
    "season-aggregate ingredients -> no as-of variant -> no forward receipt. No market claim."
)


def load_raw(season: str = "2025-26") -> pd.DataFrame:
    win = "season_" + season.replace("-", "_")
    df = pd.read_parquet(_PROFILES_PATH,
                          columns=["entity_id", "entity_name", "attribute", "window",
                                   "raw_value", "n"])
    df = df[(df["window"] == win) & (df["attribute"].isin(_ATTRS))]
    vals = df.pivot_table(index="entity_id", columns="attribute",
                           values="raw_value", aggfunc="first")
    mins = df.pivot_table(index="entity_id", columns="attribute",
                           values="n", aggfunc="first")
    names = df.groupby("entity_id")["entity_name"].first()
    out = pd.DataFrame(index=vals.index)
    out["player_name"] = names
    zone_ok = mins.get("zone_def_rim_efg_allowed_on", pd.Series(dtype=float)) >= _ZONE_MIN_MINUTES

    def _delta(off_col: str, on_col: str) -> pd.Series:
        d = vals.get(off_col) - vals.get(on_col)
        return d.where(zone_ok)

    out["rim_protect"] = _delta("zone_def_rim_efg_allowed_off", "zone_def_rim_efg_allowed_on")
    out["rim_deter"] = _delta("zone_def_rim_share_allowed_off", "zone_def_rim_share_allowed_on")
    out["three_contest"] = _delta("zone_def_above_break_3_efg_allowed_off",
                                    "zone_def_above_break_3_efg_allowed_on")
    out["rim_pressure_def"] = vals.get("rim_pressure_def")
    out["stocks_per36"] = vals.get("stocks_per36")
    out["zone_minutes"] = mins.get("zone_def_rim_efg_allowed_on")
    out = out.reset_index().rename(columns={"entity_id": "player_id"})
    out["player_id"] = out["player_id"].astype("int64")
    return out


def compute_snapshot(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    for col in ("rim_protect", "rim_deter", "three_contest",
                "rim_pressure_def", "stocks_per36"):
        df[f"pctl_{col}"] = df[col].rank(pct=True) * 100.0
    df["n_present"] = df[_PARTS].notna().sum(axis=1)
    df["nba_defender_v1"] = df[_PARTS].mean(axis=1, skipna=True).round(4)
    df.loc[df["n_present"] < MIN_PARTS_PRESENT, "nba_defender_v1"] = float("nan")
    return df


def build_claim(snap: pd.DataFrame,
                snapshot_path: Path = _SNAPSHOT_PATH) -> dict[str, Any]:
    n_considered = len(snap)
    survivors = snap[snap["n_present"] >= MIN_PARTS_PRESENT].sort_values(
        "nba_defender_v1", ascending=False).reset_index(drop=True)
    ranking = [
        {"rank": i, "player_id": int(r.player_id), "player_name": str(r.player_name),
         "value": round(float(r.nba_defender_v1), 4),
         "n": int(r.zone_minutes) if pd.notna(r.zone_minutes) else 0,
         "n_present": int(r.n_present)}
        for i, r in enumerate(survivors.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": "nba_defender_v1_triangulated_2025_26",
        "kind": "ranking",
        "question": "Who is the best defender (triangulated rim protection, rim "
                     "deterrence, three-point contest, rim pressure, stocks)?",
        "criteria": {
            "metric": "nba_defender_v1",
            "formula": "nba_defender_v1",
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
        "caveats": [LINEUP_CAVEAT],
    }


def write_claims(claim: dict[str, Any], path: Path = _CLAIMS_OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(claim, ensure_ascii=True) + "\n")
    return path


def main() -> dict[str, Any]:
    snap = compute_snapshot(load_raw())
    _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(snap, preserve_index=False), _SNAPSHOT_PATH)
    claim = build_claim(snap)
    out = write_claims(claim)
    top = claim["ranking"][0]["player_name"] if claim["ranking"] else "NONE"
    print(f"nba_defender_v1: considered={claim['n_considered']} "
          f"excluded={claim['n_excluded_below_floor']} top={top} -> {out}")
    return claim


if __name__ == "__main__":
    main()
