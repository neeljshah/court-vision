"""scripts.platformkit.live_edge.mlb_ingame.mlb_mine -- mines mlb_grid's
tagged GUMBO tick-transitions for MLB in-game conditional claims.

Observables mined (what MLB in-game markets price):
  run_scored_rest_half -- bool: does the BATTING team score >=1 more run
      between this tick and the end of this half-inning (same game_pk,
      inning, half, using each row's own recorded score as the running
      total)? Prices run-line / inning-total / NRFI-YRFI-style markets.
  next_run_scored -- bool: does the batting team's score increase by the
      very next chronological tick in the SAME game (short horizon, any
      inning boundary)? A next-event-outcome proxy (no true next-plate-
      appearance-outcome field exists in the GUMBO tick schema -- ball/
      strike/out/hit are not separately tagged per tick, only the resulting
      state -- so this is the closest observable actually on disk).
  win_prob_delta -- DATA_ABSENT: no fitted win-expectancy series joins to
      GUMBO's game_pk on disk (espn_wp/ is keyed by ESPN event id;
      game_pk_bridge/ only covers 2026-07-03, outside this corpus's
      07-07..07-12 span). Ledgered as a structural claim, not mined.

Mining mechanics: identical Welch-vs-complement (z-approx) + BH-within-batch
pattern as scripts.platformkit.live_edge.grid_sweep (NBA B1), generalized
over a `stat` column. MIN_SIDE_N=30 (same floor, never loosened).

Passes (league pooling per rails; team-grain pooling is DATA-LIMITED here --
see mlb_grid.py docstring -- so pooling runs league -> pitcher instead):
  full_grid_league        -- all 6 axes, run_scored_rest_half.
  full_grid_league_next    -- all 6 axes, next_run_scored.
  base_count_marginal      -- [base_state, count_bucket] only (coarser,
                               bigger n), both stats.
  leverage_marginal        -- [leverage_band] alone, both stats.
  pitcher_marginal         -- [base_state] x pitcher_id, run_scored_rest_half
                               only; pitchers below MIN_PITCHER_N pooled into
                               "other_pitcher" bucket (thin-cell pooling).

Bet shapes these observables map onto: run line / team-total (run_scored_
rest_half), inning totals + NRFI/YRFI (base_count_marginal on early
innings), leverage-band claims -> in-play win-prob-adjacent markets once a
real WE series is joined (future work, not this cycle).

Row-level retention (S15.K2): the tagged discovery frame is written to
data/omni/live_edge/mlb_ingame/tagged_ticks.parquet before any claim is
ledgered.

INVARIANTS: pandas + numpy + scipy + stdlib only. <=300 LOC. ASCII stdout.
Never writes data/registry/. No $/edge claims. scope.context.in_game_only=
true on every mined claim (base-out/count/TTO/leverage are in-game states).
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
from scipy import stats as sps

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni.k_sweep_nba import bh_adjust
from scripts.platformkit.live_edge.mlb_ingame import mlb_grid as mg

_PREDS_PATH = pathlib.Path("data/omni/live_edge/mlb_ingame/tagged_ticks.parquet")
_LANE = "mlb_ingame_mine_v1"

MIN_SIDE_N = 30
MIN_PITCHER_N = 40
BH_ALPHA = 0.05
MIN_PRACTICAL_EFFECT = 0.03  # probability points


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Batting-team score at each tick, then the two observables."""
    out = df.sort_values(["game_pk", "date"], kind="mergesort").reset_index(drop=True)
    bat_score = np.where(out["half"] == "Top", out["score_away"], out["score_home"])
    out["_bat_score"] = bat_score
    half_final = out.groupby(["game_pk", "inning", "half"])["_bat_score"].transform("max")
    out["run_scored_rest_half"] = (half_final > out["_bat_score"]).astype(float)
    next_score = out.groupby("game_pk")["_bat_score"].shift(-1)
    same_game_next = out["game_pk"] == out["game_pk"].shift(-1)
    out["next_run_scored"] = np.where(same_game_next, (next_score > out["_bat_score"]).astype(float), np.nan)
    return out.drop(columns=["_bat_score"])


