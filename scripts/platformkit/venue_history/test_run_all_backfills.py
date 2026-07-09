"""Tests for scripts.platformkit.venue_history.run_all_backfills. Offline, pure
functions only (no network) -- the network-calling run_*_sport wrappers are
thin pass-throughs onto already-tested run_backfill functions."""
from __future__ import annotations

from scripts.platformkit.venue_history import run_all_backfills as rab


def test_moneyline_game_series_keeps_flat_dir() -> None:
    """The sport's primary GAME series (KXMLBGAME/mlb) must land in the
    pre-existing flat dir so current flat-glob consumers see no change."""
    out = rab.kalshi_out_dir("mlb", "KXMLBGAME")
    assert out == rab.KALSHI_OUT / "mlb"


def test_other_series_gets_series_keyed_subdir() -> None:
    out_total = rab.kalshi_out_dir("mlb", "KXMLBTOTAL")
    out_spread = rab.kalshi_out_dir("mlb", "KXMLBSPREAD")
    assert out_total == rab.KALSHI_OUT / "mlb" / "kxmlbtotal"
    assert out_spread == rab.KALSHI_OUT / "mlb" / "kxmlbspread"
    assert out_total != out_spread


def test_tennis_two_moneyline_series_never_collide() -> None:
    """Tennis has TWO moneyline series (ATP+WTA) and no GAME series at all --
    both must get distinct series-keyed subdirs, never the same flat dir."""
    atp = rab.kalshi_out_dir("tennis", "KXATPMATCH")
    wta = rab.kalshi_out_dir("tennis", "KXWTAMATCH")
    assert atp != wta
    assert atp == rab.KALSHI_OUT / "tennis" / "kxatpmatch"


def test_plan_kalshi_calls_covers_every_series_spec_pair() -> None:
    from scripts.platformkit.odds_provider.kalshi_series_spec import SERIES_SPEC
    for sport, pairs in SERIES_SPEC.items():
        plan = rab.plan_kalshi_calls(sport)
        assert len(plan) == len(pairs)
        assert {p[0] for p in plan} == {series for series, _mt in pairs}


def test_plan_kalshi_calls_unsupported_sport_returns_empty() -> None:
    assert rab.plan_kalshi_calls("curling") == []


def test_polymarket_game_slug_unsupported_sport_skips_honestly() -> None:
    result = rab.run_polymarket_game_slug_sport("tennis")
    assert result["skipped"]
    assert result["venue"] == "polymarket_game_slug"
