"""Retro report is reproducible and never manufactures survivors."""
from __future__ import annotations

from scripts.platformkit.eval_gate.retro_correction import catalog_signals, render_report


def test_report_names_current_catalog_and_records_zero_survivors():
    pairs = catalog_signals()
    text = render_report(pairs)
    assert len(pairs) == 60
    assert "n_trials_this_sweep=85" in text
    assert "survivors=0" in text
    assert "basketball_nba:EloIdentitySignal" in text
