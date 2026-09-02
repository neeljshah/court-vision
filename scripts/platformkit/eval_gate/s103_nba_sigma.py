"""scripts.platformkit.eval_gate.s103_nba_sigma -- S103: the margin sigma past S98's grid limit.

S98 fit `margin_sigma` per phase cell on a grid [6.0, 24.0] and cut the NBA tick surface's
pooled gap to the raw in-play line roughly in half (-0.004805 -> -0.002378, CI including zero).
That number is a BOUND: 21 of 127 cell-folds pin at the grid MAX 24.0 and 15 at the MIN 6.0, and
the fit drifts across folds (P1|close 11.0 -> 19.5). S103 measures two treatments on the SAME
rows: (a) the same per-cell fit on a WIDE grid [3.0, 60.0] step 0.5, and (b) a PARAMETRIC
sigma = exp(a + b log(rem_s + 30) + c |margin| + d is_p4), FOUR coefficients fit on TRAIN folds
by bounded scipy `minimize` instead of 27 free cell values, so fold drift has fewer degrees of
freedom to hide in. Every arm is repriced through the closed form price_checkpoint evaluates
(`s98.price_vec`, asserted equal to the scalar) at EVERY tick. Expanding walk-forward by game-first
date, purged by game, 1-day embargo, 5 folds, SCREEN side only (verdict side never read). A SCREEN
is a NON-FINDING: no prereg seal, no charge, no K read, no ledger write. SINGLE-WINDOW.
Calibration (tick-weighted Brier) only. ASCII only.
Test: python -m pytest tests/platformkit/ingame/test_s103_nba_sigma.py -q
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate import (s94_nba_early_shrinkage as s94,
                                           s98_nba_better_prior as s98)
from scripts.platformkit.eval_gate.tick_informative import attach_informative_summary
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size

OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "cache" / "eval_gate"
STEM = "s103_nba_sigma_2026-09-03"
IMPROVEMENT_BAR = s94.IMPROVEMENT_BAR   # the row's bar, defined ONCE upstream; NEVER lowered (Q3)
MIN_CELL_TRAIN, N_FOLDS, EMBARGO_DAYS = s94.MIN_CELL_TRAIN, s94.N_FOLDS, s94.EMBARGO_DAYS
SIGMA_GRID_WIDE = np.round(np.arange(3.0, 60.0 + 1e-9, 0.5), 4)   # the row's widened grid
PRIOR = "p0_asof"                       # the S86 incumbent Elo prior; S98 proved no rival on disk
ARMS = ("cell98", "wide", "param", "blend", "recal")
ARM_DOC = {
    "cell98": "price_vec(p0_asof, state, sigma per cell fit on TRAIN, grid [6.0, 24.0] step 0.5)"
              " -- the S98 elo_sig arm, recomputed here on identical rows; wide = the same fit on"
              " the WIDENED grid [3.0, 60.0] step 0.5",
    "param": "sigma = exp(a + b log(rem_s + 30) + c |margin| + d is_p4), 4 coefficients fit on"
             " TRAIN by bounded scipy minimize of the priced prior's Brier",
    "blend": "sigmoid((1-w) logit(market) + w logit(param)), ONE global w on TRAIN (the S94 form);"
             " recal = the S94 global unregularised logistic on [1, logit(market)], the NULL",
}
THETA_NAMES = ("a_intercept", "b_log_rem_s", "c_abs_margin", "d_is_p4")
THETA_BOUNDS = ((-5.0, 8.0), (-2.0, 2.0), (-0.1, 0.1), (-3.0, 3.0))
THETA_STARTS = ((2.9, 0.0, 0.0, 0.0), (0.5, 0.30, 0.0, 0.0), (2.9, 0.0, -0.02, 0.0))
SIGMA_CLIP = (1.0, 200.0)               # a scale in points; never zero, never absurd
REF_STATES = {"P1_tied_start": (2880.0, 0.0, 0.0), "P2_close_rem20m": (1200.0, 4.0, 0.0),
              "P4_close_rem4m": (240.0, 3.0, 1.0), "P4_blowout_rem1m": (60.0, 18.0, 1.0)}

def rem_seconds(elapsed) -> np.ndarray:
    """Seconds left in the current regulation/OT frame -- the same clock `price_vec` prices on."""
    e = np.asarray(elapsed, dtype=float)
    rem_min = np.where(e <= s98.FULL_MINUTES, s98.FULL_MINUTES - e,
                       s98.OT_MINUTES - np.mod(e - s98.FULL_MINUTES, s98.OT_MINUTES))
    return np.maximum(0.0, rem_min) * 60.0

def param_sigma(theta, rem_s, abs_margin, is_p4) -> np.ndarray:
    """The parametric sigma. Row-wise in the CURRENT state only: no lag, lead or aggregate."""
    a, b, c, d = (float(v) for v in theta)
    z = a + b * np.log(np.asarray(rem_s, dtype=float) + 30.0) \
        + c * np.asarray(abs_margin, dtype=float) + d * np.asarray(is_p4, dtype=float)
    return np.clip(np.exp(np.clip(z, -6.0, 6.0)), *SIGMA_CLIP)

def _state(frame: pd.DataFrame) -> Tuple[np.ndarray, ...]:
    """(p0, margin, elapsed, y, rem_s, |margin|, is_p4) -- is_p4 covers P4 AND OT (the endgame)."""
    m, e = frame["margin"].to_numpy(float), frame["elapsed"].to_numpy(float)
    return (frame[PRIOR].to_numpy(float), m, e, frame["y"].to_numpy(float), rem_seconds(e),
            np.abs(m), (frame["period"].to_numpy(float) >= 4).astype(float))

def fit_cell_sigma(train: pd.DataFrame, grid: np.ndarray) -> Dict[str, float]:
    """margin_sigma per cell on TRAIN rows only: the grid point minimising that cell's Brier.
    A cell under MIN_CELL_TRAIN keeps the default 13.5 -- missing evidence is not a fitted value
    (B3). Identical to `s98.fit_sigma` except that the grid is an argument, not a constant."""
    out: Dict[str, float] = {}
    for cell, sub in train.groupby("cell", sort=True):
        if len(sub) < MIN_CELL_TRAIN or sub["y"].nunique() < 2:
            out[cell] = s98.SIGMA_DEFAULT
            continue
        p0, m, e, y = (sub[PRIOR].to_numpy(), sub["margin"].to_numpy(),
                       sub["elapsed"].to_numpy(), sub["y"].to_numpy(dtype=float))
        losses = [float(np.mean((s98.price_vec(p0, m, e, s) - y) ** 2)) for s in grid]
        out[cell] = float(grid[int(np.argmin(losses))])
    return out

def fit_param_sigma(train: pd.DataFrame) -> Dict[str, Any]:
    """The 4 coefficients, fit on TRAIN only by bounded L-BFGS-B from several starts."""
    p0, m, e, y, rs, am, p4 = _state(train)
    def objective(theta) -> float:
        return float(np.mean((s98.price_vec(p0, m, e, param_sigma(theta, rs, am, p4)) - y) ** 2))
    best = min((minimize(objective, np.asarray(t0, dtype=float), method="L-BFGS-B",
                         bounds=THETA_BOUNDS) for t0 in THETA_STARTS), key=lambda r: r.fun)
    theta = [float(v) for v in best.x]
    return {"theta": theta, "train_brier": float(best.fun), "success": bool(best.success),
            "coef": dict(zip(THETA_NAMES, theta)),
            "sigma_at": {k: float(param_sigma(theta, [v[0]], [v[1]], [v[2]])[0])
                         for k, v in REF_STATES.items()}}

def add_arms(frame: pd.DataFrame, cell98: Dict[str, float], wide: Dict[str, float],
             theta) -> pd.DataFrame:
    """Price the ONE prior at three sigma treatments; every arm is the same closed form."""
    out = frame.copy()
    p0, m, e, _, rs, am, p4 = _state(out)
    out["sigma_cell98"] = out["cell"].map(cell98).fillna(s98.SIGMA_DEFAULT).to_numpy(dtype=float)
    out["sigma_wide"] = out["cell"].map(wide).fillna(s98.SIGMA_DEFAULT).to_numpy(dtype=float)
    out["sigma_param"] = param_sigma(theta, rs, am, p4)
    for arm in ("cell98", "wide", "param"):
        out["p_" + arm] = s98.price_vec(p0, m, e, out["sigma_" + arm].to_numpy(dtype=float))
    return out

def assert_param_no_future_read(frame: pd.DataFrame, theta, keep: int = 4) -> Dict[str, Any]:
    """The strictly-before guard for the PARAMETRIC arm: re-pricing each game's first `keep` ticks
    with every LATER tick of that game withheld must reproduce the full-frame price EXACTLY."""
    p0, m, e, _, rs, am, p4 = _state(frame)
    full = s98.price_vec(p0, m, e, param_sigma(theta, rs, am, p4))
    pos = frame.reset_index(drop=True).groupby("game", sort=False).head(keep).index.to_numpy()
    pre = frame.iloc[pos]
    q0, qm, qe, _, qrs, qam, qp4 = _state(pre)
    redone = s98.price_vec(q0, qm, qe, param_sigma(theta, qrs, qam, qp4))
    delta = float(np.max(np.abs(redone - full[pos]))) if len(pos) else 0.0
    assert delta == 0.0, "truncation moved %d parametric prices (%.3g)" % (len(pos), delta)
    return {"n_ticks_repriced": int(len(pos)), "max_abs_delta": delta, "ticks_withheld": keep}

def apply_fold(train: pd.DataFrame, test: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Fit both cell grids, the 4 parametric coefficients, one global blend w and the null."""
    cell98 = s98.fit_sigma(train, PRIOR)                # S98's own grid, via S98's own function
    wide = fit_cell_sigma(train, SIGMA_GRID_WIDE)
    par = fit_param_sigma(train)
    out = add_arms(test, cell98, wide, par["theta"])
    tr = add_arms(train, cell98, wide, par["theta"])
    ytr = tr["y"].to_numpy(dtype=float)
    lm_tr = s94.logit(tr["market"])
    gap = s94.logit(tr["p_param"]) - lm_tr
    w = float(s94.W_GRID[int(np.argmin([float(np.mean((s94.sigmoid(lm_tr + g * gap) - ytr) ** 2))
                                        for g in s94.W_GRID]))])
    lm = s94.logit(out["market"])
    out["p_blend"] = s94.sigmoid(lm + w * (s94.logit(out["p_param"]) - lm))
    recal = s94._recal(tr.assign(logit_market=lm_tr))              # the S94 null, fit on TRAIN
    out["p_recal"] = recal.predict_proba(lm.reshape(-1, 1))[:, 1]
    out["blend_w"] = w
    tb = {a: float(np.mean((tr["p_" + a].to_numpy() - ytr) ** 2))
          for a in ("cell98", "wide", "param")}
    pins = {"n_cells": len(wide), "n_at_s98_max_24": sum(v == 24.0 for v in cell98.values()),
            "n_at_wide_min_3": sum(v == float(SIGMA_GRID_WIDE[0]) for v in wide.values()),
            "n_at_wide_max_60": sum(v == float(SIGMA_GRID_WIDE[-1]) for v in wide.values()),
            "n_above_s98_max_24": sum(v > 24.0 for v in wide.values()),
            "n_below_s98_min_6": sum(v < 6.0 for v in wide.values())}
    return out, {"sigma_cell98": cell98, "sigma_wide": wide, "param": par, "blend_w": w,
                 "train_brier_by_arm": tb, "grid_pins": pins}
