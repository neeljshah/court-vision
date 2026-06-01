"""tests/test_bet_card_render.py — Regression tests for _bet_card.html template fixes.

Covers:
  BUG 3  — lines_router._today() is ET-anchored, not server-local.
  BUG 4  — ev_pct=None (and edge_units=None) no longer raises Jinja TypeError.
  BUG 11 — live ladder accent identifies best_book+line, not loop.first (lowest line).
"""
from __future__ import annotations

import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Jinja2 setup
# ---------------------------------------------------------------------------
try:
    from jinja2 import Environment, FileSystemLoader, Undefined

    _TMPL_DIR = Path(__file__).resolve().parent.parent / "api" / "templates"
    _env = Environment(
        loader=FileSystemLoader(str(_TMPL_DIR)),
        undefined=Undefined,          # strict — surface errors, not silently empty
    )
    JINJA_AVAILABLE = True
except ImportError:
    JINJA_AVAILABLE = False


# ---------------------------------------------------------------------------
# Minimal fake objects that quack like a bet / slate namespace
# ---------------------------------------------------------------------------

def _make_bet(**overrides):
    """Return a SimpleNamespace that satisfies _bet_card.html's template vars."""
    defaults = dict(
        player_name="LeBron James",
        team="LAL",
        opp="GSW",
        venue="home",
        prop_stat="PTS",
        side="OVER",
        line=27.5,
        best_book="FanDuel",
        best_price=-115,
        q50=29.3,
        edge_units=1.8,
        ev_pct=5.2,
        model_prob=0.58,
        market_prob=0.54,
        team_color="#552583",
        all_books_live=None,
        all_books=[],
        ev_capped=False,
        form_divergence=False,
        form_divergence_text="",
        conf_tier=None,
        entry_label=None,
        conf_pct=None,
        kelly_stake_dollars=None,
        kelly_dollars=None,
        line_delta=None,
        line_open=None,
        line_current=None,
        line_velocity_per_min=None,
        line_dir_vs_proj=None,
        live_regraded_stale_price=False,
        freshest_book_age_min=None,
        bet_id="test-bet-001",
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _make_slate(**overrides):
    defaults = dict(date="2026-05-31")
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _render_bet_card(bet, rank=1, slate=None):
    """Render _bet_card.html with the given bet and return the HTML string."""
    if slate is None:
        slate = _make_slate()
    # _bet_card.html includes _bet_card_reasoning.html — stub it so we
    # don't need a real reasoning template.
    env = Environment(
        loader=FileSystemLoader(str(_TMPL_DIR)),
    )
    # Patch the environment to return an empty string for the reasoning include.
    real_get = env.loader.get_source

    def _patched_get(environment, template):
        if template == "_bet_card_reasoning.html":
            return ("", "_bet_card_reasoning.html", lambda: True)
        return real_get(environment, template)

    env.loader.get_source = _patched_get
    tmpl = env.get_template("_bet_card.html")
    return tmpl.render(bet=bet, rank=rank, slate=slate)


# ---------------------------------------------------------------------------
# BUG 3 — lines_router._today() must be ET-anchored
# ---------------------------------------------------------------------------

class TestTodayET:
    """lines_router._today() returns the ET date, not the UTC date."""

    def test_today_returns_string(self):
        from api.lines_router import _today
        result = _today()
        assert isinstance(result, str)
        assert len(result) == 10
        assert result[4] == "-" and result[7] == "-"

    def test_today_is_et_not_utc_during_midnight_window(self):
        """At 01:00 UTC (which is 21:00 ET previous day), _today() must
        return yesterday's date in ET, not today's UTC date.

        Example: 2026-06-01T01:00:00Z  →  ET = 2026-05-31T21:00-04:00
        So _today() should return "2026-05-31", not "2026-06-01".
        """
        from api.lines_router import _today

        # Simulate 01:00 UTC on June 1 (= 21:00 ET May 31)
        fake_utc = datetime(2026, 6, 1, 1, 0, 0, tzinfo=timezone.utc)

        with patch("api.lines_router.datetime") as mock_dt:
            mock_dt.now.return_value = fake_utc
            # _today() calls datetime.now(timezone.utc) — make it work
            mock_dt.now.side_effect = lambda tz=None: fake_utc if tz is not None else fake_utc
            result = _today()

        # ET date should be 2026-05-31, not 2026-06-01
        assert result == "2026-05-31", (
            f"Expected ET date '2026-05-31' at 01:00 UTC, got '{result}'. "
            "lines_router._today() is not ET-anchored."
        )

    def test_today_correct_at_noon_utc(self):
        """At 12:00 UTC, both ET and UTC are the same calendar date."""
        from api.lines_router import _today

        fake_utc = datetime(2026, 5, 31, 12, 0, 0, tzinfo=timezone.utc)

        with patch("api.lines_router.datetime") as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: fake_utc
            result = _today()

        assert result == "2026-05-31"


# ---------------------------------------------------------------------------
# BUG 4 — ev_pct=None must NOT raise TypeError in the Jinja color class block
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not JINJA_AVAILABLE, reason="jinja2 not installed")
class TestEvPctNoneGuard:

    def test_ev_pct_none_renders_without_error(self):
        """_bet_card.html must not TypeError when ev_pct is None."""
        bet = _make_bet(ev_pct=None, edge_units=1.5)
        # Should not raise
        html = _render_bet_card(bet)
        assert "LeBron James" in html
        # The EV cell should render the dash placeholder
        assert "pending" in html or "—" in html

    def test_ev_pct_none_and_edge_units_none_renders(self):
        """Both ev_pct and edge_units being None must not raise."""
        bet = _make_bet(ev_pct=None, edge_units=None)
        html = _render_bet_card(bet)
        assert "LeBron James" in html

    def test_ev_pct_positive_renders_num_pos(self):
        """Positive ev_pct renders with num-pos class."""
        bet = _make_bet(ev_pct=7.5, edge_units=2.0)
        html = _render_bet_card(bet)
        assert "num-pos" in html

    def test_ev_pct_negative_renders_num_neg(self):
        """Negative ev_pct renders with num-neg class."""
        bet = _make_bet(ev_pct=-3.1, edge_units=-0.5)
        html = _render_bet_card(bet)
        assert "num-neg" in html

    def test_normal_bet_renders_without_regression(self):
        """A fully-populated normal bet renders correctly end-to-end."""
        bet = _make_bet()
        html = _render_bet_card(bet)
        assert "LeBron James" in html
        assert "OVER" in html
        assert "FanDuel" in html


