"""scripts.platformkit.live_edge.tail_calib.mlb_replicate -- TAIL-MLB: the
independent-corpus replication of TAIL-PROMOTE (49e1d184, tier-2 PROVISIONAL,
NBA player-points width correction). Runs the EXACT promote_gate methodology
(paired per-game CRPS diff, BH across all tested entities, both-halves-same-
direction, class-level pooled test clustered by entity) on MLB team-runs.

STEP-0 PREMISE CHECK (2026-07-14, this lane): tails.py already has
load_mlb_team_runs + split_mlb_discovery_reserve (team-grain only -- MLB
player-grain batting-line store is DATA-ABSENT, tails.py's own note, unchanged
today). data/domains/mlb/espn_boxscores.parquet has 3,925 games (3,919 with
non-null runs), 2025-03-27..2026-07-12. Split by tails.MLB_RESERVE_YEAR(2026):
discovery=2025 (2,476 games), reserve=2026 (1,443 games). This replication is
therefore TEAM-grain, not the NBA claim's player-grain -- still a genuine
independent-corpus test of the WIDTH-correction MECHANISM CLASS (does an
empirical-quantile predictive distribution beat Normal on OOS CRPS), just at a
different entity grain, on a different sport, different data pipeline.

No MLB tails.* claim_id join: apex.expand_tails_testability only wires
tails.nba.points player rows to the calibration instrument; MLB team tails
claims exist in the ledger but were never joined to a per-team entity_id in
apex (a separate, out-of-scope gap). This lane tests the mechanism directly on
every MLB team with sufficient discovery+reserve rows, which is the class-
level question this replication actually needs to answer.

Imports tails.py / tail_calib.calib / tail_calib.promote_gate read-only
(reuses paired_test, bh_correct, split_reserve_halves, entity_diffs,
class_level_test, MIN_HALF_ROWS, BH_ALPHA verbatim -- zero reimplementation of
the gate math). Report-only: never writes the claims journal or
data/registry/. edge_claimed=False, calibration language only.

INVARIANTS: pandas/numpy stdlib only. <=300 LOC. ASCII stdout.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge import tails as tl
from scripts.platformkit.live_edge.tail_calib import calib as tc
from scripts.platformkit.live_edge.tail_calib import promote_gate as pg

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "tail_calib" / "mlb"
ENTITY_COL, STAT_COL = "team", "runs"
MIN_RESERVE_ROWS = 10  # same floor as apex.MIN_ENTITY_RESERVE_ROWS


def load_mlb_corpus(source=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reuses tails.py's MLB team-runs reshape + year-based discovery/reserve
    split verbatim (no reimplementation)."""
    df = tl.load_mlb_team_runs(source)
    return tl.split_mlb_discovery_reserve(df)


def run_replication(disc: pd.DataFrame, reserve: pd.DataFrame) -> pd.DataFrame:
    """Per-team gate table -- structurally identical to promote_gate.run_gate
    (same paired_test/bh_correct/entity_diffs/half-split calls), just without
    a claims_df/claim_id join: iterates every team with sufficient discovery
    fit data directly."""
    fit_metrics = tc.fit_predictors(disc, ENTITY_COL, STAT_COL)
    half_a, half_b = pg.split_reserve_halves(reserve)
    teams = sorted(t for t, m in fit_metrics.items() if not m.get("insufficient"))

    rows = []
    for team in teams:
        pooled_diff = pg.entity_diffs(team, fit_metrics, reserve, ENTITY_COL, STAT_COL)
        if len(pooled_diff) < MIN_RESERVE_ROWS:
            continue
        a_diff = pg.entity_diffs(team, fit_metrics, half_a, ENTITY_COL, STAT_COL)
        b_diff = pg.entity_diffs(team, fit_metrics, half_b, ENTITY_COL, STAT_COL)
        pooled = pg.paired_test(pooled_diff)
        a_res = pg.paired_test(a_diff)
        b_res = pg.paired_test(b_diff)
        rows.append({
            "team": team, "n_pooled": pooled["n"], "mean_pooled": pooled["mean"],
            "p_pooled": pooled["p_value"],
            "n_half_a": a_res["n"], "mean_half_a": a_res["mean"],
            "n_half_b": b_res["n"], "mean_half_b": b_res["mean"],
        })
    table = pd.DataFrame(rows)
    if not len(table):
        return table
    table["bh_q"] = pg.bh_correct(table["p_pooled"].fillna(1.0))
    dir_pooled = np.sign(table["mean_pooled"])
    dir_a, dir_b = np.sign(table["mean_half_a"]), np.sign(table["mean_half_b"])
    halves_sufficient = (table["n_half_a"] >= pg.MIN_HALF_ROWS) & (table["n_half_b"] >= pg.MIN_HALF_ROWS)
    same_direction = (dir_pooled == dir_a) & (dir_pooled == dir_b) & (dir_pooled != 0)
    table["survivor"] = halves_sufficient & same_direction & (table["bh_q"] < pg.BH_ALPHA)
    return table


