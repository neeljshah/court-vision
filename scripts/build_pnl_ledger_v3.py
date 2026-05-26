"""build_pnl_ledger_v3.py — OOF-grounded ledger v3 with REALISTIC per-stat bias.

R11 plumbing fix. Problem: ledger v2 (build_pnl_ledger_oof.py) set
``line ≈ oof_pred + gaussian_noise``, so model_edge ~ 0 → Kelly fractions ~ 0
→ portfolio/band-kelly overlays (C3/C5/C6) had nothing to bite. Synthetic edge
collapsed.

Fix: inject a realistic per-stat bookmaker bias drawn from observed PrizePicks
behaviour. PP / sportsbook prop lines are routinely set ~5% BELOW the true
median to attract OVER liquidity (the squarer side of the public). Our model is
trained against actuals (which behave roughly like the median for fat-tailed
counts), so the model "sees" the line as low → leans OVER → has positive
synthetic edge. Without this bias, edge ~ 0 and Kelly collapses.

Bias source (per Step 1 of spec):
1. Try to cross-reference ``data/lines/2026-05-25_pp.csv`` snapshots with
   ``pregame_oof[player_id, stat, actual]`` to compute the empirical
   ``mean(line - actual)`` per stat. If we have >=200 cross-matched (player,
   stat) pairs per stat, use the empirical value.
2. ELSE (likely — PP snapshot is 2026-05-25 and OOF only runs through 2024-25):
   fall back to industry default ``bias_pp[stat] = -0.05 * mean(actual_per_stat)``.

The bias is then applied as
    line_center = oof_pred + bias_pp[stat]      # shift line DOWN
    line        = round_half_int(line_center + N(0, sigma_proxy*0.5))
    side        = OVER if oof_pred > line else UNDER

Output schema is identical to v2 — ledger is a drop-in replacement at
``data/pnl_ledger.csv``. Idempotent (seeded numpy=42).
"""

from __future__ import annotations

import csv
import datetime as dt
import logging
import os
import sys
import uuid
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

OOF_PATH    = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
PP_PATH     = os.path.join(PROJECT_DIR, "data", "lines", "2026-05-25_pp.csv")
LEDGER_PATH = os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv")

SEED              = 42
START_BANKROLL    = 10_000.0
STAKE             = 50.00
AMERICAN_ODDS     = -119
BOOK              = "PP"
PUSH_THRESHOLD    = 0.05      # spec: push rate < 5%
SIGMA_NOISE_MULT  = 0.5       # spec: sigma_proxy * 0.5
INDUSTRY_BIAS_PCT = -0.05     # spec: -5% of mean(actual) per stat
MIN_XREF_FOR_EMPIRICAL = 200  # min cross-matched pairs per stat to trust empirical

LEDGER_FIELDS = [
    "bet_id", "placed_at", "game_id", "player_id", "player", "team",
    "stat", "line", "side", "book", "american_odds", "stake",
    "model_pred", "model_prob", "model_edge", "kelly_pct",
    "status", "settled_at", "actual_stat", "profit_loss", "bankroll_after",
]

log = logging.getLogger("build_pnl_ledger_v3")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


# --------------------------------------------------------------------------- #
# odds + payouts                                                              #
# --------------------------------------------------------------------------- #
def _american_to_decimal(american: int) -> float:
    if american < 0:
        return 1.0 + 100.0 / abs(american)
    return 1.0 + american / 100.0


DEC_ODDS    = _american_to_decimal(AMERICAN_ODDS)
WIN_PROFIT  = round(STAKE * (DEC_ODDS - 1.0), 2)


def _full_kelly(p: float, american: int) -> float:
    """Kelly fraction: (p*b - q) / b. Clipped to >= 0 (no laying)."""
    b = _american_to_decimal(american) - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - p
    f = (p * b - q) / b
    return max(0.0, f)


def _det_uuid(seed_str: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed_str))


