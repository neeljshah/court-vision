"""scripts.platformkit.grade_paper_asof -- as-of (any-date) finals routing + a
bounded backlog pass for stuck-open paper bets whose game ended on a PRIOR day.

WHY THIS EXISTS (gap_ledger_ultra16.md row 3)
----------------------------------------------
grade_paper.grade_open_bets's default fetch is live_board.todays_live_games, which
returns ONLY today's scoreboard -- a bet whose game ended yesterday (or earlier) is
invisible to the daily pass and stays "open" forever. Separately, kbo/npb have NO
ESPN scoreboard at all (site.api 400s both leagues -- see npb_kbo_live_state's
module docstring), so even TODAY's kbo/npb games were unsettleable (unknown_sport).

This module fixes both without touching prop_settler / clv_ledger_io / any
already-settled row:
  - route_fetch(sport, date): kbo/npb -> the existing npb_kbo_live_state bridge
    (reshaped to grade_paper's game dict); everything else -> live_board's now
    date-parameterized todays_live_games. grade_paper.grade_open_bets's default
    fetch uses this, so FUTURE same-day kbo/npb settles work too.
  - backfill_as_of(): a BOUNDED (default 200 oldest-first) one-time pass over
    stuck-open game-ML bets, grouped by (sport, candidate game date) so each board
    is fetched ONCE no matter how many bets share that game/day, 1 req/s apart.
    Reuses grade_paper's own match/settle/write path -- grading a previously-open
    row for the first time is allowed (settling, not rewriting); an already-settled
    row is never re-touched (same idempotent dedup as the daily pass).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_grade_paper_asof.py -q
"""
from __future__ import annotations

import datetime as _dt
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.clv_settle_write import write_settlement as _write_settlement
from scripts.platformkit.frontend import live_board as _lb
from scripts.platformkit.ingame import npb_kbo_live_state as _nk
from scripts.platformkit.ingame.hist_mlb_outcome_resolver import (
    parse_mlb_ticker as _parse_mlb_ticker,
    _split_tail as _mlb_split_tail,
)
from domains.baseball_kbo import team_map as _kbo_map

logger = logging.getLogger(__name__)

# ESPN carries neither league (verified live: both site.api paths 400) -- see
# npb_kbo_live_state's module docstring. These route to that bridge instead.
_BRIDGE_SPORTS = ("kbo", "npb")
_DEFAULT_MAX_BETS = 200
_DEFAULT_SLEEP_S = 1.0  # politeness: 1 req/s between DISTINCT board fetches

# MLB team-alias gap (gap ledger row: 36-row backlog, 2026-07): Kalshi in-play
# rows carry a Kalshi-house shorthand matchup label ("A's", "Chicago WS", "New
# York Y") that grade_paper._team_match's full-name token match cannot
# resolve. bet_id embeds the ORIGINAL Kalshi ticker though -- reused (not
# re-derived) via hist_mlb_outcome_resolver's proven parser/split, same module
# that already solves this exact Kalshi-shorthand-vs-ESPN-abbr gap for the
# offline hist_mlb_forward_gate corpus.
_MLB_TICKER_RE = re.compile(r"KXMLBGAME-[A-Z0-9]+")


def _mlb_ticker(bet: Dict[str, Any]) -> Optional[str]:
    """The raw KXMLBGAME-... ticker embedded in *bet*'s bet_id, or None."""
    m = _MLB_TICKER_RE.search(str(bet.get("bet_id") or ""))
    return m.group(0) if m else None


def _mlb_ticker_date(bet: Dict[str, Any]) -> Optional[str]:
    """The exact game date (ISO) embedded in *bet*'s KXMLBGAME ticker, or None.

    A hard fact straight from the ticker -- preferred over the ts-based guess
    in _candidate_dates below, since a Kalshi in-play row's ts (when our own
    system recorded/discovered the market) can trail the game's own calendar
    date by several days, well outside the ts/ts+1 heuristic window.
    """
    ticker = _mlb_ticker(bet)
    if ticker is None:
        return None
    parsed = _parse_mlb_ticker(ticker)
    return parsed[0].isoformat() if parsed else None


