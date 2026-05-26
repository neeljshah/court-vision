"""tests/test_R25_R1_backfill.py — R25_R1 pregame-feature backfill tests.

Six checks for ``scripts/backfill_pregame_features_2025_26.py`` output:
  1. schema completeness — every enriched row carries the v9 column set
  2. no leakage — first game of each team's season has default ratings
     (the expanding window has 0 prior samples, so std_lookup returns
     league averages), and ELO == 1500.0 before any prior result
  3. correctness — a known mid-season row's home_off_rtg / pace are in
     plausible NBA ranges (95-130 / 90-110)
  4. row count parity — output has the same 1230 game_ids as the
     schedule stub, no duplicates
  5. backup exists — the .bak_R25_R1 sidecar preserves the original
  6. prior-season fallback — schedule-only stubs (5 rows lacking
     home_team in the source) are carried forward, not dropped

Tests skip gracefully when the backfilled file is absent (fresh clone).
"""
from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_OUT = os.path.join(PROJECT_DIR, "data", "nba", "season_games_2025-26.json")
_BAK = _OUT + ".bak_R25_R1"

_RICH_COLS = [
    "home_off_rtg", "home_def_rtg", "home_net_rtg", "home_pace",
    "home_efg_pct", "home_ts_pct", "home_tov_pct",
    "home_rest_days", "home_back_to_back", "home_travel_miles",
    "home_last5_wins", "home_season_win_pct",
    "away_off_rtg", "away_def_rtg", "away_net_rtg", "away_pace",
    "away_efg_pct", "away_ts_pct", "away_tov_pct",
    "away_rest_days", "away_back_to_back", "away_travel_miles",
    "away_last5_wins", "away_season_win_pct",
    "net_rtg_diff", "pace_diff", "home_advantage",
    "home_top_lineup_net_rtg", "away_top_lineup_net_rtg",
    "ref_avg_fouls", "ref_home_win_pct",
    "iso_matchup_edge", "ref_fta_tendency",
    "home_elo", "away_elo", "elo_differential",
    "home_def_rtg_trend", "away_def_rtg_trend",
    "home_pace_variance", "away_pace_variance",
    "home_hustle_deflections_pg", "away_hustle_deflections_pg",
    "home_pnr_ppp", "away_pnr_ppp",
    "b2b_diff", "elo_pace_interaction",
    "home_stars_available", "away_stars_available",
    "home_bench_net_rtg", "away_bench_net_rtg",
    "home_off_rtg_L10", "home_def_rtg_L10", "home_net_rtg_L10",
    "away_off_rtg_L10", "away_def_rtg_L10", "away_net_rtg_L10",
    "home_srs", "away_srs",
    "home_efg_L10", "away_efg_L10",
    "home_tov_pct_L10", "away_tov_pct_L10",
    "home_oreb_pct_L10", "away_oreb_pct_L10",
    "home_ft_rate_L10", "away_ft_rate_L10",
    "home_off_rtg_home_L10", "away_off_rtg_away_L10",
    "home_off_rtg_vs_top_def", "away_off_rtg_vs_top_def",
    "sim_win_prob", "sim_score_diff_mean", "sim_score_diff_std", "sim_pace_adj",
]


def _load_rows():
    if not os.path.exists(_OUT):
        pytest.skip(f"{_OUT} not present (fresh clone)")
    with open(_OUT, encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict) or "rows" not in payload:
        pytest.skip(f"{_OUT} is not a v9 dict payload")
    if payload.get("v") != 9:
        pytest.skip(f"{_OUT} v={payload.get('v')} != 9 (rerun backfill)")
    return payload["rows"]


