"""scripts.platformkit.eval_gate.s97_nba_sensor_fusion -- S97: the NBA in-play line and the
as-of state price as TWO NOISY SENSORS of one latent win probability.

S86 priced every screen tick with an as-of prior; S94 found no stable fixed shrinkage weight
between the two series. S97 drops the fixed weight and filters, per S86 phase cell `c`:

    state    x_t   = x_{t-1} + w_t,      w_t ~ N(0, q_c)      (random walk on the logit)
    sensor 1 z_m,t = x_t + e_m,t,      e_m,t ~ N(0, r_m,c)    (the in-play line)
    sensor 2 z_p,t = x_t + e_p,t,      e_p,t ~ N(0, r_p,c)    (the as-of state price)

A scalar Kalman filter runs per GAME in tick order and resets at every game boundary, so only past
and current ticks of the same game reach any posterior. The posterior mean is the arm; its variance
gives the 90 pct interval whose COVERAGE is this row's deliverable even when
Brier is null. q / r are fitted on TRAIN folds only by the INNOVATION-VARIANCE method -- see
`fit_noise`. Nulls on identical rows: the S94 global logistic recalibration on [1, logit(market)],
and the S94 shrinkage form with a SINGLE global weight w. Input is the S86 archived per-tick CSV
(SCREEN side, 232,951 ticks / 797 games); the verdict side is never read. A SCREEN is a
NON-FINDING: no prereg seal, no ledger charge, no K read, no ledger write. SINGLE-WINDOW.
Calibration language only. ASCII only.
Test: python -m pytest tests/platformkit/ingame/test_s97_nba_sensor_fusion.py -q
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.s94_nba_early_shrinkage import (
    MIN_CELL_TRAIN, W_GRID, _recal, fold_dates, load_screen, sigmoid)
from scripts.platformkit.eval_gate.scoring import ece
from scripts.platformkit.eval_gate.tick_informative import attach_informative_summary, flag_ticks
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size

OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "cache" / "eval_gate"
STEM = "s97_nba_sensor_fusion_2026-09-03"
IMPROVEMENT_BAR = 0.004                          # the row's bar; NEVER lowered (Q3)
NOMINAL_COVERAGE, COVERAGE_TOL = 0.90, 0.02      # the row's "within 2 points of nominal"
Z90, P0_DIFFUSE, VAR_FLOOR = 1.6448536269514722, 100.0, 1e-4     # 90 pct z; diffuse state prior
N_FOLDS, EMBARGO_DAYS, COVERAGE_MIN_GROUP, COVERAGE_MAX_GROUPS = 5, 1, 400, 50
TARGET = ("P1", "P2", "close_le5", "rem_gt12")   # the S94 cell, reported for continuity
ARMS = ("market", "recal", "blend1", "posterior")


def fit_noise(train: pd.DataFrame) -> Tuple[Dict[str, Tuple[float, float, float]],
                                            Tuple[float, float, float]]:
    """(q_c, r_m,c, r_p,c) per phase cell from TRAIN rows -- INNOVATION-VARIANCE method.

    Local-level moments on the MARKET series' own within-game first differences: gamma0 = q + 2r
    and gamma1 = -r, so r_m = -gamma1 and q = gamma0 + 2*gamma1. r_p is the two-sensor discrepancy
    net of the market's: E[(z_p - z_m)^2] = r_p + r_m under independent sensor noise -- the MEAN
    SQUARE, so an offset prior is charged for its offset and downweighted rather than trusted. No
    outcome is read; a cell below MIN_CELL_TRAIN inherits the pooled estimate.
    """
    t = train.sort_values(["game", "ts"], kind="mergesort")
    key = t["game"].to_numpy()
    d = t["logit_market"].groupby(key, sort=False).diff()
    part = pd.DataFrame({"cell": t["cell"].to_numpy(), "d": d.to_numpy(),
                         "d1": d.groupby(key, sort=False).shift(1).to_numpy(),
                         "gap": (t["logit_model"] - t["logit_market"]).to_numpy()})

    def est(sub: pd.DataFrame) -> Tuple[float, float, float]:
        dd = sub["d"].dropna().to_numpy(dtype=float)
        g0 = float(np.var(dd, ddof=1)) if len(dd) > 1 else 0.0
        pair = sub[["d", "d1"]].dropna()
        g1 = float(np.cov(pair["d"].to_numpy(float), pair["d1"].to_numpy(float))[0, 1]) \
            if len(pair) > 1 else 0.0
        r_m = max(-g1, VAR_FLOOR)
        r_p = max(float(np.mean(sub["gap"].to_numpy(dtype=float) ** 2)) - r_m, VAR_FLOOR)
        return max(g0 + 2.0 * g1, VAR_FLOOR), r_m, r_p

    pooled = est(part)
    return ({str(c): (est(sub) if len(sub) >= MIN_CELL_TRAIN else pooled)
             for c, sub in part.groupby("cell", sort=True)}, pooled)


def kalman(frame: pd.DataFrame, by_cell: Dict[str, Tuple[float, float, float]],
           pooled: Tuple[float, float, float]) -> Tuple[np.ndarray, np.ndarray]:
    """Posterior (mean, variance) of the latent logit at every tick, per game, in tick order.

    RESET at each game boundary and never forward-looking: tick i is updated from state i-1 of the
    SAME game plus its own two observations, so appending later ticks cannot move an earlier one.
    """
    t = frame.sort_values(["game", "ts"], kind="mergesort")
    par = np.array([by_cell.get(c, pooled) for c in t["cell"].to_numpy()], dtype=float)
    zm, zp = t["logit_market"].to_numpy(float), t["logit_model"].to_numpy(float)
    games = t["game"].to_numpy()
    mean, var = np.empty(len(t)), np.empty(len(t))
    x, cov, prev = 0.0, P0_DIFFUSE, None
    for i in range(len(t)):
        if games[i] != prev:
            x, cov, prev = 0.0, P0_DIFFUSE, games[i]
        cov += par[i, 0]
        for z, r in ((zm[i], par[i, 1]), (zp[i], par[i, 2])):
            k = cov / (cov + r)
            x += k * (z - x)
            cov *= 1.0 - k
        mean[i], var[i] = x, cov
    return (pd.Series(mean, index=t.index).reindex(frame.index).to_numpy(),
            pd.Series(var, index=t.index).reindex(frame.index).to_numpy())


def fit_blend_w(train: pd.DataFrame) -> float:
    """Null 2: ONE global weight w minimising the train Brier of the S94 shrinkage form."""
    lm, y = train["logit_market"].to_numpy(float), train["y"].to_numpy(float)
    gap = (train["logit_model"] - train["logit_market"]).to_numpy(float)
    return float(W_GRID[int(np.argmin([float(np.mean((sigmoid(lm + w * gap) - y) ** 2))
                                       for w in W_GRID]))])


def apply_fold(train: pd.DataFrame, test: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Fit q/r and both nulls on TRAIN, then filter TEST and attach every arm's probability."""
    by_cell, pooled = fit_noise(train)
    w = fit_blend_w(train)
    out = test.copy()
    mean, var = kalman(out, by_cell, pooled)
    out["post_mean_logit"], out["post_var_logit"] = mean, var
    out["p_posterior"] = sigmoid(mean)
    half = Z90 * np.sqrt(var)
    out["lo90"], out["hi90"] = sigmoid(mean - half), sigmoid(mean + half)
    out["p_recal"] = _recal(train).predict_proba(out[["logit_market"]].to_numpy())[:, 1]
    out["p_blend1"] = sigmoid(out["logit_market"].to_numpy(float)
                              + w * (out["logit_model"] - out["logit_market"]).to_numpy(float))
    return out, {"w_blend1": w, "pooled_q_rm_rp": list(pooled),
                 "noise_by_cell": {c: list(v) for c, v in by_cell.items()}}


