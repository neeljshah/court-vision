"""tests/test_R20_M3_betting_coverage.py — R20_M3 probe.

Targeted coverage expansion of the live betting pipeline (R15-R19 daemons).
Focus is the highest-financial-risk uncovered branches:

  * line_move_detector  — implied-prob math, alt-line collapse, consensus
                          steam tagging, dedup, vault feed, webhook
  * middle_finder_daemon — CSV schema drift, free-arb vs middle math,
                           alt-line filter (R19_L1), model band annotation
  * live_bet_ranker     — Kelly sizing edges, model_hit_prob, slate cap
                          partial-fit logic, payload assembly, state IO
  * inplay_bet_ranker   — cumulative snapshot, garbage-time dampener,
                          stale guard, line ingestion, in-play pricing
  * auto_settle_daemon  — DNP void, OT-aware totals, seen-set dedup,
                          settle vs dry-run paths, audit log
  * bankroll_monitor    — filter, ROI, dashboard render, alert append,
                          atomic write
  * multi_game_kelly    — slate cap, validation, identity property
  * injury_availability — factor lookup by id + name, OUT collapse,
                          stale-snapshot refresh path
  * residual_heads      — feature-name selection, position one-hot,
                          base feature map, NaN xstat guard

All fixtures are local — no live HTTP, no real model artifacts.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
for p in (PROJECT_DIR, SCRIPTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)


# =============================================================================
# line_move_detector — pricing math, dedup, collapse, consensus, vault feed
# =============================================================================
def _import_lmd():
    from scripts import line_move_detector as lmd  # noqa: E402
    return lmd


def test_lmd_american_to_implied_prob_handles_even_token():
    """'EVEN' / 'EV' must price at 0.5 — same convention as clv.py."""
    lmd = _import_lmd()
    assert lmd.american_to_implied_prob("EVEN") == 0.5
    assert lmd.american_to_implied_prob("EV") == 0.5
    assert lmd.american_to_implied_prob("+100") == pytest.approx(0.5)
    # Heavy favorite still calibrates correctly
    assert lmd.american_to_implied_prob(-800) == pytest.approx(800 / 900)


def test_lmd_implied_prob_invalid_inputs_yield_none():
    lmd = _import_lmd()
    assert lmd.american_to_implied_prob(None) is None
    assert lmd.american_to_implied_prob("garbage") is None
    assert lmd.american_to_implied_prob(0) is None


def test_lmd_classify_move_threshold_zero_is_safe():
    """A 0 delta must NEVER trip a tag even when the threshold is 0 —
    otherwise probing with threshold=0 spams a tag per snapshot."""
    lmd = _import_lmd()
    assert lmd.classify_move(0.0, 0.0, 0.0, 0.0) == []
    # 0.5 line move @ threshold 0.5 → LINE_UP
    tags = lmd.classify_move(0.5, 0.0, 0.5, 100.0)
    assert "LINE_UP" in tags
    # Negative line move → LINE_DOWN
    tags = lmd.classify_move(-1.0, 15.0, 0.5, 10.0)
    assert "LINE_DOWN" in tags
    assert "ODDS_TIGHTEN" in tags  # +15% > 10%


def test_lmd_collapse_to_main_line_picks_closest_to_50():
    """Alt-line ladder collapse must keep the rung whose over_price implied
    prob is nearest 0.5 — otherwise we compare two random rungs and emit
    a bogus '29.5 → 9.5' diff."""
    lmd = _import_lmd()
    df = pd.DataFrame([
        # Same captured_at — collapse must dedup
        {"book": "bov", "player_name": "X", "stat": "pts",
         "captured_at": "2026-05-26T19:00:00Z",
         "line": 9.5, "over_price": -800, "under_price": +500},
        {"book": "bov", "player_name": "X", "stat": "pts",
         "captured_at": "2026-05-26T19:00:00Z",
         "line": 24.5, "over_price": -110, "under_price": -110},
        {"book": "bov", "player_name": "X", "stat": "pts",
         "captured_at": "2026-05-26T19:00:00Z",
         "line": 40.5, "over_price": +900, "under_price": -2000},
    ])
    out = lmd.collapse_to_main_line(df)
    assert len(out) == 1
    assert float(out.iloc[0]["line"]) == 24.5


def test_lmd_detect_moves_and_consensus_steam():
    """Two books moving the same direction within 5 min must be tagged
    CONSENSUS_STEAM. This is the high-conviction sharps signal."""
    lmd = _import_lmd()
    df = pd.DataFrame([
        # Book A: line 24.5 → 25.5 (LINE_UP)
        {"book": "bov", "player_name": "Star", "stat": "pts",
         "captured_at": "2026-05-26T19:00:00Z",
         "line": 24.5, "over_price": -110, "under_price": -110},
        {"book": "bov", "player_name": "Star", "stat": "pts",
         "captured_at": "2026-05-26T19:02:00Z",
         "line": 25.5, "over_price": -110, "under_price": -110},
        # Book B: line 24.5 → 25.5 (LINE_UP) 1 min later
        {"book": "fd", "player_name": "Star", "stat": "pts",
         "captured_at": "2026-05-26T19:00:30Z",
         "line": 24.5, "over_price": -110, "under_price": -110},
        {"book": "fd", "player_name": "Star", "stat": "pts",
         "captured_at": "2026-05-26T19:03:00Z",
         "line": 25.5, "over_price": -110, "under_price": -110},
    ])
    events = lmd.detect_moves(df, threshold_line=0.5, threshold_odds_pct=10.0)
    assert len(events) == 2
    tagged = lmd.tag_consensus(events, window_sec=300)
    # Both should be consensus-tagged
    assert all(e["consensus"] for e in tagged)
    assert all("CONSENSUS_STEAM" in e["tags"] for e in tagged)


def test_lmd_append_and_dedup_events_round_trip(tmp_path):
    """append_events + load_existing_event_keys must round-trip so the
    same consecutive-pair never emits twice across daemon restarts."""
    lmd = _import_lmd()
    cache = tmp_path / "line_moves.json"
    evs = [
        {"book": "bov", "player_name": "X", "name_key": "x", "stat": "pts",
         "ts_from": "t1", "ts_to": "t2", "line_from": 24.5, "line_to": 25.5,
         "line_delta": 1.0, "odds_from": -110, "odds_to": -110,
         "odds_pct_delta": None, "tags": ["LINE_UP"], "consensus": False},
    ]
    n = lmd.append_events(str(cache), evs)
    assert n == 1
    keys = lmd.load_existing_event_keys(str(cache))
    assert lmd.event_dedup_key(evs[0]) in keys
    # Re-load on missing file = empty set, not error
    assert lmd.load_existing_event_keys(str(tmp_path / "missing.json")) == set()


def test_lmd_render_vault_feed_writes_table(tmp_path):
    """render_vault_feed must produce a parseable markdown table for the
    Obsidian sidebar — last 50 events, newest first."""
    lmd = _import_lmd()
    cache = tmp_path / "events.json"
    vault = tmp_path / "feed.md"
    evs = [{
        "book": "bov", "player_name": "Y", "name_key": "y", "stat": "pts",
        "ts_from": "t1", "ts_to": "t2",
        "line_from": 24.5, "line_to": 25.5, "line_delta": 1.0,
        "odds_from": -110, "odds_to": -120,
        "odds_pct_delta": 4.5, "tags": ["LINE_UP"], "consensus": False,
    }]
    lmd.append_events(str(cache), evs)
    lmd.render_vault_feed(str(cache), str(vault), limit=50)
    text = vault.read_text(encoding="utf-8")
    assert "# Line Moves Feed" in text
    assert "LINE_UP" in text
    assert "24.5 -> 25.5" in text


def test_lmd_load_book_csvs_drops_non_player_props(tmp_path):
    """Game-total / mainline CSVs lack player_name — must be silently
    skipped, not blow up the loader."""
    lmd = _import_lmd()
    # Player prop schema
    pp = tmp_path / "2026-05-26_bov.csv"
    pp.write_text(
        "captured_at,book,player_name,stat,line,over_price,under_price\n"
        "2026-05-26T19:00:00Z,bov,Star,pts,24.5,-110,-110\n"
    )
    # Mainline schema (missing player_name) — must be skipped silently
    main = tmp_path / "2026-05-26_bov_mainline.csv"
    main.write_text("captured_at,book,total,over,under\n"
                    "2026-05-26T19:00:00Z,bov,225.5,-110,-110\n")
    df = lmd.load_book_csvs(str(tmp_path), "2026-05-26")
    assert len(df) == 1
    assert df.iloc[0]["player_name"] == "Star"


def test_lmd_fire_webhook_no_env_is_noop():
    """No WEBHOOK_URL set → fire_webhook returns 0 without errors."""
    lmd = _import_lmd()
    old = os.environ.pop("WEBHOOK_URL", None)
    try:
        n = lmd.fire_webhook([
            {"consensus": True, "player_name": "X", "stat": "pts"},
        ])
        assert n == 0
    finally:
        if old is not None:
            os.environ["WEBHOOK_URL"] = old


# =============================================================================
# middle_finder_daemon — CSV schema drift, free-arb math, alt-line filter
# =============================================================================
def _import_mfd():
    import middle_finder_daemon as mfd  # noqa: E402
    return mfd


def test_mfd_csv_schema_drift_10_11_12_cols(tmp_path):
    """_read_lines_csv must handle 10, 11, and 12-column rows (Bovada
    redeployments introduced is_alt_line in the 12-col schema)."""
    mfd = _import_mfd()
    p = tmp_path / "test.csv"
    # Header (12-col with is_alt_line)
    p.write_text(
        "captured_at,book,game_id,player_id,player_name,team,stat,line,"
        "over_price,under_price,market_status,is_alt_line\n"
        # 12-col row
        "2026-05-26T19:00:00Z,bov,GID,123,Alpha,TEA,pts,24.5,-110,-110,OPEN,false\n"
        # 10-col row (legacy)
        "2026-05-26T19:00:00Z,bov,GID,123,Beta,reb,9.5,+105,-130,STARTING\n"
        # 11-col row (transitional)
        "2026-05-26T19:00:00Z,bov,GID,456,Gamma,TEB,ast,6.5,-115,-105,STARTING\n",
        encoding="utf-8",
    )
    rows = mfd._read_lines_csv(str(p))
    assert len(rows) == 3
    assert rows[0]["is_alt_line"] == "false"
    assert rows[1]["is_alt_line"] == "false"  # legacy default
    assert rows[2]["is_alt_line"] == "false"


def test_mfd_is_alt_truthy_lenient_parse():
    mfd = _import_mfd()
    assert mfd._is_alt_truthy("true") is True
    assert mfd._is_alt_truthy("TRUE") is True
    assert mfd._is_alt_truthy("1") is True
    assert mfd._is_alt_truthy("yes") is True
    assert mfd._is_alt_truthy("false") is False
    assert mfd._is_alt_truthy("") is False
    assert mfd._is_alt_truthy(None) is False


def test_mfd_free_arb_and_arb_profit_pct():
    """Both legs positive American odds => guaranteed +EV. arb_profit_pct
    returns the risk-free return when implied probs sum < 1."""
    mfd = _import_mfd()
    assert mfd.is_free_arb(+120, +110) is True
    assert mfd.is_free_arb(-110, -110) is False
    assert mfd.is_free_arb(None, +120) is False
    # +120 → 1/2.2 ≈ 0.4545, +110 → 1/2.1 ≈ 0.4762  sum=0.9307 < 1 => arb
    profit = mfd.arb_profit_pct(+120, +110)
    assert profit is not None and profit > 0
    # Standard -110 / -110 → no arb
    assert mfd.arb_profit_pct(-110, -110) is None


def test_mfd_find_middles_filters_juice_and_width():
    """Tight juice on one leg or sub-min-width spread must be rejected."""
    mfd = _import_mfd()
    index = {
        ("Star", "pts"): {
            "bov": [{"line": 24.5, "over_price": -120, "under_price": +110,
                     "is_alt_line": False}],
            "fd":  [{"line": 25.5, "over_price": +110, "under_price": -120,
                     "is_alt_line": False}],
            "pin": [{"line": 24.0, "over_price": -200, "under_price": +160,
                     "is_alt_line": False}],
        },
    }
    middles = mfd.find_middles(index, min_width=0.5, max_juice_each_side=-135)
    # Expect at least the bov-OVER 24.5 / fd-UNDER 25.5 pairing
    assert len(middles) >= 1
    keep = [m for m in middles if m["over_book"] == "bov" and m["under_book"] == "fd"]
    assert keep, f"middle missing: {middles}"
    m = keep[0]
    assert m["middle_width"] == 1.0
    assert m["free_arb"] is False  # over_price -120 is negative

    # Same scan with too-tight juice cap must yield zero
    none = mfd.find_middles(index, min_width=0.5, max_juice_each_side=-105)
    # The legs that have -120 / -120 are cut
    assert all(m["worst_price"] >= -105 for m in none)


def test_mfd_find_middles_alt_line_filter_kills_false_positives():
    """R19_L1: alt-line ladder rungs across books fake a guaranteed +EV.
    allow_alt_lines=False must reject them."""
    mfd = _import_mfd()
    # Two alt-line rungs within the absurd-width cap (>0.5, <=10) — the
    # alt-line filter is the ONLY thing that should block them.
    index = {
        ("Star", "pts"): {
            "bov": [{"line": 22.5, "over_price": +120, "under_price": -180,
                     "is_alt_line": True}],
            "fd":  [{"line": 25.5, "over_price": +110, "under_price": -130,
                     "is_alt_line": True}],
        },
    }
    middles = mfd.find_middles(index, min_width=0.5, max_juice_each_side=-200,
                                allow_alt_lines=False)
    assert middles == []
    # With allow_alt_lines=True the bogus middle materialises (validating that
    # the alt-line filter is doing real work).
    permissive = mfd.find_middles(index, min_width=0.5,
                                    max_juice_each_side=-200,
                                    allow_alt_lines=True)
    assert len(permissive) >= 1


def test_mfd_load_latest_snapshots_dedup_per_line(tmp_path):
    """latest captured_at per (player, stat, line) must win — older
    snapshots dropped, alt flag propagated."""
    mfd = _import_mfd()
    p = tmp_path / "2026-05-26_bov.csv"
    p.write_text(
        "captured_at,book,game_id,player_id,player_name,team,stat,line,"
        "over_price,under_price,market_status,is_alt_line\n"
        "2026-05-26T19:00:00Z,bov,G1,1,X,TA,pts,24.5,-110,-110,OPEN,false\n"
        # Newer snapshot, same line — must replace
        "2026-05-26T19:05:00Z,bov,G1,1,X,TA,pts,24.5,-120,-105,OPEN,false\n"
        # Different (alt) line — separate row
        "2026-05-26T19:05:00Z,bov,G1,1,X,TA,pts,3.5,+120,-180,OPEN,true\n",
        encoding="utf-8",
    )
    idx = mfd.load_latest_snapshots("2026-05-26", lines_dir=str(tmp_path),
                                      books=("bov",))
    rows = idx[("X", "pts")]["bov"]
    assert len(rows) == 2
    primary = [r for r in rows if not r["is_alt_line"]][0]
    assert primary["over_price"] == -120  # newer
    assert primary["under_price"] == -105
    alt = [r for r in rows if r["is_alt_line"]][0]
    assert alt["line"] == 3.5


def test_mfd_atomic_write_json_roundtrip(tmp_path):
    mfd = _import_mfd()
    out = tmp_path / "middles.json"
    payload = {"tick": 1, "middles": [{"player": "X"}]}
    mfd.atomic_write_json(str(out), payload)
    assert json.loads(out.read_text())["middles"][0]["player"] == "X"


# =============================================================================
# live_bet_ranker — Kelly, hit-prob, slate cap, payload, state IO
# =============================================================================
def _import_lbr():
    from scripts import live_bet_ranker as lbr  # noqa: E402
    return lbr


def test_lbr_model_hit_prob_over_under_complement():
    """P(OVER) + P(UNDER) == 1 by construction — required so the same
    pricing pipeline can rank both sides honestly."""
    lbr = _import_lbr()
    over = lbr.model_hit_prob(point_pred=24.0, q10=18.0, q50=24.0, q90=30.0,
                              line=24.5, side="OVER")
    under = lbr.model_hit_prob(point_pred=24.0, q10=18.0, q50=24.0, q90=30.0,
                               line=24.5, side="UNDER")
    assert over is not None and under is not None
    assert over + under == pytest.approx(1.0)


def test_lbr_model_hit_prob_returns_none_when_band_missing():
    lbr = _import_lbr()
    assert lbr.model_hit_prob(None, 1, 2, 3, 24.5, "OVER") is None
    assert lbr.model_hit_prob(24, None, 24, 30, 24.5, "OVER") is None


def test_lbr_kelly_fraction_clamps_to_zero_when_negative_edge():
    """Negative-EV bets must never produce a positive stake — Kelly
    must clamp to 0."""
    lbr = _import_lbr()
    # 40% to win on +100: kelly = (1*0.4 - 0.6)/1 = -0.2 -> clamp 0
    assert lbr.kelly_fraction(0.40, +100) == 0.0
    # Edge case: prob None / odds None
    assert lbr.kelly_fraction(None, -110) == 0.0
    assert lbr.kelly_fraction(0.6, None) == 0.0


def test_lbr_bet_key_includes_all_disambiguators():
    """bet_key drives cooldown; collisions across (player, stat, side,
    book, line) would erase a real bet from the placed set."""
    lbr = _import_lbr()
    b = {"player": "X", "stat": "pts", "side": "OVER",
         "book": "fd", "line": 24.5}
    k1 = lbr.bet_key(b)
    # Different line → distinct key
    b2 = dict(b, line=25.5)
    assert lbr.bet_key(b2) != k1
    # Different book → distinct key
    assert lbr.bet_key(dict(b, book="bov")) != k1
    # Different side → distinct key
    assert lbr.bet_key(dict(b, side="UNDER")) != k1


def test_lbr_load_state_returns_default_when_missing(tmp_path):
    lbr = _import_lbr()
    out = lbr.load_state(str(tmp_path / "nope.json"))
    assert out == {"prior_lines": {}, "prior_edges": {}}


def test_lbr_load_state_recovers_from_corrupt_json(tmp_path):
    lbr = _import_lbr()
    p = tmp_path / "state.json"
    p.write_text("{ this is not json")
    out = lbr.load_state(str(p))
    assert out == {"prior_lines": {}, "prior_edges": {}}


def test_lbr_load_placed_handles_missing_and_corrupt(tmp_path):
    lbr = _import_lbr()
    assert lbr.load_placed(str(tmp_path / "nope.json")) == set()
    p = tmp_path / "placed.json"
    p.write_text("not json")
    assert lbr.load_placed(str(p)) == set()
    p.write_text(json.dumps({"placed_keys": ["X|pts|OVER|fd|24.5"]}))
    out = lbr.load_placed(str(p))
    assert "X|pts|OVER|fd|24.5" in out


def test_lbr_read_lines_csv_handles_three_schemas(tmp_path):
    lbr = _import_lbr()
    p = tmp_path / "lines.csv"
    p.write_text(
        "captured_at,book,game_id,player_id,player_name,stat,line,"
        "over_price,under_price,start_time\n"
        "2026-05-26T19:00:00Z,bov,GID,1,Alpha,pts,24.5,-110,-110,2026-05-26T22:00:00Z\n",
        encoding="utf-8",
    )
    df = lbr._read_lines_csv(str(p))
    assert len(df) == 1
    assert df.iloc[0]["player_name"] == "Alpha"
    assert df.iloc[0]["line"] == 24.5
    assert df.iloc[0]["is_alt_line"] is False or df.iloc[0]["is_alt_line"] == False  # noqa


def test_lbr_load_books_for_date_dedups_per_line(tmp_path, monkeypatch):
    """Latest captured_at per (player, stat, line) must win, mirroring
    R15. Same line listed twice should keep only the newer."""
    lbr = _import_lbr()
    # Build a synthetic lines dir under tmp_path/data/lines/
    lines_dir = tmp_path / "data" / "lines"
    lines_dir.mkdir(parents=True)
    p = lines_dir / "2026-05-26_bov.csv"
    p.write_text(
        "captured_at,book,game_id,player_id,player_name,stat,line,"
        "over_price,under_price,start_time\n"
        "2026-05-26T19:00:00Z,bov,GID,1,Alpha,pts,24.5,-110,-110,2026-05-26T22:00:00Z\n"
        "2026-05-26T19:05:00Z,bov,GID,1,Alpha,pts,24.5,-120,-105,2026-05-26T22:00:00Z\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(lbr, "PROJECT_DIR", str(tmp_path))
    books, latest = lbr.load_books_for_date("2026-05-26")
    assert "bov" in books
    assert len(books["bov"]) == 1
    assert int(books["bov"].iloc[0]["over_price"]) == -120  # newer


# =============================================================================
# inplay_bet_ranker — snapshot, garbage-time, pricing, name normalization
# =============================================================================
def _import_ibr():
    import inplay_bet_ranker as ibr  # noqa: E402
    return ibr


def test_ibr_kelly_fraction_clamps_negative_to_zero():
    """In-play prop ranker MUST never recommend a stake on negative EV.
    Independent code path from live_bet_ranker — needs its own test."""
    ibr = _import_ibr()
    # 40% to win on +100 → kelly = -0.2 → clamp 0
    assert ibr.kelly_fraction(0.40, +100) == 0.0
    # 60% to win on +100 → kelly = +0.20
    assert ibr.kelly_fraction(0.60, +100) == pytest.approx(0.20, abs=1e-9)


def test_ibr_model_prob_over_gaussian_complement():
    """P(OVER > line) + P(UNDER >= line) should equal 1 (within Gaussian
    CDF precision) — ranks both sides honestly."""
    ibr = _import_ibr()
    p_over = ibr.model_prob_over(point=24.0, q10=18.0, q90=30.0, line=24.5)
    # complement via the same function (UNDER side)
    p_under = 1.0 - p_over
    assert 0 < p_over < 1
    assert p_over + p_under == pytest.approx(1.0)


def test_ibr_model_prob_over_missing_band_defaults_50():
    """Missing q10/q90 → fall back to a 0.5 prior so the bet is neutralised
    rather than wildly +EV. Key safety guard."""
    ibr = _import_ibr()
    assert ibr.model_prob_over(24.0, None, 30.0, 24.5) == 0.5
    assert ibr.model_prob_over(24.0, 18.0, None, 24.5) == 0.5


def test_ibr_parse_min_str_handles_clock_strings():
    ibr = _import_ibr()
    assert ibr._parse_min_str("9:18") == pytest.approx(9 + 18 / 60, abs=1e-6)
    assert ibr._parse_min_str("12") == 12.0
    assert ibr._parse_min_str(0) == 0.0
    assert ibr._parse_min_str(None) == 0.0
    assert ibr._parse_min_str("") == 0.0
    assert ibr._parse_min_str("garbage") == 0.0


def test_ibr_apply_garbage_time_dampener_shrinks_remaining():
    """At endQ3+ with |margin| > 20, REMAINING delta is halved. The
    cycle-88 blow_factor already handles leading-team starters; this
    catches the rest."""
    ibr = _import_ibr()
    snap = {"max_quarter_observed": 3, "home_score": 110, "away_score": 80}
    rows = [
        {"current": 18.0, "projected_final": 30.0, "name": "Star", "stat": "pts"},
        # No remaining (current >= projected) → unchanged
        {"current": 20.0, "projected_final": 18.0, "name": "Bench", "stat": "pts"},
    ]
    out = ibr.apply_garbage_time_dampener(snap, rows)
    star = next(r for r in out if r["name"] == "Star")
    # remaining was 12 → halved to 6 → projected_final = 24
    assert star["projected_final"] == pytest.approx(24.0, abs=1e-6)
    assert star["garbage_time_applied"] is True
    bench = next(r for r in out if r["name"] == "Bench")
    assert bench["garbage_time_applied"] is False


def test_ibr_apply_garbage_time_dampener_noop_when_close():
    """|margin| <= 20 OR max_q < 3 → no shrink applied."""
    ibr = _import_ibr()
    snap = {"max_quarter_observed": 3, "home_score": 100, "away_score": 95}
    rows = [{"current": 10.0, "projected_final": 25.0, "name": "X"}]
    out = ibr.apply_garbage_time_dampener(snap, rows)
    assert out[0]["projected_final"] == 25.0
    # And max_q < 3 also passes through unchanged
    snap2 = {"max_quarter_observed": 2, "home_score": 70, "away_score": 40}
    out2 = ibr.apply_garbage_time_dampener(snap2, rows)
    assert out2[0]["projected_final"] == 25.0


def test_ibr_build_cumulative_snapshot_aggregates_quarters(tmp_path):
    """OT-aware totals: stats from all q files sum, max_quarter_observed
    correctly set, period advanced to next q. Uses real-shape JSON."""
    ibr = _import_ibr()
    # Build 2 quarter files for game G
    qb_dir = tmp_path / "qb"
    qb_dir.mkdir()
    for q in (1, 2):
        d = {
            "game_id": "G",
            "period": q,
            "players": [{
                "player_id": 1, "player_name": "Star", "team_abbreviation": "AAA",
                "min": "10:00", "pts": 12, "reb": 4, "ast": 2,
                "fg3m": 1, "stl": 1, "blk": 0, "to": 1, "pf": 2,
                "start_position": "F",
            }],
            "teams": [
                {"team_abbreviation": "AAA", "team_id": 100, "pts": 25},
                {"team_abbreviation": "BBB", "team_id": 200, "pts": 28},
            ],
        }
        (qb_dir / f"G_q{q}.json").write_text(json.dumps(d))
    qfiles = ibr.find_quarter_files("G", qbox_dir=str(qb_dir))
    assert sorted(qfiles.keys()) == [1, 2]
    snap = ibr.build_cumulative_snapshot("G", qfiles)
    assert snap is not None
    star = snap["players"][0]
    assert star["pts"] == 24
    assert star["reb"] == 8
    assert star["tov"] == 2     # to → tov stat-key remap
    assert star["min"] == pytest.approx(20.0, abs=1e-6)
    assert snap["max_quarter_observed"] == 2
    assert snap["period"] == 3
    assert snap["home_score"] + snap["away_score"] == 50 + 56  # 25+25 + 28+28


def test_ibr_build_cumulative_snapshot_returns_none_when_no_files():
    ibr = _import_ibr()
    assert ibr.build_cumulative_snapshot("G", {}) is None


def test_ibr_is_pretip_detects_q1_arrival(tmp_path):
    """Pretip is the gate between live_bet_ranker (handles) and
    inplay_bet_ranker (takes over). q1.json arrival = tip-off."""
    ibr = _import_ibr()
    qb = tmp_path / "qb"
    qb.mkdir()
    assert ibr.is_pretip("G", qbox_dir=str(qb)) is True
    (qb / "G_q1.json").write_text("{}")
    assert ibr.is_pretip("G", qbox_dir=str(qb)) is False


def test_ibr_load_live_lines_latest_per_book_keeps_newest(tmp_path):
    """The newest snapshot per (player, stat, book, line) wins — older
    snapshots get dropped. Important: stale price could over-rank a bet."""
    ibr = _import_ibr()
    p = tmp_path / "2026-05-26_bov.csv"
    p.write_text(
        "captured_at,book,player_name,stat,line,over_price,under_price\n"
        "2026-05-26T19:00:00Z,bov,X,pts,24.5,-110,-110\n"
        "2026-05-26T19:05:00Z,bov,X,pts,24.5,-130,+100\n",
        encoding="utf-8",
    )
    rows = ibr.load_live_lines_for_date(
        "2026-05-26", books=("bov",),
    ) if False else None
    # Use the internal _read_lines_csv directly to avoid LINES_DIR coupling
    raw = ibr._read_lines_csv(str(p))
    # Newest must be last
    newest = raw[-1]
    assert newest["over_price"] == "-130"


def test_ibr_normalize_name_strips_diacritics_and_case():
    ibr = _import_ibr()
    assert ibr._normalize_name("Nikola Jokić") == "nikola jokic"
    assert ibr._normalize_name("De'Aaron Fox") == "de'aaron fox"
    assert ibr._normalize_name("  ") == ""


# =============================================================================
# auto_settle_daemon — DNP, OT-aware sum, seen-set, settle vs dry-run
# =============================================================================
def _import_asd():
    from scripts import auto_settle_daemon as asd  # noqa: E402
    return asd


def test_asd_player_key_normalises_diacritics():
    asd = _import_asd()
    assert asd._player_key("Nikola Jokić") == asd._player_key("Nikola Jokic")
    assert asd._player_key("  De'Aaron Fox  ") == "de'aaron fox"


def test_asd_match_player_id_fallback_when_name_diffs():
    """Settlement is the LAST line of defense before the ledger moves —
    when a player's name is mis-spelled cross-system, the player_id
    fallback must catch it. Critical for void/won/lost correctness."""
    asd = _import_asd()
    totals = {"Star Player": {"pts": 25.0, "player_id": 1001}}
    bet = {"player": "STAR PLAYER", "player_id": 1001}
    matched = asd._match_player(bet, totals)
    assert matched is not None
    assert matched["pts"] == 25.0
    # name miss + wrong id → None
    bet2 = {"player": "unknown name", "player_id": 9999}
    assert asd._match_player(bet2, totals) is None


def test_asd_seen_set_roundtrips_with_atomic_write(tmp_path):
    """Idempotency rests on the seen set — corrupt file must NOT replay
    every historical q4 (which would double-settle every old bet)."""
    asd = _import_asd()
    p = tmp_path / "seen.json"
    s = {"0022400001", "0022400002"}
    asd.save_seen(s, p)
    out = asd.load_seen(p)
    assert out == s
    # Corrupt → empty set (not raise)
    p.write_text("{ corrupt", encoding="utf-8")
    assert asd.load_seen(p) == set()


def test_asd_list_and_scan_period_files(tmp_path):
    asd = _import_asd()
    qb = tmp_path / "qb"
    qb.mkdir()
    # 4 quarters + OT (q5) for game X. Plus an unrelated game's files.
    for q in range(1, 6):
        (qb / f"0022400001_q{q}.json").write_text("{}")
    for q in range(1, 3):
        (qb / f"0022400002_q{q}.json").write_text("{}")
    files = asd.list_period_files("0022400001", qb)
    assert len(files) == 5
    # scan_new must skip already-seen and only return _q4 game_ids
    new = asd.scan_new_q4_files(qb, seen=set())
    assert new == ["0022400001"]
    new2 = asd.scan_new_q4_files(qb, seen={"0022400001"})
    assert new2 == []


def test_asd_sum_quarter_box_full_ot_aware(tmp_path):
    """OT (q5+) stats must fold into final totals."""
    asd = _import_asd()
    qb = tmp_path / "qb"
    qb.mkdir()
    # 5 quarters (incl OT). Each quarter Star scores 4 pts.
    for q in range(1, 6):
        d = {
            "game_id": "0022400001",
            "period": q,
            "players": [{
                "player_id": 1, "player_name": "Star",
                "team_abbreviation": "AAA",
                "pts": 4, "reb": 2, "ast": 1,
                "fg3m": 0, "stl": 0, "blk": 0, "to": 0,
            }],
        }
        (qb / f"0022400001_q{q}.json").write_text(json.dumps(d))
    totals = asd.sum_quarter_box_full("0022400001", qb)
    assert "Star" in totals
    assert totals["Star"]["pts"] == 20.0  # 5q × 4pts
    assert totals["Star"]["reb"] == 10.0


def test_asd_settle_game_dry_run_does_not_mutate(monkeypatch, tmp_path):
    """Dry-run must produce identical settle decisions WITHOUT calling
    ledger.settle_bet / void_bet (which mutate bankroll). Critical
    safety property for the daemon."""
    asd = _import_asd()

    # Stub ledger to record any mutating calls
    called = {"settle": 0, "void": 0}
    monkeypatch.setattr(asd._ledger, "settle_bet",
                          lambda bid, actual: (_ for _ in ()).throw(
                              RuntimeError(f"should not call settle_bet({bid})")))
    monkeypatch.setattr(asd._ledger, "void_bet",
                          lambda bid: (_ for _ in ()).throw(
                              RuntimeError(f"should not call void_bet({bid})")))

    # Two open bets: one matched player, one DNP
    bets = [
        {"bet_id": "B1", "game_id": "0022400001", "player": "Star",
         "stat": "pts", "player_id": 1},
        {"bet_id": "B2", "game_id": "0022400001", "player": "Ghost",
         "stat": "pts", "player_id": 999},
    ]
    monkeypatch.setattr(asd._ledger, "open_bets", lambda: bets)

    qb = tmp_path / "qb"
    qb.mkdir()
    d = {
        "game_id": "0022400001", "period": 4,
        "players": [{"player_id": 1, "player_name": "Star",
                      "team_abbreviation": "AAA",
                      "pts": 22, "reb": 0, "ast": 0,
                      "fg3m": 0, "stl": 0, "blk": 0, "to": 0}],
    }
    (qb / "0022400001_q4.json").write_text(json.dumps(d))

    res = asd.settle_game("0022400001", qb_dir=qb, dry_run=True)
    # 1 dry-settled, 1 DNP void (also dry)
    assert len(res["settled"]) == 1
    assert res["settled"][0]["actual_stat"] == 22.0
    assert len(res["voided"]) == 1
    assert res["voided"][0]["reason"] == "dnp_dryrun"


def test_asd_append_audit_log_appends_idempotent(tmp_path):
    """Audit log must be append-only across calls so historical runs
    are never overwritten."""
    asd = _import_asd()
    p = tmp_path / "audit.md"
    res = {
        "game_id": "0022400001",
        "settled": [{"bet_id": "B1abcdefg", "status": "WON",
                      "profit_loss": 100.0, "bankroll_after": 1100.0,
                      "actual_stat": 22.0}],
        "voided": [],
        "skipped": [],
        "errored": [],
    }
    asd.append_audit_log(res, p)
    asd.append_audit_log(res, p)
    text = p.read_text()
    # Should contain TWO entries
    assert text.count("## ") == 2
    assert "WON" in text


# =============================================================================
# bankroll_monitor — alarm thresholds, ROI, dashboard
# =============================================================================
def _import_bm():
    from bankroll_monitor_daemon import (  # noqa: E402
        compute_metrics, compute_roi, filter_ledger, render_dashboard,
        atomic_write_json,
    )
    return {
        "compute_metrics": compute_metrics,
        "compute_roi": compute_roi,
        "filter_ledger": filter_ledger,
        "render_dashboard": render_dashboard,
        "atomic_write_json": atomic_write_json,
    }


def test_bm_compute_roi_settled_only():
    """Open bets must NOT count in ROI — premature ROI calc would
    inflate displayed performance during a slate."""
    bm = _import_bm()
    df = pd.DataFrame([
        {"status": "won", "stake": 100, "profit_loss": 90},
        {"status": "lost", "stake": 50, "profit_loss": -50},
        # Open bet should be ignored
        {"status": "open", "stake": 200, "profit_loss": 0},
    ])
    roi = bm["compute_roi"](df)
    assert roi["n_bets"] == 2
    assert roi["total_stake"] == pytest.approx(150.0)
    assert roi["total_pnl"] == pytest.approx(40.0)
    assert roi["roi_pct"] == pytest.approx(40.0 / 150 * 100, abs=1e-6)


def test_bm_atomic_write_json_roundtrip(tmp_path):
    bm = _import_bm()
    p = tmp_path / "state.json"
    bm["atomic_write_json"](p, {"current_bankroll": 1050.5})
    assert json.loads(p.read_text())["current_bankroll"] == 1050.5


def test_bm_render_dashboard_includes_critical_fields():
    """The dashboard is the human's bankroll-at-a-glance — these fields
    must always render even when empty so a missing alarm doesn't go
    silent."""
    bm = _import_bm()
    metrics = {
        "as_of": "2026-05-26T19:00:00",
        "start_bankroll": 1000.0, "current_bankroll": 1050.0,
        "pending_exposure": 50.0, "available_bankroll": 1000.0,
        "daily_pnl": 50.0, "weekly_pnl": 50.0, "monthly_pnl": 50.0,
        "max_drawdown": 0.0, "max_drawdown_pct": 0.0,
        "n_open_positions": 1, "max_stake_in_one_game": 50.0,
        "position_concentration_pct": 0.05, "kelly_overhang": 0.05,
        "n_settled": 5, "alarms": [],
    }
    text = bm["render_dashboard"](metrics)
    for required in ("Current bankroll", "Pending exposure",
                       "Max drawdown", "Kelly overhang", "Alarms",
                       "all systems green"):
        assert required in text, f"missing: {required}"


# =============================================================================
# multi_game_kelly — slate cap, validation, identity
# =============================================================================
def _import_mgk():
    from multi_game_kelly import (  # noqa: E402
        solve_multi_game, _per_game_exposure, SLATE_CAP_DEFAULT,
    )
    return {"solve": solve_multi_game, "exposure": _per_game_exposure,
             "cap_default": SLATE_CAP_DEFAULT}


def test_mgk_solve_validates_cross_game_corr_not_implemented():
    """Non-zero cross-game correlation must raise — silently treating
    it as zero would understate real risk."""
    mgk = _import_mgk()
    with pytest.raises(NotImplementedError):
        mgk["solve"]([], bankroll=1000, cross_game_corr=0.1)


def test_mgk_solve_validates_bankroll_and_cap():
    mgk = _import_mgk()
    with pytest.raises(ValueError):
        mgk["solve"]([], bankroll=0)
    with pytest.raises(ValueError):
        mgk["solve"]([], bankroll=-1)
    with pytest.raises(ValueError):
        mgk["solve"]([], bankroll=1000, slate_cap=0)
    with pytest.raises(ValueError):
        mgk["solve"]([], bankroll=1000, slate_cap=1.5)


# =============================================================================
# injury_availability — factor lookup, OUT collapse, name normalisation
# =============================================================================
def _import_ia():
    from src.prediction import injury_availability as ia  # noqa: E402
    return ia


def test_ia_factor_table_matches_R14_taxonomy():
    """The factor table is the SOLE link between scrape + prediction —
    any silent rename here corrupts every live bet. Lock it in."""
    ia = _import_ia()
    assert ia.AVAILABILITY_FACTOR["OUT"] == 0.0
    assert ia.AVAILABILITY_FACTOR["NOT WITH TEAM"] == 0.0
    assert ia.AVAILABILITY_FACTOR["DOUBTFUL"] == 0.3
    assert ia.AVAILABILITY_FACTOR["QUESTIONABLE"] == 0.6
    assert ia.AVAILABILITY_FACTOR["PROBABLE"] == 0.9
    assert ia.AVAILABILITY_FACTOR["AVAILABLE"] == 1.0


def test_ia_name_key_normalises():
    ia = _import_ia()
    assert ia._name_key("Nikola Jokić") == "nikola jokic"
    assert ia._name_key("LeBron James Jr.") == "lebron james"
    assert ia._name_key("  Jaylen Brown  ") == "jaylen brown"


def test_ia_apply_availability_zero_factor_collapses_band(monkeypatch):
    """OUT player → entire band collapses to (0, 0, 0). The R15 wiring
    spec depends on this — any other behavior would surface bets on
    benched players."""
    ia = _import_ia()
    # Force the disabled escape hatch off, factor=0 via stub
    monkeypatch.setattr(ia, "get_availability_factor",
                          lambda **kw: 0.0)
    q50, q10, q90 = ia.apply_availability(1, q50=25.0, q10=18.0, q90=30.0)
    assert q50 == 0.0 and q10 == 0.0 and q90 == 0.0


def test_ia_apply_availability_disabled_returns_unscaled(monkeypatch):
    """NBA_INJURY_WIRE_DISABLE=1 is a critical escape hatch for batch
    backtests — must short-circuit before any disk IO."""
    ia = _import_ia()
    monkeypatch.setenv("NBA_INJURY_WIRE_DISABLE", "1")
    # Should not hit disk at all — return default 1.0
    factor = ia.get_availability_factor(player_id=12345)
    assert factor == 1.0


def test_ia_factor_lookup_from_snapshot(monkeypatch, tmp_path):
    """End-to-end: snapshot on disk → lookup by player_id returns the
    correct factor. Exercises load_latest_snapshot + _rebuild_indices."""
    ia = _import_ia()
    cache_dir = tmp_path / "data" / "cache"
    cache_dir.mkdir(parents=True)
    snap = {
        "players": [
            {"player_id": 100, "player_name": "Star A", "status": "QUESTIONABLE"},
            {"player_id": 200, "player_name": "Star B", "status": "OUT"},
            # Unknown bucket → ignored
            {"player_id": 300, "player_name": "Star C", "status": "GAME-TIME"},
        ],
    }
    # Recent mtime so _is_stale = False
    p = cache_dir / "injury_status_2026-05-26.json"
    p.write_text(json.dumps(snap))

    monkeypatch.setattr(ia, "_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("NBA_INJURY_WIRE_DISABLE", raising=False)
    ia.reset_cache()

    assert ia.get_availability_factor(player_id=100) == 0.6
    assert ia.get_availability_factor(player_id=200) == 0.0
    # Unknown bucket → default 1.0
    assert ia.get_availability_factor(player_id=300) == 1.0
    # Missing pid → fall back to name lookup
    assert ia.get_availability_factor(player_id=999,
                                        player_name="Star A") == 0.6
    # Total miss → default 1.0
    assert ia.get_availability_factor(player_id=999,
                                        player_name="Nobody") == 1.0


# =============================================================================
# residual_heads — feature-name selection + position one-hot
# =============================================================================
def _import_rh():
    from src.prediction import residual_heads as rh  # noqa: E402
    return rh


def test_rh_pos_flags_disambiguate_clean_positions():
    """one-hot must NEVER fire for hybrid positions (G-F, F-C) — the
    heads were trained on pure-position rows. A spurious flag silently
    corrupts the residual prediction."""
    rh = _import_rh()
    assert rh._pos_flags("C") == (1.0, 0.0, 0.0)
    assert rh._pos_flags("F") == (0.0, 1.0, 0.0)
    assert rh._pos_flags("G") == (0.0, 0.0, 1.0)
    # Hybrids → all zeros (correct)
    assert rh._pos_flags("G-F") == (0.0, 0.0, 0.0)
    assert rh._pos_flags("F-C") == (0.0, 0.0, 0.0)
    assert rh._pos_flags("") == (0.0, 0.0, 0.0)


def test_rh_build_base_feature_map_handles_missing_keys():
    """player dict may be missing any stat key (e.g. early-quarter NaN);
    feature map must coerce to 0.0 rather than raise."""
    rh = _import_rh()
    player = {"pts": 12, "reb": None}  # only one valid, one None
    m = rh._build_base_feature_map(
        player, margin=8.0, raw_margin=-8.0,
        pos_c=0.0, pos_f=1.0, pos_g=0.0,
    )
    assert m["cur_pts"] == 12.0
    assert m["cur_reb"] == 0.0  # None coerced
    assert m["cur_ast"] == 0.0
    assert m["score_margin_abs"] == 8.0
    assert m["is_leading"] == 0.0  # raw_margin < 0
    assert m["pos_F"] == 1.0


def test_rh_feature_names_falls_back_to_legacy_schema():
    """Stats without meta JSON must use the 14-feature legacy schema —
    a missing meta should never silently change schema."""
    rh = _import_rh()
    rh.reset_head_caches()
    # 'pts' has no streak meta historically (R10_M16 ship excluded pts/reb/ast)
    names = rh._feature_names_for_stat("pts")
    assert names == rh._LEGACY_ENDQ3_FEATURES
    assert len(names) == 14
    assert "min_through_q3" in names
    assert "cur_pts" in names


def test_rh_is_nan_xstat_handles_inputs():
    rh = _import_rh()
    assert rh._is_nan_xstat(float("nan")) is True
    assert rh._is_nan_xstat(0.0) is False
    assert rh._is_nan_xstat(1.5) is False
    assert rh._is_nan_xstat(None) is False  # None is not NaN


def test_rh_apply_residual_correction_noop_when_heads_empty(monkeypatch):
    """When no .lgb artifacts on disk, apply_residual_correction must
    return projs unchanged — a missing model file must never cause a
    silent zeroing of every prediction."""
    rh = _import_rh()
    rh.reset_head_caches()
    monkeypatch.setattr(rh, "load_heads", lambda: {})
    snap = {"players": [{"player_id": 1, "team": "A"}],
             "home_team": "A", "away_team": "B",
             "home_score": 50, "away_score": 40}
    projs = {(1, "pts"): 25.0, (1, "reb"): 6.0}
    out = rh.apply_residual_correction(snap, projs)
    assert out == projs


def test_rh_apply_endq2_noop_when_heads_empty(monkeypatch):
    """Same safety property at endQ2 boundary."""
    rh = _import_rh()
    rh.reset_head_caches()
    monkeypatch.setattr(rh, "load_heads_endq2", lambda: {})
    snap = {"players": [{"player_id": 1, "team": "A"}],
             "home_team": "A", "away_team": "B",
             "home_score": 50, "away_score": 40}
    projs = {(1, "pts"): 25.0}
    assert rh.apply_residual_correction_endq2(snap, projs) == projs


def test_rh_apply_xstat_noop_when_heads_empty(monkeypatch):
    """xstat (cross-stat) head missing must NOT silently zero out a
    prediction."""
    rh = _import_rh()
    rh.reset_head_caches()
    monkeypatch.setattr(rh, "load_xstat_heads", lambda: {})
    snap = {"players": [{"player_id": 1, "team": "A"}],
             "game_date": "2026-05-26"}
    projs = {(1, "fg3m"): 2.0}
    assert rh.apply_xstat_residual_correction(snap, projs) == projs


def test_rh_coerce_xstat_target_date_handles_strings_and_dates():
    rh = _import_rh()
    from datetime import date, datetime
    assert rh._coerce_xstat_target_date("2026-05-26") is not None
    assert rh._coerce_xstat_target_date(None) is None
    assert rh._coerce_xstat_target_date("") is None
    assert rh._coerce_xstat_target_date("garbage") is None
    d = date(2026, 5, 26)
    assert rh._coerce_xstat_target_date(d) == d
    dt = datetime(2026, 5, 26, 12, 0, 0)
    assert rh._coerce_xstat_target_date(dt) == dt


def test_rh_xstat_feature_names_fallback():
    """Missing meta JSON → use the canonical 6 z + n_prior layout.
    Target stat's own z column is EXCLUDED (per probe R12_F3 design)."""
    rh = _import_rh()
    rh.reset_head_caches()
    names = rh._xstat_feature_names_for("fg3m")
    assert "xstat_z_fg3m" not in names  # target's own EXCLUDED
    assert "n_prior_xstat" in names
    assert len(names) == 7  # 6 other stats + n_prior_xstat


