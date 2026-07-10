"""Aggregate join-rate floor test for domains.soccer.wc_ticker_map (gap-ledger
seam b). test_build_wc_replay_corpus.py already covers match_event_any's
+/-1 day fallback with hand-built tmp_path fixtures; nothing asserted a rate
against the REAL captured WC ticker corpus.

Two real-corpus checks:

1. Round-trip self-consistency on data/venue_history/kalshi/soccer_intl/
   (READ-ONLY, the real captured Kalshi WC ticker files): build_ticker_index
   on the real dir, then for every real event, feed its OWN embedded
   (date, code1, code2) back through match_event_any and confirm it resolves
   to itself. This exercises match_event_any's date-parsing + unordered-pair
   matching against real filenames (not a synthetic fixture).

2. End-to-end coverage: how many of the real captured KXWCGAME events actually
   made it into the built replay corpus (data/cache/inplay_odds/
   soccer_checkpoints_wc2026.parquet), which requires match_event_any to have
   found the ESPN-side match. This is a SUPERSET check -- downstream goal-count
   reconciliation and candle presence also gate a game into the corpus, so a
   drop here is a necessary-but-not-sufficient signal of a ticker-matching
   regression -- floor is set generously below measured for that reason.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    domains/soccer/test_wc_ticker_map_aggregate.py -q
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from domains.soccer.wc_ticker_map import build_ticker_index, match_event_any
from scripts.platformkit.join_rate_floor import assert_join_rate_floor

_REPO_ROOT = Path(__file__).resolve().parents[2]
_KALSHI_DIR = _REPO_ROOT / "data" / "venue_history" / "kalshi" / "soccer_intl"
_CHECKPOINTS = _REPO_ROOT / "data" / "cache" / "inplay_odds" / "soccer_checkpoints_wc2026.parquet"

pytestmark = pytest.mark.skipif(
    not _KALSHI_DIR.is_dir(),
    reason="data/venue_history/kalshi/soccer_intl is local-only (gitignored); "
           "skip the real-ticker aggregate join-rate check when absent.",
)

# Measured (2026-07-11): 96/96 real captured events round-trip through
# match_event_any exactly (self-consistent by construction -- the index and
# the query both come from the same filenames). Floor set below 1.0 anyway:
# a regression in datecode()/match_event's exact-day branch would crash this
# far below the floor, not shave one event off it.
_MIN_ROUNDTRIP_FRAC = 0.95

# Measured (2026-07-11): 83/96 real captured events (86.5%) made it into the
# built checkpoint corpus. This mixes ticker-matching with downstream goal
# reconciliation/candle-presence, so the floor sits well below measured --
# it exists to catch a catastrophic drop (e.g. datecode format change),
# not to police the reconciliation rate.
_MIN_COVERAGE_FRAC = 0.60


def test_real_ticker_roundtrip_meets_floor():
    idx = build_ticker_index(_KALSHI_DIR)
    total = resolved = 0
    for dc, entries in idx.items():
        kickoff_date = datetime.strptime(dc, "%y%b%d").date()
        for ticker, codes in entries:
            total += 1
            c1, c2 = tuple(codes)
            if match_event_any(kickoff_date, c1, c2, idx) == ticker:
                resolved += 1

    assert_join_rate_floor(resolved, total, _MIN_ROUNDTRIP_FRAC,
                           label="wc_ticker_map(real KXWCGAME roundtrip)")


@pytest.mark.skipif(not _CHECKPOINTS.exists(),
                    reason="soccer_checkpoints_wc2026.parquet is local-only "
                           "(gitignored); skip the corpus-coverage check when absent.")
def test_real_corpus_coverage_meets_floor():
    import pandas as pd

    idx = build_ticker_index(_KALSHI_DIR)
    n_real_events = sum(len(v) for v in idx.values())
    df = pd.read_parquet(_CHECKPOINTS, columns=["game_id"])
    n_in_corpus = df["game_id"].nunique()

    assert_join_rate_floor(n_in_corpus, n_real_events, _MIN_COVERAGE_FRAC,
                           label="wc_ticker_map(checkpoint corpus coverage)")


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-q"]))
