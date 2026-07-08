"""domains.tennis.pressure_claims -- DESCRIPTIVE 'clutch serving' claims, no
prereg gate. charting_points ONLY (slam_points.parquet has no player-identity
column, verified in prereg_point_mechanisms.py -- not proxied).

Per player (>=200 break points faced, floor declared): break-point-save rate
vs that player's own baseline serve-win rate, delta, n, year range. Snapshot
parquet is written UNFILTERED (all players regardless of floor) so
validate_store's min_sample step recomputes n_excluded_below_floor identically.

edge_claimed hard-wired False. NETWORK: zero.
CLI: python -m domains.tennis.pressure_claims
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

from domains.tennis.prereg_point_mechanisms import (
    REPO_ROOT, _CHART_PATH, _charting_match_ids, _id_frame, charting_point_state,
)

CLAIMS_PATH = REPO_ROOT / "data/cache/intel_claims/tennis_pressure_claims.jsonl"
CLAIMS_SNAPSHOT_PATH = REPO_ROOT / "data/cache/intel_claims/tennis_pressure_claims__snapshot.parquet"
MIN_BP_FACED_CLAIM = 200


def build_pressure_claims(chart_raw: pd.DataFrame, out_path: Path = CLAIMS_PATH,
                          snapshot_path: Path = CLAIMS_SNAPSHOT_PATH) -> List[Dict[str, Any]]:
    state = charting_point_state(chart_raw)
    ids = _charting_match_ids(chart_raw["match_id"])
    state = state.merge(_id_frame(ids).rename(columns={"p1_id": "p1_name", "p2_id": "p2_name"}),
                        on="match_id", how="left")
    state["player_name"] = np.where(state["server"] == 1, state["p1_name"], state["p2_name"])

    base = state.groupby("player_name").agg(
        baseline=("server_won", "mean"),
        yr_min=("date", lambda s: int(pd.to_datetime(s).dt.year.min())),
        yr_max=("date", lambda s: int(pd.to_datetime(s).dt.year.max())))
    bp = state[state["break_point"]].groupby("player_name")["server_won"].agg(["mean", "size"])
    bp = bp.rename(columns={"mean": "bp_save_rate", "size": "n_bp_faced"})
    joined = base.join(bp, how="inner").reset_index()
    joined["delta"] = joined["bp_save_rate"] - joined["baseline"]
    joined["abs_delta"] = joined["delta"].abs()

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(joined, preserve_index=False), snapshot_path)

    qualifying = joined[joined["n_bp_faced"] >= MIN_BP_FACED_CLAIM]
    n_excluded = len(joined) - len(qualifying)
    top = qualifying.sort_values("abs_delta", ascending=False).head(50)
    ranking = [{"rank": i + 1, "player_name": r["player_name"], "value": round(float(r["abs_delta"]), 4),
                "delta": round(float(r["delta"]), 4), "n": int(r["n_bp_faced"]),
                "years": f"{r['yr_min']}-{r['yr_max']}"} for i, (_, r) in enumerate(top.iterrows())]
    claim = {
        "claim_id": "tennis_pressure_claims__bp_save_delta__career_to_date", "kind": "ranking",
        "question": "Which players' break-point-save rate deviates most from their own baseline serve-win rate?",
        "criteria": {
            "metric": "abs_delta", "formula": "abs_delta", "window": "career_to_date",
            "min_sample": {"n_bp_faced": MIN_BP_FACED_CLAIM}, "direction": "desc",
            "value_precision": 4, "entity_key": "player_name",
        },
        "ranking": ranking,
        "source_files": [str(snapshot_path.relative_to(REPO_ROOT)).replace("\\", "/")],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": len(joined), "n_excluded_below_floor": int(n_excluded),
        "edge_claimed": False,
        "caveats": [
            "charting_points only -- slam_points.parquet has no player-identity column",
            "DESCRIPTIVE ranking only -- no forecasting/market/$ edge claimed.",
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(claim) + "\n", encoding="utf-8")
    return [claim]


def main() -> int:
    chart_raw = pd.read_parquet(_CHART_PATH)
    claims = build_pressure_claims(chart_raw)
    c = claims[0]
    print(f"tennis_pressure_claims: n_considered={c['n_considered']} "
          f"n_excluded_below_floor={c['n_excluded_below_floor']} ranked={len(c['ranking'])}")
    print(f"wrote -> {CLAIMS_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
