"""Per-file tests for feed_health (NETWORK-FREE -- all providers/mark injected)."""
from __future__ import annotations

from scripts.platformkit.odds_provider import feed_health as _feed_health
from scripts.platformkit.odds_provider.feed_health import (
    DEFAULT_SPORTS, GREEN, PROVIDER_HOSTS, RED, heal, probe_one, render, scan)


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


def test_scan_schema_drift_overlay_is_fail_open(monkeypatch):
    """schema_snapshot overlay is additive: a check_sport() failure must be
    swallowed (empty overlay for that sport), never sink scan()'s own verdict."""
    def _boom(sport):
        raise RuntimeError("corrupt snapshot file")

    monkeypatch.setattr(_feed_health, "_schema_check_sport", _boom)
    good = _FakeProvider("good", {"mlb": [1]})
    doc = scan(("mlb",), providers=[good])
    assert doc["schema_drift"] == {}
    assert doc["overall"] == GREEN


def test_render_includes_red_reasons():
    bad = _FakeProvider("bad", {"mlb": {"status": "unavailable", "reason": "boom (403)"}})
    doc = scan(("mlb",), providers=[bad])
    text = render(doc)
    assert "RED" in text
    assert "boom (403)" in text
    assert "OVERALL: RED" in text


def test_default_sports_widened_to_five():
    assert {"nba", "mlb", "soccer", "soccer_intl", "tennis"} <= set(DEFAULT_SPORTS)


def test_default_sports_widened_to_seven_incl_wnba_npb():
    """paper enablement sweep (LANE 5): wnba/npb added -- every provider degrades
    cleanly to an honest 'unsupported sport' GREEN for a sport it does not carry,
    so this can only ADD visibility, never flip an existing row RED."""
    assert set(DEFAULT_SPORTS) == {
        "nba", "mlb", "soccer", "soccer_intl", "tennis", "wnba", "npb"}


def test_scan_wnba_npb_unsupported_provider_is_green_not_red():
    prov = _FakeProvider("fanduel", {})  # no wnba/npb entry -> falls to default reason
    doc = scan(("wnba", "npb"), providers=[prov])
    assert doc["overall"] == GREEN
    assert doc["n_red"] == 0


def test_heal_marks_host_for_red_auth_reason():
    doc = {"rows": [
        {"provider": "pinnacle", "sport": "soccer_intl", "status": RED,
         "reason": "pinnacle matchups call failed (401)"},
    ]}
    marked = []
    heal(doc, mark=lambda host: marked.append(host))
    assert marked == [PROVIDER_HOSTS["pinnacle"]]


def test_heal_ignores_non_blocked_red_reason():
    doc = {"rows": [
        {"provider": "pinnacle", "sport": "mlb", "status": RED,
         "reason": "exception:TimeoutError"},
    ]}
    marked = []
    heal(doc, mark=lambda host: marked.append(host))
    assert marked == []


def test_heal_ignores_green_rows():
    doc = {"rows": [
        {"provider": "pinnacle", "sport": "mlb", "status": GREEN, "reason": None},
    ]}
    marked = []
    heal(doc, mark=lambda host: marked.append(host))
    assert marked == []


def test_heal_ignores_unknown_provider():
    doc = {"rows": [
        {"provider": "totally_unknown", "sport": "mlb", "status": RED,
         "reason": "403 forbidden"},
    ]}
    marked = []
    heal(doc, mark=lambda host: marked.append(host))
    assert marked == []


def test_heal_never_raises_when_mark_raises():
    doc = {"rows": [
        {"provider": "fanduel", "sport": "nba", "status": RED, "reason": "401 auth"},
    ]}

    def boom(host):
        raise RuntimeError("disk full")

    marked = heal(doc, mark=boom)
    assert marked == []


def test_heal_case_insensitive_reason_match():
    doc = {"rows": [
        {"provider": "kalshi", "sport": "nba", "status": RED,
         "reason": "Unauthorized: token expired"},
    ]}
    marked = []
    heal(doc, mark=lambda host: marked.append(host))
    assert marked == [PROVIDER_HOSTS["kalshi"]]
