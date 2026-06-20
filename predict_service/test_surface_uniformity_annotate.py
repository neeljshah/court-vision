"""Per-file test: predict_service.surface_uniformity_annotate.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_surface_uniformity_annotate.py -q

Acceptance criteria (BE-R5-2 iter1/iter2 P0):
  (a) A surface with 11 MLB games sharing 2 prob values stamps degenerate_model=True
      + honest note on each game and nulls tier on moneyline estimates.
  (b) A diverse MLB surface (>= 3 distinct prob values) is returned unchanged.
  (c) Non-MLB sports (nba, soccer, tennis) are never touched regardless of prob spread.
  (d) No $ field present in output; annotator never raises; degrades to unchanged on
      guard error (simulated via bad input).
"""
from __future__ import annotations

import copy
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predict_service.surface_uniformity_annotate import (
    DEGENERATE_NOTE,
    annotate_surface_games,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_DOLLAR_KEYS = frozenset({
    "pnl", "roi", "dollar", "profit", "expected_value_usd",
    "bankroll", "stake", "usd",
})


def _ml_est(label: str, prob: float) -> dict:
    """Minimal moneyline estimate dict."""
    return {
        "label": label,
        "market_type": "moneyline",
        "prob": prob,
        "tier": "B",
    }


def _game(game_id: str, home_prob: float, away_prob: float, **extra) -> dict:
    """Minimal game record with two moneyline estimates."""
    return {
        "game_id": game_id,
        "home": "TeamA",
        "away": "TeamB",
        "tipoff": "2026-06-25T18:00:00Z",
        "estimates": [
            _ml_est("home_ml", home_prob),
            _ml_est("away_ml", away_prob),
        ],
        **extra,
    }


def _flat_mlb_surface(n: int = 11) -> list:
    """Return n MLB games with exactly 2 unique prob values (0.5345 / 0.4655)."""
    return [_game(f"mlb_{i}", 0.5345, 0.4655) for i in range(n)]


def _diverse_mlb_surface(n: int = 11) -> list:
    """Return n MLB games with >= n distinct prob pairs."""
    import math
    games = []
    for i in range(n):
        hp = round(0.50 + (i * 0.01), 4)
        ap = round(1.0 - hp, 4)
        games.append(_game(f"mlb_d_{i}", hp, ap))
    return games


def _no_dollar_fields(obj: dict) -> bool:
    """Recursively assert no banned $ fields are present."""
    for k, v in obj.items():
        if k.lower() in _BANNED_DOLLAR_KEYS:
            return False
        if isinstance(v, dict) and not _no_dollar_fields(v):
            return False
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and not _no_dollar_fields(item):
                    return False
    return True


# ---------------------------------------------------------------------------
# (a) Flat MLB surface -- degenerate stamps applied
# ---------------------------------------------------------------------------

def test_flat_mlb_stamps_degenerate_model_true():
    """11 MLB games at 2 prob values -> every game gets degenerate_model=True."""
    games = _flat_mlb_surface(11)
    result = annotate_surface_games(games, "mlb")
    assert result is games, "must return the same list object"
    assert all(g.get("degenerate_model") is True for g in result), (
        "Expected degenerate_model=True on every game")


def test_flat_mlb_stamps_honest_note():
    """Honest note is stamped on every game (not a per-game calibrated divergence)."""
    games = _flat_mlb_surface(11)
    annotate_surface_games(games, "mlb")
    for g in games:
        note = g.get("degenerate_note", "")
        assert "MLB moneyline model uniform" in note, (
            f"Expected honest note; got: {note!r}")
        assert "base-rate only" in note


def test_flat_mlb_nulls_tier_on_moneyline_estimates():
    """When degenerate, tier is nulled on moneyline estimates inside each game."""
    games = _flat_mlb_surface(11)
    # Confirm tier starts at 'B'
    assert games[0]["estimates"][0]["tier"] == "B"
    annotate_surface_games(games, "mlb")
    for g in games:
        for est in g.get("estimates", []):
            assert est.get("tier") is None, (
                f"Expected tier=None after annotation; got {est.get('tier')!r}")


def test_flat_mlb_nulls_game_level_tier_when_present():
    """If a game record itself carries a top-level tier field it is nulled."""
    games = _flat_mlb_surface(3)
    for g in games:
        g["tier"] = "A"
    annotate_surface_games(games, "mlb")
    for g in games:
        assert g["tier"] is None


def test_flat_mlb_no_dollar_fields():
    """No banned $ field is present anywhere in the annotated output."""
    games = _flat_mlb_surface(11)
    annotate_surface_games(games, "mlb")
    for g in games:
        assert _no_dollar_fields(g), f"Dollar field found in game {g.get('game_id')}"


# ---------------------------------------------------------------------------
# (b) Diverse MLB surface -- unchanged
# ---------------------------------------------------------------------------

def test_diverse_mlb_surface_unchanged():
    """MLB surface with >= 3 distinct prob values is returned unchanged."""
    games = _diverse_mlb_surface(11)
    original = copy.deepcopy(games)
    result = annotate_surface_games(games, "mlb")
    assert result is games
    for g, o in zip(result, original):
        assert g.get("degenerate_model") is not True, (
            "diverse surface should not be stamped degenerate")
        assert g == o, "diverse game record should be unchanged"


def test_single_value_mlb_still_stamps():
    """A surface where every game shares the exact same prob is also degenerate."""
    games = [_game(f"m{i}", 0.5000, 0.5000) for i in range(5)]
    annotate_surface_games(games, "mlb")
    assert all(g.get("degenerate_model") is True for g in games)


# ---------------------------------------------------------------------------
# (c) Non-MLB sports are never touched
# ---------------------------------------------------------------------------

def _flat_nba_surface(n: int = 8) -> list:
    """NBA games with identical probs (would trigger MLB guard if applied)."""
    return [_game(f"nba_{i}", 0.5345, 0.4655) for i in range(n)]


def test_nba_surface_never_touched():
    """NBA surface with flat probs is NOT annotated (MLB-only guard)."""
    games = _flat_nba_surface(8)
    original = copy.deepcopy(games)
    result = annotate_surface_games(games, "nba")
    assert result is games
    for g, o in zip(result, original):
        assert g == o, "NBA game record should be completely unchanged"


def test_soccer_surface_never_touched():
    games = [_game(f"s_{i}", 0.40, 0.35) for i in range(5)]
    original = copy.deepcopy(games)
    annotate_surface_games(games, "soccer")
    assert all(g == o for g, o in zip(games, original))


def test_tennis_surface_never_touched():
    games = [_game(f"t_{i}", 0.5345, 0.4655) for i in range(6)]
    original = copy.deepcopy(games)
    annotate_surface_games(games, "tennis")
    assert all(g == o for g, o in zip(games, original))


# ---------------------------------------------------------------------------
# (d) Error safety / degenerate-to-unchanged / no $ field
# ---------------------------------------------------------------------------

def test_empty_games_returns_empty():
    result = annotate_surface_games([], "mlb")
    assert result == []


def test_none_estimates_field_does_not_raise():
    """Game records with no 'estimates' key should be handled gracefully."""
    games = [
        {"game_id": "x1", "home": "A", "away": "B"},
        {"game_id": "x2", "home": "C", "away": "D", "estimates": None},
    ]
    # 0 ML probs extracted -> guard not triggered -> returned unchanged
    result = annotate_surface_games(games, "mlb")
    assert result is games


def test_malformed_prob_does_not_raise():
    """Non-numeric prob values are skipped; annotator never raises."""
    games = [
        _game("bad1", 0.5345, 0.4655),
        {"game_id": "bad2", "estimates": [{"label": "home_ml", "market_type": "moneyline", "prob": "NaN"}]},
    ]
    try:
        result = annotate_surface_games(games, "mlb")
    except Exception as exc:
        raise AssertionError(f"annotate_surface_games raised: {exc}") from exc


def test_non_dict_items_in_games_do_not_raise():
    """A games list containing non-dict items must not raise."""
    games = [None, 42, "bad", _game("ok1", 0.5345, 0.4655)]
    try:
        annotate_surface_games(games, "mlb")
    except Exception as exc:
        raise AssertionError(f"annotate_surface_games raised on non-dict items: {exc}") from exc


def test_no_dollar_field_on_any_output_diverse():
    """Diverse MLB surface output carries no $ fields."""
    games = _diverse_mlb_surface(6)
    annotate_surface_games(games, "mlb")
    for g in games:
        assert _no_dollar_fields(g)


def test_annotator_is_idempotent():
    """Running annotate twice on a flat surface produces the same result."""
    games = _flat_mlb_surface(5)
    annotate_surface_games(games, "mlb")
    snap1 = [g.get("degenerate_model") for g in games]
    annotate_surface_games(games, "mlb")
    snap2 = [g.get("degenerate_model") for g in games]
    assert snap1 == snap2


if __name__ == "__main__":
    tests = [
        test_flat_mlb_stamps_degenerate_model_true,
        test_flat_mlb_stamps_honest_note,
        test_flat_mlb_nulls_tier_on_moneyline_estimates,
        test_flat_mlb_nulls_game_level_tier_when_present,
        test_flat_mlb_no_dollar_fields,
        test_diverse_mlb_surface_unchanged,
        test_single_value_mlb_still_stamps,
        test_nba_surface_never_touched,
        test_soccer_surface_never_touched,
        test_tennis_surface_never_touched,
        test_empty_games_returns_empty,
        test_none_estimates_field_does_not_raise,
        test_malformed_prob_does_not_raise,
        test_non_dict_items_in_games_do_not_raise,
        test_no_dollar_field_on_any_output_diverse,
        test_annotator_is_idempotent,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
