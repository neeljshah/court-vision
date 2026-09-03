"""scripts.platformkit.eval_gate.s115_ingame_models -- S115: MORE MODELS, SAME OFFSET.

Every in-play arm shipped so far is a single logistic term on the tick state.  This screen
asks whether a NON-LINEAR residual model, with logit(market) held EXACT as an offset, learns
anything the line misses:  p = sigmoid(logit(market) + f(state)).  f can only CORRECT the
line; f == 0 reproduces the raw market to machine precision.  Three arms, each fit by ONE
Newton step on the logistic working response (the S108 trick): (a) hgb -- HistGradientBoosting
max_depth 3, strong l2; (b) mlp -- tiny (16,) MLP, early stopping on a TRAIN-internal split;
(c) hgb_mono -- the same HGB with monotonic_cst = margin increasing.

NULL = the S94 global recalibration `[1, logit(market)]` fit on the IDENTICAL train rows.
Design = the S94 design: expanding walk-forward by game-first date, purge by game, 1-day
embargo, 5 outer folds; inner folds pick each arm's grid config.  Input is the S86 archived
per-tick CSV (SCREEN side, 232,951 ticks / 797 games); the verdict side is never read.
A SCREEN is a NON-FINDING: no prereg seal, no ledger charge, no K read, no ledger write.
SINGLE-WINDOW.  Calibration language only (tick-weighted Brier / DM CI).  ASCII only.
Per-file test: python -m pytest tests/platformkit/ingame/test_s115_ingame_models.py -q
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neural_network import MLPRegressor

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.pbo import cscv_pbo
from scripts.platformkit.eval_gate.s108_pregame_full_model import _prep
from scripts.platformkit.eval_gate.s94_nba_early_shrinkage import (
    EMBARGO_DAYS, N_FOLDS, OUT_DIR, S86_CSV, _recal, fold_dates, logit, sigmoid)
from scripts.platformkit.eval_gate.tick_informative import attach_informative_summary
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size

STEM = "s115_ingame_models_2026-09-03"
IMPROVEMENT_BAR = 0.004          # the row's bar; NEVER lowered (Q3)
INNER_FOLDS = 2
LAGS = (3, 5, 10)
COLS = ["game_id", "game_date", "ts", "period", "game_clock_s", "margin", "model", "market", "y"]
FEATURES = ["period", "clock_frac", "margin", "dmargin_3", "dmargin_5", "dmargin_10",
            "logit_market", "logit_model"]
MARGIN_IDX = FEATURES.index("margin")
HGB_FIXED = {"max_depth": 3, "max_iter": 150, "learning_rate": 0.05, "min_samples_leaf": 200,
             "early_stopping": False, "random_state": 20260903}
MLP_FIXED = {"hidden_layer_sizes": (16,), "early_stopping": True, "validation_fraction": 0.15,
             "n_iter_no_change": 3, "max_iter": 60, "batch_size": 4096,
             "learning_rate_init": 0.01, "random_state": 20260903}
GRID = {"hgb": ({"l2_regularization": 10.0}, {"l2_regularization": 100.0}),
        "mlp": ({"alpha": 1e-3}, {"alpha": 1e-1}),
        "hgb_mono": ({"l2_regularization": 10.0}, {"l2_regularization": 100.0})}
ARMS = tuple(GRID)
W_FLOOR_HGB = 1e-3               # as S108 (the HGB arms carry sample_weight = w)
W_FLOOR_MLP = 5e-2               # MLPRegressor has no sample_weight -> bound the leverage


def past_delta(frame: pd.DataFrame, lag: int) -> np.ndarray:
    """margin change vs the tick `lag` rows earlier IN THE SAME GAME (strictly past).

    Leak guard: the borrowed row's `ts` must be strictly less than this row's `ts`;
    a same-tick or later read RAISES, it never degrades silently to a peek.
    """
    grouped = frame.groupby("game", sort=False)
    prev_ts = grouped["ts"].shift(lag).to_numpy(dtype=float)
    prev_margin = grouped["margin"].shift(lag).to_numpy(dtype=float)
    seen = np.isfinite(prev_ts)
    if seen.any() and not bool((prev_ts[seen] < frame["ts"].to_numpy(dtype=float)[seen]).all()):
        raise ValueError("leak guard: lag-%d read a same-tick or later row" % lag)
    return frame["margin"].to_numpy(dtype=float) - np.where(seen, prev_margin, 0.0)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """S94's row order and offsets, plus the tick-state feature block."""
    out = df.copy()
    out["game"] = out["game_id"].astype(str)
    out["date"] = out["game"].map(out.groupby("game")["game_date"].min())
    out = out.sort_values(["date", "game", "ts"], kind="stable").reset_index(drop=True)
    out["logit_market"] = logit(out["market"])
    out["logit_model"] = logit(out["model"])
    out["clock_frac"] = out["game_clock_s"].to_numpy(dtype=float) / 720.0
    for lag in LAGS:
        out["dmargin_%d" % lag] = past_delta(out, lag)
    return out


