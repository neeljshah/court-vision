"""scripts.platformkit.pm_trading.kalshi_pricers -- per-type model pricers that turn a
liquid Kalshi market into our model P(YES), for kalshi_edge_finder's registry.

Two pricers, each backed by a REAL model (never a fabricated number):

  * player_prop -> reuses the prop board (props_snapshot model_p_over). A Kalshi
    "<Player>: K+ <stat>" market YES == P(stat >= K) == the board's P(over K-0.5).
    Returns None when no board projection matches (honest skip).

  * team_total  -> a TRANSPARENT v0 run-rate Poisson baseline (MLB): project the game
    total from each team's runs-scored/allowed per game (statsapi), then P(total >= line)
    via a Poisson survival fn. UNVALIDATED by design -- its only judge is forward CLV vs
    the Kalshi close (the close-capture + ratchet loop). NOT an edge claim.

HONEST RAILS: model probs only (probability space, NEVER a $). A pricer returns None on
ANY gap (unparsable title, no projection, no team rate) so the edge-finder SKIPS rather
than invents. board_lookup / rpg_lookup injected for offline tests. Public fns never raise.

INVARIANTS: scripts/platformkit only; ASCII; <=300 LOC.
Per-file test: scripts/platformkit/pm_trading/test_kalshi_pricers.py
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("kalshi_pricers")

# Kalshi stat phrasing -> our canonical prop_stat (board naming).
_STAT_MAP = {
    "home run": "Home Runs", "home runs": "Home Runs", "hit": "Hits", "hits": "Hits",
    "total base": "Total Bases", "total bases": "Total Bases", "rbi": "RBIs",
    "rbis": "RBIs", "run": "Runs", "runs": "Runs", "stolen base": "Stolen Bases",
    "strikeout": "Pitcher Strikeouts", "strikeouts": "Pitcher Strikeouts",
    "walk": "Walks", "walks": "Walks",
}


def _norm(s: Any) -> str:
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


# --------------------------------------------------------------------------- #
# player_prop pricer
# --------------------------------------------------------------------------- #

def parse_prop_title(title: Any) -> Optional[Tuple[str, str, int]]:
    """'Pete Crow-Armstrong: 1+ home runs' -> ('Pete Crow-Armstrong','Home Runs',1).

    Returns (player, canonical_stat, threshold) or None on any gap."""
    s = str(title or "").strip()
    if ":" not in s:
        return None
    player, rest = s.split(":", 1)
    player = player.strip()
    m = re.search(r"(\d+)\s*\+?", rest)
    if not player or not m:
        return None
    threshold = int(m.group(1))
    tail = rest[m.end():].strip(" ?+").lower()
    stat = _STAT_MAP.get(tail) or _STAT_MAP.get(tail.rstrip("s")) or None
    if stat is None:
        for kw, canon in _STAT_MAP.items():
            if kw in tail:
                stat = canon
                break
    if stat is None or threshold < 1:
        return None
    return player, stat, threshold


def make_prop_pricer(board_lookup: Callable[[str, str, float], Optional[float]]):
    """Build a player_prop Pricer from a board_lookup(player, stat, line)->P(over)."""
    def _pricer(market: Dict[str, Any]) -> Optional[float]:
        parsed = parse_prop_title(market.get("title") or market.get("yes_sub_title"))
        if parsed is None:
            return None
        player, stat, threshold = parsed
        line = float(threshold) - 0.5            # 'K+' YES == P(stat > K-0.5)
        try:
            p = board_lookup(player, stat, line)
        except Exception as exc:  # noqa: BLE001
            logger.debug("prop board_lookup raised: %s", exc)
            return None
        return p if (p is not None and 0.0 <= p <= 1.0) else None
    return _pricer


def _default_board_lookup(player: str, stat: str, line: float) -> Optional[float]:
    """Match the prop board (props_snapshot.json) by player+stat+line -> model_p_over."""
    try:
        import json
        import pathlib
        repo = pathlib.Path(__file__).resolve().parents[3]
        rows = (json.loads((repo / "data" / "frontend" / "props_snapshot.json")
                .read_text(encoding="utf-8")) or {}).get("rows", []) or []
    except Exception:  # noqa: BLE001
        return None
    pk, sk = _norm(player), _norm(stat)
    for r in rows:
        if (_norm(r.get("prop_player")) == pk and _norm(r.get("prop_stat")) == sk
                and abs(float(r.get("line") or -9) - line) < 1e-6):
            mp = r.get("model_p_over")
            if mp is None and r.get("model_prob") is not None and r.get("side") == "over":
                mp = r.get("model_prob")
            return float(mp) if mp is not None else None
    return None


# --------------------------------------------------------------------------- #
# team_total pricer (v0 run-rate Poisson baseline; CLV is the judge)
# --------------------------------------------------------------------------- #

def _poisson_sf(lmbda: float, line: float) -> Optional[float]:
    """P(X >= ceil(line)) for X ~ Poisson(lmbda). A '> line' total YES at e.g. line=8.5
    means >=9; line=9 (integer strike) we treat as >=9. Returns None on bad input."""
    if lmbda <= 0.0:
        return None
    k = math.ceil(line) if (line % 1) else int(line)
    if k <= 0:
        return 1.0
    cdf = 0.0
    term = math.exp(-lmbda)
    for i in range(0, k):
        cdf += term
        term *= lmbda / (i + 1)
    p = 1.0 - cdf
    return min(1.0, max(0.0, p))


def parse_totals_market(market: Dict[str, Any]) -> Optional[Tuple[str, str, float]]:
    """'Philadelphia vs New York M Total Runs?' + strike -> (away, home, line) or None."""
    s = str(market.get("title") or "")
    mt = re.split(r"\bvs\b", s, maxsplit=1, flags=re.IGNORECASE)
    if len(mt) != 2:
        return None
    away = mt[0].strip()
    home = re.sub(r"total runs.*$", "", mt[1], flags=re.IGNORECASE).strip(" ?")
    # line: from the ticker suffix (KXMLBTOTAL-...-9) or yes_sub_title.
    line = None
    tk = str(market.get("ticker") or "")
    mtail = re.search(r"-(\d+(?:\.\d+)?)$", tk)
    if mtail:
        line = float(mtail.group(1))
    if line is None:
        ms = re.search(r"(\d+(?:\.\d+)?)", str(market.get("yes_sub_title") or ""))
        line = float(ms.group(1)) if ms else None
    if not away or not home or line is None:
        return None
    return away, home, line


def make_totals_pricer(rpg_lookup: Callable[[str], Optional[Tuple[float, float]]]):
    """Build a team_total Pricer from rpg_lookup(team)->(runs_scored_pg, runs_allowed_pg)."""
    def _pricer(market: Dict[str, Any]) -> Optional[float]:
        parsed = parse_totals_market(market)
        if parsed is None:
            return None
        away, home, line = parsed
        try:
            a = rpg_lookup(away)
            h = rpg_lookup(home)
        except Exception as exc:  # noqa: BLE001
            logger.debug("rpg_lookup raised: %s", exc)
            return None
        if not a or not h:
            return None
        # expected total = away offense vs home defense + home offense vs away defense
        proj = (a[0] + h[1]) / 2.0 + (h[0] + a[1]) / 2.0
        return _poisson_sf(proj, line)
    return _pricer


_MLB_STATS = "https://statsapi.mlb.com/api/v1/teams/stats?stats=season&sportId=1&season="
_rpg_cache: Dict[str, Tuple[float, float]] = {}


def default_rpg_lookup(season: int = 2026):
    """Live MLB team run-rate lookup(team)->(runs_scored_pg, runs_allowed_pg) from
    statsapi (hitting runs / pitching runs allowed). Cached per process; None on gap."""
    if not _rpg_cache:
        try:
            import json
            import urllib.request
            scored: Dict[str, Tuple[float, float]] = {}
            allowed: Dict[str, Tuple[float, float]] = {}
            for grp, dst in (("hitting", scored), ("pitching", allowed)):
                url = _MLB_STATS + str(season) + "&group=" + grp
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                for sp in (body.get("stats", [{}])[0].get("splits", []) or []):
                    nm = _norm((sp.get("team", {}) or {}).get("name"))
                    st = sp.get("stat", {}) or {}
                    g = float(st.get("gamesPlayed", 0) or 0)
                    if nm and g > 0:
                        dst[nm] = (float(st.get("runs", 0) or 0) / g, g)
            for nm, (rs, _g) in scored.items():
                ra = allowed.get(nm, (0.0, 0.0))[0]
                if ra > 0:
                    _rpg_cache[nm] = (rs, ra)
        except Exception as exc:  # noqa: BLE001
            logger.debug("default_rpg_lookup fetch failed: %s", exc)

    def _lookup(team: Any) -> Optional[Tuple[float, float]]:
        tk = _norm(team)
        if not tk:
            return None
        if tk in _rpg_cache:
            return _rpg_cache[tk]
        for nm, rates in _rpg_cache.items():     # substring (Kalshi uses city/partial)
            if tk in nm or nm in tk:
                return rates
        return None
    return _lookup


def build_pricers(*, board_lookup=None, rpg_lookup=None,
                  live_totals: bool = False) -> Dict[str, Any]:
    """Assemble the edge-finder pricer registry. team_total is included ONLY when a
    rpg_lookup is supplied (or live_totals=True for the statsapi default) -- with no run
    model, totals are HONESTLY ABSENT (skipped by the finder), never priced from air."""
    bl = board_lookup or _default_board_lookup
    pricers: Dict[str, Any] = {"player_prop": make_prop_pricer(bl)}
    rl = rpg_lookup or (default_rpg_lookup() if live_totals else None)
    if rl is not None:
        pricers["team_total"] = make_totals_pricer(rl)
    return pricers


__all__ = ["parse_prop_title", "make_prop_pricer", "parse_totals_market",
           "make_totals_pricer", "build_pricers", "_poisson_sf"]
