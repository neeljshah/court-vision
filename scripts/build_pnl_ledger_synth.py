"""build_pnl_ledger_synth.py — Build synthetic pnl_ledger.csv from prop_residuals.json.

Converts ``data/models/prop_residuals.json`` (~81k residual rows) into a full
synthetic betting ledger compatible with the schema of ``data/pnl_ledger.csv``,
so R9 CLV / strategy probes (C3-C7) have enough data to run.

Spec (per orchestrator):
* one row per residual (use the residual's pinned `direction`; do NOT synthesize
  the opposite side)
* drop rows where predicted == 0 or actual == 0 ("missed prediction" voids)
* deterministic / idempotent — seed numpy with 42
* preserve the pre-existing live bet (May 24, Jokic) at the end
* uniform `placed_at` distribution across 2023-11-01 .. 2025-04-30
* schema must match canonical ledger header exactly

Output: REPLACES data/pnl_ledger.csv
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import logging
import os
import sys
import uuid
from typing import List, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

RESIDUALS_PATH = os.path.join(PROJECT_DIR, "data", "models", "prop_residuals.json")
LEDGER_PATH    = os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv")

SEED           = 42
SEASON_START   = dt.datetime(2023, 11, 1)
SEASON_END     = dt.datetime(2025, 4, 30)
START_BANKROLL = 10_000.0
STAKE          = 50.00
AMERICAN_ODDS  = -110
WIN_PROFIT     = 45.45   # +45.45 at -110 on $50 stake
LOSS_PROFIT    = -50.00
PUSH_PROFIT    = 0.0
BOOK           = "DK"

LEDGER_FIELDS = [
    "bet_id", "placed_at", "game_id", "player_id", "player", "team",
    "stat", "line", "side", "book", "american_odds", "stake",
    "model_pred", "model_prob", "model_edge", "kelly_pct",
    "status", "settled_at", "actual_stat", "profit_loss", "bankroll_after",
]

log = logging.getLogger("build_pnl_ledger_synth")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


def _det_uuid(seed_str: str) -> str:
    """Deterministic uuid4-shaped string from a seed."""
    h = hashlib.md5(seed_str.encode("utf-8")).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _det_game_id(idx: int) -> str:
    """10-char numeric game_id, deterministic from index."""
    h = hashlib.md5(f"game-{idx}".encode("utf-8")).hexdigest()
    n = int(h[:10], 16) % (10**10)
    return f"{n:010d}"


def _load_existing_live_bet(path: str) -> Optional[dict]:
    """Read the pre-existing 1-row live bet from current ledger (if any)."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            return None
        # The seed live bet has a distinctive 2026-05-24 placed_at + 'Nikola Jokic' player
        for r in rows:
            if "2026" in (r.get("placed_at") or "") or "Jokic" in (r.get("player") or ""):
                return r
        # otherwise keep the first row as the live bet
        return rows[0]
    except (OSError, csv.Error) as exc:
        log.warning("Could not read existing ledger %s: %s", path, exc)
        return None


def _settle_status(direction: str, actual: float, line: float) -> str:
    """Return 'won' / 'lost' / 'push' given side + actual + line."""
    d = (direction or "").lower().strip()
    if abs(actual - line) < 1e-9:
        return "push"
    if d == "over":
        return "won" if actual > line else "lost"
    if d == "under":
        return "won" if actual < line else "lost"
    return "lost"  # unknown direction -> mark as lost


def _profit_for(status: str) -> float:
    if status == "won":
        return WIN_PROFIT
    if status == "push":
        return PUSH_PROFIT
    return LOSS_PROFIT


def _kelly_pct(edge_pct: float) -> Optional[float]:
    """Crude Kelly at -110 (p_win - q/b) using edge_pct as model_edge proxy.

    Not load-bearing — strategy probes (C5/C6) recompute from quantiles.
    Set to None when edge can't be inferred.
    """
    if edge_pct is None:
        return None
    try:
        e = float(edge_pct)
    except (TypeError, ValueError):
        return None
    # Cap to a sensible band
    if abs(e) > 50:
        return None
    from src.prediction.betting_portfolio import clamp_kelly_pct
    k = clamp_kelly_pct(abs(e) * 0.005)
    return None if k is None else round(k, 4)


