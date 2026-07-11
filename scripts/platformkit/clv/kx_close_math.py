"""scripts.platformkit.clv.kx_close_math -- honest PROXY CLV math for a
kx-ticker-derived last-tick close (W1 fix: paper_ingame 436/436 no_close).

WHY THIS EXISTS (do not route a kx close through clv_ledger.compute_clv):
clv_ledger.compute_clv -> odds_shop.devig_twoway -> eval_gate.shin.shin_devig
asserts booksum > 1.0 (it solves for a bookmaker's OVERROUND). A kx-derived
close is the NAIVE COMPLEMENT of a single venue's own price
(1/p_home, 1/(1-p_home)); its booksum is p_home + (1-p_home) == 1.0 EXACTLY
(mod float noise on either side of 1.0) -- it is vig-free BY CONSTRUCTION and
can never reliably satisfy shin_devig's assert. Verified empirically (W1
diagnosis): passing a kx-derived closing_decimal_home/away straight into
paper_ingame.grade_live's Level-1 path silently falls through grade_one's
try/except to clv_status='no_close' every time. Devig is also conceptually
wrong here: a single vig-free venue quote's fair probability IS the quote
itself, nothing to devig.

This module computes CLV the honest way for that case: fair_close =
close_prob_home (side='home') or its complement (side='away'); no devig.
Every row this touches is stamped clv_status='proxy' + clv_is_proxy=True
(grade_paper_one's own proxy vocabulary) -- NEVER 'true_close'. Consumers
(clv_scoreboard, clv_result_reconciler) must keep this tier SEPARATE from
the true_close 'measurable' bucket (see is_measurable_proxy).

Read-only: never mutates a ledger row or writes to disk. Never raises.

INVARIANTS: scripts/platformkit/clv/ only; <=300 LOC; ASCII; no network.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/clv/test_kx_close_math.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from scripts.platformkit.clv import kx_ticker_close as _kx
from scripts.platformkit.clv_ledger import is_clv_suspect as _is_clv_suspect

# The ONLY clv_status this module ever writes -- distinct from grade_one's
# 'true_close'/'no_close'. Never promoted, never merged into true_close.
PROXY_STATUS = "proxy"


def close_decimals(close_prob_home: float) -> Optional[Tuple[float, float]]:
    """Naive complement decimal-odds pair (close_home, close_away) from a
    home-side close probability. Same convention as
    kx_close_fallback.lookup_close_legs_kx. None for a degenerate/out-of-
    range probability. Never raises."""
    try:
        p = float(close_prob_home)
    except (TypeError, ValueError):
        return None
    if not (0.0 < p < 1.0):
        return None
    return (1.0 / p, 1.0 / (1.0 - p))


def clv_pct_no_devig(side: str, taken_decimal: float,
                     close_prob_home: float) -> Optional[float]:
    """CLV%% (positive = better number than the close), same sign convention
    as clv_ledger.compute_clv, computed WITHOUT devig (see module
    docstring). None on invalid input. Never raises."""
    s = str(side).strip().lower()
    if s not in ("home", "away"):
        return None
    try:
        p_home = float(close_prob_home)
        dec = float(taken_decimal)
    except (TypeError, ValueError):
        return None
    if not (0.0 < p_home < 1.0) or dec <= 1.0:
        return None
    fair = p_home if s == "home" else (1.0 - p_home)
    taken_p = 1.0 / dec
    return round((fair - taken_p) / taken_p * 100.0, 6)


def proxy_clv_for_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a corrected COPY of *row* carrying an honestly-labelled kx-
    proxy CLV (clv_status='proxy', clv_is_proxy=True, fair_close_prob set
    so clv_result_reconciler's close-implied expectation math works) when a
    derived kx close exists for this row's ticker. None on any miss (no
    close derived yet, missing side/taken_decimal, degenerate probability).
    Never mutates *row*; never raises."""
    ticker = str(row.get("game_id") or "")
    sport = str(row.get("sport") or "").lower()
    if not ticker or not sport:
        return None
    try:
        rec = _kx.get_close_prob(ticker, sport)
    except Exception:  # noqa: BLE001 -- an unreadable corpus is an honest miss
        return None
    if rec is None:
        return None
    try:
        p_home = float(rec.get("close_prob"))
    except (TypeError, ValueError):
        return None
    side = str(row.get("side", "")).strip().lower()
    try:
        taken = float(row.get("taken_decimal"))
    except (TypeError, ValueError):
        return None
    pair = close_decimals(p_home)
    clv_pct = clv_pct_no_devig(side, taken, p_home)
    if pair is None or clv_pct is None:
        return None
    ch, ca = pair
    fair = p_home if side == "home" else (1.0 - p_home)
    out = dict(row)
    out["closing_decimal_home"] = ch
    out["closing_decimal_away"] = ca
    out["fair_close_prob"] = round(fair, 8)
    out["clv_pct"] = clv_pct
    out["beat_close"] = clv_pct > 0.0
    out["clv_is_proxy"] = True
    out["clv_status"] = PROXY_STATUS
    out["close_kind"] = _kx.CLOSE_KIND
    out["clv_note"] = ("CLV from kx-ticker last-tick close proxy (no devig -- "
                        "a single venue price is vig-free by construction)")
    out["settled_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def is_measurable_proxy(row: Dict[str, Any]) -> bool:
    """True iff *row* is a kx-proxy-measurable CLV row: clv_status=='proxy'
    with a usable clv_pct, and not an off-market/suspect price. Mutually
    exclusive with clv_scoreboard._is_measurable (that checks 'true_close')
    -- a row is never counted in both tiers."""
    return (row.get("clv_status") == PROXY_STATUS
            and row.get("clv_pct") is not None
            and bool(row.get("clv_is_proxy"))
            and not _is_clv_suspect(row))


def enrich_paper_ingame_no_close(row: Dict[str, Any]) -> Dict[str, Any]:
    """READ-TIME historical recovery: for a paper_ingame row still labelled
    clv_status=='no_close', attempt the kx-derived proxy close via
    proxy_clv_for_row. Every other row (wrong channel/status, or a miss)
    passes through byte-identical. Never mutates the ledger; never raises."""
    if row.get("channel") != "paper_ingame" or row.get("clv_status") != "no_close":
        return row
    try:
        corrected = proxy_clv_for_row(row)
    except Exception:  # noqa: BLE001 -- a bad row is an honest pass-through
        return row
    return corrected if corrected is not None else row


__all__ = [
    "PROXY_STATUS", "close_decimals", "clv_pct_no_devig", "proxy_clv_for_row",
    "is_measurable_proxy", "enrich_paper_ingame_no_close",
]
