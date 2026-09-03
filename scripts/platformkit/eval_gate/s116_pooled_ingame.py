"""S116 -- a SPORT-BLIND in-game residual model with partial pooling (NBA + MLB).

The in-game arms in this repo are fit per sport. This row asks whether a residual
logistic over NORMALISED state, with `logit(market)` as a fixed OFFSET, transfers
across sports -- and whether PARTIAL POOLING lowers fold drift on the low-n sport:
  logit(p) = logit(market) + a_sport + b . [frac_elapsed, margin_sigma,
             margin_sigma * (1 - frac_elapsed), logit(prior) - logit(market)]
Three fits on identical TRAIN rows: PER-SPORT (own b), POOLED (one b + a sport
intercept), PARTIAL (per-sport b penalised by lambda * ||b - b_pooled||^2, lambda on
an inner TRAIN split). NULL = the S94 recalibration [1, logit(market)], per sport.
Corpora and the STEP 0 census: `s116_corpus`.
THE CALENDAR IS SHARED AND STRICTLY CAUSAL: train for any fold is every cluster of
EITHER sport whose LAST tick precedes the fold's first tick by the embargo. The two
screen corpora are date-disjoint and ordered, so information flows NBA -> MLB only:
at every NBA fold the train set holds no MLB row, the pooled design collapses to the
per-sport one and all three arms coincide BY CONSTRUCTION, so "NBA is not hurt" is a
structural fact here rather than a passed test, and is reported as such. A SCREEN IS
A NON-FINDING: no prereg seal, no ledger read/write, no K. Calibration language only;
no dollar, ROI, profit or edge claim. No bar moved. SINGLE-WINDOW.
Per-file test: python -m pytest tests/platformkit/ingame/test_s116_pooled_ingame.py -q
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.s94_nba_early_shrinkage import fold_dates, logit, sigmoid
from scripts.platformkit.eval_gate.s116_corpus import census, load_mlb, load_nba, prepare
from scripts.platformkit.eval_gate.tick_informative import attach_informative_summary
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size

OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "cache" / "eval_gate"
STEM = "s116_pooled_ingame_2026-09-03"

IMPROVEMENT_BAR = 0.004          # the S58/S82 in-game bar; NEVER lowered (Q3)
N_FOLDS = 5
EMBARGO_DAYS = 1
NBA_SIGMA = 13.5                 # price_checkpoint's own margin sigma (S86/S98)
MIN_TRAIN = 1000                 # the S82 tier's own minimum; below it a fold is NO_TRAIN
RIDGE = 1e-6                     # numerical only, identical on every fit
LAM_GRID = (0.0, 1.0, 10.0, 100.0, 1000.0, 10000.0, 1e12)   # 1e12 == fully pooled
FEATS = ("frac_elapsed", "margin_sigma", "margin_late", "gap")
ARMS = ("line", "null", "persport", "pooled", "partial")


def _scale(frame: pd.DataFrame, sigma: Dict[str, float]) -> pd.DataFrame:
    out = frame.copy()          # margin in sport-sigma units, and its late-game interaction
    out["margin_sigma"] = frame["margin"].to_numpy(float) / frame["sport"].map(sigma).to_numpy(float)
    out["margin_late"] = out["margin_sigma"] * (1.0 - frame["frac_elapsed"].to_numpy(float))
    return out


def design(frame: pd.DataFrame, sports: Sequence[str]) -> np.ndarray:
    """One intercept column per sport, then the four normalised state terms."""
    cols = [(frame["sport"] == s).to_numpy(float) for s in sports]
    return np.column_stack(cols + [frame[c].to_numpy(float) for c in FEATS])


def fit_offset(X: np.ndarray, y: np.ndarray, offset: np.ndarray, *, lam: float = 0.0,
               b0: Optional[np.ndarray] = None, iters: int = 40) -> np.ndarray:
    """IRLS for logit(p) = offset + X b penalised by 0.5*lam*||b - b0||^2 (huge lam -> b0)."""
    ref = np.zeros(X.shape[1]) if b0 is None else np.asarray(b0, dtype=float)
    b = ref.copy()
    for _ in range(iters):
        p = sigmoid(offset + X @ b)
        w = np.clip(p * (1.0 - p), 1e-8, None)
        grad = X.T @ (y - p) - lam * (b - ref)
        step = np.linalg.solve((X.T * w) @ X + (lam + RIDGE) * np.eye(X.shape[1]), grad)
        b = b + step
        if float(np.max(np.abs(step))) < 1e-9:
            break
    return b


def _fit(frame: pd.DataFrame, sports: Sequence[str], *, lam: float = 0.0,
         b0: Optional[np.ndarray] = None) -> np.ndarray:
    return fit_offset(design(frame, sports), frame["y"].to_numpy(float),
                      frame["logit_market"].to_numpy(float), lam=lam, b0=b0)


def _b0_for(pooled: np.ndarray, sports: Sequence[str], sport: str) -> np.ndarray:
    # the pooled coefficients rewritten in the one-sport parameterisation
    return np.concatenate([[pooled[list(sports).index(sport)]], pooled[len(sports):]])


def _predict(frame: pd.DataFrame, sports: Sequence[str], b: np.ndarray) -> np.ndarray:
    return sigmoid(frame["logit_market"].to_numpy(float) + design(frame, sports) @ b)


def choose_lambda(train: pd.DataFrame, sport: str, sigma: Dict[str, float]) -> Tuple[float, dict]:
    """lambda on an INNER TRAIN split: hold out the sport's last train date, purge by cluster."""
    sub = train[train["sport"] == sport]
    days = sorted(sub["date"].unique())
    if len(days) < 2:
        return 0.0, {}
    hold = sub[sub["date"] == days[-1]]
    last = train.groupby("cluster")["ts_utc"].max()
    inner = train[train["cluster"].isin(last.index[last < hold["ts_utc"].min()])]
    if len(inner[inner["sport"] == sport]) < MIN_TRAIN or hold["y"].nunique() < 2:
        return 0.0, {}
    inner, hold = _scale(inner, sigma), _scale(hold, sigma)
    sports = sorted(inner["sport"].unique())
    pooled = _fit(inner, sports)
    hy, own, losses = hold["y"].to_numpy(float), inner[inner["sport"] == sport], {}
    for lam in LAM_GRID:
        b = _fit(own, [sport], lam=lam, b0=_b0_for(pooled, sports, sport))
        losses[str(lam)] = float(np.mean((_predict(hold, [sport], b) - hy) ** 2))
    return float(min(losses, key=lambda k: losses[k])), losses


