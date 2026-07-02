"""Per-file tests for feed_health (NETWORK-FREE -- all providers injected)."""
from __future__ import annotations

from scripts.platformkit.odds_provider.feed_health import (
    GREEN, RED, probe_one, render, scan)


class _FakeProvider:
    def __init__(self, name, result_by_sport):
        self.name = name
        self._by_sport = result_by_sport

    def fetch(self, sport):
        return self._by_sport.get(sport, {"status": "unavailable",
                                          "reason": "unsupported sport '%s'" % sport})


class _RaisingProvider:
    name = "boom"

    def fetch(self, sport):
        raise RuntimeError("network down")


def test_probe_one_green_on_list_result():
    prov = _FakeProvider("pinnacle", {"mlb": [1, 2, 3]})
    row = probe_one(prov, "mlb")
    assert row == {"provider": "pinnacle", "sport": "mlb", "status": GREEN,
                   "reason": None, "n_events": 3}


def test_probe_one_green_on_empty_list():
    # An honestly empty slate (offseason / no games right now) is NOT a break.
    prov = _FakeProvider("pinnacle", {"mlb": []})
    row = probe_one(prov, "mlb")
    assert row["status"] == GREEN
    assert row["n_events"] == 0


def test_probe_one_green_on_benign_unavailable():
    prov = _FakeProvider("fanduel", {"mlb": {"status": "unavailable",
                                             "reason": "fanduel: unsupported sport 'mlb'"}})
    row = probe_one(prov, "mlb")
    assert row["status"] == GREEN


def test_probe_one_red_on_auth_error():
    prov = _FakeProvider("pinnacle", {"soccer_intl": {
        "status": "unavailable",
        "reason": "pinnacle matchups call failed (HTTPError)"}})
    row = probe_one(prov, "soccer_intl")
    assert row["status"] == RED
    assert "HTTPError" in row["reason"]


def test_probe_one_red_on_exception():
    row = probe_one(_RaisingProvider(), "mlb")
    assert row["status"] == RED
    assert row["reason"] == "exception:RuntimeError"
    assert row["n_events"] is None


def test_probe_one_red_on_unexpected_type():
    prov = _FakeProvider("weird", {"mlb": "not a list or dict"})
    row = probe_one(prov, "mlb")
    assert row["status"] == RED
    assert row["reason"] == "unexpected return type"


def test_scan_aggregates_by_provider_and_overall():
    good = _FakeProvider("good", {"mlb": [1], "soccer_intl": [1, 2]})
    bad = _FakeProvider("bad", {"mlb": {"status": "unavailable", "reason": "boom (403)"},
                                "soccer_intl": [1]})
    doc = scan(("mlb", "soccer_intl"), providers=[good, bad])
    assert doc["n_probed"] == 4
    assert doc["n_red"] == 1
    assert doc["overall"] == RED
    assert doc["by_provider"]["good"] == {"green": 2, "red": 0}
    assert doc["by_provider"]["bad"] == {"green": 1, "red": 1}


def test_scan_all_green_overall_green():
    good = _FakeProvider("good", {"mlb": []})
    doc = scan(("mlb",), providers=[good])
    assert doc["overall"] == GREEN
    assert doc["n_red"] == 0


def test_scan_never_raises_on_provider_exception():
    doc = scan(("mlb",), providers=[_RaisingProvider()])
    assert doc["overall"] == RED
    assert doc["rows"][0]["reason"] == "exception:RuntimeError"


def test_render_includes_red_reasons():
    bad = _FakeProvider("bad", {"mlb": {"status": "unavailable", "reason": "boom (403)"}})
    doc = scan(("mlb",), providers=[bad])
    text = render(doc)
    assert "RED" in text
    assert "boom (403)" in text
    assert "OVERALL: RED" in text
