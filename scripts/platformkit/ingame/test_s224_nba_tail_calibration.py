"""Focused construct checks for S224's frozen tail reliability bins."""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.ingame.s224_nba_tail_calibration import frozen_bin_labels, summarize


def test_frozen_edges_and_synthetic_rates_are_reproduced() -> None:
    frame = pd.DataFrame({
        "game_id": ["a", "a", "b", "b", "c", "c", "d"],
        "market_prob": [0.0, 0.01, 0.10, 0.90, 0.91, 1.0, 0.50],
        "outcome_home_win": [0, 1, 0, 1, 1, 1, 0],
    })
    rows, summary = summarize(frame)
    by_bin = {row["bin"]: row for row in rows}
    assert frozen_bin_labels() == (
        "00-01", "01-02", "02-03", "03-04", "04-05", "05-06", "06-07", "07-08", "08-09", "09-10",
        "90-91", "91-92", "92-93", "93-94", "94-95", "95-96", "96-97", "97-98", "98-99", "99-100",
    )
    assert summary["denominator"] == {"total": 7, "tail": 6, "middle": 1}
    assert summary["sides"]["low"] == {"ticks": 3, "games": 2, "realized_rate": 1.0 / 3.0}
    assert summary["sides"]["high"] == {"ticks": 3, "games": 2, "realized_rate": 1.0}
    assert by_bin["00-01"]["realized_rate"] == 0.0
    assert by_bin["01-02"]["realized_rate"] == 1.0
    assert by_bin["09-10"]["count"] == 1
    assert by_bin["90-91"]["count"] == 1
    assert by_bin["99-100"]["realized_rate"] == 1.0
    assert sum(row["count"] for row in rows) == 6
