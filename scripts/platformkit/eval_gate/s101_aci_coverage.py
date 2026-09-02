"""scripts.platformkit.eval_gate.s101_aci_coverage -- S101: score adaptive conformal
inference (`scripts/platformkit/ingame/aci_online.py`) on the S86 NBA per-tick SCREEN series.

S97 fitted a Kalman posterior and its nominal 90 pct intervals reached 0.08 GROUPED coverage.
S101 replaces the parametric interval with a conformal one and asks the same question of two
point predictors: the raw in-play `market` probability and the S86 as-of `model` prior.

A per-tick nonconformity score |y - p| is degenerate (y in {0,1} is never inside a narrow
probability band), so calibration is GROUPED, exactly as S97's coverage measure is grouped:
on TRAIN-fold ticks only, within each phase cell, ticks are cut into equal-count groups
(>= COVERAGE_MIN_GROUP each, capped at COVERAGE_MAX_GROUPS) ordered by p, and the score of a
group is |mean(p) - realised group frequency|. The (1-alpha) empirical quantile of those group
scores is the cell half-width. A cell too small to form 2 groups inherits the pooled quantile.

Two arms per (predictor, nominal):
  STATIC -- the train-calibrated band, held fixed on the test fold. Leak-free.
  ACI    -- `run_aci_stream` walked ONLINE over each held-out game's ticks in ts order, alpha
            reset at every game boundary, alpha at tick t built only from misses at 0..t-1.

HONEST NOTE ON THE ACI ARM: `y` is CONSTANT within a game (measured: nunique == 1 for all 797
games), so any within-game realised label is the game's own final outcome. The within-game ACI
arm therefore consumes the label of the game it is adapting on. It is reported as a
LABEL-CONSUMING diagnostic / ceiling, never as the leak-free number; STATIC is the leak-free
deliverable. This is recorded rather than hidden.

Walk-forward by game-first date, 5 folds, purged by game (asserted disjoint), 1-day embargo
(asserted). Input is the S86 archived per-tick CSV (SCREEN side). A SCREEN is a NON-FINDING:
no prereg seal, no ledger charge, no K read, no ledger write. SINGLE-WINDOW. Coverage is the
deliverable, not Brier. Calibration language only. ASCII only.
Test: python -m pytest tests/platformkit/ingame/test_s101_aci_coverage.py -q
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.s94_nba_early_shrinkage import (
    EMBARGO_DAYS, N_FOLDS, fold_dates, load_screen)
from scripts.platformkit.ingame.aci_online import (
    _DEFAULT_GAMMA, INSUFFICIENT_DATA, gate_aci_on_stream, run_aci_stream)

OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "cache" / "eval_gate"
STEM = "s101_aci_coverage_2026-09-03"
NOMINALS: Tuple[float, ...] = (0.90, 0.80)       # the row's two nominal levels
COVERAGE_TOL = 0.02                              # S97's bar, byte-identical; NEVER widened (Q3)
COVERAGE_MIN_GROUP, COVERAGE_MAX_GROUPS = 400, 50   # S97's grouped-coverage resolution
MIN_CELL_GROUPS = 2
GAMMA = _DEFAULT_GAMMA                           # aci_online's own default (0.01); reported
ARMS = ("market", "model")
PHASES = ("P1", "P2", "P3", "P4", "OT")


def _n_groups(n: int) -> int:
    return int(min(COVERAGE_MAX_GROUPS, n // COVERAGE_MIN_GROUP))


def _gid(n: int, k: int) -> np.ndarray:
    return np.minimum((np.arange(n) * k) // n, k - 1)


def calibrate(train: pd.DataFrame, arm: str, alpha: float) -> Tuple[Dict[str, float], float]:
    """Grouped split-conformal half-width per phase cell, fitted on TRAIN ticks only."""
    per_cell: Dict[str, float] = {}
    pool: List[float] = []
    for cell, sub in train.groupby("cell", sort=False):
        k = _n_groups(len(sub))
        if k < MIN_CELL_GROUPS:
            continue
        o = sub.sort_values(arm, kind="mergesort")
        gid = _gid(len(o), k)
        p, y = o[arm].to_numpy(float), o["y"].to_numpy(float)
        dev = [abs(float(p[gid == i].mean()) - float(y[gid == i].mean())) for i in range(k)]
        per_cell[str(cell)] = float(np.quantile(dev, 1.0 - alpha, method="higher"))
        pool.extend(dev)
    pooled = float(np.quantile(pool, 1.0 - alpha, method="higher")) if pool else 0.0
    return per_cell, pooled


def aci_walk(test: pd.DataFrame, lo: np.ndarray, hi: np.ndarray,
             alpha: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[dict]]:
    """Run `run_aci_stream` per held-out GAME in ts order; alpha resets at every boundary."""
    aci_lo, aci_hi = lo.copy(), hi.copy()
    alpha_at = np.full(len(test), alpha, dtype=float)
    traj: List[dict] = []
    y = test["y"].to_numpy(float)
    for game, pos in test.groupby("game", sort=False).indices.items():
        pos = np.sort(np.asarray(pos))
        res = run_aci_stream(lo[pos], hi[pos], y[pos], alpha, GAMMA)
        if not isinstance(res, dict):          # INSUFFICIENT_DATA -> keep the static band
            traj.append({"game": str(game), "n": int(len(pos)), "status": INSUFFICIENT_DATA})
            continue
        aci_lo[pos], aci_hi[pos] = np.asarray(res["aci_lo"]), np.asarray(res["aci_hi"])
        a = np.asarray(res["alpha_trajectory"], dtype=float)
        alpha_at[pos] = a[:-1]                 # alpha USED at tick t (built from misses < t)
        tail = a[max(1, int(0.75 * len(a))):]
        traj.append({"game": str(game), "n": int(len(pos)), "status": "OK",
                     "alpha_final": float(a[-1]), "alpha_tail_mean": float(tail.mean()),
                     "alpha_tail_std": float(tail.std()), "alpha_min": float(a.min()),
                     "hit_zero_clip": bool(a.min() <= 1e-12)})
    return aci_lo, aci_hi, alpha_at, traj


def grouped_coverage(p: np.ndarray, y: np.ndarray, lo: np.ndarray, hi: np.ndarray,
                     nominal: float) -> Dict[str, Any]:
    """S97's measure: equal-count groups by p; COVERED when the group frequency is in [lo, hi]."""
    n = len(p)
    k = _n_groups(n)
    if k < MIN_CELL_GROUPS:
        return {"n": n, "n_groups": k, "coverage": None,
                "absent_because": "fewer than 2 groups of %d ticks" % COVERAGE_MIN_GROUP}
    order = np.argsort(p, kind="mergesort")
    gid = _gid(n, k)
    stat = [(float(y[order][gid == i].mean()), float(lo[order][gid == i].mean()),
             float(hi[order][gid == i].mean())) for i in range(k)]
    share = float(np.mean([a <= f <= b for f, a, b in stat]))
    return {"n": n, "n_groups": k, "group_size": n // k, "coverage": share, "nominal": nominal,
            "deviation": float(share - nominal),
            "within_tolerance": bool(abs(share - nominal) <= COVERAGE_TOL),
            "mean_interval_width": float(np.mean([b - a for _, a, b in stat])),
            "mean_miss": float(np.mean([0.0 if a <= f <= b else min(abs(f - a), abs(f - b))
                                        for f, a, b in stat]))}


