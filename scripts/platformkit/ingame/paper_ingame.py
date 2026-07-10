"""scripts.platformkit.ingame.paper_ingame -- paper in-game CLV channel.

Records in-game edges as PAPER bets with channel="paper_ingame" via the
locked clv_ledger_io append path, and settles them through grade_paper.grade_one.

HONESTY CONTRACT (binding):
  * Paper only -- executed is ALWAYS False.  No dollar edge is claimed.
  * One open row per live edge (idempotent by edge_key).  A second call for
    the same key is a no-op; it does NOT add a duplicate open row.
  * Settlement (grade_live) calls grade_paper.grade_one + clv_ledger.append_settlement;
    returns the settled row for the caller to inspect.  Never raises on a corrupt
    or missing ledger -- a clean failure dict is returned instead.
  * CLV = better-number-than-close (documented sign: positive = better). The
    in-game close is a PROXY close by definition (the line seen at the moment
    the edge is signalled), labelled clv_is_proxy=True in the settled row.

CHANNEL: "paper_ingame" -- distinct from the pregame "paper" channel so reports
can separate pre-game from in-game paper track records.

IDEMPOTENCY: keyed on (sport, game_id, market, side, ts_date). A second
record_ingame_bet for the same key within the same calendar day is dropped; the
function returns the EXISTING row with added_new=False. The ledger is only ever
appended (never mutated) so the key check scans the file on each call; for
production call rates (O(10) edges/game) this is fast enough.

WRITE-GUARD: malformed rows are rejected BEFORE append so the leak cannot recur:
  * game_id shorter than _MIN_GAME_ID_LEN chars is silently dropped (no-op, never
    raises to caller -- matches the idempotency-path contract).
  * sport that starts with "test_" is similarly rejected as a synthetic row.
  Both guards mirror the read-time _is_synthetic_row filter in clv_ledger so the
  invariant is enforced at BOTH write and read boundaries.

INVARIANTS: build only under scripts/platformkit/ingame/; <=300 LOC; ASCII-only;
no secrets; no $ edge; never edits src/ or kernel/.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit import clv_ledger as _clv

logger = logging.getLogger(__name__)

# Channel marker -- distinguishes in-game paper bets from pregame channel="paper".
CHANNEL_PAPER_INGAME = "paper_ingame"

# Write-guard threshold: mirrors clv_ledger._MIN_GAME_ID_LEN.
# Real game IDs are e.g. "401859967" (9 chars); "gg" (len=2) is malformed.
_MIN_GAME_ID_LEN: int = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_malformed_input(sport: str, game_id: str) -> bool:
    """Return True when game_id or sport would produce an invalid ledger row.

    Mirrors the read-time clv_ledger._is_synthetic_row check, applied at write
    time so the row is rejected before it ever touches the file.

    Rules:
      * game_id shorter than _MIN_GAME_ID_LEN chars -> malformed.
      * sport starting with "test_" -> synthetic, not a real edge.
    """
    gid = str(game_id)
    if len(gid) < _MIN_GAME_ID_LEN:
        return True
    if str(sport).startswith("test_"):
        return True
    return False


def _edge_key(sport: str, game_id: str, market: str,
               side: str, ts_date: str) -> str:
    """Stable idempotency key for one in-game edge (one per game/market/side/day)."""
    return "|".join([
        str(sport).lower(),
        str(game_id),
        str(market).lower(),
        str(side).lower(),
        str(ts_date)[:10],  # YYYY-MM-DD
    ])


def _scan_existing(path: Path, key: str) -> Optional[Dict[str, Any]]:
    """Return the FIRST existing row (open OR settled) with this edge_key, or
    None. NEVER raises.

    FIX (2026-07-11, B2 sweep): previously only scanned status=="open" rows,
    so a same-day re-trigger of an edge whose FIRST row had ALREADY settled
    found no open twin and appended a brand-new duplicate OPEN row under the
    identical edge_key. That duplicate then sits open FOREVER -- the settle
    daemon's own idempotency guard (_settled_edge_keys) treats any edge_key
    that already has a settled twin as done and never touches it again, so it
    is never settled, never flagged, and never cleaned up. Measured on the
    real ledger: 427 of 440 open paper_ingame rows were exactly this orphaned
    duplicate (see docs/research/paper_correctness_2026-07-11.md). Scanning
    BOTH statuses restores the module's own documented invariant ("one open
    row per live edge... idempotent by edge_key") by treating a same-day
    re-trigger as a no-op regardless of whether the original settled yet.
    """
    if not path.exists():
        return None
    try:
        for row in _clv.load_ledger(path):
            if (row.get("channel") == CHANNEL_PAPER_INGAME
                    and row.get("edge_key") == key
                    and row.get("status") in ("open", "settled")):
                return row
    except Exception:  # noqa: BLE001 - ledger read failure is just a cache miss
        pass
    return None


def record_ingame_bet(
    sport: str,
    game_id: str,
    market: str,
    side: str,
    taken_decimal: float,
    model_prob: Optional[float] = None,
    stake: float = 0.0,
    taken_book: str = "paper_ingame",
    *,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Record one in-game paper edge to the CLV ledger with channel='paper_ingame'.

    Idempotent: if an open row with the same (sport, game_id, market, side, today)
    key already exists, returns the existing row with added_new=False (no duplicate).

    Parameters
    ----------
    sport : str         Normalized sport id (e.g. "nba").
    game_id : str       The in-game game identifier.
    market : str        Market name (e.g. "win_home", "over_224.5").
    side : str          "home" | "away" (moneyline side for CLV settlement).
    taken_decimal : float  Decimal odds you could obtain at this in-game moment.
    model_prob : float, optional  Calibrated P(side) from the repricer [0, 1].
    stake : float       Paper stake (never executed, tracking only). Default 0.0.
    taken_book : str    Label for the notional book. Default "paper_ingame".
    path : Path, optional  Override ledger path (tests pass a tmp file).

    Returns
    -------
    dict  The stored record + 'added_new' flag (True = freshly written).
    Never raises.
    """
    target = Path(path) if path is not None else _clv.DEFAULT_LEDGER
    ts = _now_iso()
    key = _edge_key(sport, game_id, market, side, ts)
    try:
        return _record_inner(sport, game_id, market, side, taken_decimal,
                             model_prob, stake, taken_book, ts, key, target)
    except Exception as exc:  # noqa: BLE001 - must never raise
        logger.warning("record_ingame_bet failed game=%s key=%s: %s",
                       game_id, key, exc)
        return {"status": "error", "reason": str(exc), "edge_key": key,
                "added_new": False, "executed": False,
                "channel": CHANNEL_PAPER_INGAME}


