"""Per-file integration tests for scripts.platformkit.prop_edge_nba board + calibration.

Covers: build_nba_prop_board (P0-3 criteria 5-10) and calibration cache round-trip.
Unit tests (name index, stat canon, edge_for_line_nba): test_prop_edge_nba.py

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_edge_nba_board.py -q
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.odds_provider.prop_base import PropLine
from scripts.platformkit.prop_edge_nba import build_nba_prop_board
from scripts.platformkit.test_prop_edge_nba import make_df, make_line, noop_ev


# ---------------------------------------------------------------------------
# Integration: build_nba_prop_board
# ---------------------------------------------------------------------------

class TestBuildNbaPropBoard:
    def setup_method(self):
        self.df = make_df()
        self.as_of = "2025-06-01"

    def test_empty_lines_returns_ok(self):
        board = build_nba_prop_board(
            [], self.df, self.as_of,
            calibration_path="/nonexistent/cal.json",
            apply_ev_fn=noop_ev)
        assert board["status"] == "ok"
        assert board["edges"] == []
        assert board["unresolved"] == []

    def test_none_df_returns_no_data(self):
        board = build_nba_prop_board(
            [make_line()], None, self.as_of,
            calibration_path=None,
            apply_ev_fn=noop_ev)
        assert board["status"] == "no_data"

    def test_valid_line_lands_in_edges(self):
        line = make_line("LeBron James", "Points", 25.5)
        board = build_nba_prop_board(
            [line], self.df, self.as_of,
            calibration_path="/nonexistent/cal.json",
            apply_ev_fn=noop_ev)
        assert board["status"] == "ok"
        assert len(board["edges"]) == 1
        assert len(board["unresolved"]) == 0

    def test_each_edge_row_has_required_fields(self):
        lines = [make_line("LeBron James", "Points", 25.5),
                 make_line("Stephen Curry", "Assists", 7.5)]
        board = build_nba_prop_board(
            lines, self.df, self.as_of,
            calibration_path="/nonexistent/cal.json",
            apply_ev_fn=noop_ev)
        required_fields = {"model_p_over", "calibration", "tier"}
        for e in board["edges"]:
            for f in required_fields:
                assert f in e, (
                    f"Edge row missing required field '{f}': {list(e.keys())}")

    def test_model_p_over_in_unit_range(self):
        lines = [make_line("LeBron James", stat, 5.0)
                 for stat in ["Points", "Rebounds", "Assists"]]
        board = build_nba_prop_board(
            lines, self.df, self.as_of,
            calibration_path="/nonexistent/cal.json",
            apply_ev_fn=noop_ev)
        for e in board["edges"]:
            assert 0.0 <= e["model_p_over"] <= 1.0, (
                f"model_p_over out of range for {e['stat']}: {e['model_p_over']}")

    def test_unresolved_player_lands_in_unresolved(self):
        lines = [
            make_line("LeBron James", "Points", 25.5),
            make_line("Nobody Real", "Points", 10.0),
        ]
        board = build_nba_prop_board(
            lines, self.df, self.as_of,
            calibration_path="/nonexistent/cal.json",
            apply_ev_fn=noop_ev)
        assert len(board["edges"]) == 1
        assert len(board["unresolved"]) == 1
        assert board["unresolved_count"] == 1
        assert board["unresolved"][0]["reason"] == "player_not_found"

    def test_unsupported_stat_lands_in_unresolved(self):
        lines = [make_line("LeBron James", "Fantasy Score", 45.0)]
        board = build_nba_prop_board(
            lines, self.df, self.as_of,
            calibration_path="/nonexistent/cal.json",
            apply_ev_fn=noop_ev)
        assert len(board["edges"]) == 0
        assert len(board["unresolved"]) == 1
        assert board["unresolved"][0]["reason"] == "stat_unsupported"

    def test_calibration_label_is_one_of_expected(self):
        lines = [make_line("LeBron James", "Points", 25.5)]
        board = build_nba_prop_board(
            lines, self.df, self.as_of,
            calibration_path="/nonexistent/cal.json",
            apply_ev_fn=noop_ev)
        valid_labels = {"proven", "marginal", "weak", "unmeasured"}
        for e in board["edges"]:
            assert e.get("calibration") in valid_labels, (
                f"Unexpected calibration label: {e.get('calibration')!r}")

    def test_tier_is_model_view_when_no_cache(self):
        """Absent calibration cache -> all edges get tier MODEL_VIEW."""
        lines = [make_line("LeBron James", "Points", 25.5)]
        board = build_nba_prop_board(
            lines, self.df, self.as_of,
            calibration_path="/nonexistent/path.json",
            apply_ev_fn=noop_ev)
        for e in board["edges"]:
            assert e["tier"] == "MODEL_VIEW"

    def test_board_has_honest_note(self):
        board = build_nba_prop_board(
            [], self.df, self.as_of,
            apply_ev_fn=noop_ev)
        assert isinstance(board.get("honest_note"), str)
        assert len(board["honest_note"]) > 0

    def test_no_dollar_keys_in_board_or_edges(self):
        lines = [make_line("LeBron James", "Points", 25.5)]
        board = build_nba_prop_board(
            lines, self.df, self.as_of,
            calibration_path="/nonexistent/cal.json",
            apply_ev_fn=noop_ev)

        def _all_keys(obj):
            keys = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    keys.append(str(k).lower())
                    keys.extend(_all_keys(v))
            elif isinstance(obj, list):
                for v in obj:
                    keys.extend(_all_keys(v))
            return keys

        banned = {"roi", "pnl", "profit", "edge_dollars", "dollar_return"}
        all_k = set(_all_keys(board))
        for b in banned:
            assert b not in all_k, f"Banned key '{b}' found in board output"

    def test_calibration_labels_dict_has_four_keys(self):
        lines = [make_line("LeBron James", "Points", 25.5)]
        board = build_nba_prop_board(
            lines, self.df, self.as_of,
            calibration_path="/nonexistent/cal.json",
            apply_ev_fn=noop_ev)
        labels = board.get("calibration_labels", {})
        assert isinstance(labels, dict)
        for k in ("proven", "marginal", "weak", "unmeasured"):
            assert k in labels, f"calibration_labels missing key '{k}'"

    def test_never_raises_on_corrupt_df(self):
        """Even with a malformed df, build_nba_prop_board must not raise."""
        import pandas as pd
        bad_df = pd.DataFrame({"x": [1, 2, 3]})
        lines = [make_line("LeBron James", "Points", 25.5)]
        try:
            board = build_nba_prop_board(
                lines, bad_df, self.as_of, apply_ev_fn=noop_ev)
            assert board["status"] in ("ok", "error: KeyError", "error: ValueError",
                                       "error: Exception")
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"build_nba_prop_board raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# Integration: calibration cache round-trip
# ---------------------------------------------------------------------------

class TestCalibrationCacheIntegration:
    def test_proven_stat_gets_calibration_proven_tier(self, tmp_path):
        """Cache marks pts as proven (bss=0.07, n=300); n_games=20 -> reliable=True,
        ev_flag=ok via noop_ev. apply_tier MUST promote to CALIBRATION_PROVEN."""
        cache_path = str(tmp_path / "nba_cal.json")
        payload = {
            "as_of": "2026-01-01T00:00:00+00:00",
            "settle_logic_version": None,
            "mode": "nba_oof_walk_forward",
            "overall": {"bss": 0.06, "brier": 0.22, "ece": 0.02, "n": 300},
            "per_stat": {
                "pts": {"bss": 0.07, "brier": 0.22, "ece": 0.02, "n": 300},
            },
            "note": "test proven tier",
        }
        with open(cache_path, "w", encoding="ascii") as fh:
            json.dump(payload, fh)

        df = make_df(n_games=20)
        lines = [make_line("LeBron James", "Points", 25.5)]
        board = build_nba_prop_board(
            lines, df, "2025-06-01",
            calibration_path=cache_path,
            apply_ev_fn=noop_ev)
        assert board["status"] == "ok"
        assert len(board["edges"]) == 1
        e = board["edges"][0]
        # n_games=20 >= _RELIABLE_N=5 -> reliable must be True
        assert e["reliable"] is True, (
            f"Expected reliable=True with n_games=20, got {e['reliable']!r}")
        # noop_ev sets ev_flag="ok" when conf="ok" (which follows from reliable=True)
        assert e["ev_flag"] == "ok", (
            f"Expected ev_flag='ok', got {e['ev_flag']!r}")
        assert e["calibration"] == "proven", (
            f"Expected calibration='proven', got {e['calibration']!r}")
        # All three conditions met -> tier must be CALIBRATION_PROVEN
        assert e["tier"] == "CALIBRATION_PROVEN", (
            f"Expected CALIBRATION_PROVEN tier, got {e['tier']!r}")

    def test_unmeasured_stat_stays_model_view(self, tmp_path):
        """A stat not in the cache -> calibration=unmeasured, tier=MODEL_VIEW."""
        cache_path = str(tmp_path / "nba_cal_empty.json")
        payload = {
            "as_of": "2026-01-01T00:00:00+00:00",
            "settle_logic_version": None,
            "mode": "nba_oof_walk_forward",
            "overall": {"bss": None, "brier": None, "ece": None, "n": 0},
            "per_stat": {},
            "note": "empty",
        }
        with open(cache_path, "w", encoding="ascii") as fh:
            json.dump(payload, fh)

        df = make_df(n_games=20)
        lines = [make_line("LeBron James", "Points", 25.5)]
        board = build_nba_prop_board(
            lines, df, "2025-06-01",
            calibration_path=cache_path,
            apply_ev_fn=noop_ev)
        assert board["status"] == "ok"
        for e in board["edges"]:
            assert e.get("calibration") == "unmeasured"
            assert e.get("tier") == "MODEL_VIEW"


# ---------------------------------------------------------------------------
# Integration: mixed resolved + unresolved (full acceptance test)
# ---------------------------------------------------------------------------

class TestMixedBoard:
    def test_mixed_lines_routed_correctly(self):
        """Board with known and unknown players routes correctly; nothing dropped."""
        df = make_df()
        lines = [
            make_line("LeBron James", "Points", 25.5),
            make_line("Unknown Nobody", "Points", 10.0),
            make_line("Stephen Curry", "Assists", 7.5),
            make_line("LeBron James", "Fantasy Score", 60.0),
        ]
        board = build_nba_prop_board(
            lines, df, "2025-06-01",
            calibration_path="/nonexistent/cal.json",
            apply_ev_fn=noop_ev)

        assert board["status"] == "ok"
        assert len(board["edges"]) == 2
        assert len(board["unresolved"]) == 2
        assert board["unresolved_count"] == 2

        for e in board["edges"]:
            assert "model_p_over" in e
            assert "calibration" in e
            assert "tier" in e
            assert 0.0 <= e["model_p_over"] <= 1.0

        reasons = {u["reason"] for u in board["unresolved"]}
        assert "player_not_found" in reasons
        assert "stat_unsupported" in reasons
