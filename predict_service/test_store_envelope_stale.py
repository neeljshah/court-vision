"""Per-file test for predict_service.store envelope stale-never-green guard.

Covers the ENVELOPE-LEVEL status demotion in read_latest: an on-disk 'ok'
snapshot whose games are ALL past-tipoff/final reads back as STALE_STATUS, while
a mixed/future snapshot stays 'ok' (the live slate is never broken).

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest predict_service/test_store_envelope_stale.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from predict_service import store
from predict_service.contracts import (
    GAME_STATE_POST,
    GAME_STATE_PRE,
    PredictionRecord,
    SnapshotEnvelope,
)

_NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def _env(sport, preds, status="ok"):
    return SnapshotEnvelope(
        sport=sport, generated_at=_iso(_NOW), status=status, predictions=preds)


def _pre_record(gid, tipoff):
    return PredictionRecord(sport="nba", game_id=gid, home="H", away="A",
                            tipoff=tipoff, game_state=GAME_STATE_PRE)


def _save_read(tmp_path, env):
    store.save(env, out_dir=tmp_path, append=False)
    return store.read_latest(env.sport, out_dir=tmp_path, now=_NOW)


def test_all_past_tipoff_demotes_ok_to_stale(tmp_path):
    # Two games, both tipoff days in the past -> all stale -> ok demoted to stale.
    past = _iso(_NOW - timedelta(days=6))
    preds = [_pre_record("g1", past), _pre_record("g2", past)]
    out = _save_read(str(tmp_path), _env("nba", preds, status="ok"))
    assert out.status == store.STALE_STATUS
    assert out.status != "ok"


def test_all_post_state_demotes_ok_to_stale(tmp_path):
    # game_state='post' (final) even with no tipoff -> stale.
    rec = PredictionRecord(sport="nba", game_id="g1", home="H", away="A",
                           tipoff=None, game_state=GAME_STATE_POST)
    out = _save_read(str(tmp_path), _env("nba", [rec], status="ok"))
    assert out.status == store.STALE_STATUS


def test_mixed_future_and_past_stays_ok(tmp_path):
    # One past, one upcoming -> NOT all stale -> stays ok (live slate preserved).
    past = _iso(_NOW - timedelta(days=6))
    future = _iso(_NOW + timedelta(hours=4))
    preds = [_pre_record("g1", past), _pre_record("g2", future)]
    out = _save_read(str(tmp_path), _env("nba", preds, status="ok"))
    assert out.status == "ok"


def test_all_future_stays_ok(tmp_path):
    future = _iso(_NOW + timedelta(hours=2))
    preds = [_pre_record("g1", future)]
    out = _save_read(str(tmp_path), _env("nba", preds, status="ok"))
    assert out.status == "ok"


def test_empty_predictions_untouched(tmp_path):
    # No predictions -> the envelope's own status governs (not demoted).
    out = _save_read(str(tmp_path), _env("nba", [], status="ok"))
    assert out.status == "ok"


def test_unavailable_not_demoted(tmp_path):
    # A missing file -> unavailable sentinel; demotion must not touch it.
    out = store.read_latest("nba", out_dir=str(tmp_path), now=_NOW)
    assert out.status == "unavailable"


def test_stale_status_never_green_via_heartbeat(tmp_path):
    # The scheduler reads env.status back as snapshot_status; an all-past snapshot
    # must surface as 'stale', never 'ok' (stale-never-green end to end).
    past = _iso(_NOW - timedelta(days=6))
    _save_read(str(tmp_path), _env("nba", [_pre_record("g1", past)], status="ok"))
    env = store.read_latest("nba", out_dir=str(tmp_path), now=_NOW)
    assert env.status == store.STALE_STATUS
