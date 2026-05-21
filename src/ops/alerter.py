"""
alerter.py — SLO-based ops alerter for CourtVision.

Checks data freshness, model inference latency, and slate completion time
against defined SLOs. Fires to vault/alerts.log + Telegram on breach.

SLOs:
    data_freshness    < 30 min
    model_latency_p95 < 500 ms
    slate_completion  < 10 min

Usage:
    from src.ops.alerter import check_slos, SLOBreach
    breaches = check_slos(data_freshness_min=5.0, model_inference_ms=200.0)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

log = logging.getLogger(__name__)

# ── SLO thresholds ────────────────────────────────────────────────────────────
SLO_DATA_FRESHNESS_MIN:    float = 30.0    # minutes
SLO_MODEL_LATENCY_MS_P95:  float = 500.0   # milliseconds
SLO_SLATE_COMPLETION_MIN:  float = 10.0    # minutes

_VAULT_LOG  = os.path.join(PROJECT_DIR, "vault", "alerts.log")
_ALERTS_DIR = os.path.join(PROJECT_DIR, "data", "output", "alerts")


@dataclass
class SLOBreach:
    slo_name: str
    measured: float
    threshold: float
    unit: str
    message: str


def check_slos(
    data_freshness_min:   Optional[float] = None,
    model_inference_ms:   Optional[float] = None,
    slate_completion_min: Optional[float] = None,
) -> List[SLOBreach]:
    """Check provided metrics against SLO thresholds.

    None values are skipped (not checked). Returns list of SLOBreach for each
    threshold exceeded. Returns empty list when all SLOs are met.
    """
    breaches: List[SLOBreach] = []

    if data_freshness_min is not None and data_freshness_min >= SLO_DATA_FRESHNESS_MIN:
        breaches.append(SLOBreach(
            slo_name="data_freshness",
            measured=data_freshness_min,
            threshold=SLO_DATA_FRESHNESS_MIN,
            unit="min",
            message=f"Data staleness {data_freshness_min:.1f}min >= SLO {SLO_DATA_FRESHNESS_MIN}min",
        ))

    if model_inference_ms is not None and model_inference_ms >= SLO_MODEL_LATENCY_MS_P95:
        breaches.append(SLOBreach(
            slo_name="model_latency_p95",
            measured=model_inference_ms,
            threshold=SLO_MODEL_LATENCY_MS_P95,
            unit="ms",
            message=f"Model p95 {model_inference_ms:.0f}ms >= SLO {SLO_MODEL_LATENCY_MS_P95:.0f}ms",
        ))

    if slate_completion_min is not None and slate_completion_min >= SLO_SLATE_COMPLETION_MIN:
        breaches.append(SLOBreach(
            slo_name="slate_completion",
            measured=slate_completion_min,
            threshold=SLO_SLATE_COMPLETION_MIN,
            unit="min",
            message=f"Slate completion {slate_completion_min:.1f}min >= SLO {SLO_SLATE_COMPLETION_MIN}min",
        ))

    return breaches


def fire_alert(breach: SLOBreach, send_telegram: bool = True) -> None:
    """Log a breach to vault/alerts.log and optionally send Telegram alert."""
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    msg = f"SLO BREACH [{breach.slo_name}]: {breach.message}"

    # Append to vault log
    try:
        os.makedirs(os.path.dirname(_VAULT_LOG), exist_ok=True)
        with open(_VAULT_LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")
    except OSError as e:
        log.warning("Could not write vault/alerts.log: %s", e)

    # Write ALERT file
    try:
        date_str = ts[:10]
        os.makedirs(_ALERTS_DIR, exist_ok=True)
        alert_path = os.path.join(_ALERTS_DIR, f"ALERT_{date_str}.txt")
        with open(alert_path, "a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")
    except OSError as e:
        log.warning("Could not write ALERT file: %s", e)

    # Telegram (non-fatal)
    if send_telegram:
        try:
            from src.monitoring.telegram_alerter import send_alert as _send
            _send(f"⚠️ {msg}")
        except Exception:
            pass

    log.warning(msg)


def check_and_alert(
    data_freshness_min:   Optional[float] = None,
    model_inference_ms:   Optional[float] = None,
    slate_completion_min: Optional[float] = None,
    send_telegram: bool = True,
) -> List[SLOBreach]:
    """Convenience: check SLOs and fire alerts for any breaches."""
    breaches = check_slos(data_freshness_min, model_inference_ms, slate_completion_min)
    for b in breaches:
        fire_alert(b, send_telegram=send_telegram)
    return breaches
