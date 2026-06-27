"""frontend.edge_api -- the DEEP lines-vs-predictions comparison assembler.

The core sellable object: for EVERY game in a sport's canonical snapshot, set the
model probabilities beside every market quote (one row per book), then build a
per-(market_type, side) COMPARISON that picks the best devigged market probability
across books and reports the model-vs-market gap as a pure probability/EV edge --
NEVER a dollar amount.

  build_edge_view(sport, *, store_out_dir=None) -> dict   # every game
  build_game_edge(sport, game_id, *, store_out_dir=None)  # one game / unavailable
  cache_key(sport, *, store_out_dir=None) -> str          # ETag = generated_at

cache_key returns the snapshot's generated_at: the assembler is PURE over one
O(1) store read, so generated_at fully identifies the output (304 on no change).

HONESTY (enforced by shape): NO dollar / $edge / roi / pnl key ANYWHERE. The edge
is model_prob - market_prob (probability space) plus EV and the evidence tier; CLV
(better-number-than-close) is the only money-adjacent yardstick and is flagged
clv_is_proxy where the close is a proxy. Markets are efficient; edge_claimed is
always False. DEPTH HONESTY: we present only markets the snapshot actually carried
(moneyline usually; spread/total when present) and NEVER fabricate a missing line,
book, or price -- a market with no devigged quote simply yields no comparison row.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no $ key; no secrets.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from frontend.edge_compare import comparison as _comparison
from frontend.edge_compare import edge_lookup as _edge_lookup
from predict_service.contracts import HONEST_NOTE, SCHEMA_VERSION
from predict_service.store import read_latest

logger = logging.getLogger(__name__)

_EDGE_NOTE = (
    "edge = model_prob - market_prob (probability space). No $ edge is claimed; "
    "markets are efficient. CLV (better-number-than-close) is the only honest "
    "yardstick and is flagged clv_is_proxy where the close is a proxy."
)


def _freshness(captured_at: Optional[str],
               market_type: Optional[str]) -> Dict[str, Any]:
    """Guarded freshness of the newest captured-at; 'unknown' on any miss."""
    try:
        from scripts.platformkit.odds_provider.freshness import freshness_status
        return freshness_status(captured_at, market_type=market_type)
    except Exception as exc:  # noqa: BLE001 -- freshness is advisory, never fatal
        logger.warning("edge_api: freshness failed: %s", exc)
        return {"status": "unknown", "age_sec": None}


def _fresh_line_quotes(game_id: str) -> Dict[Any, Dict[str, Any]]:
    """Most-recent on-disk book quote per (market_type, side) for *game_id*.

    PURE on-disk read of the captured line history (NO network) via the vetted
    line_store.get_latest -- the same append-only quotes the CLV pipeline grades.
    This is how TOTAL and SPREAD (run-line) quotes reach the board even when the
    canonical snapshot carried only moneyline: a market the model never priced
    still has a real, fresh, captured book line here. Returns {} on any miss /
    no history; NEVER fabricates a line and NEVER raises. Patchable in tests so a
    fixture stays hermetic (no real history read)."""
    try:
        from scripts.platformkit.odds_provider.line_store import get_latest
        return get_latest(str(game_id)) or {}
    except Exception as exc:  # noqa: BLE001 -- line history is advisory here
        logger.debug("edge_api: fresh line quotes failed gid=%s: %s", game_id, exc)
        return {}


def _market_view(m: Any) -> Dict[str, Any]:
    """Project one MarketRow to its quote view (every book line, verbatim)."""
    d = m.to_dict() if hasattr(m, "to_dict") else dict(m)
    return {
        "market_type": d.get("market_type"),
        "side": d.get("side"),
        "book": d.get("book", ""),
        "line": d.get("line"),
        "odds": d.get("odds"),
        "devigged_prob": d.get("devigged_prob"),
        "captured_at": d.get("captured_at"),
        "is_close": bool(d.get("is_close", False)),
        "clv_is_proxy": bool(d.get("clv_is_proxy", False)),
    }


def _quote_view(mtype: str, side: str, q: Dict[str, Any]) -> Dict[str, Any]:
    """Project one line_store quote row to the same shape as _market_view."""
    return {
        "market_type": mtype,
        "side": side,
        "book": q.get("book", ""),
        "line": q.get("line"),
        "odds": q.get("odds"),
        "devigged_prob": q.get("devigged_prob"),
        "captured_at": q.get("captured_at"),
        "is_close": bool(q.get("is_close", False)),
        "clv_is_proxy": bool(q.get("clv_is_proxy", True)),
    }


def _collect_markets(record: Any, env: Any, game_id: str) -> List[Dict[str, Any]]:
    """Every MarketRow for this game (record-level + envelope-level), deduped, PLUS
    the freshest captured TOTAL / SPREAD (and any other) book quote that the
    snapshot itself did not carry. The snapshot's own rows always win (vetted
    upstream); a line_store quote is only added for a (market_type, side) the
    snapshot lacked -- so moneyline stays exactly as before while total/spread
    surface as their own rows. No fabricated lines; never raises."""
    seen = set()
    snapshot_ms: set = set()
    out: List[Dict[str, Any]] = []
    for m in list(getattr(record, "markets", []) or []) + list(getattr(env, "markets", []) or []):
        if str(getattr(m, "game_id", "")) != game_id:
            continue
        snapshot_ms.add((str(m.market_type), str(m.side)))
        key = (m.market_type, m.side, m.book, m.line, m.captured_at)
        if key in seen:
            continue
        seen.add(key)
        out.append(_market_view(m))
    # Merge fresh captured quotes for market/side pairs the snapshot did not carry.
    for ms_key, q in (_fresh_line_quotes(game_id) or {}).items():
        if not isinstance(q, dict):
            continue
        try:
            mtype, side = str(ms_key[0]), str(ms_key[1])
        except (TypeError, IndexError):
            continue
        if (mtype, side) in snapshot_ms:
            continue  # snapshot's vetted row wins; never override it
        dedup = (mtype, side, q.get("book"), q.get("line"), q.get("captured_at"))
        if dedup in seen:
            continue
        seen.add(dedup)
        out.append(_quote_view(mtype, side, q))
    return out


def _game_edge(record: Any, env: Any) -> Dict[str, Any]:
    """Assemble the deep edge object for one PredictionRecord (no $ key)."""
    game_id = str(record.game_id)
    markets = _collect_markets(record, env, game_id)
    probs = dict(getattr(record, "pregame_probs", {}) or {})
    edges = _edge_lookup(env, game_id)
    comparison = _comparison(markets, probs, edges)
    captured = [m.get("captured_at") for m in markets if m.get("captured_at")]
    newest = max(captured) if captured else None
    mtype = markets[0].get("market_type") if markets else None

    return {
        "sport": str(record.sport),
        "game_id": game_id,
        "home": record.home,
        "away": record.away,
        "tipoff": record.tipoff,
        "status": "ok",
        "model": {
            "probs": dict(probs),
            "leak_guard": dict(getattr(record, "leak_guard", {}) or {"in_sample": False}),
        },
        "markets": markets,
        "comparison": comparison,
        "freshness": _freshness(newest, mtype),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def _unavailable_view(sport: str, generated_at: str, reason: str) -> Dict[str, Any]:
    """Clean top-level unavailable sentinel for build_edge_view (never faked)."""
    return {
        "sport": sport,
        "generated_at": generated_at,
        "status": "unavailable",
        "reason": reason,
        "count": 0,
        "games": [],
        "honest_note": HONEST_NOTE,
        "edge_note": _EDGE_NOTE,
        "edge_claimed": False,
        "schema_version": SCHEMA_VERSION,
    }


def cache_key(sport: str, *, store_out_dir: Any = None) -> str:
    """The snapshot's generated_at -- a cheap ETag/If-None-Match token. The
    assembler is pure over one O(1) store read, so an unchanged generated_at means
    an unchanged edge view (the caller can serve 304). Returns "" when unavailable."""
    env = read_latest(str(sport), store_out_dir)
    return str(getattr(env, "generated_at", "") or "")


def build_edge_view(sport: str, *, store_out_dir: Any = None) -> Dict[str, Any]:
    """Deep edge view for EVERY game in *sport*. NEVER raises. Reads the canonical
    SnapshotEnvelope via store.read_latest and builds one deep edge object per game
    (model probs + every market quote + per-(market_type, side) model-vs-best-market
    comparison + freshness). Unavailable snapshot -> clean top-level sentinel.
    *store_out_dir* overrides the store base dir (tests pass a temp dir)."""
    sport = str(sport)
    env = read_latest(sport, store_out_dir)
    if getattr(env, "status", "") != "ok":
        return _unavailable_view(
            sport, getattr(env, "generated_at", "") or "",
            "snapshot unavailable (%s)" % (getattr(env, "note", "") or "no snapshot"))

    games: List[Dict[str, Any]] = []
    for record in env.predictions:
        try:
            games.append(_game_edge(record, env))
        except Exception as exc:  # noqa: BLE001 -- one bad game must not sink all
            logger.warning("edge_api: game assembly failed gid=%s: %s",
                           getattr(record, "game_id", "?"), exc)

    return {
        "sport": sport,
        "generated_at": env.generated_at,
        "status": "ok",
        "count": len(games),
        "games": games,
        "honest_note": env.honest_note or HONEST_NOTE,
        "edge_note": _EDGE_NOTE,
        "edge_claimed": False,
        "schema_version": env.schema_version or SCHEMA_VERSION,
    }


def build_game_edge(sport: str, game_id: str, *,
                    store_out_dir: Any = None) -> Dict[str, Any]:
    """The single-game deep edge object for (sport, game_id). NEVER raises. Same
    per-game shape as build_edge_view's games[] entries, with the honest top-level
    note/edge_claimed fields attached. Unavailable snapshot or unknown game_id ->
    clean status='unavailable' object."""
    sport = str(sport)
    game_id = str(game_id)
    env = read_latest(sport, store_out_dir)

    def _miss(generated_at: str, reason: str) -> Dict[str, Any]:
        out = _unavailable_view(sport, generated_at, reason)
        out.pop("games", None)
        out.pop("count", None)
        out["game_id"] = game_id
        return out

    if getattr(env, "status", "") != "ok":
        return _miss(getattr(env, "generated_at", "") or "",
                     "snapshot unavailable (%s)" % (getattr(env, "note", "") or "no snapshot"))

    record = next((p for p in env.predictions if str(p.game_id) == game_id), None)
    if record is None:
        return _miss(env.generated_at, "game_id not in snapshot")

    game = _game_edge(record, env)
    game["generated_at"] = env.generated_at
    game["honest_note"] = env.honest_note or HONEST_NOTE
    game["edge_note"] = _EDGE_NOTE
    game["edge_claimed"] = False
    game["schema_version"] = env.schema_version or SCHEMA_VERSION
    return game


__all__ = ["build_edge_view", "build_game_edge", "cache_key"]
