"""risk_controls.py — bankroll-protection gate for CourtVision.

Pure logic module: no SQLite imports, no FastAPI, no async.
Importable with fully-mocked state for unit-testing.

Usage (from decision_engine or endpoint)::

    from src.prediction.risk_controls import RiskConfig, RiskState, evaluate_risk, can_place_bet

    cfg   = RiskConfig()
    state = RiskState(bankroll=1000.0, daily_pnl=-30.0, daily_stake=60.0,
                      open_bet_count=4, drawdown_30d_pct=3.1,
                      kill_switch_engaged=False, kill_reason=None)
    result = evaluate_risk(state, cfg)
    # {"ok": True, "blocked_reasons": [], "warnings": [...]}

    allowed, reasons = can_place_bet(
        {"player": "Jokic", "game_id": "0042500315",
         "stake": 25.0, "p_hit": 0.60, "ev_pct": 6.2, "side": "over"},
        state, cfg, existing_open=[]
    )
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
_KILL_SWITCH_PATH = _PROJECT_DIR / "data" / "cache" / "kill_switch.json"

# ── thread lock for kill-switch file writes ──────────────────────────────────
# Using a module-level lock to guard concurrent endpoint calls.
# In multi-process deployments the file is the source of truth (WAL on DB
# already handles persistence; this file is a side-channel flag).
_KS_LOCK = threading.Lock()


# ── config ────────────────────────────────────────────────────────────────────

@dataclass
class RiskConfig:
    """Tunable risk parameters. Override via env or pass explicitly."""
    max_bet_pct: float = 0.04              # max stake = 4% of bankroll per bet
    daily_loss_cap_pct: float = 0.05       # hard stop at -5% in a day
    confidence_floor_p_hit: float = 0.55   # bot won't surface bets below this
    confidence_floor_ev_pct: float = 4.0   # OR EV >= 4%
    max_open_bets_total: int = 20
    max_open_bets_per_game: int = 3
    correlation_cap_same_player: int = 2   # max 2 props on same player

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── state ─────────────────────────────────────────────────────────────────────

@dataclass
class RiskState:
    """Live snapshot of bankroll + position. Computed from BetDB; passed in."""
    bankroll: float
    daily_pnl: float
    daily_stake: float
    open_bet_count: int
    drawdown_30d_pct: float
    kill_switch_engaged: bool
    kill_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── kill-switch persistence ───────────────────────────────────────────────────

def read_kill_switch() -> Tuple[bool, Optional[str]]:
    """Read kill-switch state from data/cache/kill_switch.json.

    Returns (engaged: bool, reason: str|None).
    File absence → (False, None).  Parse errors → (False, None) + log warning.
    """
    path = _KILL_SWITCH_PATH
    if not path.exists():
        return False, None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        engaged = bool(data.get("engaged", False))
        reason  = data.get("reason") or None
        return engaged, reason
    except Exception as exc:
        log.warning("[risk] kill_switch.json read error: %s", exc)
        return False, None


def write_kill_switch(engaged: bool, reason: Optional[str] = None) -> None:
    """Atomically write kill-switch state.

    Uses a temp-file + rename pattern so a crash mid-write never leaves a
    corrupt file. Thread-safe via _KS_LOCK.
    """
    path = _KILL_SWITCH_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"engaged": engaged, "reason": reason or ""}

    with _KS_LOCK:
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(path)  # atomic on POSIX; near-atomic on Windows (NTFS)
        except Exception as exc:
            log.error("[risk] failed to write kill_switch.json: %s", exc)
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            raise


# ── core evaluation ───────────────────────────────────────────────────────────

def evaluate_risk(state: RiskState, cfg: RiskConfig) -> Dict[str, Any]:
    """Return {ok, blocked_reasons[], warnings[]}.

    Hard blocks (sets ok=False; any of these should engage the kill switch):
      - kill_switch_engaged already set
      - daily_pnl < -daily_loss_cap_pct * bankroll  (e.g. < -5%)
      - drawdown_30d_pct > 15%
      - open_bet_count >= max_open_bets_total

    Soft warnings (ok stays True; surfaced to operator):
      - daily_pnl < -3% of bankroll (approaching cap)
      - drawdown_30d_pct > 10%
      - daily_stake > 20% of bankroll

    Threshold semantics (cap boundary):
      The daily-loss cap triggers when daily_pnl is STRICTLY LESS THAN
      -cap_pct * bankroll.  At exactly -5.00% the condition is:
        pnl == -0.05 * bankroll  → NOT strictly less-than → NOT blocked.
      The first cent beyond 5.00% (e.g. -5.01%) triggers the block.
      This matches the "hard stop at -5%" language and avoids blocking
      right on the boundary from floating-point rounding.
    """
    blocked: List[str] = []
    warnings: List[str] = []

    if state.bankroll > 0:
        loss_cap_abs = cfg.daily_loss_cap_pct * state.bankroll
        warn_cap_abs = 0.03 * state.bankroll
        stake_warn   = 0.20 * state.bankroll
    else:
        loss_cap_abs = warn_cap_abs = stake_warn = 0.0

    # ── hard blocks ──────────────────────────────────────────────────────────
    if state.kill_switch_engaged:
        blocked.append(
            f"kill switch engaged"
            + (f": {state.kill_reason}" if state.kill_reason else "")
        )

    if state.bankroll > 0 and state.daily_pnl < -loss_cap_abs:
        pct = abs(state.daily_pnl) / state.bankroll * 100
        blocked.append(
            f"daily loss cap breached: {pct:.1f}% > {cfg.daily_loss_cap_pct*100:.0f}% cap"
        )

    if state.drawdown_30d_pct > 15.0:
        blocked.append(
            f"30d drawdown {state.drawdown_30d_pct:.1f}% > 15% hard limit"
        )

    if state.open_bet_count >= cfg.max_open_bets_total:
        blocked.append(
            f"open bets {state.open_bet_count} >= limit {cfg.max_open_bets_total}"
        )

    # ── soft warnings ─────────────────────────────────────────────────────────
    if not blocked:  # only warn when not already blocked
        if state.bankroll > 0 and state.daily_pnl < -warn_cap_abs:
            pct = abs(state.daily_pnl) / state.bankroll * 100
            warnings.append(
                f"approaching daily cap: -{pct:.1f}% of bankroll "
                f"(cap={cfg.daily_loss_cap_pct*100:.0f}%)"
            )

        if 10.0 < state.drawdown_30d_pct <= 15.0:
            warnings.append(
                f"drawdown {state.drawdown_30d_pct:.1f}% > 10% — monitor closely"
            )

        if state.bankroll > 0 and state.daily_stake > stake_warn:
            pct = state.daily_stake / state.bankroll * 100
            warnings.append(
                f"today_stake is {pct:.0f}% of bankroll — approaching cap"
            )

    return {
        "ok": len(blocked) == 0,
        "blocked_reasons": blocked,
        "warnings": warnings,
    }


# ── per-bet gate ──────────────────────────────────────────────────────────────

def can_place_bet(
    proposed: Dict[str, Any],
    state: RiskState,
    cfg: RiskConfig,
    existing_open: List[Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    """Per-bet chokepoint gate.

    proposed keys: player, game_id, stake, p_hit, ev_pct, side.
    existing_open: list of currently open bet dicts (must have 'player_name'
                   or 'player', 'game_id').

    Returns (allowed: bool, reasons: list[str]).
    """
    reasons: List[str] = []

    # 1. Portfolio-level gate first (fast path).
    portfolio = evaluate_risk(state, cfg)
    if not portfolio["ok"]:
        reasons.extend(portfolio["blocked_reasons"])
        return False, reasons

    player   = str(proposed.get("player") or proposed.get("player_name") or "")
    game_id  = str(proposed.get("game_id") or "")
    stake    = float(proposed.get("stake") or 0.0)
    p_hit    = float(proposed.get("p_hit") or 0.0)
    ev_pct   = float(proposed.get("ev_pct") or 0.0)

    # 2. Stake size cap.
    if state.bankroll > 0:
        max_stake = cfg.max_bet_pct * state.bankroll
        if stake > max_stake:
            reasons.append(
                f"stake ${stake:.2f} > max {cfg.max_bet_pct*100:.0f}% "
                f"of bankroll (${max_stake:.2f})"
            )

    # 3. Confidence floor — BOTH p_hit AND ev_pct must fail to block.
    #    If either passes the floor, the bet is acceptable on confidence grounds.
    confidence_ok = (
        p_hit >= cfg.confidence_floor_p_hit
        or ev_pct >= cfg.confidence_floor_ev_pct
    )
    if not confidence_ok:
        reasons.append(
            f"confidence below floor: p_hit={p_hit:.2f} < {cfg.confidence_floor_p_hit} "
            f"AND ev_pct={ev_pct:.1f}% < {cfg.confidence_floor_ev_pct}%"
        )

    # 4. Per-game open-bet correlation cap.
    if game_id:
        open_same_game = sum(
            1 for b in existing_open
            if str(b.get("game_id") or "") == game_id
        )
        if open_same_game >= cfg.max_open_bets_per_game:
            reasons.append(
                f"already {open_same_game} open bets on game {game_id} "
                f"(cap={cfg.max_open_bets_per_game})"
            )

    # 5. Same-player correlation cap.
    if player:
        open_same_player = sum(
            1 for b in existing_open
            if (b.get("player_name") or b.get("player") or "").lower()
            == player.lower()
        )
        if open_same_player >= cfg.correlation_cap_same_player:
            reasons.append(
                f"already {open_same_player} open props on {player} "
                f"(cap={cfg.correlation_cap_same_player})"
            )

    return len(reasons) == 0, reasons


# ── drawdown alert helper (called from endpoint + decision_engine) ────────────

def check_drawdown_alerts(
    state: RiskState,
    cfg: RiskConfig,
    *,
    auto_engage_threshold: float = 15.0,
    medium_threshold: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """Return alert dict if drawdown crossed a threshold, else None.

    Callers should:
      - POST to Slack webhook if returned dict is not None
      - publish on event bus topic TOPIC_RISK_ALERT
      - call write_kill_switch(True) when severity == 'auto_engage'
    """
    dd = state.drawdown_30d_pct
    if dd > auto_engage_threshold:
        return {
            "severity": "auto_engage",
            "title": "RISK: 30d drawdown auto-engaged kill switch",
            "body": (
                f"Drawdown {dd:.1f}% exceeded hard limit {auto_engage_threshold:.0f}%. "
                f"Kill switch auto-engaged. Manual review required before re-enabling."
            ),
            "tags": {
                "drawdown_30d_pct": f"{dd:.1f}%",
                "threshold": f"{auto_engage_threshold:.0f}%",
                "bankroll": f"${state.bankroll:.2f}",
                "daily_pnl": f"${state.daily_pnl:.2f}",
            },
        }
    if dd > medium_threshold:
        return {
            "severity": "medium",
            "title": "RISK: 30d drawdown approaching hard limit",
            "body": (
                f"Drawdown {dd:.1f}% exceeded medium threshold {medium_threshold:.0f}%. "
                f"Hard limit is {auto_engage_threshold:.0f}%."
            ),
            "tags": {
                "drawdown_30d_pct": f"{dd:.1f}%",
                "threshold": f"{medium_threshold:.0f}%",
                "bankroll": f"${state.bankroll:.2f}",
            },
        }
    return None
