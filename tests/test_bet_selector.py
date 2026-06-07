"""Tests for src/prediction/bet_selector.py (Phase 15)."""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_EDGES = [
    {"player": "LeBron James",  "stat": "pts", "projection": 26.5, "book_line": 24.5,
     "edge": 2.0,  "kelly": 0.02, "confidence": "high",   "team": "LAL", "opp_team": "BOS", "game_id": "001"},
    {"player": "LeBron James",  "stat": "reb", "projection": 8.2,  "book_line": 7.5,
     "edge": 0.7,  "kelly": 0.01, "confidence": "medium", "team": "LAL", "opp_team": "BOS", "game_id": "001"},
    {"player": "Jayson Tatum",  "stat": "pts", "projection": 28.0, "book_line": 27.0,
     "edge": 1.0,  "kelly": 0.015,"confidence": "medium", "team": "BOS", "opp_team": "LAL", "game_id": "001"},
    {"player": "Jaylen Brown",  "stat": "ast", "projection": 3.5,  "book_line": 3.0,
     "edge": 0.5,  "kelly": 0.008,"confidence": "low",    "team": "BOS", "opp_team": "LAL", "game_id": "001"},
    # Edge below threshold (0.04 = 4%, raw edge 0.1 on line 10 = 1% → filtered)
    {"player": "Anthony Davis", "stat": "blk", "projection": 2.1,  "book_line": 2.0,
     "edge": 0.1,  "kelly": 0.001,"confidence": "low",    "team": "LAL", "opp_team": "BOS", "game_id": "001"},
]


def _make_selector(tmp_path, extra_cfg=""):
    """Write a minimal betting.yaml into tmp_path and patch _CONFIG_PATH."""
    cfg = tmp_path / "betting.yaml"
    cfg.write_text(
        "bankroll: 1000.0\n"
        "kelly_fraction: 0.25\n"
        "max_bet_pct: 0.04\n"
        "edge_min: 0.04\n"
        "max_bets_per_game: 3\n"
        "max_combined_pct: 0.06\n"
        "default_odds: -110\n"
        "dry_run: false\n"
        + extra_cfg
    )
    return str(cfg)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBetSelector:
    def test_import(self):
        from src.prediction import bet_selector  # noqa: F401

    def test_select_returns_list(self, tmp_path):
        cfg_path = _make_selector(tmp_path)
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)

        with patch("src.prediction.bet_selector._CONFIG_PATH", cfg_path), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH", str(tmp_path / "bet_log.json")):
            from src.prediction.bet_selector import select
            bets = select(SAMPLE_EDGES, "2026-04-23", dry_run=False)

        assert isinstance(bets, list)

    def test_edge_filter(self, tmp_path):
        """Anthony Davis blk (edge 0.1 on line 2.0 = 5%) should pass threshold;
        the game cap of 3 is the binding constraint here."""
        cfg_path = _make_selector(tmp_path)
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)

        with patch("src.prediction.bet_selector._CONFIG_PATH", cfg_path), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH", str(tmp_path / "bet_log.json")):
            from src.prediction.bet_selector import select
            bets = select(SAMPLE_EDGES, "2026-04-23", dry_run=False)

        # max_bets_per_game=3 → at most 3 bets from a single game_id
        game_ids = [b["game_id"] for b in bets]
        for gid in set(game_ids):
            assert game_ids.count(gid) <= 3

    def test_max_bets_per_game(self, tmp_path):
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)
        cfg = {"bankroll": 1000.0, "edge_min": 0.04, "max_bets_per_game": 1,
               "max_combined_pct": 0.06, "default_odds": -110, "dry_run": False}

        with patch("src.prediction.bet_selector._load_config", return_value=cfg), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH", str(tmp_path / "bet_log.json")):
            from src.prediction.bet_selector import select
            bets = select(SAMPLE_EDGES, "2026-04-23", dry_run=False)

        game_counts: dict = {}
        for b in bets:
            game_counts[b["game_id"]] = game_counts.get(b["game_id"], 0) + 1
        for cnt in game_counts.values():
            assert cnt <= 1

    def test_dry_run_status(self, tmp_path):
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)
        cfg = {"bankroll": 1000.0, "edge_min": 0.04, "max_bets_per_game": 3,
               "max_combined_pct": 0.06, "default_odds": -110, "dry_run": False}

        with patch("src.prediction.bet_selector._load_config", return_value=cfg), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH", str(tmp_path / "bet_log.json")):
            from src.prediction.bet_selector import select
            bets = select(SAMPLE_EDGES, "2026-04-23", dry_run=True)

        assert all(b["status"] == "paper" for b in bets)

    def test_output_file_written(self, tmp_path):
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)
        cfg = {"bankroll": 1000.0, "edge_min": 0.04, "max_bets_per_game": 3,
               "max_combined_pct": 0.06, "default_odds": -110, "dry_run": False}

        with patch("src.prediction.bet_selector._load_config", return_value=cfg), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH", str(tmp_path / "bet_log.json")):
            from src.prediction.bet_selector import select
            select(SAMPLE_EDGES, "2026-04-23", dry_run=False)

        out_file = os.path.join(out_dir, "bets_20260423.json")
        assert os.path.exists(out_file)
        with open(out_file) as f:
            payload = json.load(f)
        assert "bets" in payload
        assert isinstance(payload["bets"], list)

    def test_stake_positive(self, tmp_path):
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)
        cfg = {"bankroll": 1000.0, "edge_min": 0.04, "max_bets_per_game": 3,
               "max_combined_pct": 0.06, "default_odds": -110, "dry_run": False}

        with patch("src.prediction.bet_selector._load_config", return_value=cfg), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH", str(tmp_path / "bet_log.json")):
            from src.prediction.bet_selector import select
            bets = select(SAMPLE_EDGES, "2026-04-23", dry_run=False)

        assert all(b["stake"] > 0 for b in bets)

    def test_direction_over_under(self, tmp_path):
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)
        cfg = {"bankroll": 1000.0, "edge_min": 0.04, "max_bets_per_game": 3,
               "max_combined_pct": 0.06, "default_odds": -110, "dry_run": False}
        under_edges = [
            {"player": "Player A", "stat": "pts", "projection": 20.0, "book_line": 22.0,
             "edge": -2.0, "kelly": 0.02, "confidence": "high", "team": "X", "opp_team": "Y", "game_id": "002"},
        ]
        with patch("src.prediction.bet_selector._load_config", return_value=cfg), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH", str(tmp_path / "bet_log.json")):
            from src.prediction.bet_selector import select
            bets = select(under_edges, "2026-04-23", dry_run=False)

        assert len(bets) == 1
        assert bets[0]["direction"] == "under"