def fold_blocks(frame: pd.DataFrame, n_folds: int = N_FOLDS) -> List[Tuple[int, Sequence[str], str]]:
    """(fold, test days, embargo cut) for each held-out block; block 0 is the train-only seed."""
    out = []
    for k, block in enumerate(fold_dates(frame, n_folds)[1:], start=1):
        day0 = min(block)
        cut = str(dt.date.fromisoformat(str(day0)) - dt.timedelta(days=int(EMBARGO_DAYS)))
        out.append((k, block, cut))
    return out


def run_fold(train: pd.DataFrame, test: pd.DataFrame, arm: str,
             alpha: float) -> Tuple[pd.DataFrame, dict]:
    """Calibrate on train, band the test fold, then walk ACI online within each test game."""
    per_cell, pooled = calibrate(train, arm, alpha)
    p = test[arm].to_numpy(float)
    hw = test["cell"].map(per_cell).fillna(pooled).to_numpy(float)
    lo, hi = np.clip(p - hw, 0.0, 1.0), np.clip(p + hw, 0.0, 1.0)
    aci_lo, aci_hi, alpha_at, traj = aci_walk(test, lo, hi, alpha)
    ticks = pd.DataFrame({
        "game": test["game"].to_numpy(), "date": test["date"].to_numpy(),
        "ts": test["ts"].to_numpy(), "phase": test["period_bucket"].to_numpy(),
        "cell": test["cell"].to_numpy(), "arm": arm, "nominal": round(1.0 - alpha, 2),
        "p": p, "y": test["y"].to_numpy(float), "lo_static": lo, "hi_static": hi,
        "lo_aci": aci_lo, "hi_aci": aci_hi, "alpha_t": alpha_at})
    ok = [t for t in traj if t["status"] == "OK"]
    fit = {"n_cells_calibrated": len(per_cell), "pooled_half_width": pooled,
           "half_width_min": float(np.min(hw)), "half_width_max": float(np.max(hw)),
           "n_games_streamed": len(ok), "n_games_insufficient": len(traj) - len(ok),
           "alpha_final_mean": float(np.mean([t["alpha_final"] for t in ok])) if ok else None,
           "alpha_tail_std_mean": float(np.mean([t["alpha_tail_std"] for t in ok])) if ok else None,
           "share_games_hit_zero_clip": float(np.mean([t["hit_zero_clip"] for t in ok])) if ok else None}
    return ticks, fit


