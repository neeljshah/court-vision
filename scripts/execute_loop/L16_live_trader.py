"""L16_live_trader.py — Live Trader (PAPER MODE STRICT).

Paper-vs-live mode delegated to L44_paper_mode (see L44 for the canonical
env-var list).  L16 uses ``not _L44.is_paper_mode()`` as the live gate, with
LIVE_TRADING_ENABLED env var as the fallback when L44 is absent (soft-import
pattern ensures behavior is identical if L44 is absent).

Polls a live prediction engine, evaluates edge vs market quotes, and manages
paper positions in data/ledger/paper_live_positions.json.  Real order
submission is permanently gated behind the LIVE_TRADING_ENABLED env var
(which should never be set in normal operation).

Paper vs Live Mode (MODE GATING)
---------------------------------
L16 is paper-mode by default.  The module-level ``LIVE_TRADING_ENABLED``
constant (see Config section below) is ``False`` unless the env var is
explicitly set.  When ``LIVE_TRADING_ENABLED`` is ``False``:

* ``run_live_session`` logs a reminder and continues in paper mode.
* All order routing goes through L14 OrderManager → L9-L12 paper clients;
  no real exchange API calls are made at any point in the chain.

To enable live trading (intended only for production deployments):

    export LIVE_TRADING_ENABLED=1   # or "true"

Even with ``LIVE_TRADING_ENABLED=1`` set, L16 itself does not make direct
exchange calls — it delegates to L14, which checks per-exchange flags at the
L9-L12 client layer.  The flag is documented here so L42 audits can confirm
the paper default is explicit at L16's own level.

Environment Variables
---------------------
    LIVE_TRADING_ENABLED   Set to "1" or "true" to enable live order routing
                           (default: "0" → paper mode).  Must be set at the
                           process level; L16 never writes this var.

Public API
----------
    LivePosition            dataclass
    subscribe_live_engine(period) -> Iterator[dict]
    evaluate_position(prediction, current_quote, existing_position) -> LivePosition
    run_live_session(game_id, polling_sec) -> int   # returns positions opened
    exit_all_positions() -> int                     # returns positions closed

CLI
---
    python L16_live_trader.py session --game-id 0042500207 [--polling-sec 30]
    python L16_live_trader.py exit-all
    python L16_live_trader.py status
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Repo root on sys.path
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Soft imports — None on ImportError, checked at call site
# ---------------------------------------------------------------------------
try:
    from src.prediction.live_engine import predict_live as _predict_live  # type: ignore
except ImportError:
    _predict_live = None  # type: ignore

try:
    from scripts.execute_loop.L13_cross_exchange_ev import find_ev_opportunities as _find_ev  # type: ignore
except ImportError:
    _find_ev = None  # type: ignore

try:
    from scripts.execute_loop.L14_order_manager import track_order as _track_order  # type: ignore
except ImportError:
    _track_order = None  # type: ignore

try:
    from scripts.execute_loop.L18_bankroll_manager import (  # type: ignore
        check_risk_limits as _check_risk_limits,
        kelly_fraction as _kelly_fraction,
    )
except ImportError:
    _check_risk_limits = None  # type: ignore
    _kelly_fraction = None  # type: ignore

try:
    from scripts.execute_loop.L22_alerting import send_fill_alert as _send_fill_alert  # type: ignore
except ImportError:
    _send_fill_alert = None  # type: ignore

# ---------------------------------------------------------------------------
# L44 soft-import — paper/live mode delegation
# ---------------------------------------------------------------------------
try:
    from scripts.execute_loop import L44_paper_mode as _L44  # type: ignore
except Exception:
    _L44 = None  # type: ignore


def _is_live_trading() -> bool:
    """Return True if live trading is enabled (via L44 or fallback env var)."""
    if _L44 is not None:
        return not _L44.is_paper_mode()
    return os.environ.get("LIVE_TRADING_ENABLED", "0").lower() in ("1", "true")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_PAPER_LEDGER: Path = _REPO_ROOT / "data" / "ledger" / "paper_live_positions.json"

# Paper-mode gate — False by default (paper mode).  See module docstring.
LIVE_TRADING_ENABLED: bool = os.environ.get("LIVE_TRADING_ENABLED", "0").lower() in ("1", "true")
_LIVE_ENABLED: bool = LIVE_TRADING_ENABLED  # internal alias kept for back-compat

_EDGE_OPEN_PCT: float = 5.0       # min edge to open a new position
_EDGE_ADD_PCT: float = 5.0        # min edge to add to existing position
_EDGE_CLOSE_OPP_PCT: float = 5.0  # edge on opposite side → close
_EDGE_HOLD_MIN_PCT: float = 3.0   # below this + same side → hold, not add
_EDGE_STALE_PCT: float = 2.0      # game final + edge < this → force close
_MAX_ADD_MULTIPLIER: float = 2.0  # max qty multiple vs original
_POSITION_TTL_SECS: int = 1800    # 30 min without movement → close

VALID_PERIODS = ("endQ1", "endQ2", "endQ3")

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class LivePosition:
    position_id: str
    exchange: str
    market_id: str
    player: str
    stat: str
    side: str                  # "YES"|"NO" or "OVER"|"UNDER"
    qty: float
    avg_price: float
    opened_at_period: str      # "endQ1"|"endQ2"|"endQ3"
    current_model_p: float
    current_market_p: float
    action: str                # "OPEN"|"HOLD"|"ADD"|"SELL"|"CLOSE"
    opened_at_ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    game_id: str = ""

# ---------------------------------------------------------------------------
# Ledger helpers (atomic write)
# ---------------------------------------------------------------------------

def _load_ledger() -> list[LivePosition]:
    """Return all positions from the paper ledger (empty list if missing)."""
    if not _PAPER_LEDGER.exists():
        return []
    try:
        raw = json.loads(_PAPER_LEDGER.read_text(encoding="utf-8"))
        return [LivePosition(**p) for p in raw.get("positions", [])]
    except Exception as exc:
        logger.warning("Ledger parse error: %s — starting fresh", exc)
        return []


def _save_ledger(positions: list[LivePosition]) -> None:
    """Atomically persist positions list to paper ledger."""
    _PAPER_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"positions": [asdict(p) for p in positions]}, indent=2)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=_PAPER_LEDGER.parent,
        prefix=".paper_live_positions_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_path, _PAPER_LEDGER)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _upsert_position(pos: LivePosition) -> None:
    """Insert or replace a position in the ledger by position_id."""
    positions = _load_ledger()
    idx = next((i for i, p in enumerate(positions) if p.position_id == pos.position_id), None)
    if idx is None:
        positions.append(pos)
    else:
        positions[idx] = pos
    _save_ledger(positions)

# ---------------------------------------------------------------------------
# Opposite-side helper
# ---------------------------------------------------------------------------

def _opposite_side(side: str) -> str:
    mapping = {"OVER": "UNDER", "UNDER": "OVER", "YES": "NO", "NO": "YES"}
    return mapping.get(side.upper(), side)


def _is_opposite(side_a: str, side_b: str) -> bool:
    return side_a.upper() == _opposite_side(side_b).upper()

# ---------------------------------------------------------------------------
# Core evaluate_position
# ---------------------------------------------------------------------------

def evaluate_position(
    prediction: dict,
    current_quote: dict,
    existing_position: Optional[LivePosition] = None,
) -> LivePosition:
    """Evaluate edge and decide action for a given prediction + market quote.

    Parameters
    ----------
    prediction:
        dict with keys: player, stat, period, q50, p_over, p_under, ts,
        side ("OVER"|"UNDER"|"YES"|"NO"), market_id, exchange.
    current_quote:
        dict with keys: market_p (float 0-1), side, market_id, exchange.
    existing_position:
        Current open LivePosition or None.

    Returns
    -------
    LivePosition with action set to OPEN | HOLD | ADD | SELL | CLOSE.
    """
    player = prediction.get("player", "")
    stat = prediction.get("stat", "")
    period = prediction.get("period", "endQ1")
    side = prediction.get("side", "OVER")
    market_id = prediction.get("market_id", "")
    exchange = prediction.get("exchange", "paper")

    model_p: float = float(prediction.get("p_over", 0.5) if side.upper() in ("OVER", "YES")
                           else prediction.get("p_under", 0.5))
    market_p: float = float(current_quote.get("market_p", 0.5))

    edge_pct: float = abs(model_p - market_p) * 100.0
    model_favors_side = model_p > market_p

    if existing_position is None:
        # No open position
        if edge_pct >= _EDGE_OPEN_PCT and model_favors_side:
            action = "OPEN"
            qty = _default_qty(model_p, market_p)
            pos = LivePosition(
                position_id=str(uuid.uuid4()),
                exchange=exchange,
                market_id=market_id,
                player=player,
                stat=stat,
                side=side,
                qty=qty,
                avg_price=market_p,
                opened_at_period=period,
                current_model_p=model_p,
                current_market_p=market_p,
                action=action,
            )
        else:
            # No position to act on
            pos = LivePosition(
                position_id=str(uuid.uuid4()),
                exchange=exchange,
                market_id=market_id,
                player=player,
                stat=stat,
                side=side,
                qty=0.0,
                avg_price=market_p,
                opened_at_period=period,
                current_model_p=model_p,
                current_market_p=market_p,
                action="HOLD",
            )
    else:
        # Existing position
        same_side = existing_position.side.upper() == side.upper()
        pos = LivePosition(
            position_id=existing_position.position_id,
            exchange=existing_position.exchange,
            market_id=existing_position.market_id,
            player=existing_position.player,
            stat=existing_position.stat,
            side=existing_position.side,
            qty=existing_position.qty,
            avg_price=existing_position.avg_price,
            opened_at_period=existing_position.opened_at_period,
            current_model_p=model_p,
            current_market_p=market_p,
            action="HOLD",
            opened_at_ts=existing_position.opened_at_ts,
            game_id=existing_position.game_id,
        )

        if same_side and edge_pct >= _EDGE_ADD_PCT:
            # Add to position, subject to 2x cap
            max_qty = existing_position.qty * _MAX_ADD_MULTIPLIER
            if pos.qty < max_qty:
                add_qty = _default_qty(model_p, market_p)
                new_qty = min(pos.qty + add_qty, max_qty)
                # Recalc weighted average price
                total_cost = pos.avg_price * pos.qty + market_p * add_qty
                pos.avg_price = total_cost / new_qty
                pos.qty = new_qty
                pos.action = "ADD"
            else:
                pos.action = "HOLD"
        elif _is_opposite(side, existing_position.side) and edge_pct >= _EDGE_CLOSE_OPP_PCT:
            pos.action = "CLOSE"
        elif model_p < market_p:
            # Market has moved past model — edge inverted
            pos.action = "CLOSE"
        else:
            # edge_pct 0..3 or 3..5 same side
            pos.action = "HOLD"

    return pos


def _default_qty(model_p: float, market_p: float) -> float:
    """Simple base stake: $10 per pp of edge, min $10."""
    edge_pp = abs(model_p - market_p) * 100.0
    if _kelly_fraction is not None:
        try:
            # Convert p to rough American odds implied by market_p
            decimal = 1.0 / max(market_p, 0.01)
            american = int((decimal - 1) * 100) if decimal >= 2.0 else int(-100 / (decimal - 1))
            frac = _kelly_fraction(model_p, american)
            return max(round(frac * 1000, 2), 10.0)
        except Exception:
            pass
    return max(round(edge_pp * 10, 2), 10.0)

# ---------------------------------------------------------------------------
# subscribe_live_engine
# ---------------------------------------------------------------------------

def subscribe_live_engine(period: str = "endQ1") -> Iterator[dict]:
    """Yield prediction dicts from the live engine.

    Each dict: {player, stat, period, q50, p_over, p_under, ts}.
    Yields nothing if live_engine is unavailable.
    """
    if _predict_live is None:
        logger.debug("subscribe_live_engine: live_engine unavailable — yielding nothing")
        return

    try:
        results = _predict_live(period=period)
        if not results:
            return
        for row in results:
            row.setdefault("period", period)
            yield row
    except Exception as exc:
        logger.warning("subscribe_live_engine error: %s", exc)

# ---------------------------------------------------------------------------
# exit_all_positions
# ---------------------------------------------------------------------------

def exit_all_positions() -> int:
    """Mark all open positions as CLOSE and persist ledger.

    Returns number of positions closed.
    """
    positions = _load_ledger()
    closed = 0
    for pos in positions:
        if pos.action not in ("CLOSE", "SELL"):
            pos.action = "CLOSE"
            closed += 1
            logger.info("EXIT: %s %s %s @ %.4f", pos.player, pos.stat, pos.side, pos.avg_price)
            if _send_fill_alert is not None:
                try:
                    _send_fill_alert(
                        bet_id=pos.position_id,
                        book=pos.exchange,
                        stake=pos.qty,
                        status="CLOSED",
                    )
                except Exception as exc:
                    logger.debug("send_fill_alert failed: %s", exc)
    _save_ledger(positions)
    logger.info("exit_all_positions: closed %d positions", closed)
    return closed

# ---------------------------------------------------------------------------
# _check_stale
# ---------------------------------------------------------------------------

def _is_stale(pos: LivePosition) -> bool:
    """Return True if position has been open > _POSITION_TTL_SECS without movement."""
    try:
        opened = datetime.fromisoformat(pos.opened_at_ts.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - opened).total_seconds()
        return age > _POSITION_TTL_SECS
    except Exception:
        return False

# ---------------------------------------------------------------------------
# run_live_session
# ---------------------------------------------------------------------------

def run_live_session(game_id: str, polling_sec: int = 30) -> int:
    """Poll live engine, evaluate positions, persist paper ledger.

    Exits when the live engine stops yielding predictions for all periods.

    Parameters
    ----------
    game_id : str
        NBA game ID, e.g. "0042500207".
    polling_sec : int
        Seconds between polling cycles.

    Returns
    -------
    int
        Total number of positions opened during the session.
    """
    if _is_live_trading():
        logger.warning("LIVE_TRADING_ENABLED=true — still operating in paper mode for L16")

    opened_count = 0
    period_idx = 0
    periods_done = 0

    logger.info("run_live_session START game_id=%s polling_sec=%d", game_id, polling_sec)

    while period_idx < len(VALID_PERIODS):
        period = VALID_PERIODS[period_idx]
        predictions_this_cycle: list[dict] = []

        for pred in subscribe_live_engine(period=period):
            pred.setdefault("game_id", game_id)
            predictions_this_cycle.append(pred)

        if not predictions_this_cycle:
            logger.debug("No predictions for period=%s, advancing period", period)
            period_idx += 1
            periods_done += 1
            if periods_done >= len(VALID_PERIODS):
                break
            continue

        for pred in predictions_this_cycle:
            player = pred.get("player", "")
            stat = pred.get("stat", "")
            side = pred.get("side", "OVER")
            market_id = pred.get("market_id", f"{player}_{stat}")
            market_p = float(pred.get("market_p", pred.get("p_under" if side.upper() == "OVER" else "p_over", 0.5)))

            current_quote = {
                "market_p": market_p,
                "side": side,
                "market_id": market_id,
            }

            # Find any existing position for this market
            positions = _load_ledger()
            existing = next(
                (p for p in positions
                 if p.market_id == market_id and p.player == player
                 and p.action not in ("CLOSE", "SELL")),
                None,
            )

            # Check risk limits before opening/adding
            if _check_risk_limits is not None:
                try:
                    allowed, reason = _check_risk_limits(proposed_stake=10.0, correlation_key=stat)
                    if not allowed:
                        logger.warning("Risk limit tripped (%s) — exiting all positions", reason)
                        exit_all_positions()
                        return opened_count
                except Exception as exc:
                    logger.debug("check_risk_limits error: %s", exc)

            # Stale check
            if existing and _is_stale(existing):
                logger.info("Position %s stale — closing", existing.position_id)
                existing.action = "CLOSE"
                _upsert_position(existing)
                continue

            evaluated = evaluate_position(pred, current_quote, existing)
            evaluated.game_id = game_id

            if evaluated.action == "OPEN":
                opened_count += 1
                logger.info("OPEN  %s %s %s qty=%.2f edge=%.1f%%",
                            player, stat, side, evaluated.qty,
                            abs(evaluated.current_model_p - evaluated.current_market_p) * 100)
                if _track_order is not None:
                    try:
                        _track_order(
                            market_id=market_id,
                            side=side,
                            qty=evaluated.qty,
                            price=evaluated.avg_price,
                        )
                    except Exception as exc:
                        logger.debug("track_order error: %s", exc)

            _upsert_position(evaluated)

        # End-of-period: close weak positions
        edge_threshold = _EDGE_STALE_PCT if period_idx == len(VALID_PERIODS) - 1 else 0.0
        if edge_threshold > 0:
            for pos in _load_ledger():
                if pos.action not in ("CLOSE", "SELL"):
                    ep = abs(pos.current_model_p - pos.current_market_p) * 100
                    if ep < edge_threshold:
                        pos.action = "CLOSE"
                        _upsert_position(pos)

        period_idx += 1
        if period_idx < len(VALID_PERIODS):
            logger.info("Sleeping %ds before next poll (period=%s)", polling_sec, period)
            time.sleep(polling_sec)

    logger.info("run_live_session END — opened %d positions", opened_count)
    return opened_count

# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _cmd_session(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    n = run_live_session(game_id=args.game_id, polling_sec=args.polling_sec)
    print(f"Session complete — {n} position(s) opened")


def _cmd_exit_all(args: argparse.Namespace) -> None:  # noqa: ARG001
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    n = exit_all_positions()
    print(f"Closed {n} position(s)")


def _cmd_status(args: argparse.Namespace) -> None:  # noqa: ARG001
    positions = _load_ledger()
    if not positions:
        print("No positions in ledger.")
        return
    print(f"{'ID':36}  {'PLAYER':20}  {'STAT':5}  {'SIDE':6}  {'QTY':8}  {'ACTION':6}  {'EDGE%':6}")
    print("-" * 100)
    for p in positions:
        ep = abs(p.current_model_p - p.current_market_p) * 100
        print(f"{p.position_id:36}  {p.player:20}  {p.stat:5}  {p.side:6}  "
              f"{p.qty:8.2f}  {p.action:6}  {ep:6.1f}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="L16_live_trader",
        description="Live Trader (PAPER MODE STRICT)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # session
    sess = sub.add_parser("session", help="Run a live trading session")
    sess.add_argument("--game-id", required=True, help="NBA game ID e.g. 0042500207")
    sess.add_argument("--polling-sec", type=int, default=30, help="Poll interval in seconds")
    sess.set_defaults(func=_cmd_session)

    # exit-all
    ea = sub.add_parser("exit-all", help="Close all open paper positions")
    ea.set_defaults(func=_cmd_exit_all)

    # status
    st = sub.add_parser("status", help="Print current paper ledger")
    st.set_defaults(func=_cmd_status)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()
    args.func(args)
