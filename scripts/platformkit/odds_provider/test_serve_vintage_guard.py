"""Per-file tests for serve_vintage_guard.py.

Acceptance criteria (from workstream BE8-3):
  A) Same prices as prior -> captured_at preserved (not now).
  B) Changed price        -> captured_at advances to incoming's value.
  C) Post/Final game      -> is_close=True on returned row.
  D) Missing prior        -> passthrough captured_at unchanged; no fabrication.
  E) No fabricated timestamp (never replace with now() when not needed).

Per-file test command:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/odds_provider/test_serve_vintage_guard.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.odds_provider.serve_vintage_guard import apply, apply_batch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _row(odds=1.91, line=-3.5, captured_at="2026-06-19T10:00:00Z",
         game_id="g1", market_type="spread", book="espn:DraftKings",
         side="home", **kwargs):
    r = {
        "game_id": game_id,
        "market_type": market_type,
        "side": side,
        "book": book,
        "line": line,
        "odds": odds,
        "captured_at": captured_at,
    }
    r.update(kwargs)
    return r


# ---------------------------------------------------------------------------
# A) Same price -> preserved captured_at
# ---------------------------------------------------------------------------

def test_same_price_preserves_prior_captured_at():
    """Unchanged odds/line -> prior captured_at is returned, not incoming's."""
    prior = _row(odds=1.91, line=-3.5, captured_at="2026-06-19T08:00:00Z")
    incoming = _row(odds=1.91, line=-3.5, captured_at="2026-06-19T10:00:00Z")
    result = apply(incoming, prior)
    assert result["captured_at"] == "2026-06-19T08:00:00Z", (
        "unchanged price must keep original (prior) captured_at"
    )
    assert result["price_changed"] is False
    assert result["captured_at_preserved"] is True


def test_same_price_same_timestamp_noop():
    """When prior and incoming have the same timestamp, prior is returned."""
    ts = "2026-06-19T10:00:00Z"
    prior = _row(odds=1.85, captured_at=ts)
    incoming = _row(odds=1.85, captured_at=ts)
    result = apply(incoming, prior)
    assert result["captured_at"] == ts
    assert result["price_changed"] is False
    assert result["captured_at_preserved"] is True


def test_same_price_moneyline():
    """Preserved for moneyline (no line field)."""
    prior = _row(odds=2.10, line=None, market_type="moneyline",
                 captured_at="2026-06-19T07:00:00Z")
    incoming = _row(odds=2.10, line=None, market_type="moneyline",
                    captured_at="2026-06-19T10:30:00Z")
    result = apply(incoming, prior)
    assert result["captured_at"] == "2026-06-19T07:00:00Z"
    assert result["price_changed"] is False


# ---------------------------------------------------------------------------
# B) Changed price -> advance captured_at
# ---------------------------------------------------------------------------

def test_changed_odds_advances_captured_at():
    """When odds change, the incoming captured_at is used."""
    prior = _row(odds=1.91, captured_at="2026-06-19T08:00:00Z")
    incoming = _row(odds=1.95, captured_at="2026-06-19T10:00:00Z")
    result = apply(incoming, prior)
    assert result["captured_at"] == "2026-06-19T10:00:00Z"
    assert result["price_changed"] is True
    assert result["captured_at_preserved"] is False


def test_changed_line_advances_captured_at():
    """A line shift (spread moves) counts as a price change."""
    prior = _row(odds=1.91, line=-3.5, captured_at="2026-06-19T08:00:00Z")
    incoming = _row(odds=1.91, line=-4.0, captured_at="2026-06-19T10:00:00Z")
    result = apply(incoming, prior)
    assert result["captured_at"] == "2026-06-19T10:00:00Z"
    assert result["price_changed"] is True


def test_changed_both_odds_and_line():
    prior = _row(odds=1.91, line=-3.5, captured_at="2026-06-19T06:00:00Z")
    incoming = _row(odds=1.87, line=-4.5, captured_at="2026-06-19T10:00:00Z")
    result = apply(incoming, prior)
    assert result["captured_at"] == "2026-06-19T10:00:00Z"
    assert result["price_changed"] is True


# ---------------------------------------------------------------------------
# C) Post/Final game -> is_close=True
# ---------------------------------------------------------------------------

def test_postgame_string_sets_is_close():
    """game_state='post' -> is_close=True."""
    row = _row()
    result = apply(row, None, game_state="post")
    assert result["is_close"] is True


def test_final_string_sets_is_close():
    result = apply(_row(), None, game_state="final")
    assert result["is_close"] is True


def test_Final_mixed_case_sets_is_close():
    """Case variants: 'Final' should set is_close."""
    result = apply(_row(), None, game_state="Final")
    assert result["is_close"] is True


def test_STATUS_FINAL_sets_is_close():
    result = apply(_row(), None, game_state="STATUS_FINAL")
    assert result["is_close"] is True


def test_dict_game_state_post():
    result = apply(_row(), None, game_state={"state": "post"})
    assert result["is_close"] is True


def test_dict_game_state_final():
    result = apply(_row(), None, game_state={"state": "Final"})
    assert result["is_close"] is True


def test_ingame_state_not_close():
    """An in-progress game must not be marked is_close."""
    result = apply(_row(), None, game_state="in")
    assert result["is_close"] is False


