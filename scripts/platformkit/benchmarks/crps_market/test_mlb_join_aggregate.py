"""Aggregate join-rate floor test for benchmarks.crps_market.mlb_join
(gap-ledger seam c). tests/platformkit/test_crps_market_mlb.py already covers
the back-to-back-series and UTC-rollover ambiguity edge cases with hand-built
frames; nothing asserted a rate against the REAL statcast<->line_history
corpora this join runs over in production (the join this module docstring
warns can regress silently -- see mlb_join.py's own module docstring for the
ambiguous-pair-dropped design).

NOTE (premise correction, 2026-07-11): the seam actually missing real-corpus
coverage is THIS module (scripts/platformkit/benchmarks/crps_market/mlb_join.py),
not scripts/platformkit/ingame/ingame_id_resolver_mlb.py -- that one already
has scripts/platformkit/ingame/test_ingame_id_resolver_mlb_aggregate.py (dated
2026-07-11, real Kalshi ticker corpus, 0.90 floor). Re-verified fresh before
writing this file; not duplicated.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/benchmarks/crps_market/test_mlb_join_aggregate.py -q
"""
from __future__ import annotations

import glob
from pathlib import Path

import pytest

from scripts.platformkit.benchmarks.crps_market.mlb_join import (
    build_game_join, load_line_history_totals, load_statcast_games,
)
from scripts.platformkit.join_rate_floor import assert_join_rate_floor

_REPO_ROOT = Path(__file__).resolve().parents[4]
_LINE_HISTORY_DIR = _REPO_ROOT / "data" / "cache" / "line_history" / "mlb"
_STATCAST_2026 = _REPO_ROOT / "data" / "cache" / "statcast" / "savant_full__2026.parquet"

pytestmark = pytest.mark.skipif(
    not (_LINE_HISTORY_DIR.is_dir() and _STATCAST_2026.exists()),
    reason="data/cache/{line_history/mlb,statcast} is local-only (gitignored); "
           "skip the real-corpus join-rate check when absent.",
)

# Measured (2026-07-11) on data/cache/line_history/mlb/*.jsonl (2026-06-18 ..
# 2026-07-10, 502 distinct game_ids) joined against savant_full__2026.parquet:
# 401/502 = 79.9% resolve to a single unambiguous game_pk (the rest are
# honestly EXCLUDED as doubleheader-ambiguous or unmatched, never guessed --
# see build_game_join's docstring). Floor sits a few points below so ordinary
# corpus growth does not flake this test; the historical silent regression
# this floor exists to catch dropped the rate to ~25.7%, far below this band.
_MIN_RESOLVED_FRAC = 0.70


def test_real_corpus_join_rate_meets_floor():
    files = sorted(glob.glob(str(_LINE_HISTORY_DIR / "*.jsonl")))
    assert files, "expected a real captured line_history/mlb corpus"
    start, end = Path(files[0]).stem, Path(files[-1]).stem

    sg = load_statcast_games(2026)
    lt = load_line_history_totals(start, end)
    assert not lt.empty, "expected real MLB total-market rows in the date range"

    join = build_game_join(sg, lt)
    total = lt["game_id"].nunique()

    assert_join_rate_floor(len(join), total, _MIN_RESOLVED_FRAC,
                           label="mlb_join(statcast<->line_history)")


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-q"]))
