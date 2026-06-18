"""scripts.platformkit.odds_provider.prop_underdog -- keyless Underdog props.

Underdog Fantasy publishes its over/under player props at a KEYLESS public JSON
endpoint (beta/v5/over_under_lines). The payload is MULTI-SPORT; we filter to the
World Cup soccer rows (Underdog sport_id "FIFA") for sport key "soccer_intl".

REAL payload shape (probed 2026-06-17), top-level arrays:
  over_under_lines[] : one O/U line. Carries stat_value (the numeric line, e.g.
      2.5), options[] (the higher/lower sides), and over_under.appearance_stat
      with appearance_id + display_stat (the human stat label).
  appearances[]      : id -> {player_id, team_id, match_id}. The join hub.
  players[]          : id -> {first_name, last_name, sport_id, team_id}.
  games[]            : id (int) -> {full_team_names_title, home/away_team_id,
      short_title, sport_id, scheduled_at}. match_id on an appearance == game id.

Pricing: each option carries american_price, decimal_price (the TRUE decimal odds,
e.g. "1.53") AND payout_multiplier (a profit-multiple, e.g. "0.75"). These do NOT
agree: 1 + 0.75 = 1.75 != 1.53. The decimal_price is the real vig-adjusted two-
sided price Underdog quotes (line_type "balanced"), so we use decimal_price
directly and label payout_type "sportsbook". If decimal_price is missing we fall
back to payout_type "dfs_pickem" with over/under price None (never guess a number).

No network at import. http_get is injectable; the default does one urllib GET with
a browser UA + 12s timeout and returns {} on any error. fetch_props NEVER raises.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from .base import is_unavailable, unavailable
from .prop_base import PropLine, canon_stat

logger = logging.getLogger(__name__)

_URL = "https://api.underdogfantasy.com/beta/v5/over_under_lines"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# Our sport key -> Underdog sport_id (probed 2026-06-18). World Cup soccer is
# published as "FIFA"; MLB as "MLB". NBA is "BASKETBALL" on Underdog (no separate
# NBA id -- WNBA/college share it) and is empty in the NBA off-season but wired so
# fetch_props("nba") works the moment lines post.
_SPORT_ID: Dict[str, str] = {
    "soccer_intl": "FIFA",
    "mlb": "MLB",
    "nba": "BASKETBALL",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_http_get(url: str) -> Dict[str, Any]:
    """One keyless GET with a browser UA; returns parsed JSON or {} on any error."""
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001 -- never bubble a network error
        logger.warning("underdog GET failed: %s", exc)
        return {}


def _to_float(val: Any) -> Optional[float]:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f


def _dec_price(opt: Dict[str, Any]) -> Optional[float]:
    """Decimal odds (> 1.0) from an option's decimal_price; None if unusable."""
    d = _to_float(opt.get("decimal_price"))
    if d is not None and d > 1.0:
        return d
    return None


def _player_name(p: Dict[str, Any]) -> str:
    name = " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
    return name.strip()


def _team_name(game: Optional[Dict[str, Any]], team_id: Optional[str]) -> Optional[str]:
    """Resolve a team_id to its display name using a game's home/away titles."""
    if not game or not team_id:
        return None
    title = game.get("full_team_names_title") or game.get("short_title") or ""
    parts = [s.strip() for s in title.split(" vs ")]
    if len(parts) == 2:
        if team_id == game.get("home_team_id"):
            return parts[0]
        if team_id == game.get("away_team_id"):
            return parts[1]
    return None


def _match_title(game: Optional[Dict[str, Any]]) -> Optional[str]:
    if not game:
        return None
    return game.get("full_team_names_title") or game.get("short_title") or None


def parse_props(body: Dict[str, Any], sport: str, sport_id: str,
                ) -> Union[List[PropLine], Dict[str, str]]:
    """Parse a raw over_under_lines payload into PropLine rows for one sport.

    Pure (no network): unit-tested on canned payloads. Joins each O/U line to its
    player + team + match via appearances/players/games, filters to *sport_id*,
    canonicalizes the stat, and prices from option decimal_price. Returns the
    UNAVAILABLE sentinel when the payload is unusable or yields no rows.
    """
    if not isinstance(body, dict):
        return unavailable("underdog: non-dict payload")
    lines = body.get("over_under_lines")
    if not isinstance(lines, list):
        return unavailable("underdog: missing over_under_lines")

    players = {p.get("id"): p for p in body.get("players", []) if isinstance(p, dict)}
    apps = {a.get("id"): a for a in body.get("appearances", []) if isinstance(a, dict)}
    games = {g.get("id"): g for g in body.get("games", []) if isinstance(g, dict)}

    as_of = _now_iso()
    out: List[PropLine] = []
    for o in lines:
        if not isinstance(o, dict):
            continue
        ou = o.get("over_under") or {}
        ast = ou.get("appearance_stat") or {}
        app = apps.get(ast.get("appearance_id"))
        if not app:
            continue
        player = players.get(app.get("player_id"))
        if not player or player.get("sport_id") != sport_id:
            continue
        game = games.get(app.get("match_id"))
        line_val = _to_float(o.get("stat_value"))
        stat = ast.get("display_stat")
        name = _player_name(player)
        if line_val is None or not stat or not name:
            continue

        over_price = under_price = None
        for opt in o.get("options", []):
            if not isinstance(opt, dict):
                continue
            if opt.get("choice") == "higher":
                over_price = _dec_price(opt)
            elif opt.get("choice") == "lower":
                under_price = _dec_price(opt)
        payout = "sportsbook" if (over_price or under_price) else "dfs_pickem"

        out.append(PropLine(
            sport=sport,
            event_id=str(o.get("id") or ast.get("appearance_id") or ""),
            match=_match_title(game),
            player=name,
            team=_team_name(game, app.get("team_id")),
            stat=canon_stat(stat),
            line=line_val,
            over_price=over_price,
            under_price=under_price,
            payout_type=payout,
            source="underdog",
            as_of=as_of,
        ))
    if not out:
        return unavailable(f"underdog: no rows for sport '{sport}'")
    return out


class UnderdogProvider:
    """Keyless Underdog prop provider. fetch_props -> list[PropLine]|UNAVAILABLE."""

    name = "underdog"

    def __init__(self, *, http_get: Optional[Callable[[str], Any]] = None,
                 use_cache: bool = False) -> None:
        self._http_get = http_get or _default_http_get
        self._use_cache = use_cache  # reserved; live fetch is light + keyless

    def fetch_props(self, sport: str,
                    ) -> Union[List[PropLine], Dict[str, str]]:
        sport = (sport or "").lower()
        sport_id = _SPORT_ID.get(sport)
        if not sport_id:
            return unavailable(f"underdog: unsupported sport '{sport}'")
        try:
            body = self._http_get(_URL)
        except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
            logger.warning("underdog fetch failed: %s", exc)
            return unavailable(f"underdog call failed ({type(exc).__name__})")
        if is_unavailable(body):
            return body
        if not isinstance(body, dict) or not body:
            return unavailable("underdog: empty/invalid response")
        return parse_props(body, sport, sport_id)


__all__ = ["UnderdogProvider", "parse_props"]