def apply_fold(train: pd.DataFrame, test: pd.DataFrame, sport: str) -> Tuple[pd.DataFrame, dict]:
    """Fit sigma, the null and all three arms on TRAIN; apply them to the sport's TEST rows."""
    tr_sport, mlb_m = train[train["sport"] == sport], train[train["sport"] == "mlb"]["margin"]
    sigma = {"nba": NBA_SIGMA, "mlb": float(mlb_m.std()) if len(mlb_m) > 1 else 1.0}
    lam, lam_losses = choose_lambda(train, sport, sigma)
    tr, te = _scale(train, sigma), _scale(test, sigma)
    sports = sorted(tr["sport"].unique())
    b_pool = _fit(tr, sports)
    b0 = _b0_for(b_pool, sports, sport)
    own = tr[tr["sport"] == sport]
    b_own, b_part = _fit(own, [sport]), _fit(own, [sport], lam=lam, b0=b0)
    null = fit_offset(np.column_stack([np.ones(len(tr_sport)), logit(tr_sport["market"])]),
                      tr_sport["y"].to_numpy(float), np.zeros(len(tr_sport)))
    out = te.assign(p_line=te["market"].to_numpy(float))
    out["p_null"] = sigmoid(null[0] + null[1] * out["logit_market"].to_numpy(float))
    out["p_pooled"] = _predict(out, sports, b_pool)
    out["p_persport"] = _predict(out, [sport], b_own)
    out["p_partial"] = _predict(out, [sport], b_part)
    return out, {"sigma": sigma, "lambda": lam, "lambda_inner_brier": lam_losses,
                 "sports_in_train": sports, "coef_names": ["intercept"] + list(FEATS),
                 "coef_persport": [float(v) for v in b_own], "coef_null": [float(v) for v in null],
                 "coef_partial": [float(v) for v in b_part],
                 "coef_pooled_for_sport": [float(v) for v in b0], "n_train_ticks": int(len(tr)),
                 "n_train_ticks_sport": int(len(tr_sport)),
                 "n_train_clusters": int(tr["cluster"].nunique())}


