"""scripts.platformkit.bestbets.prop_cards -- player-prop BestBetCard builder.

Surfaces PLAYER-PROP predictions as cards on the SAME unified board the /bets page
reads. Source = the live prop board (prop_edge.build_prop_board) for sports with
props TODAY -- soccer_intl + mlb. Each edge -> a market_type="prop" card. The
MODEL-ONLY synth fallback (prop_cards_bounded) calls cards_from_lines() with
parquet no-price lines so props flow even when the feed (PrizePicks / Underdog) 429s.
Each card also carries the REAL game_id of its underlying game (via _game_id_index,
the SAME edge view the v1 detail board uses) so "View detail" links resolve.

HONESTY (binding): edge_claimed ALWAYS False. MODEL-ONLY ("model_view"):
market_prob/edge_vs_market NULL, model_only=True. PRICED ("ev_vs_priced"):
edge_vs_market = model_prob - market_prob, a LABELLED prob diff (NOT $), no
beat-the-close. UNITS not $ (flat 1.0). STALE-NEVER-GREEN: a board whose as_of is
before today (ET calendar day) is DROPPED. No flag flip, no data/registry write, no $.

RAILS: ASCII only; stdlib + repo-internal; <=300 LOC; public fns NEVER raise.
Per-file test: scripts/platformkit/bestbets/test_prop_cards.py
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Sports whose prop board produces edges today (NBA omitted -- offseason, no feed).
DEFAULT_PROP_SPORTS = ("soccer_intl", "mlb")
# Cap on MODEL-ONLY cards served per sport; priced cards are ALWAYS kept. Overflow
# is counted in an honest "N more" tally, never silently dropped.
DEFAULT_MODEL_ONLY_CAP = 50
# Cap on prop LINES priced per sport (priced kept first) so the m13 tick fits 300 s.
# 0 = price the full board (offline analysis).
DEFAULT_MAX_LINES_PER_SPORT = 2500

_MODEL_ONLY_NOTE = (
    "MODEL-ONLY player prop: no market line/price -> a calibrated P(side) + "
    "projection only. NO edge / CLV claimed (edge_vs_market=null). UNITS not $."
)
_PRICED_NOTE = (
    "Player prop priced vs a SOFT DFS / sportsbook line. edge_vs_market = "
    "model_prob - market_prob (prob diff, NOT $); not beat-the-close. UNITS not $."
)


def _today_et() -> str:
    """Today's date as the ET calendar day (YYYY-MM-DD). The slate/event boundary is
    an ET day (paper/ + producer convention) so a late-ET board is not dropped a day
    early. Falls back to the UTC date when the shared et_day helper cannot import."""
    try:
        from scripts.platformkit.paper.et_day import now_et_day  # noqa: PLC0415
        return now_et_day()
    except Exception:  # noqa: BLE001 -- et_day unavailable: UTC date fallback
        return datetime.now(tz=timezone.utc).date().isoformat()


def _norm_team(name: Any) -> str:
    """Forgiving team-name join key (case/space/punct-insensitive)."""
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _split_match(match: Any) -> Optional[tuple]:
    """Split a prop 'match' into (a, b) team tokens. Soccer uses ' vs ', MLB uses
    ' @ ' (away @ home); ' v ' tolerated. None when unparseable."""
    s = str(match or "").strip()
    for sep in (" @ ", " vs ", " vs. ", " v ", " V ", "@"):
        if sep in s:
            a, b = (p.strip() for p in s.split(sep, 1))
            if a and b:
                return a, b
    return None


def _game_id_index(sport: str) -> Dict[frozenset, str]:
    """Unordered team-pair -> real game_id map from the SAME edge view the v1 detail
    board uses (build_edge_view), so a prop links to its game's detail page. Unordered:
    'A vs B' and 'B @ A' both resolve. Failure / no games -> {} (link disabled, never a
    fabricated id). Never raises."""
    index: Dict[frozenset, str] = {}
    try:
        from frontend.edge_api import build_edge_view  # noqa: PLC0415
        view = build_edge_view(sport)
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_cards: edge view(%s) unavailable: %s", sport, exc)
        return index
    if not isinstance(view, dict) or view.get("status") != "ok":
        return index
    for g in view.get("games") or []:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("game_id") or "")
        home, away = _norm_team(g.get("home")), _norm_team(g.get("away"))
        if gid and home and away:
            index[frozenset((home, away))] = gid
    return index


def _resolve_game_id(match: Any, index: Dict[frozenset, str]) -> str:
    """Real game_id for a prop's match via the team-pair index; '' when no served
    game resolves (rare -> link disabled, NEVER a fabricated id)."""
    pair = _split_match(match) if index else None
    if pair is None:
        return ""
    return index.get(frozenset((_norm_team(pair[0]), _norm_team(pair[1]))), "")


def _is_stale(as_of: Any, today: str) -> bool:
    """True when as_of (date prefix) is strictly before *today* (ET day) -> past event.
    Missing / unparseable as_of is NOT stale (board emits only future/current)."""
    if not as_of:
        return False
    try:
        d = str(as_of)[:10]
        return d < today
    except Exception:  # noqa: BLE001
        return False


def _model_prob_for_side(edge: Dict[str, Any]) -> Optional[float]:
    """Model probability for the edge's chosen side (over -> p_over; under -> 1-p_over)."""
    try:
        p_over = float(edge.get("model_p_over"))
    except (TypeError, ValueError):
        return None
    if not (0.0 <= p_over <= 1.0):
        return None
    side = str(edge.get("side", "over")).lower()
    return p_over if side != "under" else round(1.0 - p_over, 6)


