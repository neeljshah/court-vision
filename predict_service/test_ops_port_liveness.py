"""Per-file tests for predict_service.ops_port_liveness.

Run: python -m pytest predict_service/test_ops_port_liveness.py -q
(Per-file only -- a full suite freezes the box.)
"""
from __future__ import annotations

from datetime import datetime, timezone

from predict_service.ops_port_liveness import (
    _is_heartbeat_unresolved,
    _is_port_probed,
    apply_heartbeat_liveness,
    apply_port_liveness,
    build_sla_map,
)
from predict_service.status_freshness_normalizer import normalize_rows


def _open_prober(_h, _p, _t):  # noqa: ANN001, ANN202
    return True


def _closed_prober(_h, _p, _t):  # noqa: ANN001, ANN202
    return False


def test_is_port_probed_identifies_socket_governed_rows():
    assert _is_port_probed({"name": "m1_api_paper", "port": 8099, "live": None, "fresh": None})
    # Heartbeat rows (live already set, or a concrete fresh) are NOT port-probed.
    assert not _is_port_probed({"name": "m1_producer", "port": None, "live": True})
    assert not _is_port_probed({"name": "x", "port": 8099, "live": True})
    assert not _is_port_probed({"name": "x", "port": 8099, "live": None, "fresh": "stale"})
    assert not _is_port_probed({"name": "x", "port": 0, "live": None})


def test_open_socket_turns_port_probed_row_live_and_fresh():
    rows = [{"name": "m1_api_paper", "critical": True, "port": 8099,
             "live": None, "fresh": None, "fresh_sec": None}]
    stamp = "2026-06-22T22:00:00Z"
    out = apply_port_liveness(rows, prober=_open_prober, now_iso=stamp)
    assert out[0]["live"] is True
    assert out[0]["source_ts"] == stamp
    assert out[0]["age_sec"] == 0.0
    # Normalizer must now read it fresh+ok (real positive liveness signal). Pin
    # 'now' to the stamp so age==0 (in production source_ts IS now).
    now = datetime(2026, 6, 22, 22, 0, 0, tzinfo=timezone.utc)
    norm = normalize_rows(out, default_sla_sec=300.0, now=now)
    assert norm["overall"] == "ok"
    assert norm["rows"][0]["fresh"] == "fresh"
    assert norm["rows"][0]["ok"] is True


def test_closed_socket_is_red_never_green():
    rows = [{"name": "m1_ui", "critical": False, "port": 3000,
             "live": None, "fresh": None}]
    out = apply_port_liveness(rows, prober=_closed_prober)
    assert out[0]["live"] is False
    assert out[0]["fresh"] == "down"
    norm = normalize_rows(out, default_sla_sec=300.0)
    assert norm["overall"] == "down"  # a dead critical-or-not listener is never ok


def test_heartbeat_rows_pass_through_untouched():
    hb = {"name": "m1_producer", "port": None, "live": True,
          "age_sec": 412.0, "fresh_sec": 1500.0, "fresh": None}
    out = apply_port_liveness([hb], prober=_closed_prober)
    assert out[0] is hb  # identity: not copied, not probed


def test_build_sla_map_uses_declared_fresh_sec():
    rows = [
        {"name": "m1_producer", "fresh_sec": 1500.0},
        {"name": "m6_ingame_loop", "fresh_sec": 300.0},
        {"name": "m1_api_paper", "fresh_sec": None},  # omitted
        {"name": "bad", "fresh_sec": True},           # bool ignored
    ]
    sla = build_sla_map(rows)
    assert sla == {"m1_producer": 1500.0, "m6_ingame_loop": 300.0}


def test_producer_within_declared_window_reads_fresh_not_stale():
    # m1_producer ticks ~every 7 min; against a blanket 300s it false-stales,
    # against its declared 1500s window it is fresh.
    row = {"name": "m1_producer", "live": True, "age_sec": 412.0,
           "fresh_sec": 1500.0, "fresh": None, "port": None}
    blanket = normalize_rows([row], default_sla_sec=300.0)
    assert blanket["rows"][0]["fresh"] == "stale"
    declared = normalize_rows([row], default_sla_sec=300.0, sla_map=build_sla_map([row]))
    assert declared["rows"][0]["fresh"] == "fresh"
    assert declared["overall"] == "ok"


def test_apply_port_liveness_never_raises_on_garbage():
    rows = [None, {}, {"name": "x", "port": "nope", "live": None}, 42]
    # Should not raise; bad rows pass through.
    out = apply_port_liveness([r for r in rows if isinstance(r, dict)])
    assert isinstance(out, list)


# --------------------------------------------------------------------------- #
# Heartbeat-only daemon resolution (m1_bankroll, m5_autonomy_monitor, ...).
# --------------------------------------------------------------------------- #

def test_is_heartbeat_unresolved():
    assert _is_heartbeat_unresolved({"name": "m1_bankroll", "live": None, "fresh": None})
    assert not _is_heartbeat_unresolved({"name": "m1_api_paper", "port": 8099, "live": None})
    assert not _is_heartbeat_unresolved({"name": "x", "live": True})
    assert not _is_heartbeat_unresolved({"name": "x", "live": None, "fresh": "stale"})
    assert not _is_heartbeat_unresolved({"name": "", "live": None})


def _write_hb(tmp_path, name, age_sec):
    import os
    import time
    p = tmp_path / ("%s.txt" % name)
    p.write_text("2026-06-22T22:00:00Z", encoding="ascii")
    t = time.time() - age_sec
    os.utime(str(p), (t, t))
    return p


def test_fresh_heartbeat_resolves_daemon_live(tmp_path):
    _write_hb(tmp_path, "m1_bankroll", age_sec=60.0)
    rows = [{"name": "m1_bankroll", "critical": False, "port": None,
             "live": None, "fresh": None, "fresh_sec": 1500.0}]
    out = apply_heartbeat_liveness(rows, hb_dir=tmp_path)
    assert out[0]["live"] is True
    assert out[0]["age_sec"] < 1500.0
    norm = normalize_rows(out, default_sla_sec=300.0, sla_map=build_sla_map(out))
    assert norm["rows"][0]["fresh"] == "fresh"
    assert norm["overall"] == "ok"


def test_stale_heartbeat_stays_stale(tmp_path):
    # Heartbeat older than the declared window -> untouched -> normalizer marks stale.
    _write_hb(tmp_path, "m5_autonomy_monitor", age_sec=900.0)
    rows = [{"name": "m5_autonomy_monitor", "port": None,
             "live": None, "fresh": None, "fresh_sec": 300.0}]
    out = apply_heartbeat_liveness(rows, hb_dir=tmp_path)
    assert out[0].get("live") is None  # untouched
    norm = normalize_rows(out, default_sla_sec=300.0, sla_map=build_sla_map(out))
    assert norm["rows"][0]["fresh"] == "stale"


def test_absent_heartbeat_stays_stale(tmp_path):
    rows = [{"name": "m14_brain_rebuild", "port": None, "live": None, "fresh": None}]
    out = apply_heartbeat_liveness(rows, hb_dir=tmp_path)  # empty dir
    assert out[0].get("live") is None
    norm = normalize_rows(out, default_sla_sec=300.0)
    assert norm["rows"][0]["fresh"] == "stale"
