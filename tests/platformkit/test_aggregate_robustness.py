"""Per-file test: per-source isolation + cache-honest as_of in aggregate (LA-P0-c).

Proves:
  * a single venue (provider) RAISING does not abort the slate -- the other venues
    still merge, the dead one is recorded in `sources` with an error reason;
  * the slate-level as_of is the OLDEST event fetched-at (the true freshness floor),
    NOT now() -- so a slate built from a stale/cached source ages out honestly.

Offline: fake in-memory providers, no network.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_aggregate_robustness.py -q
"""
from __future__ import annotations

from scripts.platformkit.odds_provider import aggregate as agg
from scripts.platformkit.odds_provider.base import OddsEvent, unavailable


class _GoodProvider:
    name = "good"

    def __init__(self, as_of):
        self._as_of = as_of

    def fetch(self, sport):
        return [OddsEvent(
            event_id="G1", sport=sport, home="Knicks", away="Spurs",
            commence_time=None,
            prices={"espn:DK": {"home": 1.9, "away": 2.0}},
            source="good", as_of=self._as_of)]


class _RaisingProvider:
    name = "boom"

    def fetch(self, sport):
        raise RuntimeError("venue feed exploded")


class _UnavailableProvider:
    name = "down"

    def fetch(self, sport):
        return unavailable("down: maintenance")


class _HangingProvider:
    """A pathological source that hangs far longer than the slate deadline."""
    name = "hang"

    def __init__(self, seconds=30.0):
        self._seconds = seconds

    def fetch(self, sport):
        import time
        time.sleep(self._seconds)
        return []


def test_one_venue_raising_does_not_abort_the_others():
    out = agg.aggregate("nba", providers=[
        _RaisingProvider(), _GoodProvider("2026-06-18T23:00:00+00:00"),
        _UnavailableProvider()])
    # The slate is still OK because at least one venue is up.
    assert out["status"] == "ok"
    # The healthy venue's game survived the dead one.
    assert len(out["events"]) == 1
    assert out["events"][0]["event_id"] == "G1"
    # The dead venue is recorded honestly (error reason), not silently dropped.
    assert "error" in out["sources"]["boom"].lower()
    assert out["sources"]["good"] == "ok"
    assert out["sources"]["down"] == "down: maintenance"


def test_slate_as_of_is_oldest_event_not_now():
    older = "2026-06-18T20:00:00+00:00"
    newer = "2026-06-18T23:00:00+00:00"
    out = agg.aggregate("nba", providers=[
        _GoodProvider(newer), _GoodProvider(older)])
    # Both providers describe the SAME game (merged); the slate as_of must be the
    # OLDEST fetched-at -- the true freshness floor -- never re-stamped to now().
    assert out["as_of"] == older


def test_all_venues_down_is_unavailable_not_fabricated():
    out = agg.aggregate("nba", providers=[
        _RaisingProvider(), _UnavailableProvider()])
    assert out["status"] == "unavailable"
    assert out["events"] == []  # no fabricated lines from a dead slate


def test_hanging_source_is_bounded_by_the_deadline(monkeypatch):
    # A source that hangs 30s must NOT stall the slate: providers fetch concurrently
    # under a shared deadline, so the slate returns AT the deadline with the hung
    # source recorded as a timeout error and the healthy source's game intact.
    import time
    monkeypatch.setattr(agg, "_AGG_FETCH_DEADLINE_S", 1.0)
    t0 = time.monotonic()
    out = agg.aggregate("nba", providers=[
        _HangingProvider(30.0), _GoodProvider("2026-06-18T23:00:00+00:00")])
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0  # bounded by the 1s deadline, not the 30s hang
    assert out["status"] == "ok"
    assert len(out["events"]) == 1 and out["events"][0]["event_id"] == "G1"
    assert "error" in out["sources"]["hang"].lower()  # honest timeout, not silent drop
    assert out["sources"]["good"] == "ok"


def test_concurrent_fetch_preserves_provider_order_for_merge():
    # The merge's "first provider owns orientation" contract must survive concurrency:
    # provider A lists the game home=Knicks; provider B (flipped) lists home=Spurs.
    # Gathering in PROVIDER ORDER means A wins orientation -> merged home stays Knicks.
    from scripts.platformkit.odds_provider.base import OddsEvent

    class _Flipped:
        name = "flipped"

        def fetch(self, sport):
            return [OddsEvent(
                event_id="G1b", sport=sport, home="Spurs", away="Knicks",
                commence_time=None,
                prices={"fanduel": {"home": 2.1, "away": 1.8}}, source="flipped")]

    out = agg.aggregate("nba", providers=[
        _GoodProvider("2026-06-18T23:00:00+00:00"), _Flipped()])
    assert len(out["events"]) == 1
    assert out["events"][0]["home"] == "Knicks"  # first provider owns orientation
