"""Per-file test for scripts.platformkit.bestbets.prop_cards_sport_parallel.

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/bestbets/test_prop_cards_sport_parallel.py -q
"""
from __future__ import annotations

import threading
import time

import scripts.platformkit.bestbets.prop_cards_sport_parallel as spar


def test_empty_sports_returns_empty():
    cards, errors, secs = spar.run_sports_parallel((), lambda s: [{"sport": s}])
    assert cards == [] and errors == {} and secs == {}


def test_single_sport_skips_pool_but_still_works():
    cards, errors, secs = spar.run_sports_parallel(
        ("mlb",), lambda s: [{"sport": s, "n": 1}])
    assert cards == [{"sport": "mlb", "n": 1}]
    assert errors == {}
    assert "mlb" in secs


def test_deterministic_order_matches_sequential_regardless_of_finish_order():
    # soccer_intl sleeps LONGER than mlb, so if assembly used completion order
    # mlb would land first -- but the caller's fixed order is (soccer_intl, mlb).
    def build_one(sport):
        if sport == "soccer_intl":
            time.sleep(0.15)
        else:
            time.sleep(0.01)
        return [{"sport": sport, "player": "P-%s" % sport}]

    cards, errors, secs = spar.run_sports_parallel(("soccer_intl", "mlb"), build_one)
    assert errors == {}
    assert [c["sport"] for c in cards] == ["soccer_intl", "mlb"]  # fixed order, not completion
    assert set(secs.keys()) == {"soccer_intl", "mlb"}


def test_matches_sequential_output_for_same_inputs():
    # Race-audit requirement: two sports scored concurrently must produce
    # IDENTICAL output to a sequential build for the same inputs.
    def build_one(sport):
        time.sleep(0.02)
        return [{"sport": sport, "player": "A"}, {"sport": sport, "player": "B"}]

    sports = ("soccer_intl", "mlb")
    parallel_cards, errors, _ = spar.run_sports_parallel(sports, build_one)
    sequential_cards = []
    for sport in sports:
        sequential_cards.extend(build_one(sport))
    assert errors == {}
    assert parallel_cards == sequential_cards


def test_one_sport_raising_does_not_kill_the_cycle():
    def build_one(sport):
        if sport == "mlb":
            raise RuntimeError("boom")
        return [{"sport": sport, "player": "OK"}]

    cards, errors, secs = spar.run_sports_parallel(("soccer_intl", "mlb"), build_one)
    assert cards == [{"sport": "soccer_intl", "player": "OK"}]  # mlb contributes nothing
    assert "mlb" in errors
    assert "SCORE_ERROR" in errors["mlb"]
    assert "soccer_intl" not in errors  # only the failing sport is recorded
    assert set(secs.keys()) == {"soccer_intl", "mlb"}  # timing recorded even on failure


def test_never_raises_when_build_one_always_raises():
    def boom(sport):
        raise ValueError("always fails: %s" % sport)

    cards, errors, secs = spar.run_sports_parallel(("soccer_intl", "mlb"), boom)
    assert cards == []
    assert set(errors.keys()) == {"soccer_intl", "mlb"}
    for msg in errors.values():
        assert "SCORE_ERROR" in msg


def test_concurrent_execution_actually_overlaps_in_time():
    # Proves this is genuinely concurrent (not a disguised sequential loop):
    # two 0.2s sleeps in parallel should finish well under their 0.4s sum.
    def build_one(sport):
        time.sleep(0.2)
        return [{"sport": sport}]

    t0 = time.time()
    cards, errors, _ = spar.run_sports_parallel(("soccer_intl", "mlb"), build_one)
    elapsed = time.time() - t0
    assert errors == {}
    assert len(cards) == 2
    assert elapsed < 0.35  # comfortably below the 0.4s sequential sum


def test_no_cross_sport_dict_key_corruption_under_concurrency():
    # Each sport writes into a shared dict via a DIFFERENT key (mirrors the
    # _LAST_CIRCUIT_SKIPS / per_sport_seconds pattern audited in the module
    # docstring) -- concurrent per-key writes must never corrupt sibling keys.
    many_sports = tuple("sport_%d" % i for i in range(20))

    def build_one(sport):
        time.sleep(0.01)
        return [{"sport": sport, "marker": sport}]

    cards, errors, secs = spar.run_sports_parallel(many_sports, build_one)
    assert errors == {}
    assert [c["sport"] for c in cards] == list(many_sports)  # fixed order preserved
    assert all(c["marker"] == c["sport"] for c in cards)  # no cross-sport bleed
    assert set(secs.keys()) == set(many_sports)


def test_record_and_read_last_cycle_metadata():
    spar.record_last_cycle({"mlb": "SCORE_ERROR: boom"}, {"mlb": 1.23, "soccer_intl": 4.56})
    assert spar.last_sport_errors() == {"mlb": "SCORE_ERROR: boom"}
    assert spar.last_sport_seconds() == {"mlb": 1.23, "soccer_intl": 4.56}
    # A later clean cycle overwrites (not merges with) the previous one.
    spar.record_last_cycle({}, {"mlb": 0.5})
    assert spar.last_sport_errors() == {}
    assert spar.last_sport_seconds() == {"mlb": 0.5}


def test_record_last_cycle_never_raises_on_bad_input():
    spar.record_last_cycle(None, None)  # type: ignore[arg-type]
    assert spar.last_sport_errors() == {}
    assert spar.last_sport_seconds() == {}
