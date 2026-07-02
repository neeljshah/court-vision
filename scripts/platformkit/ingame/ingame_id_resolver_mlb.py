"""scripts.platformkit.ingame.ingame_id_resolver_mlb -- Kalshi <-> statsapi MLB id bridge.

The active in-play capture keys games by their KALSHI TICKER (e.g.
``KXMLBGAME-26JUN271810AZTB``), which never equals a statsapi ``gamePk`` or an ESPN
numeric event id.  Because of that the authoritative DEEP in-game state (outs + base
runners + count -> RE24) could not be attached to the live grade series.  This resolver
closes the gap:

  * parse_kalshi_mlb_ticker(ticker)            -> {yy,mon,dd,hhmm,blob} | None
  * resolve_ticker(ticker, candidates=..)      -> {game_pk,home,away,..} | None
  * linescore_deep_fields(linescore)           -> {inning,half,outs,base,bos,re,count}
  * deep_state_for_ticker(ticker, ..)          -> the deep fields + game_pk (or {})
  * make_tick_deep_fn(..)                       -> a LAZY per-tick (gid)->dict enricher

The ticker's away+home Kalshi-abbrev blob (``AZTB`` = AZ @ TB) is matched against the LIVE
statsapi candidates from ingame_box_mlb.live_games() (gamePk + full team names) by EXACT
mapped-abbrev equality.  With the gamePk it reads the keyless statsapi LINESCORE (outs +
balls/strikes + offense base runners) and feeds it through the EXISTING base-out extractor
(ingame_baseout_mlb.parse_baseout) -- no parallel base-out math that could drift.

WHY statsapi (not just the ESPN scoreboard situation): the statsapi linescore is the
authoritative per-game source AND the gamePk it yields is the JOIN KEY the rest of the
deep-in-game queue needs (true-close capture, pitcher/batter/leverage, base-out ->
win-prob validation).  Resolve once, reuse.

HONEST RAILS (binding):
  * NEVER mis-binds: a ticker resolves ONLY when EXACTLY ONE live candidate's mapped
    (away_abbr + home_abbr) equals the ticker blob.  Zero or >1 (a simultaneous
    doubleheader) -> None, so the caller SKIPS rather than bind the wrong game (a mis-bind
    manufactures fake state + fake CLV).
  * Reads PUBLIC keyless statsapi only.  UNITS / probability work happens downstream;
    this module supplies descriptive state, never a price or an edge.
  * Never fabricates: an unparseable ticker / unmatched game / absent linescore -> {}/None
    (clean skip), never a fabricated state.
  * Pure except the injectable http_get; public fns NEVER raise.

INVARIANTS: build only under scripts/platformkit/; ASCII; <=300 LOC; no edge claims.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/ingame/test_ingame_id_resolver_mlb.py -q
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame import ingame_baseout_mlb as _baseout

logger = logging.getLogger(__name__)

_LINESCORE = "https://statsapi.mlb.com/api/v1/game/%s/linescore"
_BOXSCORE = "https://statsapi.mlb.com/api/v1/game/%s/boxscore"

# statsapi full team name (lower-cased) -> Kalshi MLB game-series abbreviation.  Kalshi's
# abbrevs differ from ESPN/statsapi in a few spots (AZ not ARI, CWS not CHW, SD not SDP,
# WSH not WAS) -- these are the canonical KX*GAME-ticker abbrevs.  Validated against the
# live KXMLBGAME feed; a missing team -> no match (honest skip), never a wrong bind.
KALSHI_ABBR: Dict[str, str] = {
    "arizona diamondbacks": "AZ",
    "atlanta braves": "ATL",
    "baltimore orioles": "BAL",
    "boston red sox": "BOS",
    "chicago cubs": "CHC",
    "chicago white sox": "CWS",
    "cincinnati reds": "CIN",
    "cleveland guardians": "CLE",
    "colorado rockies": "COL",
    "detroit tigers": "DET",
    "houston astros": "HOU",
    "kansas city royals": "KC",
    "los angeles angels": "LAA",
    "los angeles dodgers": "LAD",
    "miami marlins": "MIA",
    "milwaukee brewers": "MIL",
    "minnesota twins": "MIN",
    "new york mets": "NYM",
    "new york yankees": "NYY",
    "athletics": "ATH",
    "oakland athletics": "ATH",
    "philadelphia phillies": "PHI",
    "pittsburgh pirates": "PIT",
    "san diego padres": "SD",
    "san francisco giants": "SF",
    "seattle mariners": "SEA",
    "st. louis cardinals": "STL",
    "tampa bay rays": "TB",
    "texas rangers": "TEX",
    "toronto blue jays": "TOR",
    "washington nationals": "WSH",
}

# KXMLBGAME-<YY><MON><DD><HHMM><AWAY+HOME blob>, e.g. 26JUN271810AZTB.
_TICKER_RE = re.compile(r"^KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})([A-Z]+)$", re.I)


def _norm(name: Any) -> str:
    """Lower-case + single-space a statsapi team name for the abbrev lookup."""
    return " ".join(str(name or "").lower().split())


def parse_kalshi_mlb_ticker(ticker: Any) -> Optional[Dict[str, str]]:
    """Parse a Kalshi MLB game ticker into its parts, or None if it is not one.

    Returns {yy,mon,dd,hhmm,blob} (blob = the concatenated away+home abbrevs, upper-case).
    Never raises.
    """
    m = _TICKER_RE.match(str(ticker or "").strip())
    if not m:
        return None
    yy, mon, dd, hhmm, blob = m.groups()
    return {"yy": yy, "mon": mon.upper(), "dd": dd, "hhmm": hhmm, "blob": blob.upper()}


def _expected_blob(candidate: Dict[str, Any]) -> Optional[str]:
    """The candidate game's expected ticker blob (away_abbr + home_abbr), or None.

    None when EITHER team is absent from KALSHI_ABBR -- so an unmapped team can never
    produce a (wrong) match; it just fails to resolve (honest skip)."""
    away = KALSHI_ABBR.get(_norm(candidate.get("away")))
    home = KALSHI_ABBR.get(_norm(candidate.get("home")))
    if not away or not home:
        return None
    return away + home


def _default_candidates(http_get: Optional[Callable[[str], Any]] = None
                        ) -> List[Dict[str, Any]]:
    """The LIVE statsapi MLB games as resolve candidates (gamePk + full team names).

    Reuses ingame_box_mlb.live_games (keyless statsapi schedule) so the LIVE set the
    resolver matches against is the SAME one the rest of the in-game stack reads. [] on
    any failure -- never raises."""
    try:
        from scripts.platformkit.ingame import ingame_box_mlb as _box
        return list(_box.live_games(http_get=http_get) if http_get
                    else _box.live_games())
    except Exception as exc:  # noqa: BLE001 -- a feed error is no candidates, never a crash
        logger.debug("ingame_id_resolver_mlb candidates failed: %s", exc)
        return []


def resolve_ticker(ticker: Any, *,
                   candidates: Optional[List[Dict[str, Any]]] = None,
                   http_get: Optional[Callable[[str], Any]] = None
                   ) -> Optional[Dict[str, Any]]:
    """Resolve a Kalshi MLB ticker to its statsapi game, or None.

    Matches the ticker's away+home blob against *candidates* (default: the LIVE statsapi
    games) by EXACT mapped-abbrev equality.  Returns {game_pk, home, away, away_abbr,
    home_abbr} on a UNIQUE match; None on zero or >1 match (ambiguity -> skip, NEVER a
    wrong bind).  Never raises.
    """
    parsed = parse_kalshi_mlb_ticker(ticker)
    if parsed is None:
        return None
    blob = parsed["blob"]
    cands = candidates if candidates is not None else _default_candidates(http_get)
    hits = [c for c in cands if isinstance(c, dict) and _expected_blob(c) == blob]
    if len(hits) != 1:  # 0 = no live match; >1 = ambiguous (e.g. live doubleheader)
        return None
    c = hits[0]
    return {
        "game_pk": str(c.get("game_pk")),
        "home": c.get("home"), "away": c.get("away"),
        "away_abbr": KALSHI_ABBR.get(_norm(c.get("away"))),
        "home_abbr": KALSHI_ABBR.get(_norm(c.get("home"))),
        # Carry the candidate's already-fetched linescore (live_games attaches it) so
        # deep_state_for_ticker REUSES it instead of re-GETting -- None when absent (the
        # deep reader then fetches it, so injected-candidate tests still work).
        "linescore": c.get("linescore"),
    }


def _linescore_situation(ls: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt a statsapi linescore to the ESPN-shaped ``situation`` parse_baseout expects.

    statsapi carries outs/balls/strikes at the top level and the occupied bases as keys
    under ``offense`` (first/second/third present only when occupied).  This maps them onto
    onFirst/onSecond/onThird booleans so the EXISTING extractor (RE24 table + base mask) is
    reused verbatim -- no parallel base-out logic that could drift."""
    off = ls.get("offense") if isinstance(ls.get("offense"), dict) else {}
    return {
        "outs": ls.get("outs"),
        "balls": ls.get("balls"),
        "strikes": ls.get("strikes"),
        "onFirst": off.get("first") is not None,
        "onSecond": off.get("second") is not None,
        "onThird": off.get("third") is not None,
    }


