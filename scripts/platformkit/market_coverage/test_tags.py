"""Per-file tests for market_coverage.tags -- thinness + validatable taxonomy.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/market_coverage/tests/test_tags.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import pytest  # noqa: E402

from scripts.platformkit.market_coverage import tags as TG  # noqa: E402


def test_seven_categories():
    assert len(TG.CATEGORIES) == 7
    assert "ingame-micro" in TG.CATEGORIES
    assert "mlb-soccer-tennis" in TG.CATEGORIES


def test_mainline_detection():
    assert TG.is_mainline("home_ml", "team")
    assert TG.is_mainline("game_total O221.5", "team")
    assert TG.is_mainline("match_winner NYK", "side")
    # NOT mainlines: team totals, quarter, player props.
    assert not TG.is_mainline("home_team_total O112.5", "team")
    assert not TG.is_mainline("q1_total O55.5", "quarter")
    assert not TG.is_mainline("Star A pts O26", "single")


def test_mainline_is_liquid_has_close():
    thin = TG.thinness_for("team-quarter-half", "home_ml", "team", 0.55)
    val = TG.validatable_for("team-quarter-half", "home_ml", "team")
    assert thin == "LIQUID"
    assert val == "HAS_CLOSE"
    assert TG.needs_forward_clv(val) is False


def test_obscure_defaults_and_forward_clv():
    thin = TG.thinness_for("player-props-combos", "Star A double_double", "single", 0.4)
    val = TG.validatable_for("player-props-combos", "Star A double_double", "single")
    assert thin == "THIN"
    assert val == "FORWARD_ONLY"
    assert TG.needs_forward_clv(val) is True


def test_deep_tail_escalates_to_extreme():
    thin = TG.thinness_for("player-props-core", "Star A pts 40+", "single", 0.02)
    assert thin == "EXTREME"


def test_unknown_category_raises():
    with pytest.raises(KeyError):
        TG.category_thinness("not-a-category")
    with pytest.raises(KeyError):
        TG.category_validatable("not-a-category")


def test_honesty_note_branches():
    assert "MATCH" in TG.honesty_note("LIQUID", "HAS_CLOSE")
    assert "forward CLV" in TG.honesty_note("EXTREME", "FORWARD_ONLY")
    assert "SUGGESTIVE" in TG.honesty_note("THIN", "PRICE_ONLY")
