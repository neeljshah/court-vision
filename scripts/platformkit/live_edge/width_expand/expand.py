"""scripts.platformkit.live_edge.width_expand.expand -- WIDTH-EXPAND: run the
incumbent TAIL-CALIB method (calib.py) + the EXACT promote_gate gate
(BH-across-entities + both-halves-same-direction + class-level pooled test)
over the FULL set of count observables that have data, not just NBA points.

Premise check (2026-07-14, fresh read):
  NBA player-grain (data/domains/basketball_nba/player_boxscores.parquet,
  77,744 rows, season in {2023-24,2024-25,2025-26}): pts/reb/ast/fg3m/stl/
  blk/tov/min ALL non-null 77,744/77,744 -- every one qualifies (>=300 games,
  the per-entity MIN_N=10 floor is enforced inside tails.compute_tail_metrics
  same as the incumbent).
  MLB team-grain (data/domains/mlb/espn_boxscores.parquet, 3,925 games,
  2025-03-27..2026-07-12): home/away_bat_runs (tier-1 incumbent, included as
  POSITIVE CONTROL), home/away_bat_hits, home/away_fld_errors all non-null
  3,919/3,925 -- qualify. No MLB player-grain store exists (tails.py already
  declares this DATA_ABSENT; not re-probed here).

Reuses (imports only, never edits): tails.py for load/split/compute_tail_metrics,
tail_calib.calib for the predictors+CRPS+PIT+coverage+bins, tail_calib.
promote_gate for entity_diffs/paired_test/bh_correct/split_reserve_halves/
class_level_test (all already entity_col/stat_col-parameterized -- the ONLY
adaptation vs the incumbent is the tested-entity universe: promote_gate's
load_tested_entities re-derives claims already sitting in the journal for
NBA points; new observables have no claims yet, so the gate universe here is
every entity with sufficient discovery fit, decided purely by tails.MIN_N,
identical statistical bar).

INVARIANTS: pandas/numpy/scipy + stdlib only, CPU-only (no torch/lightgbm-gpu).
<=300 LOC. ASCII stdout. Never writes data/registry/. No $/edge claims --
calibration language only. edge_claimed=False.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge import tails as tl
from scripts.platformkit.live_edge.tail_calib import calib as tc
from scripts.platformkit.live_edge.tail_calib import promote_gate as pg

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
MLB_TEAM_BOX_PATH = tl.MLB_TEAM_BOX_PATH

# NBA player observables: incumbent points (positive control) + the rest of
# the per-player count stats present in the same box store.
NBA_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
# MLB team observables: incumbent runs (positive control) + hits + errors.
MLB_STATS = [("runs", "home_bat_runs", "away_bat_runs"),
             ("hits", "home_bat_hits", "away_bat_hits"),
             ("errors", "home_fld_errors", "away_fld_errors")]


def load_mlb_team_stat(stat: str, home_col: str, away_col: str, source=None) -> pd.DataFrame:
    """Generalization of tails.load_mlb_team_runs to any home/away paired
    column -- same reshape (one row per team-game), different stat name."""
    df = source.copy() if isinstance(source, pd.DataFrame) else pd.read_parquet(
        source if source is not None else MLB_TEAM_BOX_PATH)
    df = df.dropna(subset=[home_col, away_col])
    home = df.rename(columns={"home_abbr": "team", "away_abbr": "opp", home_col: stat})
    home = home[["event_id", "date", "team", "opp", stat]]
    away = df.rename(columns={"away_abbr": "team", "home_abbr": "opp", away_col: stat})
    away = away[["event_id", "date", "team", "opp", stat]]
    return pd.concat([home, away], ignore_index=True)


def observable_specs() -> list[dict]:
    """Every observable to run: (name, sport, entity_col, stat_col, loader)."""
    specs = []
    for stat in NBA_STATS:
        specs.append({
            "name": f"nba.player.{stat}", "sport": "nba", "entity_col": "player_id",
            "stat_col": stat, "positive_control": stat == "pts",
            "loader": lambda: tl.split_nba_discovery_reserve(tl.load_nba_player_box()),
        })
    for stat, home_col, away_col in MLB_STATS:
        specs.append({
            "name": f"mlb.team.{stat}", "sport": "mlb", "entity_col": "team",
            "stat_col": stat, "positive_control": stat == "runs",
            "loader": lambda h=home_col, a=away_col, s=stat: tl.split_mlb_discovery_reserve(
                load_mlb_team_stat(s, h, a)),
        })
    return specs


def calibration_suite(disc: pd.DataFrame, reserve: pd.DataFrame,
                       entity_col: str, stat_col: str) -> dict:
    """The incumbent's full calibration readout (calib.py, unmodified) for
    one observable: fit metrics + PIT/coverage/CRPS/tail bins on reserve."""
    fit_metrics = tc.fit_predictors(disc, entity_col, stat_col)
    row_eval = tc.evaluate_reserve(reserve, fit_metrics, entity_col, stat_col)
    coverage = tc.coverage_table(reserve, fit_metrics, entity_col, stat_col)
    bins_baseline = tc.tail_bin_check(reserve, fit_metrics, "baseline", entity_col, stat_col)
    bins_tail = tc.tail_bin_check(reserve, fit_metrics, "tail_aware", entity_col, stat_col)
    pit_base = tc.pit_uniformity(row_eval["pit_baseline"].to_numpy()) if len(row_eval) else \
        {"n": 0, "ks_stat": float("nan"), "ks_pvalue": float("nan")}
    pit_tail = tc.pit_uniformity(row_eval["pit_tail"].to_numpy()) if len(row_eval) else \
        {"n": 0, "ks_stat": float("nan"), "ks_pvalue": float("nan")}
    crps_base = float(row_eval["crps_baseline"].mean()) if len(row_eval) else float("nan")
    crps_tail = float(row_eval["crps_tail"].mean()) if len(row_eval) else float("nan")
    return {
        "fit_metrics": fit_metrics, "reserve_rows_scored": int(len(row_eval)),
        "crps_baseline": crps_base, "crps_tail_aware": crps_tail,
        "crps_delta": crps_tail - crps_base, "pit_baseline": pit_base, "pit_tail_aware": pit_tail,
        "coverage": coverage, "bins_baseline": bins_baseline, "bins_tail_aware": bins_tail,
    }


def entity_gate(fit_metrics: dict, reserve: pd.DataFrame, entity_col: str, stat_col: str) -> pd.DataFrame:
    """The EXACT promote_gate per-entity gate (pooled paired test + BH-q +
    2-halves same-direction), universe = every entity with sufficient
    discovery fit (this observable has no pre-existing journal claims to
    re-derive from, unlike NBA points)."""
    entities = [e for e, m in fit_metrics.items() if not m.get("insufficient")]
    half_a, half_b = pg.split_reserve_halves(reserve)
    rows = []
    for e in entities:
        pooled = pg.paired_test(pg.entity_diffs(e, fit_metrics, reserve, entity_col, stat_col))
        a_res = pg.paired_test(pg.entity_diffs(e, fit_metrics, half_a, entity_col, stat_col))
        b_res = pg.paired_test(pg.entity_diffs(e, fit_metrics, half_b, entity_col, stat_col))
        rows.append({
            "entity_id": e, "n_pooled": pooled["n"], "mean_pooled": pooled["mean"],
            "p_pooled": pooled["p_value"], "n_half_a": a_res["n"], "mean_half_a": a_res["mean"],
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


def run_observable(spec: dict) -> dict:
    """One observable end-to-end: calibration suite + gate (class-level +
    per-entity survivors). All-in-turn; caller loops the full list."""
    disc, reserve = spec["loader"]()
    calib = calibration_suite(disc, reserve, spec["entity_col"], spec["stat_col"])
    table = entity_gate(calib["fit_metrics"], reserve, spec["entity_col"], spec["stat_col"])
    class_result = pg.class_level_test(table) if len(table) else {
        "n_entities": 0, "mean": float("nan"), "p_value": float("nan"),
        "ci_lo": float("nan"), "ci_hi": float("nan")}
    n_survivors = int(table["survivor"].sum()) if len(table) else 0
    return {
        "name": spec["name"], "sport": spec["sport"], "positive_control": spec["positive_control"],
        "n_entities_tested": len(table), "n_survivors": n_survivors,
        "class_mean": class_result["mean"], "class_ci_lo": class_result["ci_lo"],
        "class_ci_hi": class_result["ci_hi"], "class_p": class_result["p_value"],
        "calib": calib, "table": table,
    }
