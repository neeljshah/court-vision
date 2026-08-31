"""Synthetic OOS lift-history coverage for alpha_decay."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np

from scripts.platformkit.alpha_decay import analyze_signal, append_reports, load_history


def test_decay_half_life_and_statuses(tmp_path) -> None:
    """A planted decaying signal recovers its half-life while a stable one stays active."""
    ledger = tmp_path / "foundry_ledger.jsonl"
    start = datetime(2025, 1, 6, tzinfo=timezone.utc)
    half_life = 3.0
    with ledger.open("w", encoding="utf-8") as handle:
        for week in range(10):
            stamp = start + timedelta(days=7 * week)
            for signal, lift in (("decaying", np.exp(-np.log(2.0) * week / half_life)), ("stable", 0.25)):
                handle.write(json.dumps({"ts": stamp.isoformat(), "signal": signal, "lift": float(lift)}) + "\n")
    history = load_history(ledger)
    decaying = analyze_signal("decaying", history["decaying"])
    stable = analyze_signal("stable", history["stable"])
    assert abs(float(decaying["half_life_weeks"]) - half_life) < 0.15
    assert decaying["status"] == "DECAYING"
    assert stable["status"] == "ACTIVE"
    output = tmp_path / "decay_ledger.jsonl"
    append_reports([decaying, stable], output)
    assert len(output.read_text(encoding="utf-8").splitlines()) == 2
