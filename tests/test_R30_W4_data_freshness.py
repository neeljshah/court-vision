"""tests/test_R30_W4_data_freshness.py — R30_W4.

Coverage for the operator-dashboard "Data Freshness" section:

  1. All 13 sources reported, regardless of presence
  2. Missing file = red
  3. Fresh file = green
  4. Stale-within-2x = yellow; stale-beyond-2x = red
  5. Per-source threshold respected (lines=60s vs predictions_cache=12h)
  6. Glob-kind source picks the newest match
  7. Graceful degradation when every data dir is missing
  8. HTML output well-formed (section title, dot, status counts)
  9. collect_and_render wires the freshness section without regression
  10. Backward-compat: render_operator_html omits section when data is None
  11. include_data_freshness=False suppresses the section entirely

Every helper is exercised against synthetic tmp_path data so we never
touch real cache files.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

import operator_dashboard as od  # noqa: E402


# --------------------------------------------------------------------------- #
# Tiny helpers — write a file with controlled mtime                           #
# --------------------------------------------------------------------------- #
def _write_aged(path: Path, age_sec: float, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    mtime = time.time() - float(age_sec)
    os.utime(path, (mtime, mtime))


def _make_dirs(tmp_path: Path):
    cache_dir   = tmp_path / "cache"
    lineups_dir = tmp_path / "lineups"
    lines_dir   = tmp_path / "lines"
    backups_dir = tmp_path / "backups"
    vault_dir   = tmp_path / "vault"
    for d in (cache_dir, lineups_dir, lines_dir, backups_dir, vault_dir):
        d.mkdir(parents=True, exist_ok=True)
    return cache_dir, lineups_dir, lines_dir, backups_dir, vault_dir


# --------------------------------------------------------------------------- #
# 1. All 13 sources reported                                                  #
# --------------------------------------------------------------------------- #
def test_fetch_data_freshness_reports_all_13_sources(tmp_path: Path):
    cache_dir, lineups_dir, lines_dir, backups_dir, vault_dir = _make_dirs(tmp_path)
    out = od.fetch_data_freshness(
        cache_dir=cache_dir, lineups_dir=lineups_dir, lines_dir=lines_dir,
        backups_dir=backups_dir, vault_dir=vault_dir, today="2026-05-26",
    )
    assert out["ok"] is True
    assert out["n_total"] == 13
    assert len(out["sources"]) == 13
    names = {s["name"] for s in out["sources"]}
    expected = {
        "predictions_cache", "nba_injuries", "lineups",
        "lines_fd", "lines_bov", "lines_pin",
        "bankroll_state", "middles_live",
        "m2_family_cache", "feature_drift",
        "pnl_ledger_backup", "morning_md", "e2e_smoke",
    }
    assert names == expected, f"missing/extra: {names ^ expected}"


# --------------------------------------------------------------------------- #
# 2. Missing file = red                                                       #
# --------------------------------------------------------------------------- #
def test_missing_files_classified_red(tmp_path: Path):
    cache_dir, lineups_dir, lines_dir, backups_dir, vault_dir = _make_dirs(tmp_path)
    out = od.fetch_data_freshness(
        cache_dir=cache_dir, lineups_dir=lineups_dir, lines_dir=lines_dir,
        backups_dir=backups_dir, vault_dir=vault_dir, today="2026-05-26",
    )
    # Every source absent — all 13 should be red.
    assert out["n_red"] == 13
    assert out["n_green"] == 0
    assert out["n_yellow"] == 0
    for s in out["sources"]:
        assert s["status"] == "red"
        assert s["exists"] is False
        assert s["age_sec"] is None


# --------------------------------------------------------------------------- #
# 3. Fresh file = green                                                       #
# --------------------------------------------------------------------------- #
def test_fresh_file_classified_green(tmp_path: Path):
    cache_dir, lineups_dir, lines_dir, backups_dir, vault_dir = _make_dirs(tmp_path)
    today = "2026-05-26"
    # bankroll_state threshold = 5min; write 30s old → green
    _write_aged(cache_dir / "bankroll_state.json", age_sec=30)
    out = od.fetch_data_freshness(
        cache_dir=cache_dir, lineups_dir=lineups_dir, lines_dir=lines_dir,
        backups_dir=backups_dir, vault_dir=vault_dir, today=today,
    )
    by_name = {s["name"]: s for s in out["sources"]}
    assert by_name["bankroll_state"]["status"] == "green"
    assert by_name["bankroll_state"]["exists"] is True
    assert by_name["bankroll_state"]["age_sec"] < 60


# --------------------------------------------------------------------------- #
# 4. Stale-within-2x = yellow; beyond-2x = red                                #
# --------------------------------------------------------------------------- #
def test_stale_file_yellow_then_red(tmp_path: Path):
    cache_dir, lineups_dir, lines_dir, backups_dir, vault_dir = _make_dirs(tmp_path)
    today = "2026-05-26"
    # bankroll_state threshold = 5min (300s)
    #   - file aged 400s  →  within 2x (600s) → yellow
    _write_aged(cache_dir / "bankroll_state.json", age_sec=400)
    out = od.fetch_data_freshness(
        cache_dir=cache_dir, lineups_dir=lineups_dir, lines_dir=lines_dir,
        backups_dir=backups_dir, vault_dir=vault_dir, today=today,
    )
    by_name = {s["name"]: s for s in out["sources"]}
    assert by_name["bankroll_state"]["status"] == "yellow"

    # Now age the file out beyond 2x → red
    _write_aged(cache_dir / "bankroll_state.json", age_sec=1200)
    out2 = od.fetch_data_freshness(
        cache_dir=cache_dir, lineups_dir=lineups_dir, lines_dir=lines_dir,
        backups_dir=backups_dir, vault_dir=vault_dir, today=today,
    )
    by_name2 = {s["name"]: s for s in out2["sources"]}
    assert by_name2["bankroll_state"]["status"] == "red"
    assert by_name2["bankroll_state"]["exists"] is True  # red != missing


# --------------------------------------------------------------------------- #
# 5. Threshold respected per-source — lines (60s) vs predictions (12h)        #
# --------------------------------------------------------------------------- #
def test_per_source_thresholds_respected(tmp_path: Path):
    cache_dir, lineups_dir, lines_dir, backups_dir, vault_dir = _make_dirs(tmp_path)
    today = "2026-05-26"
    # lines_fd threshold = 60s → 30s old should be green
    _write_aged(lines_dir / f"{today}_fd.csv", age_sec=30)
    # lines_bov threshold = 60s → 75s old should be yellow (between 60 and 120)
    _write_aged(lines_dir / f"{today}_bov.csv", age_sec=75)
    # lines_pin threshold = 60s → 200s old should be red (> 2x)
    _write_aged(lines_dir / f"{today}_pin.csv", age_sec=200)
    # predictions_cache threshold = 12h (43200s) → 1000s old should still be green
    _write_aged(cache_dir / f"predictions_cache_{today}.parquet", age_sec=1000)
    out = od.fetch_data_freshness(
        cache_dir=cache_dir, lineups_dir=lineups_dir, lines_dir=lines_dir,
        backups_dir=backups_dir, vault_dir=vault_dir, today=today,
    )
    by_name = {s["name"]: s for s in out["sources"]}
    assert by_name["lines_fd"]["status"] == "green"
    assert by_name["lines_bov"]["status"] == "yellow"
    assert by_name["lines_pin"]["status"] == "red"
    assert by_name["predictions_cache"]["status"] == "green"
    # threshold_sec round-trip
    assert by_name["lines_fd"]["threshold_sec"] == 60.0
    assert by_name["predictions_cache"]["threshold_sec"] == 12 * 3600.0


# --------------------------------------------------------------------------- #
# 6. Glob source — picks newest match                                         #
# --------------------------------------------------------------------------- #
def test_glob_source_picks_newest_match(tmp_path: Path):
    cache_dir, lineups_dir, lines_dir, backups_dir, vault_dir = _make_dirs(tmp_path)
    today = "2026-05-26"
    # Write two m2_family files; the newer one should drive the age.
    _write_aged(cache_dir / "m2_family_predictions_old.json", age_sec=999_999)
    _write_aged(cache_dir / "m2_family_predictions_new.json", age_sec=60)
    out = od.fetch_data_freshness(
        cache_dir=cache_dir, lineups_dir=lineups_dir, lines_dir=lines_dir,
        backups_dir=backups_dir, vault_dir=vault_dir, today=today,
    )
    by_name = {s["name"]: s for s in out["sources"]}
    s = by_name["m2_family_cache"]
    assert s["exists"] is True
    assert s["age_sec"] < 120  # picked the new one
    # 60s old, 12h threshold → green
    assert s["status"] == "green"
    assert s["path"].endswith("m2_family_predictions_new.json") or \
        s["path"].endswith("m2_family_predictions_new.json".replace("/", os.sep))


# --------------------------------------------------------------------------- #
# 7. Graceful degradation when every dir is missing                           #
# --------------------------------------------------------------------------- #
def test_graceful_degradation_when_dirs_missing(tmp_path: Path):
    # Don't create the directories — point to non-existent paths.
    nope = tmp_path / "does-not-exist"
    out = od.fetch_data_freshness(
        cache_dir=nope / "cache",
        lineups_dir=nope / "lineups",
        lines_dir=nope / "lines",
        backups_dir=nope / "backups",
        vault_dir=nope / "vault",
        today="2026-05-26",
    )
    # All 13 sources still reported, all red, no exception.
    assert out["ok"] is True  # ok=True means the inventory ran
    assert out["n_total"] == 13
    assert out["n_red"] == 13
    assert out["n_green"] == 0


# --------------------------------------------------------------------------- #
# 8. HTML output well-formed                                                  #
# --------------------------------------------------------------------------- #
def test_section_html_well_formed(tmp_path: Path):
    cache_dir, lineups_dir, lines_dir, backups_dir, vault_dir = _make_dirs(tmp_path)
    today = "2026-05-26"
    _write_aged(cache_dir / "bankroll_state.json", age_sec=10)
    _write_aged(lines_dir / f"{today}_fd.csv", age_sec=200)  # red
    d = od.fetch_data_freshness(
        cache_dir=cache_dir, lineups_dir=lineups_dir, lines_dir=lines_dir,
        backups_dir=backups_dir, vault_dir=vault_dir, today=today,
    )
    html = od._section_data_freshness(d)
    assert "<h2>Data Freshness</h2>" in html
    assert 'class="dot"' in html
    # Summary line includes counts.
    assert "green" in html and "yellow" in html and "red" in html
    # Table header columns present.
    assert "<th>Source</th>" in html
    assert "<th>Age</th>" in html
    assert "<th>Threshold</th>" in html
    # Status text uppercased.
    assert "GREEN" in html or "RED" in html


def test_section_html_handles_empty_input():
    html = od._section_data_freshness({"ok": False})
    assert "<h2>Data Freshness</h2>" in html
    assert "no data sources resolved" in html


# --------------------------------------------------------------------------- #
# 9. collect_and_render wires the section + no regression                     #
# --------------------------------------------------------------------------- #
def test_collect_and_render_includes_data_freshness(tmp_path: Path):
    cache_dir, lineups_dir, lines_dir, backups_dir, vault_dir = _make_dirs(tmp_path)
    today = "2026-05-26"
    _write_aged(cache_dir / "bankroll_state.json", age_sec=10)

    html = od.collect_and_render(
        registry_path=tmp_path / "no_registry.json",
        heartbeat_dir=tmp_path / "no_hb",
        bankroll_path=tmp_path / "no_bankroll.json",
        ledger_path=tmp_path / "no_ledger.csv",
        alerts_vault=tmp_path / "no_alerts.md",
        alerts_dir=tmp_path / "no_alerts_dir",
        predictions_dir=tmp_path / "no_preds",
        today=today,
        # Wire the freshness dirs to the synthetic tmp paths.
        freshness_cache_dir=cache_dir,
        freshness_lineups_dir=lineups_dir,
        freshness_lines_dir=lines_dir,
        freshness_backups_dir=backups_dir,
        freshness_vault_dir=vault_dir,
        # Disable heavyweight optional sections so the test runs fast.
        include_live_recs=False,
        include_rec_perf=False,
        include_settlement_health=False,
        include_feature_drift=False,
    )
    # New section present
    assert "<h2>Data Freshness</h2>" in html
    # All existing required sections still present
    for title in od.SECTION_TITLES:
        assert title in html, f"regression: missing {title}"


def test_collect_and_render_can_disable_data_freshness(tmp_path: Path):
    html = od.collect_and_render(
        registry_path=tmp_path / "no.json",
        heartbeat_dir=tmp_path / "no_hb",
        bankroll_path=tmp_path / "no.json",
        ledger_path=tmp_path / "no.csv",
        alerts_vault=tmp_path / "no.md",
        alerts_dir=tmp_path / "no",
        predictions_dir=tmp_path / "no",
        today="2026-05-26",
        include_data_freshness=False,
        include_live_recs=False,
        include_rec_perf=False,
        include_settlement_health=False,
        include_feature_drift=False,
    )
    assert "<h2>Data Freshness</h2>" not in html
    # Existing sections still rendered
    for title in od.SECTION_TITLES:
        assert title in html


# --------------------------------------------------------------------------- #
# 10. render_operator_html backward-compat — section omitted when None        #
# --------------------------------------------------------------------------- #
def test_render_operator_html_backward_compat_omits_when_none():
    empty = {"ok": False}
    html = od.render_operator_html(
        empty, empty, empty, empty, empty, empty,
        auto_refresh_sec=60,
    )
    # Existing 6 sections + boilerplate present, but no freshness section.
    for title in od.SECTION_TITLES:
        assert title in html
    assert "<h2>Data Freshness</h2>" not in html


def test_render_operator_html_includes_freshness_when_passed():
    empty = {"ok": False}
    fresh = {"ok": True, "n_total": 13, "n_green": 12, "n_yellow": 1, "n_red": 0,
             "sources": [{"name": "x", "path": "/x", "age_sec": 5.0,
                          "threshold_sec": 60.0, "status": "green",
                          "exists": True}]}
    html = od.render_operator_html(
        empty, empty, empty, empty, empty, empty,
        data_freshness=fresh, auto_refresh_sec=60,
    )
    assert "<h2>Data Freshness</h2>" in html
    assert "12 green" in html