def mlb_ticker_fallback_match(bet: Dict[str, Any], games: List[Dict[str, Any]]
                              ) -> Optional[Dict[str, Any]]:
    """MLB-only fallback for grade_paper._find_final_game: split the bet's own
    KXMLBGAME ticker AWAY+HOME code tail against THIS board's own abbr set
    (hist_mlb_outcome_resolver's ticker parser + split algorithm, never a new
    hand-rolled team-name table) and match by EXACT abbr equality. None if no
    ticker, an ambiguous split, or no FINAL game at that exact pairing.
    """
    ticker = _mlb_ticker(bet)
    if ticker is None:
        return None
    parsed = _parse_mlb_ticker(ticker)
    if parsed is None:
        return None
    _, tail, _gnum = parsed
    abbr_index = {str(g.get("home_abbr") or "").upper() for g in games}
    abbr_index |= {str(g.get("away_abbr") or "").upper() for g in games}
    split = _mlb_split_tail(tail, abbr_index)
    if split is None:
        return None
    away, home = split
    from scripts.platformkit import grade_paper as _gp  # local: breaks the cycle
    for g in games:
        if g.get("state") not in _gp._FINAL_STATES:
            continue
        if (str(g.get("away_abbr") or "").upper() == away
                and str(g.get("home_abbr") or "").upper() == home
                and g.get("home_score") is not None
                and g.get("away_score") is not None):
            return g
    return None


