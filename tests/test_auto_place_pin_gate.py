"""tests/test_auto_place_pin_gate.py — 8th safety gate (pin corroboration).

Mission: D2 added pin_corroborated to line_moves JSONL. The auto-place daemon
must consume this so it does not chase scraper alt-line artifacts (the
Castle / Fox / JaW AST 2026-05-26 false positive that triggered this work).

Two top-level scenarios:
  1. Castle AST 5.5 -> 3.5 in line_moves with pin_corroborated=False AND we
     are considering Castle AST OVER 6.5 — the (non-corroborated) move
     direction (UNDER) opposes our bet (OVER). Pure CHAR-1 logic says we'd be
     trading against a "steam" event, but since the event is a false positive
     we are actually chasing artifact steam in the OPPOSITE direction. Test
     covers the symmetric case: same Castle AST OVER 6.5 candidate vs a
     non-corroborated LINE_UP event in the same OVER direction — that is the
     textbook 'chasing_artifact_steam' block.
  2. Same candidate but with the event marked pin_corroborated=True and
     direction OVER (matching the bet) — gate PASSES (this is a real,
     sharp-confirmed move pointing the same way we want to bet).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.auto_place_daemon as apd  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
def _castle_ast_over_65():
    """Candidate bet: Castle AST OVER 6.5 — the very bet the daemon almost
    placed against tonight's bogus FD alt-line 'steam'."""
    return {
        "player": "Stephon Castle",
        "stat": "ast",
        "side": "OVER",
        "book": "pin",
        "line": 6.5,
        "odds": 110,
        "model_q10": 3.1,
        "model_q50": 7.8,
        "model_q90": 11.2,
        "model_prob": 0.62,
        "edge_pct": 18.0,
        "kelly_stake_$": 35.0,
        "kelly_pct_used": 3.5,
        "stale": False,
    }


def _move_event(direction: str, *, corroborated: bool, minutes_ago: int,
                now: _dt.datetime, book: str = "fd", reason: str = "pin_flat"):
    """Build a synthetic line_moves event.

    direction='OVER' -> LINE_UP tag; direction='UNDER' -> LINE_DOWN tag.
    """
    tag = "LINE_UP" if direction == "OVER" else "LINE_DOWN"
    ts = (now - _dt.timedelta(minutes=minutes_ago)).isoformat()
    return {
        "book": book,
        "player_name": "Stephon Castle",
        "name_key": apd._name_key("Stephon Castle"),
        "stat": "ast",
        "ts_from": ts,
        "ts_to": ts,
        "line_from": 5.5 if direction == "UNDER" else 5.5,
        "line_to": 3.5 if direction == "UNDER" else 7.5,
        "line_delta": -2.0 if direction == "UNDER" else 2.0,
        "odds_from": -110,
        "odds_to": -200,
        "odds_pct_delta": 35.0,
        "tags": [tag, "ODDS_TIGHTEN"],
        "consensus": True,
        "pin_corroborated": corroborated,
        "pin_corroboration_reason": "pin_confirms" if corroborated else reason,
    }


@pytest.fixture
def now_utc():
    return _dt.datetime(2026, 5, 26, 15, 30, 0, tzinfo=_dt.timezone.utc)


# --------------------------------------------------------------------------- #
# Direct gate tests                                                           #
# --------------------------------------------------------------------------- #
def test_blocks_chasing_artifact_steam(now_utc):
    """A FALSE-POSITIVE steam event pointing the SAME way as our bet ->
    BLOCK. This is exactly the Castle/Fox/JaW tonight scenario: a non-
    corroborated event made it look like sharps loved OVER, but pin
    showed nothing — chasing it would be following a scraper artifact."""
    bet = _castle_ast_over_65()
    events = [
        _move_event("OVER", corroborated=False, minutes_ago=10, now=now_utc,
                    book="fd", reason="pin_flat"),
    ]
    ok, reason = apd.gate_pin_corroboration(bet, events, now=now_utc)
    assert ok is False, reason
    assert "chasing_artifact_steam" in reason


def test_blocks_steam_against_us(now_utc):
    """A CORROBORATED steam event pointing AGAINST our bet -> BLOCK. Sharps
    confirm the line is moving the other way."""
    bet = _castle_ast_over_65()  # OVER
    events = [
        _move_event("UNDER", corroborated=True, minutes_ago=10, now=now_utc),
    ]
    ok, reason = apd.gate_pin_corroboration(bet, events, now=now_utc)
    assert ok is False, reason
    assert "steam_against_us" in reason


def test_passes_with_corroborated_same_direction(now_utc):
    """Same candidate; line_moves has a pin_corroborated=True LINE_UP
    (OVER) event. That is sharp confirmation in OUR direction -> PASS."""
    bet = _castle_ast_over_65()
    events = [
        _move_event("OVER", corroborated=True, minutes_ago=10, now=now_utc),
    ]
    ok, reason = apd.gate_pin_corroboration(bet, events, now=now_utc)
    assert ok is True, reason


def test_passes_with_no_relevant_events(now_utc):
    """Events on a different player/stat should not affect Castle AST."""
    bet = _castle_ast_over_65()
    irrelevant = {
        **_move_event("UNDER", corroborated=False, minutes_ago=5, now=now_utc),
        "player_name": "Chet Holmgren",
        "name_key": apd._name_key("Chet Holmgren"),
        "stat": "fg3m",
    }
    ok, reason = apd.gate_pin_corroboration(bet, [irrelevant], now=now_utc)
    assert ok is True
    assert "no events" in reason


