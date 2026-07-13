"""Per-file unit tests for scripts.platformkit.odds_shop (network-free).

Covers best_line, devig_twoway, detect_arb (a known arb + a no-arb case),
ev_vs_price (+EV and -EV), parse_event_books, and fetch_odds degradation when
ODDS_API_KEY is absent (no live key, no fabricated price).

Run (per-file ONLY -- full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest scripts/platformkit/test_odds_shop.py -q
"""
from __future__ import annotations

from scripts.platformkit import odds_shop as os_mod


def test_best_line_picks_highest_per_side():
    book_prices = {
        "DK":   {"HOME": 1.95, "AWAY": 1.90},
        "FD":   {"HOME": 2.05, "AWAY": 1.85},
        "MGM":  {"HOME": 2.00, "AWAY": 1.92},
    }
    best = os_mod.best_line(book_prices)
    assert best["HOME"] == {"book": "FD", "price": 2.05}
    assert best["AWAY"] == {"book": "MGM", "price": 1.92}


def test_best_line_skips_bad_and_missing_sides():
    book_prices = {
        "DK":  {"HOME": 1.50},                 # only quotes HOME
        "FD":  {"HOME": "1.0", "AWAY": 3.0},   # HOME=1.0 invalid (<=1.0)
        "BAD": {"HOME": "x", "AWAY": None},     # unparseable -> skipped
    }
    best = os_mod.best_line(book_prices)
    assert best["HOME"] == {"book": "DK", "price": 1.50}
    assert best["AWAY"] == {"book": "FD", "price": 3.0}


def test_devig_twoway_sums_to_one_and_orders_correctly():
    # Favourite at 1.50, dog at 2.50; quoted booksum > 1 (has vig).
    fa, fb = os_mod.devig_twoway(1.50, 2.50)
    assert abs((fa + fb) - 1.0) < 1e-6
    assert fa > fb            # the shorter price is the favourite
    assert 0.0 < fb < fa < 1.0


# --------------------------------------------------------------------------- #
# Degenerate booksum <= 1 (proxy/stale/arb quote): Shin's solver requires
# booksum > 1 and used to raise -- crashed every uncaught caller (a 3-day
# m1_paper grading-tick outage). devig_twoway now bypasses Shin below this
# threshold and returns the implied probs proportionally normalised to 1.
# --------------------------------------------------------------------------- #
def test_devig_twoway_subone_booksum_bypasses_shin_no_raise():
    pa, pb = 2.10, 2.10  # 1/2.10 + 1/2.10 = 0.952381 < 1 (a two-way arb quote)
    fa, fb = os_mod.devig_twoway(pa, pb)
    assert abs((fa + fb) - 1.0) < 1e-9
    assert abs(fa - 0.5) < 1e-9 and abs(fb - 0.5) < 1e-9  # symmetric -> 50/50


def test_devig_twoway_exact_booksum_one_same_branch():
    # booksum == 1.0 exactly (vig-free by construction, e.g. a kx-ticker naive
    # complement) -- hits the same bypass branch as sub-1 (not Shin); implied
    # probs already sum to 1 so they pass through unchanged.
    fa, fb = os_mod.devig_twoway(2.0, 2.0)  # 1/2.0 + 1/2.0 == 1.0 exactly
    assert fa == 0.5 and fb == 0.5


def test_devig_twoway_normal_vig_matches_shin_exactly_regression():
    # Real-vig asymmetric pair (booksum ~1.043, well above 1 + eps) -- the
    # unchanged code path. Must match a direct shin_devig_decimal call to
    # 1e-12: the degenerate-pair guard must not perturb existing Shin output.
    from scripts.platformkit.eval_gate.shin import shin_devig_decimal
    pa, pb = 1.80, 2.05
    fa, fb = os_mod.devig_twoway(pa, pb)
    probs, _z = shin_devig_decimal([pa, pb])
    assert abs(fa - probs[0]) < 1e-12
    assert abs(fb - probs[1]) < 1e-12
    # Sanity the Shin path (not the bypass) actually ran: Shin's favourite-
    # longshot shrinkage differs from naive proportional normalisation for an
    # asymmetric vig pair.
    booksum = 1.0 / pa + 1.0 / pb
    naive_fa = (1.0 / pa) / booksum
    assert abs(fa - naive_fa) > 1e-6


def test_devig_twoway_live_incident_fixture_booksum_0_7477():
    # Representative of the diagnosed live incident: degenerate proxy-close
    # pairs with booksum in [0.72, 0.82] crashed shin_devig_decimal's
    # `assert B > 1.0` for every uncaught caller for 3 days. This fixture
    # reproduces that band (booksum ~0.7477) -- must not raise.
    pa, pb = 2.05, 3.85
    booksum = 1.0 / pa + 1.0 / pb
    assert 0.72 < booksum < 0.82  # matches the diagnosed live-incident band
    fa, fb = os_mod.devig_twoway(pa, pb)
    assert abs((fa + fb) - 1.0) < 1e-9
    assert abs(fa - (1.0 / pa) / booksum) < 1e-9
    assert abs(fb - (1.0 / pb) / booksum) < 1e-9