def test_schema_completeness():
    """Every enriched row (one with home_team) carries the full v9 column set."""
    rows = _load_rows()
    enriched = [r for r in rows if r.get("home_team") and r.get("away_team")]
    assert len(enriched) >= 1000, (
        f"only {len(enriched)} enriched rows; backfill incomplete"
    )
    sample = enriched[len(enriched) // 2]
    missing = [c for c in _RICH_COLS if c not in sample]
    assert not missing, f"missing columns on mid-season row: {missing[:10]}"


def test_no_leakage_early_season():
    """First game of the season → 0 prior samples → expanding window returns
    league-default ratings (off_rtg=112.0, ELO=1500.0). This is the
    canonical signature of leakage-free expanding-window stats.
    """
    rows = _load_rows()
    enriched = [r for r in rows if r.get("home_team") and r.get("home_off_rtg")
                is not None]
    enriched.sort(key=lambda r: (r.get("game_date", ""), r.get("game_id", "")))
    # Opening night (every team has 0 prior games)
    opening = [r for r in enriched if r.get("game_date") == "2025-10-21"]
    assert opening, "no opening-night games found"
    for r in opening:
        # Expanding window: needs ≥3 prior games → falls back to _DEFAULT
        assert r["home_off_rtg"] == 112.0, (
            f"opening-night {r['home_team']} home_off_rtg={r['home_off_rtg']} "
            f"!= 112.0 — leakage suspected (using season-final stats?)"
        )
        assert r["away_off_rtg"] == 112.0
        assert r["home_elo"] == 1500.0, (
            f"opening-night ELO={r['home_elo']} != 1500 — leakage"
        )
        assert r["away_elo"] == 1500.0


def test_correctness_plausible_ranges():
    """Mid-season rows: ratings in NBA-plausible ranges. Catches the
    pace-as-MIN bug (which produced pace ~480) and any unit scaling errors.
    """
    rows = _load_rows()
    enriched = [r for r in rows if r.get("home_team") and r.get("home_off_rtg")
                is not None and r.get("game_date", "") >= "2026-01-01"]
    assert len(enriched) >= 200, "too few mid-season rows for spot check"
    for r in enriched[:20]:
        assert 95.0 <= r["home_off_rtg"] <= 130.0, (
            f"{r['game_date']} {r['home_team']} ortg={r['home_off_rtg']} OOR"
        )
        assert 95.0 <= r["home_def_rtg"] <= 130.0
        assert 90.0 <= r["home_pace"] <= 110.0, (
            f"{r['game_date']} {r['home_team']} pace={r['home_pace']} OOR"
        )
        assert 0.40 <= r["home_efg_pct"] <= 0.65
        assert 0.05 <= r["home_tov_pct"] <= 0.20
        assert 1200.0 <= r["home_elo"] <= 1800.0


def test_row_count_and_uniqueness():
    """1230 NBA regular-season games, no duplicate game_ids."""
    rows = _load_rows()
    gids = [r.get("game_id") for r in rows if r.get("game_id")]
    assert len(rows) == 1230, f"expected 1230 rows, got {len(rows)}"
    assert len(gids) == 1230
    assert len(set(gids)) == 1230, "duplicate game_ids in output"


def test_backup_preserved():
    """Original schedule-stub file is preserved as .bak_R25_R1."""
    if not os.path.exists(_BAK):
        pytest.skip(f"{_BAK} not present (backfill not run yet)")
    with open(_BAK, encoding="utf-8") as f:
        bak = json.load(f)
    assert isinstance(bak, dict), "backup not a dict"
    bak_rows = bak.get("rows", [])
    assert len(bak_rows) == 1230, (
        f"backup has {len(bak_rows)} rows, expected 1230 (schedule stub)"
    )
    # Backup should look like the original 5-column stub
    sample = bak_rows[0]
    assert "game_id" in sample
    assert "game_date" in sample
    # The pre-backfill file had no rich columns
    assert "home_off_rtg" not in sample, (
        "backup looks like a backfilled file — original may have been lost"
    )


def test_schedule_stubs_carried_forward():
    """The 5 stubs in the original file that lack home_team must still be
    present in the backfilled output — they have no API match (probably
    cancelled / postponed / data-quality holes) but their game_id should
    be preserved so downstream consumers can identify them as scheduled-
    but-unplayable."""
    rows = _load_rows()
    # Stubs are recognisable: have game_id + season + game_date but no home_team
    stubs = [r for r in rows if not r.get("home_team")]
    # Should be ≥3 — original had 5; we carry through any the API can't pair
    assert len(stubs) >= 3, (
        f"expected schedule-only stubs to be carried forward, "
        f"got {len(stubs)}"
    )
    for s in stubs:
        assert s.get("game_id"), f"stub missing game_id: {s}"
        assert s.get("game_date"), f"stub missing game_date: {s}"