def walk_forward(frame: pd.DataFrame) -> Tuple[pd.DataFrame, List[dict]]:
    """Expanding walk-forward by game-first date; train purged by game and embargoed 1 day."""
    scored: List[pd.DataFrame] = []
    folds: List[dict] = []
    for k, block in enumerate(s94.fold_dates(frame, N_FOLDS)[1:], start=1):
        day0 = min(block)
        cut = str(dt.date.fromisoformat(str(day0)) - dt.timedelta(days=int(EMBARGO_DAYS)))
        train, test = frame[frame["date"] < cut], frame[frame["date"].isin(set(block))]
        if train.empty or train["y"].nunique() < 2 or test.empty:
            folds.append({"fold": k, "status": "INSUFFICIENT", "n_train": int(len(train))})
            continue
        assert not (set(train["game"]) & set(test["game"])), "fold not game-disjoint (purge)"
        assert train["date"].max() < cut <= day0, "embargo/ordering violated"
        block_out, rec = apply_fold(train, test)
        scored.append(block_out.assign(fold=k))
        folds.append(dict(fold=k, status="OK", test_start=str(day0), test_end=str(max(block)),
                          embargo_cut=cut, train_date_max=str(train["date"].max()),
                          n_train_ticks=int(len(train)), n_test_ticks=int(len(test)),
                          n_train_games=int(train["game"].nunique()),
                          n_test_games=int(test["game"].nunique()), **rec))
    return (pd.concat(scored, ignore_index=True) if scored else frame.iloc[0:0].copy()), folds

