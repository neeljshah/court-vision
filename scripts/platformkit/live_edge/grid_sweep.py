"""scripts.platformkit.live_edge.grid_sweep -- B1 situation-grid mining (mines
scripts.platformkit.live_edge.situation_grid's tagged possession log).

Mechanical conditional splits at parquet-scan cost (k_sweep pattern: bulk
mining, not bespoke tests). Each grid CELL's `points`-per-possession mean is
tested against its COMPLEMENT (every other possession at the same level) via
a vectorized Welch z-approximation -- exact per-cell scipy.stats.ttest_ind
doesn't vectorize across tens of thousands of cells at this row count; the
normal approximation is standard at these sample sizes (smallest surviving
cell floor is MIN_SIDE_N=30, most cells are far larger) and this module never
claims a small-sample exact p-value.

Five dimension passes (TEAM-level claims; see below for why player-level is
DATA-ABSENT):
  full_grid_league / full_grid_team -- all of situation_grid.GROUP_COLS
      (margin x period x pace x rest x blowout x close-late), in_game_only=True.
  rest_marginal_league / rest_marginal_team -- rest_bucket ALONE (the one
      grid axis that is pregame-knowable), in_game_only=False.
  lineup_unit -- off_lineup_ids alone, league-wide, over the 2024-25/2025-26
      subset where the lineup join lands (situation_grid.attach_lineups).

PLAYER-GRAIN CLAIMS: DATA-ABSENT. sim2_possessions is team-offense grain (no
scorer/player_id column); no on-disk store lets a player's stat be tagged
with a situation cell. This sweep mines TEAM and LINEUP-UNIT conditional
claims only, and ledgers one structural claim recording the gap so the funnel
sees it (upgrade path: a play-by-play store with per-possession scorer
attribution).

Row-level retention (S15.K2): the fully tagged discovery frame is written to
data/omni/live_edge/grid/tagged_possessions.parquet BEFORE any claim is
ledgered.

INVARIANTS: pandas + scipy + stdlib only. <=300 LOC. ASCII stdout. Never
writes data/registry/. No $/edge claims.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
from scipy import stats as sps

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni.k_sweep_nba import bh_adjust
from scripts.platformkit.live_edge import situation_grid as sg

_PREDS_PATH = pathlib.Path("data/omni/live_edge/grid/tagged_possessions.parquet")
_LANE = "grid_sweep_v1"
_STAT = "points"

MIN_SIDE_N = 30
BH_ALPHA = 0.05
MIN_PRACTICAL_EFFECT = 0.05  # points per possession


def _welch_vs_complement(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Vectorized Welch (z-approx) of each group's `points` mean vs its
    complement (every row NOT in that group), across ALL groups at once."""
    d = df.copy()
    d["_sq"] = d[_STAT] ** 2
    total_n, total_s, total_ss = len(d), d[_STAT].sum(), d["_sq"].sum()
    g = d.groupby(group_cols, observed=True).agg(
        n=(_STAT, "size"), s=(_STAT, "sum"), ss=("_sq", "sum")).reset_index()
    g["mean"] = g["s"] / g["n"]
    g["var"] = (g["ss"] - g["n"] * g["mean"] ** 2) / (g["n"] - 1).clip(lower=1)
    comp_n = (total_n - g["n"]).clip(lower=1)
    comp_s = total_s - g["s"]
    comp_ss = total_ss - g["ss"]
    comp_mean = comp_s / comp_n
    comp_var = (comp_ss - comp_n * comp_mean ** 2) / (comp_n - 1).clip(lower=1)
    g["comp_n"], g["comp_mean"] = comp_n, comp_mean
    se = np.sqrt(g["var"] / g["n"] + comp_var / comp_n)
    g["delta"] = g["mean"] - comp_mean
    z = g["delta"] / se.replace(0, np.nan)
    g["p"] = (2 * sps.norm.sf(np.abs(z))).clip(max=1.0)
    g["p"] = g["p"].fillna(1.0)
    g["ci_low"], g["ci_high"] = g["delta"] - 1.96 * se, g["delta"] + 1.96 * se
    return g.drop(columns=["s", "ss"])