def score(ticks: pd.DataFrame, nominal: float) -> Dict[str, Any]:
    """Grouped coverage per phase and overall, for the STATIC and the ACI band."""
    out: Dict[str, Any] = {}
    for label, (lc, hc) in (("static", ("lo_static", "hi_static")), ("aci", ("lo_aci", "hi_aci"))):
        per_phase: Dict[str, Any] = {}
        for phase in PHASES + ("ALL",):
            sub = ticks if phase == "ALL" else ticks[ticks["phase"] == phase]
            if sub.empty:
                per_phase[phase] = {"n": 0, "coverage": None, "absent_because": "no ticks"}
                continue
            per_phase[phase] = grouped_coverage(
                sub["p"].to_numpy(float), sub["y"].to_numpy(float),
                sub[lc].to_numpy(float), sub[hc].to_numpy(float), nominal)
        out[label] = per_phase
    return out


def planted_null(ticks: pd.DataFrame, alpha: float) -> Dict[str, Any]:
    """aci_online's own planted null on the pooled test stream (diagnostic, not an arm)."""
    res = gate_aci_on_stream(ticks["lo_static"].to_numpy(float),
                             ticks["hi_static"].to_numpy(float),
                             ticks["y"].to_numpy(float), alpha, GAMMA)
    nr = res.get("null_result")
    return {"null_collapses": bool(nr.get("null_collapses")) if isinstance(nr, dict) else None,
            "null_construction": res.get("null_construction"),
            "ship_recommendation": res.get("ship_recommendation"),
            "note": "per-tick coverage inside gate_aci_on_stream is the DEGENERATE binary form; "
                    "only null_collapses (alpha stability on a stationary stream) is read here"}


