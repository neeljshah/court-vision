"""scripts.platformkit.grade_paper -- auto-settle/grade PAPER bets once games end.

HONESTY CONTRACT: NEVER fabricates an outcome or close. Games settled ONLY when
state in {post,final} + both scores present. Append-only + settle_key => idempotent.
Paper only (executed=False). CLV via clv_ledger, never re-derived.

CLOSE RESOLUTION PRECEDENCE (grade_one):
  1. closing_decimal_* on bet         -> clv_is_proxy=False (true close)
  2. line_store TRUE close            -> clv_is_proxy=False
  3. line_store PROXY close           -> clv_is_proxy=True
  4. last_decimal_* / close_proxy_*   -> clv_is_proxy=True
  5. Nothing -> clv_pct=None, clv_is_proxy=False (EXPLICIT), clv_status="no_close":
     CLV genuinely unavailable -> row renders VOID/pending, NEVER an inferred
     "(proxy)" label (that would fabricate confidence). win/loss still set.

UNITS ONLY: no dollar pnl / roi / stake field is ever written; the unit record is
``unit_result`` (a pure unit count at the taken price). An equal "final" score for a
sport that cannot draw (NBA/MLB) -> outcome="void". Build only under
scripts/platformkit/; <=300 LOC; no secrets; no $-edge claim.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.clv_settle_write import write_settlement as _write_settlement
from scripts.platformkit.frontend import live_board as _lb
from scripts.platformkit.grade_paper_close import close_from_store as _close_from_store
from scripts.platformkit.grade_paper_close import fetch_boards as _fetch_boards
from scripts.platformkit.grade_paper_close import game_key_for_bet as _game_key_for_bet
from scripts.platformkit.grade_paper_close import load_predictions as _load_predictions
from scripts.platformkit.grade_paper_summary import grade_summary

logger = logging.getLogger(__name__)

_FINAL_STATES = ("post", "final")


def _is_game_ml_bet(bet: Dict[str, Any]) -> bool:
    """True only for a two-way GAME moneyline bet that THIS grader can settle.

    A player-prop row (market_type=="prop" / market="prop|...") settles on its own
    stat outcome (player over/under a line), NOT the game's home/away result -- so it
    must be SKIPPED here or it would be mis-settled as a moneyline. (PM/Kalshi rows are
    settled by their own venue grader, never re-derived from a game score.) The honest
    error direction is to skip an ambiguous row (it stays pending) rather than settle it
    as a moneyline it is not.
    """
    mt = str(bet.get("market_type") or "").strip().lower()
    if mt == "prop":
        return False
    if str(bet.get("market") or "").strip().lower().startswith("prop"):
        return False
    return str(bet.get("side", "")).strip().lower() in ("home", "away")


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


def _norm_tokens(text: str) -> List[str]:
    """Lowercased alpha tokens of a team name / abbreviation, for fuzzy matchup match."""
    return [t for t in re.split(r"[^a-z0-9]+", str(text).lower()) if t]


def _matchup_sides(matchup: str) -> Tuple[Optional[str], Optional[str]]:
    """Split a 'A @ B' / 'A vs B' matchup string into (left, right) raw labels.

    We do NOT infer home/away from string order -- only use the two labels to identify
    WHICH game this is. Win/loss uses the ledger 'side' vs the feed's home/away scores.
    """
    s = str(matchup)
    for sep in (" @ ", "@", " vs ", " vs. ", " v ", " - ", " at "):
        if sep in s:
            a, _, b = s.partition(sep)
            return a.strip(), b.strip()
    return (s.strip() or None), None


def _team_match(label: Optional[str], game_display: str, game_abbr: Optional[str]) -> bool:
    """True if a matchup label refers to the game's team (by abbr or name tokens)."""
    if not label:
        return False
    lab = _norm_tokens(label)
    if not lab:
        return False
    if game_abbr and "".join(lab) == game_abbr.lower():
        return True
    disp = set(_norm_tokens(game_display))
    abbr = set(_norm_tokens(game_abbr)) if game_abbr else set()
    # Every label token must appear in the game's name/abbr token set (handles
    # "CIN" -> "Cincinnati Reds", "NYK"/"Knicks", etc.).
    return all(t in disp or t in abbr for t in lab)


def _find_final_game(bet: Dict[str, Any], games: List[Dict[str, Any]]
                     ) -> Optional[Dict[str, Any]]:
    """The FINAL game whose two teams match this bet's matchup. None if not found/final."""
    left, right = _matchup_sides(bet.get("matchup", ""))
    for g in games:
        if g.get("state") not in _FINAL_STATES:
            continue
        hd, ha = g.get("home"), g.get("home_abbr")
        ad, aa = g.get("away"), g.get("away_abbr")
        # both labels must map onto the two teams (either orientation)
        m1 = (_team_match(left, hd, ha) and _team_match(right, ad, aa))
        m2 = (_team_match(left, ad, aa) and _team_match(right, hd, ha))
        if (m1 or m2) and g.get("home_score") is not None and g.get("away_score") is not None:
            return g
    return None


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