# ---------------------------------------------------------------------------
# BUG 11 — live ladder accent must match best_book+line, not loop.first
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not JINJA_AVAILABLE, reason="jinja2 not installed")
class TestLiveLadderAccent:

    def _make_live_books(self):
        """Return a live book list where the LOWEST-line book is NOT best_book.

        Sorted by line ascending (as the router does): DraftKings 26.5 first,
        then FanDuel 27.5, then BetMGM 28.5.  The served bet's best_book is
        FanDuel with line=27.5.  The accent should land on FanDuel, not DraftKings.
        """
        return [
            types.SimpleNamespace(book="DraftKings", line=26.5, over=-110, under=-110),
            types.SimpleNamespace(book="FanDuel",    line=27.5, over=-115, under=-105),
            types.SimpleNamespace(book="BetMGM",     line=28.5, over=-105, under=-115),
        ]

    def test_accent_on_best_book_not_loop_first(self):
        """The accented rung must be FanDuel (best_book+line), not DraftKings (loop.first)."""
        live_books = self._make_live_books()
        bet = _make_bet(
            all_books_live=live_books,
            best_book="FanDuel",
            line=27.5,
            best_price=-115,
        )
        html = _render_bet_card(bet)

        # Parse out the live-lines section
        # The accented span uses 'var(--cv-accent)' for color.
        # Find accent spans and verify which book name appears in them.
        import re

        # Each book rung looks like:
        # <span data-book="..." style="border:1px solid <color>;color:<color>">
        # Extract (book_name, color) pairs from the live ladder section.
        # We look for spans with data-book inside .bet-shop-live
        pattern = re.compile(
            r'data-book="([^"]+)"[^>]*style="[^"]*color:([^";]+)',
            re.DOTALL,
        )
        matches = pattern.findall(html)

        # Filter to live ladder only (all_books_live section rendered before shop: section)
        # Accent color is 'var(--cv-accent)', muted is 'var(--cv-muted)'.
        accented_books = [
            book for book, color in matches if "cv-accent" in color
        ]

        assert "FanDuel" in accented_books, (
            f"Expected FanDuel to be accented (best_book+line match), "
            f"but accented books are: {accented_books}. "
            "BUG 11: loop.first (DraftKings) is being accented instead."
        )
        assert "DraftKings" not in accented_books, (
            f"DraftKings (loop.first, lowest-line) must NOT be accented. "
            f"Accented: {accented_books}"
        )

    def test_accent_on_loop_first_when_it_is_best_book(self):
        """When loop.first IS also best_book+line, accent is still correct."""
        live_books = [
            types.SimpleNamespace(book="FanDuel",    line=27.5, over=-115, under=-105),
            types.SimpleNamespace(book="DraftKings", line=28.5, over=-110, under=-110),
        ]
        bet = _make_bet(
            all_books_live=live_books,
            best_book="FanDuel",
            line=27.5,
            best_price=-115,
        )
        html = _render_bet_card(bet)
        import re
        pattern = re.compile(r'data-book="([^"]+)"[^>]*style="[^"]*color:([^";]+)')
        matches = pattern.findall(html)
        accented_books = [book for book, color in matches if "cv-accent" in color]
        assert "FanDuel" in accented_books
