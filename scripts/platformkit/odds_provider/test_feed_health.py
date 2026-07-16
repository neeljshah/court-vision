"""Per-file tests for feed_health (NETWORK-FREE -- all providers/mark injected)."""
from __future__ import annotations

from scripts.platformkit.odds_provider import feed_health as _feed_health
from scripts.platformkit.odds_provider.feed_health import (
    CAPTURE_ONLY_SPORTS, DEFAULT_SPORTS, GREEN, PROVIDER_HOSTS, RED, heal,
    probe_one, render, scan)


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


# --- Matrix row 13: npb capture-only structural degrade (2026-07-05) --------

def test_npb_is_in_capture_only_sports():
    assert "npb" in CAPTURE_ONLY_SPORTS


def test_kbo_not_yet_in_capture_only_sports():
    # kbo is not in DEFAULT_SPORTS (unscanned) as of this fix; do not blanket
    # it in without live confirmation of the same structural pattern.
    assert "kbo" not in CAPTURE_ONLY_SPORTS


def test_npb_pinnacle_structural_absence_is_green_capture_only():
    """The exact live reason string ('no live league ids') on npb -> GREEN,
    labeled capture_only_degrade, not a silent pass (row still appears)."""
    prov = _FakeProvider("pinnacle", {"npb": {
        "status": "unavailable",
        "reason": "pinnacle: no live league ids for 'npb'"}})
    row = probe_one(prov, "npb")
    assert row["status"] == GREEN
    assert row["capture_only_degrade"] is True
    assert row["sport"] == "npb"  # row still present, not deleted


def test_npb_real_auth_fault_still_red():
    """A genuine fault (auth/timeout/etc) on npb -- NOT the known structural
    'no live league ids' shape -- must still classify RED. This must not
    blanket-green the whole sport."""
    prov = _FakeProvider("pinnacle", {"npb": {
        "status": "unavailable",
        "reason": "pinnacle matchups call failed (HTTPError 401)"}})
    row = probe_one(prov, "npb")
    assert row["status"] == RED


def test_npb_timeout_fault_still_red():
    prov = _FakeProvider("pinnacle", {"npb": {
        "status": "unavailable",
        "reason": "exception:TimeoutError"}})
    row = probe_one(prov, "npb")
    assert row["status"] == RED


def test_same_reason_on_non_capture_only_sport_stays_red():
    """The 'no live league ids' shape is only benign for a sport actually in
    CAPTURE_ONLY_SPORTS -- the same reason on mlb (not capture-only) must
    still be RED, proving the exemption is sport-scoped, not global."""
    prov = _FakeProvider("pinnacle", {"mlb": {
        "status": "unavailable",
        "reason": "pinnacle: no live league ids for 'mlb'"}})
    row = probe_one(prov, "mlb")
    assert row["status"] == RED
    assert "capture_only_degrade" not in row


def test_scan_npb_structural_gap_does_not_flip_overall_red():
    """End-to-end: a scan where npb's ONLY red-shaped row is the known
    structural pinnacle gap, and every other provider/sport is healthy,
    reports overall GREEN (the aggregate no longer degrades for this)."""
    prov = _FakeProvider("pinnacle", {
        "npb": {"status": "unavailable",
                "reason": "pinnacle: no live league ids for 'npb'"},
        "mlb": [1, 2, 3],
    })
    doc = scan(("npb", "mlb"), providers=[prov])
    assert doc["overall"] == GREEN
    assert doc["n_red"] == 0
    npb_row = [r for r in doc["rows"] if r["sport"] == "npb"][0]
    assert npb_row["capture_only_degrade"] is True


def test_default_providers_governs_kalshi_only():
    """BUGFIX 2026-07-07: the real provider stack's KalshiProvider must come
    back governed (governor_caller='feed_health'), every other provider
    untouched -- proves the probe no longer hits Kalshi unpaced (the 429 root
    cause), without a real network call."""
    provs = _feed_health._default_providers()
    kalshi = [p for p in provs if getattr(p, "name", None) == "kalshi"]
    assert len(kalshi) == 1
    assert kalshi[0]._governor is not None
    assert kalshi[0]._governor._caller == "feed_health"
    others = [p for p in provs if getattr(p, "name", None) != "kalshi"]
    assert len(others) == len(provs) - 1