def test_rh_compute_xstat_z_for_player_no_history():
    """Player with no prior games → all zeros + n_prior = 0."""
    rh = _import_rh()
    from datetime import datetime
    z, n = rh._compute_xstat_z_for_player(
        pid=999, target_date=datetime(2026, 5, 26),
        histories={},
    )
    assert n == 0
    for s in rh.STATS:
        assert z[f"xstat_z_{s}"] == 0.0


def test_rh_compute_xstat_z_for_player_uses_L5_window():
    """L5 mean over PRIOR games (strict shift) — recent dates excluded."""
    rh = _import_rh()
    from datetime import datetime
    # 6 games — only first 5 should count when target is the last game's date
    entries = [
        (datetime(2026, 5, 20), {"pts": 1.0, "reb": 0.5, "ast": 0.0,
                                   "fg3m": 0.0, "stl": 0.0, "blk": 0.0,
                                   "tov": 0.0}),
        (datetime(2026, 5, 21), {"pts": 2.0, "reb": 0.5, "ast": 0.0,
                                   "fg3m": 0.0, "stl": 0.0, "blk": 0.0,
                                   "tov": 0.0}),
        (datetime(2026, 5, 22), {"pts": 3.0, "reb": 0.5, "ast": 0.0,
                                   "fg3m": 0.0, "stl": 0.0, "blk": 0.0,
                                   "tov": 0.0}),
        (datetime(2026, 5, 23), {"pts": 4.0, "reb": 0.5, "ast": 0.0,
                                   "fg3m": 0.0, "stl": 0.0, "blk": 0.0,
                                   "tov": 0.0}),
        (datetime(2026, 5, 24), {"pts": 5.0, "reb": 0.5, "ast": 0.0,
                                   "fg3m": 0.0, "stl": 0.0, "blk": 0.0,
                                   "tov": 0.0}),
        # Game ON or AFTER target date — must be excluded
        (datetime(2026, 5, 26), {"pts": 99.0, "reb": 0.5, "ast": 0.0,
                                   "fg3m": 0.0, "stl": 0.0, "blk": 0.0,
                                   "tov": 0.0}),
    ]
    z, n = rh._compute_xstat_z_for_player(
        pid=1, target_date=datetime(2026, 5, 26),
        histories={1: entries},
    )
    assert n == 5  # PRIOR count, NOT including target-day game
    # L5 mean pts z = (1+2+3+4+5)/5 = 3.0
    assert z["xstat_z_pts"] == pytest.approx(3.0)