def score_cell(sub: pd.DataFrame) -> Dict[str, Any]:
    """Tick-weighted Brier of every arm vs the RAW market, with game-clustered DM CIs."""
    if sub.empty:
        return {"n": 0}
    y = sub["y"].to_numpy(dtype=float)
    loss = {a: (sub["p_" + a].to_numpy(dtype=float) - y) ** 2 for a in ARMS}
    loss["market"] = (sub["market"].to_numpy(dtype=float) - y) ** 2
    row: Dict[str, Any] = {"n": int(len(sub)), "n_games": int(sub["game"].nunique()),
                           "improvement_vs_market": {}, "dm_ci95": {},
                           "brier": {a: float(v.mean()) for a, v in loss.items()}}
    games = sub["game"].astype(str).tolist()
    for a in ARMS:
        d = loss["market"] - loss[a]                # d > 0 -> the arm lost less than the line
        row["improvement_vs_market"][a] = float(d.mean())
        dm = diebold_mariano([float(v) for v in d], games) if row["n_games"] >= 2 else None
        row["dm_ci95"][a] = [float(dm.ci95[0]), float(dm.ci95[1])] if dm else None
    head = sub.assign(loss_differential=loss["market"] - loss["param"])
    ess = effective_sample_size(head, game_column="game", loss_column="loss_differential")
    row.update(icc_by_game=ess["rho"], design_effect=ess["design_effect"], n_eff=ess["n_eff"])
    attach_informative_summary(row, head, "loss_differential", game_col="game", ts_col="ts",
                               market_col="market", model_col="p_param")
    return row

