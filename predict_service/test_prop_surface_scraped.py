"""Per-file tests for predict_service.prop_surface_scraped (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_prop_surface_scraped.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from predict_service.prop_surface_scraped import (
    build_scraped_props_response, read_scraped_snapshot, supported,
)


def _write_snapshot(tmp_path, sport: str, edges, generated_at=None):
    d = tmp_path / f"{sport}.json"
    d.write_text(json.dumps({
        "status": "ok",
        "generated_at": generated_at or datetime.now(tz=timezone.utc).isoformat(),
        "props": {"as_of": "2026-07-02", "edges": edges},
    }), encoding="ascii")
    return tmp_path


_EDGE = {"player": "Aaron Judge", "stat": "Home Runs", "line": 0.5,
         "model_p_over": 0.42, "model_lam": 0.38, "source": "underdog",
         "match": "BOS @ NYY", "team": "NYY", "confidence": "ok",
         "tier": "MODEL_VIEW", "as_of": "2026-07-02"}


def test_supported_sports():
    assert supported("mlb")
    assert supported("SOCCER_INTL")
    assert not supported("nba")
    assert not supported("cricket")


def test_unsupported_sport_returns_none():
    assert build_scraped_props_response("nba") is None


def test_missing_snapshot_returns_none(tmp_path):
    assert read_scraped_snapshot("mlb", out_dir=tmp_path) is None
    assert build_scraped_props_response("mlb", out_dir=tmp_path) is None


def test_happy_path_builds_rows(tmp_path):
    _write_snapshot(tmp_path, "mlb", [_EDGE])
    body = build_scraped_props_response("mlb", out_dir=tmp_path)
    assert body is not None
    assert body["status"] == "ok"
    assert body["count"] == 1
    assert body["source"] == "scraped_book_snapshot"
    row = body["rows"][0]
    assert row["player"] == "Aaron Judge"
    assert row["p_over"] == 0.42
    assert abs(row["p_under"] - 0.58) < 1e-9
    assert row["clv_is_proxy"] is True
    assert "edge_vs_market" not in row or row["edge_vs_market"] is None


def test_stale_snapshot_returns_none(tmp_path):
    old = "2020-01-01T00:00:00+00:00"
    _write_snapshot(tmp_path, "mlb", [_EDGE], generated_at=old)
    assert read_scraped_snapshot("mlb", out_dir=tmp_path) is None
    assert build_scraped_props_response("mlb", out_dir=tmp_path) is None


def test_empty_edges_returns_none(tmp_path):
    _write_snapshot(tmp_path, "mlb", [])
    assert build_scraped_props_response("mlb", out_dir=tmp_path) is None


def test_incomplete_edge_dropped_not_fabricated(tmp_path):
    bad = {"player": "", "stat": "Home Runs", "line": 0.5}  # missing player
    _write_snapshot(tmp_path, "mlb", [bad, _EDGE])
    body = build_scraped_props_response("mlb", out_dir=tmp_path)
    assert body["count"] == 1  # bad row silently dropped, never fabricated


def test_missing_model_p_over_never_fabricates_p_under(tmp_path):
    e = dict(_EDGE)
    del e["model_p_over"]
    _write_snapshot(tmp_path, "mlb", [e])
    body = build_scraped_props_response("mlb", out_dir=tmp_path)
    row = body["rows"][0]
    assert row["p_over"] is None
    assert row["p_under"] is None
