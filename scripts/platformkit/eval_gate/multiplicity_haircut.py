"""S675 multiplicity haircut + trial-count table over archived per-game paired-loss series.

REPORT-ONLY. Every arm's ``sealed_verdict`` is copied through untouched; the haircut label is a
separate column and never replaces a sealed verdict. Calibration language only: a BETTER label
means "lower loss than the benchmark after family-wise control", never a claim about any market.

Sign convention (eval gate): diff = loss_benchmark - loss_candidate, positive favors the candidate.
An arm with no archived series is NOT_EVALUABLE: it gets no p-value and consumes no K.
Reuses romano_wolf.romano_wolf_stepdown, spa_test.hansen_spa, deflated_metrics.expected_max_z and
ledger.load_fwer read-only; none of those modules is edited.
"""
from __future__ import annotations

import csv
import math
from datetime import datetime
from numbers import Integral, Real
from typing import Optional, Sequence

import numpy as np
from scipy import stats

from scripts.platformkit.eval_gate.deflated_metrics import expected_max_z
from scripts.platformkit.eval_gate.romano_wolf import romano_wolf_stepdown
from scripts.platformkit.eval_gate.spa_test import game_cluster_matrix, hansen_spa

BETTER, NOT_SEPARATED, NOT_EVALUABLE = "BETTER", "NOT_SEPARATED", "NOT_EVALUABLE"
SHARPE_LIKE = "sharpe_like"


def load_paired_series(path: str, cluster_col: str, base_col: str, model_col: str) -> dict:
    """Read a Q9 paired-loss CSV; diff = base - model per row (positive favors the model).

    The two loss columns are read directly; any stored differential column is ignored because
    its sign convention varies by producer (S202 stores model - base). A requested column that
    appears more than once in the header is refused rather than guessed.
    """
    diffs, ids = [], []
    with open(path, encoding="ascii", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        cols = []
        for name in (cluster_col, base_col, model_col):
            if header.count(name) != 1:
                raise ValueError("column %r must appear exactly once in the header" % name)
            cols.append(header.index(name))
        for row in reader:
            if not row:
                continue
            ids.append(row[cols[0]])
            diffs.append(float(row[cols[1]]) - float(row[cols[2]]))
    return {"diffs": diffs, "game_ids": ids, "source": path, "header": header}


def holm(p_values: Sequence[float]) -> list:
    """Holm step-down adjusted p-values (monotone, capped at 1.0)."""
    p = np.asarray(p_values, dtype=float)
    m = len(p)
    adjusted = np.ones(m, dtype=float)
    running = 0.0
    for rank, index in enumerate(np.argsort(p, kind="stable")):
        running = max(running, min(1.0, (m - rank) * float(p[index])))
        adjusted[index] = running
    return [float(x) for x in adjusted]


def _one_sided_p(game_means: np.ndarray) -> float:
    """One-sided game-cluster t p (H1: mean diff > 0), df = n_games - 1; zero variance -> 1.0."""
    n = len(game_means)
    if np.all(game_means == game_means[0]):
        return 1.0
    sd = float(np.std(game_means, ddof=1))
    if not math.isfinite(sd) or sd <= 0.0:
        return 1.0
    return float(stats.t.sf(math.sqrt(n) * float(np.mean(game_means)) / sd, df=n - 1))


def _game_means(diffs: Sequence[float], game_ids: Sequence) -> Optional[np.ndarray]:
    if len(diffs) != len(game_ids) or len(set(game_ids)) < 2:
        return None
    return game_cluster_matrix([list(diffs)], [list(game_ids)])[0]


def haircut(arms: Sequence[dict], *, alpha: float = 0.05, n_bootstrap: int = 999,
            seed: int = 2718, mean_block_length: float = 5.0) -> dict:
    """Family-wise report for one family of arms; each arm is {name, diffs, game_ids, ...}.

    Label BETTER iff the SPA family p, the arm's Holm p and its Romano-Wolf p are all <= alpha
    (an intersection of level-alpha tests, so its family-wise error is <= the smallest of the
    three). Holm and Romano-Wolf use K = K_evaluable. Arms on different game sets get Holm and
    Romano-Wolf per arm, the SPA line NOT_EVALUABLE, and label NOT_SEPARATED (never an error).
    """
    rows, live, means = [], [], []
    constant = set()
    for arm in arms:
        rows.append({"name": arm["name"], "sealed_verdict": arm.get("sealed_verdict"),
                     "n_games": None, "mean_diff": None, "raw_p": None, "holm_p": None,
                     "romano_wolf_p": None, "label": NOT_EVALUABLE})
        gm = None
        if arm.get("diffs") is not None and arm.get("game_ids") is not None:
            values = np.asarray(arm["diffs"], dtype=float)
            if values.size and np.isfinite(values).all() and np.all(values == values[0]):
                constant.add(len(rows) - 1)
            gm = _game_means(arm["diffs"], arm["game_ids"])
        if gm is not None:
            live.append(len(rows) - 1)
            means.append(gm)
    family = {"k_declared": len(rows), "k_evaluable": len(live), "alpha": alpha,
              "n_bootstrap": int(n_bootstrap), "seed": int(seed),
              "mean_block_length": float(mean_block_length), "spa_family_p": None,
              "spa_status": NOT_EVALUABLE, "aligned": None,
              "label_rule": "BETTER iff spa_family_p, holm_p, romano_wolf_p all <= alpha"}
    if not live:
        return {"family": family, "arms": rows}
    diffs = [list(arms[i]["diffs"]) for i in live]
    ids = [list(arms[i]["game_ids"]) for i in live]
    aligned = all(set(g) == set(ids[0]) for g in ids)
    family["aligned"] = aligned
    raw = [1.0 if i in constant else _one_sided_p(m) for i, m in zip(live, means)]
    adj_holm = holm(raw)
    rw = romano_wolf_stepdown(diffs, ids, alpha=alpha, n_bootstrap=n_bootstrap, seed=seed,
                              mean_block_length=mean_block_length)
    spa_p = None
    if aligned:
        spa_p = hansen_spa(diffs, ids, alpha=alpha, n_bootstrap=n_bootstrap, seed=seed,
                           mean_block_length=mean_block_length).family_p
        family.update({"spa_family_p": spa_p, "spa_status": "EVALUATED"})
    for j, i in enumerate(live):
        mean = float(means[j].mean())
        ok = (spa_p is not None and spa_p <= alpha and adj_holm[j] <= alpha
              and rw.adjusted_p[j] <= alpha and mean > 0.0)
        rows[i].update({"n_games": int(len(means[j])), "mean_diff": mean, "raw_p": raw[j],
                        "holm_p": adj_holm[j], "romano_wolf_p": float(rw.adjusted_p[j]),
                        "label": BETTER if ok else NOT_SEPARATED})
    return {"family": family, "arms": rows}


def deflate(metric_kind: str, ratio: Optional[float] = None, n_obs: Optional[int] = None,
            k: Optional[int] = None, sd_trials: Optional[float] = None,
            skew: float = 0.0, kurtosis: float = 3.0) -> dict:
    """Deflate a Sharpe-like mean/sd ratio for K trials; every other metric is NOT_APPLICABLE.

    Loss metrics (brier, log_loss) are never deflated. For metric_kind "sharpe_like":
      r0 = sd_trials * E[max of K iid N(0,1)]            (deflated_metrics.expected_max_z)
      z  = (ratio - r0) * sqrt(n_obs - 1) / sqrt(1 - skew*ratio + (kurtosis - 1)/4 * ratio^2)
      deflated_p = 1 - Phi(z)
    Missing or invalid parameters are NOT_EVALUABLE: nothing is defaulted.
    """
    if metric_kind != SHARPE_LIKE:
        return {"metric_kind": metric_kind, "status": "NOT_APPLICABLE"}
    if ratio is None or n_obs is None or k is None or sd_trials is None:
        return {"metric_kind": metric_kind, "status": NOT_EVALUABLE}
    if any(isinstance(v, bool) or not isinstance(v, Integral) for v in (n_obs, k)):
        return {"metric_kind": metric_kind, "status": NOT_EVALUABLE}
    if n_obs < 2 or k < 1:
        return {"metric_kind": metric_kind, "status": NOT_EVALUABLE}
    if any(isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v)
           for v in (ratio, sd_trials, skew, kurtosis)) or sd_trials < 0.0:
        return {"metric_kind": metric_kind, "status": NOT_EVALUABLE}
    r0 = float(sd_trials) * expected_max_z(k)
    denom = 1.0 - skew * ratio + (kurtosis - 1.0) / 4.0 * ratio * ratio
    if not math.isfinite(r0) or not math.isfinite(denom) or denom <= 0.0:
        return {"metric_kind": metric_kind, "status": NOT_EVALUABLE}
    z = (ratio - r0) * math.sqrt(n_obs - 1) / math.sqrt(denom)
    return {"metric_kind": metric_kind, "status": "DEFLATED", "k": int(k),
            "benchmark_ratio": r0, "deflated_p": float(stats.norm.sf(z))}


