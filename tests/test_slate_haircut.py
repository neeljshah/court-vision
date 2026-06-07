"""Tests for the gated CV_SLATE_HAIRCUT fix (cv_fix_build_slate._apply_slate_haircut).

Verifies:
  1. Flag OFF (default) -> byte-identical slate (no q50 changes)
  2. Flag ON -> haircut fires on blowout games (|spread|>=6) for PTS/REB/AST
  3. No-spread / missing mainline -> graceful no-op (no crash, no change)
  4. No double-count: live_adjustment blowout term suppressed when haircut ON
  5. AST handled identically to PTS/REB (haircut applies; OOF-consistent)
  6. Non-volume stats (fg3m, stl, blk, tov) not haircutted
"""
from __future__ import annotations

import importlib
import os

import pandas as pd
import pytest

cfs = importlib.import_module("scripts.cv_fix_build_slate")


# ── Fixtures ───────────────────────────────────────────────────────────────

def _make_cache(spread_games=True):
    """Minimal predictions_cache DataFrame with one game (OKC @ NYK, spread=10)."""
    stats = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
    rows = []
    for pid, team in [(1, "OKC"), (2, "NYK")]:
        for stat in stats:
            rows.append({
                "player_id": pid,
                "player_name": f"Player{pid}",
                "team": team,
                "stat": stat,
                "q50": 20.0 if stat == "pts" else (5.0 if stat == "reb" else 3.0),
                "q10": 12.0 if stat == "pts" else 2.0,
                "q90": 28.0 if stat == "pts" else 8.0,
                "sigma": 5.0,
            })
    return pd.DataFrame(rows)


# Fake games dict (home NYK, away OKC, spread ~10)
_GAMES_BLOWOUT = {
    "0022500001": {"home_abbr": "NYK", "away_abbr": "OKC"},
}
_GAMES_CLOSE = {
    "0022500002": {"home_abbr": "NYK", "away_abbr": "OKC"},
}


# ── 1. Byte-identical when flag OFF ────────────────────────────────────────

def test_flag_off_is_byte_identical(monkeypatch):
    """When CV_SLATE_HAIRCUT is OFF, cache q50 must not change at all."""
    monkeypatch.delenv("CV_SLATE_HAIRCUT", raising=False)
    cache = _make_cache()
    q50_before = cache.set_index(["player_id", "stat"])["q50"].to_dict()
    n = cfs._apply_slate_haircut(cache, _GAMES_BLOWOUT, "2026-05-30")
    q50_after = cache.set_index(["player_id", "stat"])["q50"].to_dict()
    assert n == 0, "must return 0 rows changed when flag OFF"
    assert q50_before == q50_after, "cache must be byte-identical when flag OFF"


# ── 2. Haircut fires on blowout games ─────────────────────────────────────

def _fake_load_spread(date, home, away):
    """Stub returning spread=10 for any game (simulates pregame_spreads hit)."""
    return 10.0


def test_flag_on_haircut_fires_for_pts_reb_ast(monkeypatch):
    """With CV_SLATE_HAIRCUT ON and spread=10, PTS/REB/AST must be reduced by factor 0.95."""
    monkeypatch.setenv("CV_SLATE_HAIRCUT", "1")
    monkeypatch.setattr(cfs, "_load_spread_for_game", _fake_load_spread)
    cache = _make_cache()
    n = cfs._apply_slate_haircut(cache, _GAMES_BLOWOUT, "2026-05-30")
    assert n > 0, "haircut must fire on blowout game"
    # PTS: 20.0 * 0.95 = 19.0
    pts_okc = cache.loc[(cache["player_id"] == 1) & (cache["stat"] == "pts"), "q50"].iloc[0]
    assert abs(pts_okc - 19.0) < 0.01, f"PTS q50 should be 19.0, got {pts_okc}"
    # REB: 5.0 * 0.95 = 4.75
    reb_okc = cache.loc[(cache["player_id"] == 1) & (cache["stat"] == "reb"), "q50"].iloc[0]
    assert abs(reb_okc - 4.75) < 0.01, f"REB q50 should be 4.75, got {reb_okc}"
    # AST: 3.0 * 0.95 = 2.85
    ast_okc = cache.loc[(cache["player_id"] == 1) & (cache["stat"] == "ast"), "q50"].iloc[0]
    assert abs(ast_okc - 2.85) < 0.01, f"AST q50 should be 2.85, got {ast_okc}"


def test_flag_on_no_haircut_for_small_spread(monkeypatch):
    """With spread=4 (< 6 threshold), haircut must be a no-op."""
    monkeypatch.setenv("CV_SLATE_HAIRCUT", "1")
    monkeypatch.setattr(cfs, "_load_spread_for_game", lambda d, h, a: 4.0)
    cache = _make_cache()
    q50_before = cache["q50"].tolist()
    n = cfs._apply_slate_haircut(cache, _GAMES_BLOWOUT, "2026-05-30")
    assert n == 0, "haircut must be no-op for spread<6"
    assert cache["q50"].tolist() == q50_before


