"""scripts.platformkit.live_edge.player_grid.player_mine -- mines per-(player,
situation-cell) scoring claims on the player_grid.py substrate (2024-25
discovery only, see player_grid.py docstring for the lineup-coverage cut).

Topic namespace deliberately does NOT contain the substring "situation"
(uses "player_cell.*" instead) so B4's validate_claims.load_b1_survivors
(which filters claims by topic-contains-"situation") never accidentally
picks these up -- this lane's own player_validate.py is the OOS validator.

Same mining pattern as grid_sweep.py (Welch z-approx vs complement, BH
within batch, add_claims_batch, INSUFFICIENT_DATA floor at MIN_SIDE_N=30)
except the complement is the SAME PLAYER's other on-floor possessions, never
other players' rows (grid_sweep.py is intentionally not imported/edited --
its complement is global, wrong for a "vs that player's baseline" test).
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
from scipy import stats as sps

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni.k_sweep_nba import bh_adjust
from scripts.platformkit.live_edge.player_grid import player_grid as pg

_PREDS_PATH = pathlib.Path("data/omni/live_edge/player_grid/tagged_player_possessions.parquet")
_LANE = "player_mine_v1"

MIN_SIDE_N = 30
BH_ALPHA = 0.05
MIN_PRACTICAL_EFFECT = 0.05  # points per on-floor possession


def welch_vs_player_complement(df: pd.DataFrame, cell_cols: list[str]) -> pd.DataFrame:
    """Per-(player, cell) mean `scored` vs that SAME player's complement."""
    d = df.copy()
    d["_sq"] = d["scored"] ** 2
    tot = d.groupby("player_id").agg(total_n=("scored", "size"), total_s=("scored", "sum"),
                                      total_ss=("_sq", "sum"))
    g = d.groupby(["player_id"] + cell_cols, observed=True).agg(
        n=("scored", "size"), s=("scored", "sum"), ss=("_sq", "sum")).reset_index()
    g = g.merge(tot, on="player_id", how="left")
    g["mean"] = g["s"] / g["n"]
    g["var"] = (g["ss"] - g["n"] * g["mean"] ** 2) / (g["n"] - 1).clip(lower=1)
    comp_n = (g["total_n"] - g["n"]).clip(lower=1)
    comp_s = g["total_s"] - g["s"]
    comp_ss = g["total_ss"] - g["ss"]
    comp_mean = comp_s / comp_n
    comp_var = (comp_ss - comp_n * comp_mean ** 2) / (comp_n - 1).clip(lower=1)
    g["comp_n"], g["comp_mean"] = comp_n, comp_mean
    se = np.sqrt(g["var"] / g["n"] + comp_var / comp_n)
    g["delta"] = g["mean"] - comp_mean
    z = g["delta"] / se.replace(0, np.nan)
    g["p"] = (2 * sps.norm.sf(np.abs(z))).clip(max=1.0)
    g["p"] = g["p"].fillna(1.0)
    g["ci_low"], g["ci_high"] = g["delta"] - 1.96 * se, g["delta"] + 1.96 * se
    return g.drop(columns=["s", "ss", "total_s", "total_ss"])


def claim_for_row(rec: dict, cell_cols: list[str], pass_name: str, in_game_only: bool,
                   data_asof: str, source: str) -> tuple[dict, bool]:
    cell = {c: rec[c] for c in cell_cols}
    player_id = str(rec["player_id"])
    statement = f"NBA player {player_id} scoring delta in {pass_name} cell {cell}"
    scope = {"sport": "nba", "entity_type": "player", "entity_ids": [player_id],
              "context": {"cell": cell, "in_game_only": in_game_only, "pass": pass_name}}
    n, comp_n = int(rec["n"]), int(rec["comp_n"])
    if n < MIN_SIDE_N or comp_n < MIN_SIDE_N:
        effect = {"verdict": "INSUFFICIENT_DATA"}
        evidence = {"n_a": n, "n_b": comp_n, "floor": MIN_SIDE_N}
        escalate, lifecycle = False, "screened"
    else:
        p_adj = rec.get("p_adj", 1.0)
        escalate = bool(p_adj < BH_ALPHA and abs(rec["delta"]) >= MIN_PRACTICAL_EFFECT)
        effect = {"verdict": "TESTED", "delta": float(rec["delta"]), "baseline_rate": float(rec["comp_mean"]),
                  "ci_low": float(rec["ci_low"]), "ci_high": float(rec["ci_high"]),
                  "n_a": n, "n_b": comp_n, "stat": "player_points_per_onfloor_possession"}
        evidence = {"p_value": float(rec["p"]), "p_adj_bh": float(p_adj), "source": source}
        lifecycle = "proposed" if escalate else "screened"
    claim = {
        "statement": statement, "type": "conditional", "scope": scope,
        "topic": f"player_cell.{pass_name}", "lifecycle": lifecycle,
        "effect": effect, "evidence": evidence,
        "provenance": {"created_by_lane": _LANE, "data_asof": data_asof},
        "links": {"escalate_to_funnel": escalate},
    }
    return claim, escalate


