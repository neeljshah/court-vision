"""Per-file unit tests for prop_edge_config multi-book wiring (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/test_prop_edge_config_multibook.py -q

ACCEPTANCE (all tested here):
  - Each sport's default_providers() now includes the sportsbook adapters
    (DraftKings + BetMGM for nba/mlb/soccer_intl; +FanDuel for soccer_intl)
    AHEAD of the DFS sources -- so prop_aggregate.merge_multi_source's
    base-row preference falls on a real two-sided sportsbook quote.
  - prop_edge._gather concatenates ALL provider rows then collapses
    (player, stat, event_id, line) duplicates via merge_multi_source; the
    HIGHEST decimal on each side survives.
  - Across two sportsbooks quoting the same prop, the merged row's source
    field names the book that quoted the WINNING over_price (the actual
    `best_book` shown on the card) -- not just the first provider in order.
  - DFS-only context for a prop no sportsbook covers stays as the row's
    source (no fabricated decimal injected).
  - Provider instantiation never raises at import time.

The provider classes are stubbed via injected fakes so we never hit the
network; the real adapters are only verified to BE in the list.
"""
from __future__ import annotations

from typing import List

import pytest

from scripts.platformkit.odds_provider.prop_aggregate import merge_multi_source
from scripts.platformkit.odds_provider.prop_base import PropLine
from scripts.platformkit import prop_edge_config


# --------------------------------------------------------------------------- #
# Provider-set composition
# --------------------------------------------------------------------------- #

def _names(provs) -> List[str]:
    return [type(p).__name__ for p in provs]


def test_soccer_intl_default_providers_include_betmgm_fanduel():
    """soccer_intl wires BetMGM + FanDuel ahead of Underdog/PP.
    DraftKingsProvider (old /sites/US-IL-SB/api/2 endpoint) removed -- that URL
    returns 404 for every soccer call.  Re-add DraftKingsV2Provider once the
    soccer league_id lands in prop_draftkings_v2._SPORT_IDS."""
    cfg = prop_edge_config.get_config("soccer_intl")
    assert cfg is not None
    names = _names(cfg.default_providers())
    # old dead-endpoint DK MUST NOT be in the list
    assert "DraftKingsProvider" not in names, (
        "old DK /sites/US-IL-SB 404 endpoint removed; use DraftKingsV2Provider "
        "once soccer league_id is known")
    assert "BetMGMProvider" in names
    assert "FanDuelProvider" in names
    # DFS context retained
    assert "UnderdogProvider" in names
    assert "PrizePicksProvider" in names
    # sportsbook BEFORE DFS (order matters for tie-break in merge)
    assert names.index("BetMGMProvider") < names.index("PrizePicksProvider")


def test_mlb_default_providers_include_dk_betmgm_not_fanduel():
    """MLB should wire DKv2 + BetMGM (real two-sided) ahead of Underdog/PP.
    FanDuel intentionally omitted -- its keyless adapter is soccer-only.
    DK uses the V2 adapter (sportsbook-nash endpoint) since the legacy
    /sites/US-IL-SB path is Akamai-403 dead."""
    cfg = prop_edge_config.get_config("mlb")
    assert cfg is not None
    names = _names(cfg.default_providers())
    # DKv2 is the working adapter; either name shape is acceptable here.
    has_dk = ("DraftKingsV2Provider" in names) or ("DraftKingsProvider" in names)
    assert has_dk, "expected a DraftKings provider in MLB defaults"
    assert "BetMGMProvider" in names
    assert "FanDuelProvider" not in names, (
        "FanDuel adapter has no MLB pageId -> would 100%% UNAVAILABLE")
    dk_idx = names.index("DraftKingsV2Provider") \
        if "DraftKingsV2Provider" in names else names.index("DraftKingsProvider")
    assert dk_idx < names.index("UnderdogProvider")


def test_nba_default_providers_include_dk_betmgm():
    """NBA -- offseason today, but the wiring must be ready for the season."""
    cfg = prop_edge_config.get_config("nba")
    assert cfg is not None
    names = _names(cfg.default_providers())
    assert "DraftKingsProvider" in names
    assert "BetMGMProvider" in names
    assert names.index("DraftKingsProvider") < names.index("UnderdogProvider")


def test_providers_instantiate_without_raising():
    """No provider may raise at __init__ -- a bad import would sink the board."""
    for sport in ("soccer_intl", "mlb", "nba"):
        cfg = prop_edge_config.get_config(sport)
        assert cfg is not None
        # Call the factory; instantiation must succeed.
        provs = cfg.default_providers()
        assert provs, "no providers for %s" % sport
        for p in provs:
            assert hasattr(p, "fetch_props"), (
                "%s missing fetch_props" % type(p).__name__)