def test_passes_with_empty_line_moves(now_utc):
    """No JSONL at all -> fail-open (don't strangle the daemon on missing
    data; line_validator is the hard gate)."""
    ok, reason = apd.gate_pin_corroboration(
        _castle_ast_over_65(), [], now=now_utc)
    assert ok is True


def test_ignores_events_outside_window(now_utc):
    """Event from 2h ago, window is 90min -> ignored, gate PASSES."""
    bet = _castle_ast_over_65()
    events = [
        _move_event("OVER", corroborated=False, minutes_ago=120, now=now_utc),
    ]
    ok, _ = apd.gate_pin_corroboration(
        bet, events, now=now_utc, window_min=90)
    assert ok is True


def test_ignores_legacy_events_without_field(now_utc):
    """Pre-D2 events lack pin_corroborated entirely. They should be
    skipped (not blocked) so historical JSONL doesn't paralyse the gate."""
    bet = _castle_ast_over_65()
    ev = _move_event("OVER", corroborated=False, minutes_ago=10, now=now_utc)
    ev.pop("pin_corroborated", None)
    ev.pop("pin_corroboration_reason", None)
    ok, reason = apd.gate_pin_corroboration(bet, [ev], now=now_utc)
    assert ok is True
    assert "no events" in reason or "checked" in reason


def test_require_false_short_circuits_pass(now_utc):
    """Env-disabled (AUTO_PLACE_REQUIRE_PIN_CORROBORATION=false) -> always
    passes regardless of events present."""
    bet = _castle_ast_over_65()
    events = [
        _move_event("OVER", corroborated=False, minutes_ago=5, now=now_utc),
    ]
    ok, reason = apd.gate_pin_corroboration(
        bet, events, now=now_utc, require=False)
    assert ok is True
    assert "disabled" in reason


# --------------------------------------------------------------------------- #
# Env-var plumbing                                                            #
# --------------------------------------------------------------------------- #
def test_env_var_disables_gate_via_orchestrator(now_utc, monkeypatch):
    """Setting AUTO_PLACE_REQUIRE_PIN_CORROBORATION=false should make
    run_all_gates() not block on a would-be-blocking event."""
    bet = _castle_ast_over_65()
    events = [
        _move_event("OVER", corroborated=False, minutes_ago=5, now=now_utc),
    ]
    monkeypatch.setenv("AUTO_PLACE_REQUIRE_PIN_CORROBORATION", "false")

    ok, gates = apd.run_all_gates(
        bet,
        bankroll=1000.0, per_bet_cap=0.05, daily_cap=0.25,
        existing_daily_exposure=0.0,
        open_rows=[],
        confidence_floor=0.08,
        tip_off_utc=now_utc + _dt.timedelta(hours=4),
        min_pre_tip_min=30,
        injuries={apd._name_key("Stephon Castle"): "AVAILABLE"},
        now=now_utc,
        use_snapshot_validator=False,
        line_moves=events,
    )
    # The pin gate row should exist AND be ok=True with the disabled reason.
    pin_row = next(g for g in gates if g["gate"] == "pin_corroboration")
    assert pin_row["ok"] is True
    assert "disabled" in pin_row["reason"]


def test_default_env_enables_gate(now_utc, monkeypatch):
    """With env unset, the gate is ON and should block the artifact event."""
    bet = _castle_ast_over_65()
    events = [
        _move_event("OVER", corroborated=False, minutes_ago=5, now=now_utc),
    ]
    monkeypatch.delenv("AUTO_PLACE_REQUIRE_PIN_CORROBORATION", raising=False)

    ok, gates = apd.run_all_gates(
        bet,
        bankroll=1000.0, per_bet_cap=0.05, daily_cap=0.25,
        existing_daily_exposure=0.0,
        open_rows=[],
        confidence_floor=0.08,
        tip_off_utc=now_utc + _dt.timedelta(hours=4),
        min_pre_tip_min=30,
        injuries={apd._name_key("Stephon Castle"): "AVAILABLE"},
        now=now_utc,
        use_snapshot_validator=False,
        line_moves=events,
    )
    pin_row = next(g for g in gates if g["gate"] == "pin_corroboration")
    assert pin_row["ok"] is False
    assert "chasing_artifact_steam" in pin_row["reason"]


# --------------------------------------------------------------------------- #
# JSONL loader                                                                #
# --------------------------------------------------------------------------- #
def test_load_line_moves_reads_jsonl(tmp_path, now_utc):
    cache = tmp_path / "cache"
    cache.mkdir()
    path = cache / "line_moves_2026-05-26.json"
    e1 = _move_event("OVER", corroborated=False, minutes_ago=5, now=now_utc)
    e2 = _move_event("UNDER", corroborated=True, minutes_ago=10, now=now_utc)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(e1) + "\n")
        f.write(json.dumps(e2) + "\n")
    out = apd.load_line_moves("2026-05-26", cache_dir=str(cache))
    assert len(out) == 2
    assert out[0]["pin_corroborated"] is False
    assert out[1]["pin_corroborated"] is True


def test_load_line_moves_missing_file_returns_empty():
    assert apd.load_line_moves("1999-01-01", cache_dir="/nonexistent") == []


def test_load_line_moves_skips_malformed_lines(tmp_path, now_utc):
    cache = tmp_path / "cache"
    cache.mkdir()
    path = cache / "line_moves_2026-05-26.json"
    good = _move_event("OVER", corroborated=True, minutes_ago=5, now=now_utc)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json\n")
        f.write(json.dumps(good) + "\n")
        f.write("\n")
    out = apd.load_line_moves("2026-05-26", cache_dir=str(cache))
    assert len(out) == 1