# ---------------------------------------------------------------------------
# CV_AST_DURABLE_KELLY tests — FIX 1 (AST_KELLY_ALTLINE_FIXES)
# ---------------------------------------------------------------------------

class TestASTDurableKelly:
    """Verify CV_AST_DURABLE_KELLY gating — default OFF is byte-identical;
    flag ON sizes AST on durable 55%-win quarter-Kelly capped at 2%."""

    # AST edge row that clears the 0.75 threshold at line=4.5
    _AST_EDGE = {
        "player": "Test Player",
        "stat": "ast",
        "projection": 5.5,
        "book_line": 4.5,
        "edge": 1.0,         # edge=1.0 / line=4.5 → edge_frac≈22% → win_prob≈74% → 4% cap
        "confidence": "high",
        "team": "OKC",
        "opp_team": "NYK",
        "game_id": "002",
        "odds": -110,
    }
    # Non-AST edge row to confirm non-AST stats are unchanged
    _REB_EDGE = {
        "player": "Test Player",
        "stat": "reb",
        "projection": 9.5,
        "book_line": 8.0,
        "edge": 1.5,
        "confidence": "high",
        "team": "OKC",
        "opp_team": "NYK",
        "game_id": "003",
        "odds": -110,
    }

    def _run_select(self, tmp_path, edges, env_override=None):
        import os
        from unittest.mock import patch
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)
        cfg = {
            "bankroll": 1000.0, "edge_min": 0.04, "max_bets_per_game": 3,
            "max_combined_pct": 0.06, "default_odds": -110, "dry_run": False,
        }
        env = {**os.environ, **(env_override or {})}
        with patch("src.prediction.bet_selector._load_config", return_value=cfg), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH", str(tmp_path / "bet_log.json")), \
             patch.dict("os.environ", env_override or {}, clear=False):
            from src.prediction.bet_selector import select
            return select(edges, "2026-06-04", dry_run=False)

    def test_flag_off_byte_identical_stake(self, tmp_path):
        """Flag OFF: AST stake equals the existing behavior (capped at 4% = $40)."""
        bets_off = self._run_select(
            tmp_path, [self._AST_EDGE],
            env_override={"CV_AST_DURABLE_KELLY": "0"},
        )
        assert len(bets_off) == 1
        # At edge_frac≈22%, win_prob≈74%, full_kelly≈46%, qk≈11.67% → hits 4% cap = $40
        assert bets_off[0]["stat"] == "ast"
        assert abs(bets_off[0]["stake"] - 40.0) < 1.0, (
            f"Flag-OFF AST stake should be ~$40 (4% cap), got {bets_off[0]['stake']}"
        )

    def test_flag_on_ast_stake_quarter_kelly_55pct(self, tmp_path):
        """Flag ON: AST stake uses durable 55% win-prob, quarter-Kelly, capped 2% = $13.75."""
        bets_on = self._run_select(
            tmp_path, [self._AST_EDGE],
            env_override={"CV_AST_DURABLE_KELLY": "1"},
        )
        assert len(bets_on) == 1
        assert bets_on[0]["stat"] == "ast"
        # full_kelly(0.55, -110)=5.5%, quarter=1.375%, cap=2% → stake=$13.75
        # Allow $0.50 float tolerance
        assert abs(bets_on[0]["stake"] - 13.75) < 0.51, (
            f"Flag-ON AST stake should be ~$13.75 (qK on 55%), got {bets_on[0]['stake']}"
        )
        # Must not exceed 2% cap ($20)
        assert bets_on[0]["stake"] <= 20.01, (
            f"Flag-ON AST stake must be <= $20 (2% cap), got {bets_on[0]['stake']}"
        )

    def test_flag_on_same_bets_selected(self, tmp_path, tmp_path_factory):
        """Flag ON selects the SAME bets as flag OFF — only stake changes, not selection.
        ROI% is therefore unchanged (same numerator bets pass, different denominator $)."""
        tmp_off = tmp_path_factory.mktemp("off")
        tmp_on = tmp_path_factory.mktemp("on")
        bets_off = self._run_select(
            tmp_off, [self._AST_EDGE],
            env_override={"CV_AST_DURABLE_KELLY": "0"},
        )
        bets_on = self._run_select(
            tmp_on, [self._AST_EDGE],
            env_override={"CV_AST_DURABLE_KELLY": "1"},
        )
        assert len(bets_off) == len(bets_on), (
            f"Same bets must be selected: OFF={len(bets_off)}, ON={len(bets_on)}"
        )
        for b_off, b_on in zip(bets_off, bets_on):
            assert b_off["player"] == b_on["player"]
            assert b_off["stat"] == b_on["stat"]
            assert b_off["direction"] == b_on["direction"]
            assert b_off["edge"] == b_on["edge"]

    def test_non_ast_stake_unchanged_by_flag(self, tmp_path, tmp_path_factory):
        """Non-AST stats (REB) must have identical stakes whether flag is ON or OFF."""
        tmp_off = tmp_path_factory.mktemp("reb_off")
        tmp_on = tmp_path_factory.mktemp("reb_on")
        bets_off = self._run_select(
            tmp_off, [self._REB_EDGE],
            env_override={"CV_AST_DURABLE_KELLY": "0"},
        )
        bets_on = self._run_select(
            tmp_on, [self._REB_EDGE],
            env_override={"CV_AST_DURABLE_KELLY": "1"},
        )
        assert len(bets_off) == len(bets_on)
        for b_off, b_on in zip(bets_off, bets_on):
            assert b_off["stat"] == "reb"
            assert b_off["stake"] == b_on["stake"], (
                f"REB stake must be identical flag ON/OFF: {b_off['stake']} vs {b_on['stake']}"
            )