def _shape_bridge_games(sport: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """npb_kbo_live_state row shape -> grade_paper's expected game-dict shape.

    'final' already matches grade_paper._FINAL_STATES; 'scheduled' /
    'in_progress_or_scheduled' map to 'pre' (not final, never fabricated). No abbr
    field on this bridge -- left None, same fallback-to-display-token path a
    missing-abbr ESPN row already takes in grade_paper._team_match.

    kbo ONLY: koreabaseball.com's raw page renders 5 of 10 teams as Latin codes
    ("KIA") and the other 5 as Korean glyphs ("두산") -- the SAME split the
    already-shipped domains.baseball_kbo.team_map.TEAM_MAP resolves to the
    canonical EN code (paper bets are recorded in that EN convention). Reused
    here rather than re-solved: unrecognized tokens pass through unchanged.
    """
    norm = ((lambda t: _kbo_map.normalize_team(t)) if sport == "kbo"
           else (lambda t: t))
    out: List[Dict[str, Any]] = []
    for r in rows:
        state = "final" if r.get("status") == "final" else "pre"
        out.append({"home": norm(r.get("home")), "away": norm(r.get("away")),
                    "home_abbr": None, "away_abbr": None, "state": state,
                    "home_score": r.get("home_score"), "away_score": r.get("away_score")})
    return out


def route_fetch(sport: str, date: Optional[str] = None) -> Dict[str, Any]:
    """One sport's board (today, or *date*='YYYY-MM-DD') in fetch_boards' shape.

    kbo/npb -> npb_kbo_live_state bridge. Everything else -> live_board, date-
    parameterized. Never raises (a bad feed degrades to an empty games list).
    """
    sp = str(sport).lower()
    if sp in _BRIDGE_SPORTS:
        d = None
        if date:
            try:
                d = _dt.date.fromisoformat(date)
            except ValueError:
                d = None
        try:
            rows = _nk.live_states(sp, date=d)
        except Exception as exc:  # noqa: BLE001
            logger.warning("grade_paper_asof bridge fetch failed %s %s: %s", sp, date, exc)
            rows = []
        return {"sport": sp, "status": "ok", "games": _shape_bridge_games(sp, rows)}
    espn_date = date.replace("-", "") if date else None
    return _lb.todays_live_games(sport, date=espn_date)


def _candidate_dates(bet: Dict[str, Any], *, today: Optional[str] = None) -> List[str]:
    """Primary game-date guess for *bet*, plus a ts+1day fallback ONLY when no
    explicit game_date was stamped (a bet recorded the evening before tip buckets
    under the GAME date -- same caveat grade_paper_close.game_key_for_bet notes).

    *today* is excluded from the fallback: this pass targets PRIOR-day finals only
    (live_board's TODAY board also attaches in-game predictions for every live game,
    which is expensive and pointless here -- we only need a final score). A bet whose
    true game date IS today is naturally picked up by the next normal daily
    grade_open_bets pass once that game goes final, not lost.

    MLB KXMLBGAME rows: the ticker's own embedded date is a hard fact, preferred
    over the ts guess below (see _mlb_ticker_date's docstring).
    """
    if str(bet.get("sport", "")).lower() == "mlb":
        tdate = _mlb_ticker_date(bet)
        if tdate is not None:
            return [tdate] if tdate != today else []
    gd = str(bet.get("game_date") or "").strip()[:10]
    if gd:
        return [gd] if gd != today else []
    ts = str(bet.get("ts") or "")[:10]
    if not ts:
        return []
    try:
        d = _dt.date.fromisoformat(ts)
    except ValueError:
        return [ts] if ts != today else []
    fallback = (d + _dt.timedelta(days=1)).isoformat()
    return [dt for dt in (ts, fallback) if dt != today]


def backfill_as_of(
    ledger_path: Optional[Path] = None,
    *,
    max_bets: int = _DEFAULT_MAX_BETS,
    sleep_s: float = _DEFAULT_SLEEP_S,
    today: Optional[str] = None,
    fetch: Callable[[str, Optional[str]], Dict[str, Any]] = route_fetch,
    _sleep: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Settle the oldest *max_bets* stuck-open game-ML bets from PRIOR days.

    Bounded + resumable: each run drains the oldest slice of the true backlog, so a
    large backlog clears over a few runs instead of one unbounded scrape. Boards are
    fetched ONCE per (sport, date) pair, *sleep_s* apart. Idempotent + append-only,
    same guarantees as grade_open_bets: an already-settled row is never re-touched.
    Local import of grade_paper (avoids a module-load-time circular import, since
    grade_paper imports route_fetch from this module for its own default fetch).
    """
    from scripts.platformkit import grade_paper as _gp  # local: breaks the cycle

    ledger_path = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    rows = _clv.load_ledger(ledger_path)
    today_s = today or _dt.datetime.now(_dt.timezone.utc).date().isoformat()
    open_bets = [r for r in rows if r.get("status") == "open" and _gp._is_game_ml_bet(r)]
    settled_rows = [r for r in rows if r.get("status") == "settled"]
    already: Set[str] = {r.get("settle_key") for r in settled_rows if r.get("settle_key")}
    already |= {r.get("bet_id") for r in settled_rows if r.get("bet_id")}

    backlog = [b for b in open_bets
               if _gp._settle_key(b) not in already
               and str(b.get("ts") or "")[:10] < today_s]
    backlog.sort(key=lambda b: str(b.get("ts") or ""))
    batch = backlog[:max_bets]

    boards: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    fetched: Set[Tuple[str, str]] = set()
    per_sport_settled: Dict[str, int] = {}
    per_sport_pending: Dict[str, int] = {}
    settled_now: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    _seen_keys: set = set()

    def _board(sp: str, d: str) -> List[Dict[str, Any]]:
        k = (sp, d)
        if k not in boards:
            if fetched:  # politeness: sleep only BETWEEN distinct fetches
                _sleep(sleep_s)
            fetched.add(k)
            payload = fetch(sp, d)
            boards[k] = list((payload or {}).get("games") or [])
        return boards[k]

    for bet in batch:
        key = _gp._settle_key(bet)
        if key in already:
            continue
        sp = str(bet.get("sport", "")).lower()
        game = None
        for d in _candidate_dates(bet, today=today_s):
            game = _gp._find_final_game(bet, _board(sp, d))
            if game is not None:
                break
        if game is None:
            pending.append({"matchup": bet.get("matchup"), "sport": sp})
            per_sport_pending[sp] = per_sport_pending.get(sp, 0) + 1
            continue
        settled = _gp.grade_one(bet, game)
        _write_settlement(settled, path=ledger_path, _seen=_seen_keys)
        already.add(key)
        if settled.get("bet_id"):
            already.add(settled["bet_id"])
        settled_now.append({"matchup": settled.get("matchup"), "sport": sp,
                            "outcome": settled["outcome"],
                            "close_source": settled.get("close_source")})
        per_sport_settled[sp] = per_sport_settled.get(sp, 0) + 1

    return {
        "backlog_total": len(backlog),
        "attempted": len(batch),
        "settled_now": len(settled_now),
        "still_pending": len(pending),
        "boards_fetched": len(boards),
        "per_sport_settled": per_sport_settled,
        "per_sport_pending": per_sport_pending,
        "settled": settled_now,
        "honest_note": ("Only FINAL games settled from a bounded oldest-first slice; "
                        "an already-settled row is never re-touched. Paper only, "
                        "units-only, no $-edge claimed."),
    }


__all__ = ["route_fetch", "backfill_as_of"]
