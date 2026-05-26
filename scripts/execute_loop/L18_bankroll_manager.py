"""
L18 Bankroll Manager — Kelly sizing, correlation-aware staking, kill switches.

Public API:
    kelly_fraction(model_p, american_odds, bankroll) -> float
    kelly_with_correlation(bets, corr_matrix) -> np.ndarray
    get_bankroll_state() -> BankrollState
    update_bankroll(pnl, notes) -> BankrollState
    check_risk_limits(proposed_stake, correlation_key) -> tuple[bool, str]
    reset_daily() -> None
    reset_weekly() -> None
    trip_kill_switch(reason) -> None
    clear_kill_switch(user_token) -> None

Event Publication (via L46 EventBus — optional, non-fatal if unavailable):
    "kelly.sized"
        Published after every call to kelly_fraction() that returns a positive
        fraction.  Payload keys: model_p, american_odds, bankroll,
        kelly_fraction, kelly_cap_applied (bool).

    "risk_limit.breached"
        Published by check_risk_limits() whenever a limit is violated.
        Payload keys: limit_type (str), proposed_stake (float),
        threshold (float), reason (str).

Environment Variables:
    None required by L18 itself.  L44 env-vars govern paper/live mode
    for layers that call L18; L18 does not gate its own behaviour on mode.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import math
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Soft-import L46 EventBus — optional; failure is non-fatal
# ---------------------------------------------------------------------------
try:
    from scripts.execute_loop import L46_event_bus as _L46  # type: ignore[import]
except Exception:  # noqa: BLE001
    _L46 = None

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
CONFIG: dict = {
    "default_bankroll": 100_000.0,
    "kelly_fraction_multiplier": 0.25,
    "max_single_bet_pct": 0.02,
    "max_daily_loss_pct": 0.10,
    "max_weekly_loss_pct": 0.25,
    "max_position_per_game_pct": 0.05,
    "max_open_bets_pct": 0.30,
    "breakeven_margin": 0.005,
    "kill_switch_user_token": "CONFIRM_RESUME",
    "ledger_path": "data/ledger/bankroll_state.json",
    "corr_matrix_path": "data/models/prop_corr_matrix.json",
}

# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class BetCandidate:
    market_id: str
    prob: float
    odds_american: int
    correlation_key: str = ""


@dataclass
class BankrollState:
    current_bankroll: float
    starting_bankroll: float
    test_mode: bool
    daily_pnl: float
    daily_start_iso: str
    weekly_pnl: float
    weekly_start_iso: str
    kill_switch_active: bool
    kill_switch_reason: str
    last_updated: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BankrollState":
        return cls(**d)


# ---------------------------------------------------------------------------
# KELLY MATH
# ---------------------------------------------------------------------------

_BANKROLL_NOT_SET = object()  # sentinel: caller did not pass bankroll


def kelly_fraction(
    model_p: float,
    american_odds: int,
    bankroll: float = _BANKROLL_NOT_SET,  # type: ignore[assignment]
    # Legacy keyword aliases kept for backward compat
    prob: float = None,  # type: ignore[assignment]
    odds_american: int = None,  # type: ignore[assignment]
) -> float:
    """Return fractional Kelly stake as a fraction of bankroll.

    Parameters
    ----------
    model_p:
        Win probability in [0, 1].  Must be finite.
    american_odds:
        American-format odds integer.  0 is not a valid American odds value
        and is treated as no-edge (returns 0.0).
    bankroll:
        Optional current bankroll in dollars.  When supplied and <= 0 the
        Kelly stake is trivially zero (nothing to size against) and 0.0 is
        returned immediately.  When omitted, no bankroll guard is applied
        (preserves backward-compatible behaviour).

    Returns 0.0 when edge is at or below breakeven_margin, when a non-positive
    bankroll is explicitly supplied, or when american_odds is 0.

    Raises
    ------
    ValueError
        When model_p is outside [0, 1] or is non-finite (NaN / Inf).
    """
    # ---- legacy kwarg shims (pre-v2 callers used prob= / odds_american=) ----
    if prob is not None:
        model_p = prob
    if odds_american is not None:
        american_odds = odds_american

    # ---- defensive guards -----------------------------------------------
    if math.isnan(model_p) or math.isinf(model_p):
        raise ValueError(f"model_p must be finite; got {model_p}")
    if not (0.0 <= model_p <= 1.0):
        raise ValueError(f"model_p must be in [0, 1]; got {model_p}")
    if american_odds == 0:
        # 0 is not a legal American odds value
        return 0.0
    # Only apply bankroll guard when caller explicitly passes a bankroll value
    bankroll_provided = bankroll is not _BANKROLL_NOT_SET
    if bankroll_provided and bankroll <= 0:
        # Negative or zero bankroll — nothing to size against
        return 0.0
    # Normalise sentinel to a float for downstream use (event payload etc.)
    _bankroll_val: float = float(bankroll) if bankroll_provided else 0.0

    # ---- Kelly math -------------------------------------------------------
    if american_odds < 0:
        b = 100.0 / abs(american_odds)
    else:
        b = american_odds / 100.0

    implied_prob = 1.0 / (1.0 + b)

    if model_p <= implied_prob + CONFIG["breakeven_margin"]:
        return 0.0

    q = 1.0 - model_p
    f_star = (b * model_p - q) / b

    if f_star <= 0:
        return 0.0

    result = f_star * CONFIG["kelly_fraction_multiplier"]

    # ---- L46 event publication -------------------------------------------
    if _L46 is not None and result > 0.0:
        try:
            _L46.publish(
                "kelly.sized",
                source="L18",
                payload={
                    "model_p": model_p,
                    "american_odds": american_odds,
                    "bankroll": _bankroll_val,
                    "kelly_fraction": result,
                    "kelly_cap_applied": False,
                },
            )
        except Exception:  # noqa: BLE001
            pass

    return result


def kelly_with_correlation(
    bets: list[BetCandidate],
    corr_matrix: np.ndarray,
) -> np.ndarray:
    """Return stake fractions for a portfolio of bets, accounting for correlations.

    Uses Markowitz-style adjustment: f = Cov^-1 @ mu * kelly_mult.
    Falls back to identity (independent Kelly) if corr_matrix is not PSD.
    Final fractions are clipped so that:
      - sum per correlation_key <= max_position_per_game_pct
      - total sum <= max_open_bets_pct
    """
    n = len(bets)
    if n == 0:
        return np.array([])

    kelly_mult = CONFIG["kelly_fraction_multiplier"]
    max_game = CONFIG["max_position_per_game_pct"]
    max_open = CONFIG["max_open_bets_pct"]

    # Build mu (edge per bet) and stdev vector
    mu = np.zeros(n)
    stdev = np.zeros(n)
    for i, bet in enumerate(bets):
        if bet.odds_american < 0:
            b = 100.0 / abs(bet.odds_american)
        else:
            b = bet.odds_american / 100.0
        q = 1.0 - bet.prob
        f_star = (b * bet.prob - q) / b
        mu[i] = max(f_star, 0.0)
        stdev[i] = np.sqrt(bet.prob * q) * b

    # Build covariance matrix: Cov = corr * outer(stdev, stdev)
    use_identity = False
    if corr_matrix.shape != (n, n):
        logger.warning(
            "corr_matrix shape %s does not match n=%d bets; using identity",
            corr_matrix.shape,
            n,
        )
        use_identity = True
    else:
        eigvals = np.linalg.eigvalsh(corr_matrix)
        if np.any(eigvals < -1e-6):
            logger.warning(
                "corr_matrix is not PSD (min eigenvalue=%.6f); falling back to identity",
                float(eigvals.min()),
            )
            use_identity = True

    if use_identity:
        cov = np.diag(stdev ** 2)
    else:
        cov = corr_matrix * np.outer(stdev, stdev)

    # Solve: f = Cov^-1 @ mu * kelly_mult
    try:
        cov_inv = np.linalg.inv(cov + np.eye(n) * 1e-8)
        fracs = cov_inv @ mu * kelly_mult
    except np.linalg.LinAlgError:
        logger.warning("Matrix inversion failed; falling back to independent Kelly")
        fracs = mu * kelly_mult

    fracs = np.clip(fracs, 0.0, None)

    # Clip per correlation_key
    key_groups: dict[str, list[int]] = {}
    for i, bet in enumerate(bets):
        key = bet.correlation_key or f"__solo_{i}"
        key_groups.setdefault(key, []).append(i)

    for indices in key_groups.values():
        group_sum = fracs[indices].sum()
        if group_sum > max_game:
            scale = max_game / group_sum
            fracs[indices] *= scale

    # Clip total open bets
    total = fracs.sum()
    if total > max_open:
        fracs *= max_open / total

    return fracs


# ---------------------------------------------------------------------------
# PERSISTENCE
# ---------------------------------------------------------------------------

def _ledger_path() -> Path:
    return Path(CONFIG["ledger_path"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> BankrollState:
    now = _now_iso()
    br = CONFIG["default_bankroll"]
    return BankrollState(
        current_bankroll=br,
        starting_bankroll=br,
        test_mode=False,
        daily_pnl=0.0,
        daily_start_iso=now,
        weekly_pnl=0.0,
        weekly_start_iso=now,
        kill_switch_active=False,
        kill_switch_reason="",
        last_updated=now,
    )


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_raw() -> Optional[dict]:
    p = _ledger_path()
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def _save_state(state: BankrollState) -> None:
    _atomic_write(_ledger_path(), state.to_dict())


def _auto_reset(state: BankrollState) -> BankrollState:
    """Auto-reset daily/weekly counters if calendar has rolled over."""
    now = datetime.now(timezone.utc)

    daily_start = datetime.fromisoformat(state.daily_start_iso)
    if now.date() > daily_start.date():
        state.daily_pnl = 0.0
        state.daily_start_iso = now.isoformat()

    weekly_start = datetime.fromisoformat(state.weekly_start_iso)
    if (now - weekly_start).days >= 7:
        state.weekly_pnl = 0.0
        state.weekly_start_iso = now.isoformat()

    return state


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def get_bankroll_state() -> BankrollState:
    """Load state from ledger; create defaults if missing."""
    raw = _load_raw()
    if raw is None:
        state = _default_state()
        _save_state(state)
        return state
    state = BankrollState.from_dict(raw)
    state = _auto_reset(state)
    return state


def update_bankroll(pnl: float, notes: str = "") -> BankrollState:
    """Apply a realised PnL delta and persist.

    Writes even when kill_switch_active so recovery is tracked.
    """
    state = get_bankroll_state()
    state.current_bankroll += pnl
    state.daily_pnl += pnl
    state.weekly_pnl += pnl
    state.last_updated = _now_iso()
    if notes:
        logger.info("update_bankroll pnl=%.2f notes=%s", pnl, notes)
    _save_state(state)
    return state


def check_risk_limits(
    proposed_stake: float,
    correlation_key: str = "",
) -> tuple[bool, str]:
    """Validate proposed_stake against all risk limits.

    Returns (True, "ok") or (False, "<reason>").
    On threshold breach that would auto-trip the kill switch, also calls
    trip_kill_switch().  Publishes "risk_limit.breached" via L46 on any
    breach (non-fatal if L46 unavailable).
    """
    state = get_bankroll_state()

    # 1. Kill switch
    if state.kill_switch_active:
        return False, f"kill_switch:{state.kill_switch_reason}"

    br = state.current_bankroll
    sbr = state.starting_bankroll

    # 2. Single-bet size
    if proposed_stake > CONFIG["max_single_bet_pct"] * br:
        reason = (
            f"stake {proposed_stake:.2f} exceeds max_single_bet "
            f"({CONFIG['max_single_bet_pct']*100:.0f}% of {br:.2f})"
        )
        _publish_breach("max_single_bet", proposed_stake, CONFIG["max_single_bet_pct"] * br, reason)
        return False, reason

    # 3. Daily loss limit
    if state.daily_pnl - proposed_stake < -CONFIG["max_daily_loss_pct"] * sbr:
        reason = (
            f"daily_loss_limit: placing {proposed_stake:.2f} would breach "
            f"{CONFIG['max_daily_loss_pct']*100:.0f}% daily limit"
        )
        trip_kill_switch(reason)
        _publish_breach("daily_loss_limit", proposed_stake, CONFIG["max_daily_loss_pct"] * sbr, reason)
        return False, reason

    # 4. Weekly loss limit
    if state.weekly_pnl - proposed_stake < -CONFIG["max_weekly_loss_pct"] * sbr:
        reason = (
            f"weekly_loss_limit: placing {proposed_stake:.2f} would breach "
            f"{CONFIG['max_weekly_loss_pct']*100:.0f}% weekly limit"
        )
        trip_kill_switch(reason)
        _publish_breach("weekly_loss_limit", proposed_stake, CONFIG["max_weekly_loss_pct"] * sbr, reason)
        return False, reason

    # 5. Per-game correlation cap (optional — requires L07 integration)
    if correlation_key:
        open_bets_exposure = _get_open_bets_exposure(correlation_key)
        if open_bets_exposure + proposed_stake > CONFIG["max_position_per_game_pct"] * br:
            reason = (
                f"correlation_key '{correlation_key}': combined exposure "
                f"{open_bets_exposure + proposed_stake:.2f} exceeds "
                f"max_position_per_game ({CONFIG['max_position_per_game_pct']*100:.0f}% of {br:.2f})"
            )
            _publish_breach(
                "max_position_per_game",
                proposed_stake,
                CONFIG["max_position_per_game_pct"] * br,
                reason,
            )
            return False, reason

    return True, "ok"


def _publish_breach(limit_type: str, proposed_stake: float, threshold: float, reason: str) -> None:
    """Publish 'risk_limit.breached' event via L46 (best-effort, non-fatal)."""
    if _L46 is None:
        return
    try:
        _L46.publish(
            "risk_limit.breached",
            source="L18",
            payload={
                "limit_type": limit_type,
                "proposed_stake": proposed_stake,
                "threshold": threshold,
                "reason": reason,
            },
        )
    except Exception:  # noqa: BLE001
        pass


def _get_open_bets_exposure(correlation_key: str) -> float:
    """Return total open stake for a given correlation_key via L07 if available."""
    try:
        from scripts.execute_loop import L07_bet_placer  # type: ignore
        open_bets = L07_bet_placer.get_open_bets()
        return sum(
            b.get("stake", 0.0)
            for b in open_bets
            if b.get("correlation_key") == correlation_key
        )
    except (ImportError, AttributeError):
        return 0.0


def reset_daily() -> None:
    """Zero daily PnL and advance daily_start_iso to now."""
    state = get_bankroll_state()
    state.daily_pnl = 0.0
    state.daily_start_iso = _now_iso()
    state.last_updated = _now_iso()
    _save_state(state)


def reset_weekly() -> None:
    """Zero weekly PnL and advance weekly_start_iso to now."""
    state = get_bankroll_state()
    state.weekly_pnl = 0.0
    state.weekly_start_iso = _now_iso()
    state.last_updated = _now_iso()
    _save_state(state)


def trip_kill_switch(reason: str) -> None:
    """Engage kill switch with the given reason."""
    state = get_bankroll_state()
    state.kill_switch_active = True
    state.kill_switch_reason = reason
    state.last_updated = _now_iso()
    logger.warning("Kill switch TRIPPED: %s", reason)
    _save_state(state)


def clear_kill_switch(user_token: str) -> None:
    """Disengage kill switch; raises ValueError on wrong token."""
    if user_token != CONFIG["kill_switch_user_token"]:
        raise ValueError(
            f"Invalid user_token. Expected '{CONFIG['kill_switch_user_token']}'."
        )
    state = get_bankroll_state()
    state.kill_switch_active = False
    state.kill_switch_reason = ""
    state.last_updated = _now_iso()
    logger.info("Kill switch CLEARED")
    _save_state(state)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _fmt_state(state: BankrollState) -> str:
    lines = [
        f"  Bankroll       : ${state.current_bankroll:,.2f}",
        f"  Starting       : ${state.starting_bankroll:,.2f}",
        f"  Daily PnL      : ${state.daily_pnl:+,.2f}  (since {state.daily_start_iso[:10]})",
        f"  Weekly PnL     : ${state.weekly_pnl:+,.2f}  (since {state.weekly_start_iso[:10]})",
        f"  Kill switch    : {'ON  — ' + state.kill_switch_reason if state.kill_switch_active else 'off'}",
        f"  Test mode      : {state.test_mode}",
        f"  Last updated   : {state.last_updated}",
    ]
    return "\n".join(lines)


def _cmd_status(_args: argparse.Namespace) -> None:
    state = get_bankroll_state()
    print("=== Bankroll Status ===")
    print(_fmt_state(state))


def _cmd_size(args: argparse.Namespace) -> None:
    prob: float = args.prob
    odds: int = args.odds
    if args.kelly_frac is not None:
        original = CONFIG["kelly_fraction_multiplier"]
        CONFIG["kelly_fraction_multiplier"] = args.kelly_frac

    frac = kelly_fraction(prob, odds)

    if args.kelly_frac is not None:
        CONFIG["kelly_fraction_multiplier"] = original

    state = get_bankroll_state()
    stake = frac * state.current_bankroll
    implied = 1.0 / (1.0 + (100.0 / abs(odds) if odds < 0 else odds / 100.0))
    edge = prob - implied

    print(f"  Prob           : {prob:.4f}")
    print(f"  Odds           : {odds:+d}")
    print(f"  Implied prob   : {implied:.4f}")
    print(f"  Edge           : {edge:+.4f}")
    print(f"  Kelly fraction : {frac:.6f}")
    print(f"  Recommended    : ${stake:,.2f}  ({frac*100:.3f}% of bankroll)")

    ok, msg = check_risk_limits(stake)
    if ok:
        print("  Risk check     : PASS")
    else:
        print(f"  Risk check     : FAIL — {msg}")


def _cmd_kill(args: argparse.Namespace) -> None:
    trip_kill_switch(args.reason)
    print(f"Kill switch engaged: {args.reason}")


def _cmd_clear(args: argparse.Namespace) -> None:
    try:
        clear_kill_switch(args.token)
        print("Kill switch cleared.")
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


def _cmd_reset_daily(_args: argparse.Namespace) -> None:
    reset_daily()
    print("Daily PnL reset to 0.")


def _cmd_reset_weekly(_args: argparse.Namespace) -> None:
    reset_weekly()
    print("Weekly PnL reset to 0.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="L18_bankroll_manager.py",
        description="Bankroll Manager — Kelly sizing + risk limits",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Print current bankroll state")

    size_p = sub.add_parser("size", help="Recommend stake for a bet")
    size_p.add_argument("--prob", type=float, required=True, help="Win probability 0-1")
    size_p.add_argument("--odds", type=int, required=True, help="American odds (e.g. -110)")
    size_p.add_argument(
        "--kelly-frac",
        type=float,
        default=None,
        help="Override kelly_fraction_multiplier",
    )

    kill_p = sub.add_parser("kill", help="Trip the kill switch")
    kill_p.add_argument("--reason", type=str, required=True, help="Reason string")

    clear_p = sub.add_parser("clear", help="Clear the kill switch")
    clear_p.add_argument("--token", type=str, required=True, help="Auth token")

    sub.add_parser("reset-daily", help="Reset daily PnL counter")
    sub.add_parser("reset-weekly", help="Reset weekly PnL counter")

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = _build_parser()
    args = parser.parse_args()

    dispatch = {
        "status": _cmd_status,
        "size": _cmd_size,
        "kill": _cmd_kill,
        "clear": _cmd_clear,
        "reset-daily": _cmd_reset_daily,
        "reset-weekly": _cmd_reset_weekly,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
