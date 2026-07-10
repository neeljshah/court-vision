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
scripts/platformkit/; no secrets; no $-edge claim.
"""
# ponytail: grade_one() + its _outcome/_unit_result/_settle_key helpers were
# extracted to grade_paper_one.py (C1 LOC-rail fix) to bring this file under
# the platform's <=300 LOC/file rail; re-imported here so every existing
# caller (grade_open_bets, prop_settler.py's direct import,
# settlement_correctness_audit.py's ``_gp.`` attribute access) is unaffected.
# See grade_paper_one.py's docstring for the monkeypatch-routing deviation.
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.clv_settle_write import write_settlement as _write_settlement
from scripts.platformkit.grade_paper_asof import route_fetch as _route_fetch
from scripts.platformkit.grade_paper_dates import bet_expected_dates as _bet_expected_dates
from scripts.platformkit.grade_paper_dates import today_et_iso as _today_et_iso
from scripts.platformkit.grade_paper_close import close_from_store as _close_from_store
from scripts.platformkit.grade_paper_close import fetch_boards as _fetch_boards
from scripts.platformkit.grade_paper_close import game_key_for_bet as _game_key_for_bet
from scripts.platformkit.grade_paper_close import load_predictions as _load_predictions
from scripts.platformkit.grade_paper_one import _outcome as _outcome
from scripts.platformkit.grade_paper_one import _settle_key as _settle_key
from scripts.platformkit.grade_paper_one import _unit_result as _unit_result
from scripts.platformkit.grade_paper_one import grade_one as grade_one
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


def _norm_tokens(text: str) -> List[str]:
    """Lowercased alpha tokens of a team name / abbreviation, for fuzzy matchup match.

    Unicode-aware split (\\w matches non-ASCII letters too, e.g. NPB's kanji team
    names): an ASCII-only split would silently reduce any non-Latin name to zero
    tokens (the whole run of kanji/Hangul is itself a valid \\w run, not a separator),
    which made every non-ASCII team name unmatchable. ASCII inputs are unaffected.
    """
    return [t for t in re.split(r"[^\w]+", str(text).lower(), flags=re.UNICODE) if t]


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


def _find_final_game(bet: Dict[str, Any], games: List[Dict[str, Any]],
                     *, board_date: Optional[str] = None
                     ) -> Optional[Dict[str, Any]]:
    """The FINAL game whose two teams match this bet's matchup. None if not found/final.

    MLB alias wiring (gap ledger, 36-row backlog): a Kalshi-house shorthand
    matchup label ("A's", "Chicago WS", "New York Y") routinely fails the
    token match below against ESPN's full team name. When bet_id embeds the
    original KXMLBGAME ticker, grade_paper_asof.mlb_ticker_fallback_match
    resolves the same game by exact abbr code instead (local import breaks
    the cycle, mirrors that module's own import of this one).

    DATE GUARD (wrong-settle fix, gap ledger review of 0889b481): team-only
    matching -- with no date check -- let a same-teams final from the WRONG
    calendar date settle a bet (proven live: 3 separate COL@SF tickets, dated
    26JUL09/10/11, all settled against the identical 26JUL09 8-2 final; the
    26JUL11 ticket settled before its own game could even be final). *games*
    is whatever board the caller queried; *board_date* is the date that query
    was actually FOR (None = "today", the daily pass's default unscoped
    fetch). If *bet* has its own reliable expected date(s) (MLB ticket date,
    else game_date/ts-derived) and *board_date* is known, a board for a date
    outside that set cannot hold this bet's real game -- skip, never guess.
    Applies to BOTH this team-match loop and the ticket fallback below.
    """
    expected = _bet_expected_dates(bet)
    if expected and board_date is not None and board_date not in expected:
        return None
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
    if str(bet.get("sport", "")).lower() == "mlb":
        from scripts.platformkit.grade_paper_asof import mlb_ticker_fallback_match as _mlb_fb
        return _mlb_fb(bet, games, board_date=board_date)
    return None


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
    a 'games' list). Default routes via grade_paper_asof.route_fetch (today's board;
    kbo/npb dispatch to the npb_kbo_live_state bridge since ESPN carries neither
    league -- see that module's docstring).
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

    fetch = fetch_finals if fetch_finals is not None else _route_fetch
    sports = sorted({str(b.get("sport", "")).lower() for b in open_bets})
    boards, feed_status = _fetch_boards(fetch, sports)
    # This is always "today's" board (unscoped fetch) -- feeds _find_final_game's
    # date guard so a bet whose OWN expected date isn't today can't bind to it.
    today_s = _today_et_iso()

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
        game = _find_final_game(bet, boards.get(sp, []), board_date=today_s)
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
        # kbo/npb matchups may carry Hangul/kanji -- cp1252 console stdout would
        # otherwise crash on a genuinely settled non-ASCII row (see grade_paper_asof).
        matchup = str(s["matchup"]).encode("ascii", "replace").decode("ascii")
        print("  SETTLED %s [%s] %s units=%s clv=%s%s"
              % (matchup, s["side"], s["outcome"], s.get("unit_result"),
                 s["clv_pct"], " (proxy)" if s.get("clv_is_proxy") else ""))
    print("SUMMARY:", json.dumps(grade_summary(ledger), indent=2, default=str))
    return 0


__all__ = ["grade_open_bets", "grade_summary", "grade_one"]


if __name__ == "__main__":
    raise SystemExit(_main())
