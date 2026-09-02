"""S96 -- does the NBA in-play line OVERSHOOT a scoring event and revert, or drift?

EVENT = |margin_t - margin_{t-1}| >= 3 between consecutive S86 screen ticks (also >= 5).
Premise: regress fk = logit(market_{t+k}) - logit(market_event) on m1 = logit(market_event) -
logit(market_pre_event), game-clustered.  slope < 0 = overshoot (mean reversion); > 0 = drift.
Arm on the k post-event ticks: p = sigmoid(logit(market_t) - lambda_c * m1 * decay(j/k)),
decay = 1 - (j-1)/k; lambda_c > 0 shrinks toward the pre-event line, < 0 extrapolates, and the
grid is symmetric so the TRAIN folds pick the sign.  NULL = the S94 global logistic
recalibration on identical rows (S94: a recal null must be beaten).  S86 SCREEN side only; a
SCREEN is a NON-FINDING: no seal, no charge, no K read, no ledger write.  SINGLE-WINDOW.
Per-file test: python -m pytest tests/platformkit/ingame/test_s96_nba_overreaction.py -q
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.eval_gate.s94_nba_early_shrinkage import (  # same package, reused as-is
    S86_CSV, _dm, _p, fold_dates, logit, sigmoid)
from scripts.platformkit.eval_gate.scoring import ece
from scripts.platformkit.eval_gate.tick_informative import attach_informative_summary
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size

OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "cache" / "eval_gate"
STEM = "s96_nba_overreaction_2026-09-03"
EVENT_THRESHOLDS, HORIZONS = (3, 5), (3, 5, 10)
PRIMARY_THRESHOLD, PRIMARY_K = 3, 5
IMPROVEMENT_BAR = 0.004          # the row's bar; NEVER lowered (Q3)
N_FOLDS, EMBARGO_DAYS = 5, 1
MIN_CELL_TRAIN = 200             # below this a phase keeps lambda = 0 (raw market)
LAMBDA_GRID = np.round(np.arange(-1.0, 1.0 + 1e-9, 0.02), 4)
COLS = ["game_id", "game_date", "ts", "period_bucket", "margin", "model", "market", "y"]
ARMS = ("market", "recal", "arm")
SPEC = {
    "spec_id": "scripts.platformkit.eval_gate.s96_nba_overreaction:nba_event_overreaction_v1",
    "sport": "nba", "tier": "SCREEN (uncharged, no prereg seal, no K read, no ledger write)",
    "label": "SINGLE-WINDOW", "edge_claimed": False, "improvement_bar": IMPROVEMENT_BAR,
    "event_definition": "|margin_t - margin_{t-1}| >= threshold between consecutive ticks",
    "arm": "p = sigmoid(logit(market_t) - lambda_c * m1 * decay(j/k)), decay = 1 - (j-1)/k",
    "null": "global logistic recalibration [1, logit(market)] on the identical train rows",
    "design": {"folds": N_FOLDS, "embargo_days": EMBARGO_DAYS, "purge": "by game",
               "order": "game-first date", "lambda_grid": "[-1.0, 1.0] step 0.02",
               "min_phase_train_ticks": MIN_CELL_TRAIN, "fit_on": "TRAIN folds only"},
    "honest_note": "Calibration (Brier / ECE) only; a slope > 0 is drift, not overshoot.",
}


def load_screen(path: Path = S86_CSV) -> pd.DataFrame:
    """S86 SCREEN-side ticks in per-game tick order, with the per-tick margin/line move."""
    df = pd.read_csv(path, usecols=COLS).rename(columns={"period_bucket": "phase"})
    df["game"] = df["game_id"].astype(str)
    df["date"] = df["game"].map(df.groupby("game")["game_date"].min())
    df = df.sort_values(["game", "ts"], kind="mergesort").reset_index(drop=True)
    df["lm"] = logit(df["market"])
    g = df.groupby("game", sort=False)
    df["dmargin"], df["m1"] = g["margin"].diff(), g["lm"].diff()
    return df


def cluster_slope(x, y, cluster: pd.Series) -> Dict[str, Any]:
    """OLS slope of y on x with a one-way cluster-robust (sandwich) 95 pct CI."""
    xv, yv = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    dsg = np.column_stack([np.ones(len(xv)), xv])
    xtxi = np.linalg.pinv(dsg.T @ dsg)
    beta = xtxi @ (dsg.T @ yv)
    resid, meat = yv - dsg @ beta, np.zeros((2, 2))
    for _, idx in pd.Series(np.arange(len(xv))).groupby(cluster.to_numpy(), sort=False):
        s = dsg[idx.to_numpy()].T @ resid[idx.to_numpy()]
        meat += np.outer(s, s)
    ng = int(cluster.nunique())
    se, b = float(np.sqrt((xtxi @ meat @ xtxi * (ng / max(ng - 1, 1)))[1, 1])), float(beta[1])
    return {"slope": b, "n": int(len(xv)), "n_games": ng, "ci95": [b - 1.96 * se, b + 1.96 * se]}


def _slope_block(sub: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if len(sub) < 30 or bool(sub[["m1", "fk", "mk"]].isna().any().any()):
        return None
    r = cluster_slope(sub["m1"].to_numpy(), sub["fk"].to_numpy(), sub["game"])
    y = sub["y"].to_numpy(dtype=float)
    r.update({"mean_event_move": float(sub["m1"].mean()),
              "mean_forward_move": float(sub["fk"].mean()),
              "brier_at_event": float(np.mean((sub["market"] - y) ** 2)),
              "brier_at_event_plus_k": float(np.mean((sub["mk"] - y) ** 2))})
    return r


def premise(df: pd.DataFrame) -> Dict[str, Any]:
    """STEP 0: event counts per phase, the fk-on-m1 slope, and Brier at t vs at t+k.

    PLACEBO_nonevent runs the identical regression on ticks that are NOT events: if the slope
    is the same there, the drift belongs to the tick series, not to scoring events.
    """
    g = df.groupby("game", sort=False)
    fwd = {k: g["lm"].shift(-k) - df["lm"] for k in HORIZONS}
    mkk = {k: g["market"].shift(-k) for k in HORIZONS}
    out: Dict[str, Any] = {}
    for thr in EVENT_THRESHOLDS:
        mask = df["dmargin"].abs() >= thr
        block: Dict[str, Any] = {
            "n_events": int(mask.sum()), "n_games": int(df.loc[mask, "game"].nunique()),
            "by_phase": {str(p): int(n) for p, n in df.loc[mask, "phase"].value_counts().items()},
            "horizons": {}}
        for k in HORIZONS:
            ok = fwd[k].notna() & mkk[k].notna() & df["m1"].notna()
            cut = {"ALL": mask & ok, "PLACEBO_nonevent": (~mask) & ok}
            # slice fwd/mkk by the same mask: .assign() onto an EMPTY frame reindexes to full
            sel = {n: df[m].assign(fk=fwd[k][m], mk=mkk[k][m]) for n, m in cut.items()}
            named = list(sel["ALL"].groupby("phase")) + list(sel.items())
            rows = {str(n): _slope_block(s) for n, s in named}
            block["horizons"][str(k)] = {n: r for n, r in rows.items() if r}
        out[str(thr)] = block
    return out


def assign_windows(df: pd.DataFrame, threshold: int, k: int) -> pd.DataFrame:
    """The k post-event ticks (j = 1 .. k), tagged with j and the event move; a tick inside
    two windows belongs to the NEAREST preceding event, so a new event restarts it."""
    out = df.copy()
    is_event = (out["dmargin"].abs() >= threshold).to_numpy()
    grp = out.groupby("game", sort=False)
    pos, gid = grp.cumcount().to_numpy(), grp.ngroup()
    for col, src in (("event_pos", pos), ("event_move", out["m1"].to_numpy(dtype=float))):
        out[col] = pd.Series(np.where(is_event, src, np.nan), index=out.index).groupby(gid).ffill()
    out["j"] = pos - out["event_pos"]
    out = out[(out["j"] >= 1) & (out["j"] <= k) & out["event_move"].notna()].copy()
    out["decay"] = 1.0 - (out["j"].to_numpy(dtype=float) - 1.0) / float(k)
    out["adj"] = out["event_move"].to_numpy(dtype=float) * out["decay"].to_numpy()
    return out.reset_index(drop=True)


def fit_lambda(train: pd.DataFrame) -> Dict[str, float]:
    """lambda_c per phase on TRAIN only: the grid point minimising tick-weighted Brier."""
    out: Dict[str, float] = {}
    for phase, sub in train.groupby("phase", sort=True):
        if len(sub) < MIN_CELL_TRAIN or sub["y"].nunique() < 2:
            out[str(phase)] = 0.0
            continue
        lm, adj = sub["lm"].to_numpy(dtype=float), sub["adj"].to_numpy(dtype=float)
        y = sub["y"].to_numpy(dtype=float)
        losses = [float(np.mean((sigmoid(lm - lam * adj) - y) ** 2)) for lam in LAMBDA_GRID]
        out[str(phase)] = float(LAMBDA_GRID[int(np.argmin(losses))])
    return out


def apply_fold(train: pd.DataFrame, test: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Fit lambda_c and the recalibration null on TRAIN, then apply both to TEST."""
    lam_by_phase = fit_lambda(train)
    out = test.copy()
    lam = out["phase"].astype(str).map(lam_by_phase).fillna(0.0).to_numpy(dtype=float)
    out["lambda_c"] = lam
    out["p_arm"] = sigmoid(out["lm"].to_numpy(dtype=float) - lam * out["adj"].to_numpy(dtype=float))
    null = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000).fit(
        train[["lm"]].to_numpy(), train["y"].to_numpy(dtype=int))
    out["p_recal"] = null.predict_proba(out[["lm"]].to_numpy())[:, 1]
    return out, lam_by_phase