def test_detect_arb_known_arb():
    # a=2.10, b=2.10 -> 1/2.10 + 1/2.10 = 0.952381 < 1 -> arb.
    res = os_mod.detect_arb(2.10, 2.10)
    assert res["arb"] is True
    assert res["booksum"] < 1.0
    assert res["margin_pct"] > 0.0
    assert abs(res["stake_a"] + res["stake_b"] - 1.0) < 1e-6
    assert abs(res["stake_a"] - 0.5) < 1e-6   # symmetric odds -> 50/50 split


def test_detect_arb_no_arb():
    # Typical -110/-110 market: 1.91 each -> booksum ~1.047 > 1 -> no arb.
    res = os_mod.detect_arb(1.91, 1.91)
    assert res["arb"] is False
    assert res["booksum"] > 1.0
    assert res["margin_pct"] is None
    assert res["stake_a"] is None


def test_detect_arb_rejects_bad_odds():
    res = os_mod.detect_arb(1.0, 5.0)
    assert res["arb"] is False
    assert res["margin_pct"] is None


def test_ev_vs_price_positive_when_model_beats_price():
    # Model 60% at 2.00 -> EV = 0.60*2.00 - 1 = +0.20 per $1.
    ev = os_mod.ev_vs_price(0.60, 2.00)
    assert ev > 0
    assert abs(ev - 0.20) < 1e-9


def test_ev_vs_price_negative_when_price_too_short():
    # Model 40% at 2.00 -> EV = 0.40*2.00 - 1 = -0.20 per $1.
    ev = os_mod.ev_vs_price(0.40, 2.00)
    assert ev < 0
    assert abs(ev - (-0.20)) < 1e-9


def test_summarise_twoway_bundles_fields():
    book_prices = {
        "DK": {"HOME": 2.10, "AWAY": 1.95},
        "FD": {"HOME": 2.02, "AWAY": 2.10},   # AWAY best here -> arb with HOME 2.10
    }
    out = os_mod.summarise_twoway(book_prices, "HOME", "AWAY", model_prob_a=0.55)
    assert out["best_a_book"] == "DK" and out["best_a_price"] == 2.10
    assert out["best_b_book"] == "FD" and out["best_b_price"] == 2.10
    # 1/2.10 + 1/2.10 < 1 -> arb present. An arb has booksum < 1, so Shin has no
    # overround to remove; devig_twoway bypasses Shin and proportionally
    # normalises the implied probs (symmetric prices -> 0.5/0.5) instead of
    # leaving fair_prob_* None.
    assert out["arb_pct"] is not None and out["arb_pct"] > 0
    assert out["fair_prob_a"] == 0.5 and out["fair_prob_b"] == 0.5
    # model EV vs best price on each side
    assert abs(out["model_ev_a"] - (0.55 * 2.10 - 1.0)) < 1e-6
    assert abs(out["model_ev_b"] - (0.45 * 2.10 - 1.0)) < 1e-6


def test_summarise_twoway_devigs_normal_vig_market():
    # No-arb market (booksum > 1) -> fair probs are produced and sum to 1.
    book_prices = {
        "DK": {"HOME": 1.91, "AWAY": 1.91},
        "FD": {"HOME": 1.95, "AWAY": 1.88},
    }
    out = os_mod.summarise_twoway(book_prices, "HOME", "AWAY", model_prob_a=0.50)
    assert out["arb_pct"] is None              # 1/1.95 + 1/1.91 > 1 -> no arb
    assert out["fair_prob_a"] is not None and out["fair_prob_b"] is not None
    assert abs((out["fair_prob_a"] + out["fair_prob_b"]) - 1.0) < 1e-6


def test_parse_event_books_extracts_h2h():
    event = {
        "id": "evt1",
        "bookmakers": [
            {"title": "DraftKings", "markets": [
                {"key": "h2h", "outcomes": [
                    {"name": "Boston", "price": 1.80},
                    {"name": "Lakers", "price": 2.05},
                ]},
                {"key": "totals", "outcomes": [{"name": "Over", "price": 1.91}]},
            ]},
            {"title": "FanDuel", "markets": [
                {"key": "h2h", "outcomes": [
                    {"name": "Boston", "price": 1.85},
                    {"name": "Lakers", "price": "x"},   # bad -> skipped
                ]},
            ]},
            {"title": "Empty"},                          # no markets -> skipped
        ],
    }
    books = os_mod.parse_event_books(event, "h2h")
    assert books["DraftKings"] == {"Boston": 1.80, "Lakers": 2.05}
    assert books["FanDuel"] == {"Boston": 1.85}          # bad Lakers price dropped
    assert "Empty" not in books


def test_fetch_odds_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    res = os_mod.fetch_odds("basketball_nba")
    assert res["status"] == "unavailable"
    assert "ODDS_API_KEY" in res["reason"]
    assert "events" not in res                            # never a fabricated price


