"""
action_network.py - Action Network sharp% / public% fetcher.

Fetches public betting percentages and sharp-money indicators for NBA games
and player props from Action Network's public web JSON API (no auth required).

API note (2026-05-24 endpoint migration)
----------------------------------------
Action Network deprecated the legacy ``/web/v1/competitions/nba/events``
endpoint (returns HTTP 404). The current public endpoints are:

  * ``GET /web/v2/scoreboard/nba?date=YYYYMMDD``
      Returns today's NBA games. Each game has ``markets[book_id].event``
      with moneyline / spread / total outcomes. Each outcome carries a
      populated ``bet_info.tickets.percent`` and ``bet_info.money.percent``
      (public_bets_pct / public_money_pct) - this is the steam signal source.

  * ``GET /web/v2/games/{game_id}/props``
      Returns player prop markets grouped by ``core_bet_type_*_<stat>``.
      Lines and odds are populated; ``bet_info`` percentages are returned
      as zeros for the free tier (player-prop public-bets% is gated behind
      Action Network PRO). We expose what's available and default the
      player-level public_bets_pct to neutral (50.0) when only line data
      is present, while still flagging GAME-level RLM (which IS published).

Action Network exposes:
  - public_bets_pct  : % of public tickets on the OVER (or HOME for ML/spread)
  - public_money_pct : % of public dollars on the OVER
  When public_bets_pct is high but the line moves AGAINST the public, that
  confirms sharp money (reverse-line movement = strong steam indicator).

Cache
-----
    data/nba/action_network_cache.json   (TTL: 15 minutes)

Public API
----------
    get_sharp_pct(player_name, stat)  -> dict
    refresh_action_network(force)     -> dict
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, date, timezone
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_PATH = os.path.join(PROJECT_DIR, "data", "nba", "action_network_cache.json")
_TTL_SEC    = 15 * 60   # 15 minutes

# Action Network public web API base
_AN_BASE   = "https://api.actionnetwork.com/web"
_AN_LEAGUE = "nba"

# Map our stat names to the Action Network v2 player_props key.
# Confirmed live 2026-05-24 via /web/v2/games/{id}/props.
_STAT_TO_AN_PROP: Dict[str, str] = {
    "pts":  "core_bet_type_27_points",
    "reb":  "core_bet_type_23_rebounds",
    "ast":  "core_bet_type_26_assists",
    "fg3m": "core_bet_type_21_3fgm",
    "stl":  "core_bet_type_24_steals",
    "blk":  "core_bet_type_25_blocks",
    "tov":  "core_bet_type_580_turnovers",
}

# Preferred book ID priority for line / odds (DraftKings 15, FanDuel 30,
# Caesars 75, BetMGM 68, PointsBet 71, BetRivers 69, Barstool 49).
_BOOK_PRIORITY = ["15", "30", "75", "68", "71", "69", "49"]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.actionnetwork.com/",
}


# ── Cache I/O ─────────────────────────────────────────────────────────────────

def _cache_fresh() -> bool:
    if not os.path.exists(_CACHE_PATH):
        return False
    return (time.time() - os.path.getmtime(_CACHE_PATH)) < _TTL_SEC


def _load_cache() -> dict:
    try:
        with open(_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _prop_key(player: str, stat: str) -> str:
    return f"{player.lower().strip()}|{stat}"


def _norm_name(name: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pick_book(lines_by_book: Dict[str, List[dict]]) -> Optional[str]:
    """Return preferred book_id present in the lines map (priority order)."""
    for bid in _BOOK_PRIORITY:
        if bid in lines_by_book and lines_by_book[bid]:
            return bid
    return next(iter(lines_by_book), None)


def _game_rlm(game: dict) -> bool:
    """Return True if any game-level market shows reverse-line movement.

    RLM heuristic: public is heavy on one side (>=65% tickets) yet money/odds
    skew the other way (money% < tickets% by >=10pp on the favored side).
    """
    markets = game.get("markets", {}) or {}
    for bid, bd in markets.items():
        for mtype, arr in (bd.get("event", {}) or {}).items():
            for o in arr:
                bi = o.get("bet_info", {}) or {}
                tp = (bi.get("tickets") or {}).get("percent") or 0
                mp = (bi.get("money") or {}).get("percent") or 0
                if tp >= 65 and (tp - mp) >= 10:
                    return True
    return False


# ── Fetcher ───────────────────────────────────────────────────────────────────

def refresh_action_network(force: bool = False) -> dict:
    """
    Fetch today's NBA player prop lines + game-level public% from Action Network.

    Endpoint chain (verified 2026-05-24):
        1) GET /web/v2/scoreboard/nba?date=YYYYMMDD   -> list of game IDs +
           game-level moneyline/spread/total with populated bet_info percentages.
        2) GET /web/v2/games/{game_id}/props          -> per-player prop lines
           (pts, reb, ast, fg3m, stl, blk, tov). bet_info percentages are zero
           in the free tier; we keep the line + odds and inherit the game-level
           RLM flag.

    Gracefully returns the stale cache (or empty dict) when the API is
    unavailable.

    Returns:
        Dict keyed by "{player_lower}|{stat}" -> {
            "player":          str,
            "stat":            str,
            "line":            float | None,
            "over_odds":       int   | None,
            "under_odds":      int   | None,
            "book_id":         str   | None,
            "public_bets_pct": float,    # 0-100; 50.0 if not exposed for props
            "public_money_pct":float,    # 0-100; 50.0 if not exposed for props
            "rlm":             bool,     # game-level RLM flag (inherited)
            "steam_move":      bool,     # back-compat alias of rlm
            "game_id":         int,
            "fetched_at":      str,
        }
    """
    if not force and _cache_fresh():
        return _load_cache()

    try:
        import requests
    except ImportError:
        print("[action_network] requests not installed")
        return _load_cache()

    # Action Network expects date in YYYYMMDD form (no dashes).
    today_compact = date.today().strftime("%Y%m%d")
    result: dict = {}

    # ── Step 1: scoreboard (game IDs + game-level public%) ───────────────────
    try:
        sb_url = f"{_AN_BASE}/v2/scoreboard/{_AN_LEAGUE}"
        resp = requests.get(
            sb_url,
            params={"date": today_compact},
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        games: List[dict] = payload.get("games", []) if isinstance(payload, dict) else []
    except Exception as e:
        print(f"[action_network] Scoreboard fetch failed: {e}")
        return _load_cache()

    if not games:
        print(f"[action_network] No NBA games on {today_compact}")
        return _load_cache()

    fetched_at = datetime.now(timezone.utc).isoformat()

    # ── Step 2: per-game player props ────────────────────────────────────────
    for game in games:
        game_id = game.get("id")
        if not game_id:
            continue

        game_has_rlm = _game_rlm(game)

        try:
            time.sleep(0.3)  # polite throttle
            props_url = f"{_AN_BASE}/v2/games/{game_id}/props"
            r = requests.get(props_url, headers=_HEADERS, timeout=15)
            r.raise_for_status()
            props_payload = r.json()
        except Exception as e:
            print(f"[action_network] props fetch failed for game {game_id}: {e}")
            continue

        player_props = props_payload.get("player_props", {}) or {}
        players_idx  = props_payload.get("players", {}) or {}

        def _player_name(pid) -> str:
            rec = players_idx.get(str(pid)) or players_idx.get(pid) or {}
            return rec.get("full_name") or rec.get("player_full_name") or ""

        for stat, an_key in _STAT_TO_AN_PROP.items():
            entries = player_props.get(an_key, []) or []
            for entry in entries:
                pid = entry.get("player_id")
                player = _player_name(pid)
                if not player:
                    continue
                lines_by_book = entry.get("lines", {}) or {}
                book = _pick_book(lines_by_book)
                if not book:
                    continue
                outcomes = lines_by_book[book] or []
                line_val: Optional[float] = None
                over_odds = under_odds = None
                pub_bets_acc: List[float] = []
                pub_money_acc: List[float] = []
                for o in outcomes:
                    side = (o.get("side") or "").lower()
                    val  = o.get("value")
                    if val is not None and line_val is None:
                        try:
                            line_val = float(val)
                        except (TypeError, ValueError):
                            line_val = None
                    if side == "over":
                        over_odds = o.get("odds")
                    elif side == "under":
                        under_odds = o.get("odds")
                    bi = o.get("bet_info", {}) or {}
                    tp = (bi.get("tickets") or {}).get("percent")
                    mp = (bi.get("money") or {}).get("percent")
                    if side == "over":
                        if tp:
                            pub_bets_acc.append(float(tp))
                        if mp:
                            pub_money_acc.append(float(mp))

                # Action Network gates player-prop bet_info to PRO; if all
                # entries returned zero, neutral 50.0 (the consumer treats this
                # as "no signal" and falls back to other features).
                pub_bets  = pub_bets_acc[0]  if pub_bets_acc  else 50.0
                pub_money = pub_money_acc[0] if pub_money_acc else 50.0

                key = _prop_key(player, stat)
                result[key] = {
                    "player":           player,
                    "stat":             stat,
                    "line":             line_val,
                    "over_odds":        int(over_odds) if over_odds is not None else None,
                    "under_odds":       int(under_odds) if under_odds is not None else None,
                    "book_id":          book,
                    "public_bets_pct":  round(pub_bets, 1),
                    "public_money_pct": round(pub_money, 1),
                    "rlm":              game_has_rlm,
                    "steam_move":       game_has_rlm,
                    "game_id":          int(game_id),
                    "fetched_at":       fetched_at,
                }

    if result:
        _save_cache(result)
        print(f"[action_network] Fetched {len(result)} prop markets across {len(games)} games")
    else:
        print("[action_network] No prop data returned (API may have changed structure)")

    return result or _load_cache()


# ── Public API ────────────────────────────────────────────────────────────────

def get_sharp_pct(player_name: str, stat: str) -> dict:
    """
    Return Action Network sharp/public split for a player prop.

    Args:
        player_name: Full player name (e.g. "LeBron James"). Case-insensitive.
        stat:        One of: pts, reb, ast, fg3m, stl, blk, tov.

    Returns:
        {
            "public_bets_pct":  float,   # 0-100; high = public heavy on over
            "public_money_pct": float,
            "rlm":              bool,    # reverse line movement detected
            "steam_move":       bool,    # back-compat alias of rlm
            "found":            bool,
        }
    """
    _null = {"public_bets_pct": 50.0, "public_money_pct": 50.0,
             "rlm": False, "steam_move": False, "found": False}

    cache = refresh_action_network()

    def _shape(rec: dict) -> dict:
        rlm = bool(rec.get("rlm", rec.get("steam_move", False)))
        return {
            "public_bets_pct":  rec.get("public_bets_pct", 50.0),
            "public_money_pct": rec.get("public_money_pct", 50.0),
            "rlm":              rlm,
            "steam_move":       rlm,
            "found":            True,
        }

    # Try exact key first
    key = _prop_key(player_name, stat)
    if key in cache:
        return _shape(cache[key])

    # Fuzzy name match (normalise unicode)
    norm = _norm_name(player_name)
    for k, rec in cache.items():
        if k.endswith(f"|{stat}") and _norm_name(rec.get("player", "")) == norm:
            return _shape(rec)

    return _null


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Action Network sharp% monitor")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--player",  help="Player name")
    ap.add_argument("--stat",    default="pts")
    args = ap.parse_args()

    if args.player:
        sig = get_sharp_pct(args.player, args.stat)
        print(json.dumps(sig, indent=2))
    else:
        data = refresh_action_network(force=args.refresh)
        print(f"Action Network props cached: {len(data)}")
        for k, v in list(data.items())[:5]:
            print(f"  {k}: line={v.get('line')} pub%={v['public_bets_pct']} steam={v['steam_move']}")
