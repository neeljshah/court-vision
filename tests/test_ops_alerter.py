"""Tests for src/ops/alerter.py — SLO checks and alert emission."""
from __future__ import annotations

import os
import tempfile

import pytest

from src.ops.alerter import SLOBreach, check_slos, fire_alert
import src.ops.alerter as alerter_module


def test_no_breach_when_all_good():
    breaches = check_slos(
        data_freshness_min=5.0,
        model_inference_ms=100.0,
        slate_completion_min=5.0,
    )
    assert breaches == []


def test_data_freshness_breach():
    breaches = check_slos(data_freshness_min=35.0)
    assert len(breaches) == 1
    assert breaches[0].slo_name == "data_freshness"
    assert breaches[0].measured == 35.0


def test_model_latency_breach():
    breaches = check_slos(model_inference_ms=600.0)
    assert len(breaches) == 1
    assert breaches[0].slo_name == "model_latency_p95"
    assert breaches[0].measured == 600.0


def test_fire_alert_writes_vault_log(tmp_path, monkeypatch):
    vault_log = str(tmp_path / "vault" / "alerts.log")
    monkeypatch.setattr(alerter_module, "_VAULT_LOG", vault_log)
    monkeypatch.setattr(alerter_module, "_ALERTS_DIR", str(tmp_path / "alerts"))

    breach = SLOBreach(
        slo_name="data_freshness",
        measured=35.0,
        threshold=30.0,
        unit="min",
        message="Data staleness 35.0min >= SLO 30.0min",
    )
    fire_alert(breach, send_telegram=False)

    assert os.path.exists(vault_log)
    content = open(vault_log, encoding="utf-8").read()
    assert "SLO BREACH [data_freshness]" in content
    assert "35.0min" in content