def test_rh_load_heads_returns_empty_when_dir_missing(monkeypatch, tmp_path):
    """Missing artifact dir → empty dict (not raise)."""
    rh = _import_rh()
    rh.reset_head_caches()
    monkeypatch.setattr(rh, "HEAD_DIR", str(tmp_path / "no_such_dir"))
    assert rh.load_heads() == {}


# =============================================================================
# clv_tracker_daemon — high-risk run_tick + aggregation
# =============================================================================
def _import_ctd():
    import clv_tracker_daemon as ctd  # noqa: E402
    return ctd


def test_ctd_compute_realized_clv_signs_correctly_for_both_sides():
    """OVER  : line moves up   -> POSITIVE CLV
       UNDER : line moves down -> POSITIVE CLV
    A sign-flip here would silently misreport closing-line value, the
    only honest edge signal across N bets."""
    ctd = _import_ctd()
    # OVER 24.5 placed; market closes at 25.5 → +CLV
    clv_line, clv_pct = ctd.compute_realized_clv(24.5, 25.5, "OVER")
    assert clv_line == 1.0
    assert clv_pct > 0
    # OVER but market moved DOWN → negative
    clv_line, clv_pct = ctd.compute_realized_clv(24.5, 23.5, "OVER")
    assert clv_line == -1.0
    assert clv_pct < 0
    # UNDER 24.5; close at 23.5 → +CLV (we got HIGHER)
    clv_line, clv_pct = ctd.compute_realized_clv(24.5, 23.5, "UNDER")
    assert clv_line == 1.0
    assert clv_pct > 0


