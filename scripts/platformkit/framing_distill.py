"""Prereg baseball framing distillation harness.

Executes docs/evidence/tracking/PREREG_BASEBALL_FRAMING_2026-09-01.md (FROZEN):
P(called_strike | pitch taken) with a shrunk catcher/pitcher fixed-effects
baseline (plus handedness, count, location, strike-zone bounds, in-zone
predicate), candidate columns command_target_dev_x_ft /
command_target_height_ft (TRAINING_ONLY), evaluated train-2023 -> eval-2024
AND train-2024 -> eval-2023, held-out Brier + log-loss, catcher-clustered
one-sided t-test, eps=0.025 per direction (K=2 Bonferroni), planted-null
rejection, skillful-baseline requirement. Honest REJECT is a success.

As of 2026-09-01 the teacher candidate columns do not exist locally (no
baseball broadcast has produced a ball-valid CV track), so main() reports
NOT_TESTABLE with the exact missing columns instead of running the real eval.

Compliance closures (2026-09-01 audit, recorded BEFORE any real one-shot run):
- Identity-only-recovery control (prereg: "a feature that only recovers
  catcher identity must lose to this baseline"): the train-year raw catcher
  mean called-strike rate is fed as the SINGLE feature through the same
  logistic pipeline; if it fails to lose to the shrunk fixed-effects baseline
  on the eval year in either direction, the verdict is CONTROL_FAIL -- a hard
  fail that can never become PASS.
- game_date is loaded and each direction records effects_use_only_earlier.
  Declared prereg-internal tension: the frozen prereg demands BOTH directions
  (2023->2024 AND 2024->2023) yet also that "catcher effects use only earlier
  catcher pitches". Both can hold only in the 2023->2024 direction; the
  2024->2023 direction necessarily builds catcher effects from later pitches.
  The tension lives in the frozen prereg itself; it is recorded here before
  any real run, not absorbed silently.
- Planted-null permutation runs at 3 seeds (was 1); a PASS requires the gate
  to fail on every seeded null.
"""
from __future__ import annotations

import os
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

EPS = 0.025  # per-test threshold, K=2 Bonferroni (pre-registered)
K_TESTS = 2
SHRINK_K = 200.0
CANDIDATE_COLS = ("command_target_dev_x_ft", "command_target_height_ft")
TAKEN_DESCRIPTIONS = {"called_strike", "ball", "blocked_ball"}
BASE_REQUIRED = [
    "pitcher", "fielder_2", "stand", "p_throws", "balls", "strikes",
    "plate_x", "plate_z", "sz_top", "sz_bot", "description", "game_date",
]
N_NULL_SEEDS = 3
STATCAST_ROOT = os.path.join("data", "cache", "statcast")
HALF_PLATE_FT = 0.83  # plate half-width + ball radius, standard zone edge


def shrunk_effects(keys: pd.Series, y: pd.Series,
                   k: float = SHRINK_K) -> Tuple[Dict, float]:
    """Empirical-Bayes shrunk per-key deviation from the global rate.

    Computed on training rows only; unseen keys map to 0.0 at predict time.
    """
    mu = float(np.mean(y))
    g = pd.DataFrame({"k": np.asarray(keys), "y": np.asarray(y, float)})
    agg = g.groupby("k")["y"].agg(["sum", "count"])
    eff = (agg["sum"] - agg["count"] * mu) / (agg["count"] + k)
    return eff.to_dict(), mu


def design_matrix(df: pd.DataFrame, ceff: Dict, peff: Dict,
                  candidate: bool) -> np.ndarray:
    in_zone = ((df["plate_x"].abs() <= HALF_PLATE_FT)
               & (df["plate_z"] >= df["sz_bot"])
               & (df["plate_z"] <= df["sz_top"])).astype(float)
    cols = [
        df["fielder_2"].map(ceff).fillna(0.0).astype(float),
        df["pitcher"].map(peff).fillna(0.0).astype(float),
        (df["stand"] == "R").astype(float),
        (df["p_throws"] == "R").astype(float),
        df["balls"].astype(float),
        df["strikes"].astype(float),
        df["plate_x"].astype(float),
        df["plate_z"].astype(float),
        df["sz_top"].astype(float),
        df["sz_bot"].astype(float),
        in_zone,
    ]
    if candidate:
        cols += [df[c].astype(float) for c in CANDIDATE_COLS]
    return np.column_stack([np.asarray(c) for c in cols])