def _record_inner(sport: str, game_id: str, market: str, side: str,
                  taken_decimal: float, model_prob: Optional[float],
                  stake: float, taken_book: str,
                  ts: str, key: str, target: Path) -> Dict[str, Any]:
    # Write-guard: reject malformed / synthetic rows before touching the ledger.
    # Returns a structured no-op identical in shape to the idempotency path so
    # callers need no special handling.  Never raises.
    if _is_malformed_input(sport, game_id):
        return {
            "status": "rejected",
            "reason": (
                "game_id too short (len=%d, min=%d) or synthetic sport %r"
                % (len(str(game_id)), _MIN_GAME_ID_LEN, sport)
            ),
            "edge_key": key,
            "added_new": False,
            "executed": False,
            "channel": CHANNEL_PAPER_INGAME,
        }

    existing = _scan_existing(target, key)
    if existing is not None:
        return {**existing, "added_new": False}

    # Validate side for CLV settlement compat (clv_ledger requires home/away).
    s = str(side).strip().lower()
    if s not in ("home", "away"):
        raise ValueError("side must be 'home' or 'away', got %r" % (side,))
    dec = float(taken_decimal)
    if dec <= 1.0:
        raise ValueError("taken_decimal must be > 1.0, got %r" % (taken_decimal,))

    record: Dict[str, Any] = {
        "ts": ts,
        "sport": str(sport).lower(),
        "game_id": str(game_id),
        "market": str(market),
        "side": s,
        "matchup": str(game_id),   # grade_open_bets uses matchup; game_id is a proxy
        "taken_book": str(taken_book),
        "taken_decimal": dec,
        "model_prob": (float(model_prob) if model_prob is not None else None),
        "stake": float(stake),
        "status": "open",
        "executed": False,         # binding invariant: never a real bet
        "channel": CHANNEL_PAPER_INGAME,
        "edge_key": key,           # idempotency handle
    }
    try:
        from scripts.platformkit.clv_ledger_io import append_row as _io_append
    except Exception:  # noqa: BLE001 - fall back to clv_ledger's own append path
        _io_append = None  # type: ignore[assignment]
    if _io_append is not None:
        _io_append(record, path=target)
    else:
        _clv._append_line(record, target)
    return {**record, "added_new": True}