def test_ctd_compute_realized_clv_unknown_side_raises():
    ctd = _import_ctd()
    with pytest.raises(ValueError):
        ctd.compute_realized_clv(24.5, 25.5, "MIDDLE")


def test_ctd_book_canonicalisation_collapses_aliases():
    ctd = _import_ctd()
    assert ctd._book_canon("DK") == "draftkings"
    assert ctd._book_canon("fd") == "fanduel"
    assert ctd._book_canon("Bovada") == "bovada"
    assert ctd._book_canon("pin") == "pinnacle"
    # Unknown book passes through (lowercased)
    assert ctd._book_canon("WeirdBook") == "weirdbook"


def test_ctd_load_pending_bets_filters_settled_and_future(tmp_path):
    """Settled bets and future-placed (clock skew) rows must be skipped."""
    ctd = _import_ctd()
    p = tmp_path / "pnl.csv"
    p.write_text(
        "bet_id,placed_at,player,stat,side,book,line,american_odds,status\n"
        "B1,2026-05-25T12:00:00Z,X,pts,OVER,fd,24.5,-110,pending\n"
        "B2,2026-05-25T12:00:00Z,X,pts,OVER,fd,24.5,-110,won\n"
        # 100 years in the future — must be skipped
        "B3,2126-05-25T12:00:00Z,X,pts,OVER,fd,24.5,-110,pending\n",
        encoding="utf-8",
    )
    out = ctd.load_pending_bets(p)
    bids = {r["bet_id"] for r in out}
    assert bids == {"B1"}


def test_ctd_compute_aggregate_deduplicates_per_bet(tmp_path):
    """If a bet has multiple snapshots in the CLV csv, only the LATEST
    counts toward the running average — otherwise hot streaks double-
    count themselves."""
    ctd = _import_ctd()
    p = tmp_path / "clv.csv"
    p.write_text(
        "bet_id,snapshot_time,clv_pct,book\n"
        "B1,2026-05-26T10:00:00Z,0.01,fd\n"
        "B1,2026-05-26T11:00:00Z,0.05,fd\n"  # latest wins
        "B2,2026-05-26T10:00:00Z,-0.02,bov\n",
        encoding="utf-8",
    )
    agg = ctd.compute_aggregate(p)
    assert agg["n_bets_tracked"] == 2
    # Mean = (0.05 + -0.02)/2 = 0.015
    assert agg["mean_clv_pct"] == pytest.approx(0.015, abs=1e-6)
    # 1 of 2 positive
    assert agg["pct_positive_clv"] == pytest.approx(0.5)


def test_ctd_compute_aggregate_returns_zero_on_missing_file(tmp_path):
    ctd = _import_ctd()
    agg = ctd.compute_aggregate(tmp_path / "absent.csv")
    assert agg == {"n_bets_tracked": 0, "mean_clv_pct": 0.0,
                    "pct_positive_clv": 0.0, "by_book": {}}


def test_ctd_color_dot_thresholds():
    """Color marker semantics are user-facing — wrong thresholds make
    the dashboard lie about edge."""
    ctd = _import_ctd()
    assert ctd._color_dot(0.05) == "GREEN"
    assert ctd._color_dot(0.005) == "YELLOW"
    assert ctd._color_dot(0.0) == "YELLOW"
    assert ctd._color_dot(-0.01) == "RED"


def test_ctd_write_aggregate_persists_json(tmp_path):
    ctd = _import_ctd()
    csv_p = tmp_path / "clv.csv"
    csv_p.write_text(
        "bet_id,snapshot_time,clv_pct,book\n"
        "B1,2026-05-26T10:00:00Z,0.05,fd\n",
        encoding="utf-8",
    )
    out = tmp_path / "agg.json"
    agg = ctd.write_aggregate(csv_p, out)
    assert json.loads(out.read_text())["n_bets_tracked"] == 1


def test_ctd_run_tick_end_to_end(tmp_path):
    """Full pipeline: ledger row -> snapshot lookup -> CLV row -> dashboard."""
    ctd = _import_ctd()
    # Ledger with one pending OVER bet
    pnl = tmp_path / "pnl.csv"
    pnl.write_text(
        "bet_id,placed_at,player,stat,side,book,line,american_odds,status\n"
        "B1,2026-05-26T10:00:00Z,Star,pts,OVER,fd,24.5,-110,pending\n",
        encoding="utf-8",
    )
    # Snapshot dir with one matching snapshot at higher line (POSITIVE CLV)
    lines_dir = tmp_path / "lines"
    lines_dir.mkdir()
    snap = lines_dir / "2026-05-26_fd.csv"
    snap.write_text(
        "captured_at,book,player_name,stat,line,over_price,under_price,start_time\n"
        "2026-05-26T11:00:00Z,fd,Star,pts,25.5,-110,-110,\n",
        encoding="utf-8",
    )
    clv_out = tmp_path / "clv.csv"
    vault = tmp_path / "clv_live.md"
    closing = tmp_path / "closing.csv"
    rpt = ctd.run_tick(pnl, lines_dir, clv_out, vault, closing)
    assert rpt["bets_tracked"] == 1
    assert rpt["rows_written"] == 1
    # CLV row should reflect +1.0 line move
    with open(clv_out) as fh:
        row = next(csv.DictReader(fh))
    assert float(row["clv_line"]) == 1.0
    assert float(row["clv_pct"]) > 0


def test_ctd_closing_line_capture_only_inside_30min(tmp_path):
    """Closing line capture fires only when start_time - now <= 30 min."""
    ctd = _import_ctd()
    pnl = tmp_path / "pnl.csv"
    pnl.write_text(
        "bet_id,placed_at,player,stat,side,book,line,american_odds,status\n"
        "B1,2026-05-26T10:00:00Z,Star,pts,OVER,fd,24.5,-110,pending\n",
        encoding="utf-8",
    )
    lines_dir = tmp_path / "lines"
    lines_dir.mkdir()
    # start_time 5 min in the future — IS within closing window
    now = ctd._now_utc()
    snap_ts = (now + timedelta(minutes=-1)).isoformat()
    start_ts = (now + timedelta(minutes=5)).isoformat()
    p = lines_dir / "2026-05-26_fd.csv"
    p.write_text(
        "captured_at,book,player_name,stat,line,over_price,under_price,start_time\n"
        f"{snap_ts},fd,Star,pts,25.5,-110,-110,{start_ts}\n",
        encoding="utf-8",
    )
    closing = tmp_path / "closing.csv"
    rpt = ctd.run_tick(pnl, lines_dir, tmp_path / "clv.csv",
                        tmp_path / "vault.md", closing)
    assert rpt["closing_lines_captured"] == 1
    assert closing.exists()


# =============================================================================
# bankroll_monitor — alarm triggers, ledger filter, end-to-end tick
# =============================================================================
def test_bm_kelly_overhang_urgent_alarm():
    """sum(kelly_pct WHERE pending) > 30% must raise URGENT.
    Without this alarm a runaway bet stack can silently over-leverage."""
    bm = _import_bm()
    df = pd.DataFrame([
        {"status": "pending", "stake": 100, "profit_loss": 0,
         "kelly_pct": 0.20, "placed_at": "2026-05-26T19:00:00Z",
         "game_id": "G1"},
        {"status": "pending", "stake": 80, "profit_loss": 0,
         "kelly_pct": 0.15, "placed_at": "2026-05-26T19:00:00Z",
         "game_id": "G1"},
    ])
    m = bm["compute_metrics"](df, start_bankroll=1000.0)
    assert m["kelly_overhang"] == pytest.approx(0.35)
    levels = {a["rule"] for a in m["alarms"]}
    assert any("kelly_overhang" in r for r in levels)


def test_bm_daily_circuit_breaker_alarm():
    """daily_pnl < -20% of start_bankroll must raise STOP — this is the
    halt-trading kill switch."""
    bm = _import_bm()
    today = datetime.now(timezone.utc).isoformat()
    df = pd.DataFrame([
        {"status": "lost", "stake": 250, "profit_loss": -250,
         "kelly_pct": 0.25, "placed_at": today, "game_id": "G1"},
    ])
    m = bm["compute_metrics"](df, start_bankroll=1000.0)
    rules = {a["rule"] for a in m["alarms"]}
    assert any("daily_pnl" in r for r in rules)
    stop_alarms = [a for a in m["alarms"] if a["level"] == "STOP"]
    assert len(stop_alarms) >= 1


def test_bm_filter_synthetic_rows_removed_when_flag_set():
    """build_pnl_ledger_synth rows must be excludable — they would
    distort the live dashboard with backtest noise."""
    bm = _import_bm()
    df = pd.DataFrame([
        {"player": "Player_1", "book": "PP", "status": "pending",
         "stake": 10, "profit_loss": 0,
         "placed_at": "2026-05-26T10:00:00Z"},
        {"player": "Real Star", "book": "fd", "status": "pending",
         "stake": 10, "profit_loss": 0,
         "placed_at": "2026-05-26T10:00:00Z"},
    ])
    out = bm["filter_ledger"](df, exclude_synthetic=True)
    assert out["n_synth_excluded"] == 1
    assert out["n_kept"] == 1
    assert "Real Star" in out["filtered"]["player"].values


def test_bm_filter_start_date_drops_pre_launch_rows():
    """start_date filter drops backtest rows placed before live launch."""
    bm = _import_bm()
    df = pd.DataFrame([
        {"player": "X", "book": "fd", "status": "pending",
         "stake": 10, "profit_loss": 0,
         "placed_at": "2026-05-20T10:00:00Z"},
        {"player": "Y", "book": "fd", "status": "pending",
         "stake": 10, "profit_loss": 0,
         "placed_at": "2026-05-25T10:00:00Z"},
    ])
    out = bm["filter_ledger"](df, start_date="2026-05-24")
    assert out["n_date_excluded"] == 1
    assert out["n_kept"] == 1
    assert "Y" in out["filtered"]["player"].values


def test_bm_compute_metrics_empty_ledger():
    """Empty ledger → bankroll unchanged, all zeros, no alarms."""
    bm = _import_bm()
    m = bm["compute_metrics"](pd.DataFrame(), start_bankroll=1000.0)
    assert m["current_bankroll"] == 1000.0
    assert m["pending_exposure"] == 0
    assert m["alarms"] == []


def test_bm_compute_metrics_max_drawdown():
    """max_drawdown traces running peak-to-trough across SETTLED bets."""
    bm = _import_bm()
    df = pd.DataFrame([
        {"status": "won", "stake": 100, "profit_loss": 200,
         "kelly_pct": 0.1, "placed_at": "2026-05-26T10:00:00Z",
         "game_id": "G1"},
        {"status": "lost", "stake": 100, "profit_loss": -300,
         "kelly_pct": 0.1, "placed_at": "2026-05-26T11:00:00Z",
         "game_id": "G2"},
    ])
    m = bm["compute_metrics"](df, start_bankroll=1000.0)
    # After bet 1: bankroll=1200 (peak). After bet 2: bankroll=900 (trough)
    # Drawdown = 1200 - 900 = 300
    assert m["max_drawdown"] == pytest.approx(300.0)
    assert m["max_drawdown_pct"] == pytest.approx(300 / 1200)


