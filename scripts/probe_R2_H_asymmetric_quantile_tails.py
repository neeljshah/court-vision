"""probe_R2_H_asymmetric_quantile_tails.py -- improve_loop R2-H (loop 5).

CALIBRATION probe. Asymmetric quantile bands for count stats.

ANGLE: The current live_quantile_bands uses a symmetric half-width
(scale * sigma * Z80) for all stats, even the four skewed count stats
(fg3m, stl, blk, tov). Because those distributions are right-skewed,
the lower tail is over-covered (too wide) and the upper tail is under-
covered. This probe fits per-stat (sigma_lo, sigma_hi) from one-sided
empirical residual quantiles on the train half and checks whether the
resulting asymmetric bands produce target one-sided coverage on the val half.

Evaluation: two snapshot points (endQ2 AND endQ3), four count stats only.

Ship gate (each stat at BOTH snapshot points):
    cov_lo_treat in [0.08, 0.12]   (target 0.10 -- 10% below q10)
    cov_hi_treat in [0.08, 0.12]   (target 0.10 -- 10% above q90)
    cov80_treat  in [0.78, 0.82]   (target 0.80 -- within-band)

JSON schema: scripts/_results/improve_R2_H_asymmetric_quantile_tails.json
  name, n_games_train, n_games_val, Z80,
  sigma_params: {endQ2: {stat: {sigma_lo, sigma_hi}}, endQ3: {...}},
  per_stat: [
    {stat, point, n_val,
     cov_lo_base, cov_hi_base, cov80_base,
     cov_lo_treat, cov_hi_treat, cov80_treat,
     gate_lo, gate_hi, gate_80}
  ],
  ship, ship_reason

Run:
    python scripts/probe_R2_H_asymmetric_quantile_tails.py [--max-games N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (PROJECT_DIR, os.path.join(PROJECT_DIR, "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import retro_inplay_mae as rim  # noqa: E402
from src.prediction.live_quantile_bands import (  # noqa: E402
    ASYMMETRIC_STATS,
    _Z80,
    load_calibration,
)

# ── constants ──────────────────────────────────────────────────────────────────

COUNT_STATS = ("fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS = ("endQ2", "endQ3")
_OUT_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")

# One-sided tail targets
_TARGET_LO = 0.10  # fraction BELOW q10_treat
_TARGET_HI = 0.10  # fraction ABOVE q90_treat
_TARGET_80 = 0.80  # fraction inside [q10_treat, q90_treat]
_GATE_LO_LO, _GATE_LO_HI = 0.08, 0.12
_GATE_HI_LO, _GATE_HI_HI = 0.08, 0.12
_GATE_80_LO, _GATE_80_HI = 0.78, 0.82

# Z-score for 80th one-sided quantile used to convert empirical q80(|r|) -> sigma
_Z_P80 = 1.2816  # same as _Z80


# ── corpus collection ──────────────────────────────────────────────────────────

def collect_corpus(max_games: int) -> Tuple[
    Dict[str, Dict[str, List[float]]],   # q50s[point][stat]
    Dict[str, Dict[str, List[float]]],   # q10s[point][stat]  (baseline)
    Dict[str, Dict[str, List[float]]],   # q90s[point][stat]  (baseline)
    Dict[str, Dict[str, List[float]]],   # acts[point][stat]
    List[str],                           # ordered game_ids
]:
    """For each snapshot point, collect (q50, q10_base, q90_base, actual)
    tuples for the four count stats by calling project_from_snapshot which
    returns pre-attached q10/q90 bands when _INCLUDE_QUANTILE_BANDS=True.
    """
    from src.prediction.live_quantile_bands import project_from_snapshot_with_bands

    qstats = rim.load_quarter_stats()
    all_gids = sorted(qstats["game_id"].unique().tolist())
    if max_games:
        all_gids = all_gids[:max_games]

    # Initialise accumulator
    q50s: Dict[str, Dict[str, List[float]]] = {pt: {s: [] for s in COUNT_STATS}
                                                for pt in SNAPSHOT_POINTS}
    q10s: Dict[str, Dict[str, List[float]]] = {pt: {s: [] for s in COUNT_STATS}
                                                for pt in SNAPSHOT_POINTS}
    q90s: Dict[str, Dict[str, List[float]]] = {pt: {s: [] for s in COUNT_STATS}
                                                for pt in SNAPSHOT_POINTS}
    acts: Dict[str, Dict[str, List[float]]] = {pt: {s: [] for s in COUNT_STATS}
                                                for pt in SNAPSHOT_POINTS}

    ordered_gids: List[str] = []
    n_ok = 0
    for gid in all_gids:
        game_actuals = rim.actuals_for_game(gid, qstats)
        if not game_actuals:
            continue

        any_point_ok = False
        for point in SNAPSHOT_POINTS:
            snap = rim.build_snapshot(gid, point, qstats)
            if snap is None:
                continue
            try:
                rows = project_from_snapshot_with_bands(snap)
            except Exception:
                continue

            for r in rows:
                stat = r.get("stat")
                if stat not in COUNT_STATS:
                    continue
                pid = r.get("player_id")
                if pid is None:
                    continue
                actual = game_actuals.get((int(pid), stat))
                if actual is None:
                    continue
                try:
                    q50v = float(r.get("q50") or r.get("projected_final") or 0.0)
                    q10v = float(r.get("q10", 0.0) or 0.0)
                    q90v = float(r.get("q90", q50v) or q50v)
                except (TypeError, ValueError):
                    continue
                q50s[point][stat].append(q50v)
                q10s[point][stat].append(q10v)
                q90s[point][stat].append(q90v)
                acts[point][stat].append(float(actual))
            any_point_ok = True

        if any_point_ok:
            ordered_gids.append(gid)
            n_ok += 1
            if n_ok % 100 == 0:
                print(f"  [corpus] {n_ok}/{len(all_gids)}", flush=True)

    print(f"  [corpus] done: {n_ok} games processed", flush=True)
    return q50s, q10s, q90s, acts, ordered_gids


# ── train/val split ────────────────────────────────────────────────────────────

def split_arrays(
    q50s: Dict[str, Dict[str, List[float]]],
    q10s: Dict[str, Dict[str, List[float]]],
    q90s: Dict[str, Dict[str, List[float]]],
    acts: Dict[str, Dict[str, List[float]]],
) -> Tuple[
    Dict[str, Dict[str, np.ndarray]],
    Dict[str, Dict[str, np.ndarray]],
    Dict[str, Dict[str, np.ndarray]],
    Dict[str, Dict[str, np.ndarray]],
    Dict[str, Dict[str, np.ndarray]],
    Dict[str, Dict[str, np.ndarray]],
    Dict[str, Dict[str, np.ndarray]],
    Dict[str, Dict[str, np.ndarray]],
]:
    """Chronological 50/50 split. Returns (tr_q50, tr_q10, tr_q90, tr_acts,
    va_q50, va_q10, va_q90, va_acts) each as {point: {stat: ndarray}}."""
    def _half(lst: List[float], first: bool) -> np.ndarray:
        n = len(lst)
        arr = np.array(lst, dtype=float)
        mid = n // 2
        return arr[:mid] if first else arr[mid:]

    tr_q50 = {pt: {s: _half(q50s[pt][s], True) for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    tr_q10 = {pt: {s: _half(q10s[pt][s], True) for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    tr_q90 = {pt: {s: _half(q90s[pt][s], True) for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    tr_act = {pt: {s: _half(acts[pt][s], True) for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    va_q50 = {pt: {s: _half(q50s[pt][s], False) for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    va_q10 = {pt: {s: _half(q10s[pt][s], False) for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    va_q90 = {pt: {s: _half(q90s[pt][s], False) for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    va_act = {pt: {s: _half(acts[pt][s], False) for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    return tr_q50, tr_q10, tr_q90, tr_act, va_q50, va_q10, va_q90, va_act


# ── fit asymmetric sigmas on train half ────────────────────────────────────────

def fit_sigma_params(
    tr_q50: Dict[str, Dict[str, np.ndarray]],
    tr_act: Dict[str, Dict[str, np.ndarray]],
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Return {point: {stat: {sigma_lo, sigma_hi}}} fitted on train half.

    sigma_lo = quantile(|r[r<0]|, 0.80) / Z80
    sigma_hi = quantile( r[r>0],  0.80) / Z80
    """
    params: Dict[str, Dict[str, Dict[str, float]]] = {}
    for pt in SNAPSHOT_POINTS:
        params[pt] = {}
        for s in COUNT_STATS:
            q50 = tr_q50[pt][s]
            act = tr_act[pt][s]
            if len(q50) < 10:
                params[pt][s] = {"sigma_lo": 0.5, "sigma_hi": 1.0}
                continue
            r = act - q50
            neg = np.abs(r[r < 0])
            pos = r[r > 0]
            sigma_lo = float(np.quantile(neg, 0.80)) / _Z_P80 if len(neg) >= 5 else 0.5
            sigma_hi = float(np.quantile(pos, 0.80)) / _Z_P80 if len(pos) >= 5 else 1.0
            params[pt][s] = {"sigma_lo": round(sigma_lo, 6), "sigma_hi": round(sigma_hi, 6)}
            print(f"  [fit] {pt}/{s}: sigma_lo={sigma_lo:.4f}  sigma_hi={sigma_hi:.4f}  "
                  f"n_neg={len(neg)}  n_pos={len(pos)}", flush=True)
    return params


