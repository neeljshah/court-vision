"""domains.tennis.pressure_point_claims -- DESCRIPTIVE pressure-point claim
FAMILY, no prereg gate (same status as pressure_claims.py's break-point-save
ranking, which this module extends from 1 situation to 5 and from
server-only to server+returner).

Grid: situation in pressure_situations.SITUATIONS (break_point, game_point,
set_point, tiebreak_point, deuce_battle) x role in (serve, return) x metric
"points_won_rate" delta vs that player's own role-scoped baseline -- plus a
serve-only "first_serve_in_rate" delta per situation. charting_points ONLY
(see pressure_situations.py for why). Each (situation, role, metric) is one
independent ranking claim with its own UNFILTERED snapshot parquet, so
claims_validator.py recomputes n_excluded_below_floor identically -- same
contract shape as pressure_claims.py / tennis_hold_claims.py.

MIN-N FLOORS declared per situation (rarer situations get a lower floor;
below-floor players are EXCLUDED from the ranking, never zero-filled):
  break_point=200, game_point=200, set_point=50, tiebreak_point=50,
  deuce_battle=30.

edge_claimed hard-wired False everywhere. NETWORK: zero.
CLI: python -m domains.tennis.pressure_point_claims
Per-file test: python -m pytest domains/tennis/test_pressure_point_claims.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.tennis.prereg_point_mechanisms import REPO_ROOT, _CHART_PATH, _charting_match_ids, _id_frame
from domains.tennis.pressure_situations import SITUATIONS, charting_situation_state

CLAIMS_PATH = REPO_ROOT / "data/cache/intel_claims/tennis_pressure_point_claims.jsonl"
SNAPSHOT_DIR = REPO_ROOT / "data/cache/intel_claims"

MIN_N = {"break_point": 200, "game_point": 200, "set_point": 50, "tiebreak_point": 50, "deuce_battle": 30}
ROLES = ("serve", "return")


def build_long_table(chart_raw: pd.DataFrame) -> pd.DataFrame:
    """One row per (point, role): player_name, role, won, first_serve_in,
    date, and every situation flag -- role='return' mirrors the same point
    with won=1-server_won so break/game/set-point "server vs returner"
    perspectives both fall out of one grouped mean."""
    state = charting_situation_state(chart_raw)
    ids = _id_frame(_charting_match_ids(chart_raw["match_id"])).rename(
        columns={"p1_id": "p1_name", "p2_id": "p2_name"})
    s = state.merge(ids, on="match_id", how="left")
    is_p1_server = s["server"].to_numpy() == 1
    server_name = np.where(is_p1_server, s["p1_name"], s["p2_name"])
    returner_name = np.where(is_p1_server, s["p2_name"], s["p1_name"])
    first_serve_in = (~s["is_second_serve"].to_numpy().astype(bool)).astype(int)

    cols = {c: s[c].to_numpy() for c in SITUATIONS}
    serve_rows = pd.DataFrame({
        "player_name": server_name, "role": "serve", "won": s["server_won"].to_numpy(),
        "first_serve_in": first_serve_in, "date": s["date"].to_numpy(), **cols,
    })
    return_rows = pd.DataFrame({
        "player_name": returner_name, "role": "return", "won": 1 - s["server_won"].to_numpy(),
        "first_serve_in": 0, "date": s["date"].to_numpy(), **cols,
    })
    return pd.concat([serve_rows, return_rows], ignore_index=True)


def _build_claim(long_df: pd.DataFrame, situation: str, role: str, metric_col: str,
                  metric_label: str, snapshot_dir: Path = SNAPSHOT_DIR) -> Dict[str, Any]:
    scoped = long_df[long_df["role"] == role]
    base = scoped.groupby("player_name").agg(
        baseline=(metric_col, "mean"),
        yr_min=("date", lambda x: int(pd.to_datetime(x).dt.year.min())),
        yr_max=("date", lambda x: int(pd.to_datetime(x).dt.year.max())))
    situ = scoped[scoped[situation]].groupby("player_name")[metric_col].agg(["mean", "size"])
    situ = situ.rename(columns={"mean": "situ_rate", "size": "n_situ"})
    joined = base.join(situ, how="inner").reset_index()
    joined["delta"] = joined["situ_rate"] - joined["baseline"]
    joined["abs_delta"] = joined["delta"].abs()

    claim_id = f"tennis_pressure_point_claims__{situation}__{role}__{metric_label}"
    snapshot_path = snapshot_dir / f"{claim_id}_snapshot.parquet"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(joined, preserve_index=False), snapshot_path)

    floor = MIN_N[situation]
    qualifying = joined[joined["n_situ"] >= floor]
    n_excluded = len(joined) - len(qualifying)
    top = qualifying.sort_values("abs_delta", ascending=False).head(50)
    ranking = [{"rank": i + 1, "player_name": r["player_name"], "value": round(float(r["abs_delta"]), 4),
                "delta": round(float(r["delta"]), 4), "n": int(r["n_situ"]),
                "years": f"{r['yr_min']}-{r['yr_max']}"} for i, (_, r) in enumerate(top.iterrows())]
    role_label = "serving" if role == "serve" else "returning"
    return {
        "claim_id": claim_id, "kind": "ranking",
        "question": f"Which players' {metric_label.replace('_', ' ')} deviates most from their own "
                    f"baseline while {role_label} on {situation.replace('_', ' ')} points?",
        "criteria": {
            "metric": "abs_delta", "formula": "abs_delta", "window": "career_to_date",
            "min_sample": {"n_situ": floor}, "direction": "desc",
            "value_precision": 4, "entity_key": "player_name",
        },
        "ranking": ranking,
        "source_files": [str(snapshot_path.relative_to(REPO_ROOT)).replace("\\", "/")]
        if snapshot_dir == SNAPSHOT_DIR else [str(snapshot_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": len(joined), "n_excluded_below_floor": int(n_excluded),
        "edge_claimed": False,
        "caveats": [
            "charting_points only -- slam_points.parquet has no player-identity column and no "
            "serve-in flag (ace/double-fault rate deltas on slam are a documented follow-up).",
            "set_point assumes standard ad-scoring; deuce_battle is a >=3-prior-deuce proxy, not "
            "a literal single-deuce-point flag -- see pressure_situations.py.",
            "DESCRIPTIVE ranking only -- no forecasting/market/$ edge claimed.",
        ],
    }


def build_pressure_point_claims(chart_raw: pd.DataFrame, snapshot_dir: Path = SNAPSHOT_DIR) -> List[Dict[str, Any]]:
    long_df = build_long_table(chart_raw)
    claims = []
    for situation in SITUATIONS:
        for role in ROLES:
            claims.append(_build_claim(long_df, situation, role, "won", "points_won_rate_delta", snapshot_dir))
        claims.append(_build_claim(long_df, situation, "serve", "first_serve_in",
                                    "first_serve_in_rate_delta", snapshot_dir))
    return claims


def write_claims(claims: List[Dict[str, Any]], out_path: Path = CLAIMS_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for c in claims:
            f.write(json.dumps(c) + "\n")
    return out_path


def main() -> int:
    chart_raw = pd.read_parquet(_CHART_PATH)
    claims = build_pressure_point_claims(chart_raw)
    out_path = write_claims(claims)
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} ranked={len(c['ranking'])}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
