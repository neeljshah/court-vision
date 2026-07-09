"""Per-file data-quality canary for the Savant leaderboard CSVs backing
domains.mlb.profiles.ingredients_leaderboard (bat_tracking / outs_above_average
/ catch_probability). Reads the REAL on-disk CSVs (no network, no synthetic
frame) -- this is a data-quality assertion, not a builder-logic test (that
coverage already lives in test_ingredients_leaderboard.py).

CONTEXT (fix-wave lane iota, 2026-07-11): premise-checking a leak-free
strictly-prior-season as-of join for bat-tracking found the puller
(scripts/platformkit/data_frontier/savant_bat_tracking.py) returns
BYTE-IDENTICAL bat_tracking_{2024,2025,2026}.csv -- the `year` query param it
sends is silently ignored by Savant's bat-tracking leaderboard endpoint (unlike
outs_above_average's startYear/endYear or catch_probability's own `year` param,
both of which DO differentiate real season data, asserted below). This blocks
any bat-tracking season-over-season as-of join: "2024 conditions 2025" would
actually just replay the current live snapshot under a stale label, not real
prior-season values -- see docs/research/bat_tracking_asof_2026-07-11.md for
the full writeup and the dated forward-capture need (fix the puller's params,
out of this lane's scope: scripts/platformkit/data_frontier/** is not owned
here).

This test is a CANARY, not a blocker: if the puller is ever fixed, the first
assert here starts failing -- that failure is the signal to re-attempt the
mlb_battrack_self_cross gate (already wired, already NOT_TESTABLE today for
an independent reason -- see the same doc).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/profiles/test_leaderboard_dataquality.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

_DIR = Path(__file__).resolve().parents[3] / "data" / "cache" / "statcast" / "leaderboards"
pytestmark = pytest.mark.skipif(not _DIR.exists(), reason="leaderboard CSVs not present on this checkout")


def _read(family: str, year: str) -> pd.DataFrame:
    return pd.read_csv(_DIR / f"{family}_{year}.csv", encoding="utf-8-sig")


def test_bat_tracking_years_are_currently_duplicated():
    """KNOWN BUG canary (see module docstring): bat_tracking's 3 requested
    years are byte-identical today. Asserts the CURRENT bad state so a future
    fix flips this test RED -- a deliberate tripwire, not a silenced xfail."""
    df24, df25, df26 = (_read("bat_tracking", y) for y in ("2024", "2025", "2026"))
    assert df24.equals(df25) and df25.equals(df26), (
        "bat_tracking leaderboard years no longer identical -- the puller's year "
        "param may now work; re-attempt the leak-free prior-season as-of join "
        "(see docs/research/bat_tracking_asof_2026-07-11.md) instead of trusting "
        "this stale canary.")


def test_outs_above_average_years_differ():
    """OAA's startYear/endYear params DO work -- real, distinct season data."""
    df24, df25 = _read("outs_above_average", "2024"), _read("outs_above_average", "2025")
    assert not df24.equals(df25)
    assert len(df24) != len(df25)  # different qualified-fielder populations per season


def test_catch_probability_years_differ():
    """catch_probability's `year` param DOES work -- real, distinct season data."""
    df24, df25 = _read("catch_probability", "2024"), _read("catch_probability", "2025")
    assert not df24.equals(df25)
    assert len(df24) != len(df25)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