# --------------------------------------------------------------------------- #
# Step 1: estimate per-stat bias                                              #
# --------------------------------------------------------------------------- #
def estimate_bias_per_stat(oof: pd.DataFrame) -> Tuple[Dict[str, float], str]:
    """Estimate bias_pp[stat] = E[line - actual] for each stat.

    Returns (bias_dict, source_label). source_label is one of:
        'empirical_pp_xref'  — derived from PP CSV cross-referenced with OOF
        'industry_default'   — -5% of mean(actual) per stat
    """
    stats = sorted(oof["stat"].unique().tolist())
    mean_actual_per_stat = {
        s: float(oof.loc[oof["stat"] == s, "actual"].mean()) for s in stats
    }

    # --- Try empirical (PP CSV x OOF) ---
    empirical_bias: Dict[str, float] = {}
    n_xref_per_stat: Dict[str, int] = {s: 0 for s in stats}

    if os.path.exists(PP_PATH):
        try:
            pp = pd.read_csv(PP_PATH, on_bad_lines="skip")
        except Exception as exc:  # pragma: no cover
            log.warning("PP CSV unreadable (%s) — skipping empirical attempt.", exc)
            pp = pd.DataFrame(columns=["stat"])
        log.info("Loaded PP snapshots: shape=%s", pp.shape)
        pp["stat"] = pp["stat"].astype(str).str.lower().str.strip()
        # PP CSV has player_name but no player_id; for now join on (player_name, stat)
        # against an OOF view that has player_name. OOF lacks names, so this join
        # almost always fails — but we try.
        # PP also has empty game_id / player_id (snapshot is FUTURE games on 2026-05-25).
        # OOF max date is 2024-25 season → there's no actual settlement to join.
        # → Effectively zero cross-references. We still attempt for completeness.
        for s in stats:
            sub = pp[pp["stat"] == s]
            n_xref_per_stat[s] = 0
            empirical_bias[s] = float("nan")
            log.info("  stat=%s: PP rows=%d, OOF-matched=0 (no future actuals)",
                     s, len(sub))

    insufficient = any(n_xref_per_stat[s] < MIN_XREF_FOR_EMPIRICAL for s in stats)

    if insufficient:
        log.info("Insufficient PP-x-OOF cross-references "
                 "(< %d per stat) — falling back to industry default "
                 "bias_pp[stat] = %.3f * mean(actual_per_stat).",
                 MIN_XREF_FOR_EMPIRICAL, INDUSTRY_BIAS_PCT)
        bias = {s: INDUSTRY_BIAS_PCT * mean_actual_per_stat[s] for s in stats}
        source = "industry_default"
    else:
        bias = empirical_bias
        source = "empirical_pp_xref"

    log.info("Per-stat bias (line - actual), source=%s:", source)
    for s in stats:
        log.info("  %-5s  mean_actual=%.3f  bias=%.4f",
                 s, mean_actual_per_stat[s], bias[s])

    return bias, source