# ── 3. Graceful no-op when spread unavailable ─────────────────────────────

def test_no_spread_is_graceful_no_op(monkeypatch):
    """When _load_spread_for_game returns None, haircut must not change any value."""
    monkeypatch.setenv("CV_SLATE_HAIRCUT", "1")
    monkeypatch.setattr(cfs, "_load_spread_for_game", lambda d, h, a: None)
    cache = _make_cache()
    q50_before = cache["q50"].tolist()
    n = cfs._apply_slate_haircut(cache, _GAMES_BLOWOUT, "2026-05-30")
    assert n == 0, "must return 0 when no spread data"
    assert cache["q50"].tolist() == q50_before, "cache unchanged when no spread"


# ── 4. No double-count with freshness blowout term ────────────────────────

def test_no_double_count_vac_bump_blowout_suppressed(monkeypatch):
    """When CV_SLATE_HAIRCUT is ON, _apply_vac_bump must pass game_spread=None.

    We verify by checking that the blowout field in a captured adjust_projection
    call is None when the haircut flag is active.
    """
    monkeypatch.setenv("CV_SLATE_HAIRCUT", "1")
    monkeypatch.setenv("CV_SLATE_VAC_BUMP", "1")

    calls = []

    def _fake_adjust(base, *, vac_share=0.0, game_total=None, game_spread=None, **kw):
        calls.append({"game_spread": game_spread, "game_total": game_total})
        return base

    # Patch _vac_bump_enabled to return True so we enter _apply_vac_bump
    monkeypatch.setattr(cfs, "_vac_bump_enabled", lambda: True)
    # Patch _build_vac_map to return empty (no OUT players needed for this test)
    monkeypatch.setattr(cfs, "_build_vac_map", lambda date, cache: ({}, None))
    # Patch _live_context_for_teams to return a spread context
    monkeypatch.setattr(cfs, "_live_context_for_teams",
                        lambda date, teams: {t: {"total": 225.0, "spread_abs": 14.0}
                                             for t in teams})

    cache = _make_cache()
    # Patch adjust_projection on the REAL live_adjustment module object that
    # `_apply_vac_bump` resolves via `from src.prediction import live_adjustment`.
    # (Patching sys.modules is NOT order-robust: once any earlier test imports
    # the real module, the `from package import name` binding is already on the
    # src.prediction package attribute and a sys.modules.setitem no longer wins —
    # which is why this test passed alone but failed after test_availability.)
    import importlib
    la_mod = importlib.import_module("src.prediction.live_adjustment")
    monkeypatch.setattr(la_mod, "adjust_projection", _fake_adjust)

    cfs._apply_vac_bump(cache, "2026-05-30")

    # Every call must have game_spread=None (suppressed by haircut flag)
    assert calls, "adjust_projection should have been called"
    for call in calls:
        assert call["game_spread"] is None, (
            f"game_spread must be None when CV_SLATE_HAIRCUT=ON, got {call['game_spread']}"
        )
    # game_total should still be passed (pace term not suppressed)
    assert any(c["game_total"] is not None for c in calls), \
        "game_total (pace) must still be passed when only blowout is suppressed"


# ── 5. AST handled identically ────────────────────────────────────────────

def test_ast_haircutted_same_as_pts_reb(monkeypatch):
    """AST should get the same haircut factor as PTS/REB for the same spread."""
    monkeypatch.setenv("CV_SLATE_HAIRCUT", "1")
    monkeypatch.setattr(cfs, "_load_spread_for_game", _fake_load_spread)  # spread=10
    cache = _make_cache()
    cfs._apply_slate_haircut(cache, _GAMES_BLOWOUT, "2026-05-30")
    for pid in [1, 2]:
        for stat in ["pts", "reb", "ast"]:
            row = cache.loc[(cache["player_id"] == pid) & (cache["stat"] == stat)]
            orig = 20.0 if stat == "pts" else (5.0 if stat == "reb" else 3.0)
            expected = round(orig * 0.95, 3)
            actual = round(float(row["q50"].iloc[0]), 3)
            assert abs(actual - expected) < 0.01, (
                f"{stat} pid={pid}: expected {expected}, got {actual}"
            )


# ── 6. Non-volume stats NOT haircutted ────────────────────────────────────

def test_non_volume_stats_not_haircutted(monkeypatch):
    """fg3m, stl, blk, tov must NOT be modified by the haircut (not in _GARBAGE_HAIRCUT_STATS)."""
    monkeypatch.setenv("CV_SLATE_HAIRCUT", "1")
    monkeypatch.setattr(cfs, "_load_spread_for_game", _fake_load_spread)  # spread=10
    cache = _make_cache()
    q50_before = {(int(r["player_id"]), r["stat"]): float(r["q50"])
                  for _, r in cache.iterrows()}
    cfs._apply_slate_haircut(cache, _GAMES_BLOWOUT, "2026-05-30")
    for stat in ["fg3m", "stl", "blk", "tov"]:
        for pid in [1, 2]:
            before = q50_before[(pid, stat)]
            after = float(cache.loc[(cache["player_id"] == pid) & (cache["stat"] == stat),
                                    "q50"].iloc[0])
            assert abs(after - before) < 1e-9, \
                f"{stat} pid={pid} must not be haircutted (got {before}->{after})"