def load_screen(path: Path = S86_CSV) -> pd.DataFrame:
    return prepare(pd.read_csv(path, usecols=COLS))


def apply_offset(correction, offset) -> np.ndarray:
    """p = sigmoid(logit(market) + f(state)). f == 0 -> the raw market, exactly."""
    return sigmoid(np.asarray(offset, dtype=float) + np.asarray(correction, dtype=float))


def fit_arm(arm: str, cfg: dict, Xtr: np.ndarray, ytr: np.ndarray, offtr: np.ndarray,
            Xte: np.ndarray, offte: np.ndarray) -> np.ndarray:
    """One Newton step on the logistic working response, offset held exact."""
    p0 = sigmoid(offtr)
    floor = W_FLOOR_MLP if arm == "mlp" else W_FLOOR_HGB
    w = np.clip(p0 * (1.0 - p0), floor, None)
    z = (ytr - p0) / w
    if arm == "mlp":
        # ponytail: unweighted MSE on a leverage-bounded working response -- sklearn's
        # MLPRegressor takes no sample_weight; raise W_FLOOR_MLP if the step overshoots.
        model = MLPRegressor(**{**MLP_FIXED, **cfg}).fit(Xtr, z)
        return apply_offset(model.predict(Xte), offte)
    mono = (np.arange(Xtr.shape[1]) == MARGIN_IDX).astype(int) if arm == "hgb_mono" else None
    model = HistGradientBoostingRegressor(monotonic_cst=mono, **{**HGB_FIXED, **cfg})
    model.fit(Xtr, z, sample_weight=w)
    return apply_offset(model.predict(Xte), offte)


def _blocks(frame: pd.DataFrame, n_folds: int, embargo_days: int) -> List[dict]:
    """S94's fold windows: expanding train up to (block start - embargo), test = the block."""
    out: List[dict] = []
    for k, block in enumerate(fold_dates(frame, n_folds)[1:], start=1):
        day0 = min(block)
        cut = str(dt.date.fromisoformat(str(day0)) - dt.timedelta(days=int(embargo_days)))
        train = np.flatnonzero((frame["date"] < cut).to_numpy())
        test = np.flatnonzero(frame["date"].isin(set(block)).to_numpy())
        out.append({"fold": k, "train": train, "test": test, "embargo_cut": cut,
                    "test_start": str(day0), "test_end": str(max(block))})
    return out


