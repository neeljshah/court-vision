"""Per-file test: 2026-07-18 "nba player splits" alias additions in
ask_index.py (coverage_stress Family B/C routing). Pins the 2 new home/away
phrasings (-> the existing team-grain home_minus_away_ppg metric) and the 1
new rest phrasing (-> the existing player-grain b2b_pts36_delta metric),
plus a no-regression check that the pre-existing "rest split" -> b2b_ts_drop
alias was NOT overwritten.

Run: python -m pytest scripts/platformkit/intel_query/test_ask_index_player_splits_aliases.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.intel_query import ask_index

_ALIAS_CASES = [
    ("home minus away ppg", "home_minus_away_ppg"),
    ("home away split", "home_minus_away_ppg"),
    ("short minus long rest ppg", "b2b_pts36_delta"),
]


@pytest.mark.parametrize("phrase,expected_metric", _ALIAS_CASES, ids=[c[0] for c in _ALIAS_CASES])
def test_alias_resolves_to_expected_metric(phrase, expected_metric):
    assert ask_index.extract_metric_synonym(phrase) == expected_metric


def test_pre_existing_rest_split_alias_not_overwritten():
    assert ask_index.extract_metric_synonym("rest split") == "b2b_ts_drop"


def test_pre_existing_venue_split_alias_not_overwritten():
    assert ask_index.extract_metric_synonym("venue split") == "home_minus_away_ppg"
    assert ask_index.extract_metric_synonym("home court advantage") == "home_minus_away_ppg"
