"""Aggregate join-rate test for ingame_id_resolver_mlb (gap-ledger rank 7).

test_ingame_id_resolver_mlb.py already covers the PER-SCENARIO rails (unique
match / no-match / doubleheader-ambiguous / unmapped-team never mis-bind), but
nothing asserts the AGGREGATE resolve rate over a realistic multi-game slate --
a silent join drop here corrupts in-game grading/conditioning the same way a
per-scenario green suite would not catch.

This replays the REAL Kalshi MLB ticker corpus captured under
data/venue_history/kalshi/mlb/ (local-only, gitignored -- skipped when absent).
Tickers are grouped by DATE (mirroring live_games(): the resolver only ever
sees ONE day's slate as candidates, never the whole season) and a synthetic
candidate list is reconstructed per date from each ticker's own away+home blob
(via KALSHI_ABBR), so resolve_ticker is exercised end-to-end against its own
matching logic -- no network, no live feed.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/ingame/test_ingame_id_resolver_mlb_aggregate.py -q
"""
from __future__ import annotations

import glob
import os
from collections import defaultdict
from pathlib import Path

import pytest

from scripts.platformkit.ingame import ingame_id_resolver_mlb as R

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VENUE_DIR = _REPO_ROOT / "data" / "venue_history" / "kalshi" / "mlb"

pytestmark = pytest.mark.skipif(
    not _VENUE_DIR.is_dir(),
    reason="data/venue_history/kalshi/mlb is local-only (gitignored); "
           "skip the real-ticker aggregate join-rate check when absent.",
)

# abbrev -> one canonical full team name (reverse of KALSHI_ABBR; a couple of
# abbrevs have 2 aliases -- e.g. ATH -- any one full name round-trips fine).
_ABBR_TO_NAME = {}
for _name, _abbr in R.KALSHI_ABBR.items():
    _ABBR_TO_NAME.setdefault(_abbr, _name)


def _real_base_tickers():
    """Unique base Kalshi tickers from the captured venue-history filenames.

    Each captured file is named <base_ticker>-<side_abbr>.jsonl (one file per
    side of the market); stripping the trailing side gives back the real
    ticker string the live capture observed (matches _TICKER_RE exactly).
    """
    files = glob.glob(str(_VENUE_DIR / "*.jsonl"))
    bases = set()
    for f in files:
        stem = os.path.basename(f)[: -len(".jsonl")]
        base, _, _side = stem.rpartition("-")
        if base:
            bases.add(base)
    return sorted(bases)


def _split_blob(blob: str):
    """Decompose a ticker blob into (away_abbr, home_abbr) iff exactly one
    split point yields two KNOWN abbrevs (ambiguous decompositions are simply
    excluded from the synthetic-candidate corpus, not asserted on)."""
    splits = [(blob[:i], blob[i:]) for i in range(1, len(blob))
              if blob[:i] in _ABBR_TO_NAME and blob[i:] in _ABBR_TO_NAME]
    return splits[0] if len(splits) == 1 else None


def _build_per_date_candidates(tickers):
    """date -> (candidates list, tickers on that date) using each ticker's OWN
    blob -- i.e. the exact per-day slate live_games() would have returned."""
    by_date = defaultdict(list)
    for t in tickers:
        parsed = R.parse_kalshi_mlb_ticker(t)
        if parsed is None:
            continue
        by_date[(parsed["yy"], parsed["mon"], parsed["dd"])].append((t, parsed["blob"]))

    out = {}
    pk = 0
    for date_key, entries in by_date.items():
        cands = []
        for _t, blob in entries:
            split = _split_blob(blob)
            if split is None:
                continue
            away_abbr, home_abbr = split
            pk += 1
            cands.append({"game_pk": str(pk), "away": _ABBR_TO_NAME[away_abbr],
                         "home": _ABBR_TO_NAME[home_abbr]})
        out[date_key] = (cands, [t for t, _b in entries])
    return out


def test_aggregate_resolve_rate_on_real_daily_slates_meets_floor():
    tickers = _real_base_tickers()
    assert len(tickers) > 100, "expected a real captured ticker corpus"

    per_date = _build_per_date_candidates(tickers)
    total = resolved = 0
    for _date_key, (cands, day_tickers) in per_date.items():
        for t in day_tickers:
            total += 1
            if R.resolve_ticker(t, candidates=cands) is not None:
                resolved += 1

    assert total > 0
    rate = resolved / total
    # Measured (2026-07-11) on the captured corpus: 100% (no same-day doubleheader
    # blob collisions in this sample). Floor is set below that so an honest,
    # rare doubleheader ambiguity in future captures does not flake this test --
    # a real join regression (a bad abbrev, a broken split) would crash this
    # rate far below the floor, not shave a percent off it.
    assert rate >= 0.90, "aggregate join rate regressed: %.4f (%d/%d)" % (
        rate, resolved, total)


def test_ambiguous_same_day_duplicate_blob_is_excluded_not_guessed():
    """A synthetic same-day doubleheader (two candidates sharing one blob) must
    drop BOTH tickers from the resolved count -- ambiguity shrinks the
    aggregate rate honestly, it never causes a wrong bind."""
    dup = [{"game_pk": "1", "away": "arizona diamondbacks", "home": "tampa bay rays"},
           {"game_pk": "2", "away": "arizona diamondbacks", "home": "tampa bay rays"}]
    ticker = "KXMLBGAME-26JUN271810AZTB"
    assert R.resolve_ticker(ticker, candidates=dup) is None


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-q"]))
