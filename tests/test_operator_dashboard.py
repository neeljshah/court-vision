"""tests/test_operator_dashboard.py — R22_O5.

Coverage for the single-pane operator dashboard:

  1. fetch_system_health — daemon registry + heartbeat ages
  2. fetch_bankroll      — bankroll_state.json + R19_L8 filter + ledger rollup
  3. fetch_recent_alerts — vault markdown + critical-stack JSON merge
  4. fetch_active_bets   — pnl_ledger.csv open rows, real-only
  5. fetch_today_slate   — predictions_cache_<date>.parquet top-N
  6. fetch_tracker_status — m2_family freshness + predictions cache age
  7. render_operator_html — all 6 sections present, self-contained
  8. graceful degradation — every helper survives a missing source

Each fetch is exercised independently so a single broken section can't
break the page render.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

import operator_dashboard as od  # noqa: E402


# --------------------------------------------------------------------------- #
# Tiny helpers for synthetic source files                                     #
# --------------------------------------------------------------------------- #
def _write_json(path: Path, blob) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob), encoding="utf-8")


def _write_heartbeat(path: Path, age_sec: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("hb", encoding="utf-8")
    mtime = time.time() - age_sec
    os.utime(path, (mtime, mtime))


def _write_ledger(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "bet_id", "placed_at", "game_id", "player_id", "player", "team",
        "stat", "line", "side", "book", "american_odds", "stake",
        "model_pred", "model_prob", "model_edge", "kelly_pct",
        "status", "settled_at", "actual_stat", "profit_loss",
        "bankroll_after", "strategy",
    ]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


# --------------------------------------------------------------------------- #
# 1. System Health                                                            #
# --------------------------------------------------------------------------- #
def test_fetch_system_health_classifies_green_yellow_red(tmp_path: Path):
    hb_dir = tmp_path / "hb"
    registry = tmp_path / "daemon_registry.json"
    # Three daemons, all with expected_interval_sec=30:
    #   - green: heartbeat 5s old  (<= 30*1.5 = 45s)
    #   - yellow: heartbeat 60s old (45 < 60 <= 90)
    #   - red:   heartbeat missing  (no file)
    _write_json(registry, {"daemons": [
        {"name": "alpha", "expected_interval_sec": 30,
         "heartbeat_file": str(hb_dir / "alpha.txt")},
        {"name": "beta", "expected_interval_sec": 30,
         "heartbeat_file": str(hb_dir / "beta.txt")},
        {"name": "gamma", "expected_interval_sec": 30,
         "heartbeat_file": str(hb_dir / "gamma.txt")},
    ]})
    _write_heartbeat(hb_dir / "alpha.txt", age_sec=5)
    _write_heartbeat(hb_dir / "beta.txt", age_sec=60)
    # gamma intentionally missing.

    h = od.fetch_system_health(registry_path=registry, heartbeat_dir=hb_dir)
    assert h["ok"] is True
    assert h["n_total"] == 3
    by_name = {r["name"]: r for r in h["rows"]}
    assert by_name["alpha"]["status"] == "green"
    assert by_name["beta"]["status"] == "yellow"
    assert by_name["gamma"]["status"] == "red"
    assert h["n_green"] == 1 and h["n_yellow"] == 1 and h["n_red"] == 1


def test_fetch_system_health_missing_registry_returns_empty(tmp_path: Path):
    h = od.fetch_system_health(
        registry_path=tmp_path / "absent.json",
        heartbeat_dir=tmp_path / "absent_hb",
    )
    assert h == {
        "ok": False, "n_total": 0, "n_green": 0, "n_yellow": 0,
        "n_red": 0, "rows": [],
    }


# --------------------------------------------------------------------------- #
# 2. Bankroll                                                                 #
# --------------------------------------------------------------------------- #
def test_fetch_bankroll_combines_state_and_ledger(tmp_path: Path):
    bp = tmp_path / "bankroll_state.json"
    _write_json(bp, {
        "start_bankroll": 1000.0,
        "current_bankroll": 1042.5,
        "available_bankroll": 1000.0,
        "daily_pnl": 42.5,
        "roi": {"roi_pct": 4.25, "n_bets": 3},
        "filter_info": {"n_kept": 2, "n_total": 50, "start_date": "2026-05-25"},
        "as_of": "2026-05-26T15:00:00Z",
    })
    today = "2026-05-26"
    ledger = tmp_path / "pnl_ledger.csv"
    _write_ledger(ledger, [
        {"bet_id": "1", "placed_at": "2026-05-26T10:00:00",
         "player": "Wemby", "stat": "blk", "status": "open", "strategy": "real"},
        {"bet_id": "2", "placed_at": "2026-05-26T11:00:00",
         "player": "Synth", "stat": "pts", "status": "open",
         "strategy": "synthetic_holdout"},
        {"bet_id": "3", "placed_at": "2026-05-25T20:00:00",
         "player": "SGA", "stat": "ast", "status": "won",
         "settled_at": "2026-05-26T03:00:00", "strategy": "real"},
    ])
    b = od.fetch_bankroll(bankroll_path=bp, ledger_path=ledger, today=today)
    assert b["ok"] is True
    assert b["start_bankroll"] == 1000.0
    assert b["current_bankroll"] == 1042.5
    assert b["today_pnl"] == 42.5
    assert b["today_roi_pct"] == 4.25
    # Synth row excluded; one open + one settled today.
    assert b["n_real_bets_open"] == 1
    assert b["n_real_bets_settled_today"] == 1
    assert b["filter_n_kept"] == 2


def test_fetch_bankroll_handles_missing_sources(tmp_path: Path):
    b = od.fetch_bankroll(
        bankroll_path=tmp_path / "absent.json",
        ledger_path=tmp_path / "absent.csv",
    )
    assert b["ok"] is False
    assert b["n_real_bets_open"] == 0
    assert b["n_real_bets_settled_today"] == 0


# --------------------------------------------------------------------------- #
# 3. Recent Alerts                                                            #
# --------------------------------------------------------------------------- #
def test_fetch_recent_alerts_merges_vault_and_critical(tmp_path: Path):
    vault = tmp_path / "alerts.md"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    recent_ts = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_ts    = (now - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%SZ")
    vault.write_text(
        f"# alerts\n"
        f"- {recent_ts} [WARN] [scraper] FD odds stale for 4 minutes\n"
        f"- {old_ts} [INFO] [system] really old line that should drop\n",
        encoding="utf-8",
    )
    alerts_dir = tmp_path / "alerts"
    today_iso = now.strftime("%Y-%m-%d")
    _write_json(alerts_dir / f"critical_{today_iso}.json", [
        {"timestamp": recent_ts, "level": "critical",
         "tag": "discord_fallback", "message": "Discord down — alert queued"},
    ])

    out = od.fetch_recent_alerts(
        vault_path=vault, alerts_dir=alerts_dir, window_hours=24, now=now,
    )
    assert out["ok"] is True
    # Critical from JSON + warn from vault; the 72h-old info row was filtered.
    assert out["counts"]["critical"] == 1
    assert out["counts"]["warn"] == 1
    assert out["counts"]["info"] == 0
    # Latest 5 are sorted newest-first; both equal-time entries should be in.
    msgs = [r["message"] for r in out["latest"]]
    assert any("Discord down" in m for m in msgs)
    assert any("FD odds stale" in m for m in msgs)


def test_fetch_recent_alerts_no_sources(tmp_path: Path):
    out = od.fetch_recent_alerts(
        vault_path=tmp_path / "absent.md",
        alerts_dir=tmp_path / "absent_dir",
    )
    assert out["ok"] is False
    assert out["latest"] == []
    assert out["counts"] == {"critical": 0, "warn": 0, "info": 0}


# --------------------------------------------------------------------------- #
# 4. Active Bets                                                              #
# --------------------------------------------------------------------------- #
def test_fetch_active_bets_returns_open_real_sorted_by_edge(tmp_path: Path):
    ledger = tmp_path / "pnl_ledger.csv"
    _write_ledger(ledger, [
        {"bet_id": "1", "placed_at": "2026-05-26T10:00:00",
         "player": "Wemby", "stat": "blk", "line": "2.5", "side": "UNDER",
         "book": "bov", "model_edge": "0.31", "kelly_pct": "0.025",
         "status": "open", "strategy": "real"},
        {"bet_id": "2", "placed_at": "2026-05-26T11:00:00",
         "player": "SGA", "stat": "reb", "line": "3.5", "side": "OVER",
         "book": "fd", "model_edge": "0.51", "kelly_pct": "0.04",
         "status": "open", "strategy": "real"},
        {"bet_id": "3", "placed_at": "2026-05-25T20:00:00",
         "player": "Chet", "stat": "pts", "line": "20.5", "side": "OVER",
         "status": "lost", "strategy": "real"},
        {"bet_id": "4", "placed_at": "2026-05-26T09:00:00",
         "player": "Synth", "stat": "pts", "line": "10", "side": "OVER",
         "model_edge": "0.99", "status": "open", "strategy": "synthetic"},
    ])
    out = od.fetch_active_bets(ledger_path=ledger, limit=10)
    assert out["ok"] is True
    assert out["n_open"] == 2  # Synth + settled rows excluded.
    # Sorted by edge desc — SGA (0.51) > Wemby (0.31).
    assert out["bets"][0]["player"] == "SGA"
    assert out["bets"][0]["kelly_pct"] == pytest.approx(0.04)
    assert out["bets"][1]["player"] == "Wemby"


def test_fetch_active_bets_missing_ledger(tmp_path: Path):
    out = od.fetch_active_bets(ledger_path=tmp_path / "absent.csv")
    assert out["ok"] is False
    assert out["bets"] == []
    assert out["n_open"] == 0


# --------------------------------------------------------------------------- #
# 5. Today's Slate                                                            #
# --------------------------------------------------------------------------- #
def test_fetch_today_slate_reads_parquet_top_n(tmp_path: Path):
    pd = pytest.importorskip("pandas")
    today = "2026-05-26"
    pq_path = tmp_path / f"predictions_cache_{today}.parquet"
    df = pd.DataFrame([
        {"player_id": 1, "player_name": "Wemby", "team": "SAS", "stat": "pts",
         "q10": 18.0, "q50": 28.0, "q90": 42.0, "sigma": 7.0,
         "computed_at": "2026-05-26T10:00:00Z"},
        {"player_id": 2, "player_name": "SGA", "team": "OKC", "stat": "pts",
         "q10": 22.0, "q50": 32.0, "q90": 40.0, "sigma": 5.0,
         "computed_at": "2026-05-26T10:00:00Z"},
        {"player_id": 3, "player_name": "Chet", "team": "OKC", "stat": "reb",
         "q10": 6.0,  "q50": 8.0,  "q90": 9.0,  "sigma": 1.5,
         "computed_at": "2026-05-26T10:00:00Z"},
    ])
    df.to_parquet(pq_path)
    out = od.fetch_today_slate(predictions_dir=tmp_path, today=today, limit=2)
    assert out["ok"] is True
    assert out["n_rows"] == 2  # limited
    # Top by q90-q50: Wemby (14) > Chet (1) > SGA (8) — Wemby wins, then SGA.
    assert out["top"][0]["player"] == "Wemby"
    assert out["top"][0]["ev_proxy"] == pytest.approx(14.0)


def test_fetch_today_slate_missing_parquet(tmp_path: Path):
    out = od.fetch_today_slate(predictions_dir=tmp_path, today="2026-05-26")
    assert out["ok"] is False
    assert out["top"] == []


# --------------------------------------------------------------------------- #
# 6. Tracker Status                                                           #
# --------------------------------------------------------------------------- #
def test_fetch_tracker_status_green_when_fresh(tmp_path: Path):
    today = "2026-05-26"
    pq = tmp_path / f"predictions_cache_{today}.parquet"
    pq.write_bytes(b"PAR1")  # contents not parsed for this check
    (tmp_path / "m2_family_predictions_2024-25_last100.json").write_text("{}",
                                                                          encoding="utf-8")
    out = od.fetch_tracker_status(predictions_dir=tmp_path, today=today)
    assert out["ok"] is True
    assert out["status"] == "green"
    assert out["predictions_cache_present"] is True
    assert out["m2_family_files"] == 1


def test_fetch_tracker_status_red_when_missing(tmp_path: Path):
    out = od.fetch_tracker_status(predictions_dir=tmp_path, today="1999-01-01")
    assert out["ok"] is False
    assert out["status"] == "red"
    assert out["predictions_cache_present"] is False


def test_fetch_tracker_status_yellow_when_stale(tmp_path: Path):
    today = "2026-05-26"
    pq = tmp_path / f"predictions_cache_{today}.parquet"
    pq.write_bytes(b"PAR1")
    # Force the file to look 50h old (> the default 24h freshness window).
    stale_mtime = time.time() - 50 * 3600
    os.utime(pq, (stale_mtime, stale_mtime))
    out = od.fetch_tracker_status(predictions_dir=tmp_path, today=today)
    assert out["status"] == "yellow"
    assert out["predictions_cache_present"] is True


# --------------------------------------------------------------------------- #
# 7. Full render — all 6 sections appear                                      #
# --------------------------------------------------------------------------- #
def test_render_operator_html_contains_all_six_sections():
    # Every fetch returns the minimal "ok=False" shape — we still want headings.
    empty = {"ok": False}
    html = od.render_operator_html(
        empty, empty, empty, empty, empty, empty,
        auto_refresh_sec=60,
    )
    assert html.startswith("<!DOCTYPE html>")
    assert '<meta http-equiv="refresh" content="60">' in html
    for title in od.SECTION_TITLES:
        assert title in html, f"missing section heading {title!r}"
    # Self-contained — no external URLs.
    assert "http://" not in html
    assert "https://" not in html


def test_collect_and_render_survives_all_missing_sources(tmp_path: Path):
    """Smoke-test the top-level entry with every source absent."""
    html = od.collect_and_render(
        registry_path=tmp_path / "no_registry.json",
        heartbeat_dir=tmp_path / "no_hb",
        bankroll_path=tmp_path / "no_bankroll.json",
        ledger_path=tmp_path / "no_ledger.csv",
        alerts_vault=tmp_path / "no_alerts.md",
        alerts_dir=tmp_path / "no_alerts_dir",
        predictions_dir=tmp_path / "no_preds",
        today="2026-05-26",
    )
    for title in od.SECTION_TITLES:
        assert title in html
    assert "(no" in html  # at least one "no data" placeholder rendered
