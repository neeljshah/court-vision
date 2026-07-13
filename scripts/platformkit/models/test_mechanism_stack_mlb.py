"""Tests for scripts.platformkit.models.mechanism_stack_mlb.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/models/test_mechanism_stack_mlb.py -q
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.platformkit.models import mechanism_stack_mlb as m

_STATCAST_2023 = Path("data/cache/statcast/savant_full__2023.parquet")
_STATCAST_2026 = Path("data/cache/statcast/savant_full__2026.parquet")
_LINE_HISTORY = Path("data/cache/line_history/mlb")
_HAS_REAL_DATA = _STATCAST_2023.exists() and _STATCAST_2026.exists() and _LINE_HISTORY.is_dir()

_KNOWN_TITLE = "Team staff-wide high-pitch-count day precedes next-day run-prevention degradation"


def _row(label, mechanism=_KNOWN_TITLE, effect=0.2, n=100, corpora=None, ci=None):
    return {"label": label, "mechanism": mechanism, "effect": effect, "n": n,
            "corpora": corpora if corpora is not None else ["local"], "ci": ci}


def test_select_mechanisms_excludes_provisional():
    selected, skipped = m.select_mechanisms([_row("SURVIVES_PREREG_PROVISIONAL")])
    assert selected == [] and skipped == []  # never enters the candidate pool


def test_select_mechanisms_includes_replicated_pregame_knowable():
    rows = [_row("CONFIRMED (REPLICATED across 3+ corpora)")]
    selected, skipped = m.select_mechanisms(rows)
    assert len(selected) == 1 and not skipped


def test_select_mechanisms_confirmed_local_needs_two_corpora():
    one_corpus = [_row("CONFIRMED_LOCAL", corpora=["local"])]
    two_corpora = [_row("CONFIRMED_LOCAL", corpora=["local", "2nd"])]
    sel1, _ = m.select_mechanisms(one_corpus)
    sel2, _ = m.select_mechanisms(two_corpora)
    assert sel1 == [] and len(sel2) == 1


def test_select_mechanisms_confirmed_needs_n_1000():
    small_n = [_row("CONFIRMED", n=999)]
    big_n = [_row("CONFIRMED", n=1000)]
    sel_small, _ = m.select_mechanisms(small_n)
    sel_big, _ = m.select_mechanisms(big_n)
    assert sel_small == [] and len(sel_big) == 1


def test_select_mechanisms_skips_non_pregame_knowable_with_reason():
    rows = [_row("CONFIRMED (REPLICATED across 3+ corpora)", mechanism="Platoon x pitch type")]
    selected, skipped = m.select_mechanisms(rows)
    assert selected == []
    assert len(skipped) == 1 and "pregame-knowable" in skipped[0]["reason"]


def test_select_mechanisms_skips_missing_numeric_effect():
    rows = [_row("CONFIRMED (REPLICATED across 3+ corpora)", effect=None)]
    selected, skipped = m.select_mechanisms(rows)
    assert selected == []
    assert len(skipped) == 1 and "numeric" in skipped[0]["reason"]


def test_shift_capping_positive_and_negative():
    high = m.mechanism_shift_runs({"ci": "+10.0, +12.0", "effect": None})
    low = m.mechanism_shift_runs({"ci": "-12.0, -10.0", "effect": None})
    assert high == m._MAX_SHIFT_PER_MECH
    assert low == -m._MAX_SHIFT_PER_MECH


def test_shift_uses_ci_midpoint_when_present():
    shift = m.mechanism_shift_runs({"ci": "+0.1147, +0.4311", "effect": 0.079})
    assert shift == pytest.approx(0.2729, abs=1e-4)


def test_shift_falls_back_to_effect_without_ci():
    shift = m.mechanism_shift_runs({"ci": None, "effect": 0.3})
    assert shift == pytest.approx(0.3)


def test_fatigue_flags_flags_true_only_for_gap_one_heavy_prior_day():
    rows = []
    for i in range(200):
        rows.append({"game_pk": 1, "game_date": "2026-04-02", "inning_topbot": "Top" if i % 2 == 0 else "Bot",
                      "home_team": "HOU", "away_team": "SEA", "post_home_score": 3, "post_away_score": 2})
    eval_pitch = pd.DataFrame(rows)
    statcast_games = pd.DataFrame([
        {"game_pk": 2, "game_date": date(2026, 4, 3), "home_team": "HOU", "away_team": "TEX"},
        {"game_pk": 3, "game_date": date(2026, 4, 6), "home_team": "HOU", "away_team": "TEX"},
    ])
    flags = m.fatigue_flags(eval_pitch, statcast_games, threshold=50)
    assert flags[2] is True   # gap_days==1, HOU threw >=50 the day before
    assert flags[3] is False  # gap of 3 days, not a true back-to-back


@pytest.mark.skipif(not _HAS_REAL_DATA, reason="data/cache/{statcast,line_history} is local-only (gitignored)")
def test_run_produces_valid_schema_and_verdict():
    doc = m.run()
    for key in ("sport", "market", "edge_claimed", "selected_mechanisms", "skipped_mechanisms", "verdict"):
        assert key in doc
    assert doc["edge_claimed"] is False
    assert doc["verdict"] in ("NOT_BUILDABLE", "NOT_TESTABLE", "SHARPER", "WORSE", "UNDERPOWERED")
    if doc["verdict"] not in ("NOT_BUILDABLE", "NOT_TESTABLE"):
        for key in ("n", "crps_stack", "crps_market", "crps_baseline_model", "paired_delta_95ci"):
            assert key in doc


@pytest.mark.skipif(not _HAS_REAL_DATA, reason="data/cache/{statcast,line_history} is local-only (gitignored)")
def test_run_is_deterministic():
    doc1 = m.run()
    doc2 = m.run()
    assert doc1 == doc2


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-q"]))