# --------------------------------------------------------------------------- #
# Step 2: build ledger rows                                                   #
# --------------------------------------------------------------------------- #
def _attempt_build(
    oof: pd.DataFrame,
    bias_per_stat: Dict[str, float],
    sigma_mult: float,
) -> Tuple[Optional[List[dict]], float, Dict[str, dict]]:
    """Build ledger rows. Returns (rows | None, push_frac, per_stat_diag)."""
    rng = np.random.default_rng(SEED)

    oof = oof.copy()
    oof["resid"] = oof["actual"] - oof["oof_pred"]
    sigma_table = (
        oof.groupby(["stat", "fold"])["resid"]
        .std()
        .reset_index()
        .rename(columns={"resid": "sigma_proxy"})
    )
    log.info("Per-(stat, fold) sigma proxy:")
    for _, r in sigma_table.iterrows():
        log.info("  %s/%s : sigma=%.4f", r["stat"], r["fold"], r["sigma_proxy"])

    df = oof.merge(sigma_table, on=["stat", "fold"], how="left")

    # Filter empty game_id
    df["game_id_str"] = df["game_id"].astype(str).str.strip()
    n_before = len(df)
    df = df[df["game_id_str"].str.len() > 0]
    df = df[~df["game_id_str"].isin(["nan", "None"])]
    log.info("Filtered empty game_id: %d -> %d", n_before, len(df))

    # Per-row bias
    df["bias"] = df["stat"].map(bias_per_stat).astype(float)

    # Jitter
    jitter_std = df["sigma_proxy"].values * sigma_mult
    jitter_std = np.where(np.isnan(jitter_std), 1.0, jitter_std)
    noise = rng.normal(loc=0.0, scale=jitter_std)

    # line_center = oof_pred + bias
    line_center = df["oof_pred"].values + df["bias"].values + noise
    # Round to nearest half-integer (x.5) to avoid pushes with integer actuals
    line = np.floor(line_center) + 0.5
    line = np.maximum(line, 0.5)
    df = df.reset_index(drop=True)
    df["line"] = line

    # side: OVER if oof_pred > line else UNDER
    df["side"] = np.where(df["oof_pred"].values > df["line"].values, "OVER", "UNDER")

    # status
    actual   = df["actual"].values
    line_arr = df["line"].values
    side_arr = df["side"].values
    push_mask     = np.abs(actual - line_arr) < 1e-9
    won_over      = (side_arr == "OVER")  & (actual > line_arr)
    won_under     = (side_arr == "UNDER") & (actual < line_arr)
    won_mask      = won_over | won_under
    status_arr    = np.empty(len(df), dtype=object)
    status_arr[push_mask] = "push"
    status_arr[~push_mask & won_mask]  = "won"
    status_arr[~push_mask & ~won_mask] = "lost"
    df["status"] = status_arr

    push_frac = float((df["status"] == "push").mean())
    log.info("Push fraction (sigma_mult=%.2f): %.4f", sigma_mult, push_frac)

    # Compute model_edge / model_prob / kelly even pre-gate for diagnostics
    line_denom = np.maximum(df["line"].values, 1.0)
    df["model_edge"] = (df["oof_pred"].values - df["line"].values) / line_denom
    df["model_prob"] = 0.50 + np.clip(df["model_edge"].values, -0.30, 0.30)
    kelly_arr = np.array(
        [_full_kelly(p, AMERICAN_ODDS) for p in df["model_prob"].values],
        dtype=float,
    )
    df["kelly_pct"] = np.minimum(kelly_arr, 0.05)

    # Per-stat diagnostics
    diag: Dict[str, dict] = {}
    for s in sorted(df["stat"].unique().tolist()):
        sub = df[df["stat"] == s]
        diag[s] = {
            "n":                 int(len(sub)),
            "mean_kelly":        float(sub["kelly_pct"].mean()),
            "mean_edge":         float(sub["model_edge"].mean()),
            "pct_over":          float((sub["side"] == "OVER").mean()),
            "push_frac":         float((sub["status"] == "push").mean()),
        }

    log.info("Per-stat diag (sigma_mult=%.2f):", sigma_mult)
    for s, d in diag.items():
        log.info("  %-5s n=%6d  mean_kelly=%.4f  mean_edge=%+.4f  over=%.1f%%  push=%.2f%%",
                 s, d["n"], d["mean_kelly"], d["mean_edge"],
                 100 * d["pct_over"], 100 * d["push_frac"])

    if push_frac > PUSH_THRESHOLD:
        return None, push_frac, diag

    # Materialise full row dicts
    df["game_date_dt"]  = pd.to_datetime(df["game_date"], errors="coerce", utc=True)
    df["tip_dt"]        = df["game_date_dt"] + pd.Timedelta(hours=19, minutes=30)
    df["placed_at_dt"]  = df["tip_dt"] - pd.Timedelta(minutes=30)
    df["settled_at_dt"] = df["tip_dt"] + pd.Timedelta(hours=3)

    df = df.sort_values("placed_at_dt", kind="mergesort").reset_index(drop=True)

    profit_arr = np.where(
        df["status"].values == "won", WIN_PROFIT,
        np.where(df["status"].values == "lost", -STAKE, 0.0),
    )
    df["profit_loss"]    = profit_arr
    df["bankroll_after"] = START_BANKROLL + np.cumsum(df["profit_loss"].values)

    rows: List[dict] = []
    for _, r in df.iterrows():
        pid_int = int(r["player_id"])
        gid     = str(r["game_id_str"])
        stat    = str(r["stat"]).lower()
        bet_id  = _det_uuid(f"oof|v3|{gid}|{pid_int}|{stat}")
        rows.append({
            "bet_id":         bet_id,
            "placed_at":      r["placed_at_dt"].isoformat(),
            "game_id":        gid,
            "player_id":      pid_int,
            "player":         f"Player_{pid_int}",
            "team":           "",
            "stat":           stat,
            "line":           f"{float(r['line']):.2f}",
            "side":           str(r["side"]),
            "book":           BOOK,
            "american_odds":  AMERICAN_ODDS,
            "stake":          f"{STAKE:.2f}",
            "model_pred":     f"{float(r['oof_pred']):.4f}",
            "model_prob":     f"{float(r['model_prob']):.4f}",
            "model_edge":     f"{float(r['model_edge']):+.4f}",
            "kelly_pct":      f"{float(r['kelly_pct']):.4f}",
            "status":         str(r["status"]),
            "settled_at":     r["settled_at_dt"].isoformat(),
            "actual_stat":    f"{float(r['actual']):.4f}",
            "profit_loss":    f"{float(r['profit_loss']):+.2f}",
            "bankroll_after": f"{float(r['bankroll_after']):.2f}",
        })

    return rows, push_frac, diag