def _welch_vs_complement(df: pd.DataFrame, group_cols: list[str], stat: str) -> pd.DataFrame:
    d = df.dropna(subset=[stat]).copy()
    d["_sq"] = d[stat] ** 2
    total_n, total_s, total_ss = len(d), d[stat].sum(), d["_sq"].sum()
    g = d.groupby(group_cols, observed=True).agg(
        n=(stat, "size"), s=(stat, "sum"), ss=("_sq", "sum")).reset_index()
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


def _pitcher_bucket(df: pd.DataFrame) -> pd.Series:
    counts = df["pitcher_id"].value_counts()
    keep = set(counts[counts >= MIN_PITCHER_N].index)
    return df["pitcher_id"].where(df["pitcher_id"].isin(keep), "other_pitcher").astype(str)


def _claim_for_row(rec: dict, group_cols: list[str], pass_name: str, stat: str,
                    entity_type: str, data_asof: str, source: str) -> tuple[dict, bool]:
    cell = {c: rec[c] for c in group_cols if c != "pitcher_bucket"}
    entity_ids = [str(rec["pitcher_bucket"])] if entity_type == "pitcher" else []
    label = f"pitcher {rec['pitcher_bucket']}" if entity_type == "pitcher" else "league-wide"
    statement = f"MLB {label} {stat} delta in {pass_name} cell {cell}"
    scope = {"sport": "mlb", "entity_type": entity_type, "entity_ids": entity_ids,
              "context": {"cell": cell, "in_game_only": True, "pass": pass_name, "stat": stat,
                          "leverage_is_heuristic": True}}
    n, comp_n = int(rec["n"]), int(rec["comp_n"])
    if n < MIN_SIDE_N or comp_n < MIN_SIDE_N:
        effect = {"verdict": "INSUFFICIENT_DATA"}
        evidence = {"n_a": n, "n_b": comp_n, "floor": MIN_SIDE_N}
        escalate, lifecycle = False, "screened"
    else:
        p_adj = rec.get("p_adj", 1.0)
        escalate = p_adj < BH_ALPHA and abs(rec["delta"]) >= MIN_PRACTICAL_EFFECT
        effect = {"verdict": "TESTED", "delta": float(rec["delta"]), "ci_low": float(rec["ci_low"]),
                  "ci_high": float(rec["ci_high"]), "n_a": n, "n_b": comp_n, "stat": stat}
        evidence = {"p_value": float(rec["p"]), "p_adj_bh": float(p_adj), "source": source}
        lifecycle = "proposed" if escalate else "screened"
    claim = {
        "statement": statement, "type": "conditional", "scope": scope,
        "topic": f"mlb_ingame.{pass_name}", "lifecycle": lifecycle,
        "effect": effect, "evidence": evidence,
        "provenance": {"created_by_lane": _LANE, "data_asof": data_asof},
        "links": {"escalate_to_funnel": escalate},
    }
    return claim, escalate