def _claim_for_row(rec: dict, group_cols: list[str], pass_name: str, entity_type: str,
                    in_game_only: bool, data_asof: str, source: str) -> tuple[dict, bool]:
    cell = {c: rec[c] for c in group_cols if c not in ("off_team", "off_lineup_ids")}
    if entity_type == "team":
        entity_ids = [str(rec["off_team"])]
        label = f"team {rec['off_team']}"
    elif entity_type == "lineup":
        entity_ids = [str(rec["off_lineup_ids"])]
        label = f"lineup {rec['off_lineup_ids']}"
    else:
        entity_ids, label = [], "league-wide"
    statement = f"NBA {label} points-per-possession delta in {pass_name} cell {cell}"
    scope = {"sport": "nba", "entity_type": entity_type, "entity_ids": entity_ids,
              "context": {"cell": cell, "in_game_only": in_game_only, "pass": pass_name}}
    n, comp_n = int(rec["n"]), int(rec["comp_n"])
    if n < MIN_SIDE_N or comp_n < MIN_SIDE_N:
        effect = {"verdict": "INSUFFICIENT_DATA"}
        evidence = {"n_a": n, "n_b": comp_n, "floor": MIN_SIDE_N}
        escalate, lifecycle = False, "screened"
    else:
        p_adj = rec.get("p_adj", 1.0)
        escalate = p_adj < BH_ALPHA and abs(rec["delta"]) >= MIN_PRACTICAL_EFFECT
        effect = {"verdict": "TESTED", "delta": float(rec["delta"]), "ci_low": float(rec["ci_low"]),
                  "ci_high": float(rec["ci_high"]), "n_a": n, "n_b": comp_n, "stat": "points_per_possession"}
        evidence = {"p_value": float(rec["p"]), "p_adj_bh": float(p_adj), "source": source}
        lifecycle = "proposed" if escalate else "screened"
    claim = {
        "statement": statement, "type": "conditional", "scope": scope,
        "topic": f"situation.{pass_name}", "lifecycle": lifecycle,
        "effect": effect, "evidence": evidence,
        "provenance": {"created_by_lane": _LANE, "data_asof": data_asof},
        "links": {"escalate_to_funnel": escalate},
    }
    return claim, escalate


def run_sweep(base_dir=None, possessions_source=None, box_source=None, discovery_only: bool = True) -> dict:
    poss = sg.load_possessions(possessions_source)
    box_df = sg.load_box_rate(box_source)
    if discovery_only:
        poss, _reserve = sg.split_discovery_reserve(poss)
    tagged = sg.tag_situations(poss, box_df, with_lineups=True)
    data_asof = str(tagged["season"].max())

    preds_path = _PREDS_PATH if base_dir is None else pathlib.Path(base_dir) / _PREDS_PATH.name
    preds_path.parent.mkdir(parents=True, exist_ok=True)
    tagged.drop(columns=["off_lineup_ids", "def_lineup_ids"], errors="ignore").to_parquet(preds_path, index=False)

    lineup_rows = tagged[tagged["lineup_available"]]
    passes = [
        ("full_grid_league", sg.GROUP_COLS, "league", True, tagged),
        ("full_grid_team", ["off_team"] + sg.GROUP_COLS, "team", True, tagged),
        ("rest_marginal_league", ["rest_bucket"], "league", False, tagged),
        ("rest_marginal_team", ["off_team", "rest_bucket"], "team", False, tagged),
        ("lineup_unit", ["off_lineup_ids"], "lineup", True, lineup_rows),
    ]

    source = str(sg.POSSESSIONS_PATH)
    all_recs: list[dict] = []
    for name, gcols, entity_type, in_game_only, frame in passes:
        if frame.empty:
            continue
        g = _welch_vs_complement(frame, gcols)
        for rec in g.to_dict("records"):
            all_recs.append({"rec": rec, "gcols": gcols, "name": name,
                              "entity_type": entity_type, "in_game_only": in_game_only})

    tested_idx = [i for i, r in enumerate(all_recs)
                  if r["rec"]["n"] >= MIN_SIDE_N and r["rec"]["comp_n"] >= MIN_SIDE_N]
    adj = bh_adjust([all_recs[i]["rec"]["p"] for i in tested_idx])
    for idx, a in zip(tested_idx, adj):
        all_recs[idx]["rec"]["p_adj"] = a

    claims, escalations = [], 0
    for r in all_recs:
        claim, escalate = _claim_for_row(r["rec"], r["gcols"], r["name"], r["entity_type"],
                                          r["in_game_only"], data_asof, source)
        claims.append(claim)
        escalations += int(escalate)

    lineup_join_rate = float(tagged["lineup_available"].mean())
    claims.append({
        "statement": "NBA situation-grid player-grain claims are DATA-ABSENT: no on-disk store "
                      "carries a per-possession scorer/player_id tag to condition on a situation cell.",
        "type": "structural", "scope": {"sport": "nba"}, "topic": "situation.player_grain_absent",
    })
    claims.append({
        "statement": f"NBA situation-grid lineup-on-floor join rate {lineup_join_rate:.4f} over discovery possessions.",
        "type": "structural", "scope": {"sport": "nba"}, "topic": "situation.lineup_join_rate",
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
        "lineup_join_rate": round(lineup_join_rate, 4),
        "n_possessions_discovery": len(tagged),
    }


def main() -> int:
    result = run_sweep()
    for k, v in result.items():
        print(f"[grid_sweep_v1] {k}: {v}")
    report = pathlib.Path("data/omni/live_edge/grid/SWEEP_REPORT.md")
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# B1 situation-grid sweep report\n",
              "cells_screened -> mined -> BH_survivors -> escalations\n",
              f"{result['cells_screened']} -> {result['cells_mined']} -> "
              f"{result['bh_survivors']} -> {result['escalations']}\n\n"]
    for k, v in result.items():
        lines.append(f"- {k}: {v}\n")
    lines.append("\nfoul_state axis: DATA-ABSENT (see situation_grid.py docstring).\n")
    lines.append("player-grain claims: DATA-ABSENT (see grid_sweep.py docstring + ledgered structural claim).\n")
    report.write_text("".join(lines), encoding="ascii")
    print(f"[grid_sweep_v1] wrote {report}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