def _fit_predict(x_tr: np.ndarray, y_tr: np.ndarray,
                 x_ev: np.ndarray) -> np.ndarray:
    model = make_pipeline(StandardScaler(),
                          LogisticRegression(max_iter=1000))
    model.fit(x_tr, y_tr)
    return model.predict_proba(x_ev)[:, 1]


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-12, 1.0 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def catcher_cluster_p(loss_base: np.ndarray, loss_cand: np.ndarray,
                      catchers) -> Tuple[float, int]:
    """One-sided t-test on per-catcher mean loss improvement (base - cand)."""
    diff = pd.Series(loss_base - loss_cand).groupby(np.asarray(catchers)).mean()
    res = stats.ttest_1samp(diff.values, 0.0, alternative="greater")
    return float(res.pvalue), int(len(diff))


def _identity_feature(train: pd.DataFrame, ev: pd.DataFrame,
                      mu: float) -> Tuple[np.ndarray, np.ndarray]:
    """Identity-only control: train-year raw catcher mean rate, ONE feature."""
    rate = train.groupby("fielder_2")["y"].mean()
    return (train["fielder_2"].map(rate).fillna(mu).to_numpy(float)[:, None],
            ev["fielder_2"].map(rate).fillna(mu).to_numpy(float)[:, None])


def run_direction(train: pd.DataFrame, ev: pd.DataFrame,
                  with_control: bool = True) -> Dict:
    """Fit on train, evaluate held-out on ev. Frames need 'y' + 'game_date'."""
    train = train.sort_values("game_date", kind="stable")
    ceff, mu = shrunk_effects(train["fielder_2"], train["y"])
    peff, _ = shrunk_effects(train["pitcher"], train["y"])
    y_tr = np.asarray(train["y"], float)
    y_ev = np.asarray(ev["y"], float)
    p_base = _fit_predict(design_matrix(train, ceff, peff, False), y_tr,
                          design_matrix(ev, ceff, peff, False))
    p_cand = _fit_predict(design_matrix(train, ceff, peff, True), y_tr,
                          design_matrix(ev, ceff, peff, True))
    p_val, n_cl = catcher_cluster_p((p_base - y_ev) ** 2,
                                    (p_cand - y_ev) ** 2, ev["fielder_2"])
    base_b = brier(p_base, y_ev)
    out = {
        "base_brier": base_b, "cand_brier": brier(p_cand, y_ev),
        "base_logloss": logloss(p_base, y_ev),
        "cand_logloss": logloss(p_cand, y_ev),
        "p_catcher_cluster": p_val, "n_catcher_clusters": n_cl,
        "baseline_skillful": base_b < brier(np.full_like(y_ev, mu), y_ev),
        "n_eval": int(len(y_ev)),
        "effects_use_only_earlier":
            bool(train["game_date"].max() < ev["game_date"].min()),
    }
    if with_control:
        x_tr, x_ev = _identity_feature(train, ev, mu)
        ctrl_b = brier(_fit_predict(x_tr, y_tr, x_ev), y_ev)
        out["control_brier"] = ctrl_b
        out["control_loses"] = ctrl_b > base_b
    return out


def direction_pass(r: Dict, eps: float = EPS) -> bool:
    return (r["cand_brier"] < r["base_brier"]
            and r["p_catcher_cluster"] < eps
            and r["baseline_skillful"])


def _permute_candidate(df: pd.DataFrame, rng: np.random.Generator):
    out = df.copy()
    for c in CANDIDATE_COLS:
        out[c] = rng.permutation(out[c].values)
    return out


