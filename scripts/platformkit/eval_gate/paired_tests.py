"""S688: game-level Diebold-Mariano with the Harvey-Leybourne-Newbold correction.

Report-only evaluation tooling. Calibration language only: a positive mean says the
candidate forecast has the LOWER mean loss (Brier / log loss) on the games scored; it
is never a statement about money.

Why a second DM beside eval_gate/dm_test.py: dm_test weights every STATE equally and
uses a cluster-sum (CR1) variance. When a few long games carry most of the variance,
that test is oversized (S688 spec PREMISE: 0.267 rejections at nominal 0.05 with 15
games). Here each game is first reduced to its mean loss differential dbar_g, and the
textbook DM statistic is computed on that G-long series with the HLN small-sample
factor and Student t(G-1) reference. The estimand is the GAME-WEIGHTED mean loss
differential; every result names it.

  d_i    = loss_ref_i - loss_cand_i          (positive => candidate lower loss)
  dbar_g = mean of d over game g's rows      (first-appearance game order)
  gamma_k = (1/T) sum_{t>k} (x_t - xbar)(x_{t-k} - xbar)
  V      = (gamma_0 + 2 sum_{k=1}^{h-1} gamma_k) / T
  DM     = xbar / sqrt(V);  HLN = DM * sqrt((T + 1 - 2h + h(h-1)/T) / T)
For h = 1, HLN equals the one-sample t statistic on dbar_g.

CLI (report-only, strict JSON on stdout):
  python -m scripts.platformkit.eval_gate.paired_tests --csv rows.csv \
      [--reliability-csv py.csv] [--draws 2000] [--seed 688]
  rows.csv: game_id, loss_ref, loss_cand; py.csv: p, y (adds CORP + decompositions)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from typing import Any, Sequence

import numpy as np
from scipy import stats

ESTIMAND = "game-weighted mean of (loss_ref - loss_cand); positive => candidate lower loss"
WIDTH_GAP_FLAG_PCT = 25.0
VAR_REL_TOL = 1e-12


def _finite(name: str, values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains a non-finite value")
    return arr


def game_means(loss_ref: Sequence[float], loss_cand: Sequence[float],
               game_ids: Sequence[Any]) -> tuple[list, np.ndarray, list[int]]:
    """Per-game mean loss differential, games in first-appearance order.

    Returns (game ids, dbar_g array, rows per game).
    """
    ref = _finite("loss_ref", loss_ref)
    cand = _finite("loss_cand", loss_cand)
    ids = list(game_ids)
    if not (len(ref) == len(cand) == len(ids)):
        raise ValueError("loss_ref, loss_cand and game_ids must have equal length")
    sums: dict = {}
    counts: dict = {}
    for gid, diff in zip(ids, ref - cand):
        if gid is None or (isinstance(gid, str) and not gid.strip()):
            raise ValueError("game_id must be present and non-blank")
        if gid not in sums:
            sums[gid] = 0.0
            counts[gid] = 0
        sums[gid] += float(diff)
        counts[gid] += 1
    order = list(sums)
    dbar = np.array([sums[g] / counts[g] for g in order], dtype=float)
    return order, dbar, [counts[g] for g in order]


def dm_hln(series: Sequence[float], h: int = 1) -> dict:
    """Textbook DM (rectangular window, h-1 lags) plus the HLN correction."""
    x = _finite("series", series)
    if not isinstance(h, int) or isinstance(h, bool) or h < 1:
        raise ValueError("h must be an int >= 1")
    t_len = len(x)
    out: dict = {"T": t_len, "h": h, "df": t_len - 1, "mean": None, "dm": None,
                 "hln": None, "p_value": None, "se": None, "ci95": None}
    if t_len < 2:
        return dict(out, status="INSUFFICIENT")
    factor_sq = (t_len + 1 - 2 * h + h * (h - 1) / t_len) / t_len
    if h > t_len - 1 or not factor_sq > 0.0:
        return dict(out, status="INSUFFICIENT", mean=float(x.mean()))
    xbar = float(x.mean())
    e = x - xbar
    gammas = [float(e[k:] @ e[:t_len - k]) / t_len for k in range(h)]
    var = (gammas[0] + 2.0 * sum(gammas[1:])) / t_len
    out["mean"] = xbar
    # float-residue guard: a constant series leaves gamma_0 ~ 1e-33, not 0
    if not var > VAR_REL_TOL * (xbar * xbar + gammas[0]) / t_len:
        return dict(out, status="NONPOSITIVE_VARIANCE")
    dm = xbar / math.sqrt(var)
    hln = dm * math.sqrt(factor_sq)
    se = math.sqrt(var / factor_sq)          # hln == xbar / se; defined at xbar == 0
    crit = float(stats.t.ppf(0.975, t_len - 1))
    p_value = float(2.0 * stats.t.sf(abs(hln), t_len - 1))
    return dict(out, status="OK", dm=dm, hln=hln, p_value=p_value, se=se,
                ci95=[xbar - crit * se, xbar + crit * se])


def game_level_dm(loss_ref: Sequence[float], loss_cand: Sequence[float],
                  game_ids: Sequence[Any]) -> dict:
    """dm_hln(h=1) on the per-game mean differential series (the S688 statistic).

    h is fixed at 1: games in first-appearance order are exchangeable, so a
    lag window would make the answer depend on row order.
    """
    order, dbar, sizes = game_means(loss_ref, loss_cand, game_ids)
    res = dm_hln(dbar, h=1)
    res.update(estimand=ESTIMAND, n_games=len(order), n_rows=int(sum(sizes)),
               game_means=[float(v) for v in dbar])
    return res


def game_bootstrap_ci(dbar: Sequence[float], draws: int = 2000, seed: int = 688) -> dict:
    """Percentile 95 pct interval of the game-weighted mean, resampling games."""
    x = _finite("dbar", dbar)
    if len(x) < 2 or draws < 1:
        return {"status": "INSUFFICIENT", "ci95": None, "draws": draws, "seed": seed}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(draws, len(x)))
    means = x[idx].mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return {"status": "OK", "ci95": [float(lo), float(hi)], "draws": draws, "seed": seed}


def _sign(lo: float, hi: float) -> int:
    return 1 if lo > 0 else (-1 if hi < 0 else 0)


def compare_to_bootstrap(dm_result: dict, boot: dict) -> dict:
    """Sign agreement (interval excludes 0 on the same side, or both straddle)
    and width_gap_pct = |w_boot - w_hln| / w_hln * 100 (flag above 25 pct)."""
    if dm_result.get("status") != "OK" or boot.get("status") != "OK":
        return {"status": "INSUFFICIENT", "sign_agree": None, "width_gap_pct": None,
                "flag": None}
    dlo, dhi = dm_result["ci95"]
    blo, bhi = boot["ci95"]
    bw = bhi - blo
    dw = dhi - dlo
    gap = 100.0 * abs(bw - dw) / dw
    flag = gap > WIDTH_GAP_FLAG_PCT
    return {"status": "OK", "sign_agree": _sign(dlo, dhi) == _sign(blo, bhi),
            "sign_hln": _sign(dlo, dhi), "sign_boot": _sign(blo, bhi),
            "width_hln": dw, "width_boot": bw, "width_gap_pct": gap,
            "flag": ("WIDTH_GAP_OVER_25PCT" if flag else "WITHIN_25PCT")}


def _read_csv(path: str, cols: Sequence[str]) -> list[list[str]]:
    with open(path, newline="", encoding="ascii") as fh:
        reader = csv.DictReader(fh)
        for col in cols:
            if reader.fieldnames is None or reader.fieldnames.count(col) != 1:
                raise ValueError(f"CSV column {col} must occur exactly once")
        return [[row[c] for c in cols] for row in reader]


def _json_safe(obj: Any) -> Any:
    """Non-finite floats become null so strict parsers accept the report."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def build_report(rows: Sequence[Sequence[str]], draws: int = 2000, seed: int = 688,
                 rel_rows: Sequence[Sequence[str]] | None = None, bins: int = 10) -> dict:
    """The CLI report: game-level DM/HLN, the game bootstrap and their comparison;
    with rel_rows (p, y) also CORP and both Brier decompositions."""
    ids = [r[0] for r in rows]
    res = game_level_dm([float(r[1]) for r in rows], [float(r[2]) for r in rows], ids)
    boot = game_bootstrap_ci(res["game_means"], draws=draws, seed=seed)
    report = {"row": "S688", "report_only": True, "estimand": ESTIMAND,
              "dm_hln": res, "bootstrap": boot, "compare": compare_to_bootstrap(res, boot)}
    if rel_rows is not None:
        from scripts.platformkit.eval_gate.reliability_corp import brier_decomposition, corp
        p = [float(r[0]) for r in rel_rows]
        y = [float(r[1]) for r in rel_rows]
        report["corp"] = corp(p, y)
        report["brier_decomposition"] = brier_decomposition(p, y, bins=bins)
    return _json_safe(report)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="S688 game-level DM/HLN (report-only)")
    ap.add_argument("--csv", required=True, help="columns game_id, loss_ref, loss_cand")
    ap.add_argument("--reliability-csv", default=None, help="columns p, y")
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=688)
    a = ap.parse_args(argv)
    rows = _read_csv(a.csv, ("game_id", "loss_ref", "loss_cand"))
    rel = _read_csv(a.reliability_csv, ("p", "y")) if a.reliability_csv else None
    report = build_report(rows, draws=a.draws, seed=a.seed, rel_rows=rel)
    json.dump(report, sys.stdout, allow_nan=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
