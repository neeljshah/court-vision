"""frontend.exec_support -- pure helpers for manual paper-trade placement.

Split out of frontend.exec_routes to keep each file <=300 LOC. This module owns the
stake sizing, store-row lookup, freshness check, idempotency key, and the public
row projection. NO FastAPI here -- pure functions only.

HONESTY: UNITS ONLY. The public row carries NO $ / dollar / stake / roi / pnl /
bankroll field -- sizing is ``stake_units`` and edges are EV/CLV (probability
space). A stale snapshot (age past SLA / unparseable generated_at) is fail-closed.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII-only; no secrets.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CHANNEL = "paper_manual"
PRICE_EPS = 1e-6


def snapshot_age_sec(env: Any) -> Optional[float]:
    """Seconds since the snapshot's generated_at, or None if unparseable.

    Reads ``generated_at`` off the store envelope (lane B owns the store; we only
    READ it here). None -> we cannot prove freshness, so the caller treats it as
    stale (fail-closed), never as fresh.
    """
    raw = getattr(env, "generated_at", None)
    if not raw:
        return None
    try:
        gen = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if gen.tzinfo is None:
        gen = gen.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - gen).total_seconds()


def quarter_kelly(model_prob: Optional[float], taken_decimal: float) -> float:
    """Quarter-Kelly fraction (units) for one two-way bet: 0.25 * f*, floored at
    0 (never a negative-EV line). model_prob unknown -> 0.0 (flat unit only)."""
    if model_prob is None:
        return 0.0
    try:
        p = float(model_prob)
        b = float(taken_decimal) - 1.0
    except (TypeError, ValueError):
        return 0.0
    if b <= 0.0 or not (0.0 < p < 1.0):
        return 0.0
    f_star = (p * b - (1.0 - p)) / b
    if f_star <= 0.0 or math.isnan(f_star):
        return 0.0
    return round(0.25 * f_star, 6)


def find_market(env: Any, game_id: str, market_type: str, side: str,
                book: str, taken_decimal: float) -> Optional[Any]:
    """Return the MarketRow in *env* matching the placement, or None.

    Match on (game_id, market_type, side, book) plus an odds price match within
    PRICE_EPS -- so a stale/fabricated price is rejected like a fake game.
    """
    for m in getattr(env, "markets", []) or []:
        if str(getattr(m, "game_id", "")) != str(game_id):
            continue
        if str(getattr(m, "market_type", "")) != str(market_type):
            continue
        if str(getattr(m, "side", "")) != str(side):
            continue
        if str(getattr(m, "book", "")) != str(book):
            continue
        odds = getattr(m, "odds", None)
        if odds is None:
            continue
        if abs(float(odds) - float(taken_decimal)) <= PRICE_EPS:
            return m
    return None


def find_edge(env: Any, game_id: str, market_type: str, side: str) -> Optional[Any]:
    """Return the EdgeRow in *env* for this market (stamped onto the bet)."""
    for e in getattr(env, "edges", []) or []:
        if (str(getattr(e, "game_id", "")) == str(game_id)
                and str(getattr(e, "market_type", "")) == str(market_type)
                and str(getattr(e, "side", "")) == str(side)):
            return e
    return None


def matchup_for(env: Any, game_id: str) -> str:
    """Derive an away@home matchup string for *game_id* (fallback: game_id)."""
    for p in getattr(env, "predictions", []) or []:
        if str(getattr(p, "game_id", "")) == str(game_id):
            away = str(getattr(p, "away", ""))
            home = str(getattr(p, "home", ""))
            if away or home:
                return "%s@%s" % (away, home)
    return str(game_id)


def idem_key(sport: str, game_id: str, market_type: str, side: str,
             book: str) -> str:
    """sport|game_id|market_type|side|book|YYYY-MM-DD (UTC day)."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return "|".join([str(sport), str(game_id), str(market_type),
                     str(side), str(book), day])


def existing_open(key: str, ledger_path: Optional[Path],
                  target_bet_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return an existing OPEN ledger row matching this placement, or None.

    Matches on the durable ``bet_id`` (game-anchored, survives the UTC-midnight
    boundary -- P1-8) OR the legacy same-day ``idem_key``, so a re-submit returns
    the existing open row instead of minting a phantom duplicate (PE-P0-04).
    """
    try:
        from scripts.platformkit.clv_ledger_io import load_rows
        rows = load_rows(path=ledger_path)
    except Exception as exc:  # noqa: BLE001 -- a read miss is "no existing row"
        logger.warning("exec_support: load_rows failed: %s", exc)
        return None
    for r in rows:
        if str(r.get("status", "open")).lower() != "open":
            continue
        if target_bet_id and r.get("bet_id") == target_bet_id:
            return r
        if r.get("idem_key") == key:
            return r
    return None


def fnum(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def public_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Project a ledger row to the dashboard shape (no $ / stake / roi fields)."""
    model_prob = fnum(row.get("model_prob"))
    taken_decimal = fnum(row.get("taken_decimal"))
    model_ev = fnum(row.get("ev"))
    if model_ev is None and model_prob is not None and taken_decimal is not None:
        model_ev = round(model_prob * taken_decimal - 1.0, 6)
    return {
        "sport": str(row.get("sport", "")),
        "game_id": str(row.get("game_id", "")),
        "matchup": str(row.get("matchup", "")),
        "market_type": str(row.get("market_type", "")),
        "side": str(row.get("side", "")),
        "taken_book": str(row.get("taken_book", "")),
        "taken_decimal": taken_decimal,
        "model_prob": model_prob,
        "model_ev": model_ev,
        "tier": (str(row.get("tier")) if row.get("tier") is not None else None),
        "stake_units": fnum(row.get("stake_units")),
        "channel": str(row.get("channel", CHANNEL)),
        "idem_key": row.get("idem_key"),
        "bet_id": row.get("bet_id"),
        "status": str(row.get("status", "open")).lower(),
        "executed": False,  # INVARIANT: paper-only
        "ts": str(row.get("ts", "")),
    }


__all__ = [
    "CHANNEL", "PRICE_EPS", "snapshot_age_sec", "quarter_kelly", "find_market",
    "find_edge", "matchup_for", "idem_key", "existing_open", "fnum", "public_row",
]
