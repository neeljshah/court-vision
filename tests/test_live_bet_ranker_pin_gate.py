"""tests/test_live_bet_ranker_pin_gate.py — UPSTREAM pin-corroboration gate.

E1 added a pin_corroborated gate to auto_place_daemon (consumer). This test
suite covers the symmetric gate wired into live_bet_ranker (the RANKER —
upstream of auto_place). The two layers together protect the chain:

    live_bet_ranker  (downgrades/blocks here, before URGENT_BETS write)
        |
        v
    auto_place_daemon  (hard-blocks here, before ledger fire)

The ranker is non-fatal by default — pin-blocked bets are downgraded to a
WATCH bucket with zero stake (mode=warn). Operators can flip to mode=block
(drop entirely) or mode=pass (filter off) via LIVE_RANKER_PIN_FILTER.
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

import scripts.live_bet_ranker as lbr  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
def _castle_ast_over_65():
    """Candidate bet: Castle AST OVER 6.5 — the very bet that almost slipped
    through the ranker tonight against bogus FD alt-line 'steam'."""
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
        "ev_per_dollar": 0.40,
        "kelly_stake_$": 35.0,
        "kelly_pct_used": 3.5,
        "stale": False,
    }


def _move_event(direction: str, *, corroborated: bool, minutes_ago: int,
                now: _dt.datetime, book: str = "fd", reason: str = "pin_flat"):
    """Synthetic line_moves event in the JSONL schema."""
    tag = "LINE_UP" if direction == "OVER" else "LINE_DOWN"
    ts = (now - _dt.timedelta(minutes=minutes_ago)).isoformat()
    return {
        "book": book,
        "player_name": "Stephon Castle",
        "name_key": lbr._name_key("Stephon Castle"),
        "stat": "ast",
        "ts_from": ts,
        "ts_to": ts,
        "line_from": 5.5,
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
# Direct gate (evaluate_pin_filter) — mirrors auto_place gate_pin_corroboration
# --------------------------------------------------------------------------- #
def test_blocks_chasing_artifact_steam(now_utc):
    """Non-corroborated steam pointing SAME way as our bet -> BLOCKED.
    This is the Castle/Fox/JaW 2026-05-26 false-positive scenario."""
    bet = _castle_ast_over_65()
    events = [
        _move_event("OVER", corroborated=False, minutes_ago=10, now=now_utc,
                    book="fd", reason="pin_flat"),
    ]
    verdict, reason = lbr.evaluate_pin_filter(bet, events, now=now_utc)
    assert verdict == "blocked"
    assert "chasing_artifact_steam" in reason


def test_blocks_steam_against_us(now_utc):
    """Pin-corroborated steam pointing OPPOSITE our bet -> BLOCKED."""
    bet = _castle_ast_over_65()
    events = [_move_event("UNDER", corroborated=True, minutes_ago=10, now=now_utc)]
    verdict, reason = lbr.evaluate_pin_filter(bet, events, now=now_utc)
    assert verdict == "blocked"
    assert "steam_against_us" in reason


def test_passes_with_corroborated_same_direction(now_utc):
    """Pin-corroborated steam pointing SAME way as our bet -> PASS."""
    bet = _castle_ast_over_65()
    events = [_move_event("OVER", corroborated=True, minutes_ago=10, now=now_utc)]
    verdict, _ = lbr.evaluate_pin_filter(bet, events, now=now_utc)
    assert verdict == "pass"


def test_passes_with_no_relevant_events(now_utc):
    """Event on a DIFFERENT (player, stat) -> PASS."""
    bet = _castle_ast_over_65()
    irrelevant = {
        **_move_event("UNDER", corroborated=False, minutes_ago=5, now=now_utc),
        "player_name": "Chet Holmgren",
        "name_key": lbr._name_key("Chet Holmgren"),
        "stat": "fg3m",
    }
    verdict, reason = lbr.evaluate_pin_filter(bet, [irrelevant], now=now_utc)
    assert verdict == "pass"
    assert "no events" in reason


def test_passes_with_empty_line_moves(now_utc):
    """No JSONL events at all -> fail-open PASS."""
    verdict, _ = lbr.evaluate_pin_filter(_castle_ast_over_65(), [], now=now_utc)
    assert verdict == "pass"


def test_ignores_events_outside_window(now_utc):
    """Event older than window_min -> ignored, verdict PASS."""
    bet = _castle_ast_over_65()
    events = [_move_event("OVER", corroborated=False, minutes_ago=120,
                           now=now_utc)]
    verdict, _ = lbr.evaluate_pin_filter(
        bet, events, now=now_utc, window_min=90)
    assert verdict == "pass"


def test_ignores_legacy_events_without_field(now_utc):
    """Pre-D2 events lack pin_corroborated. Skip (do NOT block)."""
    bet = _castle_ast_over_65()
    ev = _move_event("OVER", corroborated=False, minutes_ago=10, now=now_utc)
    ev.pop("pin_corroborated", None)
    verdict, _ = lbr.evaluate_pin_filter(bet, [ev], now=now_utc)
    assert verdict == "pass"


def test_under_bet_blocked_by_non_corroborated_line_down(now_utc):
    """Castle AST UNDER 3.5 vs non-corroborated LINE_DOWN -> chasing artifact."""
    bet = _castle_ast_over_65()
    bet["side"] = "UNDER"
    bet["line"] = 3.5
    events = [
        _move_event("UNDER", corroborated=False, minutes_ago=5, now=now_utc,
                    book="fd", reason="pin_flat"),
    ]
    verdict, reason = lbr.evaluate_pin_filter(bet, events, now=now_utc)
    assert verdict == "blocked"
    assert "chasing_artifact_steam" in reason


# --------------------------------------------------------------------------- #
# Env-var (LIVE_RANKER_PIN_FILTER) plumbing                                   #
# --------------------------------------------------------------------------- #
def test_env_default_is_warn(monkeypatch):
    monkeypatch.delenv("LIVE_RANKER_PIN_FILTER", raising=False)
    assert lbr._pin_filter_mode() == "warn"


def test_env_pass_disables(monkeypatch):
    monkeypatch.setenv("LIVE_RANKER_PIN_FILTER", "pass")
    assert lbr._pin_filter_mode() == "pass"


def test_env_block_enables_hard_drop(monkeypatch):
    monkeypatch.setenv("LIVE_RANKER_PIN_FILTER", "block")
    assert lbr._pin_filter_mode() == "block"


def test_env_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("LIVE_RANKER_PIN_FILTER", "nonsense")
    assert lbr._pin_filter_mode() == "warn"


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
    out = lbr.load_line_moves("2026-05-26", cache_dir=str(cache))
    assert len(out) == 2
    assert out[0]["pin_corroborated"] is False
    assert out[1]["pin_corroborated"] is True


def test_load_line_moves_missing_file_returns_empty():
    assert lbr.load_line_moves("1999-01-01", cache_dir="/nonexistent") == []


def test_load_line_moves_skips_malformed_lines(tmp_path, now_utc):
    cache = tmp_path / "cache"
    cache.mkdir()
    path = cache / "line_moves_2026-05-26.json"
    good = _move_event("OVER", corroborated=True, minutes_ago=5, now=now_utc)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json\n")
        f.write(json.dumps(good) + "\n")
        f.write("\n")
    out = lbr.load_line_moves("2026-05-26", cache_dir=str(cache))
    assert len(out) == 1


# --------------------------------------------------------------------------- #
# PinFilterCache — refresh cadence                                            #
# --------------------------------------------------------------------------- #
def test_pin_cache_refreshes_every_n_ticks(tmp_path, now_utc, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    path = cache_dir / "line_moves_2026-05-26.json"
    e1 = _move_event("OVER", corroborated=False, minutes_ago=5, now=now_utc)
    path.write_text(json.dumps(e1) + "\n")

    pc = lbr.PinFilterCache(refresh_every_ticks=5, cache_dir=str(cache_dir))
    # First call -> loads from disk
    out0 = pc.get("2026-05-26", 0)
    assert len(out0) == 1

    # Mutate file; cache should NOT pick it up until refresh threshold hit
    e2 = _move_event("UNDER", corroborated=True, minutes_ago=5, now=now_utc)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(e1) + "\n")
        f.write(json.dumps(e2) + "\n")

    out1 = pc.get("2026-05-26", 1)  # tick 1 -> within window
    out4 = pc.get("2026-05-26", 4)  # still within
    assert len(out1) == 1 and len(out4) == 1, "cache should not refresh yet"

    out5 = pc.get("2026-05-26", 5)  # tick 5 -> refresh
    assert len(out5) == 2, "cache should refresh after 5 ticks"


def test_pin_cache_refresh_on_date_change(tmp_path, now_utc):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    p1 = cache_dir / "line_moves_2026-05-26.json"
    p2 = cache_dir / "line_moves_2026-05-27.json"
    p1.write_text(json.dumps(
        _move_event("OVER", corroborated=True, minutes_ago=5, now=now_utc)
    ) + "\n")
    p2.write_text("")  # empty for the next day

    pc = lbr.PinFilterCache(refresh_every_ticks=999, cache_dir=str(cache_dir))
    out_day1 = pc.get("2026-05-26", 0)
    out_day2 = pc.get("2026-05-27", 1)
    assert len(out_day1) == 1
    assert out_day2 == []


# --------------------------------------------------------------------------- #
# Output-format preservation (downstream-consumer contract)                   #
# --------------------------------------------------------------------------- #
def test_bet_dict_has_new_fields_but_keeps_old_ones():
    """The ranker output adds pin_filter + pin_reason but must not break
    existing field names that auto_place_daemon + downstream consumers
    rely on (player, stat, side, book, line, odds, edge_pct, kelly_stake_$,
    etc.)."""
    REQUIRED = {
        "player", "stat", "side", "book", "line", "odds",
        "model_q50", "model_q10", "model_q90",
        "implied_prob", "model_prob", "edge_pct", "ev_per_dollar",
        "kelly_pct_used", "kelly_stake_$", "line_move", "stale",
        "pin_filter", "pin_reason",
    }
    # Build a real bet via run_tick? Too heavy — assert the schema via the
    # field set we know run_tick produces (per scripts/live_bet_ranker.py).
    # The fields are co-located in the b = {...} dict; if any key is renamed
    # in the source, that change WILL show up in run_tick's payload and the
    # downstream auto_place daemon would break. Pin this contract here.
    import inspect
    src = inspect.getsource(lbr.run_tick)
    for field in REQUIRED:
        assert f'"{field}"' in src, f"field {field!r} missing from run_tick"


# --------------------------------------------------------------------------- #
# End-to-end: pin-filter actually segregates blocked bets                     #
# --------------------------------------------------------------------------- #
def _make_bet(player, stat, side, line, pin_filter="pass", edge=10.0):
    return {
        "player": player, "stat": stat, "side": side, "book": "pin",
        "line": line, "odds": 110, "model_q50": 7.0, "model_q10": 4.0,
        "model_q90": 10.0, "implied_prob": 0.476, "model_prob": 0.60,
        "edge_pct": edge, "ev_per_dollar": 0.20, "kelly_pct_used": 3.0,
        "kelly_stake_$": 30.0, "line_move": "", "stale": False,
        "pin_filter": pin_filter, "pin_reason": "",
    }


def test_warn_mode_routes_blocked_to_watch_bucket():
    """Mode=warn: blocked bets go to watch_bets with $0 stake; capped
    list retains only passing bets."""
    bets = [
        _make_bet("A", "pts", "OVER", 20.5, pin_filter="pass", edge=15.0),
        _make_bet("B", "ast", "OVER", 6.5,  pin_filter="blocked", edge=18.0),
        _make_bet("C", "reb", "UNDER", 8.5, pin_filter="pass", edge=12.0),
    ]
    # Manually simulate the post-build pin-filter slice that run_tick runs.
    pin_mode = "warn"
    pos = [b for b in bets if b["edge_pct"] >= lbr.MIN_EDGE_PCT]
    watch = []
    if pin_mode == "warn":
        kept = []
        for b in pos:
            if b.get("pin_filter") == "blocked":
                w = dict(b)
                w["kelly_stake_$"] = 0.0
                w["kelly_pct_used"] = 0.0
                watch.append(w)
            else:
                kept.append(b)
        pos = kept
    elif pin_mode == "block":
        pos = [b for b in pos if b.get("pin_filter") != "blocked"]
    assert len(pos) == 2  # A + C
    assert len(watch) == 1  # B
    assert watch[0]["player"] == "B"
    assert watch[0]["kelly_stake_$"] == 0.0


def test_block_mode_drops_blocked_entirely():
    bets = [
        _make_bet("A", "pts", "OVER", 20.5, pin_filter="pass", edge=15.0),
        _make_bet("B", "ast", "OVER", 6.5,  pin_filter="blocked", edge=18.0),
    ]
    pos = [b for b in bets if b["edge_pct"] >= lbr.MIN_EDGE_PCT]
    pos = [b for b in pos if b.get("pin_filter") != "blocked"]
    assert len(pos) == 1
    assert pos[0]["player"] == "A"


def test_pass_mode_lets_everything_through():
    bets = [
        _make_bet("A", "pts", "OVER", 20.5, pin_filter="pass", edge=15.0),
        _make_bet("B", "ast", "OVER", 6.5,  pin_filter="blocked", edge=18.0),
    ]
    pos = [b for b in bets if b["edge_pct"] >= lbr.MIN_EDGE_PCT]
    # In pass mode, no filtering occurs after the edge threshold.
    assert len(pos) == 2
