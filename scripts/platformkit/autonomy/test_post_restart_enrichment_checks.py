"""Per-file tests for post_restart_enrichment_checks (LANE 5, waves 11-13).

Everything is fake/injected -- NO real network call, NO real PID/socket, NO
real filesystem outside tmp_path (module-level path constants monkeypatched to
tmp_path via setattr, never the real repo data/ tree).

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_post_restart_enrichment_checks.py -q
"""
from __future__ import annotations

import json

import scripts.platformkit.autonomy.post_restart_checks as checks
import scripts.platformkit.autonomy.post_restart_enrichment_checks as enrich


# --------------------------------------------------------------------------- #
# (h) m37 artifact dirs
# --------------------------------------------------------------------------- #
def test_m37_no_live_game_is_all_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich, "_FOTMOB_DIR", tmp_path / "fotmob")
    monkeypatch.setattr(enrich, "_GUMBO_DIR", tmp_path / "gumbo")
    monkeypatch.setattr(enrich, "_BOOK_DEPTH", tmp_path / "book_depth")
    rows = enrich.check_m37_artifact_dirs(1000.0, live_game_fn=lambda s: False)
    assert len(rows) == 3
    assert all(r["status"] == checks.PENDING for r in rows)


def test_m37_fotmob_live_no_dir_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich, "_FOTMOB_DIR", tmp_path / "missing_fotmob")
    monkeypatch.setattr(enrich, "_GUMBO_DIR", tmp_path / "gumbo")
    monkeypatch.setattr(enrich, "_BOOK_DEPTH", tmp_path / "book_depth")
    rows = enrich.check_m37_artifact_dirs(
        1000.0, live_game_fn=lambda s: s == "soccer_intl")
    by_name = {r["name"]: r for r in rows}
    assert by_name["m37_fotmob_live"]["status"] == checks.FAIL
    assert by_name["m37_gumbo_live"]["status"] == checks.PENDING
    assert by_name["m37_book_depth"]["status"] == checks.PENDING


def test_m37_fotmob_live_fresh_row_is_pass(tmp_path, monkeypatch):
    fotmob_dir = tmp_path / "fotmob"
    fotmob_dir.mkdir()
    tick = fotmob_dir / "12345.jsonl"
    tick.write_text('{"x":1}\n', encoding="ascii")
    monkeypatch.setattr(enrich, "_FOTMOB_DIR", fotmob_dir)
    monkeypatch.setattr(enrich, "_GUMBO_DIR", tmp_path / "gumbo")
    monkeypatch.setattr(enrich, "_BOOK_DEPTH", tmp_path / "book_depth")
    now = tick.stat().st_mtime + 5.0
    rows = enrich.check_m37_artifact_dirs(now, live_game_fn=lambda s: s == "soccer_intl")
    by_name = {r["name"]: r for r in rows}
    assert by_name["m37_fotmob_live"]["status"] == checks.PASS


def test_m37_gumbo_live_stale_row_is_fail(tmp_path, monkeypatch):
    gumbo_dir = tmp_path / "gumbo"
    gumbo_dir.mkdir()
    tick = gumbo_dir / "823120.jsonl"
    tick.write_text('{"x":1}\n', encoding="ascii")
    monkeypatch.setattr(enrich, "_FOTMOB_DIR", tmp_path / "fotmob")
    monkeypatch.setattr(enrich, "_GUMBO_DIR", gumbo_dir)
    monkeypatch.setattr(enrich, "_BOOK_DEPTH", tmp_path / "book_depth")
    now = tick.stat().st_mtime + 5000.0
    rows = enrich.check_m37_artifact_dirs(now, live_game_fn=lambda s: s == "mlb",
                                          fresh_sec=1800.0)
    by_name = {r["name"]: r for r in rows}
    assert by_name["m37_gumbo_live"]["status"] == checks.FAIL


def test_m37_book_depth_gates_on_either_mlb_or_wnba(tmp_path, monkeypatch):
    bd_dir = tmp_path / "book_depth"
    venue_dir = bd_dir / "kalshi"
    venue_dir.mkdir(parents=True)
    tick = venue_dir / "2026-07-04.jsonl"
    tick.write_text('{"x":1}\n', encoding="ascii")
    monkeypatch.setattr(enrich, "_FOTMOB_DIR", tmp_path / "fotmob")
    monkeypatch.setattr(enrich, "_GUMBO_DIR", tmp_path / "gumbo")
    monkeypatch.setattr(enrich, "_BOOK_DEPTH", bd_dir)
    now = tick.stat().st_mtime + 5.0
    rows = enrich.check_m37_artifact_dirs(now, live_game_fn=lambda s: s == "wnba")
    by_name = {r["name"]: r for r in rows}
    assert by_name["m37_book_depth"]["status"] == checks.PASS


