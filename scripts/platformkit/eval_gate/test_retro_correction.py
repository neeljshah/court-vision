"""Retro report is reproducible and never manufactures survivors."""
from __future__ import annotations

from scripts.platformkit.eval_gate.retro_correction import (
    RETRO_SWEEP_TRIALS, catalog_signals, render_report,
)


def test_report_names_current_catalog_and_records_zero_survivors():
    """S40b / RT-21(b): `len(pairs) == 60` and the literal "n_trials_this_sweep=85" pinned
    the two sides of the RT-14 mismatch SIDE BY SIDE -- a 61st catalog class broke the
    catalog assertion and never the K. Both are now asserted against RETRO_SWEEP_TRIALS,
    which is the pre-registered sweep width the report is actually corrected for."""
    pairs = catalog_signals()
    text = render_report(pairs)
    assert pairs, "no signal classes found on disk"
    # the pre-registered width must COVER the catalog; a catalog that outgrows it is a
    # real failure, not a number to edit down (RT-14 is the open fix on the module side).
    assert len(pairs) <= RETRO_SWEEP_TRIALS
    assert "catalog_signals_on_disk=%d" % len(pairs) in text
    assert "n_trials_this_sweep=%d" % RETRO_SWEEP_TRIALS in text
    assert "survivors=0" in text
    assert "basketball_nba:EloIdentitySignal" in text