# ── coverage metrics ───────────────────────────────────────────────────────────

def compute_coverage(
    q50: np.ndarray, q10: np.ndarray, q90: np.ndarray, act: np.ndarray
) -> Tuple[float, float, float]:
    """Returns (cov_lo, cov_hi, cov80) for a set of (q50, q10, q90, actual) arrays.

    cov_lo  = fraction of actuals BELOW q10 (i.e. r < q10 - q50 expressed as
              fraction of total; we compare act < q10 directly)
    cov_hi  = fraction of actuals ABOVE q90
    cov80   = fraction inside [q10, q90]
    """
    if len(act) == 0:
        return float("nan"), float("nan"), float("nan")
    cov_lo = float((act < q10).mean())
    cov_hi = float((act > q90).mean())
    cov80 = float(((act >= q10) & (act <= q90)).mean())
    return cov_lo, cov_hi, cov80


# ── build treatment bands ──────────────────────────────────────────────────────

def build_treat_bands(
    q50: np.ndarray,
    sigma_params: Dict[str, float],
) -> Tuple[np.ndarray, np.ndarray]:
    """q10_new = max(0, q50 - sigma_lo * Z80),  q90_new = q50 + sigma_hi * Z80."""
    half_lo = sigma_params["sigma_lo"] * _Z80
    half_hi = sigma_params["sigma_hi"] * _Z80
    q10_new = np.maximum(0.0, q50 - half_lo)
    q90_new = q50 + half_hi
    return q10_new, q90_new


