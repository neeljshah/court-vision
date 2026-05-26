"""build_pnl_ledger_oof.py — OOF-grounded synthetic pnl_ledger.csv builder.

Replaces the prior `build_pnl_ledger_synth.py` ledger (which had fake player_ids='0'
and synthetic game_ids and a degenerate line==actual_stat causing all 50,985 bets
to settle as 'push') with a ledger built from the REAL pregame OOF parquet.

Inputs:
    data/cache/pregame_oof.parquet
        Columns: game_id, player_id, stat, oof_pred, actual, game_date, fold, season
        Real NBA IDs (player_id e.g. 203999, game_id e.g. '0022400123').
        ~335k rows; 99.92% have game_id (we SKIP any rows with empty game_id).

For each OOF row we emit ONE bet with realistic synthetic fields:
    line  = round((oof_pred + N(0, sigma_proxy * mult)) * 2) / 2   (half-point line)
            where sigma_proxy = std(actual - oof_pred) within (stat, fold)
    side  = OVER if oof_pred > line else UNDER
    book  = 'PP'      (so C4 PrizePicks join can fire on future bets)
    odds  = -119      (matches PP synthetic juice in clv.py)
    stake = 50.00
    status = won/lost/push using (side, actual, line)
    profit_loss = standard payout from -119

Sanity check: at most 10% of rows should be 'push'. If >10% we increase the
sigma multiplier and retry up to 3 times (multipliers tried: 0.5, 0.75, 1.0).

Output: REPLACES data/pnl_ledger.csv
Idempotent (seeded numpy=42).
"""

from __future__ import annotations

import csv
import datetime as dt
import logging
import os
import sys
import uuid
from typing import List, Optional

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

OOF_PATH    = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
LEDGER_PATH = os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv")

SEED            = 42
START_BANKROLL  = 10_000.0
STAKE           = 50.00
AMERICAN_ODDS   = -119
BOOK            = "PP"
PUSH_THRESHOLD  = 0.10    # max acceptable push fraction
SIGMA_MULTS     = [0.5, 0.75, 1.0]   # retry escalation if push frac > 10%

LEDGER_FIELDS = [
    "bet_id", "placed_at", "game_id", "player_id", "player", "team",
    "stat", "line", "side", "book", "american_odds", "stake",
    "model_pred", "model_prob", "model_edge", "kelly_pct",
    "status", "settled_at", "actual_stat", "profit_loss", "bankroll_after",
]

log = logging.getLogger("build_pnl_ledger_oof")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


# --------------------------------------------------------------------------- #
# helpers                                                                     #
# --------------------------------------------------------------------------- #
def _american_to_decimal(american: int) -> float:
    """Convert American odds to decimal."""
    if american < 0:
        return 1.0 + 100.0 / abs(american)
    return 1.0 + american / 100.0


DEC_ODDS = _american_to_decimal(AMERICAN_ODDS)
WIN_PROFIT = round(STAKE * (DEC_ODDS - 1.0), 2)   # +42.02 at -119 on $50


def _full_kelly(p: float, american: int) -> float:
    """Kelly criterion fraction for a binary bet.

    f* = (p*b - q) / b
    where b = decimal_odds - 1, q = 1 - p.
    Returned value is clipped to >= 0 (we don't lay).
    """
    b = _american_to_decimal(american) - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - p
    f = (p * b - q) / b
    return max(0.0, f)


def _settle(side: str, actual: float, line: float) -> str:
    """Return 'won' / 'lost' / 'push'."""
    if abs(actual - line) < 1e-9:
        return "push"
    if side == "OVER":
        return "won" if actual > line else "lost"
    return "won" if actual < line else "lost"


def _profit_for(status: str, stake: float) -> float:
    if status == "won":
        return round(stake * (DEC_ODDS - 1.0), 2)
    if status == "push":
        return 0.0
    return -round(stake, 2)


def _det_uuid(seed_str: str) -> str:
    """Seeded uuid4-shaped string (deterministic given seed_str)."""
    # uuid4 is non-deterministic; instead use uuid5 with a fixed namespace.
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed_str))