def _aware(value: str) -> datetime:
    stamp = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if stamp.tzinfo is None:
        raise ValueError("timestamp %r has no timezone" % value)
    return stamp


def trial_count_table(rows: Sequence[dict], launch_at: Optional[str] = None) -> dict:
    """Report-only charged-trial counts from ledger.load_fwer rows; never writes any ledger.

    Per-family K = COUNT of rows whose family resolves (family_bars.resolve_family) to it, the
    S89/S134 rule of ledger.next_k_family. Rows with no family group as sport|predictor. The
    global max k_cumulative is reported separately. k_at_launch counts rows with at <= launch_at,
    both parsed as timezone-aware datetimes (Q2: K read at launch); naive values are refused.
    """
    # Lazy, as in ledger.next_k_family: family_bars pulls statsmodels at import time.
    from scripts.platformkit.eval_gate.family_bars import resolve_family

    groups: dict = {}
    for r in rows:
        fam = resolve_family(r.get("family")) if r.get("family") is not None else None
        key = ("family:%s" % fam) if fam is not None else "%s|%s" % (r.get("sport"), r.get("predictor"))
        g = groups.setdefault(key, {"group": key, "k": 0, "first_at": None, "last_at": None})
        g["k"] += 1
        if r.get("at") is not None:
            at = _aware(r["at"])
            g["first_at"] = r["at"] if g["first_at"] is None or at < _aware(g["first_at"]) else g["first_at"]
            g["last_at"] = r["at"] if g["last_at"] is None or at > _aware(g["last_at"]) else g["last_at"]
    kcs = [r["k_cumulative"] for r in rows if r.get("k_cumulative") is not None]
    k_launch = None
    if launch_at is not None:
        cut = _aware(launch_at)
        k_launch = sum(1 for r in rows if r.get("at") is not None and _aware(r["at"]) <= cut)
    return {"k_total_rows": len(rows), "max_k_cumulative": max(kcs) if kcs else None,
            "k_at_launch": k_launch, "launch_at": launch_at,
            "groups": sorted(groups.values(), key=lambda g: g["group"])}


__all__ = ["BETTER", "NOT_SEPARATED", "NOT_EVALUABLE", "SHARPE_LIKE", "load_paired_series",
           "holm", "haircut", "deflate", "trial_count_table"]