def walk_forward(frame: pd.DataFrame, *, n_folds: int = N_FOLDS,
                 embargo_days: int = EMBARGO_DAYS,
                 inner_folds: int = INNER_FOLDS) -> Tuple[pd.DataFrame, np.ndarray, List[dict]]:
    """Per outer fold: every grid config's test predictions, the inner-CV pick, and the null."""
    X = frame[FEATURES]
    y = frame["y"].to_numpy(dtype=float)
    off = frame["logit_market"].to_numpy(dtype=float)
    scored: List[pd.DataFrame] = []
    grid_cols: List[np.ndarray] = []
    folds: List[dict] = []
    for win in _blocks(frame, n_folds, embargo_days):
        train, test = win["train"], win["test"]
        tr_frame, te_frame = frame.iloc[train], frame.iloc[test]
        if not len(train) or not len(test) or tr_frame["y"].nunique() < 2:
            folds.append({"fold": win["fold"], "status": "INSUFFICIENT", "n_train": int(len(train))})
            continue
        assert not (set(tr_frame["game"]) & set(te_frame["game"])), "fold not game-disjoint (purge)"
        assert tr_frame["date"].max() < win["embargo_cut"] <= win["test_start"], "embargo violated"
        Ztr, Zte = _prep(X, train, test)
        inner = _blocks(tr_frame.reset_index(drop=True), inner_folds, embargo_days)
        preds, picks = {}, {}
        for arm, cfgs in GRID.items():
            outer_p = np.column_stack([fit_arm(arm, c, Ztr, y[train], off[train], Zte, off[test])
                                       for c in cfgs])
            score = np.zeros(len(cfgs))
            for iw in inner:
                itr, ite = iw["train"], iw["test"]
                if not len(itr) or not len(ite):
                    continue
                Wtr, Wte = _prep(X.iloc[train], itr, ite)
                ay, ao = y[train], off[train]
                for j, cfg in enumerate(cfgs):
                    p = fit_arm(arm, cfg, Wtr, ay[itr], ao[itr], Wte, ao[ite])
                    score[j] += float(np.mean((p - ay[ite]) ** 2))
            pick = int(np.argmin(score))
            preds[arm] = outer_p[:, pick]
            picks[arm] = {"cfg": cfgs[pick], "inner_brier": [float(s) for s in score]}
            grid_cols.append(outer_p)
        block = te_frame.copy()
        block["fold"] = win["fold"]
        block["p_null"] = _recal(tr_frame).predict_proba(te_frame[["logit_market"]].to_numpy())[:, 1]
        for arm in ARMS:
            block["p_" + arm] = preds[arm]
        scored.append(block)
        folds.append({"fold": win["fold"], "status": "OK", "test_start": win["test_start"],
                      "test_end": win["test_end"], "embargo_cut": win["embargo_cut"],
                      "train_date_max": str(tr_frame["date"].max()),
                      "n_train_ticks": int(len(train)), "n_train_games": int(tr_frame["game"].nunique()),
                      "n_test_ticks": int(len(test)), "n_test_games": int(te_frame["game"].nunique()),
                      "n_inner_folds": len(inner), "picks": picks})
    if not scored:
        return frame.iloc[0:0].copy(), np.zeros((0, 0)), folds
    n_arms = len(ARMS)
    grid = np.vstack([np.hstack(grid_cols[i:i + n_arms]) for i in range(0, len(grid_cols), n_arms)])
    return pd.concat(scored, ignore_index=True), grid, folds


def _dm(diff: np.ndarray, games: pd.Series) -> Dict[str, Any]:
    if games.nunique() < 2:
        return {"stat": None, "p_value": None, "ci95": None, "n_clusters": int(games.nunique())}
    r = diebold_mariano([float(v) for v in diff], games.astype(str).tolist())
    return {"stat": float(r.dm_stat), "p_value": float(r.p_value),
            "ci95": [float(r.ci95[0]), float(r.ci95[1])], "n_clusters": int(r.n_clusters)}


def summarize(scored: pd.DataFrame, grid: np.ndarray, folds: List[dict],
              n_all: int, n_games_all: int) -> Dict[str, Any]:
    y = scored["y"].to_numpy(dtype=float)
    loss = {"market": (scored["market"].to_numpy(dtype=float) - y) ** 2,
            "null": (scored["p_null"].to_numpy(dtype=float) - y) ** 2}
    for arm in ARMS:
        loss[arm] = (scored["p_" + arm].to_numpy(dtype=float) - y) ** 2
    brier = {k: float(v.mean()) for k, v in loss.items()}
    best = min(ARMS, key=lambda a: brier[a])
    arms: Dict[str, Any] = {}
    for arm in ARMS:
        arms[arm] = {"brier": brier[arm],
                     "improvement_vs_market": float((loss["market"] - loss[arm]).mean()),
                     "improvement_vs_null": float((loss["null"] - loss[arm]).mean()),
                     "dm_vs_market": _dm(loss["market"] - loss[arm], scored["game"]),
                     "dm_vs_null": _dm(loss["null"] - loss[arm], scored["game"])}
    head = arms[best]
    ci = head["dm_vs_market"]["ci95"]
    cleared = bool(head["improvement_vs_market"] >= IMPROVEMENT_BAR
                   and ci is not None and ci[0] > 0.0
                   and head["improvement_vs_null"] > 0.0)
    diff = pd.DataFrame({"game": scored["game"], "loss_differential": loss["market"] - loss[best]})
    ess = effective_sample_size(diff, game_column="game", loss_column="loss_differential")
    out: Dict[str, Any] = {
        "spec_id": "scripts.platformkit.eval_gate.s115_ingame_models:nba_ingame_offset_models_v1",
        "sport": "nba", "tier": "SCREEN (uncharged, no prereg seal, no K read, no ledger write)",
        "label": "SINGLE-WINDOW", "edge_claimed": False,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": {"path": str(S86_CSV), "side": "S86 SCREEN only (verdict side never read)",
                   "n_ticks": n_all, "n_games": n_games_all},
        "candidate": "p = sigmoid(logit(market) + f(tick state)); f by one Newton step on the "
                     "logistic working response; the offset is exact (f == 0 -> the raw market)",
        "features": FEATURES,
        "nulls": {"market": "the raw in-play line",
                  "null": "S94 global logistic [1, logit(market)] on the identical train rows"},
        "design": {"folds": len([f for f in folds if f["status"] == "OK"]),
                   "embargo_days": EMBARGO_DAYS, "purge": "by game", "order": "game-first date",
                   "inner_folds": INNER_FOLDS, "fit_on": "TRAIN folds only (arms and the null)",
                   "windows": "identical to s94_nba_early_shrinkage.walk_forward"},
        "improvement_bar": IMPROVEMENT_BAR, "denominator_arms": len(ARMS), "folds": folds,
        "n_scored_ticks": int(len(scored)), "n_scored_games": int(scored["game"].nunique()),
        "brier": brier, "arms": arms, "best_arm": best, "clears_bar": cleared,
        "headline_improvement_vs_market": head["improvement_vs_market"], "headline_ci95": ci,
        "verdict": "CANDIDATE" if cleared else "NULL",
        "icc_by_game": ess["rho"], "design_effect": ess["design_effect"], "n_eff": ess["n_eff"],
        "honest_note": "Calibration (tick-weighted Brier, game-clustered DM CI) only. No dollar, "
                       "ROI, profit or edge claim. A NULL is a PASS of the process.",
    }
    if grid.shape[1] >= 2:
        pbo = cscv_pbo(np.clip(grid, 0.0, 1.0), y)
        out["pbo"] = {"pbo": float(pbo.pbo), "n_configs": int(grid.shape[1])}
    attach_informative_summary(
        out, scored.assign(loss_differential=loss["market"] - loss[best]),
        "loss_differential", game_col="game", ts_col="ts")
    return out