def linescore_deep_fields(ls: Dict[str, Any]) -> Dict[str, Any]:
    """Deep in-game fields from a statsapi linescore (else {} -- honest, no fabrication).

    Returns {inning, half, outs, base, bos, re, count} where outs/base/bos/re/count come
    from ingame_baseout_mlb (the RE24 base-out encoding).  Between half-innings (3 outs,
    inningState Middle/End) the base-out block is absent by design -- parse_baseout's
    [0,2]-out guard skips it -- so a transient non-state is never recorded."""
    if not isinstance(ls, dict) or not ls:
        return {}
    out: Dict[str, Any] = {}
    try:
        inn = int(ls.get("currentInning") or 0)
        if inn > 0:
            out["inning"] = inn
    except (TypeError, ValueError):
        pass
    state = str(ls.get("inningState") or "").lower()
    is_top = ls.get("isTopInning")
    if is_top is True or state.startswith("top"):
        out["half"] = "top"
    elif is_top is False or state.startswith("bot"):
        out["half"] = "bottom"
    # base-out / RE24 via the SAME extractor the ESPN path uses (reuse, never duplicate).
    out.update(_baseout.baseout_summary_fields("mlb", {"situation": _linescore_situation(ls)}))
    return out


def _fetch(url: str, http_get: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    """Read a keyless statsapi JSON body. {} on any failure -- never raises."""
    try:
        if http_get is not None:
            body = http_get(url)
        else:
            from scripts.platformkit.bestbets.prop_settler_mlb import _http_get_json
            body = _http_get_json(url)
        return body if isinstance(body, dict) else {}
    except Exception as exc:  # noqa: BLE001 -- a feed error is no body, never a crash
        logger.debug("ingame_id_resolver_mlb fetch %s failed: %s", url, exc)
        return {}


def _fetch_linescore(game_pk: str,
                     http_get: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    """Read one game's statsapi linescore (keyless). {} on any failure -- never raises."""
    return _fetch(_LINESCORE % game_pk, http_get)


def deep_state_for_ticker(ticker: Any, *,
                          candidates: Optional[List[Dict[str, Any]]] = None,
                          http_get: Optional[Callable[[str], Any]] = None
                          ) -> Dict[str, Any]:
    """Resolve *ticker* -> gamePk -> statsapi linescore -> deep base-out fields.

    Returns the deep fields plus {game_pk} on success, or {} when the ticker cannot be
    resolved / the linescore is absent (honest skip; the caller leaves the state shallow
    rather than carry a fabricated one).  Never raises.
    """
    res = resolve_ticker(ticker, candidates=candidates, http_get=http_get)
    if res is None:
        return {}
    pk = res["game_pk"]
    # Prefer the linescore the candidate already carries (live_games fetched it for frac) ->
    # no redundant per-tick GET; fall back to a fetch for injected-candidate / test paths.
    ls = res.get("linescore") or _fetch_linescore(pk, http_get)
    deep = linescore_deep_fields(ls)
    # DEEP pitcher/batter/pitch-count/TTO (needs the boxscore) -- ADDITIVE + guarded so a
    # boxscore miss never blocks the base-out (linescore) state that already flowed.
    try:
        from scripts.platformkit.ingame import ingame_pitcher_mlb as _pit
        deep.update(_pit.pitcher_batter_fields(ls, _fetch(_BOXSCORE % pk, http_get)))
    except Exception as exc:  # noqa: BLE001 -- pitcher state is additive, never fatal
        logger.debug("ingame_id_resolver_mlb pitcher %s failed: %s", pk, exc)
    if deep:
        deep["game_pk"] = pk
    return deep


def make_tick_deep_fn(*, candidates_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                      resolver_fn: Optional[Callable[..., Dict[str, Any]]] = None,
                      http_get: Optional[Callable[[str], Any]] = None
                      ) -> Callable[[str], Dict[str, Any]]:
    """A LAZY per-tick (kalshi_ticker) -> deep-state enricher for the capture loop.

    The returned callable memoizes the live candidate set on its FIRST call within a tick
    (so a tick with NO mlb game to enrich makes NO network call -- the dead-feed test path
    stays offline) then resolves each ticker's deep state against it.  *candidates_fn* and
    *resolver_fn* are injectable so the tested path needs no network.  Never raises (any
    error -> {} for that game)."""
    cand_fn = candidates_fn or (lambda: _default_candidates(http_get))
    res_fn = resolver_fn or deep_state_for_ticker
    cache: Dict[str, Any] = {"cands": None, "loaded": False}

    def _deep(gid: str) -> Dict[str, Any]:
        try:
            if not cache["loaded"]:
                cache["cands"] = cand_fn()
                cache["loaded"] = True
            return res_fn(gid, candidates=cache["cands"], http_get=http_get) or {}
        except Exception as exc:  # noqa: BLE001 -- enrichment is additive; never break capture
            logger.debug("ingame_id_resolver_mlb deep(%s) failed: %s", gid, exc)
            return {}

    return _deep


__all__ = [
    "KALSHI_ABBR",
    "parse_kalshi_mlb_ticker",
    "resolve_ticker",
    "linescore_deep_fields",
    "deep_state_for_ticker",
    "make_tick_deep_fn",
]