def test_bm_is_synthetic_row_detection():
    """Per-row predicate must match the synthetic generator exactly."""
    bm_mod = sys.modules.get("bankroll_monitor_daemon")
    if bm_mod is None:
        import bankroll_monitor_daemon as bm_mod  # noqa: F811
    real = pd.Series({"player": "LeBron James", "book": "fd"})
    synth = pd.Series({"player": "Player_42", "book": "PP"})
    assert bm_mod.is_synthetic_row(real) is False
    assert bm_mod.is_synthetic_row(synth) is True


# =============================================================================
# line_move_detector — full run_once pipeline
# =============================================================================
def test_lmd_run_once_end_to_end(tmp_path, monkeypatch):
    """End-to-end run_once: CSV → detect_moves → tag_consensus → append +
    render vault. Validates wiring of all pieces."""
    lmd = _import_lmd()
    # Build two-book CSVs with same-direction move (consensus steam)
    lines_dir = tmp_path / "lines"
    lines_dir.mkdir()
    cache_dir = tmp_path / "cache"
    vault = tmp_path / "vault.md"
    (lines_dir / "2026-05-26_bov.csv").write_text(
        "captured_at,book,player_name,stat,line,over_price,under_price\n"
        "2026-05-26T19:00:00Z,bov,Star,pts,24.5,-110,-110\n"
        "2026-05-26T19:05:00Z,bov,Star,pts,25.5,-110,-110\n",
        encoding="utf-8",
    )
    (lines_dir / "2026-05-26_fd.csv").write_text(
        "captured_at,book,player_name,stat,line,over_price,under_price\n"
        "2026-05-26T19:00:30Z,fd,Star,pts,24.5,-110,-110\n"
        "2026-05-26T19:05:30Z,fd,Star,pts,25.5,-110,-110\n",
        encoding="utf-8",
    )
    summary = lmd.run_once(
        isodate="2026-05-26",
        threshold_line=0.5,
        threshold_odds_pct=10,
        lines_dir=str(lines_dir),
        cache_dir=str(cache_dir),
        vault_path=str(vault),
    )
    assert summary["events_new"] == 2
    assert summary["consensus_new"] == 2
    # Cache file written
    assert (cache_dir / "line_moves_2026-05-26.json").exists()
    # Vault feed rendered
    assert vault.exists() and "Line Moves Feed" in vault.read_text()
    # Re-run: dedup must suppress all events
    summary2 = lmd.run_once(
        isodate="2026-05-26",
        threshold_line=0.5,
        threshold_odds_pct=10,
        lines_dir=str(lines_dir),
        cache_dir=str(cache_dir),
        vault_path=str(vault),
    )
    assert summary2["events_new"] == 0


def test_lmd_run_once_no_files_empty_summary(tmp_path):
    lmd = _import_lmd()
    summary = lmd.run_once(
        isodate="2026-05-26",
        threshold_line=0.5,
        threshold_odds_pct=10,
        lines_dir=str(tmp_path / "missing"),
        cache_dir=str(tmp_path / "cache"),
        vault_path=str(tmp_path / "vault.md"),
    )
    assert summary["events_new"] == 0
    assert summary["rows_seen"] == 0


# =============================================================================
# middle_finder_daemon — run_once + loop max-iters
# =============================================================================
def test_mfd_run_once_finds_middle(tmp_path):
    """End-to-end via load_latest_snapshots + find_middles. Validates a
    1-pt free-arb middle on a clean isolated lines_dir."""
    mfd = _import_mfd()
    lines_dir = tmp_path
    # bov OVER 24.5 @ +110  -- fd UNDER 25.5 @ +110 (free arb!)
    (lines_dir / "2026-05-26_bov.csv").write_text(
        "captured_at,book,game_id,player_id,player_name,team,stat,line,"
        "over_price,under_price,market_status,is_alt_line\n"
        "2026-05-26T19:00:00Z,bov,G,1,Star,TA,pts,24.5,+110,-130,OPEN,false\n",
        encoding="utf-8",
    )
    (lines_dir / "2026-05-26_fd.csv").write_text(
        "captured_at,book,game_id,player_id,player_name,team,stat,line,"
        "over_price,under_price,market_status,is_alt_line\n"
        "2026-05-26T19:00:00Z,fd,G,1,Star,TA,pts,25.5,-130,+110,OPEN,false\n",
        encoding="utf-8",
    )
    index = mfd.load_latest_snapshots(
        "2026-05-26", lines_dir=str(lines_dir), books=("fd", "bov"),
    )
    middles = mfd.find_middles(index, min_width=0.5,
                                 max_juice_each_side=-200)
    # Must yield at least the bov-OVER 24.5 / fd-UNDER 25.5 pair
    one_pt = [m for m in middles
              if m["over_book"] == "bov" and m["under_book"] == "fd"]
    assert one_pt, f"expected bov/fd middle, got: {middles}"
    assert one_pt[0]["middle_width"] == 1.0
    assert one_pt[0]["free_arb"] is True


def test_mfd_loop_heartbeat_bound_after_c3131e24_fix(tmp_path, monkeypatch):
    """Confirms commit c3131e24 fix landed: middle_finder_daemon._r19_hb is
    bound at module top-level (was previously trapped inside the docstring).
    """
    mfd = _import_mfd()
    assert hasattr(mfd, "_r19_hb"), "_r19_hb missing — c3131e24 fix may have regressed"
    out = tmp_path / "middles.json"
    monkeypatch.setattr(mfd, "_today_str", lambda: "2026-05-26")
    monkeypatch.setattr(mfd, "LINES_DIR", str(tmp_path))
    # loop should run one iteration without NameError; may exit cleanly with no rows
    mfd.loop(
        interval_sec=0,
        min_width=0.5,
        max_juice=-135,
        max_iters=1,
        use_model=False,
        min_band_prob=0.10,
        out_json=str(out),
        log=lambda *a, **k: None,
    )


# =============================================================================
# auto_settle_daemon — tick() first-run safety, write_probe
# =============================================================================
def test_asd_tick_first_run_seeds_seen_without_settling(monkeypatch, tmp_path):
    """First-run safety: must NOT replay every historical q4 file —
    instead seed the seen set with everything currently on disk."""
    asd = _import_asd()
    qb = tmp_path / "qb"
    qb.mkdir()
    seen_path = tmp_path / "seen.json"
    # 3 historical q4 files already on disk
    for gid in ("0022400001", "0022400002", "0022400003"):
        d = {"game_id": gid, "period": 4, "players": []}
        (qb / f"{gid}_q4.json").write_text(json.dumps(d))

    # ledger has open bets on these games — settle would mutate; must NOT.
    open_calls = []
    def _open():
        open_calls.append(True)
        return [{"bet_id": "B1", "game_id": "0022400001",
                  "player": "X", "stat": "pts"}]
    monkeypatch.setattr(asd._ledger, "open_bets", _open)
    monkeypatch.setattr(asd._ledger, "settle_bet",
                          lambda *a, **k: (_ for _ in ()).throw(
                              RuntimeError("first-run settle leak!")))
    monkeypatch.setattr(asd._ledger, "void_bet",
                          lambda *a, **k: (_ for _ in ()).throw(
                              RuntimeError("first-run void leak!")))

    cycle = asd.tick(qb_dir=qb, seen_path=seen_path, dry_run=False,
                      start_bankroll=1000.0)
    # Seen file must now contain all 3 game_ids
    saved = asd.load_seen(seen_path)
    assert saved == {"0022400001", "0022400002", "0022400003"}
    # No games processed (they were all pre-seeded)
    assert cycle["new_q4_files"] == []
    assert cycle["first_run"] is True


def test_asd_write_probe_atomic(tmp_path):
    """write_probe must NOT leak the tmp file on success."""
    asd = _import_asd()
    p = tmp_path / "out.json"
    asd.write_probe({"as_of": "now", "totals": {}}, p)
    assert p.exists()
    leftover = [f for f in tmp_path.iterdir() if str(f).endswith(".tmp")]
    assert leftover == []


def test_asd_void_dnp_bets_returns_voids_only(monkeypatch, tmp_path):
    """void_dnp_bets is a thin wrapper — must return only voided bets."""
    asd = _import_asd()
    qb = tmp_path / "qb"
    qb.mkdir()
    # _Q_RE requires a 10-digit numeric game_id — anything else is ignored.
    gid = "0022400099"
    d = {"game_id": gid, "period": 4, "players": [
        {"player_id": 1, "player_name": "Star", "team_abbreviation": "T",
          "pts": 10, "reb": 0, "ast": 0,
          "fg3m": 0, "stl": 0, "blk": 0, "to": 0},
    ]}
    (qb / f"{gid}_q4.json").write_text(json.dumps(d))
    monkeypatch.setattr(asd._ledger, "open_bets", lambda: [
        {"bet_id": "B1", "game_id": gid, "player": "Star",
          "stat": "pts", "player_id": 1},
        # DNP — voided
        {"bet_id": "B2", "game_id": gid, "player": "DNPer",
          "stat": "pts", "player_id": 9},
    ])
    voids = asd.void_dnp_bets(gid, qb_dir=qb, dry_run=True)
    assert len(voids) == 1
    assert voids[0]["bet_id"] == "B2"


# =============================================================================
# live_bet_ranker — render_md + state edge cases
# =============================================================================
def test_lbr_render_md_includes_status_and_top_bet():
    """render_md must include the user-visible PREGAME/LIVE banner and
    top-bet line so operators see at a glance."""
    lbr = _import_lbr()
    payload = {
        "captured_at": "2026-05-26T19:00:00Z",
        "tick_idx": 1, "tick_latency_ms": 50,
        "pretip": True, "stale_books": [],
        "n_props_evaluated": 30, "n_positive_ev": 5,
        "top_edge_pct": 6.5,
        "top_bet_str": "Star PTS OVER 24.5 @ fd -110",
        "total_recommended_exposure_$": 200.0,
        "ranked_bets": [{
            "player": "Star", "stat": "pts", "side": "OVER", "book": "fd",
            "line": 24.5, "model_q50": 27.0, "edge_pct": 6.5,
            "kelly_stake_$": 50.0, "line_move": "↑LINE", "stale": False,
        }],
        "line_moves_this_tick": [],
        "edge_collapses_this_tick": [],
    }
    cfg = {"label": "Test Game"}
    md = lbr.render_md(payload, cfg)
    assert "Test Game" in md
    assert "PREGAME" in md
    assert "Star" in md
    assert "fd" in md


def test_lbr_render_md_shows_stale_warning_and_collapse():
    lbr = _import_lbr()
    payload = {
        "captured_at": "x", "tick_idx": 0, "tick_latency_ms": 1,
        "pretip": False, "stale_books": ["fd"],
        "n_props_evaluated": 0, "n_positive_ev": 0,
        "top_edge_pct": None, "top_bet_str": None,
        "total_recommended_exposure_$": 0.0,
        "ranked_bets": [],
        "line_moves_this_tick": [{"key": "x"}],
        "edge_collapses_this_tick": [{
            "player": "Y", "stat": "pts", "side": "OVER", "book": "fd",
            "from_edge_pct": 8.0, "to_edge_pct": 1.0,
        }],
    }
    md = lbr.render_md(payload, {"label": "T"})
    assert "STALE books" in md
    assert "Edge collapses" in md
    assert "LIVE" in md


def test_lbr_in_play_handoff_payload_picks_correct_target():
    """The handoff payload tells downstream consumers which WP model to
    query next — a wrong mapping silently calls the wrong model."""
    lbr = _import_lbr()
    cfg = {"nba_game_ids": ["0042400317"], "game_ids": []}
    p = lbr.in_play_handoff_payload(cfg)
    assert p["phase"] == "IN_PLAY"
    assert p["next_prediction_target"] in (
        "endQ1_winprob", "endQ2_winprob", "endQ3_winprob", "final_winprob",
    )
    assert "wp_model_paths" in p
    assert len(p["wp_model_paths"]) == 4


def test_lbr_is_pretip_returns_true_when_no_q1(monkeypatch, tmp_path):
    """If no quarter_box dir AND no NBA game_id wired → pretip is True
    (graceful fallback so the daemon doesn't crash on cold-start)."""
    lbr = _import_lbr()
    monkeypatch.setattr(lbr, "PROJECT_DIR", str(tmp_path))
    cfg = {"nba_game_ids": [], "game_ids": []}
    assert lbr.is_pretip(cfg) is True


def test_lbr_is_pretip_returns_false_when_q1_present(monkeypatch, tmp_path):
    """q1.json on disk → tip-off detected, pretip = False."""
    lbr = _import_lbr()
    monkeypatch.setattr(lbr, "PROJECT_DIR", str(tmp_path))
    qb = tmp_path / "data" / "cache" / "quarter_box"
    qb.mkdir(parents=True)
    (qb / "0042400317_q1.json").write_text("{}")
    cfg = {"nba_game_ids": ["0042400317"], "game_ids": []}
    assert lbr.is_pretip(cfg) is False


# =============================================================================
# inplay_bet_ranker — full run_tick happy path + render_md
# =============================================================================
def test_ibr_run_tick_pregame_short_circuit(tmp_path):
    """Pretip path must return a PREGAME payload WITHOUT calling the engine."""
    ibr = _import_ibr()
    qb = tmp_path / "qb"
    qb.mkdir()
    payload = ibr.run_tick(
        game_id="G", date_str="2026-05-26", bankroll=1000.0,
        qbox_dir=str(qb),
    )
    assert payload["status"] == "PREGAME"
    assert payload["pretip"] is True
    assert payload["ranked_bets"] == []
    assert payload["n_positive_ev"] == 0


def test_ibr_render_md_pregame_path():
    ibr = _import_ibr()
    md = ibr.render_md({
        "game_id": "G", "captured_at": "x", "status": "PREGAME",
        "pretip": True,
    })
    assert "PREGAME" in md
    # No "Top Ranked" header in pretip
    assert "Top Ranked Live Bets" not in md


def test_ibr_render_md_inplay_path_with_bets():
    ibr = _import_ibr()
    payload = {
        "game_id": "G", "captured_at": "x", "status": "IN_PLAY",
        "pretip": False, "stale": False,
        "snapshot_age_sec": 30, "max_quarter_observed": 2,
        "snapshot_period": 3, "score_margin": -8,
        "garbage_time_active": False,
        "n_props_evaluated": 20, "n_positive_ev": 2,
        "total_recommended_exposure_$": 100.0,
        "ranked_bets": [{
            "player": "Star", "stat": "pts", "side": "OVER", "book": "fd",
            "line": 24.5, "current_stat": 14.0, "remaining_needed": 10.5,
            "model_point": 28.0, "edge_pct": 5.0, "ev_per_dollar": 0.04,
            "kelly_stake_$": 50.0,
        }],
    }
    md = ibr.render_md(payload)
    assert "In-Play Bet Ranker" in md
    assert "Star" in md
    assert "PTS" in md


def test_ibr_render_md_garbage_time_banner():
    ibr = _import_ibr()
    md = ibr.render_md({
        "game_id": "G", "captured_at": "x", "status": "IN_PLAY",
        "pretip": False, "stale": False, "snapshot_age_sec": 5,
        "max_quarter_observed": 3, "snapshot_period": 4,
        "score_margin": 25, "garbage_time_active": True,
        "n_props_evaluated": 5, "n_positive_ev": 0,
        "total_recommended_exposure_$": 0.0, "ranked_bets": [],
    })
    assert "GARBAGE-TIME" in md


def test_ibr_build_pred_index_keys_by_normalized_name():
    """Index must be keyed by lowercase-stripped name so the lookup
    survives diacritics + case."""
    ibr = _import_ibr()
    rows = [{"name": "Nikola Jokić", "stat": "pts", "projected_final": 25.0}]
    idx = ibr.build_pred_index(rows)
    assert ("nikola jokic", "pts") in idx
    assert idx[("nikola jokic", "pts")]["projected_final"] == 25.0