# ── 7. q10/q90/sigma scaled proportionally ────────────────────────────────

def test_quantiles_scaled_proportionally(monkeypatch):
    """q10, q90, sigma must scale by the same ratio as q50."""
    monkeypatch.setenv("CV_SLATE_HAIRCUT", "1")
    monkeypatch.setattr(cfs, "_load_spread_for_game", _fake_load_spread)  # spread=10 -> factor=0.95
    cache = _make_cache()
    cfs._apply_slate_haircut(cache, _GAMES_BLOWOUT, "2026-05-30")
    row = cache.loc[(cache["player_id"] == 1) & (cache["stat"] == "pts")].iloc[0]
    # Original: q50=20, q10=12, q90=28, sigma=5 -> factor=0.95
    assert abs(row["q50"] - 19.0) < 0.01
    assert abs(row["q10"] - 11.4) < 0.01
    assert abs(row["q90"] - 26.6) < 0.01
    assert abs(row["sigma"] - 4.75) < 0.01


# ── 8. Gap-G overlay-bypass: haircut written back to the cache parquet ──────
#
# _predictions_overlay (api/_build_home_data) reads predictions_cache_<date>.
# parquet DIRECTLY, bypassing the slate CSV.  The Gap-G fix writes the
# haircut-mutated cache back so /api/home serves the same validated (haircut)
# q50 as /tonight + /api/slate.  These tests pin both directions:
#   ON  + blowout -> cache parquet on disk IS haircut (overlay sees it)
#   OFF           -> cache parquet on disk is byte-identical (no writeback)

def _run_main_against_temp_cache(monkeypatch, tmp_path, *, haircut_on, spread):
    """Run cv_fix_build_slate.main() against a temp cache+slate dir and return
    the cache parquet's PTS q50 for pid=1 AFTER the build."""
    import sys
    import pandas as _pd

    date = "2026-05-30"
    cache_dir = tmp_path / "cache"
    pred_dir = tmp_path / "predictions"
    cache_dir.mkdir()
    pred_dir.mkdir()
    cache_path = cache_dir / f"predictions_cache_{date}.parquet"
    _make_cache().to_parquet(cache_path, index=False)

    # Redirect module dirs to temp so no real files are touched.
    monkeypatch.setattr(cfs, "CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(cfs, "PRED_DIR", str(pred_dir))
    # Stub the slate-shaping I/O so main() runs offline + deterministically.
    monkeypatch.setattr(cfs, "_games_for_date",
                        lambda d, g: {"42500301": {"home_abbr": "OKC", "away_abbr": "NYK"}})
    monkeypatch.setattr(cfs, "_ensure_cache", lambda d: str(cache_path))
    monkeypatch.setattr(cfs, "out_players", lambda d: set())
    monkeypatch.setattr(cfs, "_load_spread_for_game", lambda d, h, a: spread)
    # Vac-bump OFF for this test (isolate the haircut writeback path).
    monkeypatch.delenv("CV_SLATE_VAC_BUMP", raising=False)
    if haircut_on:
        monkeypatch.setenv("CV_SLATE_HAIRCUT", "1")
    else:
        monkeypatch.delenv("CV_SLATE_HAIRCUT", raising=False)

    monkeypatch.setattr(sys, "argv", ["cv_fix_build_slate.py", "--date", date])
    cfs.main()

    disk = _pd.read_parquet(cache_path)
    return float(disk.loc[(disk["player_id"] == 1) & (disk["stat"] == "pts"),
                          "q50"].iloc[0])


def test_gapg_haircut_written_back_to_cache(monkeypatch, tmp_path):
    """Flag ON + |spread|>=14 -> cache parquet on disk carries the 0.92 haircut
    so the overlay (/api/home) serves the same value as the slate (/tonight)."""
    disk_q50 = _run_main_against_temp_cache(
        monkeypatch, tmp_path, haircut_on=True, spread=14.0)
    # _make_cache PTS q50 = 20.0 ; |spread|=14 -> factor 0.92 -> 18.4
    assert abs(disk_q50 - 18.4) < 0.01, (
        f"overlay cache must carry the haircut (expected 18.4, got {disk_q50})")


def test_gapg_flag_off_cache_byte_identical(monkeypatch, tmp_path):
    """Flag OFF -> cache parquet on disk is unchanged (no writeback)."""
    disk_q50 = _run_main_against_temp_cache(
        monkeypatch, tmp_path, haircut_on=False, spread=14.0)
    assert abs(disk_q50 - 20.0) < 1e-9, (
        f"flag OFF must leave cache byte-identical (expected 20.0, got {disk_q50})")