def run_mine(base_dir=None, possessions_source=None, box_source=None, scorer_dir=None) -> dict:
    long_df = pg.build_player_frame(slice="discovery", possessions_source=possessions_source,
                                     box_source=box_source, scorer_dir=scorer_dir)
    data_asof = str(long_df["season"].max())

    preds_path = _PREDS_PATH if base_dir is None else pathlib.Path(base_dir) / _PREDS_PATH.name
    preds_path.parent.mkdir(parents=True, exist_ok=True)
    long_df.to_parquet(preds_path, index=False)

    source = str(pg.SCORER_DIR)
    all_recs = []
    for pass_name, cell_cols in pg.PLAYER_CELL_PASSES.items():
        g = welch_vs_player_complement(long_df, cell_cols)
        for rec in g.to_dict("records"):
            all_recs.append({"rec": rec, "cell_cols": cell_cols, "name": pass_name,
                              "in_game_only": pg.IN_GAME_ONLY[pass_name]})

    tested_idx = [i for i, r in enumerate(all_recs)
                  if r["rec"]["n"] >= MIN_SIDE_N and r["rec"]["comp_n"] >= MIN_SIDE_N]
    adj = bh_adjust([all_recs[i]["rec"]["p"] for i in tested_idx])
    for idx, a in zip(tested_idx, adj):
        all_recs[idx]["rec"]["p_adj"] = a

    claims, escalations = [], 0
    for r in all_recs:
        claim, escalate = claim_for_row(r["rec"], r["cell_cols"], r["name"], r["in_game_only"],
                                         data_asof, source)
        claims.append(claim)
        escalations += int(escalate)

    claims.append({
        "statement": "NBA player-grid scoring claims mined on 2024-25 discovery only "
                      "(2023-24 dropped -- no on-floor lineup store); see player_grid.py.",
        "type": "structural", "scope": {"sport": "nba"}, "topic": "player_cell.lineup_coverage_note",
    })

    claims_added, _ids = cl.add_claims_batch(claims, base_dir=base_dir)
    insufficient_n = sum(1 for r in all_recs if r["rec"]["n"] < MIN_SIDE_N or r["rec"]["comp_n"] < MIN_SIDE_N)
    return {
        "cells_screened": len(all_recs),
        "cells_mined": len(all_recs) - insufficient_n,
        "insufficient_data": insufficient_n,
        "bh_survivors": sum(1 for i in tested_idx if all_recs[i]["rec"]["p_adj"] < BH_ALPHA),
        "escalations": escalations,
        "claims_added": claims_added,
        "n_players": int(long_df["player_id"].nunique()),
        "n_onfloor_possessions_discovery": len(long_df),
    }


def main() -> int:
    result = run_mine()
    for k, v in result.items():
        print(f"[player_mine_v1] {k}: {v}")
    report = pathlib.Path("data/omni/live_edge/player_grid/MINE_REPORT.md")
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# player_grid B1-analog mining report (PLAYER grain)\n",
        "cells_screened -> mined -> BH_survivors -> escalations\n",
        f"{result['cells_screened']} -> {result['cells_mined']} -> "
        f"{result['bh_survivors']} -> {result['escalations']}\n\n",
    ]
    for k, v in result.items():
        lines.append(f"- {k}: {v}\n")
    lines.append("\ndiscovery slice: 2024-25 only (2023-24 dropped, no lineup store).\n")
    report.write_text("".join(lines), encoding="ascii")
    print(f"[player_mine_v1] wrote {report}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
