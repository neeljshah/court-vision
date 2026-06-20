"""tests for cached_board_read.py -- freshness-gated cache reader.

Acceptance criteria:
  A. Fresh envelope: generated_at within SLA -> status='fresh', overall='ok', cards returned.
  B. Stale envelope: generated_at older than SLA -> status='stale', overall!='ok',
     stale_note non-empty (stale-never-green invariant).
  C. Past-tipoff card in fresh cache is filtered out on read (defense-in-depth).
  D. Missing file -> status='unavailable', no raise.
  E. No $ / ROI / PnL field in any output dict.
  F. Generated_at missing -> unavailable (not raise).
  G. Mixed cards: only future-tipoff cards survive in stale+fresh envelopes.

Per-file test only: run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/bestbets/test_cached_board_read.py -q
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from scripts.platformkit.bestbets.cached_board_read import (
    DEFAULT_SLA_SEC,
    read,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW_EPOCH = 1_750_000_000.0  # fixed reference epoch (2025-era Unix timestamp)
_SLA = 300.0  # match DEFAULT_SLA_SEC


def _future_tipoff(offset_sec: float = 7200.0) -> str:
    """ISO-8601 tipoff string that is *offset_sec* seconds in the future."""
    dt = datetime.fromtimestamp(_NOW_EPOCH + offset_sec, tz=timezone.utc)
    return dt.isoformat()


def _past_tipoff(offset_sec: float = 3600.0) -> str:
    """ISO-8601 tipoff string that is *offset_sec* seconds in the past."""
    dt = datetime.fromtimestamp(_NOW_EPOCH - offset_sec, tz=timezone.utc)
    return dt.isoformat()


def _make_card(tipoff: str, market_prob: float = 0.55) -> Dict[str, Any]:
    return {
        "matchup": "TeamA vs TeamB",
        "market": "moneyline",
        "model_prob": 0.60,
        "market_prob": market_prob,
        "edge_vs_market": 0.05,
        "tier": "A",
        "units": 1.0,
        "best_odds": 1.9,
        "tipoff_utc": tipoff,
        "sport": "nba",
    }


def _write_cache(
    tmp_dir: pathlib.Path,
    cards: List[Dict[str, Any]],
    generated_at: float,
    overall: str = "ok",
) -> pathlib.Path:
    doc = {
        "generated_at": generated_at,
        "overall": overall,
        "honest_note": "test envelope",
        "card_count": len(cards),
        "cards": cards,
        "note": "",
    }
    p = tmp_dir / "best_bets.json"
    p.write_text(json.dumps(doc, ensure_ascii=True), encoding="ascii")
    return p


def _check_no_dollar_fields(result: Dict[str, Any]) -> None:
    forbidden = frozenset({"roi", "pnl", "profit", "dollar", "$", "revenue"})
    for key in result:
        assert key.lower() not in forbidden, "Forbidden $ field in output: %r" % key
    for card in result.get("cards", []):
        if isinstance(card, dict):
            for key in card:
                assert key.lower() not in forbidden, (
                    "Forbidden $ field in card: %r" % key
                )


# ---------------------------------------------------------------------------
# A. Fresh envelope (parametrized)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("check,expected", [
    ("status",      "fresh"),
    ("overall",     "ok"),
    ("stale_note",  ""),
])
def test_fresh_envelope_fields(check: str, expected: Any, tmp_path: pathlib.Path) -> None:
    """Fresh cache (60s old): key fields have correct values."""
    cards = [_make_card(_future_tipoff())]
    p = _write_cache(tmp_path, cards, _NOW_EPOCH - 60.0)
    result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
    assert result[check] == expected


def test_fresh_cards_returned(tmp_path: pathlib.Path) -> None:
    """Two future-tipoff cards both survive in a fresh envelope."""
    cards = [_make_card(_future_tipoff()), _make_card(_future_tipoff(3600.0))]
    p = _write_cache(tmp_path, cards, _NOW_EPOCH - 60.0)
    result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
    assert len(result["cards"]) == 2


def test_fresh_generated_at_returned(tmp_path: pathlib.Path) -> None:
    """generated_at round-trips correctly in a fresh envelope."""
    gen_at = _NOW_EPOCH - 60.0
    p = _write_cache(tmp_path, [], gen_at)
    result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
    assert result["generated_at"] == pytest.approx(gen_at)


# ---------------------------------------------------------------------------
# B. Stale envelope (parametrized)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("age_offset,check,negate", [
    (_SLA + 1.0,              "status",      False),  # status == "stale"
    (_SLA + 100.0,            "overall",     True),   # overall != "ok"
    (_SLA + 500.0,            "stale_note",  False),  # stale_note non-empty (checked separately)
    (365 * 24 * 3600.0,       "status",      False),  # year-old is stale
])
def test_stale_envelope_fields(
    age_offset: float, check: str, negate: bool, tmp_path: pathlib.Path
) -> None:
    """Stale cache (past SLA): status/overall/stale_note behave correctly."""
    p = _write_cache(tmp_path, [_make_card(_future_tipoff())], _NOW_EPOCH - age_offset, overall="ok")
    result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
    if check == "stale_note":
        assert len(result["stale_note"]) > 0
    elif negate:
        assert result[check] != "ok"
    else:
        assert result[check] == "stale"


def test_stale_year_old_overall_not_ok(tmp_path: pathlib.Path) -> None:
    """A year-old Polymarket card must never read overall=='ok'."""
    gen_at = _NOW_EPOCH - (365 * 24 * 3600.0)
    p = _write_cache(tmp_path, [], gen_at, overall="ok")
    result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
    assert result["overall"] != "ok"


def test_stale_future_tipoff_cards_survive(tmp_path: pathlib.Path) -> None:
    """Stale envelope: cards with future tipoffs still pass through."""
    cards = [_make_card(_future_tipoff(7200.0))]
    gen_at = _NOW_EPOCH - (_SLA + 1.0)
    p = _write_cache(tmp_path, cards, gen_at)
    result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
    assert result["status"] == "stale"
    assert len(result["cards"]) == 1


# ---------------------------------------------------------------------------
# C. Past-tipoff card filtered on read (defense-in-depth)
# ---------------------------------------------------------------------------

class TestPastTipoffFilter:
    def test_past_tipoff_card_dropped_fresh_cache(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Even in a fresh cache, a card whose game has started is dropped."""
        good = _make_card(_future_tipoff(3600.0))
        stale_card = _make_card(_past_tipoff(600.0))  # game started 10 min ago
        gen_at = _NOW_EPOCH - 60.0
        p = _write_cache(tmp_path, [good, stale_card], gen_at)
        result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
        assert result["status"] == "fresh"
        assert len(result["cards"]) == 1
        assert result["cards"][0]["tipoff_utc"] == good["tipoff_utc"]

    def test_all_past_tipoff_yields_zero_cards(
        self, tmp_path: pathlib.Path
    ) -> None:
        cards = [_make_card(_past_tipoff(100.0)), _make_card(_past_tipoff(200.0))]
        gen_at = _NOW_EPOCH - 60.0
        p = _write_cache(tmp_path, cards, gen_at)
        result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
        assert result["cards"] == []
        assert result["card_count"] == 0

    def test_nba_finals_card_dropped_after_tipoff(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Scenario: NBA Finals card served after tipoff must be filtered."""
        nba_card = _make_card(_past_tipoff(7200.0))  # tipoff 2h ago
        nba_card["matchup"] = "Knicks vs Spurs"
        nba_card["sport"] = "nba"
        gen_at = _NOW_EPOCH - 30.0
        p = _write_cache(tmp_path, [nba_card], gen_at)
        result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
        assert result["status"] == "fresh"
        assert len(result["cards"]) == 0


# ---------------------------------------------------------------------------
# D. Missing file -> UNAVAILABLE, no raise
# ---------------------------------------------------------------------------

class TestMissingFile:
    def test_missing_file_returns_unavailable(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "nonexistent.json"
        result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
        assert result["status"] == "unavailable"

    def test_missing_file_does_not_raise(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "does_not_exist.json"
        try:
            read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
        except Exception as exc:  # noqa: BLE001
            pytest.fail("read() raised unexpectedly: %s" % exc)

    def test_missing_file_cards_empty(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "ghost.json"
        result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
        assert result["cards"] == []
        assert result["card_count"] == 0

    def test_missing_generated_at_is_unavailable(
        self, tmp_path: pathlib.Path
    ) -> None:
        doc = {"overall": "ok", "cards": [], "honest_note": "x"}
        p = tmp_path / "no_gen.json"
        p.write_text(json.dumps(doc), encoding="ascii")
        result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
        assert result["status"] == "unavailable"


# ---------------------------------------------------------------------------
# E. No $ / ROI / PnL field -- parametrized over all three status paths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", ["fresh", "stale", "unavailable"])
def test_no_dollar_fields(scenario: str, tmp_path: pathlib.Path) -> None:
    """No forbidden $ fields in any output path."""
    if scenario == "fresh":
        p = _write_cache(tmp_path, [_make_card(_future_tipoff())], _NOW_EPOCH - 60.0)
    elif scenario == "stale":
        p = _write_cache(tmp_path, [], _NOW_EPOCH - (_SLA + 500.0))
    else:
        p = tmp_path / "missing.json"
    result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
    _check_no_dollar_fields(result)


# ---------------------------------------------------------------------------
# F. Boundary: exactly at SLA edge (parametrized)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("age_offset,expected_status", [
    (_SLA,       "fresh"),   # exactly at SLA -> fresh (impl uses age_sec > sla_sec)
    (_SLA + 1.0, "stale"),   # one second past
    (_SLA - 1.0, "fresh"),   # one second before
])
def test_sla_boundary(
    age_offset: float, expected_status: str, tmp_path: pathlib.Path
) -> None:
    """SLA boundary cases: fresh/stale transition matches implementation semantics."""
    p = _write_cache(tmp_path, [], _NOW_EPOCH - age_offset)
    result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
    assert result["status"] == expected_status


# ---------------------------------------------------------------------------
# G. honest_note always present -- parametrized over all three status paths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", ["fresh", "stale", "unavailable"])
def test_honest_note_always_present(scenario: str, tmp_path: pathlib.Path) -> None:
    """honest_note is non-empty in every output status."""
    if scenario == "fresh":
        p = _write_cache(tmp_path, [], _NOW_EPOCH - 10.0)
    elif scenario == "stale":
        p = _write_cache(tmp_path, [], _NOW_EPOCH - (_SLA + 1000.0))
    else:
        p = tmp_path / "missing.json"
    result = read(path=p, sla_sec=_SLA, now_epoch=_NOW_EPOCH)
    assert "honest_note" in result
    assert len(result["honest_note"]) > 0
