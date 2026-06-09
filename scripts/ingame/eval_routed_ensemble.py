"""HONEST walk-forward eval of the ROUTED ensembles (player lines + team score).

This harness substantiates (or refutes) the central routing claim across the
*FULL* game-time grid -- explicitly INCLUDING the early-Q1 and late-Q4 regions
that the canonical ``eval_curve_v2.json`` grid omits (it stops at 06min..42min).
Those edge regions are exactly where the SBS v2 head is documented to LOSE
(pregame-L5 wins before the first measured point; the production snapshot wins at
the buzzer), so a routing claim is only honest if it is tested there too.

WHAT IS SCORED
--------------
1. PLAYER LINES -- ``src.ingame.routed_ensemble`` (held-out-weighted blend of
   {pregame_l5, v2, snapshot}) vs each COMPONENT head, per (stat, game-time):
       snapshot (PRODUCTION bar), pregame_l5, v2 (trained inline WF), routed.
   A (stat,bucket) cell is a routed WIN only if routed <= the best individual
   head there (+eps). The whole-game verdict is whether routed beats PRODUCTION
   pooled across the grid AND ties-or-beats the per-bucket best everywhere.
   We ALSO report the "oracle-route" floor = the per-cell min over the three
   heads: routing can never beat that, and the honest counter-question the task
   poses ("does routing beat simply using SBS-where-it-wins?") is answered by
   comparing routed vs a hard SBS-where-it-wins switch (no blend).

2. TEAM SCORE -- ``src.ingame.score_ensemble.project_score_ensemble`` (ridge
   POINT + sim WIN-PROB/distribution) vs ridge-only / sim-only / production,
   per bucket: final-score MAE (home/away/margin/total) + win-prob Brier/LogLoss.

SAME FOLDS / UNIVERSE / GRID AS eval_curve_v2.json
--------------------------------------------------
We reuse the *identical* record builder, fold machinery, chronological-even
subsample, leak discipline, and the canonical 7-point grid from
``eval_second_by_second`` -- then EXTEND that grid with extra EARLY (<06min) and
LATE (>42min) buckets so the edge regions are measured. The canonical 7 points
are preserved unchanged so each canonical cell is directly comparable to
``eval_curve_v2.json``. The grid extension is applied by temporarily swapping
``eval_second_by_second.GRID_SEC`` / ``GRID_LABELS`` (which ``grid_states``
reads) for the duration of record-building -- additive, reverted in a finally.

HARD HONESTY
------------
  * Routing weights for player lines are FIXED from the prior held-out
    ``eval_curve_v2.json`` -- NOT re-fit on this test set. At an EXTENDED bucket
    with no curve evidence, ``route_weights`` falls back per the router's own
    rules (pregame before the first centre, last-centre winner held flat after
    the last centre) -- so the edge regions test the router's ACTUAL deployed
    behaviour, not a bucket fit here.
  * Walk-forward: the v2 head + the team ridge + the sim priors are fit/observed
    ONLY on games with date < the test fold's earliest date. A test game is
    never trained on. pregame_l5 + the snapshot/production heads are closed-form.
  * Per-EVENT (a state row at a grid second), NOT per-second.
  * GPU: v2 xgb probes cuda w/ cpu fallback (``--device auto``); ridge + sim are
    numpy (CPU).
  * A NULL / NEGATIVE result reported straight is acceptable. If routing does not
    beat SBS-where-it-wins, the verdict says so.

Run (subsample for speed; SAY SO in the report):
    set NBA_OFFLINE=1
    python scripts/ingame/eval_routed_ensemble.py --max-games 220 --folds 3 \
        --n-sims 1500
Outputs:
    .planning/ingame/eval_routed.json
    .planning/ingame/eval_routed.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import numpy as np  # noqa: E402

import scripts.ingame.eval_second_by_second as ESBS  # noqa: E402
from scripts.ingame.eval_second_by_second import (  # noqa: E402
    GamelogStore, load_season_games, build_game_record,
    baseline_player_snapshot, baseline_team_projection, baseline_winprob,
    _parse_iso_date, TEAM_FEATS, _ridge_fit, _ridge_pred,
    PLAYER_STATS,
)
from scripts.ingame.eval_sbs_v2 import (  # noqa: E402
    FEATURES_V2_PACE, _build_v2_row, _assemble_player_frame,
)
from scripts.ingame.eval_possession_sim import TeamPriorStore  # noqa: E402
from src.ingame.state_featurizer import discover_game_ids  # noqa: E402
from src.ingame.continuous_projection import (  # noqa: E402
    train_player_lines_v2, _select_device,
)
from src.ingame import routed_ensemble as RE  # noqa: E402
from src.ingame.score_ensemble import project_score_ensemble  # noqa: E402
from src.sim.rest_of_game_sim import RestOfGameSim  # noqa: E402

PLAN_DIR = os.path.join(ROOT, ".planning", "ingame")
os.makedirs(PLAN_DIR, exist_ok=True)

# --------------------------------------------------------------------------- #
# Grid: canonical 7 (== eval_curve_v2.json) + EARLY (<06min) + LATE (>42min).
# We must measure the edge regions where SBS alone is documented to lose.
# --------------------------------------------------------------------------- #
CANONICAL_GRID_SEC: Tuple[int, ...] = (360, 720, 1080, 1440, 1800, 2160, 2520)
EXTRA_EARLY_SEC: Tuple[int, ...] = (120, 240)            # 02min, 04min (early Q1)
EXTRA_LATE_SEC: Tuple[int, ...] = (2640, 2760)           # 44min, 46min (late Q4)
EXTENDED_GRID_SEC: Tuple[int, ...] = tuple(
    sorted(set(CANONICAL_GRID_SEC) | set(EXTRA_EARLY_SEC) | set(EXTRA_LATE_SEC))
)
EXTENDED_GRID_LABELS: Dict[int, str] = {
    120: "02min(earlyQ1)", 240: "04min(earlyQ1)",
    360: "06min(midQ1)", 720: "12min(endQ1)", 1080: "18min(midQ2)",
    1440: "24min(endQ2/half)", 1800: "30min(midQ3)", 2160: "36min(endQ3)",
    2520: "42min(midQ4)", 2640: "44min(lateQ4)", 2760: "46min(lateQ4)",
}
# Display order for the curve / markdown (ascending game-time).
GRID_ORDER: List[str] = [EXTENDED_GRID_LABELS[s] for s in EXTENDED_GRID_SEC]
LABEL_TO_SEC: Dict[str, int] = {v: k for k, v in EXTENDED_GRID_LABELS.items()}


def _patch_grid():
    """Context-manager-ish helper: swap ESBS grid for the EXTENDED grid.

    grid_states() / build_game_record() read ESBS.GRID_SEC + ESBS.GRID_LABELS.
    We extend them so the same leak-free record builder emits the extra early +
    late buckets too. Returns (old_sec, old_labels) to restore in a finally.
    """
    old_sec, old_labels = ESBS.GRID_SEC, ESBS.GRID_LABELS
    ESBS.GRID_SEC = list(EXTENDED_GRID_SEC)
    ESBS.GRID_LABELS = dict(EXTENDED_GRID_LABELS)
    return old_sec, old_labels


# --------------------------------------------------------------------------- #
# Routing helpers (player lines)
# --------------------------------------------------------------------------- #
def _blend_from_components(stat: str, grid_sec: int,
                           comp: Dict[str, Optional[float]]) -> float:
    """Apply the held-out routing weights to component values at the TRUE sec.

    Exactly what project_player_lines_routed does internally, driven off the true
    grid second + already-computed component values (no flag-gate / projector
    reload). Weight of any missing component is redistributed over present ones.
    """
    w = RE.route_weights(stat, float(grid_sec))
    usable = {h: comp[h] for h in comp if comp.get(h) is not None}
    wsum = sum(w.get(h, 0.0) for h in usable)
    if not usable or wsum <= 0.0:
        return float(comp.get("snapshot") or 0.0)
    return float(sum((w[h] / wsum) * usable[h] for h in usable))


def _hard_switch_value(stat: str, grid_sec: int,
                       comp: Dict[str, Optional[float]]) -> float:
    """The 'SBS-where-it-wins' HARD switch (the task's honest counterfactual).

    Pick the SINGLE head the routing table names as the held-out winner at the
    NEAREST canonical bucket centre (no blend). This is what 'just use SBS where
    it wins, snapshot/L5 elsewhere' literally means -- the thing routing must
    beat to justify the blend. Falls back to snapshot if the chosen head's value
    is missing here.
    """
    centre = min(CANONICAL_GRID_SEC, key=lambda g: abs(g - grid_sec))
    head = RE._winner_at_center(stat, centre)
    v = comp.get(head)
    if v is None:
        v = comp.get("snapshot")
    return float(v if v is not None else 0.0)


# --------------------------------------------------------------------------- #
# Team-score ridge (mirror eval_possession_sim._fit_team_ridge exactly)
# --------------------------------------------------------------------------- #
def _fit_team_ridge(train_recs: List[Dict[str, Any]]
                    ) -> Dict[int, Dict[str, np.ndarray]]:
    """Per-bucket ridge: TEAM_FEATS at grid t -> (home_final, away_final)."""
    by_X = defaultdict(list)
    by_yh = defaultdict(list)
    by_ya = defaultdict(list)
    for r in train_recs:
        for t, gd in r["grids"].items():
            grow = gd["game"]
            by_X[t].append([float(grow.get(k, 0) or 0) for k in TEAM_FEATS])
            by_yh[t].append(r["home_final"])
            by_ya[t].append(r["away_final"])
    out = {}
    for t in by_X:
        X = np.array(by_X[t], dtype=float)
        out[t] = {
            "home": _ridge_fit(X, np.array(by_yh[t], dtype=float)),
            "away": _ridge_fit(X, np.array(by_ya[t], dtype=float)),
        }
    return out


def _brier(p: float, y: int) -> float:
    return float((p - y) ** 2)


def _logloss(p: float, y: int) -> float:
    eps = 1e-12
    p = min(1 - eps, max(eps, p))
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)))


# --------------------------------------------------------------------------- #
# Faithfulness self-check: prove that deriving the ensemble columns from a single
# sim roll (point:=ridge, winprob:=sim) is EXACTLY what project_score_ensemble
# returns -- so the per-state shortcut below is not a quiet re-definition. Run
# ONCE per harness invocation on a synthetic state (no data, deterministic).
# --------------------------------------------------------------------------- #
def _assert_ensemble_equivalence(n_sims: int, seed: int) -> None:
    state = {
        "home_score": 55.0, "away_score": 51.0, "period": 3,
        "elapsed_sec_in_period": 240, "game_remaining_sec": 780.0,
        "pace_poss_per_min": 2.0,
    }
    rh, ra = 110.3, 104.7
    s = RestOfGameSim(n_sims=int(n_sims), seed=int(seed))
    sim_res = s.simulate(state)
    # rebuild a FRESH sim with the same seed so project_score_ensemble's internal
    # roll is identical to the one we just took.
    s2 = RestOfGameSim(n_sims=int(n_sims), seed=int(seed))
    ens = project_score_ensemble(
        state, ridge_point={"home_final": rh, "away_final": ra},
        sim=s2, calibrate_to_point=True)
    assert abs(ens.home_final - rh) < 1e-9 and abs(ens.away_final - ra) < 1e-9, \
        "ensemble point must equal injected ridge point"
    assert abs(ens.home_win_prob - sim_res.home_win_prob) < 1e-9, \
        "ensemble win prob must equal the un-recentred sim win prob"
    print("[routed-eval] ensemble-equivalence self-check OK "
          "(point==ridge, winprob==sim)")


# --------------------------------------------------------------------------- #
# Main eval
# --------------------------------------------------------------------------- #
def run(max_games: int, folds: int, min_train: int, num_boost_round: int,
        device: str, n_sims: int, seed: int, use_priors: bool) -> Dict[str, Any]:
    _assert_ensemble_equivalence(n_sims, seed)
    season_games = load_season_games()
    store = GamelogStore()
    all_ids = [g for g in discover_game_ids() if g in season_games]
    all_ids = [g for g in all_ids
               if _parse_iso_date(season_games[g].get("game_date") or "")]
    all_ids.sort(key=lambda g: season_games[g]["game_date"])

    n_total = len(all_ids)
    if max_games and n_total > max_games:
        idx = np.linspace(0, n_total - 1, max_games).astype(int)
        sampled = [all_ids[i] for i in sorted(set(idx.tolist()))]
    else:
        sampled = all_ids
    print(f"[routed-eval] {n_total} dated games; using {len(sampled)} "
          f"(chronological-even subsample={max_games})")

    # Build records on the EXTENDED grid (revert ESBS grid afterwards).
    old_sec, old_labels = _patch_grid()
    records: List[Dict[str, Any]] = []
    n_fail = 0
    try:
        for i, gid in enumerate(sampled):
            try:
                rec = build_game_record(gid, season_games[gid], store)
            except Exception:
                rec = None
                n_fail += 1
            if rec is not None:
                records.append(rec)
            if (i + 1) % 50 == 0:
                print(f"  ...{i+1}/{len(sampled)} ({len(records)} usable)")
    finally:
        ESBS.GRID_SEC, ESBS.GRID_LABELS = old_sec, old_labels
    records.sort(key=lambda r: r["game_date"])
    print(f"[routed-eval] {len(records)} usable ({n_fail} failed)")
    if len(records) < min_train + 10:
        raise SystemExit(f"too few usable games ({len(records)})")

    dates = [r["game_date"] for r in records]
    uniq = sorted(set(dates))
    chunks = np.array_split(np.array(uniq, dtype=object), folds + 1)
    fold_test_dates = [set(chunks[k].tolist()) for k in range(1, folds + 1)]

    # player accumulators: pacc[bucket][method][stat] -> [abs errors]
    pacc = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    # team accumulators: tacc[bucket][method][metric] -> [values]
    tacc = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    fold_summaries = []
    dev = device if device != "auto" else _select_device("cuda")
    print(f"[routed-eval] xgb device = {dev}; sim n_sims={n_sims}")

    for fold_i, test_dates in enumerate(fold_test_dates):
        train_recs = [r for r in records if r["game_date"] < min(test_dates)]
        test_recs = [r for r in records if r["game_date"] in test_dates]
        if len(train_recs) < min_train or not test_recs:
            continue
        print(f"[fold {fold_i}] train={len(train_recs)} test={len(test_recs)}")

        # --- WF-fit the deployable v2 head on train-only rows ---
        df_tr = _assemble_player_frame(train_recs)
        proj_v2, _ = train_player_lines_v2(
            df_tr, features=FEATURES_V2_PACE, walk_forward=False,
            num_boost_round=num_boost_round, device=dev, save=False,
        )
        # --- WF-fit team ridge + observe sim priors on train-only ---
        ridge_w = _fit_team_ridge(train_recs)
        priors = TeamPriorStore()
        for r in train_recs:
            priors.observe(r)
        sim = RestOfGameSim(n_sims=int(n_sims), seed=int(seed))

        for r in test_recs:
            _score_player_lines(r, proj_v2, pacc)
            _score_team_lines(r, sim, ridge_w,
                              priors if use_priors else None, tacc)

        fold_summaries.append({
            "fold": fold_i, "n_train": len(train_recs), "n_test": len(test_recs),
            "test_date_min": str(min(test_dates)),
            "test_date_max": str(max(test_dates)),
        })

    return _summarize(pacc, tacc, fold_summaries, len(records), n_total, dev,
                      num_boost_round, n_sims, use_priors)


def _score_player_lines(r, proj_v2, pacc) -> None:
    store_r = r["store"]
    for t, gd in r["grids"].items():
        grow = gd["game"]
        bucket = EXTENDED_GRID_LABELS.get(t)
        if bucket is None:
            continue
        for (_team, _ln), prow in gd["players"].items():
            pid = prow.get("player_id")
            if pid is None or pid not in r["player_finals"]:
                continue
            lab = r["player_finals"][pid]
            if lab.get("min", 0) <= 0:
                continue
            pf = float(prow.get("pf", 0) or 0)
            snap = baseline_player_snapshot(prow, grow, pf)
            l5 = store_r.l5_prior(pid, r["game_date"])
            v2row = _build_v2_row(prow, grow, l5)
            v2_out = proj_v2.project(v2row)
            for s in PLAYER_STATS:
                truth = lab[s]
                cur = float(prow.get(s, 0) or 0)
                snap_v = float(snap[s])
                l5_v = float(l5[s]) if (l5 and s in l5) else None
                v2_v = float(v2_out[s])
                comp = {"snapshot": snap_v, "v2": v2_v}
                if l5_v is not None:
                    comp["pregame_l5"] = max(cur, l5_v)
                routed = max(cur, _blend_from_components(s, t, comp))
                hard = max(cur, _hard_switch_value(s, t, comp))

                pacc[bucket]["snapshot"][s].append(abs(snap_v - truth))
                if l5_v is not None:
                    pacc[bucket]["pregame_l5"][s].append(
                        abs(max(cur, l5_v) - truth))
                pacc[bucket]["v2"][s].append(abs(v2_v - truth))
                pacc[bucket]["routed"][s].append(abs(routed - truth))
                pacc[bucket]["sbs_switch"][s].append(abs(hard - truth))


def _score_team_lines(r, sim, ridge_w, priors, tacc) -> None:
    home_final = r["home_final"]
    away_final = r["away_final"]
    y = r["home_win"]
    for t, gd in r["grids"].items():
        grow = gd["game"]
        bucket = EXTENDED_GRID_LABELS.get(t)
        if bucket is None:
            continue
        # production snapshot (pace extrapolation) -- the deployed bar
        ph, pa = baseline_team_projection(grow)
        # learned ridge point
        rw = ridge_w.get(t)
        if rw is not None:
            feats = np.array([[float(grow.get(k, 0) or 0) for k in TEAM_FEATS]])
            rh = float(_ridge_pred(rw["home"], feats)[0])
            ra = float(_ridge_pred(rw["away"], feats)[0])
        else:
            rh, ra = ph, pa
        # Pass the FULL game_row (grow) to the sim -- identical to
        # eval_possession_sim, which reads the four-factors-so-far / pace fields
        # off the state row -- so sim-only here matches that harness's universe.
        pr = priors.priors_for(r) if priors else None
        # ONE sim roll powers BOTH the sim-only column and the ensemble (the
        # ensemble re-rolling would only burn time AND inject sampling noise that
        # makes ensemble-winprob != sim-winprob; deriving it from the same roll is
        # both faster and EXACTLY faithful to project_score_ensemble's contract:
        #   point := injected ridge ; win-prob := the un-recentred sim's win prob.
        # (That equivalence is unit-tested in tests/test_score_ensemble.py.)
        sim_res = sim.simulate(grow, priors=pr)
        sh = float(sim_res.home_final_mean)
        sa = float(sim_res.away_final_mean)
        swp = float(sim_res.home_win_prob)
        # ENSEMBLE := ridge POINT + sim WIN-PROB (== what project_score_ensemble
        # returns for this state with this ridge point + this sim roll).
        eh, ea = rh, ra
        ewp = swp

        for method, (mh, ma) in (
            ("production", (ph, pa)),
            ("ridge", (rh, ra)),
            ("sim", (sh, sa)),
            ("ensemble", (eh, ea)),
        ):
            tacc[bucket][method]["home_mae"].append(abs(mh - home_final))
            tacc[bucket][method]["away_mae"].append(abs(ma - away_final))
            tacc[bucket][method]["margin_mae"].append(
                abs((mh - ma) - (home_final - away_final)))
            tacc[bucket][method]["total_mae"].append(
                abs((mh + ma) - (home_final + away_final)))
        # win prob: production logistic, sim, ensemble(==sim by design), ridge proxy
        b_wp = baseline_winprob(grow)
        r_wp = 1.0 / (1.0 + np.exp(-0.20 * (rh - ra)))
        for method, p in (("production", b_wp), ("ridge", r_wp),
                          ("sim", swp), ("ensemble", ewp)):
            tacc[bucket][method]["brier"].append(_brier(p, y))
            tacc[bucket][method]["logloss"].append(_logloss(p, y))


def _mean(xs):
    return float(np.mean(xs)) if xs else None


def _wavg(pairs):
    num = sum(n * v for n, v in pairs)
    den = sum(n for n, _ in pairs)
    return (num / den) if den else None


def _summarize(pacc, tacc, fold_summaries, n_records, n_total, dev, nbr,
               n_sims, use_priors) -> Dict[str, Any]:
    # ---------- PLAYER curve ----------
    pmethods = ("snapshot", "pregame_l5", "v2", "routed", "sbs_switch")
    indiv = ("snapshot", "pregame_l5", "v2")
    player_curve = {}
    for bucket in GRID_ORDER:
        if bucket not in pacc:
            continue
        per_stat = {}
        for s in PLAYER_STATS:
            per_stat[s] = {
                "n": len(pacc[bucket]["snapshot"][s]),
                **{m: _mean(pacc[bucket][m][s]) for m in pmethods},
            }
        player_curve[bucket] = per_stat

    pooled = {m: [] for m in pmethods}
    oracle_pool = []
    routed_ge_best = routed_cells = 0
    routed_le_switch = switch_cells = 0
    for bucket, per_stat in player_curve.items():
        for s in PLAYER_STATS:
            d = per_stat[s]
            n = d["n"]
            for m in pmethods:
                if d[m] is not None:
                    pooled[m].append((n, d[m]))
            inds = {m: d[m] for m in indiv if d[m] is not None}
            if inds:
                oracle_pool.append((n, min(inds.values())))
            if d["routed"] is not None and inds:
                routed_cells += 1
                if d["routed"] <= min(inds.values()) + 1e-9:
                    routed_ge_best += 1
            if d["routed"] is not None and d["sbs_switch"] is not None:
                switch_cells += 1
                if d["routed"] <= d["sbs_switch"] + 1e-9:
                    routed_le_switch += 1

    player_pooled_mae = {m: _wavg(pooled[m]) for m in pmethods}
    player_pooled_mae["oracle_route"] = _wavg(oracle_pool)

    # ---------- TEAM curve ----------
    tmethods = ("production", "ridge", "sim", "ensemble")
    team_metrics = ("home_mae", "away_mae", "margin_mae", "total_mae",
                    "brier", "logloss")
    team_curve = {}
    for bucket in GRID_ORDER:
        if bucket not in tacc:
            continue
        per = {}
        for m in tmethods:
            per[m] = {"n": len(tacc[bucket][m]["home_mae"])}
            for metric in team_metrics:
                per[m][metric] = _mean(tacc[bucket][m][metric])
        team_curve[bucket] = per

    team_pooled = {m: {metric: [] for metric in team_metrics} for m in tmethods}
    for bucket, per in team_curve.items():
        for m in tmethods:
            n = per[m]["n"]
            for metric in team_metrics:
                if per[m][metric] is not None:
                    team_pooled[m][metric].append((n, per[m][metric]))
    team_pooled_mae = {m: {metric: _wavg(team_pooled[m][metric])
                           for metric in team_metrics} for m in tmethods}

    # ---------- verdicts ----------
    def _beats(a, b):
        return (a is not None and b is not None and a < b)

    player_verdict = {
        "pooled_mae": player_pooled_mae,
        "routed_beats_production_pooled":
            _beats(player_pooled_mae["routed"], player_pooled_mae["snapshot"]),
        "routed_beats_sbs_switch_pooled":
            _beats(player_pooled_mae["routed"], player_pooled_mae["sbs_switch"]),
        "routed_le_best_indiv_cells": f"{routed_ge_best}/{routed_cells}",
        "routed_le_sbs_switch_cells": f"{routed_le_switch}/{switch_cells}",
        "routed_minus_oracle_pooled":
            (None if player_pooled_mae["routed"] is None
             or player_pooled_mae["oracle_route"] is None
             else player_pooled_mae["routed"] - player_pooled_mae["oracle_route"]),
    }
    team_verdict = {
        "pooled": team_pooled_mae,
        "ensemble_beats_production_total_mae":
            _beats(team_pooled_mae["ensemble"]["total_mae"],
                   team_pooled_mae["production"]["total_mae"]),
        "ensemble_beats_production_margin_mae":
            _beats(team_pooled_mae["ensemble"]["margin_mae"],
                   team_pooled_mae["production"]["margin_mae"]),
        "ensemble_beats_production_brier":
            _beats(team_pooled_mae["ensemble"]["brier"],
                   team_pooled_mae["production"]["brier"]),
        "ensemble_point_eq_ridge":
            "by construction (ensemble point == injected ridge point)",
        "ensemble_winprob_eq_sim":
            "by construction (win prob taken from the un-recentred sim)",
    }

    return {
        "meta": {
            "n_total_dated_pbp_games": n_total,
            "n_usable_records": n_records,
            "folds": fold_summaries,
            "canonical_grid_sec": list(CANONICAL_GRID_SEC),
            "extended_grid_sec": list(EXTENDED_GRID_SEC),
            "extra_early_sec": list(EXTRA_EARLY_SEC),
            "extra_late_sec": list(EXTRA_LATE_SEC),
            "grid_labels": EXTENDED_GRID_LABELS,
            "device": dev,
            "num_boost_round": nbr,
            "n_sims": n_sims,
            "use_priors": use_priors,
            "routing_table": RE.ROUTING_TABLE,
            "routing_source": str(RE.EVAL_CURVE_V2),
            "design": (
                "PLAYER: routed = held-out-weighted blend of {pregame_l5, v2, "
                "snapshot}, weights FIXED from eval_curve_v2.json (NOT fit on "
                "this test set), smooth linear handoff across canonical bucket "
                "centres; at EXTRA early/late buckets the router uses its own "
                "fallback (pregame before first centre / last-centre winner "
                "after last centre). sbs_switch = HARD pick of the table's "
                "winner at the nearest canonical centre (no blend) = the "
                "'just use SBS where it wins' counterfactual. oracle_route = "
                "per-cell min over the 3 heads (un-achievable floor). "
                "TEAM: ensemble = ridge POINT + sim win-prob/distribution "
                "(score_ensemble.project_score_ensemble) vs ridge/sim/"
                "production."),
            "honesty": (
                "held-out walk-forward; v2 + team-ridge + sim-priors fit on "
                "dates < test; routing weights NOT re-fit on test; per-event; "
                "grid EXTENDED with early-Q1 + late-Q4 buckets to test the "
                "edge regions where SBS alone loses."),
        },
        "player_curve": player_curve,
        "team_curve": team_curve,
        "player_verdict": player_verdict,
        "team_verdict": team_verdict,
    }


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def _f(x, nd=3):
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) else "n/a"


def write_markdown(summary: Dict[str, Any], path: str) -> None:
    m = summary["meta"]
    pv = summary["player_verdict"]
    tv = summary["team_verdict"]
    L = ["# Routed Ensembles - Honest Walk-Forward Eval (FULL grid incl edges)\n"]
    L.append(f"- usable records: **{m['n_usable_records']}** of "
             f"{m['n_total_dated_pbp_games']} dated; device **{m['device']}**; "
             f"xgb rounds {m['num_boost_round']}; sim n_sims {m['n_sims']}")
    L.append(f"- canonical grid (== eval_curve_v2): `{m['canonical_grid_sec']}`")
    L.append(f"- EXTENDED with early `{m['extra_early_sec']}` + late "
             f"`{m['extra_late_sec']}` (the regions SBS alone loses)")
    L.append(f"- routing source (held-out, NOT re-fit here): "
             f"`{m['routing_source']}`")
    L.append("- " + m["honesty"] + "\n")

    # ---- PLAYER verdict ----
    pm = pv["pooled_mae"]
    L.append("## PLAYER LINES\n")
    L.append("**Pooled MAE (whole-game, weighted by n):** "
             + ", ".join(f"{k}={_f(pm[k],4)}" for k in
                         ("snapshot", "pregame_l5", "v2", "routed",
                          "sbs_switch", "oracle_route")))
    L.append(f"- routed beats PRODUCTION (snapshot) pooled: "
             f"**{pv['routed_beats_production_pooled']}**")
    L.append(f"- routed beats SBS-where-it-wins HARD switch pooled: "
             f"**{pv['routed_beats_sbs_switch_pooled']}** "
             f"(routed-oracle gap = {_f(pv['routed_minus_oracle_pooled'],4)})")
    L.append(f"- routed <= best individual head at "
             f"**{pv['routed_le_best_indiv_cells']}** (stat,bucket) cells")
    L.append(f"- routed <= SBS-switch at "
             f"**{pv['routed_le_sbs_switch_cells']}** (stat,bucket) cells\n")
    for b in GRID_ORDER:
        if b not in summary["player_curve"]:
            continue
        L.append(f"### {b}\n")
        L.append("| stat | n | snap | L5 | v2 | routed | sbs_sw | best-indiv "
                 "| routed<=best |")
        L.append("|---|--:|--:|--:|--:|--:|--:|--:|:--:|")
        for s in PLAYER_STATS:
            d = summary["player_curve"][b][s]
            inds = {k: d[k] for k in ("snapshot", "pregame_l5", "v2")
                    if d[k] is not None}
            best = min(inds.values()) if inds else None
            ok = (d["routed"] is not None and best is not None
                  and d["routed"] <= best + 1e-9)
            L.append(f"| {s} | {d['n']} | {_f(d['snapshot'])} | "
                     f"{_f(d['pregame_l5'])} | {_f(d['v2'])} | {_f(d['routed'])} "
                     f"| {_f(d['sbs_switch'])} | {_f(best)} | "
                     f"{'Y' if ok else '.'} |")
        L.append("")

    # ---- TEAM verdict ----
    L.append("## TEAM SCORE\n")
    tp = tv["pooled"]
    L.append("**Pooled (whole-game):**")
    L.append("| method | total_mae | margin_mae | home_mae | away_mae "
             "| brier | logloss |")
    L.append("|---|--:|--:|--:|--:|--:|--:|")
    for mth in ("production", "ridge", "sim", "ensemble"):
        d = tp[mth]
        L.append(f"| {mth} | {_f(d['total_mae'])} | {_f(d['margin_mae'])} | "
                 f"{_f(d['home_mae'])} | {_f(d['away_mae'])} | "
                 f"{_f(d['brier'],4)} | {_f(d['logloss'],4)} |")
    L.append("")
    L.append(f"- ensemble beats production total_mae: "
             f"**{tv['ensemble_beats_production_total_mae']}**")
    L.append(f"- ensemble beats production margin_mae: "
             f"**{tv['ensemble_beats_production_margin_mae']}**")
    L.append(f"- ensemble beats production Brier: "
             f"**{tv['ensemble_beats_production_brier']}**")
    L.append(f"- {tv['ensemble_point_eq_ridge']}")
    L.append(f"- {tv['ensemble_winprob_eq_sim']}\n")
    for b in GRID_ORDER:
        if b not in summary["team_curve"]:
            continue
        L.append(f"### {b}\n")
        L.append("| method | n | total_mae | margin_mae | brier | logloss |")
        L.append("|---|--:|--:|--:|--:|--:|")
        for mth in ("production", "ridge", "sim", "ensemble"):
            d = summary["team_curve"][b][mth]
            L.append(f"| {mth} | {d['n']} | {_f(d['total_mae'])} | "
                     f"{_f(d['margin_mae'])} | {_f(d['brier'],4)} | "
                     f"{_f(d['logloss'],4)} |")
        L.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=220)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--min-train", type=int, default=40)
    ap.add_argument("--rounds", type=int, default=300)
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--n-sims", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-priors", action="store_true",
                    help="disable sim team-form priors (sim uses only state).")
    args = ap.parse_args()
    summary = run(args.max_games, args.folds, args.min_train, args.rounds,
                  args.device, args.n_sims, args.seed, not args.no_priors)
    jp = os.path.join(PLAN_DIR, "eval_routed.json")
    mp = os.path.join(PLAN_DIR, "eval_routed.md")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    write_markdown(summary, mp)
    print(f"\n[routed-eval] wrote {jp}\n[routed-eval] wrote {mp}")
    print(json.dumps({"player_verdict": summary["player_verdict"],
                      "team_verdict": summary["team_verdict"]},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