def walk_forward(frame: pd.DataFrame, *, embargo_days: int = EMBARGO_DAYS,
                 n_folds: int = N_FOLDS) -> Tuple[pd.DataFrame, List[dict]]:
    """Expanding walk-forward by game-first date; train purged by game and embargoed."""
    ordered = frame.sort_values(["date", "game", "ts"], kind="stable").reset_index(drop=True)
    scored, folds = [], []  # type: List[pd.DataFrame], List[dict]
    for i, block in enumerate(fold_dates(ordered, n_folds)[1:], start=1):
        day0 = min(block)
        cut = str(dt.date.fromisoformat(str(day0)) - dt.timedelta(days=int(embargo_days)))
        train = ordered[ordered["date"] < cut]
        test = ordered[ordered["date"].isin(set(block))]
        if train.empty or train["y"].nunique() < 2 or test.empty:
            folds.append({"fold": i, "status": "INSUFFICIENT", "n_train": int(len(train))})
            continue
        assert not (set(train["game"]) & set(test["game"])), "fold not game-disjoint (purge)"
        assert train["date"].max() < cut <= day0, "embargo/ordering violated"
        block_out, lam_by_phase = apply_fold(train, test)
        block_out["fold"] = i
        scored.append(block_out)
        folds.append({"fold": i, "status": "OK", "test_start": str(day0), "test_end": str(max(block)),
                      "embargo_cut": cut, "train_date_max": str(train["date"].max()),
                      "n_train_ticks": len(train), "n_train_games": train["game"].nunique(),
                      "n_test_ticks": len(test), "n_test_games": test["game"].nunique(),
                      "lambda_by_phase": lam_by_phase})
    return (pd.concat(scored, ignore_index=True) if scored else ordered.iloc[0:0].copy()), folds


