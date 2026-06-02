"""tests/test_wave3_misc_fixes.py

Wave-3 regression tests for three bug fixes:

  Bug 4 — live_game_router._load_pregame_for_game must NEVER return the
           whole predictions_cache when no player/team match is available.

  Bug 5 — cv_fix_bet_timing._grade must treat a push (actual == line) as
           hit=None / net_units=0.0, not a loss.

  Bug 6 — pointsbet_scraper.decimal_to_american(1.0) must return None (no
           ZeroDivisionError); downstream call site must skip None results;
           and one_snapshot must not abort on a bad event.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Ensure repo root is importable
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ===========================================================================
# Bug 4 — _load_pregame_for_game returns [] for an unresolvable game_id
# ===========================================================================
class TestBug4LoadPregameForGame(unittest.TestCase):
    """_load_pregame_for_game must not return the whole league when the
    game_id has no matching props and no team abbreviations are available."""

    def _make_parquet_df(self):
        """Build a tiny in-memory DataFrame that mimics the cache parquet."""
        import pandas as pd  # noqa: PLC0415
        return pd.DataFrame([
            {"player_name": f"Player {i}", "team": "LAL", "stat": "pts",
             "q50": 20.0, "q10": 15.0, "q90": 25.0}
            for i in range(508)
        ] + [
            {"player_name": f"Away {i}", "team": "BOS", "stat": "pts",
             "q50": 18.0, "q10": 13.0, "q90": 23.0}
            for i in range(10)
        ])

    def test_returns_empty_when_no_match_and_no_team_abbrevs(self):
        """When consolidate() returns nothing for this game_id AND
        resolve_game_id() returns {}, _load_pregame_for_game must return []."""
        try:
            import pandas as pd  # noqa: PLC0415
        except ImportError:
            self.skipTest("pandas not available")

        df = self._make_parquet_df()

        # Patch: parquet exists and loads; consolidate returns props for a
        # DIFFERENT game_id; resolve_game_id returns {}.
        fake_consolidate = [
            {"game_id": "OTHER_GAME", "player": "Some Player"},
        ]

        with patch("api.live_game_router._ROOT", _ROOT), \
             patch("pandas.read_parquet", return_value=df), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("api._courtvision_odds.consolidate", return_value=fake_consolidate,
                   create=True), \
             patch("api._courtvision_odds.resolve_game_id", return_value={},
                   create=True):
            from api.live_game_router import _load_pregame_for_game  # noqa: PLC0415
            result = _load_pregame_for_game("UNRESOLVABLE_GAME_ID", "2026-01-01")

        # Must be empty — not 508 rows
        self.assertEqual(result, [],
                         f"Expected [], got {len(result)} rows — whole-league fallback triggered")

    def test_returns_team_rows_when_team_abbrevs_known(self):
        """When resolve_game_id() returns home/away abbrevs and the parquet
        has rows for those teams, only those rows are returned."""
        try:
            import pandas as pd  # noqa: PLC0415
        except ImportError:
            self.skipTest("pandas not available")

        df = self._make_parquet_df()  # LAL (508 rows) + BOS (10 rows)

        fake_consolidate: list = []  # no props for this game_id
        resolved = {"home_abbr": "LAL", "away_abbr": "BOS"}

        with patch("api.live_game_router._ROOT", _ROOT), \
             patch("pandas.read_parquet", return_value=df), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("api._courtvision_odds.consolidate", return_value=fake_consolidate,
                   create=True), \
             patch("api._courtvision_odds.resolve_game_id", return_value=resolved,
                   create=True):
            from api.live_game_router import _load_pregame_for_game  # noqa: PLC0415
            result = _load_pregame_for_game("GAME_WITH_TEAMS", "2026-01-01")

        teams = {r["team"] for r in result}
        self.assertIn("LAL", teams)
        self.assertIn("BOS", teams)
        # Must NOT include other teams
        other = teams - {"LAL", "BOS"}
        self.assertEqual(other, set(), f"Unexpected teams in result: {other}")
        # Total rows = 508 (LAL) + 10 (BOS) = 518 — not 508-only fallback
        self.assertEqual(len(result), 518)


# ===========================================================================
# Bug 5 — _grade treats push as hit=None / net_units=0.0
# ===========================================================================
class TestBug5GradePush(unittest.TestCase):
    """A push (actual == line) must be hit=None and net_units==0.0."""

    def _make_cap(self, side: str, line: float, price: int = -110):
        return {
            "disp": "Test Player",
            "line": line,
            "proj": line,
            "entry_label": "Q2",
            "stage": "Q2",
            "cap": 1,
            "ep": 0.5,
            "eval": {
                "side": side,
                "price": price,
                "ev": 0.01,
                "prob": 0.52,
                "edge": 0.02,
            },
        }

    def _import_grade(self):
        # Import lazily so the module is only loaded when pandas etc. are ready
        import importlib  # noqa: PLC0415
        spec = importlib.util.spec_from_file_location(
            "cv_fix_bet_timing",
            str(_ROOT / "scripts" / "cv_fix_bet_timing.py"),
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod._grade

    def test_over_push(self):
        """OVER line=7.0 actual=7.0 → hit=None, net_units=0.0."""
        _grade = self._import_grade()
        cap = self._make_cap("OVER", 7.0)
        actuals = {("Test Player", "pts"): 7.0}
        row = _grade(cap, ("Test Player", "pts"), actuals)
        self.assertIsNone(row["hit"], "Push OVER: hit must be None")
        self.assertAlmostEqual(row["net_units"], 0.0, places=6,
                               msg="Push OVER: net_units must be 0.0")

    def test_under_push(self):
        """UNDER line=7.0 actual=7.0 → hit=None, net_units=0.0."""
        _grade = self._import_grade()
        cap = self._make_cap("UNDER", 7.0)
        actuals = {("Test Player", "pts"): 7.0}
        row = _grade(cap, ("Test Player", "pts"), actuals)
        self.assertIsNone(row["hit"], "Push UNDER: hit must be None")
        self.assertAlmostEqual(row["net_units"], 0.0, places=6,
                               msg="Push UNDER: net_units must be 0.0")

    def test_over_win(self):
        """OVER line=7.0 actual=8.0 → hit=True, net_units > 0."""
        _grade = self._import_grade()
        cap = self._make_cap("OVER", 7.0)
        actuals = {("Test Player", "pts"): 8.0}
        row = _grade(cap, ("Test Player", "pts"), actuals)
        self.assertTrue(row["hit"])
        self.assertGreater(row["net_units"], 0.0)

    def test_over_loss(self):
        """OVER line=7.0 actual=6.0 → hit=False, net_units==-1.0."""
        _grade = self._import_grade()
        cap = self._make_cap("OVER", 7.0)
        actuals = {("Test Player", "pts"): 6.0}
        row = _grade(cap, ("Test Player", "pts"), actuals)
        self.assertFalse(row["hit"])
        self.assertAlmostEqual(row["net_units"], -1.0, places=6)

    def test_push_not_graded_in_summarize(self):
        """_summarize must exclude push rows (hit=None) from n/hit_pct/ROI."""
        import importlib  # noqa: PLC0415
        spec = importlib.util.spec_from_file_location(
            "cv_fix_bet_timing",
            str(_ROOT / "scripts" / "cv_fix_bet_timing.py"),
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _summarize = mod._summarize

        bets = [
            {"hit": True, "net_units": 0.909, "entry_stage": "Pregame"},
            {"hit": None, "net_units": 0.0, "entry_stage": "Pregame"},   # push
            {"hit": False, "net_units": -1.0, "entry_stage": "Pregame"},
        ]
        summary = _summarize(bets)
        self.assertEqual(summary["n"], 2, "Push must be excluded from n")
        self.assertEqual(summary["hits"], 1)


# ===========================================================================
# Bug 6 — decimal_to_american guards d<=1.0; bad event isolated in snapshot
# ===========================================================================
class TestBug6DecimalToAmerican(unittest.TestCase):
    """decimal_to_american must return None for d<=1.0 without raising."""

    def _import_mod(self):
        import importlib  # noqa: PLC0415
        spec = importlib.util.spec_from_file_location(
            "pointsbet_scraper",
            str(_ROOT / "scripts" / "pointsbet_scraper.py"),
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        # Stub out curl_cffi so the import doesn't fail in test environments
        fake_cf = types.ModuleType("curl_cffi")
        fake_requests = types.ModuleType("curl_cffi.requests")
        fake_cf.requests = fake_requests
        sys.modules.setdefault("curl_cffi", fake_cf)
        sys.modules.setdefault("curl_cffi.requests", fake_requests)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_d_equals_1_returns_none(self):
        mod = self._import_mod()
        result = mod.decimal_to_american(1.0)
        self.assertIsNone(result, "decimal_to_american(1.0) must return None, not raise")

    def test_d_below_1_returns_none(self):
        mod = self._import_mod()
        result = mod.decimal_to_american(0.5)
        self.assertIsNone(result)

    def test_d_1_5_returns_minus_200(self):
        """1.5 → -200 (dog favourite: -100/(1.5-1) = -100/0.5 = -200)."""
        mod = self._import_mod()
        result = mod.decimal_to_american(1.5)
        self.assertEqual(result, -200)

    def test_d_2_0_returns_100(self):
        """2.0 → +100 (evens)."""
        mod = self._import_mod()
        result = mod.decimal_to_american(2.0)
        self.assertEqual(result, 100)

    def test_d_3_0_returns_200(self):
        """3.0 → +200."""
        mod = self._import_mod()
        result = mod.decimal_to_american(3.0)
        self.assertEqual(result, 200)


if __name__ == "__main__":
    unittest.main()