def run(out_dir: Path = OUT_DIR, stem: str = STEM) -> Dict[str, Any]:
    frame = load_screen()
    blocks = fold_blocks(frame)
    all_ticks: List[pd.DataFrame] = []
    folds: List[dict] = []
    for k, block, cut in blocks:
        train = frame[frame["date"] < cut]
        test = frame[frame["date"].isin(set(block))].reset_index(drop=True)
        if train.empty or train["y"].nunique() < 2 or test.empty:
            folds.append({"fold": k, "status": "INSUFFICIENT", "n_train": int(len(train))})
            continue
        assert not (set(train["game"]) & set(test["game"])), "fold not game-disjoint (purge)"
        assert train["date"].max() < cut <= min(block), "embargo/ordering violated"
        rec = {"fold": k, "status": "OK", "test_start": str(min(block)), "test_end": str(max(block)),
               "embargo_cut": cut, "train_date_max": str(train["date"].max()),
               "n_train_ticks": int(len(train)), "n_train_games": int(train["game"].nunique()),
               "n_test_ticks": int(len(test)), "n_test_games": int(test["game"].nunique()),
               "fits": {}}
        for arm in ARMS:
            for nominal in NOMINALS:
                t, fit = run_fold(train, test, arm, round(1.0 - nominal, 10))
                t["fold"] = k
                all_ticks.append(t)
                rec["fits"]["%s|%.2f" % (arm, nominal)] = fit
        folds.append(rec)
    ticks = pd.concat(all_ticks, ignore_index=True)
    results: Dict[str, Any] = {}
    for arm in ARMS:
        for nominal in NOMINALS:
            sub = ticks[(ticks["arm"] == arm) & (ticks["nominal"] == round(nominal, 2))]
            key = "%s|%.2f" % (arm, nominal)
            results[key] = score(sub, nominal)
            results[key]["planted_null"] = planted_null(sub, round(1.0 - nominal, 10))
            results[key]["alpha_settles"] = {
                "mean_alpha_used": float(sub["alpha_t"].mean()),
                "share_ticks_at_zero_clip": float((sub["alpha_t"] <= 1e-12).mean()),
                "mean_alpha_last_quarter_by_game": float(
                    sub.groupby("game")["alpha_t"].apply(lambda s: s.tail(max(1, len(s) // 4)).mean()).mean())}
    out_dir.mkdir(parents=True, exist_ok=True)
    tick_path = out_dir / (stem + "_ticks.csv.gz")
    ticks.to_csv(tick_path, index=False, compression="gzip")
    summary = {
        "row": "S101", "corpus": "S86 NBA per-tick SCREEN archive", "verdict_side_read": False,
        "generated": dt.date.today().isoformat(), "gamma": GAMMA, "nominals": list(NOMINALS),
        "coverage_tol": COVERAGE_TOL, "coverage_min_group": COVERAGE_MIN_GROUP,
        "coverage_max_groups": COVERAGE_MAX_GROUPS, "n_folds": N_FOLDS,
        "embargo_days": EMBARGO_DAYS, "arms": list(ARMS),
        "n_ticks_corpus": int(len(frame)), "n_games_corpus": int(frame["game"].nunique()),
        "n_ticks_scored": int(len(ticks) // (len(ARMS) * len(NOMINALS))),
        "n_games_scored": int(ticks["game"].nunique()),
        "s97_reference_grouped_coverage_at_0.90": 0.08,
        "aci_arm_label": "LABEL-CONSUMING: y is constant within a game, so within-game online "
                         "adaptation reads that game's own final outcome. STATIC is the "
                         "leak-free arm; ACI is a ceiling diagnostic.",
        "single_window": True, "charged": False, "prereg_seal": None,
        "folds": folds, "results": results, "tick_archive": str(tick_path)}
    (out_dir / (stem + ".json")).write_text(json.dumps(summary, indent=2), encoding="ascii")
    return summary


def main() -> int:
    s = run()
    print("=== S101 adaptive conformal coverage on S86 NBA ticks ===")
    print("  scored %d ticks / %d games; gamma=%.3f; S97 reference at 0.90 = 0.08"
          % (s["n_ticks_scored"], s["n_games_scored"], s["gamma"]))
    for key, res in s["results"].items():
        print("  --- %s" % key)
        for band in ("static", "aci"):
            row = "    %-7s" % band
            for phase in PHASES + ("ALL",):
                c = res[band][phase].get("coverage")
                row += " %s=%s" % (phase, "n/a" if c is None else "%.3f" % c)
            print(row)
            w = res[band]["ALL"].get("mean_interval_width")
            print("            ALL width=%s within_tol(ALL)=%s"
                  % ("n/a" if w is None else "%.4f" % w, res[band]["ALL"].get("within_tolerance")))
        print("    alpha: %s" % json.dumps(res["alpha_settles"]))
        print("    planted_null collapses=%s" % res["planted_null"]["null_collapses"])
    print("  Calibration only -- no $ / ROI / edge claim. SINGLE-WINDOW. No ledger charge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
