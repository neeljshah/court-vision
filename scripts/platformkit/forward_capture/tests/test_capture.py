"""Per-file test for forward_capture/capture.py -- the OddsFeed intake contract.

Asserts:
  - MockFeed is DETERMINISTIC (fixture captured_at -> byte-stable snapshots across two polls);
  - poll() validates (coerces price to float, enforces decimal>1, valid ISO captured_at);
  - a malformed quote (bad captured_at / non-decimal price / missing field) trips an assertion;
  - RealFeed.poll() RAISES NotImplementedError and references NO secret / makes NO live call;
  - has_real_feed()/build_feed() branch on env PRESENCE only (DRY RUN -> MockFeed by default).

Hermetic: stdlib + the local OddsSnapshot shim only. No network, no IO, no env mutation leak.
Run: python -m pytest scripts/platformkit/forward_capture/tests/test_capture.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# direct per-file import (sibling capture.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture as cap  # noqa: E402


_QUOTES = [
    {"book": "fd", "market": "ml", "sport": "nba", "game_id": "G1",
     "side": "home", "price": 1.91, "captured_at": "2026-01-15T17:00:00+00:00"},
    {"book": "fd", "market": "ml", "sport": "nba", "game_id": "G1",
     "side": "away", "price": 1.95, "captured_at": "2026-01-15T17:00:00+00:00"},
]


def test_mockfeed_is_deterministic_and_validates():
    feed = cap.MockFeed(_QUOTES)
    a = feed.poll()
    b = feed.poll()
    assert [s.as_dict() for s in a] == [s.as_dict() for s in b], "MockFeed must be deterministic"
    assert len(a) == 2
    first = a[0]
    assert isinstance(first.price, float) and first.price == 1.91
    assert first.captured_at == "2026-01-15T17:00:00+00:00"
    assert first.book == "fd" and first.side == "home"


def test_poll_coerces_string_price_to_float():
    feed = cap.MockFeed([{**_QUOTES[0], "price": "1.91"}])
    snap = feed.poll()[0]
    assert isinstance(snap.price, float) and snap.price == 1.91


def test_poll_defaults_captured_at_deterministically():
    q = {k: v for k, v in _QUOTES[0].items() if k != "captured_at"}
    feed = cap.MockFeed([q], default_captured_at="2026-02-02T12:00:00+00:00")
    assert feed.poll()[0].captured_at == "2026-02-02T12:00:00+00:00"


def test_poll_rejects_bad_captured_at():
    feed = cap.MockFeed([{**_QUOTES[0], "captured_at": "not-a-time"}])
    with pytest.raises(ValueError):
        feed.poll()


def test_poll_rejects_non_decimal_price():
    feed = cap.MockFeed([{**_QUOTES[0], "price": 0.5}])
    with pytest.raises(AssertionError):
        feed.poll()


def test_poll_rejects_missing_field():
    bad = {k: v for k, v in _QUOTES[0].items() if k != "game_id"}
    feed = cap.MockFeed([bad])
    with pytest.raises(KeyError):
        feed.poll()


def test_realfeed_stub_raises_and_holds_no_secret():
    feed = cap.RealFeed()
    with pytest.raises(NotImplementedError) as ei:
        feed.poll()
    msg = str(ei.value)
    # mentions the env var NAME (how to wire), never a key value
    assert cap.REAL_FEED_ENV in msg
    assert "HUMAN-RUN" in msg
    # no hardcoded secret-looking literal in the module source
    src = Path(cap.__file__).read_text(encoding="utf-8")
    assert "api_key=" not in src.replace("api_key_env", "")


def test_has_real_feed_and_build_feed_branch_on_presence(monkeypatch):
    monkeypatch.delenv(cap.REAL_FEED_ENV, raising=False)
    assert cap.has_real_feed() is False
    feed = cap.build_feed(_QUOTES)
    assert isinstance(feed, cap.MockFeed)
    assert len(feed.poll()) == 2  # DRY RUN path works end-to-end

    monkeypatch.setenv(cap.REAL_FEED_ENV, "PLACEHOLDER_NOT_USED")
    assert cap.has_real_feed() is True
    real = cap.build_feed(_QUOTES)
    assert isinstance(real, cap.RealFeed)
    assert real.configured is True
    with pytest.raises(NotImplementedError):
        real.poll()  # real key present but human has not wired the fetch -> still raises
