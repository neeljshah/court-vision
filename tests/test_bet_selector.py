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
