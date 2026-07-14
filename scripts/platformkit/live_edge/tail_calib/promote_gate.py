"""scripts.platformkit.live_edge.tail_calib.promote_gate -- TAIL-PROMOTE: the
honest promotion gate for B4-APEX's 159 TAIL_CALIB_BEATS_BASELINE entities
(commit 60206997). Fable's judgment on those 159: point-delta paired-CRPS
wins with NO multiplicity correction and NO second corpus -- candidate CLASS,
not promoted. This module runs the actual gate:

  1. Per-entity PAIRED test on per-game CRPS differentials (baseline minus
     tail-aware). Reserve rows are already one-row-per-player-game (box
     score grain), so the diff array IS the per-game series -- no further
     clustering needed within an entity.
  2. BH correction across ALL 412 tested entities (not just the 159) -- the
     tails.nba.points player claims apex.expand_tails_testability actually
     scored (verdict != INSUFFICIENT_DATA / NOT_TESTABLE_HERE).
  3. 2-corpora agreement: the reserve (2025-26) split into two disjoint
     trailing-date halves on one global median-date cutoff. A survivor is
     BH-significant in the POOLED test AND same-direction (sign of mean
     diff) in both halves, each with >= MIN_HALF_ROWS games.
  4. CLASS-level test: one pooled paired test across all tested entities'
     per-game differentials, CLUSTERED BY ENTITY (each entity's own mean
     diff is the unit fed to the test) -- this is valid even if almost no
     individual entity survives step 2/3.

Imports apex.py / calib.py / tails.py read-only (never edits). Report-only:
does NOT write the claims journal -- Fable ledgers any promotion decision.

INVARIANTS: pandas/numpy/scipy stdlib only. <=300 LOC. ASCII stdout.
edge_claimed=False, calibration language only, no $/ROI.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd
from scipy import stats as sps

from scripts.platformkit.live_edge.replay import apex as ax
from scripts.platformkit.live_edge.tail_calib import calib as tc
from scripts.platformkit.live_edge import tails as tl

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "tail_calib" / "promote"
BH_ALPHA = 0.05
MIN_HALF_ROWS = 5  # ponytail: half apex's MIN_ENTITY_RESERVE_ROWS(10) -- honest floor for a split corpus
TESTED_VERDICTS = ("TAIL_CALIB_BEATS_BASELINE", "NULL", "TAIL_CALIB_WORSE")


def split_reserve_halves(reserve: pd.DataFrame, date_col: str = "date") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two disjoint trailing-date halves on ONE global median-date cutoff
    (not per-entity) -- a fixed forward/backward time split, not a
    leak-prone per-entity resample."""
    ordered = reserve.sort_values(date_col)
    cutoff = ordered[date_col].median()
    return ordered[ordered[date_col] <= cutoff], ordered[ordered[date_col] > cutoff]


def entity_diffs(entity_id, fit_metrics: dict, reserve: pd.DataFrame,
                  entity_col: str = "player_id", stat_col: str = "pts") -> np.ndarray:
    """Per-game CRPS differential (baseline - tail_aware; positive = tail-
    aware wins) for one entity on one reserve slice. Reuses tail_calib.
    calib's exact fit/CRPS plumbing (same instrument apex used)."""
    m = fit_metrics.get(entity_id)
    if m is None or m.get("insufficient"):
        return np.array([])
    rows = reserve[reserve[entity_col] == entity_id]
    if not len(rows):
        return np.array([])
    actual = rows[stat_col].to_numpy(dtype=float)
    mean, std, quantiles = m["mean"], m["std"], m["quantiles"]
    crps_base = np.array([tc.crps_approx(lambda q: tc.baseline_ppf(q, mean, std), x) for x in actual])
    crps_tail = np.array([tc.crps_approx(lambda q: tc.tail_aware_ppf(q, quantiles), x) for x in actual])
    return crps_base - crps_tail


def paired_test(diffs: np.ndarray) -> dict:
    """One-sample t-test of the diff series against 0 -- this IS the paired
    test (baseline CRPS vs tail-aware CRPS on the same game)."""
    n = int(len(diffs))
    if n < 2 or diffs.std(ddof=1) == 0.0:
        return {"n": n, "mean": float(diffs.mean()) if n else float("nan"), "p_value": float("nan")}
    _, p = sps.ttest_1samp(diffs, popmean=0.0)
    return {"n": n, "mean": float(diffs.mean()), "p_value": float(p)}


