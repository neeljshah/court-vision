"""
tests/test_wave4_templates.py — Wave-4 template regression tests.

Covers:
  BUG 2 — share.html ev_pct=None guard (was TypeError on None > 0)
  BUG 4 — share.html best_price=None guard (was TypeError on '%+d'|format(None))
  BUG 6 — odds.html loadArbs() field-name audit (string check; JS not runnable in Jinja)
"""

import types
import pytest
from jinja2 import Environment, FileSystemLoader, Undefined

# ---------------------------------------------------------------------------
# Jinja env pointing at the real template directory
# ---------------------------------------------------------------------------
TEMPLATE_DIR = "api/templates"


def _make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        undefined=Undefined,   # silent for missing vars we don't supply
        autoescape=False,
    )
    return env


# ---------------------------------------------------------------------------
# Minimal bet / slate stubs
# ---------------------------------------------------------------------------

def _slate():
    return types.SimpleNamespace(
        date="2026-05-31",
        generated_at="2026-05-31 12:00 ET",
    )


def _bet_base():
    """A fully-valid bet with all fields populated."""
    return types.SimpleNamespace(
        player_name="LeBron James",
        team="LAL",
        opp="BOS",
        venue="home",
        prop_stat="PTS",
        side="OVER",
        line=25.5,
        best_book="FanDuel",
        best_price=-115,
        q50=27.3,
        edge_units=1.8,
        ev_pct=6.4,
        team_color="#552583",
        spark_last5=[24, 26, 28, 22, 30],
        last_5_median=26.0,
        season_median=25.5,
        narrative_text="Strong pace advantage tonight.",
    )


def _render_share(bets, slate=None):
    env = _make_env()
    tpl = env.get_template("share.html")
    ctx = dict(
        shown=bets,
        slate=slate or _slate(),
        avg_ev=5.0,
        share_text="Test share text",
    )
    # share.html extends base.html — render the block content only via macro trick;
    # easier: render with blocks disabled by rendering the raw template source with
    # a synthetic base that passes content through.
    # Simplest: patch the env to make {% extends %} a no-op by providing a dummy base.
    env2 = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    # Override base.html in memory so extends works without the full CSS stack.
    from jinja2 import DictLoader, ChoiceLoader
    base_stub = (
        "{% block title %}{% endblock %}"
        "{% block subtitle %}{% endblock %}"
        "{% block og_title %}{% endblock %}"
        "{% block og_desc %}{% endblock %}"
        "{% block content %}{% endblock %}"
        "{% block footer %}{% endblock %}"
    )
    stub_loader = DictLoader({"base.html": base_stub})
    env2 = Environment(
        loader=ChoiceLoader([stub_loader, FileSystemLoader(TEMPLATE_DIR)]),
        autoescape=False,
    )
    tpl2 = env2.get_template("share.html")
    return tpl2.render(**ctx)


# ---------------------------------------------------------------------------
# BUG 2 — ev_pct=None must not raise; must render an em-dash
# ---------------------------------------------------------------------------

class TestBug2EvPctNone:
    def test_no_type_error(self):
        bet = _bet_base()
        bet.ev_pct = None
        # Must not raise TypeError
        html = _render_share([bet])
        assert html is not None

    def test_renders_dash(self):
        bet = _bet_base()
        bet.ev_pct = None
        html = _render_share([bet])
        # The em-dash entity should appear in the EV cell
        assert "&mdash;" in html

    def test_no_percent_sign_for_none(self):
        bet = _bet_base()
        bet.ev_pct = None
        html = _render_share([bet])
        # Should not attempt to format None as a float percentage
        # (would produce something like "+None%" if the guard fails)
        assert "+None%" not in html
        assert "None%" not in html


# ---------------------------------------------------------------------------
# BUG 4 — best_book set + best_price=None must not raise
# ---------------------------------------------------------------------------

class TestBug4BestPriceNone:
    def test_no_type_error(self):
        bet = _bet_base()
        bet.best_price = None  # best_book still set to "FanDuel"
        html = _render_share([bet])
        assert html is not None

    def test_book_line_omitted_when_price_none(self):
        bet = _bet_base()
        bet.best_price = None
        html = _render_share([bet])
        # The book · price fragment should be absent entirely
        assert "FanDuel" not in html

    def test_no_none_in_price_output(self):
        bet = _bet_base()
        bet.best_price = None
        html = _render_share([bet])
        assert "+None" not in html


# ---------------------------------------------------------------------------
# Normal render — both ev_pct and best_price set → should show values
# ---------------------------------------------------------------------------

class TestNormalRenderUnaffected:
    def test_ev_pct_positive_shows_value(self):
        bet = _bet_base()
        bet.ev_pct = 6.4
        html = _render_share([bet])
        assert "+6.4%" in html

    def test_ev_pct_negative_shows_value(self):
        bet = _bet_base()
        bet.ev_pct = -3.2
        html = _render_share([bet])
        assert "-3.2%" in html

    def test_best_price_shows_when_set(self):
        bet = _bet_base()
        bet.best_book = "DraftKings"
        bet.best_price = -110
        html = _render_share([bet])
        assert "DraftKings" in html
        assert "-110" in html


# ---------------------------------------------------------------------------
# BUG 6 — odds.html source must reference correct field names (string audit)
# ---------------------------------------------------------------------------

class TestBug6OddsHtmlFieldNames:
    @pytest.fixture(scope="class")
    def odds_src(self):
        with open(f"{TEMPLATE_DIR}/odds.html", encoding="utf-8") as f:
            return f.read()

    def test_uses_over_spread_pp(self, odds_src):
        assert "over_spread_pp" in odds_src, (
            "odds.html must reference r.over_spread_pp (real field from cross_book_spread)"
        )

    def test_uses_under_spread_pp(self, odds_src):
        assert "under_spread_pp" in odds_src, (
            "odds.html must reference r.under_spread_pp"
        )

    def test_uses_arb_best_over_book(self, odds_src):
        assert "arb_best_over_book" in odds_src, (
            "odds.html must reference r.arb_best_over_book (only present on is_arb rows)"
        )

    def test_uses_arb_best_under_book(self, odds_src):
        assert "arb_best_under_book" in odds_src, (
            "odds.html must reference r.arb_best_under_book"
        )

    def test_no_stale_spread_pp(self, odds_src):
        # The old bare "r.spread_pp" field does not exist in the API schema.
        # Acceptable references: "over_spread_pp", "under_spread_pp" — but NOT
        # a standalone "spread_pp" that is not prefixed with over_ or under_.
        import re
        bare = re.findall(r'\br\.spread_pp\b', odds_src)
        assert bare == [], (
            f"odds.html still references non-existent r.spread_pp: {bare}"
        )

    def test_no_stale_best_over_book(self, odds_src):
        import re
        # r.best_over_book (without arb_ prefix) does not exist in schema
        bare = re.findall(r'\br\.best_over_book\b', odds_src)
        assert bare == [], (
            f"odds.html still references non-existent r.best_over_book: {bare}"
        )

    def test_no_stale_best_under_book(self, odds_src):
        import re
        bare = re.findall(r'\br\.best_under_book\b', odds_src)
        assert bare == [], (
            f"odds.html still references non-existent r.best_under_book: {bare}"
        )
