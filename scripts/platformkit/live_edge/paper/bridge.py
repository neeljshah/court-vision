"""scripts.platformkit.live_edge.paper.bridge -- shadow prediction row ->
paper-bet row in the EXISTING clv_ledger (never a new ledger/CLV math).

Pipeline: resolve_identity() recovers the event_key + same-book entry price
already sitting in the shadow row's own capture provenance; select() is a
PARAMETERIZED divergence gate (same report-only discipline as
clv_trial.selection_policy -- not a validated +EV trigger); shadow_row_to_bet
calls clv_ledger.record_bet VERBATIM (the paper ledger's own write path,
imported not reimplemented) and tags channel=CHANNEL_LIVE_EDGE_PAPER on the
in-memory copy only (mirrors pm_trading.paper_autobet's own established
pattern: the persisted open row carries executed=False; channel is stamped
on the settled twin / summary, never mutated back onto the on-disk open row).

CLV DISCIPLINE (binding): edge_claimed is never set True here; this module
records candidates for LATER grading (clv_scoreboard/clv_result_reconciler,
imported not reimplemented), it does not compute or claim a CLV number.

INVARIANTS: stdlib + clv_ledger only; ASCII; <=300 LOC; never writes the
claims journal; never mutates shadow_ledger rows; a row that cannot resolve
or cannot price is an honest skip (returned status), never a fabricated bet.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from scripts.platformkit import clv_ledger
from scripts.platformkit.live_edge.paper.resolve_identity import resolve_identity

CHANNEL_LIVE_EDGE_PAPER = "paper_live_edge"
DEFAULT_THRESHOLD = 0.03


def select(shadow_row: Dict[str, Any], *, threshold: float = DEFAULT_THRESHOLD,
           pred_field: str = "conditioned_pred") -> bool:
    """PARAMETERIZED selection hook: |model_pred - market_price_at_capture|
    >= threshold. Same divergence-gate shape as clv_trial.selection_policy;
    a report-only hook, NOT a validated +EV trigger -- selecting the biggest-
    divergence rows selects for noise as readily as signal."""
    pred = shadow_row.get(pred_field)
    price = shadow_row.get("market_price")
    if pred is None or price is None:
        return False
    return abs(float(pred) - float(price)) >= threshold


def shadow_row_to_bet(shadow_row: Dict[str, Any], identity: Dict[str, Any], *,
                      stake_units: float = 1.0, path=None) -> Optional[Dict[str, Any]]:
    """One resolved+selected shadow row -> one OPEN paper-bet ledger row via
    clv_ledger.record_bet (reused verbatim, never reimplemented). None when
    the identity lacks a usable two-way decimal price/side -- an honest skip,
    never a fabricated bet."""
    side = identity.get("side")
    dec = identity.get("odds_decimal")
    if side not in ("home", "away") or dec is None:
        return None
    try:
        dec_f = float(dec)
    except (TypeError, ValueError):
        return None
    if dec_f <= 1.0:
        return None
    ek = identity["event_key"]
    matchup = f"{identity['home_raw']}@{identity['away_raw']}"
    rec = clv_ledger.record_bet(
        ek.sport, matchup, side, str(identity.get("book") or "unknown"), dec_f,
        model_prob=shadow_row.get("conditioned_pred"), stake_units=stake_units,
        market=ek.market_family, event_id=str(shadow_row.get("game")),
        game_date=ek.date, path=path,
    )
    rec = dict(rec)
    rec["channel"] = CHANNEL_LIVE_EDGE_PAPER
    rec["event_key"] = list(ek)
    rec["is_same_book_capture"] = True  # entry price came from the row's OWN book
    rec["mechanism_applied"] = shadow_row.get("mechanism_applied")
    return rec


def run_bridge_row(shadow_row: Dict[str, Any], *, threshold: float = DEFAULT_THRESHOLD,
                    stake_units: float = 1.0, path=None, line_history_dir=None) -> Dict[str, Any]:
    """One shadow row -> {status, ...}. status is one of
    'ungradeable_identity' / 'not_selected' / 'ungradeable_price' / 'recorded'
    -- every row is accounted for, none silently dropped. line_history_dir is
    an injectable override for tests; production callers omit it."""
    kwargs = {} if line_history_dir is None else {"line_history_dir": line_history_dir}
    identity = resolve_identity(shadow_row, **kwargs)
    if identity is None:
        return {"status": "ungradeable_identity", "game": shadow_row.get("game"),
                "sport": shadow_row.get("sport")}
    ek = identity["event_key"]
    if not select(shadow_row, threshold=threshold):
        return {"status": "not_selected", "event_key": list(ek)}
    bet = shadow_row_to_bet(shadow_row, identity, stake_units=stake_units, path=path)
    if bet is None:
        return {"status": "ungradeable_price", "event_key": list(ek)}
    return {"status": "recorded", "event_key": list(ek), "bet_id": bet["bet_id"], "bet": bet}


__all__ = ["select", "shadow_row_to_bet", "run_bridge_row",
           "CHANNEL_LIVE_EDGE_PAPER", "DEFAULT_THRESHOLD"]
