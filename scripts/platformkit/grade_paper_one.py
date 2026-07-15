"""scripts.platformkit.grade_paper_one -- grade_one() + its outcome/unit/settle-
key helpers, split out of grade_paper.py to keep both modules under the
platform's <=300 LOC/file rail (LOC-rail fix, C1 retry).

DEVIATION (Fable-authorized, this split only): a relocated function resolves
free variables in its DEFINING module's __globals__, so a plain
``from ... import close_from_store as _close_from_store`` here would make
test_grade_paper.py's ``monkeypatch.setattr(gp, "_close_from_store", ...)``
invisible to grade_one (the patch lands on the ``grade_paper`` module object,
not this one). grade_one() therefore reaches it as ``_gp._close_from_store``
via a LOCAL import of the grade_paper module (breaks the load-time cycle,
same precedent as grade_paper_asof.mlb_ticker_fallback_match's own local
``from scripts.platformkit import grade_paper as _gp`` import) so the
attribute lookup happens at call time, after any monkeypatch has landed.
_outcome/_unit_result/_settle_key carry no such coupling (nothing patches
them) and stay ordinary module-local names. grade_paper.py re-imports all
four names (grade_one, _outcome, _unit_result, _settle_key) so existing
callers -- grade_open_bets's own ``_settle_key`` use, prop_settler.py's direct
``from scripts.platformkit.grade_paper import _settle_key, _unit_result``,
and settlement_correctness_audit.py's ``_gp._outcome`` / ``_gp._unit_result``
attribute access -- see byte-identical behavior.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.platformkit import clv_ledger as _clv

logger = logging.getLogger(__name__)

# Sports that can draw in regulation (real push). NBA/MLB cannot -> equal final = void.
_CAN_DRAW = ("soccer", "soccer_intl")


def _outcome(sport: str, side: str, home_score: int, away_score: int) -> Optional[str]:
    """Moneyline result for the backed two-way *side*.

    Returns "win" / "loss"; "push" only for a sport that can draw (soccer 90-min);
    "void" when an equal final score appears for a sport that CANNOT draw (a data
    glitch / not-actually-final feed -- never fabricated into a push or a win).
    """
    if home_score == away_score:
        if str(sport).lower() in _CAN_DRAW:
            return "push"  # legitimate draw -> refund
        return "void"  # NBA/MLB cannot tie: contradictory data, not a result
    home_won = home_score > away_score
    if side == "home":
        return "win" if home_won else "loss"
    return "win" if not home_won else "loss"


def _unit_result(outcome: Optional[str], taken_decimal: float,
                 stake_units: float) -> Optional[float]:
    """UNITS won/lost at the taken price (NOT dollars). Push -> 0.0; void -> None.

    win -> +(decimal-1)*stake_units; loss -> -stake_units; push -> 0.0. A pure unit
    count -- NO bankroll, NO money -- so history shows a unit record, never dollars.
    """
    if outcome == "win":
        return round((float(taken_decimal) - 1.0) * float(stake_units), 6)
    if outcome == "loss":
        return round(-float(stake_units), 6)
    if outcome == "push":
        return 0.0
    return None  # void / undecided -> no unit result


def _settle_key(bet: Dict[str, Any]) -> str:
    """Stable identity for one open bet, used to dedupe settlements (idempotency).

    Prefers the durable ``bet_id`` (independent of the write ts) so a same-bet
    re-record across a tick / UTC-midnight boundary settles ONCE. Falls back to
    the legacy ts-bearing tuple only for rows minted before bet_id existed.
    """
    if bet.get("bet_id"):
        return str(bet["bet_id"])
    keys = ("sport", "matchup", "side", "taken_book", "taken_decimal", "ts")
    return "|".join(str(bet.get(k, "")) for k in keys)


def grade_one(
    bet: Dict[str, Any],
    game: Dict[str, Any],
    *,
    _line_store_base: Optional[Path] = None,
) -> Dict[str, Any]:
    """SETTLED twin of *bet* from FINAL *game* (see grade_paper's module CLOSE
    RESOLUTION PRECEDENCE docstring). *_line_store_base* overrides the history
    dir for tests."""
    hs, as_ = int(game["home_score"]), int(game["away_score"])
    sport = str(bet.get("sport", "")).strip().lower()
    side = str(bet.get("side", "")).strip().lower()
    outcome = _outcome(sport, side, hs, as_)
    stake_units = float(bet.get("stake_units", 1.0) or 1.0)
    taken_decimal = float(bet["taken_decimal"])
    settled = dict(bet)

    # Level 1: closing decimals already on the bet. clv_is_proxy is EXPLICIT.
    ch = bet.get("closing_decimal_home")
    ca = bet.get("closing_decimal_away")
    is_proxy: bool = False
    close_book_home: Optional[str] = None
    close_book_away: Optional[str] = None

    if ch is None or ca is None:  # Levels 2+3: line_store captured close.
        from scripts.platformkit import grade_paper as _gp  # local: breaks the cycle
        sr = _gp._close_from_store(bet, base=_line_store_base)
        if sr is not None:
            ch, ca, is_true, close_book_home, close_book_away = sr
            is_proxy = not is_true

    if ch is None or ca is None:  # Level 4: explicit last-observed proxy on bet.
        ch = bet.get("last_decimal_home") or bet.get("close_proxy_home")
        ca = bet.get("last_decimal_away") or bet.get("close_proxy_away")
        if ch is not None and ca is not None:
            is_proxy = True

    if ch is not None and ca is not None:
        try:
            settled = _clv.settle_closing_line(settled, float(ch), float(ca))
        except Exception:  # noqa: BLE001 - a degenerate close (e.g. an arbitrage-
            # implying booksum<1 proxy quote -- shin_devig raises rather than fabricate
            # a fair prob) must never crash the grader. Treat exactly like Level 5 (no
            # usable close): win/loss still settles, CLV honestly unavailable.
            logger.debug("grade_one: bad close %r/%r for %r; falling to no-close",
                        ch, ca, bet.get("matchup"), exc_info=True)
            ch = ca = None
    if ch is not None and ca is not None:
        settled["clv_is_proxy"] = bool(is_proxy)
        settled["clv_status"] = "proxy" if is_proxy else "true_close"
        # suspect_close guard (pre-registered 2026-07-15): a degenerate close join
        # or off-market taken price fabricates a huge fake CLV (e.g. +2918% from a
        # 56.0 taken vs a 1.82 close). Stamp such rows suspect_close so they keep the
        # raw clv_pct but drop out of every true-close aggregate (is_clv_suspect
        # short-circuits on this status). clv_is_proxy is left as-is (a separate axis).
        if _clv.is_suspect_close(
            taken_decimal, settled.get("clv_pct"), settled.get("fair_close_prob")
        ):
            settled["clv_status"] = "suspect_close"
        # Same-venue CLV restriction needs to know WHICH book supplied the close
        # (line_store mixes books with zero venue awareness -- see
        # docs/research/PROPOSED_same_venue_close_restriction.md). Only line_store
        # (levels 2+3) knows a per-side book; Level 1 (bet already carries its own
        # closing_decimal_*) and Level 4 (bare last_decimal_* proxy) have none --
        # left None honestly, never guessed.
        settled["close_book_home"] = close_book_home
        settled["close_book_away"] = close_book_away
        # PT-CROSSVENUE fix (2026-07-08b): stamp close_source (book name if it
        # matches the bet's OWN taken_book, else "cross_venue_fallback") so
        # basis diagnostics (_is_same_venue_close / pm_close_capture.
        # _resolved_keys) can tell same-venue from cross-venue -- previously
        # always None here, so every row read as cross-venue basis regardless
        # of the real match. Same side-aware book pick as the pre-existing
        # execution_quality_math.same_venue_bucket, reused for consistency.
        side_book = close_book_home if side == "home" else (
            close_book_away if side == "away" else None)
        taken = str(bet.get("taken_book") or "").strip().lower()
        if side_book:
            book = str(side_book).strip().lower()
            settled["close_source"] = book if (taken and taken == book) else "cross_venue_fallback"
        else:
            # A close WAS resolved (ch/ca not None) but the resolving path (Level 1
            # bet-carried closing_decimal_*, or Level 4 last_decimal_* proxy) never
            # knows which book supplied it -- stamp the field with an explicit
            # "none_available" sentinel (2026-07-09 fix) rather than leaving it None,
            # so a downstream reader can tell "stamp attempted, no same-venue book
            # known" apart from a row that never went through this code at all
            # (a pre-fix row on disk with the KEY missing entirely).
            settled["close_source"] = "none_available"
    else:
        # Level 5 (PE-P0-03): NO close -> CLV genuinely unavailable. clv_pct=None,
        # clv_is_proxy EXPLICITLY False (proxy=True would fabricate confidence) +
        # clv_status="no_close" so the UI renders VOID/pending, not "(proxy)".
        settled["status"] = "settled"
        settled["settled_at"] = _clv._now_iso()
        settled["clv_pct"] = None
        settled["beat_close"] = None
        settled["clv_is_proxy"] = False
        settled["clv_status"] = "no_close"
        settled["clv_note"] = "no closing line captured; CLV unavailable (win/loss only)"
        settled["close_source"] = "none_available"  # stamp attempted, nothing to stamp

    settled["graded"] = True
    settled["outcome"] = outcome  # win | loss | push | void (never fabricated)
    if outcome == "void":
        settled["void_reason"] = "equal_final_score_for_non_draw_sport"
    settled["home_score"] = hs
    settled["away_score"] = as_
    # UNITS ONLY -- never a dollar pnl. None for void/undecided.
    settled["unit_result"] = _unit_result(outcome, taken_decimal, stake_units)
    settled["executed"] = False
    settled["settle_key"] = _settle_key(bet)
    settled["bet_id"] = bet.get("bet_id") or _clv.bet_id(bet)
    return settled


__all__ = ["grade_one", "_outcome", "_unit_result", "_settle_key"]