def clears(row: Dict[str, Any], arm: str) -> bool:
    """Bar (never lowered, Q3): +0.004 vs the RAW market, CI excluding 0, Brier under the null."""
    ci = row["dm_ci95"].get(arm)
    return bool(row["improvement_vs_market"][arm] >= IMPROVEMENT_BAR and ci and ci[0] > 0.0
                and row["brier"][arm] < row["brier"]["recal"])

def load(bridged: bool = True) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """`bridged` reuses S98's loader (identical rows, so the arms are comparable); `bridged=False`
    is the FULL S86 screen -- S103 needs no candidate prior, hence no crosswalk and no date cap."""
    if bridged:
        frame, cover = s98.load_screen()
        cover["frame"] = "S98 bridged screen (identical rows)"
        return frame, cover
    raw = pd.read_csv(s98.S86_CSV, usecols=s98.COLS)
    raw["game"] = raw["game_id"].astype(str)
    raw["date"] = raw["game"].map(raw.groupby("game")["game_date"].min())
    raw["cell"] = raw["period_bucket"] + "|" + raw["margin_bucket"] + "|" + raw["rem_bucket"]
    assert (raw["margin"] == raw["score_home"] - raw["score_away"]).all(), "margin != score diff"
    assert raw[PRIOR].notna().all(), "p0_asof missing on the full screen"
    out = raw.sort_values(["date", "game", "ts"], kind="stable").reset_index(drop=True)
    return out, {"frame": "FULL S86 screen (no crosswalk; S103 uses no candidate prior)",
                 "n_screen_ticks": int(len(out)), "n_screen_games": int(out["game"].nunique()),
                 "date_min": str(out["date"].min()), "date_max": str(out["date"].max()),
                 "n_games_after_2026_04_12": int((out.groupby("game")["date"].min()
                                                  > "2026-04-12").sum())}