def test_scan_npb_real_fault_still_flips_overall_red():
    """A genuine npb fault (not the structural shape) must still surface as
    RED in the aggregate -- this fix must not silence real breakage."""
    prov = _FakeProvider("pinnacle", {
        "npb": {"status": "unavailable",
                "reason": "pinnacle matchups call failed (403 Forbidden)"},
    })
    doc = scan(("npb",), providers=[prov])
    assert doc["overall"] == RED
    assert doc["n_red"] == 1


# --------------------------------------------------------------------------- #
# schema-drift soft_red counter (2026-07-08): >=3 consecutive type_change
# drifts promote to soft_red WITHOUT flipping the top-level overall to RED.
# --------------------------------------------------------------------------- #
def _drift_note():
    return {"nba": {"pinnacle": {"status": "drift", "type_changes": ["a.b"],
                                 "missing_keys": [], "new_keys": []}}}


def test_promote_persistent_drift_soft_red_after_threshold(tmp_path):
    counter = tmp_path / "drift_counters.json"
    n1 = _feed_health.promote_persistent_drift(_drift_note(), counter_path=counter)
    assert n1["nba"]["pinnacle"]["status"] == "drift"
    n2 = _feed_health.promote_persistent_drift(_drift_note(), counter_path=counter)
    assert n2["nba"]["pinnacle"]["status"] == "drift"
    n3 = _feed_health.promote_persistent_drift(_drift_note(), counter_path=counter)
    assert n3["nba"]["pinnacle"]["status"] == _feed_health.SOFT_RED
    assert n3["nba"]["pinnacle"]["consecutive_type_change_drifts"] == 3


def test_promote_persistent_drift_resets_when_type_change_clears(tmp_path):
    counter = tmp_path / "drift_counters.json"
    _feed_health.promote_persistent_drift(_drift_note(), counter_path=counter)
    _feed_health.promote_persistent_drift(_drift_note(), counter_path=counter)
    # a drift with NO type_change (only missing_keys) resets the persistence counter
    cleared = {"nba": {"pinnacle": {"status": "drift", "type_changes": [],
                                    "missing_keys": ["x"], "new_keys": []}}}
    _feed_health.promote_persistent_drift(cleared, counter_path=counter)
    import json as _json
    counters = _json.loads(counter.read_text(encoding="ascii"))
    assert counters["nba|pinnacle"] == 0


def test_soft_red_is_distinct_from_red_never_flips_overall():
    # soft_red is its own token in the overlay only; scan()'s overall stays keyed on RED.
    assert _feed_health.SOFT_RED != _feed_health.RED


# --------------------------------------------------------------------------- #
# 429 rate-limit transient classification (fix lane F3, 2026-07-15): a live
# kalshi/pinnacle rate-limit blip must not read as a broken scraper.
# --------------------------------------------------------------------------- #

def test_probe_one_429_is_green_transient_not_red():
    prov = _FakeProvider("kalshi", {"mlb": {
        "status": "unavailable", "reason": "kalshi markets failed: HTTP Error 429"}})
    row = probe_one(prov, "mlb")
    assert row["status"] == GREEN
    assert row["transient_degrade"] is True


def test_probe_one_too_many_requests_is_green_transient():
    prov = _FakeProvider("pinnacle", {"soccer_intl": {
        "status": "unavailable", "reason": "pinnacle: too many requests"}})
    row = probe_one(prov, "soccer_intl")
    assert row["status"] == GREEN
    assert row["transient_degrade"] is True


def test_probe_one_real_auth_fault_not_tagged_transient():
    prov = _FakeProvider("pinnacle", {"soccer_intl": {
        "status": "unavailable", "reason": "pinnacle matchups call failed (401)"}})
    row = probe_one(prov, "soccer_intl")
    assert row["status"] == RED
    assert "transient_degrade" not in row


def test_scan_429_blip_does_not_flip_overall_red():
    prov = _FakeProvider("kalshi", {
        "mlb": {"status": "unavailable", "reason": "HTTP Error 429"},
        "nba": [1, 2],
    })
    doc = scan(("mlb", "nba"), providers=[prov])
    assert doc["overall"] == GREEN
    assert doc["n_red"] == 0
