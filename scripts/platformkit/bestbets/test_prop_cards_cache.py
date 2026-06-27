"""Per-file test for scripts.platformkit.bestbets.prop_cards_cache.

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/bestbets/test_prop_cards_cache.py -q
"""
from __future__ import annotations

import json

import scripts.platformkit.bestbets.prop_cards_cache as cache


def _card(sport="mlb", model_only=True):
    return {
        "game_id": "", "matchup": "A vs B", "sport": sport,
        "market_type": "prop", "prop_player": "P", "prop_stat": "PTS",
        "line": 1.5, "side": "over", "model_prob": 0.6, "proj": 2.0,
        "market_prob": None if model_only else 0.55,
        "edge_vs_market": None if model_only else 0.05,
        "units": 1.0, "model_only": model_only,
        "edge_claimed": not model_only, "status": "pregame",
    }


def test_write_then_fresh_read(tmp_path):
    p = tmp_path / "c.json"
    assert cache.write([_card()], 1000.0, n_more_model_only={"mlb": 9}, path=p)
    env = cache.read(path=p, now_epoch=1010.0, sla_sec=600.0)
    assert env["status"] == "fresh"
    assert env["overall"] == "ok"
    assert env["card_count"] == 1
    assert env["n_more_model_only"] == {"mlb": 9}
    assert env["cards"][0]["sport"] == "mlb"


def test_stale_read_omits_cards_never_green(tmp_path):
    p = tmp_path / "c.json"
    cache.write([_card()], 1000.0, path=p)
    # now is far past the SLA -> stale, no cards, overall must NOT be ok.
    env = cache.read(path=p, now_epoch=1000.0 + 9999.0, sla_sec=600.0)
    assert env["status"] == "stale"
    assert env["overall"] != "ok"
    assert env["cards"] == []
    assert env["card_count"] == 0
    assert env["stale_note"]


def test_future_stamped_cache_reads_stale_not_fresh(tmp_path):
    """A cache stamped in the FUTURE (clock skew / corruption -> negative age) must
    read STALE, never green. Fail-CLOSED, mirroring odds_provider.freshness."""
    p = tmp_path / "c.json"
    # generated_at is far AHEAD of now_epoch -> age is very negative.
    cache.write([_card()], 1_000_000.0, path=p)
    env = cache.read(path=p, now_epoch=1000.0, sla_sec=600.0)
    assert env["status"] == "stale"
    assert env["overall"] != "ok"
    assert env["cards"] == []
    assert env["card_count"] == 0
    assert "future" in env["stale_note"].lower()


def test_mild_future_skew_within_tolerance_stays_fresh(tmp_path):
    """A generated_at only slightly ahead (benign box clock offset, within the skew
    tolerance) must NOT flip a healthy cache to stale."""
    p = tmp_path / "c.json"
    skew = cache.FUTURE_SKEW_TOLERANCE_SEC / 2.0
    cache.write([_card()], 1000.0 + skew, path=p)
    env = cache.read(path=p, now_epoch=1000.0, sla_sec=600.0)
    assert env["status"] == "fresh"
    assert env["overall"] == "ok"
    assert env["card_count"] == 1


def test_missing_cache_unavailable(tmp_path):
    env = cache.read(path=tmp_path / "nope.json", now_epoch=1.0)
    assert env["status"] == "unavailable"
    assert env["overall"] != "ok"
    assert env["cards"] == []


def test_corrupt_cache_unavailable(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not json", encoding="ascii")
    env = cache.read(path=p, now_epoch=1.0)
    assert env["status"] == "unavailable"
    assert env["cards"] == []


def test_no_generated_at_unavailable(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"cards": [_card()]}), encoding="ascii")
    env = cache.read(path=p, now_epoch=1.0)
    assert env["status"] == "unavailable"


def test_empty_write_is_unavailable_envelope(tmp_path):
    p = tmp_path / "c.json"
    assert cache.write([], 5.0, path=p)
    doc = json.loads(p.read_text(encoding="ascii"))
    assert doc["overall"] == "UNAVAILABLE"
    assert doc["card_count"] == 0
    # read of an empty-but-fresh cache: fresh status but no cards -> not green.
    env = cache.read(path=p, now_epoch=6.0)
    assert env["cards"] == []
    assert env["overall"] != "ok"


def test_no_dollar_fields(tmp_path):
    p = tmp_path / "c.json"
    cache.write([_card(model_only=False)], 1.0, path=p)
    raw = p.read_text(encoding="ascii")
    for banned in ("dollar_pnl", "pnl_usd", '"usd"', '"pnl"', '"roi"'):
        assert banned not in raw


def test_atomic_write_returns_true(tmp_path):
    assert cache.write([_card()], 1.0, path=tmp_path / "c.json") is True


def test_default_path_under_data_frontend():
    p = cache.default_path()
    assert p.name == "prop_cards_cache.json"
    assert "frontend" in str(p)


# ---------------------------------------------------------------------------
# Last-good prop-LINE snapshot (429 resilience)
# ---------------------------------------------------------------------------

def _patch_line_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_LINE_CACHE_DIR", tmp_path / "lines")


def test_line_cache_roundtrip(monkeypatch, tmp_path):
    from scripts.platformkit.odds_provider.prop_base import PropLine
    _patch_line_dir(monkeypatch, tmp_path)
    ln = PropLine(sport="mlb", event_id="e1", match="A vs B", player="P",
                  team="A", stat="Hits", line=1.5, over_price=1.9,
                  under_price=1.9, payout_type="sportsbook", source="ud")
    cache.line_cache_write("mlb", [ln])
    out = cache.line_cache_read("mlb", ttl_sec=1e9)
    assert out is not None and len(out) == 1
    assert out[0].player == "P" and out[0].stat == "Hits"
    assert out[0].over_price == 1.9  # priced line rehydrated as a BONUS


def test_line_cache_ttl_expiry(monkeypatch, tmp_path):
    from scripts.platformkit.odds_provider.prop_base import PropLine
    _patch_line_dir(monkeypatch, tmp_path)
    ln = PropLine(sport="mlb", event_id="e", match="m", player="P", team="A",
                  stat="Hits", line=1.5)
    cache.line_cache_write("mlb", [ln])
    # ttl 0 -> any age exceeds it -> None (a feed outage cannot serve forever).
    assert cache.line_cache_read("mlb", ttl_sec=0.0) is None


def test_line_cache_missing_returns_none(monkeypatch, tmp_path):
    _patch_line_dir(monkeypatch, tmp_path)
    assert cache.line_cache_read("soccer_intl") is None


def test_line_cache_write_empty_is_noop(monkeypatch, tmp_path):
    _patch_line_dir(monkeypatch, tmp_path)
    cache.line_cache_write("mlb", [])  # never raises, writes nothing
    assert cache.line_cache_read("mlb", ttl_sec=1e9) is None
