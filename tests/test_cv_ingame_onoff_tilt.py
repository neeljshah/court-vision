"""tests/test_cv_ingame_onoff_tilt.py — CV_INGAME_ONOFF_TILT unit tests.

Validates:
  1. FLAG OFF  — apply_onoff_tilt returns rows byte-identical (no mutation).
  2. FLAG OFF  — no 'onoff_tilt_mult' key added anywhere.
  3. Positive tilt — oncourt player's projected_final increases for a lineup
     with above-average net_rtg.
  4. Negative tilt — oncourt player's projected_final decreases for a below-
     average lineup.
  5. Bench player — projected_final UNCHANGED (not in tilt_map).
  6. Stat guard — only pts/reb/ast are tilted; fg3m/stl/blk/tov untouched.
  7. Tilt cap — raw delta > MAX_TILT_RAW gets clamped to ±MAX_TILT.
  8. Missing lineup file — graceful no-op (tilt == 1.0).
  9. Fewer than 5 starters in box file — graceful no-op.
 10. _infer_point — endQ1/Q2/Q3 at clock ~12:00; None mid-quarter.
 11. _season_of — correct season strings from game_id prefix.
 12. compute_tilt_map integration — with synthetic quarter_box + lineup files.
 13. apply_onoff_tilt mid-period — no-op (point is None).

All tests are offline (no network, no real filesystem reads). Lineup and
quarter_box files are written to tmp dirs.
"""
from __future__ import annotations

import copy
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


# ---------------------------------------------------------------------------
# Helper: import module with flag set / unset
# ---------------------------------------------------------------------------

def _import_mod(*, flag_on: bool):
    """Import snapshot_onoff_tilt_enricher with CV_INGAME_ONOFF_TILT patched."""
    old = os.environ.get("CV_INGAME_ONOFF_TILT")
    os.environ["CV_INGAME_ONOFF_TILT"] = "1" if flag_on else "0"
    try:
        import src.ingame.snapshot_onoff_tilt_enricher as mod
        importlib.reload(mod)
        # Clear the module-level cache so tests don't share lineup state.
        mod._LINEUP_INDEX_CACHE.clear()
        return mod
    finally:
        if old is None:
            os.environ.pop("CV_INGAME_ONOFF_TILT", None)
        else:
            os.environ["CV_INGAME_ONOFF_TILT"] = old


# ---------------------------------------------------------------------------
# Fixtures: synthetic data builders
# ---------------------------------------------------------------------------

_HOME = "HOM"
_AWAY = "AWY"
_HOME_PIDS = [1001, 1002, 1003, 1004, 1005]
_AWAY_PIDS = [2001, 2002, 2003, 2004, 2005]


def _make_snap(*, period: int = 2, clock: str = "12:00",
               game_id: str = "0022400001") -> dict:
    """Minimal snapshot at start of ``period`` (= end of prior quarter)."""
    players = []
    for pid in _HOME_PIDS + _AWAY_PIDS:
        players.append({
            "player_id": pid,
            "team": _HOME if pid < 2000 else _AWAY,
            "min": 12.0,
            "pts": 10.0, "reb": 3.0, "ast": 2.0,
            "fg3m": 1.0, "stl": 0.5, "blk": 0.2, "tov": 1.0,
        })
    return {
        "game_id": game_id,
        "period": period,
        "clock": clock,
        "home_team": _HOME,
        "away_team": _AWAY,
        "players": players,
    }


def _make_rows(*, player_ids, stats=("pts", "reb", "ast"),
               projected_final: float = 20.0) -> List[dict]:
    rows = []
    for pid in player_ids:
        for stat in stats:
            rows.append({
                "player_id": pid,
                "stat": stat,
                "projected_final": projected_final,
                "current": 10.0,
            })
    return rows