def run(out_dir: Path = OUT_DIR, stem: str = STEM, frame: Optional[pd.DataFrame] = None,
        **kwargs: Any) -> Dict[str, Any]:
    df = load_screen() if frame is None else frame
    scored, grid, folds = walk_forward(df, **kwargs)
    summary = summarize(scored, grid, folds, int(len(df)), int(df["game"].nunique()))
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    series = scored[["game", "game_date", "ts", "fold", "y", "market", "model", "p_null"]].copy()
    for arm in ARMS:
        series["p_" + arm] = scored["p_" + arm].to_numpy(dtype=float)
    yv = series["y"].to_numpy(dtype=float)
    for name in ("market", "null") + ARMS:
        col = "market" if name == "market" else "p_" + name
        series["loss_" + name] = (series[col].to_numpy(dtype=float) - yv) ** 2
    for arm in ARMS:                                             # Q9: the paired-loss series
        series["d_%s_vs_market" % arm] = series["loss_market"] - series["loss_" + arm]
        series["d_%s_vs_null" % arm] = series["loss_null"] - series["loss_" + arm]
    series["cluster_id"] = series["game"]
    csv_path = Path(out_dir) / (stem + ".csv")
    series.to_csv(csv_path, index=False, encoding="ascii")
    summary["per_tick_csv"] = str(csv_path)
    (Path(out_dir) / (stem + ".json")).write_text(
        json.dumps(summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="S115 non-linear in-game arms over the market offset")
    ap.add_argument("--folds", type=int, default=N_FOLDS)
    ap.add_argument("--inner-folds", type=int, default=INNER_FOLDS)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    args.stem = STEM
    s = run(out_dir=args.out_dir, stem=args.stem, n_folds=args.folds, inner_folds=args.inner_folds)
    print("S115 SCREEN n %d ticks / %d games | market %.6f null %.6f"
          % (s["n_scored_ticks"], s["n_scored_games"], s["brier"]["market"], s["brier"]["null"]))
    for arm in ARMS:
        a = s["arms"][arm]
        print("  %-9s brier %.6f | vs market %+.6f ci %s | vs null %+.6f"
              % (arm, a["brier"], a["improvement_vs_market"], a["dm_vs_market"]["ci95"],
                 a["improvement_vs_null"]))
    print("best %s | headline %+.6f | pbo %s | n_eff %.1f | VERDICT %s (bar %+.4f)"
          % (s["best_arm"], s["headline_improvement_vs_market"], s.get("pbo", {}).get("pbo"),
             s["n_eff"], s["verdict"], s["improvement_bar"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
