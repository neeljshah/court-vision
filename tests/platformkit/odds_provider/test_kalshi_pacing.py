"""Per-file test for odds_provider.kalshi_pacing (pure helpers, no network).

Covers: 429 detection (HTTPError code 429 vs other errors), Retry-After parsing,
stats counters (None-safe, in-place mutation), inter-request stagger (skips the
first call, sleeps via the injected clock otherwise), and the 429 cool-down
(honors Retry-After when present, capped at MAX_429_COOLDOWN_SEC otherwise).

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi_pacing.py -q
"""
from __future__ import annotations

import urllib.error

from scripts.platformkit.odds_provider import kalshi_pacing as kp


def _http_error(code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://x", code=code, msg="err", hdrs=headers or {}, fp=None)


# --------------------------------------------------------------------------------------- #
# is_429                                                                                   #
# --------------------------------------------------------------------------------------- #
def test_is_429_true_for_http_429():
    assert kp.is_429(_http_error(429)) is True


def test_is_429_false_for_other_http_codes():
    assert kp.is_429(_http_error(503)) is False
    assert kp.is_429(_http_error(500)) is False
    assert kp.is_429(_http_error(404)) is False


def test_is_429_false_for_non_http_errors():
    assert kp.is_429(RuntimeError("network down")) is False
    assert kp.is_429(TimeoutError("timeout")) is False
    assert kp.is_429(ValueError("bad json")) is False


# --------------------------------------------------------------------------------------- #
# retry_after_sec                                                                          #
# --------------------------------------------------------------------------------------- #
def test_retry_after_sec_parses_header():
    exc = _http_error(429, headers={"Retry-After": "5"})
    assert kp.retry_after_sec(exc) == 5.0


def test_retry_after_sec_none_when_absent():
    exc = _http_error(429, headers={})
    assert kp.retry_after_sec(exc) is None


def test_retry_after_sec_none_on_unparseable_value():
    exc = _http_error(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
    assert kp.retry_after_sec(exc) is None


def test_retry_after_sec_none_for_non_http_error():
    assert kp.retry_after_sec(RuntimeError("boom")) is None


# --------------------------------------------------------------------------------------- #
# record_request / record_429 -- None-safe in-place counters                               #
# --------------------------------------------------------------------------------------- #
def test_record_request_increments_and_is_none_safe():
    stats: dict = {}
    kp.record_request(stats)
    kp.record_request(stats)
    assert stats["n_requests"] == 2
    kp.record_request(None)  # must never raise


def test_record_429_increments_and_is_none_safe():
    stats: dict = {}
    kp.record_429(stats)
    assert stats["n_429"] == 1
    kp.record_429(None)  # must never raise


def test_record_request_and_429_independent_keys():
    stats: dict = {}
    kp.record_request(stats)
    kp.record_request(stats)
    kp.record_429(stats)
    assert stats == {"n_requests": 2, "n_429": 1}


# --------------------------------------------------------------------------------------- #
# stagger_sleep -- skips the first call in a batch, sleeps otherwise                        #
# --------------------------------------------------------------------------------------- #
def test_stagger_sleep_skips_first_request():
    sleeps = []
    kp.stagger_sleep(sleeps.append, 0.3, is_first=True)
    assert sleeps == []


def test_stagger_sleep_sleeps_for_non_first_request():
    sleeps = []
    kp.stagger_sleep(sleeps.append, 0.3, is_first=False)
    assert sleeps == [0.3]


def test_stagger_sleep_zero_stagger_is_noop():
    sleeps = []
    kp.stagger_sleep(sleeps.append, 0.0, is_first=False)
    assert sleeps == []


def test_stagger_sleep_never_raises_on_broken_clock():
    def _boom(_):
        raise RuntimeError("clock broken")

    kp.stagger_sleep(_boom, 0.3, is_first=False)  # must not raise


# --------------------------------------------------------------------------------------- #
# cooldown_after_429 -- honors Retry-After, capped, never raises                            #
# --------------------------------------------------------------------------------------- #
def test_cooldown_after_429_uses_retry_after_when_under_cap():
    sleeps = []
    exc = _http_error(429, headers={"Retry-After": "1"})
    kp.cooldown_after_429(exc, sleeps.append, max_cooldown_sec=2.0)
    assert sleeps == [1.0]


def test_cooldown_after_429_caps_retry_after_above_max():
    sleeps = []
    exc = _http_error(429, headers={"Retry-After": "30"})
    kp.cooldown_after_429(exc, sleeps.append, max_cooldown_sec=2.0)
    assert sleeps == [2.0]


def test_cooldown_after_429_falls_back_to_cap_when_absent():
    sleeps = []
    exc = _http_error(429, headers={})
    kp.cooldown_after_429(exc, sleeps.append, max_cooldown_sec=2.0)
    assert sleeps == [2.0]


def test_cooldown_after_429_never_raises_on_broken_clock():
    def _boom(_):
        raise RuntimeError("clock broken")

    exc = _http_error(429, headers={})
    kp.cooldown_after_429(exc, _boom)  # must not raise


# --------------------------------------------------------------------------------------- #
# module constants sanity (cadence-fit math the wave prompt asked to document)              #
# --------------------------------------------------------------------------------------- #
def test_worst_case_stagger_for_full_six_sport_cycle_fits_cadence():
    # 17 series total (mlb4+soccer_intl3+tennis2+wnba3+npb2+kbo3) x REQUEST_STAGGER_SEC,
    # staggers are BETWEEN requests only (16 gaps, not 17) -- must stay well under the
    # capture loop's LIVE_INTERVAL_SEC=20s cadence even in the worst case (no 429s).
    n_series_total = 17
    worst_case_stagger_sec = (n_series_total - 1) * kp.REQUEST_STAGGER_SEC
    assert worst_case_stagger_sec < 20.0
