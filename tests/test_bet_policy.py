"""Tests for src/prediction/bet_policy.py — flag-gated stat allowlist."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.prediction import bet_policy


@pytest.fixture(autouse=True)
def _clean_env():
    """Ensure CV_BET_POLICY does not leak between tests."""
    saved = os.environ.pop("CV_BET_POLICY", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["CV_BET_POLICY"] = saved


class TestActivePolicy:
    def test_default_is_iter57(self):
        assert bet_policy.active_policy() == "iter57"
        assert bet_policy.is_iter57_default() is True

    def test_unknown_value_falls_back_to_default(self):
        os.environ["CV_BET_POLICY"] = "garbage_xyz"
        assert bet_policy.active_policy() == "iter57"

    def test_reb_ast_recognized(self):
        os.environ["CV_BET_POLICY"] = "reb_ast"
        assert bet_policy.active_policy() == "reb_ast"
        assert bet_policy.is_iter57_default() is False

    def test_reb_ast_fg3m_recognized(self):
        os.environ["CV_BET_POLICY"] = "reb_ast_fg3m"
        assert bet_policy.active_policy() == "reb_ast_fg3m"


class TestPolicyAllowsStat:
    def test_default_allows_every_stat(self):
        for s in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            assert bet_policy.policy_allows_stat(s)

    def test_reb_ast_excludes_pts_and_fg3m(self):
        os.environ["CV_BET_POLICY"] = "reb_ast"
        assert bet_policy.policy_allows_stat("reb") is True
        assert bet_policy.policy_allows_stat("ast") is True
        assert bet_policy.policy_allows_stat("pts") is False
        assert bet_policy.policy_allows_stat("fg3m") is False
        assert bet_policy.policy_allows_stat("stl") is False
        assert bet_policy.policy_allows_stat("blk") is False
        assert bet_policy.policy_allows_stat("tov") is False

    def test_reb_ast_fg3m_keeps_fg3m_drops_pts(self):
        os.environ["CV_BET_POLICY"] = "reb_ast_fg3m"
        assert bet_policy.policy_allows_stat("reb") is True
        assert bet_policy.policy_allows_stat("ast") is True
        assert bet_policy.policy_allows_stat("fg3m") is True
        assert bet_policy.policy_allows_stat("pts") is False

    def test_case_insensitive(self):
        os.environ["CV_BET_POLICY"] = "reb_ast"
        assert bet_policy.policy_allows_stat("REB") is True
        assert bet_policy.policy_allows_stat("PTS") is False

    def test_none_stat_passes_through(self):
        os.environ["CV_BET_POLICY"] = "reb_ast"
        # None means "no stat info" — never block on degraded input
        assert bet_policy.policy_allows_stat(None) is True


class TestAllowedStats:
    def test_default_returns_empty_iterable(self):
        # iter57 has no allowlist — everything is allowed
        assert tuple(bet_policy.allowed_stats()) == ()

    def test_reb_ast_returns_two_stats(self):
        os.environ["CV_BET_POLICY"] = "reb_ast"
        assert set(bet_policy.allowed_stats()) == {"reb", "ast"}

    def test_ast_high_returns_only_ast(self):
        os.environ["CV_BET_POLICY"] = "ast_high"
        assert set(bet_policy.allowed_stats()) == {"ast"}


class TestPolicyMinEdge:
    def test_default_returns_zero(self):
        for s in ("pts", "reb", "ast", "fg3m"):
            assert bet_policy.policy_min_edge(s) == 0.0

    def test_reb_ast_no_per_stat_override(self):
        os.environ["CV_BET_POLICY"] = "reb_ast"
        for s in ("ast", "reb"):
            assert bet_policy.policy_min_edge(s) == 0.0

    def test_ast_high_returns_075_for_ast(self):
        os.environ["CV_BET_POLICY"] = "ast_high"
        assert bet_policy.policy_min_edge("ast") == 0.75
        assert bet_policy.policy_min_edge("AST") == 0.75  # case-insensitive
        # other stats stay at zero (they're not allowed anyway, but the API
        # contract is "only tighten what we override")
        assert bet_policy.policy_min_edge("reb") == 0.0

    def test_none_stat_passes_through(self):
        os.environ["CV_BET_POLICY"] = "ast_high"
        assert bet_policy.policy_min_edge(None) == 0.0


class TestPolicyMaxLine:
    def test_default_returns_none(self):
        for s in ("pts", "reb", "ast", "fg3m"):
            assert bet_policy.policy_max_line(s) is None

    def test_ast_high_caps_at_75(self):
        os.environ["CV_BET_POLICY"] = "ast_high"
        assert bet_policy.policy_max_line("ast") == 7.5

    def test_ast_high_no_cap_for_other_stats(self):
        os.environ["CV_BET_POLICY"] = "ast_high"
        # PTS isn't allowed anyway, but the cap-API is independent of allowlist
        assert bet_policy.policy_max_line("pts") is None


class TestPolicyDropsLine:
    def test_default_keeps_everything(self):
        for line in (1.5, 7.5, 10.5, 30.5):
            assert bet_policy.policy_drops_line("ast", line) is False

    def test_ast_high_drops_above_cap(self):
        os.environ["CV_BET_POLICY"] = "ast_high"
        assert bet_policy.policy_drops_line("ast", 5.5) is False
        assert bet_policy.policy_drops_line("ast", 7.5) is False  # cap is inclusive
        assert bet_policy.policy_drops_line("ast", 7.6) is True
        assert bet_policy.policy_drops_line("ast", 9.5) is True

    def test_ast_high_does_not_drop_unrelated_stat(self):
        os.environ["CV_BET_POLICY"] = "ast_high"
        # PTS line of 30 is well above 7.5 but PTS has no cap -> not dropped
        assert bet_policy.policy_drops_line("pts", 30.5) is False

    def test_garbage_line_does_not_raise(self):
        os.environ["CV_BET_POLICY"] = "ast_high"
        assert bet_policy.policy_drops_line("ast", "not a number") is False
        assert bet_policy.policy_drops_line("ast", None) is False


class TestSelectorIntegration:
    """Confirm bet_selector skips PTS candidates when CV_BET_POLICY=reb_ast."""

    SAMPLE_EDGES = [
        {"player": "LeBron James", "stat": "pts", "projection": 26.5,
         "book_line": 24.5, "edge": 2.0, "kelly": 0.02,
         "confidence": "high", "team": "LAL", "opp_team": "BOS",
         "game_id": "g1"},
        {"player": "Jaylen Brown", "stat": "ast", "projection": 5.5,
         "book_line": 3.5, "edge": 2.0, "kelly": 0.02,
         "confidence": "high", "team": "BOS", "opp_team": "LAL",
         "game_id": "g1"},
    ]

    def _make_cfg(self, tmp_path):
        cfg = tmp_path / "betting.yaml"
        cfg.write_text(
            "bankroll: 1000.0\nkelly_fraction: 0.25\nmax_bet_pct: 0.04\n"
            "edge_min: 0.04\nmax_bets_per_game: 5\nmax_combined_pct: 0.06\n"
            "default_odds: -110\ndry_run: false\n"
        )
        return str(cfg)

    def test_default_iter57_keeps_pts(self, tmp_path):
        cfg_path = self._make_cfg(tmp_path)
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)
        with patch("src.prediction.bet_selector._CONFIG_PATH", cfg_path), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH",
                   str(tmp_path / "bet_log.json")):
            from src.prediction.bet_selector import select
            bets = select(self.SAMPLE_EDGES, "2026-04-23", dry_run=False)
        stats = {b["stat"] for b in bets}
        assert "pts" in stats, "default iter57 must keep PTS bets"

    def test_reb_ast_drops_pts(self, tmp_path):
        os.environ["CV_BET_POLICY"] = "reb_ast"
        cfg_path = self._make_cfg(tmp_path)
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)
        with patch("src.prediction.bet_selector._CONFIG_PATH", cfg_path), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH",
                   str(tmp_path / "bet_log.json")):
            from src.prediction.bet_selector import select
            bets = select(self.SAMPLE_EDGES, "2026-04-23", dry_run=False)
        stats = {b["stat"] for b in bets}
        assert "pts" not in stats, "reb_ast must skip PTS"


class TestPolicyAllowsContext:
    """IN-2: playoff-AST regime guard (VS_VEGAS_ASSESSMENT §8e)."""

    def test_ast_playoff_blocked_by_default(self):
        from src.prediction.bet_policy import policy_allows_context
        assert policy_allows_context("ast", "0042500317") is False
        assert policy_allows_context("AST", "0042500317") is False

    def test_ast_regular_season_allowed(self):
        from src.prediction.bet_policy import policy_allows_context
        assert policy_allows_context("ast", "0022400123") is True

    def test_non_ast_playoff_allowed(self):
        from src.prediction.bet_policy import policy_allows_context
        assert policy_allows_context("pts", "0042500317") is True
        assert policy_allows_context("reb", "0042500317") is True

    def test_escape_hatch(self):
        from src.prediction.bet_policy import policy_allows_context
        os.environ["CV_ALLOW_PLAYOFF_AST"] = "1"
        try:
            assert policy_allows_context("ast", "0042500317") is True
        finally:
            os.environ.pop("CV_ALLOW_PLAYOFF_AST", None)

    def test_none_inputs_allowed(self):
        from src.prediction.bet_policy import policy_allows_context
        assert policy_allows_context("ast", None) is True
        assert policy_allows_context(None, "0042500317") is True


class TestAstHighSelectorKnobs:
    """IN-1/IN-2: ast_high edge-floor (0.75) + line-cap (7.5) + playoff guard
    enforced in live bet_selector (was harness-only)."""

    def _cfg(self, tmp_path):
        cfg = tmp_path / "betting.yaml"
        cfg.write_text(
            "bankroll: 1000.0\nkelly_fraction: 0.25\nmax_bet_pct: 0.04\n"
            "edge_min: 0.04\nmax_bets_per_game: 5\nmax_combined_pct: 0.06\n"
            "default_odds: -110\ndry_run: false\n")
        return str(cfg)

    def _run(self, rows, tmp_path):
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)
        with patch("src.prediction.bet_selector._CONFIG_PATH", self._cfg(tmp_path)), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH", str(tmp_path / "bl.json")):
            from src.prediction.bet_selector import select
            return select(rows, "2026-04-23", dry_run=False)

    def _ast_row(self, edge, line, game_id="0022400999"):
        return {"player": "Trae Young", "stat": "ast", "projection": line + edge,
                "book_line": line, "edge": edge, "kelly": 0.02, "confidence": "high",
                "team": "ATL", "opp_team": "BOS", "game_id": game_id}

    def test_ast_high_drops_low_edge(self, tmp_path):
        os.environ["CV_BET_POLICY"] = "ast_high"
        rows = [self._ast_row(0.5, 5.5), self._ast_row(1.2, 5.5)]
        bets = self._run(rows, tmp_path)
        edges = sorted(round(abs(b["edge"]), 2) for b in bets)
        assert all(e >= 0.75 for e in edges), f"ast_high must drop edge<0.75; got {edges}"
        assert 1.2 in edges, "ast_high must keep edge>=0.75"

    def test_ast_high_drops_high_line(self, tmp_path):
        os.environ["CV_BET_POLICY"] = "ast_high"
        rows = [self._ast_row(1.5, 9.5), self._ast_row(1.5, 5.5)]
        bets = self._run(rows, tmp_path)
        lines = {b.get("book_line") for b in bets}
        assert 9.5 not in lines, "ast_high must drop line>7.5"
        assert 5.5 in lines, "ast_high must keep line<=7.5"

    def test_iter57_default_keeps_all_ast(self, tmp_path):
        # default policy = no floor/cap; the low-edge/high-line AST survive
        rows = [self._ast_row(0.5, 9.5)]
        bets = self._run(rows, tmp_path)
        assert any(b["stat"] == "ast" for b in bets), "iter57 must not apply ast_high knobs"

    def test_playoff_ast_skipped(self, tmp_path):
        # default iter57 + playoff game -> AST skipped by the regime guard
        rows = [self._ast_row(2.0, 5.5, game_id="0042500317")]
        bets = self._run(rows, tmp_path)
        assert not any(b["stat"] == "ast" for b in bets), "playoff AST must be skipped by default"


class TestKellyTilt:
    """H1 flag-gated Kelly sizing tilt (CV_KELLY_TILT). Default OFF = no-op."""

    @pytest.fixture(autouse=True)
    def _clean_tilt_env(self):
        saved = os.environ.pop("CV_KELLY_TILT", None)
        try:
            yield
        finally:
            os.environ.pop("CV_KELLY_TILT", None)
            if saved is not None:
                os.environ["CV_KELLY_TILT"] = saved

    def test_disabled_by_default_is_noop(self):
        assert bet_policy.kelly_tilt_enabled() is False
        # every stat / pace combination returns 1.0 when flag is off
        assert bet_policy.policy_kelly_tilt("ast", 110.0) == 1.0
        assert bet_policy.policy_kelly_tilt("ast", 95.0) == 1.0
        assert bet_policy.policy_kelly_tilt("reb", 110.0) == 1.0
        assert bet_policy.policy_kelly_tilt(None, None) == 1.0

    def test_high_pace_ast_tilts_up_when_enabled(self):
        os.environ["CV_KELLY_TILT"] = "1"
        assert bet_policy.kelly_tilt_enabled() is True
        # high pace AST -> tilt up
        assert bet_policy.policy_kelly_tilt("ast", 110.0) == pytest.approx(1.25)
        # low pace AST -> no tilt (low+mid is still a winner, never down-tilt)
        assert bet_policy.policy_kelly_tilt("ast", 95.0) == 1.0
        # right at threshold -> no tilt (strictly greater)
        assert bet_policy.policy_kelly_tilt("ast", 101.9) == 1.0
        # non-AST stat -> no tilt even at high pace
        assert bet_policy.policy_kelly_tilt("reb", 110.0) == 1.0
        assert bet_policy.policy_kelly_tilt("pts", 110.0) == 1.0

    def test_missing_pace_is_noop_even_when_enabled(self):
        os.environ["CV_KELLY_TILT"] = "1"
        assert bet_policy.policy_kelly_tilt("ast", None) == 1.0
        assert bet_policy.policy_kelly_tilt("ast", "garbage") == 1.0

    def test_result_is_clamped(self):
        os.environ["CV_KELLY_TILT"] = "true"
        v = bet_policy.policy_kelly_tilt("ast", 110.0)
        assert 1.0 <= v <= 1.5