def walk_forward(frame: pd.DataFrame, *, embargo_days: int = EMBARGO_DAYS,
                 n_folds: int = N_FOLDS) -> Tuple[pd.DataFrame, List[dict]]:
    """Expanding walk-forward by game-first date; train purged by game and embargoed 1 day."""
    scored: List[pd.DataFrame] = []
    folds: List[dict] = []
    for k, block in enumerate(fold_dates(frame, n_folds)[1:], start=1):
        day0 = min(block)
        cut = str(dt.date.fromisoformat(str(day0)) - dt.timedelta(days=int(embargo_days)))
        train, test = frame[frame["date"] < cut], frame[frame["date"].isin(set(block))]
        if train.empty or train["y"].nunique() < 2 or test.empty:
            folds.append({"fold": k, "status": "INSUFFICIENT", "n_train": int(len(train))})
            continue
        assert not (set(train["game"]) & set(test["game"])), "fold not game-disjoint (purge)"
        assert train["date"].max() < cut <= day0, "embargo/ordering violated"
        block_out, fit = apply_fold(train, test)
        block_out["fold"] = k
        scored.append(block_out)
        folds.append(dict(fold=k, status="OK", test_start=str(day0), test_end=str(max(block)),
                          embargo_cut=cut, train_date_max=str(train["date"].max()),
                          n_train_ticks=len(train), n_train_games=train["game"].nunique(),
                          n_test_ticks=len(test), n_test_games=test["game"].nunique(), **fit))
    return (pd.concat(scored, ignore_index=True) if scored else frame.iloc[0:0].copy()), folds


