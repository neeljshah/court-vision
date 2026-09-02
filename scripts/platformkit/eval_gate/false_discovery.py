"""Eval-gate contribution to the nightly false-discovery accounting contract."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

# S40b / RT-5. The rule used to be `len(survivors) <= math.ceil(expected)`, and ceil of any
# expectation in (0,1] is 1 -- so ONE survivor was ALWAYS "within the noise floor", however
# small the expectation (measured: 85 rows, expected_false_survivors=0.050000, observed=1,
# within_noise_floor=True). That allowance is real but it is a POLICY, not arithmetic, so it
# is named here instead of hiding inside a rounding call.
#
# Reasoning for the value: this sweep's screen is a coarse pre-filter feeding the full
# per-candidate ceremony, and a single survivor is the smallest unit it can emit; flagging
# every one-survivor sweep would fire on the expected outcome of a healthy screen and train
# the reader to ignore the field. Two or more survivors against an expectation below one is
# the honest signal, and it now fires -- 2 <= max(1, int(0.05)) is False.
MIN_SURVIVORS_ALLOWED = 1


def accounting_row(rows: Sequence[dict]) -> dict:
    """Build an R1-compatible row for one eval-gate screen sweep.

    Callers append this row to the existing nightly false-discovery ledger; this
    pure helper intentionally owns no data/cache writer.
    """
    measured = [r for r in rows if "n_trials_this_sweep" in r and "n" in r]
    expected = sum(float(r.get("bonferroni_eps", 0.0)) for r in measured)
    survivors = sorted(r["corpus"] for r in measured if r.get("ship_eligible"))
    allowed = max(MIN_SURVIVORS_ALLOWED, int(expected))
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "n_tested": len(measured),
        "families_touched": ["eval_gate"],
        "expected_false_survivors": round(expected, 6),
        "alpha_used": 0.05,
        "observed_survivors": len(survivors),
        "survivor_ids": survivors,
        # Rows missing either key field are dropped from n_tested AND from survivor_ids;
        # counting them keeps the denominator honest instead of silently shrinking it.
        "n_unscorable": len(rows) - len(measured),
        "min_survivors_allowed": allowed,
        "within_noise_floor": len(survivors) <= allowed,
        "screen_source": "eval_gate",
    }


__all__ = ["accounting_row"]
