"""Per-file test for bestbets.prop_cards_cache SLA window (offline, fixed clock).

Proves the widened SLA (1200 s = 4x the 300 s m13 cadence):
  * a HEALTHY-but-slightly-slow tick (cache aged a bit past the old 600 s, but
    inside one slow cadence+compute) reads FRESH -- the board is NOT zeroed;
  * a GENUINELY DEAD m13 (no write for many minutes, > SLA) still reads STALE with
    cards=[] -- stale-never-green preserved for a real outage;
  * a fresh write reads fresh; a missing cache reads unavailable.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_prop_cards_cache_sla.py -q
"""
from __future__ import annotations

from scripts.platformkit.bestbets import prop_cards_cache as cache

CADENCE = 300.0  # m13 writes every 300 s


def _cards(n=3):
    return [{"id": i, "model_only": True, "edge_claimed": False} for i in range(n)]


def test_default_sla_tolerates_one_slow_tick(tmp_path):
    path = tmp_path / "prop_cards_cache.json"
    t0 = 1_000_000.0
    assert cache.write(_cards(654 if False else 5), t0, path=path)

    # A slow-but-ALIVE tick: cache age = cadence + a long compute (well past the
    # OLD 600 s SLA) but inside the new 1200 s window. Must stay FRESH.
    slow_age = CADENCE + 500.0  # 800 s -- would have been STALE under 600 s
    assert slow_age > 600.0, "scenario must exceed the old SLA"
    env = cache.read(path=path, now_epoch=t0 + slow_age)
    assert env["status"] == "fresh", "healthy slow tick must not zero the board"
    assert env["card_count"] == 5 and env["cards"], "cards still served"


def test_dead_daemon_still_reads_stale(tmp_path):
    path = tmp_path / "prop_cards_cache.json"
    t0 = 2_000_000.0
    assert cache.write(_cards(5), t0, path=path)

    # m13 is DEAD: no write for ~5 missed cadences (well beyond the 1200 s SLA).
    dead_age = cache.DEFAULT_SLA_SEC + CADENCE  # 1500 s
    env = cache.read(path=path, now_epoch=t0 + dead_age)
    assert env["status"] == "stale", "a genuinely dead daemon must read stale"
    assert env["cards"] == [] and env["overall"] == "stale", "stale-never-green"
    assert env["card_count"] == 0


def test_sla_value_brackets_cadence_and_outage():
    # The SLA must comfortably exceed one cadence (tolerate a slow tick) yet stay
    # finite/bounded so a real outage is still caught within minutes.
    assert cache.DEFAULT_SLA_SEC >= 4 * CADENCE       # tolerates one slow cycle
    assert cache.DEFAULT_SLA_SEC <= 1800.0            # still catches a dead daemon


def test_fresh_and_unavailable(tmp_path):
    path = tmp_path / "prop_cards_cache.json"
    t0 = 3_000_000.0
    cache.write(_cards(2), t0, path=path)
    fresh = cache.read(path=path, now_epoch=t0 + 10.0)
    assert fresh["status"] == "fresh" and fresh["overall"] == "ok"

    missing = cache.read(path=tmp_path / "nope.json", now_epoch=t0)
    assert missing["status"] == "unavailable" and missing["cards"] == []