# ---------------------------------------------------------------------------
# Phase 15.5 — CI field tests (xfail until Plan 03 wires conformal into select())
# ---------------------------------------------------------------------------

class TestBetSelectorCI:
    """Verifies conformal CI fields and alt-line schema in bet_selector output."""

    @pytest.mark.xfail(reason="CI fields not yet wired into select() — Plan 03", strict=False)
    def test_bet_selector_ci_fields(self, tmp_path):
        """Each bet returned by select() must have ci_lo_80 and ci_hi_80 keys."""
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)
        cfg = {
            "bankroll": 1000.0, "edge_min": 0.04, "max_bets_per_game": 3,
            "max_combined_pct": 0.06, "default_odds": -110, "dry_run": False,
        }
        with patch("src.prediction.bet_selector._load_config", return_value=cfg), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH", str(tmp_path / "bet_log.json")):
            from src.prediction.bet_selector import select
            bets = select(SAMPLE_EDGES, "2026-04-23", dry_run=False)

        assert len(bets) > 0, "Need at least one bet to check CI fields"
        for bet in bets:
            assert "ci_lo_80" in bet, f"Missing ci_lo_80 in bet for {bet.get('player')}"
            assert "ci_hi_80" in bet, f"Missing ci_hi_80 in bet for {bet.get('player')}"

    @pytest.mark.xfail(reason="alt_line schema not yet wired into select() — Plan 03", strict=False)
    def test_alt_bets_json_schema(self, tmp_path):
        """bets JSON must include alt_line and alt_line_ev keys in output file."""
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)
        # Inject alt_line fields into edge rows to simulate ladder output
        alt_edges = [
            {**SAMPLE_EDGES[0], "alt_line": 25.5, "alt_line_ev": 0.062},
        ]
        cfg = {
            "bankroll": 1000.0, "edge_min": 0.04, "max_bets_per_game": 3,
            "max_combined_pct": 0.06, "default_odds": -110, "dry_run": False,
        }
        with patch("src.prediction.bet_selector._load_config", return_value=cfg), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH", str(tmp_path / "bet_log.json")):
            from src.prediction.bet_selector import select
            bets = select(alt_edges, "2026-04-23", dry_run=False)

        assert len(bets) > 0
        # When input has alt_line, output must preserve it
        for bet in bets:
            assert "alt_line" in bet, "alt_line key missing from bet schema"
            assert "alt_line_ev" in bet, "alt_line_ev key missing from bet schema"