def grade_live(
    bet: Dict[str, Any],
    home_score: int,
    away_score: int,
    *,
    closing_decimal_home: Optional[float] = None,
    closing_decimal_away: Optional[float] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Settle an open in-game paper bet with the final scores + proxy close.

    Reuses grade_paper.grade_one for CLV + outcome math.  Since the close is
    captured at the moment the edge was signalled (in-game), clv_is_proxy=True
    is forced.  The settled row is appended to the ledger via
    clv_ledger.append_settlement (never mutates the open row).

    Parameters
    ----------
    bet : dict                     The open record returned by record_ingame_bet.
    home_score : int               Final home score.
    away_score : int               Final away score.
    closing_decimal_home : float, optional  Proxy close (home).
    closing_decimal_away : float, optional  Proxy close (away).
    path : Path, optional          Override ledger path.

    Returns
    -------
    dict  The settled row with graded=True, outcome, unit_result, clv_pct
          (UNITS / probability only -- never a dollar pnl).
    Never raises.
    """
    target = Path(path) if path is not None else _clv.DEFAULT_LEDGER
    try:
        return _grade_live_inner(bet, home_score, away_score,
                                 closing_decimal_home, closing_decimal_away,
                                 target)
    except Exception as exc:  # noqa: BLE001 - must never raise
        logger.warning("grade_live failed bet=%s: %s", bet.get("edge_key"), exc)
        return {"status": "error", "reason": str(exc), "executed": False,
                "channel": CHANNEL_PAPER_INGAME}


def _grade_live_inner(bet: Dict[str, Any], home_score: int, away_score: int,
                      ch: Optional[float], ca: Optional[float],
                      path: Path) -> Dict[str, Any]:
    from scripts.platformkit import grade_paper as _gp
    # Build a minimal 'game' dict that grade_one expects.
    game: Dict[str, Any] = {
        "state": "final",
        "home_score": int(home_score),
        "away_score": int(away_score),
        "home": "",
        "home_abbr": "",
        "away": "",
        "away_abbr": "",
    }
    # Inject proxy closing decimals onto the bet copy so grade_one resolves at Level 4.
    bet_copy = dict(bet)
    if ch is not None:
        bet_copy["closing_decimal_home"] = float(ch)
    if ca is not None:
        bet_copy["closing_decimal_away"] = float(ca)
    settled = _gp.grade_one(bet_copy, game)
    # Force clv_is_proxy because in-game closes are always proxies.
    settled["clv_is_proxy"] = True
    settled["channel"] = CHANNEL_PAPER_INGAME
    _clv.append_settlement(settled, path=path)
    return settled


def load_ingame_bets(
    *,
    path: Optional[Path] = None,
    channel: str = CHANNEL_PAPER_INGAME,
) -> List[Dict[str, Any]]:
    """Read only paper_ingame rows from the ledger (open + settled). Never raises."""
    target = Path(path) if path is not None else _clv.DEFAULT_LEDGER
    try:
        return [r for r in _clv.load_ledger(target)
                if r.get("channel") == channel]
    except Exception:  # noqa: BLE001
        return []


__all__ = [
    "CHANNEL_PAPER_INGAME",
    "record_ingame_bet",
    "grade_live",
    "load_ingame_bets",
]