def summarize(scored: pd.DataFrame, folds: List[dict], cover: Dict[str, Any],
              repro: dict, guard: dict) -> Dict[str, Any]:
    overall = score_cell(scored)
    best = max(ARMS, key=lambda a: overall["improvement_vs_market"][a]) if overall["n"] else None
    by_cell = {str(c): score_cell(s) for c, s in scored.groupby("cell", sort=True)}
    cells = sorted(c for c, r in by_cell.items() if r.get("n") and any(clears(r, a) for a in ARMS))
    ok = [f for f in folds if f.get("status") == "OK"]
    return {
        "spec_id": "scripts.platformkit.eval_gate.s103_nba_sigma:nba_sigma_wide_parametric_v1",
        "sport": "nba", "tier": "SCREEN (uncharged, no prereg seal, no K read, no ledger write)",
        "label": "SINGLE-WINDOW", "edge_claimed": False,
        "source": {"path": str(s98.S86_CSV), "side": "S86 SCREEN only (verdict side never read)",
                   "prior": PRIOR, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat()},
        "coverage": cover, "arms": ARM_DOC, "price_vec_reproduction": repro, "asof_guard": guard,
        "improvement_bar": IMPROVEMENT_BAR, "cells_clearing_bar": cells,
        "design": {"folds": N_FOLDS, "embargo_days": EMBARGO_DAYS, "purge": "by game",
                   "order": "game-first date", "min_cell_train_ticks": MIN_CELL_TRAIN,
                   "sigma_grid_s98": [6.0, 24.0, 0.5], "sigma_grid_wide": [3.0, 60.0, 0.5],
                   "parametric_form": "exp(a + b*log(rem_s+30) + c*|margin| + d*is_p4)",
                   "parametric_bounds": dict(zip(THETA_NAMES, THETA_BOUNDS)),
                   "fit_on": "TRAIN folds only"},
        "n_scored_ticks": int(len(scored)), "n_scored_games": int(scored["game"].nunique()),
        "overall": overall, "by_cell": by_cell, "folds": folds, "best_arm_overall": best,
        "coefficient_stability": {n: [f["param"]["theta"][i] for f in ok]
                                  for i, n in enumerate(THETA_NAMES)},
        "sigma_at_reference_states": {f["fold"]: f["param"]["sigma_at"] for f in ok},
        "grid_pins_by_fold": {f["fold"]: f["grid_pins"] for f in ok},
        "honest_note": "Calibration (tick-weighted Brier) only; an arm that does not beat the"
        " raw line is an honest BEHIND.",
        "prereg_draft_warranted": bool(cells or (best and clears(overall, best))),
    }

def run(out_dir: Path = OUT_DIR, stem: str = STEM, bridged: bool = True,
        frame: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    cover: Dict[str, Any] = {"frame": "INJECTED"} if frame is not None else {}
    if frame is None:
        frame, cover = load(bridged)
    repro = s98.assert_reproduces_scalar(frame)
    guard = {"prior": s98.assert_no_future_read(frame, PRIOR)}
    scored, folds = walk_forward(frame)
    theta0 = next((f["param"]["theta"] for f in folds if f.get("status") == "OK"), (2.9, 0, 0, 0))
    guard["parametric"] = assert_param_no_future_read(frame, theta0)
    summary = summarize(scored, folds, cover, repro, guard)
    series = scored[["game", "game_date", "ts", "fold", "cell", "period", "y", "market", PRIOR,
                     "sigma_cell98", "sigma_wide", "sigma_param", "blend_w"]
                    + ["p_" + a for a in ARMS]].copy()
    y = series["y"].to_numpy(dtype=float)             # Q9: both losses + the differential, per arm
    series["loss_market"] = (series["market"].to_numpy(dtype=float) - y) ** 2
    for a in ARMS:
        series["loss_" + a] = (series["p_" + a].to_numpy(dtype=float) - y) ** 2
        series["d_" + a + "_vs_market"] = series["loss_market"] - series["loss_" + a]
    series["cluster_id"] = series["game"]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    series.to_csv(csv_path := Path(out_dir) / (stem + ".csv"), index=False, encoding="ascii")
    summary["per_tick_csv"] = str(csv_path)
    (Path(out_dir) / (stem + ".json")).write_text(json.dumps(
        summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary

def main() -> int:
    for stem, bridged in ((STEM, True), (STEM + "_fullscreen", False)):
        o = (s := run(stem=stem, bridged=bridged))["overall"]
        print("%s n %d games %d inf %d n_eff %.1f market %.6f" % (
            stem, o["n"], o["n_games"], o["tick_informative"]["n_informative"], o["n_eff"],
            o["brier"]["market"]))
        for a in ARMS:
            print("  %-7s brier %.6f impr %+.6f ci %s" % (a, o["brier"][a],
                  o["improvement_vs_market"][a], o["dm_ci95"][a]))
        print("  cells clearing %s | prereg_draft %s (bar %+.4f)" % (
            s["cells_clearing_bar"], s["prereg_draft_warranted"], s["improvement_bar"]))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