def walk_forward(rows: pd.DataFrame, *, n_folds: int = N_FOLDS,
                 embargo_days: int = EMBARGO_DAYS) -> Tuple[pd.DataFrame, List[dict]]:
    """Per-sport date blocks on ONE shared, strictly causal calendar."""
    last = rows.groupby("cluster")["ts_utc"].max()
    scored: List[pd.DataFrame] = []
    folds: List[dict] = []
    for sport, sub in rows.groupby("sport", sort=True):
        for k, block in enumerate(fold_dates(sub, n_folds)[1:], start=1):
            test = sub[sub["date"].isin(set(block))]
            if test.empty:
                continue
            cut = test["ts_utc"].min() - pd.Timedelta(days=embargo_days)
            train = rows[rows["cluster"].isin(last.index[last < cut])]
            n_own = int((train["sport"] == sport).sum())
            if n_own < MIN_TRAIN or train[train["sport"] == sport]["y"].nunique() < 2:
                folds.append({"sport": sport, "fold": k, "status": "NO_TRAIN",
                              "test_start": str(min(block)), "n_train": n_own})
                continue
            assert not (set(train["cluster"]) & set(test["cluster"])), "fold not cluster-disjoint"
            assert train["ts_utc"].max() < cut <= test["ts_utc"].min(), "embargo violated"
            block_out, info = apply_fold(train, test, sport)
            block_out["fold"] = k
            scored.append(block_out)
            info.update(sport=sport, fold=k, status="OK", embargo_cut=str(cut),
                        test_start=str(min(block)), test_end=str(max(block)),
                        n_test_ticks=int(len(test)), n_test_clusters=int(test["cluster"].nunique()))
            folds.append(info)
    return (pd.concat(scored, ignore_index=True) if scored else rows.iloc[0:0].copy()), folds


def _dm(diff: np.ndarray, clusters: pd.Series) -> Dict[str, Any]:
    if clusters.nunique() < 2 or not len(diff) or float(np.abs(diff).max()) == 0.0:
        return {"stat": None, "p_value": None, "ci95": None, "n_clusters": int(clusters.nunique())}
    r = diebold_mariano([float(v) for v in diff], clusters.astype(str).tolist())
    return {"stat": float(r.dm_stat), "p_value": float(r.p_value),
            "ci95": [float(r.ci95[0]), float(r.ci95[1])], "n_clusters": int(r.n_clusters)}


def score_sport(sub: pd.DataFrame) -> Dict[str, Any]:
    """Tick-weighted Brier per arm plus every paired, cluster-robust DM interval."""
    if sub.empty:
        return {"n": 0}
    y = sub["y"].to_numpy(float)
    loss = {a: (sub["p_" + a].to_numpy(float) - y) ** 2 for a in ARMS}
    row: Dict[str, Any] = {"n": int(len(sub)), "n_clusters": int(sub["cluster"].nunique()),
                           "brier": {a: float(v.mean()) for a, v in loss.items()},
                           "improvement": {}, "dm": {}}
    pairs = [(a, b) for a in ("pooled", "persport", "partial")
             for b in ("line", "null", "persport") if a != b]
    for arm, base in pairs:
        d, key = loss[base] - loss[arm], "%s_vs_%s" % (arm, base)   # d > 0 -> `arm` lost less
        row["improvement"][key] = float(d.mean())
        row["dm"][key] = _dm(d, sub["cluster"])
    frame = sub.assign(loss_differential=loss["line"] - loss["partial"])
    ess = effective_sample_size(frame, game_column="cluster", loss_column="loss_differential")
    row.update(icc_by_cluster=ess["rho"], design_effect=ess["design_effect"], n_eff=ess["n_eff"])
    attach_informative_summary(row, frame, "loss_differential", game_col="cluster", ts_col="ts_utc")
    row["n_informative"] = int(row["tick_informative"]["n_informative"])
    return row


def coef_drift(folds: List[dict]) -> Dict[str, Any]:
    """Fold-to-fold spread of each coefficient: per-sport fit vs the partially pooled one."""
    out: Dict[str, Any] = {}
    ok = [f for f in folds if f["status"] == "OK"]
    for sport in sorted({f["sport"] for f in ok}):
        rows = [f for f in ok if f["sport"] == sport]
        names = rows[0]["coef_names"]
        block: Dict[str, Any] = {"n_folds": len(rows), "lambda_by_fold": [f["lambda"] for f in rows]}
        for key in ("coef_persport", "coef_partial"):
            mat = np.array([f[key] for f in rows], dtype=float)
            block[key] = {n: {"min": float(mat[:, j].min()), "max": float(mat[:, j].max()),
                              "std": float(mat[:, j].std(ddof=1)) if len(rows) > 1 else 0.0}
                          for j, n in enumerate(names)}
            block[key + "_mean_abs_std"] = float(np.mean([block[key][n]["std"] for n in names]))
        out[sport] = dict(block, drift_reduction_partial_vs_persport=float(
            block["coef_persport_mean_abs_std"] - block["coef_partial_mean_abs_std"]))
    return out


