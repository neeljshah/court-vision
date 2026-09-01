"""Eval-gate contribution to the nightly false-discovery accounting contract."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Sequence


def accounting_row(rows: Sequence[dict]) -> dict:
    """Build an R1-compatible row for one eval-gate screen sweep.

    Callers append this row to the existing nightly false-discovery ledger; this
    pure helper intentionally owns no data/cache writer.
    """
    measured = [r for r in rows if "n_trials_this_sweep" in r and "n" in r]
    expected = sum(float(r.get("bonferroni_eps", 0.0)) for r in measured)
    survivors = sorted(r["corpus"] for r in measured if r.get("ship_eligible"))
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "n_tested": len(measured),
        "families_touched": ["eval_gate"],
        "expected_false_survivors": round(expected, 6),
        "alpha_used": 0.05,
        "observed_survivors": len(survivors),
        "survivor_ids": survivors,
        "within_noise_floor": len(survivors) <= math.ceil(expected),
        "screen_source": "eval_gate",
    }


__all__ = ["accounting_row"]