def _market_prob_for_side(edge: Dict[str, Any]) -> Optional[float]:
    """Devigged fair market prob for the chosen side, ONLY for priced edges (uses
    fair_over/fair_under). None for model-only edges so no edge is fabricated."""
    if str(edge.get("edge_basis", "")) != "ev_vs_priced":
        return None
    side = str(edge.get("side", "over")).lower()
    key = "fair_under" if side == "under" else "fair_over"
    raw = edge.get(key)
    try:
        mp = float(raw)
    except (TypeError, ValueError):
        return None
    if not (0.0 <= mp <= 1.0):
        return None
    return round(mp, 6)


def _card_from_edge(edge: Dict[str, Any], sport: str,
                    game_index: Optional[Dict[frozenset, str]] = None,
                    ) -> Optional[Dict[str, Any]]:
    """Map one prop-board edge to a BestBetCard. Returns None on unusable rows.
    *game_index* (team-pair -> real game_id) links the prop to its underlying game's
    detail page; '' when no game resolves (link disabled, never a fabricated id)."""
    if not isinstance(edge, dict):
        return None
    player = str(edge.get("player") or edge.get("matched_name") or "")
    stat = str(edge.get("stat") or "")
    if not player or not stat:
        return None
    model_prob = _model_prob_for_side(edge)
    if model_prob is None:
        return None
    side = str(edge.get("side", "over")).lower()
    line = edge.get("line")
    try:
        line_f: Optional[float] = float(line) if line is not None else None
    except (TypeError, ValueError):
        line_f = None
    try:
        proj = float(edge.get("model_lam")) if edge.get("model_lam") is not None else None
    except (TypeError, ValueError):
        proj = None

    market_prob = _market_prob_for_side(edge)
    model_only = market_prob is None
    if model_only:
        edge_vs_market: Optional[float] = None
        note = _MODEL_ONLY_NOTE
    else:
        edge_vs_market = round(model_prob - market_prob, 6)
        note = _PRICED_NOTE

    match = str(edge.get("match") or "")
    # game_id links the prop to its underlying game's detail page (real v1 board id);
    # '' (link disabled) when no served game resolves -- never fabricated. UNITS not $.
    game_id = _resolve_game_id(match, game_index or {})
    return {
        "game_id": game_id, "matchup": match, "sport": sport,
        "market_type": "prop", "prop_player": player, "prop_stat": stat,
        "line": line_f, "side": side, "model_prob": round(model_prob, 6),
        "proj": (round(proj, 4) if proj is not None else None),
        "market_prob": market_prob, "best_book": str(edge.get("source") or ""),
        "best_odds": None, "all_books": [], "edge_vs_market": edge_vs_market,
        "units": 1.0, "tier": str(edge.get("tier") or "MODEL_VIEW"),
        "confidence": round(model_prob, 6),
        "calibration": str(edge.get("calibration") or "unmeasured"),
        "reliable": bool(edge.get("reliable")), "ev_flag": str(edge.get("ev_flag") or ""),
        "edge_basis": str(edge.get("edge_basis") or "model_view"),
        "model_only": model_only, "edge_claimed": False,
        "clv": {"clv_pct": None, "beat_close": None,
                "clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True},
        "clv_is_proxy": True, "status": "pregame",
        "as_of": str(edge.get("as_of") or ""), "honest_note": note,
    }


def _is_priced_line(line: Any) -> bool:
    """True when a PropLine has a real two-way sportsbook price (bettable, not a
    model-only DFS pick'em). Lets us keep ALL priced lines under the cap."""
    try:
        return (getattr(line, "over_price", None) is not None
                and getattr(line, "under_price", None) is not None
                and getattr(line, "payout_type", None) == "sportsbook")
    except Exception:  # noqa: BLE001
        return False


def last_circuit_skips(sport: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Circuit-breaker SKIPPED_CIRCUIT entries recorded on the most recent
    _capped_lines() call, keyed by sport (delegates to prop_cards_circuit_io so
    this file stays <=300 LOC). Never raises."""
    from scripts.platformkit.bestbets import prop_cards_circuit_io as _pcio  # noqa: PLC0415
    return _pcio.last_circuit_skips(sport)


def _capped_lines(sport: str, max_lines: int) -> Optional[List[Any]]:
    """Fetch + cap provider lines for *sport* to *max_lines* (ALL priced first;
    model-only tail truncated). None when providers/config unavailable. 429 RESILIENCE:
    on an empty gather (feed throttled) REUSE the disk-cached last-good set rather than
    re-poll; never fabricate a line. Never raises. CIRCUIT BREAKER (m13-circuit): a
    provider with 3 consecutive failures is skipped for a cooldown BEFORE dispatch
    (never inline-called dead) -- see prop_cards_circuit_io / last_circuit_skips."""
    if max_lines <= 0:
        return None
    from scripts.platformkit.bestbets import prop_cards_cache as _cc  # noqa: PLC0415
    from scripts.platformkit.bestbets import prop_cards_circuit_io as _pcio  # noqa: PLC0415
    cached = _cc.line_cache_read(sport)
    try:
        from scripts.platformkit import prop_edge as _pe  # noqa: PLC0415
        from scripts.platformkit import prop_edge_config  # noqa: PLC0415
        cfg = prop_edge_config.get_config(sport)
        if cfg is None:
            return None
        providers = _pcio.apply_circuit_breaker(sport, cfg.default_providers())
        lines, _sources = _pe._gather(providers, sport)
        _pcio.record_circuit_results(_sources)
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_cards: line gather(%s) failed: %s", sport, exc)
        lines = []
    if lines:
        _cc.line_cache_write(sport, lines)  # refresh last-good snapshot
    elif cached:
        # Feed empty / 429-throttled -> reuse the short-lived last-good snapshot so
        # priced props keep flowing without re-polling the rate-limited feed.
        logger.debug("prop_cards: feed(%s) empty; reusing cached lines", sport)
        lines = cached
    if not lines:
        return None
    priced = [ln for ln in lines if _is_priced_line(ln)]
    other = [ln for ln in lines if not _is_priced_line(ln)]
    capped = priced + other[: max(0, max_lines - len(priced))]
    return capped


def _board_edges(sport: str, max_lines: int = 0,
                 lines_source: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    """Fetch the live prop board for *sport*; [] on any failure. Never raises.
    max_lines > 0 caps fed lines (priced first) for the m13 budget; 0 = full board.
    *lines_source* OVERRIDES the feed (synth fallback prices parquet no-price lines)."""
    try:
        from scripts.platformkit.prop_edge import build_prop_board  # noqa: PLC0415
        src = lines_source
        if src is None and max_lines > 0:
            src = _capped_lines(sport, max_lines)
        board = (build_prop_board(sport, lines_source=src)
                 if src is not None else build_prop_board(sport))
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_cards: build_prop_board(%s) failed: %s", sport, exc)
        return []
    if not isinstance(board, dict):
        return []
    status = str(board.get("status", ""))
    if not status.startswith("ok"):  # honest UNAVAILABLE (offseason / no_data)
        return []
    edges = board.get("edges") or []
    return [e for e in edges if isinstance(e, dict)]


def _cards_from_edges(edges: List[Dict[str, Any]], sport: str, today: str,
                      reliable_only: bool) -> List[Dict[str, Any]]:
    """Filter (stale / reliability) + map board edges to cards. Shared by the feed
    and model-only synthesis paths so they never drift. Builds the team-pair ->
    game_id index ONCE per call (one edge-view read) so every prop card carries the
    real game_id of its underlying game. Never raises."""
    out: List[Dict[str, Any]] = []
    game_index = _game_id_index(sport)
    for edge in edges:
        if _is_stale(edge.get("as_of"), today):
            continue
        if reliable_only:
            ok_flag = str(edge.get("ev_flag", "")) == "ok"
            if not (bool(edge.get("reliable")) and ok_flag):
                continue
        card = _card_from_edge(edge, sport, game_index)
        if card is not None:
            out.append(card)
    return out


def _today_for(now: Optional[float]) -> str:
    """The event/stale-boundary date for epoch *now* as the ET calendar day: the
    epoch is read as a UTC instant then bucketed onto its America/New_York day (so a
    late-ET slate is not dropped early). UTC-date fallback if et_day cannot import."""
    try:
        if now is not None:
            from datetime import datetime as _dt  # noqa: PLC0415
            inst = _dt.fromtimestamp(now, tz=timezone.utc)
            try:
                from scripts.platformkit.paper.et_day import now_et_day  # noqa: PLC0415
                return now_et_day(inst)
            except Exception:  # noqa: BLE001 -- et_day unavailable: UTC fallback
                return inst.date().isoformat()
    except (OSError, OverflowError, ValueError):
        pass
    return _today_et()


def cards_from_lines(sport: str, lines: List[Any], *, now: Optional[float] = None,
                     reliable_only: bool = True) -> List[Dict[str, Any]]:
    """Price an EXPLICIT PropLine list for *sport* into cards, bypassing the feed.
    Used by the model-only synthesis fallback (no-price parquet lines). Never raises."""
    today = _today_for(now)
    return _cards_from_edges(_board_edges(sport, lines_source=lines), sport,
                             today, reliable_only)


def build_prop_cards(
    now: Optional[float] = None,
    sports: Optional[tuple] = None,
    reliable_only: bool = True,
    max_lines_per_sport: int = 0,
) -> List[Dict[str, Any]]:
    """BestBetCards (market_type="prop") for every sport with live props. now: epoch
    stale-guard ref. sports: fan-out override (default DEFAULT_PROP_SPORTS).
    reliable_only: keep reliable + ev_flag=="ok". max_lines_per_sport: >0 caps priced
    LINES (priced first; m13 budget), 0 = full board. Never raises -> []. Model-only
    cards carry model_only=True / NO edge; priced carry edge_vs_market (prob diff). No $."""
    today = _today_for(now)
    _sports = sports if sports is not None else DEFAULT_PROP_SPORTS

    from scripts.platformkit.bestbets import prop_cards_circuit_io as _pcio  # noqa: PLC0415

    cards: List[Dict[str, Any]] = []
    for sport in _sports:
        edges = _board_edges(sport, max_lines=max_lines_per_sport)
        sport_cards = _cards_from_edges(edges, sport, today, reliable_only)
        if max_lines_per_sport > 0:
            _pcio.stamp_circuit_skips(sport_cards, sport)
        cards.extend(sport_cards)
    return cards


# Bounded/ranked SERVED path lives in prop_cards_bounded.py (keeps this <=300 LOC).
from scripts.platformkit.bestbets.prop_cards_bounded import (  # noqa: E402
    build_bounded_prop_cards, build_synth_only_prop_cards, pregame_games_exist)

__all__ = [
    "DEFAULT_PROP_SPORTS", "DEFAULT_MODEL_ONLY_CAP", "DEFAULT_MAX_LINES_PER_SPORT",
    "build_prop_cards", "cards_from_lines", "build_bounded_prop_cards",
    "build_synth_only_prop_cards", "pregame_games_exist", "last_circuit_skips"]