def run_prereg(corpus_a: pd.DataFrame, corpus_b: pd.DataFrame,
               rng: np.random.Generator,
               n_null_seeds: int = N_NULL_SEEDS) -> Dict:
    """Full pre-registered gate: directions, identity control, planted null.

    CONTROL_FAIL is a hard fail (never PASS): the identity-only control must
    lose to the shrunk fixed-effects baseline on the eval year, both ways.
    """
    real = [run_direction(corpus_a, corpus_b),
            run_direction(corpus_b, corpus_a)]
    null, null_pass = [], False
    for _ in range(n_null_seeds):
        a0 = _permute_candidate(corpus_a, rng)
        b0 = _permute_candidate(corpus_b, rng)
        pair = [run_direction(a0, b0, with_control=False),
                run_direction(b0, a0, with_control=False)]
        null.extend(pair)
        null_pass = null_pass or all(direction_pass(r) for r in pair)
    control_ok = all(r["control_loses"] for r in real)
    real_pass = all(direction_pass(r) for r in real)
    if not control_ok:
        verdict = "CONTROL_FAIL"
    elif real_pass and not null_pass:
        verdict = "PASS"
    else:
        verdict = "REJECT"
    return {
        "verdict": verdict, "directions": real, "planted_null": null,
        "control_ok": control_ok, "n_null_seeds": n_null_seeds,
        "eps": EPS, "k_tests": K_TESTS,
    }


def load_corpus(year: int, root: str = STATCAST_ROOT) -> pd.DataFrame:
    path = os.path.join(root, "savant_full__%d.parquet" % year)
    df = pd.read_parquet(path,
                         columns=BASE_REQUIRED + list(CANDIDATE_COLS))
    df = df[df["description"].isin(TAKEN_DESCRIPTIONS)].copy()
    df["y"] = (df["description"] == "called_strike").astype(float)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.dropna(subset=["plate_x", "plate_z", "sz_top", "sz_bot",
                           "game_date"] + list(CANDIDATE_COLS))
    return df.reset_index(drop=True)


def readiness(root: str = STATCAST_ROOT) -> Dict[int, list]:
    """Per-corpus missing requirements. Empty lists everywhere == READY."""
    import pyarrow.parquet as pq
    missing: Dict[int, list] = {}
    for year in (2023, 2024):
        path = os.path.join(root, "savant_full__%d.parquet" % year)
        if not os.path.exists(path):
            missing[year] = ["<file absent: %s>" % path]
            continue
        names = set(pq.read_schema(path).names)
        missing[year] = [c for c in BASE_REQUIRED + list(CANDIDATE_COLS)
                         if c not in names]
    return missing


def main() -> int:
    miss = readiness()
    if any(miss.values()):
        print("VERDICT: NOT_TESTABLE")
        for year in sorted(miss):
            print("  corpus %d missing columns: %s" % (year, miss[year]))
        print("Label/baseline side is READY (0 additional download).")
        print("Gap = CV teacher output: run command_meter.py over catcher-")
        print("side broadcast clips (>=400 confident-target taken pitches")
        print("per corpus, two broadcasts each, 2023 + 2024), derive the")
        print("command_* columns, join to Statcast by game identity.")
        print("Scoped clips keep acquisition under 100MB; no Statcast dl.")
        return 0
    rng = np.random.default_rng(20260901)
    result = run_prereg(load_corpus(2023), load_corpus(2024), rng)
    print("VERDICT: %s (eps=%.3f per test, K=%d Bonferroni)"
          % (result["verdict"], result["eps"], result["k_tests"]))
    labels = ["2023->2024", "2024->2023"]
    for name, r in zip(labels, result["directions"]):
        print("  %s base_brier=%.5f cand_brier=%.5f base_ll=%.5f "
              "cand_ll=%.5f p=%.2e clusters=%d skillful=%s n=%d"
              % (name, r["base_brier"], r["cand_brier"], r["base_logloss"],
                 r["cand_logloss"], r["p_catcher_cluster"],
                 r["n_catcher_clusters"], r["baseline_skillful"], r["n_eval"]))
        print("    control_brier=%.5f control_loses=%s earlier_only=%s"
              % (r["control_brier"], r["control_loses"],
                 r["effects_use_only_earlier"]))
    for i, r in enumerate(result["planted_null"]):
        print("  planted-null seed%d %s cand_brier=%.5f p=%.2e pass=%s"
              % (i // 2, labels[i % 2], r["cand_brier"],
                 r["p_catcher_cluster"], direction_pass(r)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