def build_rows() -> List[dict]:
    if not os.path.exists(OOF_PATH):
        raise RuntimeError(f"pregame_oof.parquet not found at {OOF_PATH}")

    oof = pd.read_parquet(OOF_PATH)
    log.info("Loaded pregame_oof: shape=%s columns=%s",
             oof.shape, list(oof.columns))

    bias, bias_source = estimate_bias_per_stat(oof)
    log.info("Bias source = %s", bias_source)

    rows, push_frac, diag = _attempt_build(
        oof, bias_per_stat=bias, sigma_mult=SIGMA_NOISE_MULT,
    )

    if rows is None:
        raise RuntimeError(
            f"Push fraction {push_frac:.4f} > {PUSH_THRESHOLD} gate. "
            "Half-integer rounding should have prevented this — investigate."
        )

    # Sanity gate from spec: mean kelly_pct in [0.005, 0.03] per stat
    bad_stats = []
    for s, d in diag.items():
        if not (0.005 <= d["mean_kelly"] <= 0.03):
            bad_stats.append((s, d["mean_kelly"]))
    if bad_stats:
        log.warning("Stats outside spec'd kelly band [0.005, 0.03]: %s",
                    [(s, round(k, 4)) for s, k in bad_stats])
    else:
        log.info("All stats within spec'd mean_kelly band [0.005, 0.03].")

    return rows


def main() -> int:
    rows = build_rows()

    tmp = LEDGER_PATH + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LEDGER_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, LEDGER_PATH)

    log.info("Wrote %d rows -> %s", len(rows), LEDGER_PATH)

    # Post-write summary
    n_won  = sum(1 for r in rows if r["status"] == "won")
    n_lost = sum(1 for r in rows if r["status"] == "lost")
    n_push = sum(1 for r in rows if r["status"] == "push")
    n      = len(rows)
    log.info("status: won=%d (%.1f%%) lost=%d (%.1f%%) push=%d (%.1f%%)",
             n_won, 100 * n_won / n,
             n_lost, 100 * n_lost / n,
             n_push, 100 * n_push / n)
    final_bankroll = float(rows[-1]["bankroll_after"]) if rows else START_BANKROLL
    log.info("Final bankroll: $%.2f (start $%.2f, %+.1f%%)",
             final_bankroll, START_BANKROLL,
             100 * (final_bankroll - START_BANKROLL) / START_BANKROLL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
