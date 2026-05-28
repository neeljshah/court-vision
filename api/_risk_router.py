"""_risk_router.py — /api/risk/* endpoints for CourtVision risk control panel.

Endpoints
---------
GET  /api/risk/status       — live risk snapshot (RiskState + evaluate_risk output)
POST /api/risk/kill-switch  — engage / disengage the kill switch
POST /api/bankroll/set      — update the bankroll value (auth-gated)

Auth
----
All endpoints require LIVE_V2_AUTH_TOKEN via ?token=... query param when the env
var is set.  When unset the API is open (local-dev mode), matching live_v2_app.py.

Drawdown alerts
---------------
/api/risk/status fires Slack webhook + event-bus TOPIC_RISK_ALERT when
drawdown crosses 10% (medium) or 15% (auto-engage kill switch).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter()

# ── auth (mirrors live_v2_app.py) ─────────────────────────────────────────────

def _required_token() -> Optional[str]:
    return os.environ.get("LIVE_V2_AUTH_TOKEN") or None


def auth_dep(request: Request, token: Optional[str] = Query(None)) -> None:
    """Cookie-first auth (HttpOnly cv_session) with ?token= fallback for curl."""
    required = _required_token()
    if required is None:
        return
    # Cookie path (browser sends automatically — token never in JS/HTML)
    cookie_val = request.cookies.get("cv_session")
    if cookie_val and cookie_val == required:
        return
    # Fallback: explicit ?token= for curl / server-to-server
    if token and token == required:
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing token",
    )


# ── lazy imports ──────────────────────────────────────────────────────────────

def _get_db():
    from database.bet_db import BetDB  # noqa: PLC0415
    return BetDB()


def _get_cfg():
    from src.prediction.risk_controls import RiskConfig  # noqa: PLC0415
    return RiskConfig()


def _build_state_from_db(db) -> "RiskState":
    from src.prediction.risk_controls import RiskState, read_kill_switch  # noqa: PLC0415
    today       = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_sum   = db.daily_summary(today)
    current     = db.current_bankroll()
    open_count  = _count_open_bets(db)
    drawdown    = db.drawdown_pct(30)
    ks_engaged, ks_reason = read_kill_switch()
    return RiskState(
        bankroll=current,
        daily_pnl=today_sum.get("total_pnl", 0.0),
        daily_stake=today_sum.get("total_stake", 0.0),
        open_bet_count=open_count,
        drawdown_30d_pct=drawdown,
        kill_switch_engaged=ks_engaged,
        kill_reason=ks_reason,
    )


def _count_open_bets(db) -> int:
    try:
        rows = db.list_bets(status="pending", limit=500)
        return len(rows)
    except Exception:
        return 0


# ── drawdown alert side-effect (fire-and-forget) ──────────────────────────────

def _maybe_fire_drawdown_alert(state, cfg) -> None:
    """Check drawdown thresholds; fire Slack + event bus if crossed."""
    try:
        from src.prediction.risk_controls import check_drawdown_alerts, write_kill_switch  # noqa: PLC0415
        alert = check_drawdown_alerts(state, cfg)
        if alert is None:
            return

        # Auto-engage kill switch at 15%
        if alert["severity"] == "auto_engage" and not state.kill_switch_engaged:
            try:
                write_kill_switch(True, "auto-engaged: 30d drawdown > 15%")
                log.warning("[risk] kill switch auto-engaged: drawdown=%.1f%%",
                            state.drawdown_30d_pct)
            except Exception as exc:
                log.error("[risk] failed to auto-engage kill switch: %s", exc)

        # Slack
        try:
            from src.notifications.webhook_alerts import WebhookNotifier  # noqa: PLC0415
            n = WebhookNotifier(min_severity="medium")
            n.send(
                title=alert["title"],
                body=alert["body"],
                severity="high" if alert["severity"] == "auto_engage" else "medium",
                tags=alert.get("tags"),
            )
        except Exception as exc:
            log.debug("[risk] slack notify skipped: %s", exc)

        # Event bus (best-effort — bus may not be running in all deployments)
        try:
            from src.live.event_bus import get_bus  # noqa: PLC0415
            _TOPIC_RISK_ALERT = "risk.alert"
            bus = get_bus()
            loop = None
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                pass
            if loop and loop.is_running():
                loop.create_task(bus.publish(_TOPIC_RISK_ALERT, {
                    "alert": alert,
                    "drawdown_30d_pct": state.drawdown_30d_pct,
                }))
        except Exception as exc:
            log.debug("[risk] event bus publish skipped: %s", exc)

    except Exception as exc:
        log.warning("[risk] drawdown alert check failed: %s", exc)


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/api/risk/status", tags=["risk"])
def api_risk_status(_auth: None = Depends(auth_dep)):
    """Live risk snapshot. Recomputed fresh from SQLite each call.

    Response::

        {
          "kill_switch_engaged": false,
          "config": {...},
          "state": {...},
          "blocked_reasons": [],
          "warnings": ["today_stake is 18% of bankroll — approaching cap"],
          "ok": true
        }
    """
    try:
        from src.prediction.risk_controls import RiskConfig, evaluate_risk  # noqa: PLC0415
        db    = _get_db()
        cfg   = _get_cfg()
        state = _build_state_from_db(db)
        result = evaluate_risk(state, cfg)

        # Side-effect: fire drawdown alerts if thresholds crossed
        _maybe_fire_drawdown_alert(state, cfg)

        return JSONResponse({
            "kill_switch_engaged": state.kill_switch_engaged,
            "kill_reason":         state.kill_reason,
            "config":              cfg.to_dict(),
            "state":               state.to_dict(),
            "blocked_reasons":     result["blocked_reasons"],
            "warnings":            result["warnings"],
            "ok":                  result["ok"],
        })
    except Exception as exc:
        log.error("[risk] status endpoint error: %s", exc)
        return JSONResponse(
            {"error": str(exc), "ok": False, "kill_switch_engaged": False,
             "blocked_reasons": [f"internal error: {exc}"], "warnings": []},
            status_code=500,
        )


class KillSwitchRequest(BaseModel):
    engage: bool
    reason: Optional[str] = None


@router.post("/api/risk/kill-switch", tags=["risk"])
def api_kill_switch(body: KillSwitchRequest, _auth: None = Depends(auth_dep)):
    """Engage or disengage the kill switch.

    Body: ``{"engage": true, "reason": "manual emergency"}``

    When engaged:
    - write_kill_switch() persists to data/cache/kill_switch.json
    - /api/risk/status will reflect the new state
    - decision_engine emits 0 recommendations on next cycle
    - UI shows a full-page banner
    """
    try:
        from src.prediction.risk_controls import write_kill_switch  # noqa: PLC0415
        write_kill_switch(body.engage, body.reason)
        action = "engaged" if body.engage else "disengaged"
        log.info("[risk] kill switch %s — reason: %s", action, body.reason or "(none)")
        return JSONResponse({
            "ok": True,
            "engaged": body.engage,
            "reason": body.reason or "",
            "message": f"Kill switch {action}.",
        })
    except Exception as exc:
        log.error("[risk] kill-switch write error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── bankroll/set ──────────────────────────────────────────────────────────────

class BankrollSetRequest(BaseModel):
    bankroll: Optional[float] = None  # preferred field name
    value: Optional[float] = None     # legacy alias — kept for backwards compat
    notes: Optional[str] = None

    @property
    def resolved_value(self) -> float:
        """Prefer `bankroll`, fall back to `value`."""
        v = self.bankroll if self.bankroll is not None else self.value
        if v is None:
            raise ValueError("must supply 'bankroll' or 'value'")
        return v


@router.post("/api/bankroll/set", tags=["risk"])
def api_bankroll_set(body: BankrollSetRequest, _auth: None = Depends(auth_dep)):
    """Update the bankroll to a new value and record a snapshot.

    Accepts either ``{"bankroll": 1000.0}`` (preferred) or the legacy
    ``{"value": 1000.0}`` — whichever field is present wins (bankroll takes
    priority when both are supplied).

    Auth-gated by LIVE_V2_AUTH_TOKEN.
    """
    try:
        amount = body.resolved_value
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if amount < 0:
        raise HTTPException(status_code=422, detail="bankroll must be >= 0")
    try:
        db = _get_db()
        db.update_bankroll(amount, notes=body.notes or "")
        log.info("[bankroll] set to %.2f (%s)", amount, body.notes or "")
        return JSONResponse({
            "ok": True,
            "new_bankroll": amount,
            "notes": body.notes or "",
        })
    except Exception as exc:
        log.error("[bankroll] set error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