def build_rows() -> List[dict]:
    if not os.path.exists(RESIDUALS_PATH):
        raise RuntimeError(f"prop_residuals.json not found at {RESIDUALS_PATH}")

    with open(RESIDUALS_PATH, encoding="utf-8") as fh:
        residuals = json.load(fh)

    log.info("Loaded %d residuals", len(residuals))

    rng = np.random.default_rng(SEED)

    # Pre-compute uniform placed_at across the 2-season window
    span_secs = int((SEASON_END - SEASON_START).total_seconds())
    # Generate one offset per residual (we'll drop voids after)
    offsets = rng.integers(low=0, high=span_secs, size=len(residuals))

    rows: List[dict] = []
    bankroll = START_BANKROLL
    n_void = 0
    n_zero_line = 0

    for idx, r in enumerate(residuals):
        stat      = (r.get("stat") or "").lower().strip()
        predicted = r.get("predicted")
        actual    = r.get("actual")
        line      = r.get("line")
        edge_pct  = r.get("edge_pct")
        direction = (r.get("direction") or "").lower().strip()

        # void rule: drop if predicted == 0 or actual == 0
        if predicted == 0 or actual == 0:
            n_void += 1
            continue

        # also skip if line == 0 (degenerate prop)
        if line is None or float(line) == 0.0:
            n_zero_line += 1
            continue

        placed_at = SEASON_START + dt.timedelta(seconds=int(offsets[idx]))
        settled_at = placed_at + dt.timedelta(hours=3)

        bet_id    = _det_uuid(f"synth-{idx}-{stat}")
        game_id   = _det_game_id(idx)
        # player_id absent in residuals — use 0 for name-only mode (per spec)
        player_id = 0
        player    = f"Player_{idx}"
        team      = "SYN"

        status   = _settle_status(direction, float(actual), float(line))
        profit   = _profit_for(status)
        bankroll = round(bankroll + profit, 2)

        side_u = "OVER" if direction == "over" else "UNDER"

        rows.append({
            "bet_id":         bet_id,
            "placed_at":      placed_at.isoformat(timespec="seconds"),
            "game_id":        game_id,
            "player_id":      player_id,
            "player":         player,
            "team":           team,
            "stat":           stat,
            "line":           f"{float(line):.2f}",
            "side":           side_u,
            "book":           BOOK,
            "american_odds":  AMERICAN_ODDS,
            "stake":          f"{STAKE:.2f}",
            "model_pred":     f"{float(predicted):.4f}",
            "model_prob":     "",   # not provided
            "model_edge":     f"{float(edge_pct):+.4f}" if edge_pct is not None else "",
            "kelly_pct":      _kelly_pct(edge_pct) if edge_pct is not None else "",
            "status":         status,
            "settled_at":     settled_at.isoformat(timespec="seconds"),
            "actual_stat":    f"{float(actual):.4f}",
            "profit_loss":    f"{profit:+.2f}",
            "bankroll_after": f"{bankroll:.2f}",
        })

    log.info("Built %d synthetic ledger rows (voided %d, dropped zero-line %d)",
             len(rows), n_void, n_zero_line)
    return rows


def main() -> int:
    existing_live_bet = _load_existing_live_bet(LEDGER_PATH)

    rows = build_rows()

    # Sort by placed_at ascending so bankroll progression reads naturally
    rows.sort(key=lambda r: r["placed_at"])

    # Recompute bankroll progression after sort (since order changed)
    bankroll = START_BANKROLL
    for r in rows:
        profit = float(r["profit_loss"])
        bankroll = round(bankroll + profit, 2)
        r["bankroll_after"] = f"{bankroll:.2f}"

    # Append the preserved live bet at end (if present)
    if existing_live_bet:
        # Sanitize: ensure all canonical fields present, drop any extras
        live = {k: (existing_live_bet.get(k, "") or "") for k in LEDGER_FIELDS}
        # If bankroll_after looks stale (e.g. 1043.48 from old single-bet ledger),
        # leave it as-is — it's the live bet's snapshot value, not the synth chain.
        rows.append(live)
        log.info("Preserved existing live bet at end: %s %s %s",
                 live.get("placed_at"), live.get("player"), live.get("stat"))

    # Atomic write
    tmp_path = LEDGER_PATH + ".tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=LEDGER_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    os.replace(tmp_path, LEDGER_PATH)

    log.info("Wrote %d rows -> %s", len(rows), LEDGER_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