def _write_report(table: pd.DataFrame, class_result: dict, base_dir=None) -> pathlib.Path:
    out_dir = OUT_DIR if base_dir is None else pathlib.Path(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if len(table):
        table.to_parquet(out_dir / "mlb_replicate_table.parquet", index=False)
    survivors = table[table["survivor"]] if len(table) else table
    L = ["# MLB_REPLICATION_REPORT -- TAIL-MLB independent-corpus replication "
         "of TAIL-PROMOTE (calibration language only, edge_claimed=False)\n\n",
         "Grain: MLB TEAM runs-per-game (player-grain DATA-ABSENT on this corpus, "
         "see tails.py header). Discovery=2025 season, reserve=2026 season, "
         "reserve split into two trailing-date halves on one global median cutoff.\n\n",
         f"Tested entities (teams with >= {MIN_RESERVE_ROWS} reserve rows): {len(table)}\n\n",
         "## Individual-team gate (BH q<0.05 pooled AND same-direction both halves)\n\n",
         f"- survivors: {int(survivors['survivor'].sum()) if len(survivors) else 0} / {len(table)}\n\n",
         "team | n_pooled | mean_pooled | p_pooled | bh_q | survivor\n---|---|---|---|---|---\n"]
    for _, r in (survivors[survivors["survivor"]] if len(table) else pd.DataFrame()).iterrows():
        L.append(f"{r['team']} | {r['n_pooled']} | {r['mean_pooled']:+.4f} | "
                  f"{r['p_pooled']:.4g} | {r['bh_q']:.4g} | True\n")
    if len(table):
        L.append(f"\n(full per-team table: {out_dir / 'mlb_replicate_table.parquet'})\n\n")
    L.append("## CLASS-level pooled test (clustered by team, n=%s)\n\n" % class_result.get("n_entities", 0))
    L.append(f"- mean per-game CRPS delta (baseline-tail_aware): {class_result['mean']:+.4f} "
             f"95%CI [{class_result['ci_lo']:+.4f}, {class_result['ci_hi']:+.4f}]\n"
             if np.isfinite(class_result.get("mean", float("nan"))) else "- insufficient entities for class test\n")
    L.append(f"- p-value: {class_result.get('p_value', float('nan')):.4g}\n\n" if np.isfinite(
        class_result.get("p_value", float("nan"))) else "\n")
    L.append("## Not verified\n\n"
              "- TEAM grain, not player grain -- MLB has no per-player batting-line store on "
              "disk; this is a genuine independent-corpus replication of the mechanism CLASS, "
              "not an entity-for-entity replay of the promoted NBA claim.\n"
              "- No claims-journal join (MLB tails.* claim_ids were never linked to a per-team "
              "entity_id by apex.expand_tails_testability, an existing gap out of this lane's "
              "OWNS scope) -- every team with sufficient data was tested directly.\n"
              "- Same tail_aware_ppf/_cdf flat-extrapolation-beyond-anchors ceiling documented in "
              "TAIL_CALIB_REPORT.md applies here (invisible mass beyond the 0.5%/99.5% quantiles).\n"
              "- Half-split is one global median-date cutoff, not per-team (same simplification "
              "promote_gate.py documents for NBA).\n")
    path = out_dir / "MLB_REPLICATION_REPORT.md"
    path.write_text("".join(L), encoding="ascii")
    return path


def main() -> int:
    disc, reserve = load_mlb_corpus()
    table = run_replication(disc, reserve)
    class_result = pg.class_level_test(table) if len(table) else {
        "n_entities": 0, "mean": float("nan"), "p_value": float("nan"),
        "ci_lo": float("nan"), "ci_hi": float("nan")}
    path = _write_report(table, class_result)
    n_survivors = int(table["survivor"].sum()) if len(table) else 0
    print(f"[mlb_replicate] n_teams_tested={len(table)} n_survivors={n_survivors}")
    print(f"[mlb_replicate] class n={class_result['n_entities']} mean={class_result['mean']:+.4f} "
          f"p={class_result['p_value']:.4g} ci=[{class_result['ci_lo']:+.4f},{class_result['ci_hi']:+.4f}]")
    print(f"[mlb_replicate] wrote {path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