def bh_correct(p_values: pd.Series, alpha: float = BH_ALPHA) -> pd.Series:
    """Benjamini-Hochberg q-values (5-line rank-based BH -- statsmodels isn't
    an existing dependency here, not worth adding for this)."""
    p = p_values.to_numpy(dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    q_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    q = np.empty(n)
    q[order] = np.clip(q_sorted, 0, 1)
    return pd.Series(q, index=p_values.index)


def load_tested_entities(claims_df: pd.DataFrame, disc: pd.DataFrame, reserve: pd.DataFrame) -> pd.DataFrame:
    """Re-derives the exact 412 tails.nba.points player claims apex actually
    tested (verdict != INSUFFICIENT_DATA/NOT_TESTABLE_HERE), by re-running
    apex's OWN classification (read-only reuse, never re-derived logic) and
    recovering each claim's entity_id via apex._entity_id."""
    expansion = ax.expand_tails_testability(claims_df, disc, reserve)
    tested = expansion[expansion["verdict"].isin(TESTED_VERDICTS)].copy()
    tails_df = ax.tails_claims(claims_df)
    # entity_id is only well-formed (int player_id) for tails.nba.points
    # PLAYER rows -- apex's own expand_tails_testability guards this the
    # same way before calling _entity_id; team rows carry string ids (e.g.
    # "ATL") and never reach TESTED_VERDICTS, so this guard is a no-op for
    # the tested set, just avoiding _entity_id's int() crash on the rest.
    id_map = {}
    for _, r in tails_df.iterrows():
        scope = json.loads(r["scope_json"])
        if r["topic"] == "tails.nba.points" and scope.get("entity_type") == "player":
            id_map[r["claim_id"]] = ax._entity_id(r["scope_json"])
    tested["entity_id"] = tested["claim_id"].map(id_map)
    return tested


def run_gate(claims_df: pd.DataFrame, disc: pd.DataFrame, reserve: pd.DataFrame,
             entity_col: str = "player_id", stat_col: str = "pts") -> pd.DataFrame:
    """The full per-entity gate table: pooled paired test + BH-q + 2-halves
    direction check + survivor flag, for every apex-tested entity."""
    fit_metrics = tc.fit_predictors(disc, entity_col, stat_col)
    tested = load_tested_entities(claims_df, disc, reserve)
    half_a, half_b = split_reserve_halves(reserve)

    rows = []
    for _, r in tested.iterrows():
        eid = r["entity_id"]
        pooled = paired_test(entity_diffs(eid, fit_metrics, reserve, entity_col, stat_col))
        a_res = paired_test(entity_diffs(eid, fit_metrics, half_a, entity_col, stat_col))
        b_res = paired_test(entity_diffs(eid, fit_metrics, half_b, entity_col, stat_col))
        rows.append({
            "claim_id": r["claim_id"], "entity_id": eid, "apex_verdict": r["verdict"],
            "n_pooled": pooled["n"], "mean_pooled": pooled["mean"], "p_pooled": pooled["p_value"],
            "n_half_a": a_res["n"], "mean_half_a": a_res["mean"],
            "n_half_b": b_res["n"], "mean_half_b": b_res["mean"],
        })
    table = pd.DataFrame(rows)
    table["bh_q"] = bh_correct(table["p_pooled"].fillna(1.0))
    dir_pooled = np.sign(table["mean_pooled"])
    dir_a, dir_b = np.sign(table["mean_half_a"]), np.sign(table["mean_half_b"])
    halves_sufficient = (table["n_half_a"] >= MIN_HALF_ROWS) & (table["n_half_b"] >= MIN_HALF_ROWS)
    same_direction = (dir_pooled == dir_a) & (dir_pooled == dir_b) & (dir_pooled != 0)
    table["survivor"] = halves_sufficient & same_direction & (table["bh_q"] < BH_ALPHA)
    return table


def class_level_test(table: pd.DataFrame) -> dict:
    """CLASS-level pooled test across ALL tested entities, CLUSTERED BY
    ENTITY: each entity's own mean per-game diff (mean_pooled) is the unit
    fed to a one-sample t-test -- avoids the pseudo-replication a raw
    pooled-row test would have from entities with very different game
    counts. The class can be real even with zero individual BH survivors."""
    means = table["mean_pooled"].dropna().to_numpy()
    n = len(means)
    if n < 2:
        return {"n_entities": n, "mean": float("nan"), "p_value": float("nan"),
                "ci_lo": float("nan"), "ci_hi": float("nan")}
    m = float(means.mean())
    se = float(means.std(ddof=1) / np.sqrt(n))
    _, p = sps.ttest_1samp(means, popmean=0.0)
    t_crit = float(sps.t.ppf(0.975, df=n - 1))
    return {"n_entities": n, "mean": m, "p_value": float(p),
            "ci_lo": m - t_crit * se, "ci_hi": m + t_crit * se}


def _write_report(table: pd.DataFrame, class_result: dict, base_dir=None) -> pathlib.Path:
    out_dir = OUT_DIR if base_dir is None else pathlib.Path(base_dir) / "promote"
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_dir / "promote_table.parquet", index=False)
    survivors = table[table["survivor"]]
    L = ["# TAIL-PROMOTE report -- honest promotion gate on B4-APEX's 159 "
         "TAIL_CALIB_BEATS_BASELINE entities (calibration language only, edge_claimed=False)\n\n",
         f"Tested entities (BH universe): {len(table)}\n\n",
         "## Individual-entity gate (BH q<0.05 pooled AND same-direction both trailing-date halves)\n\n",
         f"- survivors: {len(survivors)} / {len(table)}\n\n",
         "claim_id | entity_id | apex_verdict | mean_pooled | p_pooled | bh_q | survivor\n---|---|---|---|---|---|---\n"]
    for _, r in survivors.iterrows():
        L.append(f"{r['claim_id']} | {r['entity_id']} | {r['apex_verdict']} | {r['mean_pooled']:+.4f} | "
                  f"{r['p_pooled']:.4g} | {r['bh_q']:.4g} | True\n")
    L.append(f"\n(full 412-row table: {out_dir / 'promote_table.parquet'})\n\n")
    L.append("## CLASS-level pooled test (clustered by entity, n=%d)\n\n" % class_result["n_entities"])
    L.append(f"- mean per-game CRPS delta (baseline-tail_aware): {class_result['mean']:+.4f} "
             f"95%CI [{class_result['ci_lo']:+.4f}, {class_result['ci_hi']:+.4f}]\n")
    L.append(f"- p-value: {class_result['p_value']:.4g}\n\n")
    L.append("## Not verified\n\n"
             "- Half-split is one global median-date cutoff, not per-entity -- entities whose games "
             "cluster on one side of the cutoff get an unbalanced/insufficient half and cannot survive "
             "step 2 regardless of the pooled result (reported via n_half_a/n_half_b, not silently dropped).\n"
             "- CLASS-level test treats each entity's pooled mean as one i.i.d. observation; entities "
             "share the same discovery-fit machinery and reserve season, so this is a documented "
             "simplification, not a fully independent-samples design.\n"
             "- tail_aware_ppf/_cdf clip-beyond-anchors artifact (noted in TAIL_CALIB_REPORT.md) is "
             "unresolved and still affects every per-game CRPS pair computed here.\n")
    path = out_dir / "PROMOTE_REPORT.md"
    path.write_text("".join(L), encoding="ascii")
    return path


def main() -> int:
    claims_df = pd.read_parquet(REPO_ROOT / "data" / "omni" / "claims" / "claims.parquet")
    box = tl.load_nba_player_box()
    disc, reserve = tl.split_nba_discovery_reserve(box)
    table = run_gate(claims_df, disc, reserve)
    class_result = class_level_test(table)
    path = _write_report(table, class_result)
    print(f"[promote_gate] n_tested={len(table)} n_survivors={int(table['survivor'].sum())}")
    print(f"[promote_gate] class n={class_result['n_entities']} mean={class_result['mean']:+.4f} "
          f"p={class_result['p_value']:.4g} ci=[{class_result['ci_lo']:+.4f},{class_result['ci_hi']:+.4f}]")
    print(f"[promote_gate] wrote {path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