# --------------------------------------------------------------------------- #
# core builder                                                                #
# --------------------------------------------------------------------------- #
def _attempt_build(oof: pd.DataFrame, sigma_mult: float) -> tuple:
    """Build ledger rows with the given sigma multiplier.

    Returns (rows, push_frac).
    """
    rng = np.random.default_rng(SEED)

    # Per-(stat, fold) residual sigma
    oof = oof.copy()
    oof["resid"] = oof["actual"] - oof["oof_pred"]
    sigma_table = (
        oof.groupby(["stat", "fold"])["resid"]
        .std()
        .reset_index()
        .rename(columns={"resid": "sigma_proxy"})
    )
    log.info("Per-(stat, fold) sigma proxy (mult=%.2f):", sigma_mult)
    for _, r in sigma_table.iterrows():
        log.info("  %s/%s : sigma=%.4f", r["stat"], r["fold"], r["sigma_proxy"])

    df = oof.merge(sigma_table, on=["stat", "fold"], how="left")

    # Skip rows where game_id is empty/null
    df["game_id_str"] = df["game_id"].astype(str).str.strip()
    n_before = len(df)
    df = df[df["game_id_str"].str.len() > 0]
    df = df[df["game_id_str"] != "nan"]
    df = df[df["game_id_str"] != "None"]
    n_after = len(df)
    log.info("Filtered empty game_id: %d -> %d rows (%d dropped)",
             n_before, n_after, n_before - n_after)

    # Pre-generate per-row jitter noise (one draw per row, vectorised)
    jitter_std = df["sigma_proxy"].values * sigma_mult
    # Some rows may have NaN sigma_proxy if (stat, fold) was singleton; default to 1.0
    jitter_std = np.where(np.isnan(jitter_std), 1.0, jitter_std)
    noise = rng.normal(loc=0.0, scale=jitter_std)

    # Compute the line: round to nearest HALF-INTEGER (x.5) to avoid pushes
    # (actuals are integer counts; a half-point line cannot tie an integer).
    # raw_line = oof_pred + noise; line = floor(raw_line) + 0.5
    raw_line = df["oof_pred"].values + noise
    line = np.floor(raw_line) + 0.5
    # Clip line to be non-negative (counts can't be negative)
    line = np.maximum(line, 0.5)

    df = df.reset_index(drop=True)
    df["line"] = line

    # side: OVER if oof_pred > line else UNDER (tied -> OVER)
    df["side"] = np.where(df["oof_pred"].values > df["line"].values, "OVER", "UNDER")

    # status
    actual = df["actual"].values
    line_arr = df["line"].values
    side_arr = df["side"].values
    status_arr = np.empty(len(df), dtype=object)
    push_mask = np.abs(actual - line_arr) < 1e-9
    won_over_mask = (side_arr == "OVER") & (actual > line_arr)
    won_under_mask = (side_arr == "UNDER") & (actual < line_arr)
    won_mask = won_over_mask | won_under_mask
    status_arr[push_mask] = "push"
    status_arr[~push_mask & won_mask] = "won"
    status_arr[~push_mask & ~won_mask] = "lost"
    df["status"] = status_arr

    push_frac = float((df["status"] == "push").mean())
    log.info("Push fraction (sigma_mult=%.2f): %.4f (%d rows)",
             sigma_mult, push_frac, int((df["status"] == "push").sum()))

    if push_frac > PUSH_THRESHOLD:
        return None, push_frac

    # Build the full row dicts
    # placed_at = game_date - 30 min UTC; settled_at = game_date + 3h UTC
    # game_date is stored as object (ISO date string like '2023-11-06') in OOF; parse it.
    df["game_date_dt"] = pd.to_datetime(df["game_date"], errors="coerce", utc=True)
    # Default game tipoff at 19:30 UTC (~7:30pm ET)
    df["tip_dt"] = df["game_date_dt"] + pd.Timedelta(hours=19, minutes=30)
    df["placed_at_dt"] = df["tip_dt"] - pd.Timedelta(minutes=30)
    df["settled_at_dt"] = df["tip_dt"] + pd.Timedelta(hours=3)

    # Sort by placed_at to make bankroll progression read naturally
    df = df.sort_values("placed_at_dt", kind="mergesort").reset_index(drop=True)

    # model_edge = (oof_pred - line) / max(line, 1.0)
    line_denom = np.maximum(df["line"].values, 1.0)
    df["model_edge"] = (df["oof_pred"].values - df["line"].values) / line_denom

    # model_prob = 0.50 + clip(model_edge, -0.30, 0.30)
    df["model_prob"] = 0.50 + np.clip(df["model_edge"].values, -0.30, 0.30)

    # kelly: full_kelly(model_prob, -119) capped at 0.05
    kelly_arr = np.array(
        [_full_kelly(p, AMERICAN_ODDS) for p in df["model_prob"].values],
        dtype=float,
    )
    df["kelly_pct"] = np.minimum(kelly_arr, 0.05)

    # profit
    profit_arr = np.where(
        df["status"].values == "won", WIN_PROFIT,
        np.where(df["status"].values == "lost", -STAKE, 0.0)
    )
    df["profit_loss"] = profit_arr

    # cumulative bankroll
    df["bankroll_after"] = START_BANKROLL + np.cumsum(df["profit_loss"].values)

    # Now construct the row dicts in the canonical schema order
    rows: List[dict] = []
    for i, r in df.iterrows():
        pid_int = int(r["player_id"])
        gid     = str(r["game_id_str"])
        stat    = str(r["stat"]).lower()
        bet_id  = _det_uuid(f"oof|{gid}|{pid_int}|{stat}")

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

    return rows, push_frac