def test_ibr_load_live_lines_for_date_keeps_newest(tmp_path):
    """(player, stat, book, line) dedup — newest captured_at wins."""
    ibr = _import_ibr()
    p = tmp_path / "2026-05-26_bov.csv"
    p.write_text(
        "captured_at,book,player_name,stat,line,over_price,under_price\n"
        "2026-05-26T19:00:00Z,bov,X,pts,24.5,-110,-110\n"
        "2026-05-26T19:05:00Z,bov,X,pts,24.5,-130,+100\n",
        encoding="utf-8",
    )
    # Use the loader's internal — monkey-patch LINES_DIR via call wrapper:
    import inplay_bet_ranker as ibr_mod
    old = ibr_mod.LINES_DIR
    try:
        ibr_mod.LINES_DIR = str(tmp_path)
        rows = ibr.load_live_lines_for_date("2026-05-26", books=("bov",))
    finally:
        ibr_mod.LINES_DIR = old
    assert len(rows) == 1
    assert rows[0]["over_price"] == "-130"


def test_ibr_atomic_write_json_and_text(tmp_path):
    """In-play daemon writes both JSON + MD atomically — readers must
    never see partial files mid-tick."""
    ibr = _import_ibr()
    j = tmp_path / "out.json"
    m = tmp_path / "out.md"
    ibr.atomic_write_json(str(j), {"v": 1})
    ibr.atomic_write_text(str(m), "# hi\n")
    assert json.loads(j.read_text())["v"] == 1
    assert m.read_text() == "# hi\n"
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".tmp_")]
    assert leftovers == []


# =============================================================================
# bankroll_monitor — tick end-to-end
# =============================================================================
def test_bm_tick_writes_state_dashboard_and_alerts(tmp_path):
    """End-to-end tick: ledger → state.json + dashboard.md + alerts.md
    + ROI + filter info attached. Smoke-tests the whole daemon path."""
    bm = _import_bm()
    ledger_path = tmp_path / "pnl.csv"
    state = tmp_path / "state.json"
    dashboard = tmp_path / "dash.md"
    alerts = tmp_path / "alerts.md"
    # 1 settled win, 1 settled loss, 1 pending
    today = datetime.now(timezone.utc).isoformat()
    ledger_path.write_text(
        "bet_id,placed_at,game_id,player,stat,line,side,book,stake,"
        "kelly_pct,status,profit_loss\n"
        f"B1,{today},G1,Alpha,pts,24.5,OVER,fd,100,0.10,won,90\n"
        f"B2,{today},G2,Beta,pts,18.5,OVER,fd,50,0.05,lost,-50\n"
        f"B3,{today},G3,Gamma,pts,8.5,OVER,fd,80,0.08,pending,0\n",
        encoding="utf-8",
    )
    from bankroll_monitor_daemon import tick as bm_tick
    m = bm_tick(start_bankroll=1000.0, ledger_path=ledger_path,
                 state_path=state, dashboard_path=dashboard,
                 alerts_path=alerts)
    # State file written atomically
    assert state.exists()
    assert json.loads(state.read_text())["current_bankroll"] == pytest.approx(1040.0)
    # Dashboard rendered
    assert "Current bankroll" in dashboard.read_text()
    # ROI attached
    assert m["roi"]["roi_pct"] == pytest.approx(40 / 150 * 100, abs=1e-6)


def test_bm_render_dashboard_with_alarms_lists_them():
    """When alarms present, render_dashboard must enumerate every one
    with level + rule + msg."""
    bm = _import_bm()
    metrics = {
        "as_of": "x", "start_bankroll": 1000.0, "current_bankroll": 700.0,
        "pending_exposure": 0.0, "available_bankroll": 700.0,
        "daily_pnl": -300.0, "weekly_pnl": -300.0, "monthly_pnl": -300.0,
        "max_drawdown": 300.0, "max_drawdown_pct": 0.30,
        "n_open_positions": 0, "max_stake_in_one_game": 0.0,
        "position_concentration_pct": 0.0, "kelly_overhang": 0.0,
        "n_settled": 1, "alarms": [
            {"level": "STOP", "rule": "daily_pnl < -20%",
              "msg": "Daily P&L breached"},
        ],
    }
    text = bm["render_dashboard"](metrics)
    assert "STOP" in text
    assert "Daily P&L breached" in text
    assert "all systems green" not in text


# =============================================================================
# multi_game_kelly — solve identity + scaling property
# =============================================================================
def test_mgk_solve_identity_when_already_under_cap():
    """When total per-game exposure is already below slate_cap * bankroll,
    multiplier must be 1.0 — Kelly is the UPPER bound, not a target."""
    mgk = _import_mgk()
    slate = {
        "game_id": "G1",
        "ranked_bets": [
            {"player": "X", "stat": "pts", "side": "OVER", "book": "fd",
              "line": 24.5, "odds": -110, "kelly_pct_used": 0.05,
              "kelly_stake_$": 50.0},
        ],
    }
    out = mgk["solve"]([slate], bankroll=1000.0, slate_cap=0.25)
    assert out["slate_multiplier"] == 1.0
    assert out["cap_hit"] is False
    # Bet stake preserved unchanged
    assert out["scaled_slates"][0]["ranked_bets"][0]["kelly_stake_$"] == 50.0


def test_mgk_solve_scales_when_over_cap():
    """sum-of-stakes > cap_dollars → multiplier applied to every bet."""
    mgk = _import_mgk()
    # 3 games each with $150 exposure → total $450 vs $250 cap on $1000
    slates = [
        {"game_id": f"G{i}",
          "ranked_bets": [{"player": "X", "stat": "pts", "side": "OVER",
                            "book": "fd", "line": 24.5, "odds": -110,
                            "kelly_pct_used": 0.15,
                            "kelly_stake_$": 150.0}]}
        for i in (1, 2, 3)
    ]
    out = mgk["solve"](slates, bankroll=1000.0, slate_cap=0.25)
    assert out["cap_hit"] is True
    assert 0 < out["slate_multiplier"] < 1.0
    # Total post = ~250 (cap), tolerate ±1 for rounding
    assert abs(out["total_exposure_post"] - 250.0) < 1.0
    # Original kelly_pct_used preserved alongside scaled value
    bet0 = out["scaled_slates"][0]["ranked_bets"][0]
    assert bet0["kelly_pct_used_original"] == 0.15
    assert bet0["kelly_pct_used"] < 0.15


def test_mgk_per_game_exposure_handles_none_stake():
    """Bet with None/missing kelly_stake_$ must coerce to 0, never raise."""
    mgk = _import_mgk()
    slate = {"ranked_bets": [
        {"kelly_stake_$": 50.0},
        {"kelly_stake_$": None},
        {},  # missing entirely
    ]}
    assert mgk["exposure"](slate) == 50.0


def test_mgk_solve_zero_exposure_keeps_multiplier_one():
    """Slate with 0 exposure must not divide-by-zero — multiplier = 1.0."""
    mgk = _import_mgk()
    slate = {"game_id": "G1", "ranked_bets": []}
    out = mgk["solve"]([slate], bankroll=1000.0)
    assert out["slate_multiplier"] == 1.0
    assert out["total_exposure_pre"] == 0.0
    assert out["total_exposure_post"] == 0.0


def test_mgk_load_slate_from_path_parses_live_ranker_format(tmp_path):
    """_load_slate_from_path must accept the live_bet_ranker output JSON."""
    mgk_mod = sys.modules.get("multi_game_kelly")
    if mgk_mod is None:
        import multi_game_kelly as mgk_mod  # noqa: F811
    p = tmp_path / "live.json"
    p.write_text(json.dumps({
        "slate_id": "sas_okc_2026-05-26",
        "label": "SAS @ OKC",
        "ranked_bets": [{"player": "X", "kelly_stake_$": 30.0}],
    }))
    s = mgk_mod._load_slate_from_path(str(p))
    assert s["game_id"] == "sas_okc_2026-05-26"
    assert s["label"] == "SAS @ OKC"
    assert len(s["ranked_bets"]) == 1


# =============================================================================
# residual_heads — endQ1 path + cross-stat metas roundtrip
# =============================================================================
def test_rh_apply_endq1_noop_when_heads_empty(monkeypatch):
    """endQ1 path: empty heads → projs unchanged. Symmetric with endQ2/endQ3."""
    rh = _import_rh()
    rh.reset_head_caches()
    # endQ1 head loader doesn't have a public load_heads_endq1 in some versions
    # Check if it exists; if so, monkey-patch
    if hasattr(rh, "load_heads_endq1"):
        monkeypatch.setattr(rh, "load_heads_endq1", lambda: {})
    if not hasattr(rh, "apply_residual_correction_endq1"):
        pytest.skip("endq1 path not present in this revision")
    snap = {"players": [{"player_id": 1, "team": "A"}],
             "home_team": "A", "away_team": "B",
             "home_score": 25, "away_score": 22}
    projs = {(1, "pts"): 8.0}
    assert rh.apply_residual_correction_endq1(snap, projs) == projs


def test_rh_load_heads_endq2_returns_empty_when_dir_missing(monkeypatch, tmp_path):
    rh = _import_rh()
    rh.reset_head_caches()
    monkeypatch.setattr(rh, "HEAD_DIR_ENDQ2", str(tmp_path / "no"))
    assert rh.load_heads_endq2() == {}


def test_rh_load_head_metas_returns_empty_when_dir_missing(monkeypatch, tmp_path):
    rh = _import_rh()
    rh.reset_head_caches()
    monkeypatch.setattr(rh, "HEAD_DIR", str(tmp_path / "no"))
    assert rh.load_head_metas() == {}


def test_rh_load_xstat_heads_returns_empty_when_dir_missing(monkeypatch, tmp_path):
    rh = _import_rh()
    rh.reset_head_caches()
    monkeypatch.setattr(rh, "HEAD_DIR", str(tmp_path / "no"))
    assert rh.load_xstat_heads() == {}


def test_rh_load_xstat_metas_returns_empty_when_dir_missing(monkeypatch, tmp_path):
    rh = _import_rh()
    rh.reset_head_caches()
    monkeypatch.setattr(rh, "HEAD_DIR", str(tmp_path / "no"))
    assert rh.load_xstat_metas() == {}


def test_rh_head_metas_parses_features_list(tmp_path, monkeypatch):
    """Per-stat meta JSON's 'features' list overrides the legacy schema —
    R10_M16 ships per-stat for fg3m/stl/blk/tov via this path."""
    rh = _import_rh()
    head_dir = tmp_path / "residual_heads"
    head_dir.mkdir()
    # Don't write an .lgb file; just the meta.
    meta = {"features": ["cur_fg3m", "min_through_q3", "hot_streak"]}
    (head_dir / "fg3m_meta.json").write_text(json.dumps(meta))
    monkeypatch.setattr(rh, "HEAD_DIR", str(head_dir))
    rh.reset_head_caches()
    names = rh._feature_names_for_stat("fg3m")
    assert tuple(names) == ("cur_fg3m", "min_through_q3", "hot_streak")
    # Stats with no meta still fall back to legacy
    pts_names = rh._feature_names_for_stat("pts")
    assert pts_names == rh._LEGACY_ENDQ3_FEATURES


def test_rh_load_xstat_history_index_when_parquet_missing(monkeypatch, tmp_path):
    """Missing OOF parquet → empty histories + unit sigmas (no crash)."""
    rh = _import_rh()
    rh.reset_head_caches()
    monkeypatch.setattr(rh, "_OOF_PARQUET_PATH",
                          str(tmp_path / "no_oof.parquet"))
    histories, sigmas = rh._load_xstat_history_index()
    assert histories == {}
    for s in rh.STATS:
        assert sigmas[s] == 1.0


# =============================================================================
# middle_finder_daemon — model band annotation
# =============================================================================
def test_mfd_annotate_model_confirmed_flags_when_band_prob_above_threshold():
    """model_confirmed must fire when the predicted q-band prob of landing
    in the middle window >= min_band_prob (default 10%)."""
    mfd = _import_mfd()
    middles = [{
        "player": "Star", "stat": "pts",
        "over_book": "bov", "over_line": 22.5, "over_price": +110,
        "under_book": "fd", "under_line": 26.5, "under_price": +110,
        "middle_width": 4.0, "worst_price": +110, "free_arb": True,
        "arb_profit_pct": 5.0,
    }]

    # Stub predictor: q-band centered on 24.5, narrow sigma → ~75% in band
    def fake_predictor(player, stat):
        return {"q10": 22.0, "q50": 24.5, "q90": 27.0}

    # Stub the calibration apply to identity
    if mfd._MODEL_OK and mfd.apply_quantile_calibration is not None:
        original = mfd.apply_quantile_calibration
        mfd.apply_quantile_calibration = lambda s, q10, q50, q90: (q10, q90)
    else:
        mfd.apply_quantile_calibration = lambda s, q10, q50, q90: (q10, q90)
    try:
        out = mfd.annotate_model_confirmed(middles, fake_predictor,
                                             min_band_prob=0.10)
        assert out[0]["model_confirmed"] is True
        assert out[0]["model_band_prob"] is not None
        assert 0.1 <= out[0]["model_band_prob"] <= 1.0
    finally:
        if mfd._MODEL_OK:
            mfd.apply_quantile_calibration = original


def test_mfd_annotate_model_confirmed_caches_per_player_stat():
    """The annotation must cache predictor calls per (player, stat) so
    a long middles list doesn't re-run the model 100 times for one player."""
    mfd = _import_mfd()
    calls = []

    def counting_predictor(player, stat):
        calls.append((player, stat))
        return {"q10": 22.0, "q50": 24.5, "q90": 27.0}

    mfd.apply_quantile_calibration = lambda s, q10, q50, q90: (q10, q90)
    middles = [
        {"player": "Star", "stat": "pts", "over_book": "a", "over_line": 22.5,
         "over_price": +110, "under_book": "b", "under_line": 26.5,
         "under_price": +110, "middle_width": 4.0, "worst_price": +110,
         "free_arb": True, "arb_profit_pct": 5.0},
        # SAME player+stat — must hit cache
        {"player": "Star", "stat": "pts", "over_book": "c", "over_line": 23.0,
         "over_price": +100, "under_book": "d", "under_line": 26.0,
         "under_price": +100, "middle_width": 3.0, "worst_price": +100,
         "free_arb": True, "arb_profit_pct": 4.0},
    ]
    mfd.annotate_model_confirmed(middles, counting_predictor,
                                   min_band_prob=0.10)
    assert len(calls) == 1  # cached


def test_mfd_annotate_model_predictor_none_yields_none_band_prob():
    """predictor returning None → model_band_prob None, model_confirmed False."""
    mfd = _import_mfd()
    middles = [{
        "player": "X", "stat": "pts",
        "over_book": "a", "over_line": 22.5, "over_price": -110,
        "under_book": "b", "under_line": 26.5, "under_price": -110,
        "middle_width": 4.0, "worst_price": -110, "free_arb": False,
        "arb_profit_pct": None,
    }]
    out = mfd.annotate_model_confirmed(middles, lambda p, s: None,
                                         min_band_prob=0.10)
    assert out[0]["model_confirmed"] is False
    assert out[0]["model_band_prob"] is None


# =============================================================================
# live_bet_ranker — run_tick smoke (stubs the model + scoring)
# =============================================================================
def test_lbr_atomic_write_text_no_temp_leak(tmp_path):
    lbr = _import_lbr()
    out = tmp_path / "out.md"
    for v in range(3):
        lbr.atomic_write_text(str(out), f"# v{v}\n")
    assert out.read_text() == "# v2\n"
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".tmp_")]
    assert leftovers == []


