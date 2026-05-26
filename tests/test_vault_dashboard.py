"""tests/test_vault_dashboard.py — R17_J7.

Six tests covering the single-pane-of-glass vault dashboard daemon:
  1. Full render with every source present produces a complete file.
  2. Render with EVERY source missing still produces a valid Markdown file
     with graceful ``(awaiting RXX_YY)`` placeholders for each section.
  3. Section ordering is canonical: header → URGENT → Top Bets → Lineups →
     CLV → Middles → Line Moves → System Health.
  4. atomic_write_text never leaves a partial file (no .tmp residue, replace
     is atomic).
  5. Line-moves window filter only includes events from the last hour.
  6. Top-bets table formats positive odds with ``+`` and respects the limit.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

import vault_dashboard_daemon as vdd  # noqa: E402

UTC = timezone.utc


# --------------------------------------------------------------------------- #
# Fixtures.                                                                   #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def tmp_sources(tmp_path: Path) -> dict:
    """Build a complete set of source files in a tmp dir."""
    # NOTE: cache_dir mirrors the daemon's PROJECT_DIR/data/cache layout so
    # the hardcoded line_moves lookup (PROJECT_DIR/"data"/"cache"/"line_moves_*")
    # resolves correctly when we monkeypatch PROJECT_DIR -> tmp_path.
    live_bets_dir = tmp_path / "live_bets"
    lineups_dir = tmp_path / "lineups"
    cache_dir = tmp_path / "data" / "cache"
    vault_dir = tmp_path / "vault"
    for d in (live_bets_dir, lineups_dir, cache_dir, vault_dir):
        d.mkdir(parents=True, exist_ok=True)

    isodate = "2026-05-26"

    # live_bets payload (matches R16_E2 schema).
    live_bets = {
        "slate_id": "sas_okc_2026-05-26",
        "label": "SAS @ OKC Game 7 WCF",
        "captured_at": "2026-05-26T14:00:00+00:00",
        "tick_idx": 99,
        "stale_books": [],
        "ranked_bets": [
            {
                "player": "Victor Wembanyama", "stat": "blk", "side": "UNDER",
                "book": "bov", "line": 2.5, "odds": 205,
                "edge_pct": 51.62, "kelly_pct_used": 5.0,
                "kelly_stake_$": 50.0, "line_move": "↓LINE",
            },
            {
                "player": "Keldon Johnson", "stat": "reb", "side": "OVER",
                "book": "fd", "line": 3.5, "odds": 190,
                "edge_pct": 39.47, "kelly_pct_used": 5.0,
                "kelly_stake_$": 50.0, "line_move": "",
            },
        ] + [
            {
                "player": f"Filler{i}", "stat": "pts", "side": "OVER",
                "book": "pin", "line": 10.5 + i, "odds": -110,
                "edge_pct": 5.0 + i, "kelly_pct_used": 1.0,
                "kelly_stake_$": 10.0, "line_move": "",
            }
            for i in range(8)
        ],
    }
    (live_bets_dir / f"{isodate}_sas_okc_{isodate}.json").write_text(
        json.dumps(live_bets), encoding="utf-8")

    middles = {
        "generated_at": "2026-05-26T14:00:00Z",
        "n_middles": 2, "n_free_arbs": 1, "n_model_confirmed": 1,
        "middles": [
            {
                "player": "De'Aaron Fox", "stat": "pts",
                "over_book": "bov", "over_line": 3.5, "over_price": 105,
                "under_book": "pin", "under_line": 13.5, "under_price": 117,
                "middle_width": 10.0, "worst_price": 105,
                "free_arb": True, "arb_profit_pct": 5.41,
                "model_band_prob": 0.151, "model_confirmed": True,
            },
            {
                "player": "Chet Holmgren", "stat": "pts",
                "over_book": "bov", "over_line": 3.5, "over_price": -110,
                "under_book": "pin", "under_line": 13.5, "under_price": -125,
                "middle_width": 10.0, "worst_price": -125,
                "free_arb": False, "arb_profit_pct": None,
                "model_band_prob": 0.352, "model_confirmed": True,
            },
        ],
    }
    (cache_dir / "middles_live.json").write_text(json.dumps(middles), encoding="utf-8")

    clv = {
        "n_bets_tracked": 4,
        "mean_clv_pct": 1.83,
        "pct_positive_clv": 75.0,
        "by_book": {
            "pin": {"n": 2, "pos": 1, "mean_clv_pct": 0.5, "pct_positive": 50.0},
            "bov": {"n": 2, "pos": 2, "mean_clv_pct": 3.1, "pct_positive": 100.0},
        },
        "updated_at": "2026-05-26T14:00:00+00:00",
    }
    (cache_dir / "clv_running_total.json").write_text(json.dumps(clv), encoding="utf-8")

    bankroll = {
        "total": 1037.50, "pending": 250.00, "available": 787.50,
        "daily_pnl": 37.50,
    }
    (cache_dir / "bankroll_state.json").write_text(json.dumps(bankroll), encoding="utf-8")

    lineups = {
        "status": "confirmed",
        "teams": [
            {"name": "SAS", "starters": ["Wembanyama", "Vassell", "Fox", "Johnson", "Harper"],
             "scratches": ["Sochan (knee)"]},
            {"name": "OKC", "starters": ["Holmgren", "SGA", "J. Williams", "Dort", "Caruso"]},
        ],
    }
    (lineups_dir / f"{isodate}.json").write_text(json.dumps(lineups), encoding="utf-8")

    urgent = "## 2026-05-26 13:45 — Wemby U2.5 BLK +205 closing 14:30\n\nact fast.\n"
    (vault_dir / "URGENT_BETS.md").write_text(urgent, encoding="utf-8")

    # Line moves: 3 events — 2 within last hour, 1 outside.
    now = datetime.now(UTC)
    moves = [
        {"detected_at": (now - timedelta(minutes=5)).isoformat(),
         "player": "SGA", "stat": "pts", "book": "fd",
         "line_old": 32.5, "line_new": 33.5, "line_delta": 1.0,
         "change": "line 32.5 → 33.5"},
        {"detected_at": (now - timedelta(minutes=30)).isoformat(),
         "player": "Wemby", "stat": "blk", "book": "bov",
         "line_old": 3.0, "line_new": 2.5, "line_delta": -0.5,
         "change": "line 3.0 → 2.5"},
        {"detected_at": (now - timedelta(hours=3)).isoformat(),
         "player": "ZZ_STALE_PLAYER", "stat": "pts", "book": "pin",
         "line_old": 10.5, "line_new": 11.5, "line_delta": 1.0},
    ]
    moves_path = cache_dir / f"line_moves_{isodate}.json"
    with open(moves_path, "w", encoding="utf-8") as fh:
        for ev in moves:
            fh.write(json.dumps(ev) + "\n")

    return {
        "isodate": isodate,
        "tmp_path": tmp_path,
        "live_bets_dir": live_bets_dir,
        "lineups_dir": lineups_dir,
        "cache_dir": cache_dir,
        "vault_dir": vault_dir,
        "moves_path": moves_path,
        "sources": {
            "live_bets_dir": live_bets_dir,
            "middles_path": cache_dir / "middles_live.json",
            "clv_path": cache_dir / "clv_running_total.json",
            "bankroll_path": cache_dir / "bankroll_state.json",
            "lineups_dir": lineups_dir,
            "urgent_path": vault_dir / "URGENT_BETS.md",
        },
    }


# --------------------------------------------------------------------------- #
# Test 1: full render — every source present.                                 #
# --------------------------------------------------------------------------- #
def test_full_render_with_all_sources(tmp_sources, monkeypatch):
    # Force line-moves lookup to point at the tmp cache dir.
    monkeypatch.setattr(vdd, "PROJECT_DIR", tmp_sources["tmp_path"])
    # Bypass network/ps probes.
    monkeypatch.setattr(vdd, "fetch_health", lambda url, timeout=2.0: {
        "now": "2026-05-26T14:00:00",
        "books": {
            "fd": {"alive": True, "last_tick_ago_sec": 0.3,
                   "total_ticks": 50, "total_errors": 0},
        },
    })
    monkeypatch.setattr(vdd, "count_alive_daemons", lambda: 5)

    res = vdd.render_dashboard(
        tmp_sources["isodate"], "fallback label",
        tmp_sources["sources"], health_url="http://ignored",
    )
    text = res["text"]

    # Header label comes from live_bets, not the fallback.
    assert "SAS @ OKC Game 7 WCF" in text
    # Bankroll line is real, not a placeholder.
    assert "$1,037.50" in text
    assert "available $787.50" in text
    assert "+$37.50" in text
    # Top bets.
    assert "Victor Wembanyama" in text
    assert "+205" in text  # positive odds formatted with '+'
    # Lineups.
    assert "Wembanyama" in text and "SGA" in text
    assert "scratches" in text.lower()
    # CLV.
    assert "Mean CLV%" in text and "+1.83%" in text
    # Middles.
    assert "De'Aaron Fox" in text and "ARB" in text
    # Line moves (only the in-window events).
    assert "SGA" in text and "Wemby" in text
    assert "ZZ_STALE_PLAYER" not in text  # 3h ago — filtered out
    # System health.
    assert "Scraper orchestrator: OK" in text
    assert "Daemon count: 5 alive" in text

    # Every source present -> available list has all 8.
    assert len(res["available"]) == 8, res
    assert res["missing"] == [], res


# --------------------------------------------------------------------------- #
# Test 2: render with EVERY source missing — graceful degradation.            #
# --------------------------------------------------------------------------- #
def test_render_with_missing_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(vdd, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(vdd, "fetch_health", lambda url, timeout=2.0: None)
    monkeypatch.setattr(vdd, "count_alive_daemons", lambda: 0)
    empty = {
        "live_bets_dir": tmp_path / "nope_live",
        "middles_path":  tmp_path / "nope_middles.json",
        "clv_path":      tmp_path / "nope_clv.json",
        "bankroll_path": tmp_path / "nope_bankroll.json",
        "lineups_dir":   tmp_path / "nope_lineups",
        "urgent_path":   tmp_path / "nope_urgent.md",
    }
    res = vdd.render_dashboard("2026-05-26", "label", empty, "http://ignored")
    text = res["text"]
    # File still valid Markdown with a header.
    assert text.startswith("# Tonight — 2026-05-26 — label")
    # Every section has its graceful placeholder.
    assert "awaiting R17_J4" in text  # bankroll
    assert "awaiting R17_J3" in text  # urgent
    assert "awaiting R16_E2" in text  # live bets
    assert "awaiting R17_J1" in text  # lineups
    assert "awaiting R16_E8" in text  # CLV
    assert "awaiting R16_E5" in text  # middles
    assert "awaiting R16_E4" in text  # line moves
    assert "health endpoint unreachable" in text  # system health
    assert "Daemon count: 0 alive" in text
    # No source available, all missing.
    assert res["available"] == []
    assert sorted(res["missing"]) == sorted([
        "live_bets", "middles", "clv", "bankroll",
        "lineups", "urgent", "line_moves", "health",
    ])


# --------------------------------------------------------------------------- #
# Test 3: section ordering is canonical.                                      #
# --------------------------------------------------------------------------- #
def test_section_ordering(tmp_sources, monkeypatch):
    monkeypatch.setattr(vdd, "PROJECT_DIR", tmp_sources["tmp_path"])
    monkeypatch.setattr(vdd, "fetch_health", lambda url, timeout=2.0: None)
    monkeypatch.setattr(vdd, "count_alive_daemons", lambda: 1)
    text = vdd.render_dashboard(
        tmp_sources["isodate"], "lbl", tmp_sources["sources"], "http://x",
    )["text"]
    expected_order = [
        "# Tonight",
        "## ⚠️ URGENT",
        "## 🎯 Top 5 Bets",
        "## 🏟️ Lineup Status",
        "## 📊 CLV Running Total",
        "## 💸 Active Middles",
        "## 📈 Line Moves (Last Hour)",
        "## ⚙️ System Health",
    ]
    positions = [text.find(h) for h in expected_order]
    assert all(p >= 0 for p in positions), f"missing heading: {list(zip(expected_order, positions))}"
    assert positions == sorted(positions), \
        f"section order violated: {list(zip(expected_order, positions))}"


# --------------------------------------------------------------------------- #
# Test 4: atomic write leaves no .tmp residue and replaces target atomically. #
# --------------------------------------------------------------------------- #
def test_atomic_write(tmp_path):
    out = tmp_path / "OUT.md"
    vdd.atomic_write_text(out, "hello world\n")
    assert out.read_text(encoding="utf-8") == "hello world\n"
    # Overwrite — still works, no leftover .tmp.
    vdd.atomic_write_text(out, "second\n")
    assert out.read_text(encoding="utf-8") == "second\n"
    assert not (tmp_path / "OUT.md.tmp").exists()
    # Parent auto-created if missing.
    deep = tmp_path / "a" / "b" / "c" / "X.md"
    vdd.atomic_write_text(deep, "deep\n")
    assert deep.read_text(encoding="utf-8") == "deep\n"


# --------------------------------------------------------------------------- #
# Test 5: line-moves window filter respects --window.                         #
# --------------------------------------------------------------------------- #
def test_line_moves_window_filter(tmp_path):
    moves_path = tmp_path / "line_moves_x.json"
    now = datetime.now(UTC)
    events = [
        {"detected_at": (now - timedelta(minutes=10)).isoformat(),
         "player": "A", "stat": "pts", "book": "fd",
         "line_old": 20, "line_new": 21, "line_delta": 1.0},
        {"detected_at": (now - timedelta(hours=2)).isoformat(),
         "player": "STALE", "stat": "pts", "book": "fd",
         "line_old": 5, "line_new": 6, "line_delta": 1.0},
    ]
    with open(moves_path, "w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")
    md = vdd.render_line_moves(moves_path, limit=5, window_min=60)
    assert "A" in md
    assert "STALE" not in md
    # Empty file behaviour.
    empty = tmp_path / "empty_moves.json"
    empty.write_text("", encoding="utf-8")
    assert "no line moves in the last hour" in vdd.render_line_moves(empty)
    # Missing file behaviour.
    missing = tmp_path / "nope.json"
    assert "awaiting R16_E4" in vdd.render_line_moves(missing)


# --------------------------------------------------------------------------- #
# Test 6: top-bets formatter respects limit and formats odds.                 #
# --------------------------------------------------------------------------- #
def test_top_bets_limit_and_odds_formatting():
    payload = {
        "captured_at": "2026-05-26T14:00:00+00:00",
        "tick_idx": 1,
        "stale_books": [],
        "ranked_bets": [
            {"player": f"P{i}", "stat": "pts", "side": "OVER",
             "book": "fd", "line": 10.5, "odds": 150 if i == 0 else -110,
             "edge_pct": 10.0 - i, "kelly_pct_used": 1.0,
             "kelly_stake_$": 10.0, "line_move": ""}
            for i in range(20)
        ],
    }
    md = vdd.render_top_bets(payload, limit=5)
    # Header table is present.
    assert "| Player |" in md
    # Limit honoured: only 5 player rows P0..P4 are in the table.
    for i in range(5):
        assert f"| P{i} " in md
    for i in (5, 6, 19):
        assert f"| P{i} " not in md
    # Positive odds prefixed with '+'.
    assert "+150" in md
    assert "-110" in md
    # Empty ranker -> placeholder.
    empty_md = vdd.render_top_bets({"ranked_bets": []})
    assert "0 positive-EV bets" in empty_md