# ── result schema ─────────────────────────────────────────────────────────────

@dataclass
class R2HResult:
    name: str
    n_games_train: int
    n_games_val: int
    Z80: float
    sigma_params: Dict  # {point: {stat: {sigma_lo, sigma_hi}}}
    per_stat: List[Dict] = field(default_factory=list)
    ship: bool = False
    ship_reason: str = ""

    def to_md(self) -> str:
        lines = [
            f"# probe {self.name} -- improve_loop (CALIBRATION)",
            "",
            f"**Games:** train={self.n_games_train}  val={self.n_games_val}  "
            f"Z80={self.Z80}",
            "",
            "## Fitted sigma parameters",
            "",
            "| point | stat | sigma_lo | sigma_hi |",
            "|-------|------|----------|----------|",
        ]
        for pt in SNAPSHOT_POINTS:
            for s in COUNT_STATS:
                p = self.sigma_params.get(pt, {}).get(s, {})
                lines.append(f"| {pt} | {s} | "
                              f"{p.get('sigma_lo', float('nan')):.4f} | "
                              f"{p.get('sigma_hi', float('nan')):.4f} |")
        lines += [
            "",
            "## One-sided tail coverage (val half)",
            "",
            "| stat | point | n | cov_lo_base | cov_hi_base | cov80_base "
            "| cov_lo_treat | cov_hi_treat | cov80_treat "
            "| gate_lo | gate_hi | gate_80 |",
            "|------|-------|---|-------------|-------------|------------|"
            "--------------|--------------|-------------|---------|---------|---------|",
        ]
        def _f(v):
            return f"{v:.3f}" if isinstance(v, float) and v == v else "nan"
        def _ok(b):
            return "PASS" if b else "FAIL"
        for r in self.per_stat:
            lines.append(
                f"| {r['stat']} | {r['point']} | {r['n_val']} "
                f"| {_f(r['cov_lo_base'])} | {_f(r['cov_hi_base'])} | {_f(r['cov80_base'])} "
                f"| {_f(r['cov_lo_treat'])} | {_f(r['cov_hi_treat'])} | {_f(r['cov80_treat'])} "
                f"| {_ok(r['gate_lo'])} | {_ok(r['gate_hi'])} | {_ok(r['gate_80'])} |"
            )
        lines += [
            "",
            "## Verdict",
            "",
            f"- **{'SHIP' if self.ship else 'REJECT'}**: {self.ship_reason}",
        ]
        return "\n".join(lines) + "\n"


