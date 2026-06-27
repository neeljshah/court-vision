"""frontend.report -- assemble the FULL per-game report from REAL sources.

build_report(sport, game_id, *, store_out_dir=None) -> dict pulls the canonical
PredictionRecord for (sport, game_id) from ``predict_service.store.read_latest``
and assembles one honest, every-field-real-or-null report::

    {
      "status": "ok",
      "sport": "<str>", "game_id": "<str>",
      "pregame": {home, away, tipoff, model_probs, leak_guard, produced_at},
      "markets": [ MarketRow.to_dict(), ... ],
      "edges":   [ {model_prob, market_prob, ev, tier, market_type, side,
                    book, line, clv_is_proxy}, ... ],   # NO $ field
      "live":    {status, ...} | {"status": "unavailable", "reason": "<str>"},
      "intel":   <report_intel.intel_blurbs output>,
      "meta":    {as_of, freshness, clv_is_proxy, honest_note,
                  schema_version, snapshot_generated_at},
    }

An unknown game / sport / unavailable snapshot -> a clean
{"status": "unavailable", "reason": "<str>", ...} -- NEVER fabricated.

HONESTY (binding): edges carry probability/EV/tier ONLY -- there is NO dollar /
$edge / roi / pnl key anywhere by construction. Markets are efficient; this is
calibrated decision-support. CLV (better-number-than-close) is the only honest
yardstick and is flagged clv_is_proxy where the close is a proxy. The live block
is best-effort scaffolding -- the real in-game spine is a later milestone.

Every optional collaborator (live board, intel, freshness) is import- and
call-guarded so one missing piece nulls THAT section only, never the report.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no $ key; no secrets.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from predict_service.contracts import HONEST_NOTE, SCHEMA_VERSION
from predict_service.store import read_latest

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _intel(sport: str, home: str, away: str,
           base: Any = None) -> Dict[str, Any]:
    """Guarded descriptive scouting; a miss nulls the section, never raises."""
    try:
        from frontend.report_intel import intel_blurbs
    except Exception as exc:  # noqa: BLE001 -- intel is optional
        logger.warning("report: intel import failed: %s", exc)
        return {"home": None, "away": None, "matchup": None,
                "status": "unavailable",
                "note": "intel module unavailable (%s)" % type(exc).__name__}
    try:
        return intel_blurbs(sport, home, away, base=base)
    except Exception as exc:  # noqa: BLE001 -- intel must never sink the report
        logger.warning("report: intel_blurbs failed: %s", exc)
        return {"home": None, "away": None, "matchup": None,
                "status": "unavailable",
                "note": "intel error (%s)" % type(exc).__name__}


def _freshness(captured_at: Optional[str],
               market_type: Optional[str]) -> Dict[str, Any]:
    """Guarded freshness of the captured-at timestamp; 'unknown' on any miss."""
    try:
        from scripts.platformkit.odds_provider.freshness import freshness_status
        return freshness_status(captured_at, market_type=market_type)
    except Exception as exc:  # noqa: BLE001 -- freshness is advisory
        logger.warning("report: freshness failed: %s", exc)
        return {"status": "unknown", "age_sec": None}


def _live(sport: str, home: str, away: str,
          game_id: str = "") -> Dict[str, Any]:
    """Best-effort in-game state for THIS game. Default: status='unavailable'.

    Read precedence (additive + fully guarded):
      1. M6 ingame spine snapshot (scripts.platformkit.ingame.snapshot.read_live).
         Prefers the per-game snapshot written by the live_loop daemon for this
         game_id.  An unavailable status in the snapshot -> falls through to 2.
      2. live_board.todays_live_games (keyless ESPN scoreboard).
         Scans today's feed for a home/away name match.
      3. Clean unavailable sentinel on every miss.

    Any module absence, feed error, or sentinel "unavailable" status -> falls
    through to the next level.  Never raises; never fabricates a number.
    """
    # Level 1: M6 ingame spine snapshot for this game_id (guarded, additive).
    if game_id:
        try:
            from scripts.platformkit.ingame import snapshot as igsnap
            envelope = igsnap.read_live(game_id, sport=sport)
            if envelope is not None:
                ms = envelope.get("market_set")
                if isinstance(ms, dict) and ms.get("status") not in (None, "unavailable"):
                    ms.setdefault("status", "ok")
                    ms["served_from"] = "ingame_snapshot"
                    return ms
        except Exception as exc:  # noqa: BLE001 -- spine snapshot is optional
            logger.debug("report._live spine snapshot failed game_id=%s: %s",
                         game_id, exc)

    # Level 2: keyless ESPN live board (match by home/away name).
    try:
        from scripts.platformkit.frontend import live_board
    except Exception as exc:  # noqa: BLE001 -- live board optional
        return {"status": "unavailable",
                "reason": "live board module unavailable (%s)" % type(exc).__name__}
    try:
        board = live_board.todays_live_games(sport)
    except Exception as exc:  # noqa: BLE001 -- a live feed must never 500 us
        return {"status": "unavailable",
                "reason": "live board error (%s)" % type(exc).__name__}
    if not isinstance(board, dict) or board.get("status") not in (None, "ok"):
        reason = (board.get("note") if isinstance(board, dict) else None) \
            or "live feed unavailable"
        return {"status": "unavailable", "reason": str(reason)}
    h, a = str(home).lower(), str(away).lower()
    for g in board.get("games", []) or []:
        if not isinstance(g, dict):
            continue
        gh = str(g.get("home", "")).lower()
        ga = str(g.get("away", "")).lower()
        if (h and (h in gh or gh in h)) and (a and (a in ga or ga in a)):
            g.setdefault("status", "ok")
            return g
    return {"status": "unavailable", "reason": "no live game matched this matchup"}


def _edge_view(edge: Any) -> Dict[str, Any]:
    """Project an EdgeRow to its JSON view -- probability/EV/tier ONLY (no $)."""
    d = edge.to_dict() if hasattr(edge, "to_dict") else dict(edge)
    return {
        "game_id": d.get("game_id"),
        "market_type": d.get("market_type"),
        "side": d.get("side"),
        "model_prob": d.get("model_prob"),
        "market_prob": d.get("market_prob"),
        "ev": d.get("ev"),
        "tier": d.get("tier"),
        "book": d.get("book", ""),
        "line": d.get("line"),
        "clv_is_proxy": bool(d.get("clv_is_proxy", False)),
    }


def _unavailable(sport: str, game_id: str, reason: str) -> Dict[str, Any]:
    """The clean, honest sentinel for an unknown/unavailable game (never faked)."""
    return {
        "status": "unavailable",
        "sport": sport,
        "game_id": game_id,
        "reason": reason,
        "pregame": None,
        "markets": [],
        "edges": [],
        "live": {"status": "unavailable", "reason": reason},
        "intel": None,
        "meta": {"as_of": _now_iso(), "honest_note": HONEST_NOTE,
                 "schema_version": SCHEMA_VERSION},
    }


def build_report(sport: str, game_id: str, *,
                 store_out_dir: Any = None) -> Dict[str, Any]:
    """Assemble the full per-game report for (sport, game_id). NEVER raises.

    Reads the canonical SnapshotEnvelope via predict_service.store.read_latest,
    finds the PredictionRecord for *game_id*, then assembles pregame / markets /
    edges (verbatim, no $), best-effort live, descriptive intel, and meta. An
    unavailable snapshot or unknown game returns the clean unavailable sentinel.

    *store_out_dir* overrides the store base dir (tests pass a temp dir).
    """
    sport = str(sport)
    game_id = str(game_id)
    env = read_latest(sport, store_out_dir)
    if getattr(env, "status", "") != "ok":
        return _unavailable(sport, game_id,
                            "snapshot unavailable (%s)" % (env.note or "no snapshot"))

    record = next((p for p in env.predictions if str(p.game_id) == game_id), None)
    if record is None:
        return _unavailable(sport, game_id, "game_id not in snapshot")

    # Markets for THIS game: the record's own markets, plus any envelope-level
    # market rows that carry the same game_id (deduped by identity tuple).
    seen = set()
    markets: List[Dict[str, Any]] = []
    for m in list(record.markets) + list(env.markets):
        if str(getattr(m, "game_id", "")) != game_id:
            continue
        key = (m.market_type, m.side, m.book, m.line, m.captured_at)
        if key in seen:
            continue
        seen.add(key)
        markets.append(m.to_dict())

    edges = [_edge_view(e) for e in env.edges if str(e.game_id) == game_id]

    # Freshness off the most recent captured_at among this game's markets.
    captured = [m.get("captured_at") for m in markets if m.get("captured_at")]
    newest = max(captured) if captured else None
    mtype = markets[0].get("market_type") if markets else None
    freshness = _freshness(newest, mtype)

    any_proxy = any(m.get("clv_is_proxy") for m in markets) or \
        any(e.get("clv_is_proxy") for e in edges)

    pregame = {
        "home": record.home,
        "away": record.away,
        "tipoff": record.tipoff,
        "model_probs": dict(record.pregame_probs or {}),
        "leak_guard": dict(record.leak_guard or {"in_sample": False}),
        "produced_at": record.produced_at,
        "note": record.note or "",
    }

    return {
        "status": "ok",
        "sport": sport,
        "game_id": game_id,
        "pregame": pregame,
        "markets": markets,
        "edges": edges,
        "live": _live(sport, record.home, record.away, game_id=game_id),
        "intel": _intel(sport, record.home, record.away, base=record),
        "meta": {
            "as_of": _now_iso(),
            "snapshot_generated_at": env.generated_at,
            "freshness": freshness,
            "clv_is_proxy": bool(any_proxy),
            "schema_version": env.schema_version or SCHEMA_VERSION,
            "honest_note": env.honest_note or HONEST_NOTE,
        },
    }


__all__ = ["build_report"]
