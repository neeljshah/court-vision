"""nba_gravity_v2 -- TRIANGULATED player-gravity composite (2025-26).

Gravity = how much a player warps defensive attention. No single on/off
number proves it (roster confound), so this composite triangulates THREE
independently-built shadows of the same warp -- if all three agree, the
evidence is much stronger than any one:

  teammate_efg_lift   teammate eFG% with him ON minus OFF
                      (data/cache/team_system/lineups/on_off_2025_26.parquet
                      -- the classic gravity proxy: everyone else's looks
                      get easier)
  net_rating_lift     team net rating per48 ON minus OFF (same table --
                      total on-court impact, wider than shooting)
  scoring_lift        team pts_per48 WITH minus WITHOUT (the teammate-
                      context lineup corpus, an independently-built stint
                      reconstruction: gravity_context_2025_26.parquet)

Each ingredient -> percentile within the floor-qualified pool, equal-weight
mean (skipna), >=2/3 present. Pair-keyed (player_id, team_id) so a trade
never blends two contexts (same rationale as nba_on_off_claims).

FLOORS: min_on>=300 minutes AND teammate FGA >=200 on both sides (identical
to the gravity_proxy claim / gravity_spacing builder); the scoring_lift
ingredient additionally carries its own upstream 12000s stint floors and is
simply absent (skipna) where they failed.

HONEST LIMITS (declared): DESCRIPTIVE, not causal -- triangulation reduces
but does not eliminate the roster/lineup confound; defender-distance
tracking does not exist for 2025-26; an AS-OF variant (gravity frozen at a
past date predicting teammates' future efficiency) needs date-sliced stint
data and is declared future work, not silently skipped. No market claim.

CLI: python -m scripts.platformkit.intel_validation.nba_gravity_v2_claims
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

_ON_OFF_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "on_off_2025_26.parquet"
_GRAVCTX_PATH = (_CLAIMS_DIR / "nba_teammate_context_gravity_snapshots"
                  / "gravity_context_2025_26.parquet")
_SNAPSHOT_PATH = _CLAIMS_DIR / "nba_gravity_v2_snapshot.parquet"
_CLAIMS_OUT = _CLAIMS_DIR / "nba_gravity_v2_claims.jsonl"

MIN_ON_MINUTES = 300.0
MIN_TEAMMATE_FGA = 200
_PARTS = ["pctl_teammate_efg_lift", "pctl_net_rating_lift", "pctl_scoring_lift"]
MIN_PARTS_PRESENT = 2

TRIANGULATION_CAVEAT = (
    "DESCRIPTIVE triangulated on/off composite -- NOT causal: roster/lineup confound is "
    "reduced by requiring three independently-built lift measurements to agree, not "
    "eliminated. No defender-distance feed exists for 2025-26. AS-OF forward test "
    "(does frozen gravity predict teammates' future efficiency?) requires date-sliced "
    "stint data -- declared future work. No market/edge claim."
)


def load_raw() -> pd.DataFrame:
    onoff = pd.read_parquet(_ON_OFF_PATH)
    df = onoff[["player_id", "team_id", "player_name", "n_games", "min_on",
                "teammate_efg_on", "teammate_efg_off",
                "teammate_fga_on", "teammate_fga_off",
                "net_rating_on_per48", "net_rating_off_per48"]].copy()
    df["teammate_efg_lift"] = df["teammate_efg_on"] - df["teammate_efg_off"]
    df["net_rating_lift"] = df["net_rating_on_per48"] - df["net_rating_off_per48"]
    grav = pd.read_parquet(_GRAVCTX_PATH)
    # apply the upstream claim's own stint floors before deriving the delta;
    # below-floor rows enter as NaN (skipna ingredient), never as noise.
    stint_ok = (grav["with_seconds"] >= 12000.0) & (grav["without_seconds"] >= 12000.0)
    grav = grav.loc[stint_ok, ["player_id", "team_id",
                                "pts_per48_with", "pts_per48_without"]].copy()
    grav["scoring_lift"] = grav["pts_per48_with"] - grav["pts_per48_without"]
    grav = grav[["player_id", "team_id", "scoring_lift"]]
    df = df.merge(grav, on=["player_id", "team_id"], how="left")
    df["player_id"] = df["player_id"].astype("int64")
    df["team_id"] = df["team_id"].astype("int64")
    return df


def compute_snapshot(raw: pd.DataFrame) -> pd.DataFrame:
    """ALL raw rows stay in the snapshot -- below-floor rows keep NaN parts
    (n_present=0) so the validator re-derives the floor itself instead of
    seeing a pre-filtered file with nothing to exclude (the exact anti-
    pattern nba_gravity_proxy_claims' docstring warns about)."""
    df = raw.copy()
    qualified = ((df["min_on"] >= MIN_ON_MINUTES)
                  & (df["teammate_fga_on"] >= MIN_TEAMMATE_FGA)
                  & (df["teammate_fga_off"] >= MIN_TEAMMATE_FGA))
    for col in ("teammate_efg_lift", "net_rating_lift", "scoring_lift"):
        pctl = df.loc[qualified, col].rank(pct=True) * 100.0  # pool = qualified only
        df[f"pctl_{col}"] = pctl.reindex(df.index)
    df["n_present"] = df[_PARTS].notna().sum(axis=1)
    df["nba_gravity_v2"] = df[_PARTS].mean(axis=1, skipna=True).round(4)
    df.loc[df["n_present"] < MIN_PARTS_PRESENT, "nba_gravity_v2"] = float("nan")
    return df


def build_claim(snap: pd.DataFrame, n_considered_raw: int,
                snapshot_path: Path = _SNAPSHOT_PATH) -> dict[str, Any]:
    survivors = snap[snap["n_present"] >= MIN_PARTS_PRESENT].sort_values(
        "nba_gravity_v2", ascending=False).reset_index(drop=True)
    ranking = [
        {"rank": i, "player_id": int(r.player_id), "team_id": int(r.team_id),
         "player_name": str(r.player_name), "value": round(float(r.nba_gravity_v2), 4),
         "n": int(r.n_games), "n_present": int(r.n_present)}
        for i, r in enumerate(survivors.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": "nba_gravity_v2_triangulated_2025_26",
        "kind": "ranking",
        "question": "Which players warp the most defensive attention (triangulated "
                     "teammate-eFG / net-rating / scoring on-off lifts)?",
        "criteria": {
            "metric": "nba_gravity_v2",
            "formula": "nba_gravity_v2",
            "min_sample": {"n_present": MIN_PARTS_PRESENT},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": ["player_id", "team_id"],
            "window": "2025-26",
        },
        "ranking": ranking,
        "source_files": [_rel(snapshot_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered_raw,
        "n_excluded_below_floor": n_considered_raw - len(survivors),
        "edge_claimed": False,
        "caveats": [TRIANGULATION_CAVEAT],
    }


def write_claims(claim: dict[str, Any], path: Path = _CLAIMS_OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(claim, ensure_ascii=True) + "\n")
    return path


def main() -> dict[str, Any]:
    raw = load_raw()
    snap = compute_snapshot(raw)
    _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(snap, preserve_index=False), _SNAPSHOT_PATH)
    claim = build_claim(snap, len(raw))
    out = write_claims(claim)
    top = claim["ranking"][0]["player_name"] if claim["ranking"] else "NONE"
    print(f"nba_gravity_v2: considered={claim['n_considered']} "
          f"excluded={claim['n_excluded_below_floor']} top={top} -> {out}")
    return claim


if __name__ == "__main__":
    main()