def _dm(diff: np.ndarray, games: pd.Series) -> Dict[str, Any]:
    if games.nunique() < 2:
        return {"stat": None, "p_value": None, "ci95": None, "n_clusters": int(games.nunique())}
    r = diebold_mariano([float(v) for v in diff], games.astype(str).tolist())
    return {"stat": float(r.dm_stat), "p_value": float(r.p_value), "n_clusters": int(r.n_clusters),
            "ci95": [float(r.ci95[0]), float(r.ci95[1])]}

def _p(sub: pd.DataFrame, arm: str) -> np.ndarray:
    return sub["market"].to_numpy(float) if arm == "market" else sub["p_" + arm].to_numpy(float)


def score_cell(sub: pd.DataFrame) -> Dict[str, Any]:
    """Tick-weighted Brier / ECE of every arm on one slice, with game-clustered DM CIs."""
    if sub.empty:
        return {"n": 0}
    y = sub["y"].to_numpy(float)
    loss = {a: (_p(sub, a) - y) ** 2 for a in ARMS}
    row: Dict[str, Any] = {
        "n": int(len(sub)), "n_games": int(sub["game"].nunique()),
        "brier": {a: float(v.mean()) for a, v in loss.items()},
        "ece": {a: float(ece(_p(sub, a), y)) for a in ARMS}, "improvement": {}, "dm": {}}
    for a in ("market", "recal", "blend1"):
        d = loss[a] - loss["posterior"]          # d > 0 -> the posterior lost less
        row["improvement"]["posterior_vs_" + a] = float(d.mean())
        row["dm"]["posterior_vs_" + a] = _dm(d, sub["game"])
    ess = effective_sample_size(sub.assign(loss_differential=loss["market"] - loss["posterior"]),
                                game_column="game", loss_column="loss_differential")
    row["icc_by_game"], row["design_effect"], row["n_eff"] = ess["rho"], ess["design_effect"], ess["n_eff"]
    _, inf = flag_ticks(sub.sort_values(["game", "ts"], kind="mergesort"), game_col="game",
                        ts_col="ts", market_col="market", model_col="model")
    row["n_informative"] = int(inf["n_informative"])
    return row


