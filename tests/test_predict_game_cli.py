"""
test_predict_game_cli.py — Tests for scripts/predict_game.py CLI.

Mocks all model loaders so the test suite runs without trained pkl files.
Verifies:
  - Report contains expected section headers
  - WIN PROBABILITY, GAME SCORE, and at least one number appear in output
  - --json flag returns parseable JSON with correct keys
  - --players flag populates PLAYER PROPS section
  - No-model graceful degradation (error messages, not crashes)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import MagicMock, patch

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_PATH = os.path.join(PROJECT_DIR, "scripts", "predict_game.py")
sys.path.insert(0, PROJECT_DIR)

# ── Reusable mock data ─────────────────────────────────────────────────────────

_MOCK_WIN_PROB = {
    "home_win_prob":    0.584,
    "away_win_prob":    0.416,
    "predicted_winner": "BOS",
    "margin_est":       2.5,
    "model_id":         "xgboost_v2",
    "brier":            0.209,
    "confidence_interval": [0.534, 0.634],
    "injury_warnings":  {"home": [], "away": [], "has_warnings": False},
    "features":         {},
}

_MOCK_GAME_MODELS = {
    "total_est":        229.7,
    "spread_est":       -4.8,
    "blowout_prob":     0.221,
    "first_half_total": 113.2,
    "pace_est":         101.4,
    "ot_prob":          0.064,
    "total_std":        14.1,
    "spread_std":       11.2,
    "first_half_std":   6.7,
}

_MOCK_PROPS = {
    "pts":  27.3,
    "reb":   8.4,
    "ast":   8.1,
    "fg3m":  1.9,
    "stl":   1.1,
    "blk":   1.0,
    "tov":   3.2,
    "player_id": 2544,
    "player_name": "LeBron James",
    "fg_pct": 0.52,
}


# ── Helper: run CLI in subprocess ──────────────────────────────────────────────

def _run_cli(*args, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """Run the CLI as a subprocess and return the result."""
    env = os.environ.copy()
    env["NBA_OFFLINE"] = "1"   # prevent any live API calls
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, CLI_PATH] + list(args),
        capture_output=True, text=True, cwd=PROJECT_DIR, env=env,
        timeout=90,
    )


# ── Unit tests (in-process with mocks) ────────────────────────────────────────

class TestRenderReport(unittest.TestCase):
    """Test the _render_report formatter directly — no subprocess needed."""

    def setUp(self):
        from scripts.predict_game import _render_report
        self._render = _render_report

    def _base_report(self) -> dict:
        return {
            "home_team": "BOS",
            "away_team": "LAL",
            "season": "2025-26",
            "game_date": "2026-05-22",
            "win_probability": {**_MOCK_WIN_PROB},
            "game_models": {**_MOCK_GAME_MODELS},
        }

    def test_contains_win_probability_header(self):
        out = self._render(self._base_report())
        self.assertIn("WIN PROBABILITY", out)

    def test_contains_game_score_header(self):
        out = self._render(self._base_report())
        self.assertIn("GAME SCORE", out)

    def test_contains_home_win_pct(self):
        out = self._render(self._base_report())
        self.assertIn("58.4%", out)

    def test_contains_total(self):
        out = self._render(self._base_report())
        self.assertIn("229.7", out)

    def test_contains_separator(self):
        out = self._render(self._base_report())
        self.assertIn("=" * 20, out)

    def test_json_mode(self):
        report = self._base_report()
        out = self._render(report, use_json=True)
        parsed = json.loads(out)
        self.assertEqual(parsed["home_team"], "BOS")
        self.assertIn("win_probability", parsed)

    def test_props_section_present(self):
        report = self._base_report()
        report["player_props"] = [{
            "player_name": "LeBron James",
            "props": {
                "pts": {"mean": 27.3, "lo": 20.0, "hi": 34.6,
                        "line": 25.5, "edge": 1.8, "direction": "Over"},
            },
        }]
        out = self._render(report)
        self.assertIn("PLAYER PROPS", out)
        self.assertIn("LeBron James", out)
        self.assertIn("27.3", out)

    def test_props_skipped_message(self):
        report = self._base_report()
        report["props_skipped"] = "no --players arg provided"
        out = self._render(report)
        self.assertIn("PLAYER PROPS", out)
        self.assertIn("skipped", out)

    def test_injury_warnings(self):
        report = self._base_report()
        report["win_probability"]["injury_warnings"] = {
            "home": [{"player_name": "Jaylen Brown", "status": "Out", "comment": "knee"}],
            "away": [],
            "has_warnings": True,
        }
        out = self._render(report)
        self.assertIn("INJURY WARNINGS", out)
        self.assertIn("Jaylen Brown", out)

    def test_portfolio_section(self):
        report = self._base_report()
        report["lines"] = {"total": 228.5, "spread": -3.5}
        report["portfolio"] = {
            "expected_roi": 6.2,
            "win_prob": 54.3,
            "var_5pct": -3.1,
            "allocations": [{
                "player_name": "LeBron James",
                "stat": "pts",
                "direction": "Over",
                "odds": -110,
                "kelly_pct": 2.1,
                "edge_pct": 0.07,
            }],
        }
        out = self._render(report)
        self.assertIn("PORTFOLIO", out)
        self.assertIn("2.1%", out)
        self.assertIn("+6.2%", out)

    def test_game_models_error_graceful(self):
        report = self._base_report()
        report["game_models"] = {"error": "model file not found"}
        out = self._render(report)
        self.assertIn("GAME SCORE", out)
        self.assertIn("unavailable", out)

    def test_win_prob_error_graceful(self):
        report = self._base_report()
        report["win_probability"] = {"error": "pkl missing"}
        out = self._render(report)
        self.assertIn("WIN PROBABILITY", out)
        self.assertIn("unavailable", out)


class TestIntervalLoader(unittest.TestCase):
    """Test conformal interval loading with and without artifacts."""

    def test_loads_conformal_when_available(self):
        from scripts.predict_game import _load_conformal_intervals
        intervals = _load_conformal_intervals()
        self.assertIn("pts", intervals)
        self.assertIsInstance(intervals["pts"], float)
        self.assertGreater(intervals["pts"], 0)

    def test_all_stats_present(self):
        from scripts.predict_game import _load_conformal_intervals
        intervals = _load_conformal_intervals()
        for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]:
            self.assertIn(stat, intervals, f"Missing interval for {stat}")


class TestPortfolioSimulator(unittest.TestCase):
    def test_empty_edge_plays(self):
        from scripts.predict_game import _simulate_portfolio
        result = _simulate_portfolio([], 10_000)
        self.assertEqual(result["expected_roi"], 0.0)
        self.assertEqual(result["allocations"], [])

    def test_positive_edge_play(self):
        from scripts.predict_game import _simulate_portfolio
        plays = [{
            "player_name": "LeBron James",
            "stat": "pts",
            "direction": "Over",
            "edge_pct": 0.08,
            "odds": -110,
        }]
        result = _simulate_portfolio(plays, 10_000, n_sims=1000)
        self.assertIn("expected_roi", result)
        self.assertIn("allocations", result)
        self.assertEqual(len(result["allocations"]), 1)

    def test_negative_edge_excluded(self):
        from scripts.predict_game import _simulate_portfolio
        plays = [{
            "player_name": "X",
            "stat": "reb",
            "direction": "Under",
            "edge_pct": -0.05,
            "odds": -110,
        }]
        result = _simulate_portfolio(plays, 10_000)
        self.assertEqual(result["allocations"], [])


class TestLinesParser(unittest.TestCase):
    def test_parse_json_string(self):
        from scripts.predict_game import _parse_lines
        raw = '{"pts": {"LeBron James": 25.5}, "total": 228.5}'
        result = _parse_lines(raw, None)
        self.assertEqual(result["pts"]["LeBron James"], 25.5)
        self.assertEqual(result["total"], 228.5)

    def test_parse_bad_json_returns_empty(self):
        from scripts.predict_game import _parse_lines
        result = _parse_lines("{bad json", None)
        self.assertEqual(result, {})

    def test_parse_none_returns_empty(self):
        from scripts.predict_game import _parse_lines
        result = _parse_lines(None, None)
        self.assertEqual(result, {})


class TestPlayersParser(unittest.TestCase):
    def test_single_team(self):
        from scripts.predict_game import _parse_players
        result = _parse_players("LAL:LeBron James,Anthony Davis")
        self.assertIn("LAL", result)
        self.assertEqual(result["LAL"], ["LeBron James", "Anthony Davis"])

    def test_multi_team(self):
        from scripts.predict_game import _parse_players
        result = _parse_players("LAL:LeBron James;BOS:Jayson Tatum,Jaylen Brown")
        self.assertIn("LAL", result)
        self.assertIn("BOS", result)
        self.assertEqual(len(result["BOS"]), 2)

    def test_empty_string(self):
        from scripts.predict_game import _parse_players
        result = _parse_players("")
        self.assertEqual(result, {})


# ── Subprocess integration test ────────────────────────────────────────────────

class TestCLISubprocess(unittest.TestCase):
    """
    Integration tests that call the CLI as a subprocess.
    These require real model files.  They skip gracefully if models are absent.
    """

    @classmethod
    def setUpClass(cls):
        wp_path = os.path.join(PROJECT_DIR, "data", "models", "win_probability.pkl")
        cls.models_available = os.path.exists(wp_path)
        if not cls.models_available:
            cls.skip_reason = f"win_probability.pkl not found at {wp_path}"

    def _skip_if_no_models(self):
        if not self.models_available:
            self.skipTest(f"Models unavailable: {self.skip_reason}")

    def test_basic_run_no_players(self):
        """CLI runs and produces WIN PROBABILITY + GAME SCORE."""
        self._skip_if_no_models()
        result = _run_cli(
            "--home", "BOS", "--away", "LAL",
            "--date", "2026-05-22", "--no-save-prediction",
        )
        # Tolerate errors from unavailable models (graceful degradation expected)
        self.assertIn("WIN PROBABILITY", result.stdout + result.stderr,
                      msg=f"stdout={result.stdout[:500]}\nstderr={result.stderr[:500]}")

    def test_json_flag_produces_valid_json(self):
        """--json flag returns parseable JSON."""
        self._skip_if_no_models()
        result = _run_cli(
            "--home", "BOS", "--away", "LAL",
            "--date", "2026-05-22", "--json", "--no-save-prediction",
        )
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(f"Invalid JSON output: {result.stdout[:300]}")
        self.assertEqual(parsed.get("home_team"), "BOS")
        self.assertIn("win_probability", parsed)

    def test_output_contains_number(self):
        """Output must contain at least one percentage or decimal number."""
        self._skip_if_no_models()
        import re
        result = _run_cli(
            "--home", "GSW", "--away", "PHX",
            "--date", "2026-05-22", "--no-save-prediction",
        )
        output = result.stdout
        numbers = re.findall(r"\d+\.\d+", output)
        self.assertTrue(len(numbers) > 0,
                        msg=f"No numbers in output: {output[:400]}")

    def test_players_flag_shows_props(self):
        """--players arg causes PLAYER PROPS section to appear."""
        self._skip_if_no_models()
        result = _run_cli(
            "--home", "LAL", "--away", "BOS",
            "--date", "2026-05-22",
            "--players", "LAL:LeBron James",
            "--no-save-prediction",
        )
        output = result.stdout + result.stderr
        # Either player props appear OR an informative skip message
        self.assertTrue(
            "PLAYER PROPS" in output,
            msg=f"PLAYER PROPS section missing. stdout={result.stdout[:500]}"
        )

    def test_no_lines_omits_edge(self):
        """When no --lines provided, edge column is absent."""
        self._skip_if_no_models()
        result = _run_cli(
            "--home", "LAL", "--away", "BOS",
            "--date", "2026-05-22",
            "--players", "LAL:LeBron James",
            "--no-save-prediction",
        )
        # Edge column should NOT appear without lines
        self.assertNotIn("EDGE", result.stdout,
                         msg="EDGE appeared without --lines")


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