def build_rows() -> List[dict]:
    if not os.path.exists(OOF_PATH):
        raise RuntimeError(f"pregame_oof.parquet not found at {OOF_PATH}")

    oof = pd.read_parquet(OOF_PATH)
    log.info("Loaded pregame_oof: shape=%s columns=%s",
             oof.shape, list(oof.columns))

    last_push_frac: Optional[float] = None
    for mult in SIGMA_MULTS:
        log.info("== Attempting build with sigma_mult=%.2f ==", mult)
        rows, push_frac = _attempt_build(oof, sigma_mult=mult)
        last_push_frac = push_frac
        if rows is not None:
            log.info("Accepted sigma_mult=%.2f -> push_frac=%.4f <= %.2f gate",
                     mult, push_frac, PUSH_THRESHOLD)
            return rows
        log.warning("sigma_mult=%.2f produced push_frac=%.4f > %.2f — retrying",
                    mult, push_frac, PUSH_THRESHOLD)

    raise RuntimeError(
        f"All {len(SIGMA_MULTS)} sigma multipliers failed the push-frac gate "
        f"(last push_frac={last_push_frac:.4f} > {PUSH_THRESHOLD}). "
        "Line jitter still too small — investigate sigma_proxy."
    )


def main() -> int:
    rows = build_rows()

    # Atomic write
    tmp_path = LEDGER_PATH + ".tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=LEDGER_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    os.replace(tmp_path, LEDGER_PATH)

    log.info("Wrote %d rows -> %s", len(rows), LEDGER_PATH)

    # Quick post-write sanity check
    n_won  = sum(1 for r in rows if r["status"] == "won")
    n_lost = sum(1 for r in rows if r["status"] == "lost")
    n_push = sum(1 for r in rows if r["status"] == "push")
    log.info("status: won=%d (%.1f%%) lost=%d (%.1f%%) push=%d (%.1f%%)",
             n_won, 100 * n_won / len(rows),
             n_lost, 100 * n_lost / len(rows),
             n_push, 100 * n_push / len(rows))
    final_bankroll = float(rows[-1]["bankroll_after"]) if rows else START_BANKROLL
    log.info("Final bankroll: $%.2f (start $%.2f, %+.1f%%)",
             final_bankroll, START_BANKROLL,
             100 * (final_bankroll - START_BANKROLL) / START_BANKROLL)

    return 0


if __name__ == "__main__":
    sys.exit(main())
