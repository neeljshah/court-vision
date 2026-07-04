"""Per-file tests for tick_segment_backfill (offline; injected http_get + tmp dirs)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.platformkit.ingame import tick_segment_backfill as tsb


def _ev(eid, home, away, date, status="STATUS_FULL_TIME", completed=True):
    return {
        "id": eid, "date": date,
        "competitions": [{
            "status": {"type": {"name": status, "completed": completed}},
            "competitors": [
                {"homeAway": "home", "team": {"displayName": home}},
                {"homeAway": "away", "team": {"displayName": away}},
            ],
        }],
    }


def test_parse_ticker_ok():
    parsed = tsb.parse_ticker("KXWCGAME-26JUN22ARGAUT")
    assert parsed is not None
    date, a, b = parsed
    assert (date.year, date.month, date.day) == (2026, 6, 22)
    assert a == "ARG" and b == "AUT"


def test_parse_ticker_bad_input_never_raises():
    assert tsb.parse_ticker("not-a-ticker") is None
    assert tsb.parse_ticker("") is None
    assert tsb.parse_ticker(None) is None  # type: ignore[arg-type]


def test_resolve_kickoff_unique_match():
    events = [_ev("1", "Argentina", "Austria", "2026-06-22T17:00Z")]
    kickoff, status = tsb.resolve_kickoff("KXWCGAME-26JUN22ARGAUT", events)
    assert kickoff == datetime(2026, 6, 22, 17, 0, tzinfo=timezone.utc)
    assert status == "STATUS_FULL_TIME"


def test_resolve_kickoff_code_override():
    # AUT/AUS both prefix-collide without the override table; confirm disambiguation.
    events = [_ev("1", "Argentina", "Austria", "2026-06-22T17:00Z"),
              _ev("2", "Australia", "Egypt", "2026-07-03T10:00Z")]
    kickoff, _ = tsb.resolve_kickoff("KXWCGAME-26JUL03AUSEGY", events)
    assert kickoff == datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)


def test_resolve_kickoff_ambiguous_returns_none():
    events = [_ev("1", "Argentina", "Austria", "2026-06-22T17:00Z"),
              _ev("2", "Argentina", "Austria", "2026-06-22T17:00Z")]
    assert tsb.resolve_kickoff("KXWCGAME-26JUN22ARGAUT", events) is None


def test_resolve_kickoff_no_match_returns_none():
    events = [_ev("1", "France", "Iraq", "2026-06-22T21:00Z")]
    assert tsb.resolve_kickoff("KXWCGAME-26JUN22ARGAUT", events) is None


def test_label_tick_h1_h2_and_excluded_boundary():
    kickoff = datetime(2026, 6, 22, 17, 0, tzinfo=timezone.utc)
    # well inside H1 (elapsed ~20 min)
    assert tsb.label_tick("2026-06-22T17:20:00Z", kickoff) == "H1"
    # well inside H2 (elapsed ~70 min, i.e. kickoff+45+25)
    assert tsb.label_tick("2026-06-22T18:10:00Z", kickoff) == "H2"
    # inside the +/-10min boundary band around kickoff+45 -> excluded
    assert tsb.label_tick("2026-06-22T17:45:00Z", kickoff) is None
    assert tsb.label_tick("2026-06-22T17:36:00Z", kickoff) is None
    assert tsb.label_tick("2026-06-22T17:54:00Z", kickoff) is None


def test_label_tick_unparseable_ts_returns_none():
    kickoff = datetime(2026, 6, 22, 17, 0, tzinfo=timezone.utc)
    assert tsb.label_tick("not-a-timestamp", kickoff) is None


def test_backfill_game_counts_and_labels():
    kickoff_str = "2026-06-22T17:00Z"
    events = [_ev("1", "Argentina", "Austria", kickoff_str)]
    ticks = [
        {"ts": "2026-06-22T17:10:00Z"},  # H1
        {"ts": "2026-06-22T17:45:00Z"},  # excluded (boundary)
        {"ts": "2026-06-22T18:20:00Z"},  # H2
        {"ts": ""},                       # skipped (no ts)
    ]
    doc = tsb.backfill_game("KXWCGAME-26JUN22ARGAUT", ticks, events)
    assert doc["method"] == "kickoff_plus_elapsed"
    assert doc["n_h1"] == 1 and doc["n_h2"] == 1 and doc["n_excluded"] == 1
    assert doc["n_ticks"] == 4
    assert doc["labels"]["2026-06-22T17:10:00Z"] == "H1"
    assert doc["labels"]["2026-06-22T18:20:00Z"] == "H2"
    assert "2026-06-22T17:45:00Z" not in doc["labels"]


def test_backfill_game_unresolved_kickoff_never_fabricates():
    doc = tsb.backfill_game("KXWCGAME-26JUN22ARGAUT", [{"ts": "2026-06-22T17:10:00Z"}], [])
    assert doc["method"] == "unresolved"
    assert doc["labels"] == {}
    assert doc["n_h1"] == 0 and doc["n_h2"] == 0 and doc["n_excluded"] == 0


def test_find_unk_games_only_bare_live(tmp_path):
    base = tmp_path / "soccer_intl"
    base.mkdir()
    unk = base / "KXWCGAME-26JUN22ARGAUT.jsonl"
    unk.write_text(
        json.dumps({"ts": "2026-06-22T17:10:00Z", "state_summary": "live"}) + "\n" +
        json.dumps({"ts": "2026-06-22T17:11:00Z", "state_summary": "live"}) + "\n",
        encoding="utf-8")
    labeled = base / "KXWCGAME-26JUL01BELSEN.jsonl"
    labeled.write_text(
        json.dumps({"ts": "2026-07-01T18:00:00Z",
                    "state_summary": "home_score=0.0 away_score=0.0 minute=10"}) + "\n",
        encoding="utf-8")
    games = tsb.find_unk_games(base)
    assert list(games.keys()) == ["KXWCGAME-26JUN22ARGAUT"]


def test_find_unk_games_missing_dir_returns_empty(tmp_path):
    assert tsb.find_unk_games(tmp_path / "does_not_exist") == {}


def test_build_sidecar_end_to_end(tmp_path):
    base = tmp_path / "soccer_intl"
    base.mkdir()
    (base / "KXWCGAME-26JUN22ARGAUT.jsonl").write_text(
        "\n".join(json.dumps({"ts": ts, "state_summary": "live"}) for ts in [
            "2026-06-22T17:10:00Z", "2026-06-22T17:45:00Z", "2026-06-22T18:20:00Z",
        ]), encoding="utf-8")

    def fake_http_get(url):
        assert "dates=20260622" in url or "dates=20260621" in url or "dates=20260623" in url
        if "dates=20260622" in url:
            return {"events": [_ev("1", "Argentina", "Austria", "2026-06-22T17:00Z")]}
        return {"events": []}

    doc = tsb.build_sidecar(base, http_get=fake_http_get)
    assert doc["n_games"] == 1
    assert doc["n_games_unresolved"] == 0
    assert doc["n_ticks_h1"] == 1 and doc["n_ticks_h2"] == 1 and doc["n_ticks_excluded"] == 1
    assert doc["segment_source"] == "backfilled"
    assert doc["per_game"]["KXWCGAME-26JUN22ARGAUT"]["method"] == "kickoff_plus_elapsed"


def test_write_and_load_sidecar_roundtrip(tmp_path):
    path = tmp_path / "sidecar.json"
    doc = {"n_games": 1, "per_game": {"X": {"labels": {"t1": "H1"}}}}
    written = tsb.write_sidecar(doc, path)
    assert written == path and path.is_file()
    loaded = tsb.load_sidecar(path)
    assert loaded == doc


def test_load_sidecar_missing_file_returns_none(tmp_path):
    assert tsb.load_sidecar(tmp_path / "nope.json") is None


def test_lookup_segment():
    sidecar = {"per_game": {"KXWCGAME-26JUN22ARGAUT": {"labels": {"2026-06-22T17:10:00Z": "H1"}}}}
    assert tsb.lookup_segment(sidecar, "KXWCGAME-26JUN22ARGAUT", "2026-06-22T17:10:00Z") == "H1"
    assert tsb.lookup_segment(sidecar, "KXWCGAME-26JUN22ARGAUT", "no-such-ts") is None
    assert tsb.lookup_segment(sidecar, "NO_SUCH_GAME", "2026-06-22T17:10:00Z") is None
    assert tsb.lookup_segment({}, "any", "any") is None