def summarize(scored: pd.DataFrame, folds: List[dict], corpus: Dict[str, Any]) -> Dict[str, Any]:
    """The artifact. `prereg_draft_warranted` is the row's own three-part condition."""
    by_sport = {s: score_sport(sub) for s, sub in scored.groupby("sport", sort=True)}
    mlb, nba = by_sport.get("mlb", {"n": 0}), by_sport.get("nba", {"n": 0})
    mlb_ci = (mlb.get("dm", {}).get("partial_vs_line", {}) or {}).get("ci95")
    nba_ci = (nba.get("dm", {}).get("partial_vs_persport", {}) or {}).get("ci95")
    nba_ok = bool(not nba.get("n") or nba_ci is None or nba_ci[0] >= 0.0
                  or nba["improvement"]["partial_vs_persport"] >= 0.0)
    cleared = bool(mlb.get("n") and mlb["improvement"]["partial_vs_line"] >= IMPROVEMENT_BAR
                   and mlb_ci is not None and mlb_ci[0] > 0.0
                   and mlb["improvement"]["partial_vs_null"] > 0.0 and nba_ok)
    return {
        "spec_id": "scripts.platformkit.eval_gate.s116_pooled_ingame:pooled_ingame_residual_v1",
        "tier": "SCREEN (uncharged, no prereg seal, no K read, no ledger write)",
        "label": "SINGLE-WINDOW", "edge_claimed": False,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "corpus": corpus,
        "model": "logit(p) = logit(market) + a_sport + b . [frac_elapsed, margin_sigma, "
                 "margin_sigma * (1 - frac_elapsed), logit(prior) - logit(market)]",
        "null": "S94 global recalibration [1, logit(market)] fit per sport on the identical rows",
        "design": {"folds": N_FOLDS, "embargo_days": EMBARGO_DAYS,
                   "purge": "by cluster settlement (NBA game, MLB real game -- S106)",
                   "calendar": "shared, strictly causal: train is every cluster of EITHER sport "
                               "whose last tick precedes the fold's first tick",
                   "nba_sigma": NBA_SIGMA, "mlb_sigma": "std of the run differential on TRAIN",
                   "lambda_grid": list(LAM_GRID), "min_train_ticks": MIN_TRAIN},
        "improvement_bar": IMPROVEMENT_BAR, "n_scored_ticks": int(len(scored)),
        "by_sport": by_sport, "coefficient_drift": coef_drift(folds), "folds": folds,
        "nba_direction_note": "The screen corpora are date-disjoint and ordered, so no NBA fold "
                              "has an MLB row in train: the pooled design collapses to the per-sport "
                              "one and all three arms coincide. NBA being unhurt is structural.",
        "nba_not_hurt": nba_ok, "prereg_draft_warranted": cleared,
        "honest_note": "Tick-weighted Brier only. No dollar, ROI, profit or edge claim. An "
                       "uncharged screen is a NON-FINDING; a null result is a success.",
    }


def run(out_dir: Path = OUT_DIR, stem: str = STEM,
        rows: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    frame = prepare([load_nba(), load_mlb()]) if rows is None else rows
    scored, folds = walk_forward(frame)
    summary = summarize(scored, folds, census(frame))
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    series = scored[["sport", "cluster", "date", "ts_utc", "fold", "y", "margin", "frac_elapsed",
                     "margin_sigma", "gap"] + ["p_" + a for a in ARMS]].copy()
    y = series["y"].to_numpy(float)
    for arm in ARMS:                                        # Q9: the paired-loss series
        series["loss_" + arm] = (series["p_" + arm].to_numpy(float) - y) ** 2
    for base in ("line", "null", "persport"):
        series["d_partial_vs_" + base] = series["loss_" + base] - series["loss_partial"]
    series.to_csv(Path(out_dir) / (stem + ".csv"), index=False, encoding="ascii")
    summary["per_tick_csv"] = str(Path(out_dir) / (stem + ".csv"))
    (Path(out_dir) / (stem + ".json")).write_text(json.dumps(
        summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary


def main() -> int:
    s = run()
    print("corpus %s" % json.dumps(s["corpus"], sort_keys=True))
    for sport, r in sorted(s["by_sport"].items()):
        print("%-4s n %6d clusters %4d inf %6d n_eff %8.1f | %s"
              % (sport, r["n"], r["n_clusters"], r["n_informative"], r["n_eff"],
                 " ".join("%s %.6f" % (a, r["brier"][a]) for a in ARMS)))
        for key in sorted(r["improvement"]):
            print("      %-22s %+.6f ci %s" % (key, r["improvement"][key], r["dm"][key]["ci95"]))
    for sport, d in sorted(s["coefficient_drift"].items()):
        print("drift %-4s persport %.6f partial %.6f reduction %+.6f lambda %s"
              % (sport, d["coef_persport_mean_abs_std"], d["coef_partial_mean_abs_std"],
                 d["drift_reduction_partial_vs_persport"], d["lambda_by_fold"]))
    print("nba_not_hurt %s | prereg_draft_warranted %s (bar %+.4f)"
          % (s["nba_not_hurt"], s["prereg_draft_warranted"], s["improvement_bar"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
