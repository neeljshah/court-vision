"""Aggregate join-rate floor test for odds_provider.market_join (gap-ledger
seam a). test_market_join.py (both copies) already covers per-scenario
matching/omission behavior with hand-built quotes; nothing asserted the join
against a REAL captured quote corpus.

join_quotes_to_edges has no natural "denominator" of its own (it is a pure
function with no IO -- there is no captured (edge, quote) pair corpus on disk,
data/edges/ is empty). So this measures the join engine itself against real
captured quotes: for every distinct (game_id, market_type, side) key actually
observed in data/cache/line_history/nba/*.jsonl (real MarketQuote rows written
by write_quotes), a synthetic edge sharing that exact key is joined against
the FULL real quote list. This isolates join_quotes_to_edges' key-matching and
its odds>1.0 usability filter (the two things that could silently regress)
from any question of upstream data quality -- the edge side is synthesized
on-key, so a key can only fail to resolve if the join logic itself drops it.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/odds_provider/test_market_join_aggregate.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.join_rate_floor import assert_join_rate_floor
from scripts.platformkit.odds_provider.market_join import join_quotes_to_edges
from scripts.platformkit.odds_provider.markets import MarketQuote

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LINE_HISTORY_DIR = _REPO_ROOT / "data" / "cache" / "line_history" / "nba"

pytestmark = pytest.mark.skipif(
    not _LINE_HISTORY_DIR.is_dir(),
    reason="data/cache/line_history/nba is local-only (gitignored); "
           "skip the real-quote aggregate join-rate check when absent.",
)

_QUOTE_FIELDS = {"sport", "game_id", "home", "away", "market_type", "side",
                  "line", "odds", "book", "captured_at", "devigged_prob"}

# Measured (2026-07-11) on data/cache/line_history/nba/*.jsonl: 100% (68/68
# distinct real keys). Floor set a few points below 1.0 given the small key
# count (~68) -- a real regression (key normalization, the odds<=1.0 filter)
# would crash this far below the floor, not shave one key off it.
_MIN_RESOLVED_FRAC = 0.95


def _real_quotes() -> list:
    quotes = []
    for fp in sorted(_LINE_HISTORY_DIR.glob("*.jsonl")):
        with open(fp, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    quotes.append(MarketQuote(**{k: row.get(k) for k in _QUOTE_FIELDS}))
                except TypeError:
                    continue  # malformed row -- skipped, never fabricated
    return quotes


def test_real_quote_keys_join_when_paired_with_a_matching_edge():
    quotes = _real_quotes()
    assert len(quotes) > 100, "expected a real captured quote corpus"

    keys = sorted({(q.game_id, q.market_type, q.side) for q in quotes})
    edges = [{"game_id": gid, "market_type": mt, "side": side,
              "model_prob": 0.5, "market_prob": 0.5, "ev": 0.0}
             for gid, mt, side in keys]

    rows = join_quotes_to_edges(edges, quotes)
    resolved_keys = {(r.game_id, r.market_type, r.side) for r in rows}

    assert_join_rate_floor(len(resolved_keys), len(keys), _MIN_RESOLVED_FRAC,
                           label="market_join(real nba line_history keys)")


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-q"]))
