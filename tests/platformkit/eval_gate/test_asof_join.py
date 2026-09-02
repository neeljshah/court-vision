"""S104 per-file test: the shared backward as-of join with a staleness rail.

Run ONLY this file: python -m pytest tests/platformkit/eval_gate/test_asof_join.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.asof_join import asof_join_state

STATES = pd.DataFrame({"ts": [1000, 2000], "cur_h": [0.0, 1.0], "half": ["top", "bottom"]})


def _ticks(stamps):
    return pd.DataFrame({"ts": np.array(stamps, dtype="int64"),
                         "price": np.full(len(stamps), 0.5)})


def test_fresh_state_survives():
    merged, share = asof_join_state(_ticks([1000, 1299, 2000]), STATES, "ts", 300)
    assert merged["cur_h"].tolist() == [0.0, 0.0, 1.0]
    assert merged["half"].tolist() == ["top", "top", "bottom"]
    assert share == 0.0


def test_stale_and_absent_state_are_nulled_not_carried_forward():
    # 5000 is 3000 s past the last state: the exact defect S99 found (a 2-hour-stale score
    # carried forward). 500 precedes every state row and has none at all.
    merged, share = asof_join_state(_ticks([500, 1000, 5000]), STATES, "ts", 300)
    assert merged["cur_h"].isna().tolist() == [True, False, True]
    assert merged["half"].isna().tolist() == [True, False, True]
    assert share == 2.0 / 3.0


def test_boundary_is_inclusive_and_matches_pandas_tolerance():
    stamps = [999, 1000, 1300, 1301, 1999, 2300, 2301, 9999]
    merged, share = asof_join_state(_ticks(stamps), STATES, "ts", 300)
    assert merged.loc[merged["ts"] == 1300, "cur_h"].tolist() == [0.0]   # lag == 300 kept
    assert merged.loc[merged["ts"] == 1301, "cur_h"].isna().all()       # lag == 301 dropped
    want = pd.merge_asof(_ticks(stamps), STATES, on="ts", direction="backward", tolerance=300)
    for column in ("cur_h", "half"):
        assert merged[column].isna().tolist() == want[column].isna().tolist()
        assert (merged[column].dropna().to_numpy() == want[column].dropna().to_numpy()).all()
    assert share == float(want["cur_h"].isna().mean())


def test_empty_ticks_do_not_raise():
    merged, share = asof_join_state(_ticks([]), STATES, "ts", 300)
    assert len(merged) == 0 and share == 0.0


def test_soccer_state_summary_schema_never_bare_when_structured_fields_exist():
    """S104(a): the soccer capture path writes score + minute, not the bare 'live' sentinel.

    Synthetic ESPN scoreboard status -> the two functions that build the captured string.
    'live' survives ONLY as the honest empty-state fallback (no structured field at all)."""
    from scripts.platformkit.ingame.ingame_live_state import _segment_fields
    from scripts.platformkit.ingame.live_grade import _state_summary

    status = {"period": 1, "type": {"shortDetail": "45'+2'", "detail": "45'+2'"}}
    fields = _segment_fields("soccer_intl", {"status": status})
    assert fields["minute"] == 45 and fields["half"] == "1"
    summary = _state_summary({"home_score": 1.0, "away_score": 0.0, **fields})
    for token in ("home_score=1.0", "away_score=0.0", "minute=45"):
        assert token in summary, summary
    assert summary != "live"
    assert _state_summary({}) == "live"          # the honest fallback, unchanged
