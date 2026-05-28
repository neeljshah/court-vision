"""_deeplinks.py — pure-function deeplink generator for book bet-slip pre-fill.

Each function returns {'web_url': str, 'app_url': str | None} for a given
prop + book combination.  Callers should always fall back gracefully — if
neither selectionId nor eventId is known, the web_url degrades to the
book's NBA landing page.

Prop dict schema (from _courtvision_odds.consolidate):
    player, stat, line, game_id, start_time, book,
    over_price, under_price,
    selection_id_over  (str | None)  — DK / FD / BR / PB populated after scraper upgrade
    selection_id_under (str | None)  — same

DraftKings deeplink mechanics (confirmed 2026):
  • Bet-slip pre-fill:  https://sportsbook.draftkings.com/bet?outcomeId=<id>&betType=Straight&stake=<n>
  • Event page:         https://sportsbook.draftkings.com/event/<eventId>
  • App scheme:         dksb://event/<eventId>?outcomeId=<id>
  The selectionId from the Nash response IS the outcomeId used in the web/app deeplinks.

FanDuel deeplink mechanics (confirmed 2026):
  • Bet-slip pre-fill:  https://sportsbook.fanduel.com/addToBetslip?marketId=<m>&runnerId=<r>
    FD's runnerId == runner.selectionId from the content-managed-page response.
    marketId == the market's eventId (from attachments.markets[key])
  • Event page:         https://sportsbook.fanduel.com/navigation/nba
  • App scheme:         fanduel://addToBetslip?marketId=<m>&runnerId=<r>

BetRivers (KAMBI) deeplink mechanics (confirmed 2026):
  • Event page:  https://www.betrivers.com/?page=sportsbook&type=event&id=<event_id>
    game_id from the KAMBI offering API IS the betrivers event ID used in this URL.
  • No public per-outcome bet-slip deeplink without authentication.
  • Fallback: NBA lobby if game_id is absent.

Pinnacle deeplink mechanics (confirmed 2026):
  • Event page:  https://www.pinnacle.com/en/sports/event/<eventId>
    game_id IS the Pinnacle parent matchup ID, usable directly in this URL.
  • No public bet-slip deeplink — authentication required.

Bovada deeplink mechanics (confirmed 2026):
  • Event page:  https://www.bovada.lv/sports/basketball/nba/<eventId>
    game_id from the Bovada coupon API IS the eventId in this URL.
  • No public bet-slip deeplink — Bovada uses in-page modals only.

PointsBet AU:
  • Event page:         https://au.pointsbet.com/sports/basketball/competitions/7176/events/<eventKey>
  • Market page:        …/events/<eventKey>/markets/<marketKey>  (marketKey from fixedOddsMarkets[].key)
    book_selection_id_over stores the market key (pointsbet_scraper v2+); empty for the-odds-api rows.
  • No public bet-slip deeplink.

BetMGM (MGM):
  • No dedicated scraper yet — WAF requires authenticated session.
  • Player-search fallback: https://sports.betmgm.com/en/sports?q=<player>
  • Deferred to future round.

Caesars Sportsbook:
  • No dedicated scraper yet — William Hill / OpenBet feed requires auth.
  • Player-search fallback: https://www.caesars.com/sportsbook-and-casino/sports/basketball/nba
  • Deferred to future round.

Fanatics:
  • No dedicated scraper yet — newer book with limited public API surface.
  • Deferred to future round.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode

# ── book landing pages (fallback) ────────────────────────────────────────────
_LANDING: dict[str, str] = {
    "dk":        "https://sportsbook.draftkings.com/leagues/basketball/nba",
    "fd":        "https://sportsbook.fanduel.com/navigation/nba",
    "pin":       "https://www.pinnacle.com/en/basketball/nba/matchups",
    "bov":       "https://www.bovada.lv/sports/basketball/nba",
    "betrivers": "https://www.betrivers.com/?page=sportsbook&group=1000093656&type=league",
    "mgm":       "https://sports.betmgm.com/en/sports/basketball-7/betting/usa-9/nba-6004",
    "caesars":   "https://www.caesars.com/sportsbook-and-casino/sports/basketball/nba",
    "espnbet":   "https://espnbet.com/sport/basketball/organization/us/competition/nba",
    "pointsbet": "https://au.pointsbet.com/sports/basketball/competitions/7176",
    "fanatics":  "https://sportsbook.fanaticsbetting.com/sport/basketball/nba",
    "bet365":    "https://www.bet365.com/#/AS/B18/",
    "underdog":  "https://underdogfantasy.com/pick-em",
    "hardrock":  "https://sports.hardrock.bet/sports/basketball/nba",
    "betonline":  "https://www.betonline.ag/sportsbook/basketball/nba",
    "pp":        "https://app.prizepicks.com/",
}
_DEFAULT_LANDING = "https://sportsbook.draftkings.com/leagues/basketball/nba"

# Default stake injected into DK bet-slip deeplinks
_DEFAULT_STAKE = 10.0


def _landing(book: str) -> str:
    return _LANDING.get(book.lower(), _DEFAULT_LANDING)


# ── DraftKings ────────────────────────────────────────────────────────────────

def _dk_links(prop: dict, side: str, stake: float) -> dict:
    """Return DK web + app deeplinks.

    Uses selection_id_over / selection_id_under captured by the scraper.
    Falls back to event page (game_id) if the selection ID is absent.
    """
    side_upper = side.upper()
    selection_id: Optional[str] = None
    if side_upper == "OVER":
        selection_id = prop.get("selection_id_over") or None
    elif side_upper == "UNDER":
        selection_id = prop.get("selection_id_under") or None

    game_id: str = prop.get("game_id") or ""

    if selection_id:
        params = urlencode({"outcomeId": selection_id, "betType": "Straight",
                             "stake": int(stake)})
        web_url = f"https://sportsbook.draftkings.com/bet?{params}"
        app_url = (f"dksb://event/{game_id}?outcomeId={selection_id}"
                   if game_id else f"dksb://bet?outcomeId={selection_id}")
    elif game_id:
        web_url = f"https://sportsbook.draftkings.com/event/{game_id}"
        app_url = f"dksb://event/{game_id}"
    else:
        web_url = _landing("dk")
        app_url = None

    return {"web_url": web_url, "app_url": app_url}


# ── FanDuel ───────────────────────────────────────────────────────────────────

def _fd_links(prop: dict, side: str) -> dict:
    """Return FD web + app deeplinks.

    FD uses (marketId, runnerId) pairs.  The scraper stores both in
    selection_id_over as "marketId:runnerId" (colon-delimited).  When the
    value contains ":", we split it; otherwise we treat the whole string as
    the runnerId and use game_id as the marketId (legacy / fallback).

    FD only publishes the YES/Over side on threshold markets so
    selection_id_under is always empty for FD rows.
    """
    side_upper = side.upper()
    raw_sel: Optional[str] = None
    if side_upper == "OVER":
        raw_sel = prop.get("selection_id_over") or None
    elif side_upper == "UNDER":
        raw_sel = prop.get("selection_id_under") or None

    game_id: str = str(prop.get("game_id") or "")
    market_id: Optional[str] = None
    runner_id: Optional[str] = None

    if raw_sel:
        if ":" in raw_sel:
            parts = raw_sel.split(":", 1)
            market_id, runner_id = parts[0], parts[1]
        else:
            # Fallback: treat as runner_id only, use game_id as market_id
            runner_id = raw_sel
            market_id = game_id

    if runner_id and market_id:
        params = urlencode({"marketId": market_id, "runnerId": runner_id})
        web_url = f"https://sportsbook.fanduel.com/addToBetslip?{params}"
        app_url = f"fanduel://addToBetslip?marketId={market_id}&runnerId={runner_id}"
    elif game_id:
        web_url = "https://sportsbook.fanduel.com/navigation/nba"
        app_url = None
    else:
        web_url = _landing("fd")
        app_url = None

    return {"web_url": web_url, "app_url": app_url}


# ── PointsBet ─────────────────────────────────────────────────────────────────

def _pb_links(prop: dict) -> dict:
    """PointsBet AU: event page (+ market fragment when market_key is available).

    book_selection_id_over stores the market key captured by pointsbet_scraper
    (set when data comes from the dedicated PB scraper, not the-odds-api).
    When present, appends the /markets/<key> path for a per-market URL.
    When game_id is a 32-char hex hash (the-odds-api internal ID) it is NOT
    a valid PB event key — fall back gracefully to landing page.
    """
    event_key: str = str(prop.get("game_id") or "")
    market_key: str = str(prop.get("selection_id_over") or "")
    # Detect the-odds-api hash IDs (32-char lowercase hex): not valid PB event keys
    _is_hash = len(event_key) == 32 and all(c in "0123456789abcdef" for c in event_key)
    if not event_key or _is_hash:
        return {"web_url": _landing("pointsbet"), "app_url": None}
    base_event = (f"https://au.pointsbet.com/sports/basketball/competitions"
                  f"/7176/events/{event_key}")
    if market_key:
        web_url = f"{base_event}/markets/{market_key}"
    else:
        web_url = base_event
    return {"web_url": web_url, "app_url": None}


# ── BetRivers (KAMBI) ─────────────────────────────────────────────────────────

def _betrivers_links(prop: dict) -> dict:
    """Return BetRivers event-page deeplink.

    KAMBI game_id (the betOffer event ID, a numeric integer) maps directly to
    the BetRivers event page URL pattern.  No public per-outcome bet-slip
    deeplink exists.

    When game_id is a 32-char hex hash (the-odds-api.com internal ID) it is
    NOT a valid BetRivers event ID — fall back to player-name search instead.
    """
    game_id: str = str(prop.get("game_id") or "")
    # Detect the-odds-api hash IDs (32-char lowercase hex): not usable on betrivers.com
    _is_hash = len(game_id) == 32 and all(c in "0123456789abcdef" for c in game_id)
    if game_id and not _is_hash:
        web_url = f"https://www.betrivers.com/?page=sportsbook&type=event&id={game_id}"
    elif game_id and _is_hash:
        # TheOddsAPI hash — use player-search so user lands close to the right market
        from urllib.parse import quote_plus as _qp  # noqa: PLC0415
        player: str = prop.get("player") or ""
        if player:
            web_url = f"https://www.betrivers.com/?page=sportsbook&search={_qp(player)}"
        else:
            web_url = _landing("betrivers")
    else:
        web_url = _landing("betrivers")
    return {"web_url": web_url, "app_url": None}


# ── Pinnacle / Bovada / other event-page books ────────────────────────────────

def _event_page_only_links(book: str, prop: dict) -> dict:
    """For books that expose event pages but no bet-slip deeplink."""
    event_id: str = str(prop.get("game_id") or "")
    base = _landing(book)
    if not event_id:
        return {"web_url": base, "app_url": None}

    if book == "pin":
        web_url = f"https://www.pinnacle.com/en/sports/event/{event_id}"
    elif book == "bov":
        web_url = f"https://www.bovada.lv/sports/basketball/nba/{event_id}"
    else:
        web_url = base  # no known event-page pattern
    return {"web_url": web_url, "app_url": None}


# ── Player-search fallback (books without public IDs) ─────────────────────────

def _player_search_links(book: str, prop: dict) -> dict:
    """Return a player-search URL — better than the homepage for books where
    no event-page pattern is known (MGM, Caesars, Fanatics, ESPN BET, etc.).

    The search link pre-fills the player name so the user lands one click away
    from the correct market rather than on the book's front page.
    """
    from urllib.parse import quote_plus  # noqa: PLC0415
    player: str = prop.get("player") or ""
    base = _landing(book)
    if not player:
        return {"web_url": base, "app_url": None}
    q = quote_plus(player)
    if book == "mgm":
        web_url = f"https://sports.betmgm.com/en/sports?q={q}"
    elif book == "caesars":
        web_url = f"https://sportsbook.caesars.com/us/bet/search?query={q}"
    elif book == "espnbet":
        web_url = f"https://espnbet.com/sport/basketball/organization/us/competition/nba"
    elif book == "fanatics":
        web_url = f"https://sportsbook.fanaticsbetting.com/search?q={q}"
    else:
        web_url = base
    return {"web_url": web_url, "app_url": None}


# ── Public API ────────────────────────────────────────────────────────────────

def book_deeplink(book: str, prop: dict, side: str = "OVER",
                  stake: float = _DEFAULT_STAKE) -> dict:
    """Return {'web_url': str, 'app_url': str | None} for a given prop + book.

    Args:
        book:  Book key (lowercase), e.g. 'dk', 'fd', 'pin'.
        prop:  Prop dict from _courtvision_odds.consolidate() — must include
               selection_id_over / selection_id_under when available.
        side:  'OVER' or 'UNDER'.
        stake: Default stake to pre-fill (DK only, ignored by others).

    Returns:
        dict with keys:
          'web_url'  — always present, opens bet slip or event page in browser
          'app_url'  — native app deeplink scheme, or None if not supported
    """
    b = (book or "").lower()
    if b == "dk":
        return _dk_links(prop, side, stake)
    if b in ("dk_inplay",):
        # DK in-play uses the same bet-slip pattern with the live outcomeId.
        return _dk_links(prop, side, stake)
    if b == "fd":
        return _fd_links(prop, side)
    if b in ("fd_inplay",):
        return _fd_links(prop, side)
    if b == "pointsbet":
        return _pb_links(prop)
    if b in ("pin", "bov"):
        return _event_page_only_links(b, prop)
    if b == "betrivers":
        return _betrivers_links(prop)
    if b in ("mgm", "caesars", "espnbet", "fanatics"):
        # No dedicated event-page pattern known; player-search is better than homepage.
        return _player_search_links(b, prop)
    # All other books (bet365, underdog, hardrock, betonline, pp): landing page only.
    return {"web_url": _landing(b), "app_url": None}


def multi_book_links(prop: dict, side: str = "OVER",
                     books: Optional[list] = None,
                     stake: float = _DEFAULT_STAKE,
                     max_tabs: int = 3) -> list[dict]:
    """Return up to max_tabs deeplinks for the given prop + side, ordered by priority.

    Default priority: DK → FD → PIN → others.
    Used by the 'Open in N books' button — caller opens each web_url in a tab.

    Args:
        prop:     Consolidated prop dict.
        side:     'OVER' or 'UNDER'.
        books:    Explicit book-key list to use (from prop['books']).  If None,
                  derives from the prop's own book list.
        stake:    Default stake (DK only).
        max_tabs: Hard cap on returned links to prevent tab-bombing.

    Returns:
        List of dicts: [{book, display, web_url, app_url}, ...]
    """
    _PRIORITY = ["dk", "fd", "pin", "pointsbet", "bov", "betrivers",
                 "mgm", "caesars", "espnbet", "fanatics", "bet365",
                 "underdog", "hardrock", "betonline"]

    if books is None:
        books = [b["book"] for b in (prop.get("books") or [])]

    # De-dup + prioritise
    seen: set[str] = set()
    ordered: list[str] = []
    for b in _PRIORITY:
        if b in books and b not in seen:
            ordered.append(b)
            seen.add(b)
    for b in books:
        if b not in seen:
            ordered.append(b)
            seen.add(b)

    result = []
    for bk in ordered[:max_tabs]:
        links = book_deeplink(bk, prop, side=side, stake=stake)
        result.append({
            "book": bk,
            "display": _LANDING_DISPLAY.get(bk, bk.upper()),
            "web_url": links["web_url"],
            "app_url": links["app_url"],
        })
    return result


_LANDING_DISPLAY: dict[str, str] = {
    "dk": "DraftKings", "fd": "FanDuel", "pin": "Pinnacle",
    "bov": "Bovada", "betrivers": "BetRivers", "mgm": "BetMGM",
    "caesars": "Caesars", "espnbet": "ESPN BET", "pointsbet": "PointsBet",
    "fanatics": "Fanatics", "bet365": "Bet365", "underdog": "Underdog",
    "hardrock": "Hard Rock Bet", "betonline": "BetOnline", "pp": "PrizePicks",
}