def test_m37_live_game_lookup_raises_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich, "_FOTMOB_DIR", tmp_path / "fotmob")
    monkeypatch.setattr(enrich, "_GUMBO_DIR", tmp_path / "gumbo")
    monkeypatch.setattr(enrich, "_BOOK_DEPTH", tmp_path / "book_depth")

    def _raise(_sport):
        raise RuntimeError("espn down")

    rows = enrich.check_m37_artifact_dirs(1000.0, live_game_fn=_raise)
    assert all(r["status"] == checks.PENDING for r in rows)


# --------------------------------------------------------------------------- #
# (i) enrichment tick fields
# --------------------------------------------------------------------------- #
def test_enrichment_fields_no_live_game_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich, "_LINE_HIST", tmp_path)
    row = enrich.check_enrichment_tick_fields(1000.0, live_game_fn=lambda s: False)
    assert row["status"] == checks.PENDING


def test_enrichment_fields_live_no_tick_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich, "_LINE_HIST", tmp_path)
    row = enrich.check_enrichment_tick_fields(1000.0, live_game_fn=lambda s: True)
    assert row["status"] == checks.PENDING


def test_enrichment_fields_fresh_tick_all_keys_present_is_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich, "_LINE_HIST", tmp_path)
    sport_dir = tmp_path / "mlb"
    sport_dir.mkdir()
    doc = {k: None for k in enrich.ENRICHMENT_KEYS}
    doc["extra"] = "ok"
    tick = sport_dir / "2026-07-04.jsonl"
    tick.write_text(json.dumps(doc) + "\n", encoding="ascii")
    now = tick.stat().st_mtime + 5.0
    row = enrich.check_enrichment_tick_fields(now, live_game_fn=lambda s: True, sport="mlb")
    assert row["status"] == checks.PASS


def test_enrichment_fields_missing_key_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich, "_LINE_HIST", tmp_path)
    sport_dir = tmp_path / "mlb"
    sport_dir.mkdir()
    doc = {k: None for k in enrich.ENRICHMENT_KEYS if k != "espn_wp"}
    tick = sport_dir / "2026-07-04.jsonl"
    tick.write_text(json.dumps(doc) + "\n", encoding="ascii")
    now = tick.stat().st_mtime + 5.0
    row = enrich.check_enrichment_tick_fields(now, live_game_fn=lambda s: True, sport="mlb")
    assert row["status"] == checks.FAIL
    assert "espn_wp" in row["missing"]


# --------------------------------------------------------------------------- #
# (j) espn_event_id (mlb)
# --------------------------------------------------------------------------- #
def test_espn_event_id_no_live_game_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich, "_LINE_HIST", tmp_path)
    row = enrich.check_espn_event_id_mlb(1000.0, live_game_fn=lambda s: False)
    assert row["status"] == checks.PENDING


def test_espn_event_id_present_is_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich, "_LINE_HIST", tmp_path)
    sport_dir = tmp_path / "mlb"
    sport_dir.mkdir()
    tick = sport_dir / "2026-07-04.jsonl"
    tick.write_text(json.dumps({"espn_event_id": "401700001"}) + "\n", encoding="ascii")
    now = tick.stat().st_mtime + 5.0
    row = enrich.check_espn_event_id_mlb(now, live_game_fn=lambda s: True)
    assert row["status"] == checks.PASS


def test_espn_event_id_missing_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich, "_LINE_HIST", tmp_path)
    sport_dir = tmp_path / "mlb"
    sport_dir.mkdir()
    tick = sport_dir / "2026-07-04.jsonl"
    tick.write_text(json.dumps({"espn_event_id": None}) + "\n", encoding="ascii")
    now = tick.stat().st_mtime + 5.0
    row = enrich.check_espn_event_id_mlb(now, live_game_fn=lambda s: True)
    assert row["status"] == checks.FAIL


def test_espn_event_id_lookup_raises_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich, "_LINE_HIST", tmp_path)

    def _raise(_sport):
        raise RuntimeError("espn down")

    row = enrich.check_espn_event_id_mlb(1000.0, live_game_fn=_raise)
    assert row["status"] == checks.PENDING
