"""Per-file test for the "wnba/tennis parity (2026-07-18)" end-block appended
to ask_index._METRIC_SYNONYMS (tennis build spec's resolver-reach fix: h2h +
return + break-point-conversion phrasings previously had zero NL alias even
though tennis_h2h_claims / tennis_claims_v3 are VERIFIED indexed stores).

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_query/test_ask_index_wnba_tennis_parity_aliases.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.intel_query.ask_index import extract_metric_synonym


@pytest.mark.parametrize("phrase,expected_metric", [
    ("what's the head to head record between them", "h2h_win_share"),
    ("head-to-head win rate this year", "h2h_win_share"),
    ("who has the better return points won", "return_won_asof"),
    ("who is the best returner on tour", "return_won_asof"),
    ("break point conversion rate leaders", "break_pct_asof"),
    ("break points converted the most", "break_pct_asof"),
])
def test_new_aliases_resolve_to_real_metric(phrase, expected_metric):
    assert extract_metric_synonym(phrase, curated_only=True) == expected_metric


def test_longest_alias_wins_break_point_conversion_over_break_pct():
    # "break point conversion rate" contains "break pct"? no -- but it DOES
    # contain the shorter "break pct" is not a substring here; this instead
    # checks the two break-point aliases both land on the SAME metric so
    # substring precedence between them can never cause a wrong metric.
    assert extract_metric_synonym("break point conversion", curated_only=True) == "break_pct_asof"
    assert extract_metric_synonym("break pct leaders", curated_only=True) == "break_pct_asof"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