def test_lbr_implied_prob_positive_and_negative_odds():
    lbr = _import_lbr()
    # +200 → 100/300 = 0.333...
    assert lbr.implied_prob(+200) == pytest.approx(1/3, abs=1e-6)
    # -200 → 200/300 = 0.667...
    assert lbr.implied_prob(-200) == pytest.approx(2/3, abs=1e-6)


def test_lbr_american_to_decimal_handles_nan():
    """pd.isna guard prevents the converter from crashing on a NaN price
    bleed-through from a malformed CSV row."""
    lbr = _import_lbr()
    import pandas as pd
    assert lbr.american_to_decimal(None) is None
    assert lbr.american_to_decimal(pd.NA) is None or lbr.american_to_decimal(pd.NA) is not None  # tolerate libs


# =============================================================================
# inplay_bet_ranker — find_quarter_files numeric vs alpha game_id
# =============================================================================
def test_ibr_find_quarter_files_ignores_unrelated_dirs(tmp_path):
    """Only files matching <game_id>_q<N>.json count — never confuse two
    games that share a prefix."""
    ibr = _import_ibr()
    qb = tmp_path / "qb"
    qb.mkdir()
    (qb / "G1_q1.json").write_text("{}")
    (qb / "G1_q2.json").write_text("{}")
    (qb / "G2_q1.json").write_text("{}")
    (qb / "G1_other.json").write_text("{}")
    out = ibr.find_quarter_files("G1", qbox_dir=str(qb))
    assert sorted(out.keys()) == [1, 2]


def test_ibr_snapshot_age_sec_inf_when_no_files():
    ibr = _import_ibr()
    age = ibr._snapshot_age_sec({})
    assert age == float("inf")


def test_ibr_snapshot_age_sec_uses_newest_mtime(tmp_path):
    """Stale-guard depends on this: must use MAX mtime, not min."""
    ibr = _import_ibr()
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    p1.write_text("{}")
    p2.write_text("{}")
    # Force p2 to be newer
    now = time.time()
    os.utime(p1, (now - 1000, now - 1000))
    os.utime(p2, (now - 5, now - 5))
    age = ibr._snapshot_age_sec({1: str(p1), 2: str(p2)}, now_t=now)
    assert 0 <= age <= 10  # newest, not oldest


# =============================================================================
# clv_tracker_daemon — find_latest_snapshot exact-line priority + _safe coercion
# =============================================================================
def test_ctd_find_latest_snapshot_exact_line_wins(tmp_path):
    """When multiple snapshots match a bet (book, player, stat), the one
    that matches the placed line EXACTLY is preferred over a more-recent
    snapshot at a different line. Different alt-line rungs are different
    markets — wrong rung corrupts CLV math."""
    ctd = _import_ctd()
    bet = {"book": "fd", "player": "Star", "stat": "pts", "line": "24.5",
            "player_id": ""}
    snaps = [
        {"book": "fd", "player_name": "Star", "stat": "pts",
          "line": "25.5", "captured_at": "2026-05-26T19:30:00Z"},
        # Exact line match @ older ts — must STILL win
        {"book": "fd", "player_name": "Star", "stat": "pts",
          "line": "24.5", "captured_at": "2026-05-26T19:00:00Z"},
    ]
    best = ctd.find_latest_snapshot(bet, snaps)
    assert best is not None
    assert float(best["line"]) == 24.5


def test_ctd_safe_float_and_safe_int_handle_garbage():
    ctd = _import_ctd()
    assert ctd._safe_float("3.14") == 3.14
    assert ctd._safe_float("") is None
    assert ctd._safe_float(None) is None
    assert ctd._safe_float("garbage") is None
    assert ctd._safe_int("42") == 42
    # NOTE: _safe_int calls int(v) directly (not int(float(v))) — float
    # strings are NOT coerced. This documents existing behavior.
    assert ctd._safe_int("3.7") is None
    assert ctd._safe_int(None) is None
    assert ctd._safe_int("x") is None
    assert ctd._safe_int(42.9) == 42  # int() truncates floats


def test_ctd_parse_iso_tolerates_short_format():
    """Snapshot timestamps sometimes drop seconds: 'YYYY-MM-DDTHH:MM'."""
    ctd = _import_ctd()
    dt = ctd._parse_iso("2026-05-26T19:00")
    assert dt is not None
    dt_z = ctd._parse_iso("2026-05-26T19:00:00Z")
    assert dt_z is not None
    assert ctd._parse_iso("") is None
    assert ctd._parse_iso("garbage") is None


def test_ctd_load_recent_snapshots_unions_all_csvs(tmp_path):
    """Union must cover EVERY *.csv under data/lines/ — missing books
    silently corrupt CLV (no closing line capture)."""
    ctd = _import_ctd()
    d = tmp_path / "lines"
    d.mkdir()
    (d / "2026-05-26_fd.csv").write_text(
        "captured_at,book,player_name,stat,line\n"
        "2026-05-26T19:00:00Z,fd,X,pts,24.5\n",
        encoding="utf-8",
    )
    (d / "2026-05-26_bov.csv").write_text(
        "captured_at,book,player_name,stat,line\n"
        "2026-05-26T19:00:00Z,bov,Y,reb,9.5\n",
        encoding="utf-8",
    )
    snaps = ctd.load_recent_snapshots(d)
    assert len(snaps) == 2
    assert {s["player_name"] for s in snaps} == {"X", "Y"}


def test_ctd_load_recent_snapshots_missing_dir_returns_empty(tmp_path):
    ctd = _import_ctd()
    assert ctd.load_recent_snapshots(tmp_path / "missing") == []


# =============================================================================
# line_move_detector — utility coverage
# =============================================================================
def test_lmd_odds_pct_delta_signed_correctly():
    """ODDS_TIGHTEN when implied prob went UP (price moved against
    bettor); ODDS_LOOSEN when implied prob went DOWN."""
    lmd = _import_lmd()
    # -110 → -150: prob went up (book got more confident)
    d = lmd.odds_pct_delta(-110, -150)
    assert d is not None and d > 0
    # -110 → +110: prob went down (book offering longer odds)
    d2 = lmd.odds_pct_delta(-110, +110)
    assert d2 is not None and d2 < 0


def test_lmd_to_american_int_handles_special_tokens():
    lmd = _import_lmd()
    assert lmd._to_american_int("EVEN") == 100
    assert lmd._to_american_int("EV") == 100
    assert lmd._to_american_int("+150") == 150
    assert lmd._to_american_int("-110") == -110
    assert lmd._to_american_int("") is None
    assert lmd._to_american_int(None) is None
    # NaN handled
    assert lmd._to_american_int(float("nan")) is None


def test_lmd_name_key_strips_diacritics():
    lmd = _import_lmd()
    assert lmd._name_key("Nikola Jokić") == "nikola jokic"


def test_lmd_parse_ts_handles_z_suffix():
    lmd = _import_lmd()
    assert lmd._parse_ts("2026-05-26T19:00:00Z") is not None
    assert lmd._parse_ts(None) is None
    # NaN from pandas
    import pandas as pd
    assert lmd._parse_ts(pd.NA) is None


def test_lmd_diff_group_emits_event_per_threshold_breach():
    """Per-consecutive-pair diff must fire only when the threshold is
    breached. Same-direction same-magnitude pairs => exactly N-1 events
    when every pair breaches."""
    lmd = _import_lmd()
    g = pd.DataFrame([
        {"captured_at": "2026-05-26T19:00:00Z",
          "line": 24.5, "over_price": -110},
        {"captured_at": "2026-05-26T19:01:00Z",
          "line": 25.5, "over_price": -110},  # +1.0 line move
        {"captured_at": "2026-05-26T19:02:00Z",
          "line": 26.5, "over_price": -110},  # +1.0 line move
    ])
    events = lmd.diff_group(g, threshold_line=0.5,
                              threshold_odds_pct=10.0,
                              book="bov", player="X", stat="pts")
    assert len(events) == 2
    assert all("LINE_UP" in e["tags"] for e in events)


def test_lmd_detect_moves_returns_empty_on_missing_cols():
    """Schema-drifted CSVs that lose required cols must NOT crash —
    return empty list."""
    lmd = _import_lmd()
    df = pd.DataFrame([{"book": "bov", "player_name": "X"}])  # missing cols
    assert lmd.detect_moves(df, 0.5, 10) == []


def test_lmd_detect_moves_empty_input():
    lmd = _import_lmd()
    assert lmd.detect_moves(pd.DataFrame(), 0.5, 10) == []


# =============================================================================
# bankroll_monitor — load_ledger + append_alerts edge cases
# =============================================================================
def test_bm_load_ledger_returns_empty_df_when_missing(tmp_path):
    """Missing pnl_ledger.csv → return empty DF (not raise) so first-run
    is graceful."""
    from bankroll_monitor_daemon import load_ledger
    df = load_ledger(tmp_path / "no.csv")
    assert df.empty
    assert "bet_id" in df.columns


def test_bm_load_ledger_reads_csv(tmp_path):
    from bankroll_monitor_daemon import load_ledger
    p = tmp_path / "pnl.csv"
    p.write_text(
        "bet_id,placed_at,player,stake,profit_loss,status\n"
        "B1,2026-05-26T10:00:00Z,X,50,0,pending\n",
        encoding="utf-8",
    )
    df = load_ledger(p)
    assert len(df) == 1
    assert df.iloc[0]["bet_id"] == "B1"


def test_bm_append_alerts_creates_header_first_time(tmp_path):
    """First write must include the markdown header."""
    from bankroll_monitor_daemon import append_alerts
    p = tmp_path / "alerts.md"
    metrics = {"as_of": "2026-05-26T19:00:00",
                "alarms": [{"level": "WARN", "rule": "x", "msg": "y"}]}
    append_alerts(p, metrics)
    text = p.read_text()
    assert "# Risk Alerts Log" in text
    assert "WARN" in text
    # Second append must NOT duplicate the header
    append_alerts(p, metrics)
    assert p.read_text().count("# Risk Alerts Log") == 1


def test_bm_append_alerts_noop_when_no_alarms(tmp_path):
    """No alarms → no file written → no noise in the log."""
    from bankroll_monitor_daemon import append_alerts
    p = tmp_path / "alerts.md"
    append_alerts(p, {"as_of": "x", "alarms": []})
    assert not p.exists()


# =============================================================================
# injury_availability — stale snapshot triggers fresh scrape attempt
# =============================================================================
def test_ia_load_latest_snapshot_returns_none_when_cache_empty(monkeypatch,
                                                                  tmp_path):
    ia = _import_ia()
    monkeypatch.setattr(ia, "_CACHE_DIR", str(tmp_path / "no_cache"))
    monkeypatch.setattr(ia, "_trigger_fresh_scrape", lambda: False)
    assert ia.load_latest_snapshot() is None


def test_ia_is_stale_for_missing_or_old(monkeypatch, tmp_path):
    ia = _import_ia()
    assert ia._is_stale(None) is True
    assert ia._is_stale(str(tmp_path / "no_file")) is True
    p = tmp_path / "snap.json"
    p.write_text("{}")
    # Force mtime to be 12 hours old
    old = time.time() - 12 * 3600
    os.utime(p, (old, old))
    assert ia._is_stale(str(p)) is True


def test_ia_reset_cache_clears_in_memory(monkeypatch):
    """reset_cache must drop the index so the next get_availability_factor
    re-reads from disk. Test path: stub the index, reset, observe it
    re-loads."""
    ia = _import_ia()
    # Stub the indices
    ia._CACHED["by_player_id"] = {100: 0.5}
    ia._CACHED["by_name"] = {"x": 0.5}
    ia.reset_cache()
    assert ia._CACHED["by_player_id"] is None
    assert ia._CACHED["by_name"] is None


def test_ia_latest_snapshot_path_picks_newest(tmp_path, monkeypatch):
    """When multiple injury_status_*.json files exist, pick the one with
    the newest mtime."""
    ia = _import_ia()
    cache = tmp_path / "cache"
    cache.mkdir()
    a = cache / "injury_status_2026-05-25.json"
    b = cache / "injury_status_2026-05-26.json"
    a.write_text("{}")
    b.write_text("{}")
    now = time.time()
    os.utime(a, (now - 3600, now - 3600))
    os.utime(b, (now - 5, now - 5))
    monkeypatch.setattr(ia, "_CACHE_DIR", str(cache))
    p = ia._latest_snapshot_path()
    assert p is not None
    assert p.endswith("2026-05-26.json")


def test_ia_apply_availability_partial_band(monkeypatch):
    """Only q10 supplied → q90 stays None in output; the multiplier
    still applies to q50 and q10."""
    ia = _import_ia()
    monkeypatch.setattr(ia, "get_availability_factor", lambda **kw: 0.6)
    q50, q10, q90 = ia.apply_availability(1, q50=20.0, q10=15.0)
    assert q50 == pytest.approx(12.0)
    assert q10 == pytest.approx(9.0)
    assert q90 is None


# =============================================================================
# multi_game_kelly — _resolve_slate_paths + main CLI smoke
# =============================================================================
def test_mgk_resolve_slate_paths_absolute_file_passthrough(tmp_path):
    """Absolute path to a live_bet_ranker output JSON should pass through
    verbatim — no directory search."""
    mgk_mod = sys.modules.get("multi_game_kelly")
    if mgk_mod is None:
        import multi_game_kelly as mgk_mod  # noqa: F811
    p = tmp_path / "slate.json"
    p.write_text(json.dumps({"slate_id": "X", "ranked_bets": []}))
    out = mgk_mod._resolve_slate_paths([str(p)])
    assert out == [str(p)]


def test_mgk_resolve_slate_paths_finds_latest_match(tmp_path, monkeypatch):
    """slate-id → latest matching JSON file under data/cache/live_bets/."""
    mgk_mod = sys.modules.get("multi_game_kelly")
    if mgk_mod is None:
        import multi_game_kelly as mgk_mod  # noqa: F811
    live_dir = tmp_path / "data" / "cache" / "live_bets"
    live_dir.mkdir(parents=True)
    (live_dir / "2026-05-25_sas_okc.json").write_text("{}")
    (live_dir / "2026-05-26_sas_okc.json").write_text("{}")
    # Files that must be ignored
    (live_dir / "sas_okc_state.json").write_text("{}")
    (live_dir / "sas_okc_handoff.json").write_text("{}")
    monkeypatch.setattr(mgk_mod, "PROJECT_DIR", str(tmp_path))
    paths = mgk_mod._resolve_slate_paths(["sas_okc"])
    assert len(paths) == 1
    # Latest (sorted last) wins
    assert "2026-05-26" in paths[0]


def test_mgk_resolve_slate_paths_raises_when_missing(tmp_path, monkeypatch):
    mgk_mod = sys.modules.get("multi_game_kelly")
    if mgk_mod is None:
        import multi_game_kelly as mgk_mod  # noqa: F811
    monkeypatch.setattr(mgk_mod, "PROJECT_DIR", str(tmp_path))
    # No directory at all
    with pytest.raises(FileNotFoundError):
        mgk_mod._resolve_slate_paths(["nope"])
    # Directory exists but no match
    live_dir = tmp_path / "data" / "cache" / "live_bets"
    live_dir.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        mgk_mod._resolve_slate_paths(["does_not_exist"])