def _write_quarter_box(tmp_path: Path, game_id: str, quarter: int,
                       home_pids: List[int], away_pids: List[int]) -> None:
    """Write a synthetic quarter box JSON with start_position starters."""
    players = []
    for pid in home_pids:
        players.append({
            "player_id": pid,
            "team_abbreviation": _HOME,
            "start_position": "F",
            "min": "8:00",
        })
    for pid in away_pids:
        players.append({
            "player_id": pid,
            "team_abbreviation": _AWAY,
            "start_position": "G",
            "min": "8:00",
        })
    data = {"game_id": game_id, "period": quarter, "players": players}
    path = tmp_path / f"{game_id}_q{quarter}.json"
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_lineup_json(tmp_path: Path, team: str, season: str,
                       pids: List[int], net_rtg: float,
                       avg_net_rtg: float = 0.0) -> None:
    """Write a synthetic lineup JSON with one target unit + a filler unit."""
    group_id = "-" + "-".join(str(p) for p in sorted(pids)) + "-"
    # Add a second unit with avg_net_rtg so weighted average ≈ avg_net_rtg.
    # Use high minutes for filler to dominate the average.
    filler_pids = [p + 9000 for p in pids]
    filler_group = "-" + "-".join(str(p) for p in sorted(filler_pids)) + "-"
    lineups = [
        {
            "group_id": group_id,
            "net_rtg": net_rtg,
            "min": 50.0,
        },
        {
            "group_id": filler_group,
            "net_rtg": avg_net_rtg,
            "min": 950.0,   # dominant weight pulls average close to avg_net_rtg
        },
    ]
    path = tmp_path / f"lineup_splits_{team}_{season}.json"
    path.write_text(json.dumps(lineups), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFlagOff:
    """apply_onoff_tilt is a pure no-op when flag is OFF."""

    def test_returns_identical_list_object(self):
        mod = _import_mod(flag_on=False)
        snap = _make_snap()
        rows = _make_rows(player_ids=_HOME_PIDS + _AWAY_PIDS)
        rows_before = copy.deepcopy(rows)
        result = mod.apply_onoff_tilt(snap, rows)
        assert result is rows   # same object
        assert result == rows_before   # unchanged content

    def test_no_onoff_tilt_mult_key(self):
        mod = _import_mod(flag_on=False)
        snap = _make_snap()
        rows = _make_rows(player_ids=_HOME_PIDS)
        mod.apply_onoff_tilt(snap, rows)
        for r in rows:
            assert "onoff_tilt_mult" not in r


class TestPointInference:
    """_infer_point returns correct point strings at quarter boundaries."""

    def _infer(self, period, clock):
        mod = _import_mod(flag_on=True)
        return mod._infer_point({"period": period, "clock": clock})

    def test_endQ1_period2_12min(self):
        assert self._infer(2, "12:00") == "endQ1"

    def test_endQ2_period3_12min(self):
        assert self._infer(3, "12:00") == "endQ2"

    def test_endQ3_period4_12min(self):
        assert self._infer(4, "12:00") == "endQ3"

    def test_mid_quarter_none(self):
        assert self._infer(2, "06:30") is None

    def test_period1_none(self):
        assert self._infer(1, "12:00") is None

    def test_period5_ot_none(self):
        # OT — no defined endQ point in our mapping
        assert self._infer(5, "12:00") is None


class TestSeasonOf:
    """_season_of extracts the season string from game_id prefix."""

    def test_2024_25(self):
        mod = _import_mod(flag_on=True)
        assert mod._season_of("0022400001") == "2024-25"

    def test_2025_26(self):
        mod = _import_mod(flag_on=True)
        assert mod._season_of("0022500001") == "2025-26"

    def test_short_id_fallback(self):
        mod = _import_mod(flag_on=True)
        # Should not raise; fallback to "2024-25"
        result = mod._season_of("001")
        assert isinstance(result, str)


def _run_with_flag(mod, flag_on, fn):
    """Call fn() with CV_INGAME_ONOFF_TILT set/unset around the call."""
    old = os.environ.get("CV_INGAME_ONOFF_TILT")
    os.environ["CV_INGAME_ONOFF_TILT"] = "1" if flag_on else "0"
    try:
        return fn()
    finally:
        if old is None:
            os.environ.pop("CV_INGAME_ONOFF_TILT", None)
        else:
            os.environ["CV_INGAME_ONOFF_TILT"] = old


class TestTiltApplication:
    """Core tilt logic: positive delta increases projected_final."""

    def test_positive_delta_increases_pts(self, tmp_path):
        mod = _import_mod(flag_on=True)
        # lineup net_rtg = +20, team avg ≈ 1.0 (filler at 0 with 950 min)
        # delta ≈ 19, raw_tilt = 0.02 * 19 / 100 = 0.0038 → mult ≈ 1.0038
        _write_quarter_box(tmp_path, "0022400001", 2, _HOME_PIDS, _AWAY_PIDS)
        _write_lineup_json(tmp_path, _HOME, "2024-25", _HOME_PIDS,
                           net_rtg=20.0, avg_net_rtg=0.0)
        _write_lineup_json(tmp_path, _AWAY, "2024-25", _AWAY_PIDS,
                           net_rtg=0.0, avg_net_rtg=0.0)
        mod._LINEUP_INDEX_CACHE.clear()

        snap = _make_snap(period=2, clock="12:00", game_id="0022400001")
        rows = _make_rows(player_ids=_HOME_PIDS, stats=("pts",),
                          projected_final=20.0)
        rows_orig = copy.deepcopy(rows)

        result = _run_with_flag(mod, True, lambda: mod.apply_onoff_tilt(
            snap, rows, quarter_box_dir=tmp_path, lineup_dir=tmp_path,
        ))

        # projected_final should have increased for HOME oncourt players
        for r in result:
            assert r["projected_final"] > rows_orig[result.index(r)]["projected_final"], \
                f"Expected increase for pid={r['player_id']} stat={r['stat']}"

    def test_negative_delta_decreases_pts(self, tmp_path):
        mod = _import_mod(flag_on=True)
        # lineup net_rtg = -20 vs avg ≈ 0 → delta ≈ -20 → mult < 1
        _write_quarter_box(tmp_path, "0022400001", 2, _HOME_PIDS, _AWAY_PIDS)
        _write_lineup_json(tmp_path, _HOME, "2024-25", _HOME_PIDS,
                           net_rtg=-20.0, avg_net_rtg=0.0)
        _write_lineup_json(tmp_path, _AWAY, "2024-25", _AWAY_PIDS,
                           net_rtg=0.0, avg_net_rtg=0.0)
        mod._LINEUP_INDEX_CACHE.clear()

        snap = _make_snap(period=2, clock="12:00", game_id="0022400001")
        rows = _make_rows(player_ids=_HOME_PIDS, stats=("pts",),
                          projected_final=20.0)
        rows_orig = copy.deepcopy(rows)

        result = _run_with_flag(mod, True, lambda: mod.apply_onoff_tilt(
            snap, rows, quarter_box_dir=tmp_path, lineup_dir=tmp_path,
        ))
        for r, orig in zip(result, rows_orig):
            assert r["projected_final"] < orig["projected_final"]

    def test_bench_player_untouched(self, tmp_path):
        mod = _import_mod(flag_on=True)
        _write_quarter_box(tmp_path, "0022400001", 2, _HOME_PIDS, _AWAY_PIDS)
        _write_lineup_json(tmp_path, _HOME, "2024-25", _HOME_PIDS,
                           net_rtg=15.0, avg_net_rtg=0.0)
        _write_lineup_json(tmp_path, _AWAY, "2024-25", _AWAY_PIDS,
                           net_rtg=0.0, avg_net_rtg=0.0)
        mod._LINEUP_INDEX_CACHE.clear()

        snap = _make_snap(period=2, clock="12:00", game_id="0022400001")
        bench_pid = 9999  # not in any oncourt set
        rows = _make_rows(player_ids=[bench_pid], stats=("pts",),
                          projected_final=20.0)

        result = _run_with_flag(mod, True, lambda: mod.apply_onoff_tilt(
            snap, rows, quarter_box_dir=tmp_path, lineup_dir=tmp_path,
        ))
        assert result[0]["projected_final"] == pytest.approx(20.0), \
            "Bench player projected_final must be unchanged"

    def test_stat_guard_fg3m_stl_untouched(self, tmp_path):
        mod = _import_mod(flag_on=True)
        _write_quarter_box(tmp_path, "0022400001", 2, _HOME_PIDS, _AWAY_PIDS)
        _write_lineup_json(tmp_path, _HOME, "2024-25", _HOME_PIDS,
                           net_rtg=20.0, avg_net_rtg=0.0)
        _write_lineup_json(tmp_path, _AWAY, "2024-25", _AWAY_PIDS,
                           net_rtg=20.0, avg_net_rtg=0.0)
        mod._LINEUP_INDEX_CACHE.clear()

        snap = _make_snap(period=2, clock="12:00", game_id="0022400001")
        rows = _make_rows(player_ids=_HOME_PIDS[:1],
                          stats=("fg3m", "stl", "blk", "tov"),
                          projected_final=5.0)
        rows_orig = copy.deepcopy(rows)

        result = _run_with_flag(mod, True, lambda: mod.apply_onoff_tilt(
            snap, rows, quarter_box_dir=tmp_path, lineup_dir=tmp_path,
        ))
        for r, orig in zip(result, rows_orig):
            assert r["projected_final"] == pytest.approx(orig["projected_final"]), \
                f"stat={r['stat']} should NOT be tilted"

    def test_tilt_cap(self, tmp_path):
        """delta = +1000 (absurd) → tilt capped at MAX_TILT."""
        mod = _import_mod(flag_on=True)
        _write_quarter_box(tmp_path, "0022400001", 2, _HOME_PIDS, _AWAY_PIDS)
        _write_lineup_json(tmp_path, _HOME, "2024-25", _HOME_PIDS,
                           net_rtg=1000.0, avg_net_rtg=0.0)
        _write_lineup_json(tmp_path, _AWAY, "2024-25", _AWAY_PIDS,
                           net_rtg=0.0, avg_net_rtg=0.0)
        mod._LINEUP_INDEX_CACHE.clear()

        snap = _make_snap(period=2, clock="12:00", game_id="0022400001")
        rows = _make_rows(player_ids=_HOME_PIDS[:1], stats=("pts",),
                          projected_final=10.0)

        result = _run_with_flag(mod, True, lambda: mod.apply_onoff_tilt(
            snap, rows, quarter_box_dir=tmp_path, lineup_dir=tmp_path,
        ))
        mult = result[0]["projected_final"] / 10.0
        max_expected = 1.0 + mod._MAX_TILT
        assert mult <= max_expected + 1e-9, \
            f"Tilt capped at MAX_TILT={mod._MAX_TILT}, got mult={mult}"

    def test_diagnostic_key_set(self, tmp_path):
        """onoff_tilt_mult is stamped on tilted rows."""
        mod = _import_mod(flag_on=True)
        _write_quarter_box(tmp_path, "0022400001", 2, _HOME_PIDS, _AWAY_PIDS)
        _write_lineup_json(tmp_path, _HOME, "2024-25", _HOME_PIDS,
                           net_rtg=10.0, avg_net_rtg=0.0)
        _write_lineup_json(tmp_path, _AWAY, "2024-25", _AWAY_PIDS,
                           net_rtg=0.0, avg_net_rtg=0.0)
        mod._LINEUP_INDEX_CACHE.clear()

        snap = _make_snap(period=2, clock="12:00", game_id="0022400001")
        rows = _make_rows(player_ids=_HOME_PIDS[:1], stats=("pts",))
        _run_with_flag(mod, True, lambda: mod.apply_onoff_tilt(
            snap, rows, quarter_box_dir=tmp_path, lineup_dir=tmp_path,
        ))
        assert "onoff_tilt_mult" in rows[0]
        assert rows[0]["onoff_tilt_mult"] > 1.0


class TestGracefulNoop:
    """Missing data → no-op, no exception."""

    def test_missing_lineup_file(self, tmp_path):
        mod = _import_mod(flag_on=True)
        # Write quarter_box but NO lineup file.
        _write_quarter_box(tmp_path, "0022400001", 2, _HOME_PIDS, _AWAY_PIDS)
        mod._LINEUP_INDEX_CACHE.clear()

        snap = _make_snap(period=2, clock="12:00", game_id="0022400001")
        rows = _make_rows(player_ids=_HOME_PIDS, stats=("pts",),
                          projected_final=20.0)
        rows_before = copy.deepcopy(rows)

        result = _run_with_flag(mod, True, lambda: mod.apply_onoff_tilt(
            snap, rows, quarter_box_dir=tmp_path, lineup_dir=tmp_path,
        ))
        assert result == rows_before

    def test_missing_quarter_box_file(self, tmp_path):
        mod = _import_mod(flag_on=True)
        # Write lineup but NO quarter_box file.
        _write_lineup_json(tmp_path, _HOME, "2024-25", _HOME_PIDS,
                           net_rtg=10.0)
        mod._LINEUP_INDEX_CACHE.clear()

        snap = _make_snap(period=2, clock="12:00", game_id="0022400001")
        rows = _make_rows(player_ids=_HOME_PIDS, stats=("pts",),
                          projected_final=20.0)
        rows_before = copy.deepcopy(rows)

        result = _run_with_flag(mod, True, lambda: mod.apply_onoff_tilt(
            snap, rows, quarter_box_dir=tmp_path, lineup_dir=tmp_path,
        ))
        assert result == rows_before

    def test_fewer_than_5_starters(self, tmp_path):
        """Quarter box with only 4 starters for a team → no tilt for that team."""
        mod = _import_mod(flag_on=True)
        only4 = _HOME_PIDS[:4]  # 4 players — incomplete
        _write_quarter_box(tmp_path, "0022400001", 2, only4, _AWAY_PIDS)
        _write_lineup_json(tmp_path, _HOME, "2024-25", _HOME_PIDS,
                           net_rtg=10.0)
        _write_lineup_json(tmp_path, _AWAY, "2024-25", _AWAY_PIDS,
                           net_rtg=10.0, avg_net_rtg=0.0)
        mod._LINEUP_INDEX_CACHE.clear()

        snap = _make_snap(period=2, clock="12:00", game_id="0022400001")
        rows = _make_rows(player_ids=_HOME_PIDS, stats=("pts",),
                          projected_final=20.0)
        rows_before = copy.deepcopy(rows)

        result = _run_with_flag(mod, True, lambda: mod.apply_onoff_tilt(
            snap, rows, quarter_box_dir=tmp_path, lineup_dir=tmp_path,
        ))
        # HOME rows should be untouched (only 4 starters in box)
        home_rows = [r for r in result if r["player_id"] in _HOME_PIDS]
        for r, orig in zip(home_rows, [r for r in rows_before if r["player_id"] in _HOME_PIDS]):
            assert r["projected_final"] == pytest.approx(orig["projected_final"])

    def test_mid_period_snap_no_tilt(self, tmp_path):
        """Snapshot mid-quarter (clock=6:30) → no tilt applied."""
        mod = _import_mod(flag_on=True)
        _write_quarter_box(tmp_path, "0022400001", 2, _HOME_PIDS, _AWAY_PIDS)
        _write_lineup_json(tmp_path, _HOME, "2024-25", _HOME_PIDS,
                           net_rtg=20.0, avg_net_rtg=0.0)
        _write_lineup_json(tmp_path, _AWAY, "2024-25", _AWAY_PIDS,
                           net_rtg=0.0, avg_net_rtg=0.0)
        mod._LINEUP_INDEX_CACHE.clear()

        snap = _make_snap(period=2, clock="06:30", game_id="0022400001")
        rows = _make_rows(player_ids=_HOME_PIDS, stats=("pts",),
                          projected_final=20.0)
        rows_before = copy.deepcopy(rows)

        result = _run_with_flag(mod, True, lambda: mod.apply_onoff_tilt(
            snap, rows, quarter_box_dir=tmp_path, lineup_dir=tmp_path,
        ))
        assert result == rows_before

    def test_missing_game_id_no_tilt(self):
        """Snapshot without game_id → no-op, no exception."""
        mod = _import_mod(flag_on=True)
        snap = _make_snap()
        snap.pop("game_id")
        rows = _make_rows(player_ids=_HOME_PIDS, stats=("pts",),
                          projected_final=20.0)
        rows_before = copy.deepcopy(rows)
        result = _run_with_flag(mod, True, lambda: mod.apply_onoff_tilt(snap, rows))
        assert result == rows_before