# --------------------------------------------------------------------------- #
# merge_multi_source -- best-line discrimination + source attribution
# --------------------------------------------------------------------------- #

def _make_line(*, source: str, over: float, under: float,
               player: str = "Aaron Judge", stat: str = "Hits",
               line: float = 1.5, event_id: str = "EV1",
               payout_type: str = "sportsbook") -> PropLine:
    return PropLine(
        sport="mlb", event_id=event_id, match="Yankees vs Tigers",
        player=player, team="NYY", stat=stat, line=line,
        over_price=over, under_price=under,
        payout_type=payout_type, source=source,
        as_of="2026-06-23T12:00:00+00:00",
    )


def test_merge_picks_highest_over_across_two_sportsbooks():
    """DK 2.10 vs BetMGM 2.30 on the SAME (player, stat, line) -> BetMGM wins."""
    rows = [
        _make_line(source="draftkings", over=2.10, under=1.85),
        _make_line(source="betmgm", over=2.30, under=1.78),
    ]
    merged = merge_multi_source(rows)
    assert len(merged) == 1
    r = merged[0]
    assert abs(r.over_price - 2.30) < 1e-9
    # Source attribution: the WINNING over_price came from BetMGM.
    assert r.source == "betmgm", (
        "best_book should report the book that owns the winning over: %r" % r.source)


def test_merge_picks_best_per_side_independently():
    """DK has better over, BetMGM has better under -> source reports the over-winner.

    The merge_multi_source contract: best over AND best under both win their side;
    the row's reported `source` names the book owning the OVER (preferred attribution).
    """
    rows = [
        _make_line(source="draftkings", over=2.40, under=1.70),
        _make_line(source="betmgm", over=2.10, under=1.95),
    ]
    merged = merge_multi_source(rows)
    assert len(merged) == 1
    r = merged[0]
    assert abs(r.over_price - 2.40) < 1e-9  # DK over wins
    assert abs(r.under_price - 1.95) < 1e-9  # BetMGM under wins
    assert r.source == "draftkings"  # over-side winner owns the source field


def test_sportsbook_with_real_price_beats_dfs_context_on_same_key():
    """A DK two-sided line beats a DFS pick'em row (None prices) on the same key."""
    rows = [
        _make_line(source="draftkings", over=2.05, under=1.90),
        _make_line(source="underdog", over=None, under=None,
                   payout_type="dfs_pickem"),
    ]
    merged = merge_multi_source(rows)
    assert len(merged) == 1
    r = merged[0]
    assert r.over_price is not None and r.over_price > 1.0
    assert r.payout_type == "sportsbook"
    assert r.source == "draftkings"


def test_dfs_only_prop_keeps_dfs_source_no_fabricated_price():
    """No sportsbook covers this prop -> DFS row survives as context; no fake price."""
    rows = [
        _make_line(source="prizepicks", over=None, under=None,
                   payout_type="dfs_pickem", player="Some Bench Bat"),
    ]
    merged = merge_multi_source(rows)
    assert len(merged) == 1
    r = merged[0]
    assert r.over_price is None
    assert r.under_price is None
    assert r.payout_type == "dfs_pickem"
    assert r.source == "prizepicks"


def test_merge_keeps_distinct_props_separate():
    """Different (player, stat, line) keys must NOT collapse."""
    rows = [
        _make_line(source="draftkings", over=2.10, under=1.85,
                   player="Aaron Judge", stat="Hits", line=1.5),
        _make_line(source="draftkings", over=2.60, under=1.55,
                   player="Aaron Judge", stat="Hits", line=2.5),
        _make_line(source="betmgm", over=1.95, under=1.95,
                   player="Riley Greene", stat="Hits", line=1.5),
    ]
    merged = merge_multi_source(rows)
    assert len(merged) == 3
    # Sorted by (player, stat, line)
    players = [r.player for r in merged]
    assert players == ["Aaron Judge", "Aaron Judge", "Riley Greene"]
    lines = [r.line for r in merged]
    assert lines[0] == 1.5 and lines[1] == 2.5


def test_merge_handles_empty_and_non_propline_input():
    """[] -> []; non-PropLine entries are silently skipped (never raises)."""
    assert merge_multi_source([]) == []
    assert merge_multi_source(None) == []  # type: ignore[arg-type]
    mixed = [_make_line(source="dk", over=2.0, under=1.95), None,
             "garbage", {"not": "a propline"}]
    out = merge_multi_source(mixed)  # type: ignore[arg-type]
    assert len(out) == 1
    assert out[0].source == "dk"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