# ── main probe ────────────────────────────────────────────────────────────────

def run_probe(max_games: int = 0) -> R2HResult:
    name = "R2_H_asymmetric_quantile_tails"
    print(f"[{name}] collecting corpus...", flush=True)
    q50s, q10s, q90s, acts, gids = collect_corpus(max_games)

    print(f"[{name}] splitting train/val (50/50 chronological)...", flush=True)
    tr_q50, tr_q10, tr_q90, tr_act, va_q50, va_q10, va_q90, va_act = split_arrays(
        q50s, q10s, q90s, acts)

    # Rough game counts from pts (or first available stat)
    def _n_games(d):
        try:
            return len(d[SNAPSHOT_POINTS[0]][COUNT_STATS[0]])
        except Exception:
            return 0

    n_train = _n_games(tr_q50)
    n_val = _n_games(va_q50)
    print(f"[{name}] train rows(fg3m/endQ2)={n_train}  val rows={n_val}", flush=True)

    print(f"[{name}] fitting asymmetric sigma params on train half...", flush=True)
    sigma_params = fit_sigma_params(tr_q50, tr_act)

    per_stat: List[Dict] = []
    all_pass = True
    fail_reasons: List[str] = []

    for pt in SNAPSHOT_POINTS:
        for s in COUNT_STATS:
            q50_va = va_q50[pt][s]
            q10_va = va_q10[pt][s]
            q90_va = va_q90[pt][s]
            act_va = va_act[pt][s]
            n_va = len(act_va)

            if n_va < 5:
                print(f"  [eval] {pt}/{s}: n={n_va} -- too few, skip", flush=True)
                continue

            # Baseline coverage
            cov_lo_b, cov_hi_b, cov80_b = compute_coverage(q50_va, q10_va, q90_va, act_va)

            # Treatment bands from fitted sigmas
            sp = sigma_params.get(pt, {}).get(s, {"sigma_lo": 0.5, "sigma_hi": 1.0})
            q10_tr, q90_tr = build_treat_bands(q50_va, sp)
            cov_lo_t, cov_hi_t, cov80_t = compute_coverage(q50_va, q10_tr, q90_tr, act_va)

            gate_lo = _GATE_LO_LO <= cov_lo_t <= _GATE_LO_HI
            gate_hi = _GATE_HI_LO <= cov_hi_t <= _GATE_HI_HI
            gate_80 = _GATE_80_LO <= cov80_t <= _GATE_80_HI

            print(
                f"  [eval] {pt}/{s}: n={n_va} "
                f"base=[lo={cov_lo_b:.3f} hi={cov_hi_b:.3f} 80={cov80_b:.3f}] "
                f"treat=[lo={cov_lo_t:.3f} hi={cov_hi_t:.3f} 80={cov80_t:.3f}] "
                f"gates=[lo={'OK' if gate_lo else 'FAIL'} "
                f"hi={'OK' if gate_hi else 'FAIL'} "
                f"80={'OK' if gate_80 else 'FAIL'}]",
                flush=True,
            )

            if not (gate_lo and gate_hi and gate_80):
                all_pass = False
                if not gate_lo:
                    fail_reasons.append(f"{pt}/{s} cov_lo={cov_lo_t:.3f} not in "
                                        f"[{_GATE_LO_LO},{_GATE_LO_HI}]")
                if not gate_hi:
                    fail_reasons.append(f"{pt}/{s} cov_hi={cov_hi_t:.3f} not in "
                                        f"[{_GATE_HI_LO},{_GATE_HI_HI}]")
                if not gate_80:
                    fail_reasons.append(f"{pt}/{s} cov80={cov80_t:.3f} not in "
                                        f"[{_GATE_80_LO},{_GATE_80_HI}]")

            per_stat.append({
                "stat": s,
                "point": pt,
                "n_val": n_va,
                "cov_lo_base": round(cov_lo_b, 6),
                "cov_hi_base": round(cov_hi_b, 6),
                "cov80_base": round(cov80_b, 6),
                "cov_lo_treat": round(cov_lo_t, 6),
                "cov_hi_treat": round(cov_hi_t, 6),
                "cov80_treat": round(cov80_t, 6),
                "gate_lo": gate_lo,
                "gate_hi": gate_hi,
                "gate_80": gate_80,
            })

    ship_reason = (
        "all one-sided gates pass at both endQ2 and endQ3 for all 4 count stats"
        if all_pass else "; ".join(fail_reasons) or "gate not met"
    )

    result = R2HResult(
        name=name,
        n_games_train=n_train,
        n_games_val=n_val,
        Z80=_Z80,
        sigma_params=sigma_params,
        per_stat=per_stat,
        ship=all_pass,
        ship_reason=ship_reason,
    )

    print(f"  [{name}] SHIP={all_pass}  {ship_reason}", flush=True)

    os.makedirs(_OUT_DIR, exist_ok=True)
    md_path = os.path.join(_OUT_DIR, f"improve_{name}.md")
    json_path = os.path.join(_OUT_DIR, f"improve_{name}.json")

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(result.to_md())

    def _clean(o):
        if isinstance(o, float) and o != o:
            return None
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_clean(v) for v in o]
        return o

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(_clean(asdict(result)), fh, indent=2)

    print(f"  wrote {md_path}", flush=True)
    print(f"  wrote {json_path}", flush=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Calibration probe R2-H: asymmetric one-sided quantile tails "
                    "for count stats (fg3m, stl, blk, tov) at endQ2 and endQ3."
    )
    ap.add_argument("--max-games", type=int, default=0,
                    help="Cap number of games processed (0 = all)")
    args = ap.parse_args()
    warnings.filterwarnings("ignore")
    run_probe(max_games=args.max_games)
    return 0


if __name__ == "__main__":
    sys.exit(main())