def coverage(sub: pd.DataFrame) -> Dict[str, Any]:
    """Grouped 90 pct interval coverage on one slice.

    A binary outcome can never lie inside a probability interval, so the LITERAL per-tick share is
    0 by construction and carries no information. The measurable claim is grouped: ticks are cut
    into equal-count groups (>= COVERAGE_MIN_GROUP ticks each) by posterior mean, and a group is
    COVERED when its realised outcome frequency lies inside that group's mean [lo90, hi90].
    """
    n_groups = int(min(COVERAGE_MAX_GROUPS, len(sub) // COVERAGE_MIN_GROUP))
    if n_groups < 2:
        return {"n": int(len(sub)), "n_groups": n_groups, "coverage": None,
                "absent_because": "fewer than 2 groups of %d ticks" % COVERAGE_MIN_GROUP}
    order = sub.sort_values("p_posterior", kind="mergesort")
    gid = np.minimum((np.arange(len(order)) * n_groups) // len(order), n_groups - 1)
    stat = [(float(g["y"].mean()), float(g["lo90"].mean()), float(g["hi90"].mean()))
            for g in (order[gid == i] for i in range(n_groups))]
    share = float(np.mean([lo <= f <= hi for f, lo, hi in stat]))
    return {"n": int(len(sub)), "n_groups": n_groups, "group_size": int(len(sub) // n_groups),
            "coverage": share, "nominal": NOMINAL_COVERAGE,
            "deviation": float(share - NOMINAL_COVERAGE),
            "within_tolerance": bool(abs(share - NOMINAL_COVERAGE) <= COVERAGE_TOL),
            "mean_interval_width": float(np.mean([hi - lo for _, lo, hi in stat])),
            "mean_miss": float(np.mean([0.0 if lo <= f <= hi else min(abs(f - lo), abs(f - hi))
                                        for f, lo, hi in stat])),
            "literal_per_tick_share": "0.0 -- degenerate: y in {0,1} is never inside a (0,1) interval"}


def summarize(scored: pd.DataFrame, folds: List[dict], n_all: int, n_games_all: int) -> Dict[str, Any]:
    overall = score_cell(scored)
    tmask = (scored["period_bucket"].isin(TARGET[:2]) & (scored["margin_bucket"] == TARGET[2])
             & (scored["rem_bucket"] == TARGET[3]))
    ci = (overall.get("dm", {}).get("posterior_vs_market", {}) or {}).get("ci95")
    cleared = bool(overall.get("n")
                   and overall["improvement"]["posterior_vs_market"] >= IMPROVEMENT_BAR
                   and ci is not None and ci[0] > 0.0
                   and overall["improvement"]["posterior_vs_recal"] > 0.0
                   and overall["improvement"]["posterior_vs_blend1"] > 0.0)
    out = {
        "spec_id": "scripts.platformkit.eval_gate.s97_nba_sensor_fusion:nba_two_sensor_kalman_v1",
        "sport": "nba", "tier": "SCREEN (uncharged, no prereg seal, no K read, no ledger write)",
        "label": "SINGLE-WINDOW", "edge_claimed": False,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": {"path": "s86_nba_every_tick_2026-09-03.csv", "n_ticks": n_all,
                   "n_games": n_games_all, "side": "S86 SCREEN only (verdict side never read)"},
        "candidate": "scalar Kalman on the logit: random walk q_c, two sensors (market r_m,c, "
                     "as-of state price r_p,c); posterior mean = arm, variance = 90 pct interval",
        "noise_fit_method": "innovation-variance (moments on the local-level model); TRAIN only",
        "nulls": {"recal": "S94 global logistic [1, logit(market)] on the identical train rows",
                  "blend1": "S94 shrinkage form with a SINGLE global weight w"},
        "design": {"folds": N_FOLDS, "embargo_days": EMBARGO_DAYS, "purge": "by game",
                   "order": "game-first date", "filter_reset": "per game (strictly-before guard)",
                   "min_cell_train_ticks": MIN_CELL_TRAIN, "p0": P0_DIFFUSE, "floor": VAR_FLOOR},
        "improvement_bar": IMPROVEMENT_BAR, "gate_slice": "overall (all cells, held-out folds)",
        "n_scored_ticks": int(len(scored)), "n_scored_games": int(scored["game"].nunique()),
        "overall": overall, "target_cell_s94": score_cell(scored[tmask]),
        "by_cell": {str(c): score_cell(sub) for c, sub in scored.groupby("cell", sort=True)},
        "coverage_overall": coverage(scored),
        "coverage_by_phase": {str(p): coverage(sub)
                              for p, sub in scored.groupby("period_bucket", sort=True)},
        "folds": folds, "prereg_draft_warranted": cleared,
        "honest_note": "Calibration (tick-weighted Brier / ECE / interval coverage) only. No "
                       "dollar, ROI or profit claim; the coverage table is the deliverable."}
    y = scored["y"].to_numpy(float)
    series = scored.assign(loss_differential=(scored["market"].to_numpy(float) - y) ** 2
                           - (scored["p_posterior"].to_numpy(float) - y) ** 2)
    return attach_informative_summary(out, series, "loss_differential", game_col="game",
                                      ts_col="ts", market_col="market", model_col="model")


def run(out_dir: Path = OUT_DIR, stem: str = STEM,
        frame: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    df = load_screen() if frame is None else frame
    scored, folds = walk_forward(df)
    summary = summarize(scored, folds, int(len(df)), int(df["game"].nunique()))
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    series = scored[["game", "game_date", "ts", "fold", "cell", "period_bucket", "y", "market",
                     "model", "post_mean_logit", "post_var_logit", "p_posterior", "lo90", "hi90",
                     "p_recal", "p_blend1"]].copy()
    for name, col in (("loss_market", "market"), ("loss_recal", "p_recal"),
                      ("loss_blend1", "p_blend1"), ("loss_posterior", "p_posterior")):
        series[name] = (series[col].to_numpy(float) - series["y"].to_numpy(float)) ** 2
    for a in ("market", "recal", "blend1"):
        series["d_posterior_vs_" + a] = series["loss_" + a] - series["loss_posterior"]
    series["cluster_id"] = series["game"]
    csv_path = Path(out_dir) / (stem + ".csv")
    series.to_csv(csv_path, index=False, encoding="ascii")
    summary["per_tick_csv"] = str(csv_path)                      # Q9: the paired-loss series
    (Path(out_dir) / (stem + ".json")).write_text(
        json.dumps(summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary


def main() -> int:
    s = run()
    for name in ("overall", "target_cell_s94"):
        r = s[name]
        print("%-15s n %6d games %4d inf %6d n_eff %8.1f | %s" % (
            name, r["n"], r["n_games"], r["n_informative"], r["n_eff"],
            " ".join("%s %.6f" % (a, r["brier"][a]) for a in ARMS)))
        for a in ("market", "recal", "blend1"):
            print("    vs %-7s impr %+.6f ci %s" % (a, r["improvement"]["posterior_vs_" + a],
                                                    r["dm"]["posterior_vs_" + a]["ci95"]))
    for phase, c in sorted(list(s["coverage_by_phase"].items()) + [("ALL", s["coverage_overall"])]):
        print("cover90 %-4s n %6d groups %2d cover %s width %.4f" % (
            phase, c["n"], c["n_groups"], c["coverage"], c.get("mean_interval_width", -1.0)))
    print("prereg_draft_warranted %s (bar %+.4f)" % (s["prereg_draft_warranted"], IMPROVEMENT_BAR))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
