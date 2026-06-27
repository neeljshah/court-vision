"""tests for scripts.platformkit.autonomy.status_composer -- ONE canonical status.

The composer must NEVER upgrade a severity: a stale feed is RED, a missing source
is DEGRADED (not absent-as-ok). Run ONLY this file:
    python -m pytest tests/platformkit/autonomy/test_status_composer.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.autonomy import status_composer as sc  # noqa: E402

NOW = 1_000_000.0


# --------------------------------------------------------------------------- #
# _degrade: the monotone-DOWN chokepoint -- proves the composer never upgrades.
# --------------------------------------------------------------------------- #
def test_degrade_is_monotone_down_only():
    assert sc._degrade(sc.OK, sc.DEGRADED) == sc.DEGRADED
    assert sc._degrade(sc.DEGRADED, sc.DOWN) == sc.DOWN
    # Worse current is never pulled back up by a better candidate.
    assert sc._degrade(sc.DOWN, sc.OK) == sc.DOWN
    assert sc._degrade(sc.DEGRADED, sc.OK) == sc.DEGRADED


def test_degrade_unknown_label_is_treated_as_degraded_not_ok():
    # A garbage severity can never be silently optimistic.
    assert sc._degrade(sc.OK, "wat") == sc.DEGRADED


# --------------------------------------------------------------------------- #
# _services_block: inherits health_aggregator._row_severity -> stale feed RED.
# --------------------------------------------------------------------------- #
def test_stale_feed_yields_degraded_not_green():
    """A row whose freshness verdict is 'stale' must NOT roll up to ok."""
    health_doc = {
        "overall": "ok",  # a naive aggregator might say ok; the composer must not.
        "services": [
            {"name": "line_daemon", "live": True, "fresh": "stale",
             "breaker": "CLOSED", "last_seen": None, "age_sec": 9999.0},
        ],
        "notes": [],
    }
    blk = sc._services_block(health_doc)
    assert blk["worst_row_severity"] == sc.DEGRADED
    assert blk["services"][0]["severity"] == sc.DEGRADED


def test_down_feed_yields_down_not_green():
    """A row whose freshness verdict is 'down' must roll up to down (RED)."""
    health_doc = {
        "overall": "ok",
        "services": [
            {"name": "inplay_history", "live": True, "fresh": "down",
             "breaker": "CLOSED", "last_seen": None, "age_sec": None},
        ],
        "notes": [],
    }
    blk = sc._services_block(health_doc)
    assert blk["worst_row_severity"] == sc.DOWN


# --------------------------------------------------------------------------- #
# compose(): overall is the WORST of health-overall + rows + loop liveness.
# A health 'ok' with a stale row must come out DEGRADED, never ok.
# --------------------------------------------------------------------------- #
def _patch_health(monkeypatch, doc):
    monkeypatch.setattr(sc._health, "aggregate", lambda **kw: dict(doc))


def test_compose_never_upgrades_a_stale_feed_to_ok(monkeypatch):
    doc = {
        "generated_at": "2026-06-19T00:00:00Z",
        "overall": "ok",
        "services": [
            {"name": "predict_service", "live": True, "fresh": "stale",
             "breaker": "CLOSED", "last_seen": None, "age_sec": 8000.0},
        ],
        "notes": [],
    }
    _patch_health(monkeypatch, doc)
    out = sc.compose(now=NOW)
    # The stale feed degrades the overall even though health said 'ok'.
    assert out["overall"] in (sc.DEGRADED, sc.DOWN)
    assert out["overall"] != sc.OK


def test_compose_missing_loop_service_is_degraded_not_absent_as_ok(monkeypatch):
    """No loop service in the snapshot -> loop liveness DEGRADED, not assumed ok."""
    doc = {
        "generated_at": "2026-06-19T00:00:00Z",
        "overall": "ok",
        "services": [
            {"name": "some_other_server", "live": None, "fresh": None,
             "breaker": None, "last_seen": None, "age_sec": None},
        ],
        "notes": [],
    }
    _patch_health(monkeypatch, doc)
    out = sc.compose(now=NOW)
    assert out["loop"]["liveness_missing"] is True
    assert out["loop"]["liveness_severity"] == sc.DEGRADED
    assert out["overall"] != sc.OK


def test_compose_down_critical_stays_down(monkeypatch):
    """A health 'down' can never be upgraded by the composer."""
    doc = {
        "generated_at": "2026-06-19T00:00:00Z",
        "overall": "down",
        "services": [
            {"name": "predict_service", "live": False, "fresh": None,
             "breaker": None, "last_seen": None, "age_sec": None},
        ],
        "notes": ["critical service predict_service is down"],
    }
    _patch_health(monkeypatch, doc)
    out = sc.compose(now=NOW)
    assert out["overall"] == sc.DOWN


def test_compose_health_raises_degrades_not_crashes(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("health exploded")
    monkeypatch.setattr(sc._health, "aggregate", _boom)
    out = sc.compose(now=NOW)
    # Must not raise; must not be ok.
    assert out["overall"] != sc.OK
    assert "services" in out and "loop" in out and "ratchet" in out


def test_compose_has_all_canonical_blocks(monkeypatch):
    doc = {"generated_at": "2026-06-19T00:00:00Z", "overall": "ok",
           "services": [], "notes": []}
    _patch_health(monkeypatch, doc)
    out = sc.compose(now=NOW)
    for key in ("overall", "services", "loop", "ratchet", "high_water",
                "idle_reason", "notes", "honest_note"):
        assert key in out, key


# --------------------------------------------------------------------------- #
# idle_reason: an explicit honest "idle because X", never a green blank.
# --------------------------------------------------------------------------- #
def test_idle_reason_explicit_when_no_new_games():
    loop = {"last_status": {"status": "no_new_games"}}
    reason = sc._idle_reason(loop, sc.OK)
    assert reason is not None and "no newly-settled" in reason


def test_idle_reason_none_when_down():
    # Down is not 'idle' -- the severity already tells the story.
    loop = {"last_status": {"status": "no_new_games"}}
    assert sc._idle_reason(loop, sc.DOWN) is None


def test_ratchet_block_missing_file_is_honest_idle_shell():
    # Point at a nonexistent ratchet ckpt -> IDLE shell, no fabricated SHIP.
    orig = sc._RATCHET_CKPT
    try:
        sc._RATCHET_CKPT = Path(str(orig) + ".does-not-exist")
        blk = sc._ratchet_block()
        assert blk["state"] == "IDLE"
        assert blk["n_ships"] == 0
        assert blk["present"] is False
    finally:
        sc._RATCHET_CKPT = orig