def run_sweep(base_dir=None, ticks_source=None, discovery_only: bool = True) -> dict:
    raw = mg.load_ticks(ticks_source)
    deduped = mg.dedupe_transitions(raw)
    with_targets = add_targets(deduped)
    if discovery_only:
        with_targets, _reserve = mg.split_discovery_reserve(with_targets)
    tagged = mg.tag_situations(with_targets)
    tagged["pitcher_bucket"] = _pitcher_bucket(tagged)
    data_asof = str(tagged["date"].max())

    preds_path = _PREDS_PATH if base_dir is None else pathlib.Path(base_dir) / _PREDS_PATH.name
    preds_path.parent.mkdir(parents=True, exist_ok=True)
    tagged.to_parquet(preds_path, index=False)

    passes = [
        ("full_grid_league", mg.GROUP_COLS, "run_scored_rest_half", "league"),
        ("full_grid_league_next", mg.GROUP_COLS, "next_run_scored", "league"),
        ("base_count_marginal", ["base_state", "count_bucket"], "run_scored_rest_half", "league"),
        ("base_count_marginal_next", ["base_state", "count_bucket"], "next_run_scored", "league"),
        ("leverage_marginal", ["leverage_band"], "run_scored_rest_half", "league"),
        ("leverage_marginal_next", ["leverage_band"], "next_run_scored", "league"),
        ("pitcher_marginal", ["pitcher_bucket", "base_state"], "run_scored_rest_half", "pitcher"),
    ]

    source = str(mg.GUMBO_DIR)
    all_recs: list[dict] = []
    for name, gcols, stat, entity_type in passes:
        g = _welch_vs_complement(tagged, gcols, stat)
        for rec in g.to_dict("records"):
            all_recs.append({"rec": rec, "gcols": gcols, "name": name, "stat": stat, "entity_type": entity_type})

    tested_idx = [i for i, r in enumerate(all_recs)
                  if r["rec"]["n"] >= MIN_SIDE_N and r["rec"]["comp_n"] >= MIN_SIDE_N]
    adj = bh_adjust([all_recs[i]["rec"]["p"] for i in tested_idx])
    for idx, a in zip(tested_idx, adj):
        all_recs[idx]["rec"]["p_adj"] = a

    claims, escalations = [], 0
    for r in all_recs:
        rec = r["rec"]
        rec.setdefault("pitcher_bucket", rec.get("pitcher_bucket", ""))
        claim, escalate = _claim_for_row(rec, r["gcols"], r["name"], r["stat"], r["entity_type"],
                                          data_asof, source)
        claims.append(claim)
        escalations += int(escalate)

    claims.append({
        "statement": "MLB in-game win_prob_delta is DATA-ABSENT: no fitted win-expectancy series joins "
                      "to GUMBO game_pk on disk (espn_wp/ keyed by ESPN event id; game_pk_bridge/ covers "
                      "only 2026-07-03, outside this corpus's 07-07..07-12 span).",
        "type": "structural", "scope": {"sport": "mlb"}, "topic": "mlb_ingame.win_prob_delta_absent",
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
        "n_ticks_discovery": len(tagged),
        "n_games": int(tagged["game_pk"].nunique()),
    }


def main() -> int:
    result = run_sweep()
    for k, v in result.items():
        print(f"[mlb_ingame_mine_v1] {k}: {v}")
    report = pathlib.Path("data/omni/live_edge/mlb_ingame/MLB_SWEEP_REPORT.md")
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# MLB in-game grid sweep report\n",
              "cells_screened -> mined -> BH_survivors -> escalations\n",
              f"{result['cells_screened']} -> {result['cells_mined']} -> "
              f"{result['bh_survivors']} -> {result['escalations']}\n\n"]
    for k, v in result.items():
        lines.append(f"- {k}: {v}\n")
    lines.append("\nbet shapes covered: run line / team-total (run_scored_rest_half), "
                 "inning totals + NRFI/YRFI (base_count_marginal, early-inning cells), "
                 "leverage-band claims (in-play win-prob-adjacent, pending a real WE join).\n")
    lines.append("win_prob_delta: DATA-ABSENT (see mlb_mine.py docstring + ledgered structural claim).\n")
    lines.append("team-grain pooling: DATA-LIMITED (game_pk_bridge covers only 2026-07-03); "
                 "pooling ran league->pitcher instead, per rails.\n")
    lines.append("NOT validated here: these are DISCOVERY-slice candidates only; B4/harden validates "
                 "next cycle on the reserve slice.\n")
    report.write_text("".join(lines), encoding="ascii")
    print(f"[mlb_ingame_mine_v1] wrote {report}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
