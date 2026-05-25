"""probe_R4_C_asymmetric_tails_v2.py -- improve_loop R4-C-v2 (loop 5).

CALIBRATION probe. Two independent 1D bisections for asymmetric per-(stat, point)
sigma pairs on count stats FG3M/BLK/STL/TOV.

ANGLE: R2-H was REJECTED because the coupled 2D approach over-constrained the fit.
This version decouples the two tails mathematically: for each stat/point we run
TWO INDEPENDENT 1D fits on the signed residuals:

  sigma_lo = quantile(|r[r<0]|, 0.80) / Z80   <- constrain lower tail coverage to 0.10
  sigma_hi = quantile( r[r>0],  0.80) / Z80   <- constrain upper tail coverage to 0.10

Both are closed-form (no iteration), matching calibrate_live_quantiles_v2 style.

Ship gate per (stat, point):
  cov_lo_treat in [0.085, 0.115]
  cov_hi_treat in [0.085, 0.115]
  cov80_treat  in [0.79,  0.81]
  sum(|cov_lo - 0.10| + |cov_hi - 0.10|) reduced >= 0.02 vs baseline

Run:
    python scripts/probe_R4_C_asymmetric_tails_v2.py [--max-games N]

Output:
    scripts/_results/improve_R4_C_asymmetric_tails_v2.{md,json}
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

# ── constants ──────────────────────────────────────────────────────────────────

COUNT_STATS = ("fg3m", "blk", "stl", "tov")
SNAPSHOT_POINTS = ("endQ2", "endQ3")

_Z80 = 1.2816  # z-score for 80th-percentile one-sided Gaussian

_OUT_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")

# Ship gate bounds (tighter than R2-H)
_GATE_LO = (0.085, 0.115)
_GATE_HI = (0.085, 0.115)
_GATE_80 = (0.79,  0.81)
_MIN_DELTA_SUM = 0.02   # sum |cov_lo-0.10|+|cov_hi-0.10| must drop by >= this


# ── corpus collection ──────────────────────────────────────────────────────────

def collect_corpus(
    max_games: int = 0,
) -> Tuple[
    Dict[str, Dict[str, List[float]]],   # q50s[point][stat]
    Dict[str, Dict[str, List[float]]],   # q10s[point][stat]  (baseline)
    Dict[str, Dict[str, List[float]]],   # q90s[point][stat]  (baseline)
    Dict[str, Dict[str, List[float]]],   # acts[point][stat]
]:
    """Collect (q50, q10_base, q90_base, actual) for count stats via live_engine."""
    from src.prediction.live_engine import project_from_snapshot

    qstats = rim.load_quarter_stats()
    all_gids = sorted(qstats["game_id"].unique().tolist())
    if max_games:
        all_gids = all_gids[:max_games]

    q50s: Dict[str, Dict[str, List[float]]] = {pt: {s: [] for s in COUNT_STATS}
                                                for pt in SNAPSHOT_POINTS}
    q10s: Dict[str, Dict[str, List[float]]] = {pt: {s: [] for s in COUNT_STATS}
                                                for pt in SNAPSHOT_POINTS}
    q90s: Dict[str, Dict[str, List[float]]] = {pt: {s: [] for s in COUNT_STATS}
                                                for pt in SNAPSHOT_POINTS}
    acts: Dict[str, Dict[str, List[float]]] = {pt: {s: [] for s in COUNT_STATS}
                                                for pt in SNAPSHOT_POINTS}

    n_ok = 0
    for gid in all_gids:
        game_actuals = rim.actuals_for_game(gid, qstats)
        if not game_actuals:
            continue

        for point in SNAPSHOT_POINTS:
            snap = rim.build_snapshot(gid, point, qstats)
            if snap is None:
                continue
            try:
                rows = project_from_snapshot(snap)
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
                    q10v = float(r.get("q10") or 0.0)
                    q90v = float(r.get("q90") or q50v)
                except (TypeError, ValueError):
                    continue
                q50s[point][stat].append(q50v)
                q10s[point][stat].append(q10v)
                q90s[point][stat].append(q90v)
                acts[point][stat].append(float(actual))

        n_ok += 1
        if n_ok % 100 == 0:
            print(f"  [corpus] {n_ok}/{len(all_gids)} games", flush=True)

    print(f"  [corpus] done: {n_ok} games processed", flush=True)
    return q50s, q10s, q90s, acts


# ── chronological 50/50 split ──────────────────────────────────────────────────

def _half(lst: List[float], first: bool) -> np.ndarray:
    arr = np.array(lst, dtype=float)
    mid = len(arr) // 2
    return arr[:mid] if first else arr[mid:]


def split_corpus(
    q50s: Dict[str, Dict[str, List[float]]],
    q10s: Dict[str, Dict[str, List[float]]],
    q90s: Dict[str, Dict[str, List[float]]],
    acts: Dict[str, Dict[str, List[float]]],
) -> Tuple[
    Dict[str, Dict[str, np.ndarray]],   # tr_q50
    Dict[str, Dict[str, np.ndarray]],   # tr_act
    Dict[str, Dict[str, np.ndarray]],   # va_q50
    Dict[str, Dict[str, np.ndarray]],   # va_q10  (baseline)
    Dict[str, Dict[str, np.ndarray]],   # va_q90  (baseline)
    Dict[str, Dict[str, np.ndarray]],   # va_act
]:
    tr_q50 = {pt: {s: _half(q50s[pt][s], True)  for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    tr_act = {pt: {s: _half(acts[pt][s], True)   for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    va_q50 = {pt: {s: _half(q50s[pt][s], False)  for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    va_q10 = {pt: {s: _half(q10s[pt][s], False)  for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    va_q90 = {pt: {s: _half(q90s[pt][s], False)  for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    va_act = {pt: {s: _half(acts[pt][s], False)  for s in COUNT_STATS} for pt in SNAPSHOT_POINTS}
    return tr_q50, tr_act, va_q50, va_q10, va_q90, va_act


# ── fit asymmetric sigmas (two independent 1D closed-form fits) ────────────────

def fit_sigma_params(
    tr_q50: Dict[str, Dict[str, np.ndarray]],
    tr_act: Dict[str, Dict[str, np.ndarray]],
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Return {point: {stat: {sigma_lo, sigma_hi}}}.

    For each (stat, point) the two tails are fit independently:
      r = actual - q50
      r_neg = r[r < 0]  (under-predictions)
      r_pos = r[r > 0]  (over-predictions)
      sigma_lo = quantile(|r_neg|, 0.80) / Z80  -> 10% lower-tail coverage
      sigma_hi = quantile( r_pos,  0.80) / Z80  -> 10% upper-tail coverage
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
            r_neg = np.abs(r[r < 0])
            r_pos = r[r > 0]
            sigma_lo = (float(np.quantile(r_neg, 0.80)) / _Z80
                        if len(r_neg) >= 5 else 0.5)
            sigma_hi = (float(np.quantile(r_pos, 0.80)) / _Z80
                        if len(r_pos) >= 5 else 1.0)
            params[pt][s] = {
                "sigma_lo": round(sigma_lo, 6),
                "sigma_hi": round(sigma_hi, 6),
            }
            print(f"  [fit] {pt}/{s}: sigma_lo={sigma_lo:.4f}  sigma_hi={sigma_hi:.4f}  "
                  f"n_neg={len(r_neg)}  n_pos={len(r_pos)}", flush=True)
    return params


# ── coverage helpers ───────────────────────────────────────────────────────────

def coverage(
    q10: np.ndarray, q90: np.ndarray, act: np.ndarray,
) -> Tuple[float, float, float]:
    """Return (cov_lo, cov_hi, cov80)."""
    if len(act) == 0:
        return float("nan"), float("nan"), float("nan")
    cov_lo = float((act < q10).mean())
    cov_hi = float((act > q90).mean())
    cov80  = float(((act >= q10) & (act <= q90)).mean())
    return cov_lo, cov_hi, cov80


def treat_bands(
    q50: np.ndarray, sp: Dict[str, float],
) -> Tuple[np.ndarray, np.ndarray]:
    """Build asymmetric treatment bands from fitted sigma params."""
    q10 = np.maximum(0.0, q50 - sp["sigma_lo"] * _Z80)
    q90 = q50 + sp["sigma_hi"] * _Z80
    return q10, q90


# ── result schema ─────────────────────────────────────────────────────────────

@dataclass
class R4Cv2Result:
    name: str
    n_games_total: int
    Z80: float
    sigma_params: Dict
    per_stat: List[Dict] = field(default_factory=list)
    ship: bool = False
    ship_reason: str = ""

    def to_md(self) -> str:
        lines = [
            f"# probe {self.name} -- improve_loop (CALIBRATION)",
            "",
            f"**Games total:** {self.n_games_total}  "
            f"(train=first-50%  val=last-50%)  Z80={self.Z80}",
            "",
            "## Fitted sigma parameters (train half)",
            "",
            "| point | stat | sigma_lo | sigma_hi |",
            "|-------|------|----------|----------|",
        ]
        for pt in SNAPSHOT_POINTS:
            for s in COUNT_STATS:
                p = self.sigma_params.get(pt, {}).get(s, {})
                lines.append(
                    f"| {pt} | {s} | "
                    f"{p.get('sigma_lo', float('nan')):.4f} | "
                    f"{p.get('sigma_hi', float('nan')):.4f} |"
                )
        lines += [
            "",
            "## One-sided tail coverage (val half)",
            "",
            "| stat | point | n | cov_lo_base | cov_hi_base | cov80_base "
            "| cov_lo_treat | cov_hi_treat | cov80_treat "
            "| delta_sum | gate_lo | gate_hi | gate_80 | gate_delta |",
            "|------|-------|---|-------------|-------------|------------|"
            "--------------|--------------|-------------|-----------|"
            "---------|---------|---------|------------|",
        ]

        def _f(v: object) -> str:
            return f"{v:.3f}" if isinstance(v, float) and v == v else "nan"

        def _ok(b: bool) -> str:
            return "PASS" if b else "FAIL"

        for r in self.per_stat:
            lines.append(
                f"| {r['stat']} | {r['point']} | {r['n_val']} "
                f"| {_f(r['cov_lo_base'])} | {_f(r['cov_hi_base'])} | {_f(r['cov80_base'])} "
                f"| {_f(r['cov_lo_treat'])} | {_f(r['cov_hi_treat'])} | {_f(r['cov80_treat'])} "
                f"| {_f(r['delta_sum_improvement'])} "
                f"| {_ok(r['gate_lo'])} | {_ok(r['gate_hi'])} "
                f"| {_ok(r['gate_80'])} | {_ok(r['gate_delta'])} |"
            )
        lines += [
            "",
            "## Verdict",
            "",
            f"- **{'SHIP' if self.ship else 'REJECT'}**: {self.ship_reason}",
        ]
        return "\n".join(lines) + "\n"


# ── main probe ────────────────────────────────────────────────────────────────

def run_probe(max_games: int = 0) -> R4Cv2Result:
    name = "R4_C_asymmetric_tails_v2"
    print(f"[{name}] collecting corpus (max_games={max_games or 'ALL'})...", flush=True)
    q50s, q10s, q90s, acts = collect_corpus(max_games)

    print(f"[{name}] splitting 50/50 chronologically...", flush=True)
    tr_q50, tr_act, va_q50, va_q10, va_q90, va_act = split_corpus(
        q50s, q10s, q90s, acts)

    # Total row count (fg3m/endQ2 as proxy)
    try:
        _probe_arr = q50s[SNAPSHOT_POINTS[0]][COUNT_STATS[0]]
        n_total = len(_probe_arr)
    except Exception:
        n_total = 0

    print(f"[{name}] total rows (fg3m/endQ2): {n_total}  train={n_total//2}  val={n_total - n_total//2}", flush=True)

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

            # Baseline coverage from live_engine bands
            cov_lo_b, cov_hi_b, cov80_b = coverage(q10_va, q90_va, act_va)
            base_sum = abs(cov_lo_b - 0.10) + abs(cov_hi_b - 0.10)

            # Treatment bands from two independent 1D fits
            sp = sigma_params.get(pt, {}).get(s, {"sigma_lo": 0.5, "sigma_hi": 1.0})
            q10_tr, q90_tr = treat_bands(q50_va, sp)
            cov_lo_t, cov_hi_t, cov80_t = coverage(q10_tr, q90_tr, act_va)
            treat_sum = abs(cov_lo_t - 0.10) + abs(cov_hi_t - 0.10)

            delta_improvement = base_sum - treat_sum   # positive = improvement

            gate_lo    = _GATE_LO[0] <= cov_lo_t <= _GATE_LO[1]
            gate_hi    = _GATE_HI[0] <= cov_hi_t <= _GATE_HI[1]
            gate_80    = _GATE_80[0] <= cov80_t  <= _GATE_80[1]
            gate_delta = delta_improvement >= _MIN_DELTA_SUM

            gate_all = gate_lo and gate_hi and gate_80 and gate_delta

            print(
                f"  [eval] {pt}/{s}: n={n_va} "
                f"base=[lo={cov_lo_b:.3f} hi={cov_hi_b:.3f} 80={cov80_b:.3f}] "
                f"treat=[lo={cov_lo_t:.3f} hi={cov_hi_t:.3f} 80={cov80_t:.3f}] "
                f"delta_sum={delta_improvement:+.4f} "
                f"gates=[lo={'OK' if gate_lo else 'FAIL'} "
                f"hi={'OK' if gate_hi else 'FAIL'} "
                f"80={'OK' if gate_80 else 'FAIL'} "
                f"delta={'OK' if gate_delta else 'FAIL'}]",
                flush=True,
            )

            if not gate_all:
                all_pass = False
                if not gate_lo:
                    fail_reasons.append(
                        f"{pt}/{s} cov_lo={cov_lo_t:.3f} not in {_GATE_LO}")
                if not gate_hi:
                    fail_reasons.append(
                        f"{pt}/{s} cov_hi={cov_hi_t:.3f} not in {_GATE_HI}")
                if not gate_80:
                    fail_reasons.append(
                        f"{pt}/{s} cov80={cov80_t:.3f} not in {_GATE_80}")
                if not gate_delta:
                    fail_reasons.append(
                        f"{pt}/{s} delta_sum={delta_improvement:.4f} < {_MIN_DELTA_SUM}")

            per_stat.append({
                "stat":                 s,
                "point":                pt,
                "n_val":                n_va,
                "sigma_lo":             sp["sigma_lo"],
                "sigma_hi":             sp["sigma_hi"],
                "cov_lo_base":          round(cov_lo_b, 6),
                "cov_hi_base":          round(cov_hi_b, 6),
                "cov80_base":           round(cov80_b, 6),
                "cov_lo_treat":         round(cov_lo_t, 6),
                "cov_hi_treat":         round(cov_hi_t, 6),
                "cov80_treat":          round(cov80_t, 6),
                "delta_sum_improvement": round(delta_improvement, 6),
                "gate_lo":              gate_lo,
                "gate_hi":              gate_hi,
                "gate_80":              gate_80,
                "gate_delta":           gate_delta,
            })

    ship_reason = (
        "all one-sided gates pass for all 4 count stats at both endQ2 and endQ3"
        if all_pass else ("; ".join(fail_reasons) or "gate not met")
    )

    result = R4Cv2Result(
        name=name,
        n_games_total=n_total,
        Z80=_Z80,
        sigma_params=sigma_params,
        per_stat=per_stat,
        ship=all_pass,
        ship_reason=ship_reason,
    )
    print(f"[{name}] SHIP={all_pass}  {ship_reason}", flush=True)

    os.makedirs(_OUT_DIR, exist_ok=True)
    md_path   = os.path.join(_OUT_DIR, f"improve_{name}.md")
    json_path = os.path.join(_OUT_DIR, f"improve_{name}.json")

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(result.to_md())

    def _clean(o: object) -> object:
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
        description="Calibration probe R4-C-v2: decoupled asymmetric 1D sigma fits "
                    "for count stats (fg3m, blk, stl, tov) at endQ2 and endQ3."
    )
    ap.add_argument("--max-games", type=int, default=0,
                    help="Cap number of games (0 = all)")
    args = ap.parse_args()
    warnings.filterwarnings("ignore")
    run_probe(max_games=args.max_games)
    return 0


if __name__ == "__main__":
    sys.exit(main())
