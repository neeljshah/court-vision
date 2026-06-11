"""scripts/ingame/ingame_rmsebias_harness.py — the in-game RMSE+bias eval GATE.

THE LOAD-BEARING DISCIPLINE (the MAE-vs-RMSE memory): the "shrink toward current" MAE win is a
median-vs-mean artifact that WORSENS RMSE+bias. So this harness scores any in-game player-stat
projection rule on the OOF eval cache by **RMSE + signed bias** (MAE is REPORTED but NEVER gates).
This is the gate referenced by src/ingame/trust_curve.py and src/ingame/frozen_score_shrink.py — the
trust-curve json / frozen-score shrink may flip ON only if a candidate clears this gate on a same-era
fold. The shrink / non-identity-trust candidates are EXPECTED to be REJECTED here until such a
validated curve exists; that rejection (shrink wins MAE but loses RMSE/bias) is the artifact guard,
demonstrated end-to-end.

BASE / prior = ``routed`` (the deployed base projection). truth = the player's actual final value.
The IDENTITY rule (base, and bayes with the default identity trust curve) reproduces ``routed``
byte-for-byte -> RMSE delta exactly 0.0. The bayes posterior is computed VECTORIZED for speed over the
2.47M-row cache, with a parity test asserting it equals the per-row posterior_projection(...) within 1e-9.

DEFAULT-OFF tooling: this scores experiments; it never changes a served value.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Callable, Dict, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (os.path.join(ROOT, "scripts", "team_system"), os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ingame.bayes_player_update import posterior_projection  # noqa: E402,F401
from ingame.live_state_hook import remaining_min_from  # noqa: E402
from ingame import trust_curve  # noqa: E402,F401
from ingame import frozen_score_shrink  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_CACHE = os.path.join(ROOT, "data", "cache", "ingame_eval_cache.parquet")
_SMOKE = os.path.join(ROOT, "data", "cache", "ingame_eval_cache_smoke.parquet")
_FULL_GAME_SEC = 2880.0  # 48 min — the frozen-score-shrink remaining-frac denominator


def load_eval_frame(path: str = _CACHE) -> pd.DataFrame:
    """Load the OOF in-game eval cache (default: the full cache; the smoke cache is the test fixture)."""
    return pd.read_parquet(path)


def rmse_bias_mae(pred, truth) -> Tuple[float, float, float]:
    """Return (rmse, signed_bias, mae) for pred vs truth, vectorized. signed_bias = mean(pred-truth)."""
    p = np.asarray(pred, dtype=float)
    a = np.asarray(truth, dtype=float)
    err = p - a
    rmse = float(np.sqrt(np.mean(err ** 2)))
    bias = float(np.mean(err))
    mae = float(np.mean(np.abs(err)))
    return rmse, bias, mae


# ---------------------------------------------------------------------------
# Remaining minutes — REUSE the exact live-serve helper (the gate is only valid
# if it scores the SAME remaining-min formula the live path uses).
# ---------------------------------------------------------------------------

def _remaining_min_vec(df: pd.DataFrame) -> np.ndarray:
    cur_min = df["cur_min"].to_numpy(float)
    g_el = df["game_elapsed_sec"].to_numpy(float)
    g_rem = df["game_remaining_sec"].to_numpy(float)
    return np.array([remaining_min_from(c, e, r) for c, e, r in zip(cur_min, g_el, g_rem)], dtype=float)


def _regime_rows(df: pd.DataFrame):
    """Per-row regime dict matching the live path: playoff iff game_id startswith '004'; coarse |margin| bucket."""
    gid = df["game_id"].astype(str).to_numpy()
    am = np.abs(df["score_margin"].to_numpy(float))
    mb = np.where(am <= 5.0, 0, np.where(am <= 12.0, 1, 2))
    return gid, mb


# ---------------------------------------------------------------------------
# Candidate rules — rule_fn(df) -> candidate projection array (df order). BASE = routed.
# ---------------------------------------------------------------------------

def base_rule(df: pd.DataFrame) -> np.ndarray:
    """Identity: the deployed base projection (``routed``). RMSE delta vs itself is exactly 0.0."""
    return df["routed"].to_numpy(float)


def bayes_rule(df: pd.DataFrame, trust_override: Optional[float] = None) -> np.ndarray:
    """Vectorized minutes-weighted Bayesian posterior: tw*evidence + (1-tw)*prior.

    evidence = cur + (cur/cur_min)*remaining_min where cur_min>0 else cur (matches evidence_extrap).
    With trust_override=None and no trust_curve json, trust_w==0 -> posterior == routed EXACTLY (identity).
    The AST playoff guard caps trust_w at 0.10 (mirrors posterior_projection). A parity test asserts this
    fast path equals the per-row module within 1e-9.
    """
    prior = df["routed"].to_numpy(float)
    cur = df["cur"].to_numpy(float)
    cur_min = df["cur_min"].to_numpy(float)
    stat = df["stat"].to_numpy()
    rem_min = _remaining_min_vec(df)

    total = cur_min + rem_min
    with np.errstate(divide="ignore", invalid="ignore"):
        rf = np.where(total > 0, rem_min / total, 1.0)

    gid, mb = _regime_rows(df)
    is_po = np.char.startswith(gid.astype(str), "004")

    # trust_w per row (identity curve -> 0; override -> constant), then AST playoff cap.
    if trust_override is None:
        tw = np.array(
            [trust_curve.trust_w(s, float(r), {"is_playoff": bool(p), "margin_bucket": int(b)}, float(m))
             for s, r, p, b, m in zip(stat, rf, is_po, mb, cur_min)],
            dtype=float,
        )
    else:
        tw = np.full(len(df), float(trust_override), dtype=float)
    ast_po = (stat == "ast") & is_po
    tw = np.where(ast_po, np.minimum(tw, 0.10), tw)
    tw = np.clip(tw, 0.0, 1.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        evidence = np.where(cur_min > 0, cur + (cur / np.where(cur_min > 0, cur_min, 1.0)) * rem_min, cur)
    return tw * evidence + (1.0 - tw) * prior


def shrink_rule(df: pd.DataFrame, mode: str = "shrink") -> np.ndarray:
    """Frozen-score-shrink candidate: reprice routed toward the live score (remaining_frac = g_rem/2880).

    Per-row via frozen_score_shrink.reprice. EXPECTED to win MAE on skewed stats yet LOSE RMSE/worsen
    bias -> this harness shows the gate FAIL (the artifact guard, end-to-end).
    """
    prior = df["routed"].to_numpy(float)
    cur = df["cur"].to_numpy(float)
    rfrac = df["game_remaining_sec"].to_numpy(float) / _FULL_GAME_SEC
    return np.array(
        [frozen_score_shrink.reprice(float(pf), float(c), float(rf), mode=mode)
         for pf, c, rf in zip(prior, cur, rfrac)],
        dtype=float,
    )


# ---------------------------------------------------------------------------
# Scorer — RMSE+bias is the GATE, MAE is reported only.
# ---------------------------------------------------------------------------

def _verdict(base: np.ndarray, new: np.ndarray, truth: np.ndarray) -> Dict[str, object]:
    b_rmse, b_bias, b_mae = rmse_bias_mae(base, truth)
    n_rmse, n_bias, n_mae = rmse_bias_mae(new, truth)
    passed = (n_rmse < b_rmse - 1e-9) and (abs(n_bias) <= abs(b_bias) + 1e-9)
    return {"base_rmse": b_rmse, "new_rmse": n_rmse, "base_bias": b_bias, "new_bias": n_bias,
            "base_mae": b_mae, "new_mae": n_mae, "pass": bool(passed)}


def score_rule(df: pd.DataFrame, rule_fn: Callable[[pd.DataFrame], np.ndarray], label: str,
               stats: Tuple[str, ...] = STATS, verbose: bool = True) -> Dict[str, object]:
    """Score a candidate rule by RMSE+signed-bias (MAE reported, NEVER gated), overall + per bucket + per stat.

    rule_fn(df) -> candidate array (df order). BASE = df['routed']. GATE pass iff RMSE strictly improves
    AND |bias| does not worsen, aggregated over the scored rows. Per-bucket/per-stat dicts let a future
    caller gate individual trust-curve cells. Returns {label, overall, per_bucket, per_stat, n}.
    """
    new_full = np.asarray(rule_fn(df), dtype=float)
    mask = df["stat"].isin(stats).to_numpy()
    sub = df.loc[mask]
    base = sub["routed"].to_numpy(float)
    truth = sub["truth"].to_numpy(float)
    new = new_full[mask]

    overall = _verdict(base, new, truth)
    per_bucket: Dict[str, object] = {}
    for bk, idx in sub.groupby("bucket").indices.items():
        per_bucket[str(bk)] = _verdict(base[idx], new[idx], truth[idx])
    per_stat: Dict[str, object] = {}
    for st, idx in sub.groupby("stat").indices.items():
        per_stat[str(st)] = _verdict(base[idx], new[idx], truth[idx])

    result = {"label": label, "overall": overall, "per_bucket": per_bucket,
              "per_stat": per_stat, "n": int(mask.sum())}
    if verbose:
        _print_result(result)
    return result


def _print_result(r: Dict[str, object]) -> None:
    o = r["overall"]
    d_rmse = o["new_rmse"] - o["base_rmse"]
    verdict = "PASS" if o["pass"] else "FAIL"
    print(f"\n=== {r['label']}  (n={r['n']:,}) ===")
    print(f"  RMSE  base={o['base_rmse']:.4f}  new={o['new_rmse']:.4f}  delta={d_rmse:+.4f}")
    print(f"  BIAS  base={o['base_bias']:+.4f}  new={o['new_bias']:+.4f}  "
          f"|base|={abs(o['base_bias']):.4f} |new|={abs(o['new_bias']):.4f}")
    print(f"  MAE   base={o['base_mae']:.4f}  new={o['new_mae']:.4f}  (reported, NOT a gate)")
    print(f"  GATE (RMSE+bias only): {verdict}")
    if not o["pass"] and d_rmse > 0:
        print("        -> rejected: worsens RMSE (the shrink/trust MAE-vs-RMSE artifact guard)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    ap = argparse.ArgumentParser(description="In-game RMSE+bias eval gate (never gates on MAE).")
    ap.add_argument("--cache", default=_CACHE, help="path to the eval cache parquet (default: full)")
    ap.add_argument("--smoke", action="store_true", help="use the small smoke cache for a fast run")
    ap.add_argument("--trust", type=float, default=None, help="trust_override for bayes_rule (e.g. 0.3)")
    args = ap.parse_args()

    path = _SMOKE if args.smoke else args.cache
    print(f"Loading eval cache: {path}")
    df = load_eval_frame(path)
    print(f"  rows={len(df):,}  stats={sorted(df['stat'].unique().tolist())}")

    print("\n[1] BASE / identity rule (must show RMSE delta == 0.0000 — byte-identity proof):")
    rb = score_rule(df, base_rule, "base (identity = routed)")
    assert abs(rb["overall"]["new_rmse"] - rb["overall"]["base_rmse"]) < 1e-9, "identity broke!"
    print(f"    identity RMSE delta = {rb['overall']['new_rmse'] - rb['overall']['base_rmse']:.4f}")

    tw = args.trust if args.trust is not None else 0.3
    print(f"\n[2] BAYES rule @ trust_override={tw} (EXPECTED to LOSE on RMSE -> gate FAIL):")
    score_rule(df, lambda d: bayes_rule(d, trust_override=tw), f"bayes(trust={tw})")

    print("\n[3] SHRINK rule (EXPECTED to worsen RMSE/bias even if MAE improves -> gate FAIL):")
    score_rule(df, shrink_rule, "frozen-score shrink")

    print("\nGate discipline: a candidate ships ONLY if it BEATS base RMSE and does not worsen |bias|. "
          "MAE is never a gate. Shrink/trust stay OFF until a same-era validated curve clears this gate.")


if __name__ == "__main__":
    _main()