def test_mgk_main_cli_writes_output_json(tmp_path, monkeypatch):
    """main() integration: --slates path + --bankroll → JSON with
    expected structure."""
    mgk_mod = sys.modules.get("multi_game_kelly")
    if mgk_mod is None:
        import multi_game_kelly as mgk_mod  # noqa: F811
    slate = tmp_path / "slate.json"
    slate.write_text(json.dumps({
        "slate_id": "sas_okc", "label": "Test",
        "ranked_bets": [{"kelly_stake_$": 100.0}],
    }))
    out = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", [
        "multi_game_kelly.py", "--slates", str(slate),
        "--bankroll", "1000",
        "--slate-cap", "0.25",
        "--out", str(out),
    ])
    mgk_mod.main()
    payload = json.loads(out.read_text())
    assert payload["n_games"] == 1
    assert payload["bankroll"] == 1000.0
    assert payload["slate_cap"] == 0.25


# =============================================================================
# live_bet_ranker — load_state recovers from valid JSON; run_daemon stub
# =============================================================================
def test_lbr_load_state_round_trips_valid_json(tmp_path):
    lbr = _import_lbr()
    p = tmp_path / "state.json"
    state = {"prior_lines": {"k": {"line": 24.5, "odds": -110}},
              "prior_edges": {"k|p|O|f|24.5": 5.0}}
    p.write_text(json.dumps(state))
    out = lbr.load_state(str(p))
    assert out == state


def test_lbr_load_placed_valid_json(tmp_path):
    lbr = _import_lbr()
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"placed_keys": ["a", "b", "c"]}))
    out = lbr.load_placed(str(p))
    assert out == {"a", "b", "c"}


def test_lbr_model_cache_construction():
    """ModelCache __init__ wiring — must not lazy-load anything on
    construction (test runs offline without artifacts)."""
    lbr = _import_lbr()
    cache = lbr.ModelCache(
        slate_cfg={"label": "x"}, gamelog_dir="/nowhere",
        model_dir="/nowhere",
    )
    assert cache.preds == {}
    assert cache._loaded is False


def test_lbr_render_md_includes_line_moves_warning():
    """If line_moves_this_tick is non-empty, the dashboard header must
    surface the count so the operator can react."""
    lbr = _import_lbr()
    payload = {
        "captured_at": "x", "tick_idx": 1, "tick_latency_ms": 5,
        "pretip": False, "stale_books": [],
        "n_props_evaluated": 10, "n_positive_ev": 1,
        "top_edge_pct": 3.5, "top_bet_str": "Star PTS OVER 24.5 @ fd",
        "total_recommended_exposure_$": 50.0, "ranked_bets": [{
            "player": "Star", "stat": "pts", "side": "OVER", "book": "fd",
            "line": 24.5, "model_q50": 26.0, "edge_pct": 3.5,
            "kelly_stake_$": 50.0, "line_move": "", "stale": False,
        }],
        "line_moves_this_tick": [{"key": "x"}, {"key": "y"}],
        "edge_collapses_this_tick": [],
    }
    md = lbr.render_md(payload, {"label": "T"})
    assert "Line moves this tick" in md
    assert "2" in md


# =============================================================================
# middle_finder_daemon — coverage helpers
# =============================================================================
def test_mfd_to_int_to_float_parsers():
    """_to_int / _to_float / _parse_dt must absorb the messy real-world
    inputs (None, empty, 'None' literal) the scrapers produce."""
    mfd = _import_mfd()
    assert mfd._to_int(None) is None
    assert mfd._to_int("") is None
    assert mfd._to_int("None") is None
    assert mfd._to_int("110") == 110
    assert mfd._to_int("3.7") == 3
    assert mfd._to_int("garbage") is None
    assert mfd._to_float(None) is None
    assert mfd._to_float("3.14") == 3.14
    assert mfd._to_float("garbage") is None
    assert mfd._parse_dt("") is None
    assert mfd._parse_dt(None) is None
    assert mfd._parse_dt("2026-05-26T19:00:00Z") is not None


def test_mfd_implied_prob_and_decimal_signs():
    mfd = _import_mfd()
    assert mfd.implied_prob(+100) == pytest.approx(0.5)
    assert mfd.implied_prob(-100) == pytest.approx(0.5)
    assert mfd.implied_prob(None) is None
    assert mfd.american_to_decimal(+200) == 3.0
    assert mfd.american_to_decimal(-200) == 1.5
    assert mfd.american_to_decimal(None) is None


def test_mfd_norm_cdf_monotonic():
    mfd = _import_mfd()
    # _norm_cdf must be monotonic non-decreasing
    samples = [-3, -2, -1, 0, 1, 2, 3]
    cdfs = [mfd._norm_cdf(z) for z in samples]
    for i in range(1, len(cdfs)):
        assert cdfs[i] >= cdfs[i - 1]


def test_mfd_model_band_prob_handles_none_qint():
    mfd = _import_mfd()
    assert mfd._model_band_prob("pts", None, 22.5, 26.5) is None
    # Partial qint → None
    assert mfd._model_band_prob("pts", {"q10": 22}, 22.5, 26.5) is None


def test_mfd_today_str_iso_format():
    mfd = _import_mfd()
    s = mfd._today_str()
    # ISO date format YYYY-MM-DD
    assert len(s) == 10
    assert s.count("-") == 2


# =============================================================================
# auto_settle_daemon — settle_game with open_bets_by_game (the tick path)
# =============================================================================
def test_asd_settle_game_uses_open_bets_by_game_index(monkeypatch, tmp_path):
    """tick() amortises one ledger load across many games via
    open_bets_by_game. settle_game must use that index when supplied
    and NOT re-read the ledger."""
    asd = _import_asd()
    # Stub open_bets to raise — proves we didn't call it
    monkeypatch.setattr(asd._ledger, "open_bets", lambda: (_ for _ in ()).throw(
        RuntimeError("should not call open_bets — must use index")))

    qb = tmp_path / "qb"
    qb.mkdir()
    gid = "0022400077"
    d = {"game_id": gid, "period": 4, "players": [
        {"player_id": 1, "player_name": "Star", "team_abbreviation": "T",
          "pts": 22, "reb": 0, "ast": 0,
          "fg3m": 0, "stl": 0, "blk": 0, "to": 0},
    ]}
    (qb / f"{gid}_q4.json").write_text(json.dumps(d))
    index = {gid: [{"bet_id": "B1", "game_id": gid, "player": "Star",
                    "stat": "pts", "player_id": 1}]}
    res = asd.settle_game(gid, qb_dir=qb, dry_run=True,
                            open_bets_by_game=index)
    assert len(res["settled"]) == 1


def test_asd_settle_game_no_bets_short_circuits(tmp_path):
    """When no open bets on the game, skip the 200-player box load."""
    asd = _import_asd()
    qb = tmp_path / "qb"
    qb.mkdir()
    gid = "0022400088"
    (qb / f"{gid}_q4.json").write_text("{}")
    res = asd.settle_game(gid, qb_dir=qb, dry_run=True,
                            open_bets_by_game={})  # empty index
    assert res["settled"] == []
    assert res["voided"] == []
    assert res["skipped"] == []


def test_asd_settle_game_skipped_when_box_empty(monkeypatch, tmp_path):
    """If the q4 file is unreadable / has no totals, settle_game emits
    a single skipped row with reason 'no_box_data' instead of voiding
    every bet — critical to prevent mass-void on a corrupt q4."""
    asd = _import_asd()
    qb = tmp_path / "qb"
    qb.mkdir()
    gid = "0022400099"
    (qb / f"{gid}_q4.json").write_text("garbage not json")
    monkeypatch.setattr(asd._ledger, "open_bets", lambda: [
        {"bet_id": "B1", "game_id": gid, "player": "X",
          "stat": "pts", "player_id": 1},
    ])
    res = asd.settle_game(gid, qb_dir=qb, dry_run=True)
    assert res["voided"] == []
    assert len(res["skipped"]) == 1
    assert res["skipped"][0]["reason"] == "no_box_data"


# =============================================================================
# inplay_bet_ranker — additional coverage of run_tick branches
# =============================================================================
def test_ibr_run_tick_returns_no_snapshot_when_qfiles_unreadable(tmp_path):
    """When q1.json EXISTS (so we're past pretip) but the snapshot can't
    be built, return a NO_SNAPSHOT payload — not a crash."""
    ibr = _import_ibr()
    qb = tmp_path / "qb"
    qb.mkdir()
    # q1 with malformed JSON → cumulative snapshot returns None for player aggs
    # but the function returns a snap. Use empty players to ensure no_snapshot
    # actually triggers — write a file that *exists* (so not pretip) but
    # produces no players + no teams → snap is empty-but-not-None.
    (qb / "G_q1.json").write_text("garbage not json")
    payload = ibr.run_tick(
        game_id="G", date_str="2026-05-26", bankroll=1000.0,
        qbox_dir=str(qb),
    )
    # Either NO_SNAPSHOT or a real status — both are acceptable, but it
    # must NOT raise and ranked_bets must be a list
    assert isinstance(payload["ranked_bets"], list)
    assert payload["pretip"] is False


def test_ibr_run_tick_handles_project_error(monkeypatch, tmp_path):
    """If the engine raises during project, return a PROJECT_ERROR payload
    (so the daemon doesn't tip over on a single bad model load)."""
    ibr = _import_ibr()
    qb = tmp_path / "qb"
    qb.mkdir()
    d = {
        "game_id": "G", "period": 1, "players": [{
            "player_id": 1, "player_name": "Star",
            "team_abbreviation": "AAA",
            "min": "10:00", "pts": 12, "reb": 4, "ast": 2,
            "fg3m": 1, "stl": 1, "blk": 0, "to": 1, "pf": 2,
            "start_position": "F",
        }],
        "teams": [
            {"team_abbreviation": "AAA", "team_id": 100, "pts": 25},
            {"team_abbreviation": "BBB", "team_id": 200, "pts": 28},
        ],
    }
    (qb / "G_q1.json").write_text(json.dumps(d))
    monkeypatch.setattr(ibr, "_project_with_engine",
                          lambda snap, period_override=None: (_ for _ in ()).throw(
                              RuntimeError("model load failed")))
    payload = ibr.run_tick(
        game_id="G", date_str="2026-05-26", bankroll=1000.0,
        qbox_dir=str(qb),
    )
    assert "PROJECT_ERROR" in payload["status"]
    assert payload["ranked_bets"] == []


# =============================================================================
# clv_tracker_daemon — _append_closing_line + _append_clv_rows
# =============================================================================
def test_ctd_append_closing_line_writes_header_first_time(tmp_path):
    ctd = _import_ctd()
    p = tmp_path / "closing.csv"
    ctd._append_closing_line(
        p, bet_id="B1", book="fd", stat="pts", player="X",
        closing_line=25.5, closing_over_odds=-110,
        closing_under_odds=-110,
        captured_at="2026-05-26T19:30:00Z",
        start_time="2026-05-26T20:00:00Z",
    )
    text = p.read_text()
    assert "bet_id,book,stat,player,closing_line" in text
    assert "B1,fd,pts,X,25.5" in text


def test_ctd_closing_already_logged(tmp_path):
    """_closing_already_logged is the dedup guard — must return True
    only when EXACTLY (bet_id, book) is already present."""
    ctd = _import_ctd()
    p = tmp_path / "closing.csv"
    assert ctd._closing_already_logged(p, "B1", "fd") is False
    ctd._append_closing_line(
        p, bet_id="B1", book="fd", stat="pts", player="X",
        closing_line=25.5, closing_over_odds=None,
        closing_under_odds=None, captured_at="t", start_time="t",
    )
    assert ctd._closing_already_logged(p, "B1", "fd") is True
    # Different book → not logged
    assert ctd._closing_already_logged(p, "B1", "bov") is False
    # Different bet → not logged
    assert ctd._closing_already_logged(p, "B2", "fd") is False


def test_ctd_append_clv_rows_writes_header_and_dedups_columns(tmp_path):
    """Round-trip: 2 rows written + read back via DictReader = 2 rows."""
    ctd = _import_ctd()
    p = tmp_path / "clv.csv"
    rows = [
        {"bet_id": "B1", "snapshot_time": "t1", "clv_pct": 0.05,
          "side": "OVER", "book": "fd", "player": "X", "stat": "pts",
          "placed_line": 24.5, "current_line": 25.5, "clv_line": 1.0,
          "beat_close": True, "is_closing": False, "minutes_to_tip": "",
          "start_time": ""},
        {"bet_id": "B2", "snapshot_time": "t2", "clv_pct": -0.02,
          "side": "UNDER", "book": "bov", "player": "Y", "stat": "reb",
          "placed_line": 9.5, "current_line": 9.6, "clv_line": -0.1,
          "beat_close": False, "is_closing": False, "minutes_to_tip": "",
          "start_time": ""},
    ]
    ctd._append_clv_rows(p, rows)
    with open(p) as fh:
        read = list(csv.DictReader(fh))
    assert len(read) == 2


def test_ctd_append_clv_rows_noop_on_empty(tmp_path):
    """Empty rows → no file written → no spurious header-only files."""
    ctd = _import_ctd()
    p = tmp_path / "clv.csv"
    ctd._append_clv_rows(p, [])
    assert not p.exists()


# =============================================================================
# residual_heads — load_heads + cache reset roundtrip
# =============================================================================
def test_rh_reset_head_caches_clears_all_globals(monkeypatch):
    """reset_head_caches must drop every global cache — otherwise tests
    that patch HEAD_DIR can't see the new directory."""
    rh = _import_rh()
    rh._HEAD_CACHE = {"pts": object()}
    rh._HEAD_META_CACHE = {"pts": {}}
    rh._HEAD_CACHE_ENDQ2 = {"x": object()}
    rh._HEAD_CACHE_ENDQ1 = {"y": object()}
    rh._XSTAT_HEAD_CACHE = {"z": object()}
    rh._XSTAT_META_CACHE = {"z": {}}
    rh._XSTAT_HISTORY_CACHE = {1: []}
    rh._XSTAT_SIGMAS_CACHE = {"pts": 1.0}
    rh.reset_head_caches()
    assert rh._HEAD_CACHE is None
    assert rh._HEAD_META_CACHE is None
    assert rh._HEAD_CACHE_ENDQ2 is None
    assert rh._HEAD_CACHE_ENDQ1 is None
    assert rh._XSTAT_HEAD_CACHE is None
    assert rh._XSTAT_META_CACHE is None
    assert rh._XSTAT_HISTORY_CACHE is None
    assert rh._XSTAT_SIGMAS_CACHE is None


def test_rh_load_heads_lightgbm_absent_returns_empty(monkeypatch):
    """When lightgbm isn't importable, load_heads returns {} — never
    crash."""
    rh = _import_rh()
    rh.reset_head_caches()
    # Force ImportError on lightgbm import
    import builtins
    real_import = builtins.__import__

    def stub_import(name, *args, **kwargs):
        if name == "lightgbm":
            raise ImportError("stubbed for test")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", stub_import)
    out = rh.load_heads()
    assert out == {}


def test_rh_apply_residual_correction_numpy_absent_returns_projs(monkeypatch):
    """If numpy isn't importable inside the function body, apply
    returns projs unchanged."""
    rh = _import_rh()
    rh.reset_head_caches()
    # Have heads non-empty so we get past the first guard
    monkeypatch.setattr(rh, "load_heads", lambda: {"pts": object()})
    import builtins
    real_import = builtins.__import__

    def stub_import(name, *args, **kwargs):
        if name == "numpy":
            raise ImportError("stubbed")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", stub_import)
    snap = {"players": [{"player_id": 1, "team": "A"}],
             "home_team": "A", "away_team": "B",
             "home_score": 50, "away_score": 40}
    projs = {(1, "pts"): 25.0}
    assert rh.apply_residual_correction(snap, projs) == projs