def grade_one(
    bet: Dict[str, Any],
    game: Dict[str, Any],
    *,
    _line_store_base: Optional[Path] = None,
) -> Dict[str, Any]:
    """SETTLED twin of *bet* from FINAL *game* (see module CLOSE RESOLUTION
    PRECEDENCE). *_line_store_base* overrides the history dir for tests."""
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
        sr = _close_from_store(bet, base=_line_store_base)
        if sr is not None:
            ch, ca, is_true, close_book_home, close_book_away = sr
            is_proxy = not is_true

    if ch is None or ca is None:  # Level 4: explicit last-observed proxy on bet.
        ch = bet.get("last_decimal_home") or bet.get("close_proxy_home")
        ca = bet.get("last_decimal_away") or bet.get("close_proxy_away")
        if ch is not None and ca is not None:
            is_proxy = True

    if ch is not None and ca is not None:
        settled = _clv.settle_closing_line(settled, float(ch), float(ca))
        settled["clv_is_proxy"] = bool(is_proxy)
        settled["clv_status"] = "proxy" if is_proxy else "true_close"
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


def grade_open_bets(
    ledger_path: Optional[Path] = None,
    predictions_path: Optional[Path] = None,
    *,
    fetch_finals: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Settle every OPEN paper bet whose game is FINAL; append settled twins.

    Idempotent: a bet already settled (matching settle_key in the ledger) is skipped.
    Games that are not final are SKIPPED and counted as pending -- never fabricated.
    *fetch_finals* is injectable for tests: sport -> live_board-shaped payload (with
    a 'games' list). Default fetches the keyless ESPN scoreboard via live_board.
    """
    ledger_path = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    rows = _clv.load_ledger(ledger_path)
    # Only GAME moneyline rows settle here; prop rows settle on their own stat
    # outcome (see _is_game_ml_bet) and would be MIS-settled as a moneyline otherwise.
    open_bets = [r for r in rows
                 if r.get("status") == "open" and _is_game_ml_bet(r)]
    # Dedup on the durable settle identity AND bet_id of already-settled rows, so a
    # re-record settles ONCE regardless of which key a prior twin used.
    settled_rows = [r for r in rows if r.get("status") == "settled"]
    already = {r.get("settle_key") for r in settled_rows if r.get("settle_key")}
    already |= {r.get("bet_id") for r in settled_rows if r.get("bet_id")}
    preds = _load_predictions(predictions_path)  # optional proxy-close enrichment

    fetch = fetch_finals if fetch_finals is not None else _lb.todays_live_games
    sports = sorted({str(b.get("sport", "")).lower() for b in open_bets})
    boards, feed_status = _fetch_boards(fetch, sports)

    settled_now: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    # Pre-load the seen-set once so write_settlement need not re-scan per row.
    _seen_keys: set = set()
    for bet in open_bets:
        key = _settle_key(bet)
        if key in already:
            continue  # idempotent: do not double-settle
        sp = str(bet.get("sport", "")).lower()
        # carry any stored proxy close from the predictions store into the bet
        pr = preds.get(str(bet.get("matchup", "")))
        if pr:
            for k in ("closing_decimal_home", "closing_decimal_away",
                      "last_decimal_home", "last_decimal_away"):
                if bet.get(k) is None and pr.get(k) is not None:
                    bet = {**bet, k: pr[k]}
        game = _find_final_game(bet, boards.get(sp, []))
        if game is None:
            pending.append({"matchup": bet.get("matchup"), "sport": sp,
                            "reason": "no final game matched"})
            continue
        settled = grade_one(bet, game)
        # Route through the status-aware dedup wrapper (be-r2-w1-clv-writer-dedup):
        # a tick-overlap or daemon-restart double-fire on the same (bet_id|settled)
        # pair is now a no-op instead of appending a second identical row.
        _write_settlement(settled, path=ledger_path, _seen=_seen_keys)
        already.add(key)
        if settled.get("bet_id"):
            already.add(settled["bet_id"])
        settled_now.append({"matchup": settled.get("matchup"), "sport": sp,
                            "side": settled.get("side"), "outcome": settled["outcome"],
                            "unit_result": settled.get("unit_result"),
                            "clv_pct": settled.get("clv_pct"),
                            "clv_status": settled.get("clv_status"),
                            "clv_is_proxy": settled.get("clv_is_proxy", False)})

    return {
        "n_open": len(open_bets),
        "n_settled_now": len(settled_now),
        "n_pending": len(pending),
        "feed_status": feed_status,
        "settled": settled_now,
        "pending": pending,
        "honest_note": ("Only FINAL games settled; no outcome/close fabricated. Paper "
                        "only (executed=False); CLV may be a labelled proxy. UNITS "
                        "ONLY -- no $-edge claimed."),
    }


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Settle/grade open paper bets on FINAL games.")
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--predictions", default=None)
    a = ap.parse_args(argv)
    ledger = Path(a.ledger) if a.ledger else None
    graded = grade_open_bets(ledger, Path(a.predictions) if a.predictions else None)
    print("GRADE PASS (paper, executed_any=False): open=%d settled_now=%d pending=%d"
          % (graded["n_open"], graded["n_settled_now"], graded["n_pending"]))
    for s in graded["settled"]:
        print("  SETTLED %s [%s] %s units=%s clv=%s%s"
              % (s["matchup"], s["side"], s["outcome"], s.get("unit_result"),
                 s["clv_pct"], " (proxy)" if s.get("clv_is_proxy") else ""))
    print("SUMMARY:", json.dumps(grade_summary(ledger), indent=2, default=str))
    return 0


__all__ = ["grade_open_bets", "grade_summary", "grade_one"]


if __name__ == "__main__":
    raise SystemExit(_main())