def test_pregame_state_not_close():
    result = apply(_row(), None, game_state="pre")
    assert result["is_close"] is False


def test_none_game_state_not_close():
    result = apply(_row(), None, game_state=None)
    assert result["is_close"] is False


def test_is_close_preserved_on_same_price():
    """is_close combines with captured_at preservation."""
    prior = _row(odds=1.91, captured_at="2026-06-19T08:00:00Z")
    incoming = _row(odds=1.91, captured_at="2026-06-19T10:00:00Z")
    result = apply(incoming, prior, game_state="final")
    assert result["is_close"] is True
    assert result["captured_at"] == "2026-06-19T08:00:00Z"
    assert result["price_changed"] is False


# ---------------------------------------------------------------------------
# D) Missing prior -> passthrough unchanged
# ---------------------------------------------------------------------------

def test_no_prior_passthrough_captured_at():
    """First observation: captured_at is NOT changed."""
    ts = "2026-06-19T09:15:00Z"
    row = _row(captured_at=ts)
    result = apply(row, None)
    assert result["captured_at"] == ts
    assert result["price_changed"] is False
    assert result["captured_at_preserved"] is False


def test_no_prior_extra_fields_preserved():
    """Other fields on the row are not dropped."""
    row = _row(captured_at="2026-06-19T09:00:00Z", home="NYK", away="SAS",
               sport="basketball_nba")
    result = apply(row, None)
    assert result["home"] == "NYK"
    assert result["away"] == "SAS"
    assert result["sport"] == "basketball_nba"


def test_prior_with_missing_captured_at_falls_through():
    """If prior's captured_at is empty/None, incoming captured_at is kept."""
    prior = _row(odds=1.91, captured_at="")
    incoming = _row(odds=1.91, captured_at="2026-06-19T10:00:00Z")
    result = apply(incoming, prior)
    # Price unchanged but prior has no usable timestamp -> keep incoming ts.
    assert result["captured_at"] == "2026-06-19T10:00:00Z"
    assert result["captured_at_preserved"] is False


# ---------------------------------------------------------------------------
# E) No fabricated timestamp
# ---------------------------------------------------------------------------

def test_no_timestamp_fabrication_on_first_observation():
    """apply() must not inject now() or any fabricated timestamp."""
    ts = "2026-06-19T11:00:00Z"
    row = _row(captured_at=ts)
    result = apply(row, None)
    assert result["captured_at"] == ts


def test_no_timestamp_fabrication_on_price_change():
    """Price change: incoming ts used as-is; no now() injection."""
    prior = _row(odds=1.91, captured_at="2026-06-19T08:00:00Z")
    incoming_ts = "2026-06-19T10:00:00Z"
    incoming = _row(odds=1.95, captured_at=incoming_ts)
    result = apply(incoming, prior)
    assert result["captured_at"] == incoming_ts


# ---------------------------------------------------------------------------
# apply_batch tests
# ---------------------------------------------------------------------------

def test_batch_same_and_changed():
    """Batch correctly applies per-row guards from prior_by_key map."""
    prior_map = {
        ("g1", "spread", "bk", "home"): _row(
            odds=1.91, line=-3.5, captured_at="2026-06-19T08:00:00Z",
            game_id="g1", market_type="spread", book="bk", side="home"),
        ("g1", "spread", "bk", "away"): _row(
            odds=1.95, line=3.5, captured_at="2026-06-19T08:00:00Z",
            game_id="g1", market_type="spread", book="bk", side="away"),
    }
    rows = [
        # unchanged
        _row(odds=1.91, line=-3.5, captured_at="2026-06-19T10:00:00Z",
             game_id="g1", market_type="spread", book="bk", side="home"),
        # changed
        _row(odds=1.99, line=3.5, captured_at="2026-06-19T10:00:00Z",
             game_id="g1", market_type="spread", book="bk", side="away"),
    ]
    results = apply_batch(rows, prior_map)
    assert results[0]["captured_at"] == "2026-06-19T08:00:00Z"   # preserved
    assert results[0]["price_changed"] is False
    assert results[1]["captured_at"] == "2026-06-19T10:00:00Z"   # advanced
    assert results[1]["price_changed"] is True


def test_batch_is_close_propagated():
    """game_state=final propagates is_close=True to all rows in batch."""
    rows = [_row(game_id="g1"), _row(game_id="g2")]
    results = apply_batch(rows, game_state="final")
    assert all(r["is_close"] is True for r in results)


def test_batch_empty_input():
    assert apply_batch([]) == []


def test_batch_no_prior_map_passthrough():
    ts = "2026-06-19T09:00:00Z"
    rows = [_row(captured_at=ts)]
    results = apply_batch(rows, None)
    assert results[0]["captured_at"] == ts
    assert results[0]["price_changed"] is False


def test_apply_does_not_mutate_inputs():
    """apply() must return a new dict; inputs unchanged."""
    prior = _row(captured_at="2026-06-19T08:00:00Z")
    incoming = _row(odds=1.91, captured_at="2026-06-19T10:00:00Z")
    prior_copy = dict(prior)
    incoming_copy = dict(incoming)
    apply(incoming, prior)
    assert prior == prior_copy
    assert incoming == incoming_copy
