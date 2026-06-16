"""Per-file test for edge_engine.schedule_fatigue_map. Run ONLY this file (full suite freezes).

  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/edge_engine/test_schedule_fatigue_map.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest  # noqa: E402

from scripts.platformkit.edge_engine.schedule_fatigue_map import (  # noqa: E402
    Candidate, FACT_KINDS, FatigueFact, candidates, stamp_leak_free, validate_fact,
)


def _fact(**kw) -> FatigueFact:
    base = dict(
        fact_kind="travel_disruption", subject_id="1610612743",
        game_date="2026-01-15", value_text="charter delayed; 4am local arrival",
        source="https://x.com/beat/status/1", availability_ts="2026-01-15T11:00:00",
        confidence=0.8,
    )
    base.update(kw)
    return FatigueFact(**base)


def test_candidates_are_well_formed():
    cs = candidates()
    assert len(cs) >= 5
    for c in cs:
        assert isinstance(c, Candidate)
        assert c.fact_kind in FACT_KINDS
        assert c.priority in ("P0", "P1", "P2")
        assert c.proprietary in ("high", "medium", "low")
        # every candidate must name a leak-free capture and a prior-evidence honesty note
        assert "availability_ts" in c.leak_free_capture or "timestamp" in c.leak_free_capture
        assert c.prior_evidence


def test_at_least_one_p0():
    assert any(c.priority == "P0" for c in candidates())


def test_validate_fact_accepts_clean_row():
    validate_fact(_fact().as_dict())  # no raise


def test_validate_fact_rejects_bad_kind():
    with pytest.raises(AssertionError):
        validate_fact(_fact(fact_kind="not_a_kind").as_dict())


def test_validate_fact_rejects_out_of_range_confidence():
    with pytest.raises(AssertionError):
        validate_fact(_fact(confidence=1.5).as_dict())


def test_validate_fact_forbids_outcome_number():
    d = _fact().as_dict()
    d["win_prob"] = 0.61  # an outcome number must never ride on a FACT row
    with pytest.raises(AssertionError):
        validate_fact(d)


def test_stamp_leak_free_passes_when_known_before_move():
    # availability 11:00 < line move 18:00 -> leak-free
    out = stamp_leak_free(_fact(), "2026-01-15T18:00:00")
    assert out["fact_kind"] == "travel_disruption"


def test_stamp_leak_free_trips_on_hindsight():
    # availability 19:00 >= line move 18:00 -> LEAK
    with pytest.raises(AssertionError) as e:
        stamp_leak_free(_fact(availability_ts="2026-01-15T19:00:00"),
                        "2026-01-15T18:00:00")
    assert "LEAK" in str(e.value)