def score_cell(sub: pd.DataFrame) -> Dict[str, Any]:
    """Tick-weighted Brier / ECE of every arm on one slice, with game-clustered DM CIs."""
    if sub.empty:
        return {"n": 0}
    y = sub["y"].to_numpy(dtype=float)
    loss = {a: (_p(sub, a) - y) ** 2 for a in ARMS}
    row: Dict[str, Any] = {
        "n": int(len(sub)), "n_games": int(sub["game"].nunique()),
        "brier": {a: float(v.mean()) for a, v in loss.items()},
        "ece": {a: float(ece(_p(sub, a), y)) for a in ARMS},
        "improvement": {}, "dm": {}, "lambda_c_mean": float(sub["lambda_c"].mean())}
    for a in ("market", "recal"):
        d = loss[a] - loss["arm"]                 # d > 0 -> the arm lost less
        row["improvement"]["arm_vs_" + a] = float(d.mean())
        row["dm"]["arm_vs_" + a] = _dm(d, sub["game"])
    frame = sub.assign(loss_differential=loss["market"] - loss["arm"])
    ess = effective_sample_size(frame, game_column="game", loss_column="loss_differential")
    row.update(icc_by_game=ess["rho"], design_effect=ess["design_effect"], n_eff=ess["n_eff"])
    attach_informative_summary(row, frame, "loss_differential", game_col="game", ts_col="ts")
    return dict(row, n_informative=int(row["tick_informative"]["n_informative"]))


def score_arm(df: pd.DataFrame, threshold: int, k: int) -> Tuple[Dict[str, Any], pd.DataFrame]:
    """One (threshold, k) arm: walk-forward, score overall and per phase, report stability."""
    scored, folds = walk_forward(assign_windows(df, threshold, k))
    if scored.empty:
        return {"threshold": threshold, "k": k, "status": "INSUFFICIENT", "folds": folds}, scored
    overall = score_cell(scored)
    lam = {str(f["fold"]): f["lambda_by_phase"] for f in folds if f["status"] == "OK"}
    vals = {p: [t.get(p, 0.0) for t in lam.values()] for p in {p for t in lam.values() for p in t}}
    spread = {p: {"min": min(v), "max": max(v), "mean": float(np.mean(v))}
              for p, v in sorted(vals.items())}
    ci = (overall["dm"]["arm_vs_market"] or {}).get("ci95")
    return {"threshold": threshold, "k": k, "status": "OK", "overall": overall,
            "n_scored_ticks": int(len(scored)), "n_scored_games": int(scored["game"].nunique()),
            "by_phase": {str(p): score_cell(s) for p, s in scored.groupby("phase", sort=True)},
            "lambda_by_fold": lam, "lambda_spread_across_folds": spread, "folds": folds,
            "bar_met": bool(overall["improvement"]["arm_vs_market"] >= IMPROVEMENT_BAR
                            and ci is not None and ci[0] > 0.0
                            and overall["improvement"]["arm_vs_recal"] > 0.0)}, scored