def test_fetch_odds_degrades_on_network_failure(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "dummy-test-key-not-real")

    def boom(url, timeout=20.0):  # noqa: ANN001
        raise OSError("simulated network down")

    res = os_mod.fetch_odds("basketball_nba", http_get=boom)
    assert res["status"] == "unavailable"
    assert "failed" in res["reason"].lower()


def test_fetch_odds_ok_with_injected_payload(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "dummy-test-key-not-real")
    payload = [{"id": "e1", "bookmakers": []}]
    res = os_mod.fetch_odds("basketball_nba", http_get=lambda url, timeout=20.0: payload)
    assert res["status"] == "ok"
    assert res["events"] == payload


# --------------------------------------------------------------------------- #
# venue_type HONESTY tag: a prediction-market YES price must not win the
# bettable best line / arb; PM prices stay visible separately.
# --------------------------------------------------------------------------- #
def test_best_line_no_filter_pm_can_win_legacy_default():
    # Default (no restrict): legacy behaviour -- the PM (kalshi) price WINS if
    # it is the highest. This guards back-compat (the old result is preserved).
    book_prices = {
        "espn:DraftKings": {"HOME": 1.95, "AWAY": 1.90},
        "kalshi":          {"HOME": 2.20, "AWAY": 1.70},
    }
    best = os_mod.best_line(book_prices)
    assert best["HOME"] == {"book": "kalshi", "price": 2.20}


def test_best_line_sportsbook_restrict_excludes_pm():
    # Restricted to sportsbooks: the thin kalshi YES price is ignored, so the
    # republished ESPN book wins the bettable best HOME line.
    book_prices = {
        "espn:DraftKings": {"HOME": 1.95, "AWAY": 1.90},
        "kalshi":          {"HOME": 2.20, "AWAY": 1.70},
    }
    best = os_mod.best_line(book_prices, restrict_to=os_mod.VENUE_SPORTSBOOK)
    assert best["HOME"] == {"book": "espn:DraftKings", "price": 1.95}
    assert best["AWAY"] == {"book": "espn:DraftKings", "price": 1.90}


def test_pm_line_sees_only_prediction_markets():
    book_prices = {
        "espn:DraftKings": {"HOME": 1.95, "AWAY": 1.90},
        "kalshi":          {"HOME": 2.20, "AWAY": 1.70},
        "polymarket":      {"HOME": 2.30, "AWAY": 1.65},
    }
    pm = os_mod.pm_line(book_prices)
    assert pm["HOME"] == {"book": "polymarket", "price": 2.30}  # best PM HOME
    assert pm["AWAY"] == {"book": "kalshi", "price": 1.70}      # best PM AWAY
    assert "espn:DraftKings" not in {v["book"] for v in pm.values()}


def test_summarise_sportsbook_restrict_drops_pm_arb_keeps_pm_visible():
    # An apparent arb exists ONLY because a thin PM YES price is the best on one
    # side. Restricting the bettable scan to sportsbooks removes that phantom arb;
    # the PM price stays visible separately as a divergence signal.
    book_prices = {
        "espn:DraftKings": {"HOME": 1.95, "AWAY": 1.90},  # sportsbook, no arb
        "kalshi":          {"HOME": 2.30, "AWAY": 2.30},  # PM: would arb w/ itself
    }
    out = os_mod.summarise_twoway(
        book_prices, "HOME", "AWAY",
        bettable_restrict=os_mod.VENUE_SPORTSBOOK)
    # Bettable best is the sportsbook -- PM never surfaces as the bettable best.
    assert out["best_a_book"] == "espn:DraftKings" and out["best_a_price"] == 1.95
    assert out["best_b_book"] == "espn:DraftKings" and out["best_b_price"] == 1.90
    assert out["arb_pct"] is None  # no sportsbook-only arb (1.95/1.90 booksum>1)
    # PM line is surfaced SEPARATELY (signal, not bettable).
    assert out["pm_a_book"] == "kalshi" and out["pm_a_price"] == 2.30
    assert out["pm_b_book"] == "kalshi" and out["pm_b_price"] == 2.30


def test_summarise_default_unchanged_for_sportsbook_only_inputs():
    # Pure-sportsbook input + default (no restrict): identical to legacy result.
    book_prices = {
        "DK": {"HOME": 2.10, "AWAY": 1.95},
        "FD": {"HOME": 2.02, "AWAY": 2.10},
    }
    out = os_mod.summarise_twoway(book_prices, "HOME", "AWAY", model_prob_a=0.55)
    assert out["best_a_book"] == "DK" and out["best_a_price"] == 2.10
    assert out["best_b_book"] == "FD" and out["best_b_price"] == 2.10
    assert out["arb_pct"] is not None and out["arb_pct"] > 0
    # No PM venues present -> PM fields are honestly None.
    assert out["pm_a_price"] is None and out["pm_b_price"] is None