def _series(scored: pd.DataFrame, thr: int, k: int) -> pd.DataFrame:
    """Q9: the per-tick paired-loss series for one arm (both differentials + the cluster id)."""
    keep = scored[["game", "game_date", "ts", "fold", "phase", "j", "event_move", "adj",
                   "lambda_c", "y", "market", "model", "p_recal", "p_arm"]].copy()
    keep["threshold"], keep["k"], keep["cluster_id"] = thr, k, keep["game"]
    y = keep["y"].to_numpy(dtype=float)
    for name, col in (("loss_market", "market"), ("loss_recal", "p_recal"), ("loss_arm", "p_arm")):
        keep[name] = (keep[col].to_numpy(dtype=float) - y) ** 2
    keep["d_arm_vs_market"] = keep["loss_market"] - keep["loss_arm"]
    keep["d_arm_vs_recal"] = keep["loss_recal"] - keep["loss_arm"]
    return keep


def run(out_dir: Path = OUT_DIR, stem: str = STEM,
        frame: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    df = load_screen() if frame is None else frame
    arms: Dict[str, Any] = {}
    series: List[pd.DataFrame] = []  # Q9: per-tick paired losses, one block per arm
    for thr in EVENT_THRESHOLDS:
        for k in HORIZONS:
            res, scored = score_arm(df, thr, k)
            arms["thr%d_k%d" % (thr, k)] = res
            if not scored.empty:
                series.append(_series(scored, thr, k))
    primary = "thr%d_k%d" % (PRIMARY_THRESHOLD, PRIMARY_K)
    summary: Dict[str, Any] = dict(
        SPEC, generated_at=dt.datetime.now(dt.timezone.utc).isoformat(), primary=primary,
        source={"path": str(S86_CSV), "side": "S86 SCREEN only (verdict side never read)",
                "n_ticks": int(len(df)), "n_games": int(df["game"].nunique())},
        premise=premise(df), arms=arms,
        prereg_draft_warranted=bool(arms[primary].get("bar_met")))
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    csv_path = Path(out_dir) / (stem + ".csv")
    pd.concat(series, ignore_index=True).to_csv(csv_path, index=False, encoding="ascii")
    summary["per_tick_csv"] = str(csv_path)
    (Path(out_dir) / (stem + ".json")).write_text(
        json.dumps(summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary


def main() -> int:
    s = run()
    for thr in EVENT_THRESHOLDS:
        p = s["premise"][str(thr)]
        print("EVENTS |dmargin|>=%d n %d games %d %s"
              % (thr, p["n_events"], p["n_games"], sorted(p["by_phase"].items())))
        for k in HORIZONS:
            for ph, r in sorted(p["horizons"][str(k)].items()):
                print("  k=%-2d %-16s n %6d slope %+.4f ci [%+.4f,%+.4f] brier_t %.5f t+k %.5f" % (
                    k, ph, r["n"], r["slope"], r["ci95"][0], r["ci95"][1],
                    r["brier_at_event"], r["brier_at_event_plus_k"]))
    for name in sorted(s["arms"]):
        a = s["arms"][name]
        o = a.get("overall") or {"n": 0}
        if not o["n"]:
            print("%-10s %s" % (name, a["status"]))
            continue
        print("%-10s n %6d g %4d inf %6d n_eff %7.1f | market %.6f recal %.6f arm %.6f | vs market "
              "%+.6f %s | vs recal %+.6f | lam %s | bar_met %s" % (
                  name, o["n"], o["n_games"], o["n_informative"], o["n_eff"], o["brier"]["market"],
                  o["brier"]["recal"], o["brier"]["arm"], o["improvement"]["arm_vs_market"],
                  o["dm"]["arm_vs_market"]["ci95"], o["improvement"]["arm_vs_recal"],
                  a["lambda_spread_across_folds"], a["bar_met"]))
    print("prereg_draft_warranted %s (bar %+.4f)" % (s["prereg_draft_warranted"], s["improvement_bar"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
