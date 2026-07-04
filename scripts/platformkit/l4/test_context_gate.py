"""Tests for scripts.platformkit.l4.context_gate -- the L4 pre-registration gate.

Three fixture classes, one per verdict path that matters:
  1. genuine signal      -> ADDS_SKILL, and the planted-null (shuffled) variant must NOT
                            also show a CI-positive delta (it must fail to "improve").
  2. pure noise          -> NO_ADD.
  3. leaking context     -> context_prob literally encodes the outcome even after a
                            game-level shuffle would normally sever the link (built so the
                            shuffled variant ALSO improves) -> PLANTED_NULL_FAIL/SCOUTING_ONLY.
Plus: sample-floor / INSUFFICIENT, determinism of the seed, and malformed-row exclusion.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/l4/test_context_gate.py -q
"""
from __future__ import annotations

import random
import unittest

from scripts.platformkit.l4 import context_gate as cg


def _make_rows(n_games: int, ticks: int, base_noise: float, context_fn, seed: int):
    """Build synthetic rows: latent per-game strength drives outcome; base_prob is a
    noisy but real function of strength; context_fn(strength, outcome, rng) returns
    context_prob for a given game (constant across that game's ticks, for simplicity)."""
    rng = random.Random(seed)
    rows = []
    for g in range(n_games):
        strength = rng.uniform(-2.0, 2.0)
        p_true = 1.0 / (1.0 + pow(2.718281828, -strength))
        outcome = 1 if rng.random() < p_true else 0
        base_p = min(max(p_true + rng.uniform(-base_noise, base_noise), 0.01), 0.99)
        ctx_p = context_fn(strength, outcome, p_true, rng)
        ctx_p = min(max(ctx_p, 0.01), 0.99)
        for t in range(ticks):
            rows.append({
                "game_id": "G%03d" % g, "state_ts": t,
                "base_prob": base_p, "context_prob": ctx_p,
                "context_id": "fixture", "outcome": outcome,
            })
    return rows


class TestGenuineSignal(unittest.TestCase):
    """Context adds real per-game information beyond base -> ADDS_SKILL, null must fail."""

    def test_adds_skill_and_null_does_not_improve(self):
        def ctx_fn(strength, outcome, p_true, rng):
            # context sees the TRUE probability almost exactly (tiny noise) while base
            # only sees a noisy proxy -- context should genuinely beat base. A real
            # per-GAME signal like this is exactly what a whole-game shuffle destroys.
            return p_true + rng.uniform(-0.02, 0.02)

        rows = _make_rows(n_games=100, ticks=10, base_noise=0.45, context_fn=ctx_fn, seed=1)
        result = cg.evaluate(rows)
        self.assertEqual(result.verdict, cg.VERDICT_ADDS_SKILL)
        self.assertEqual(result.label, "")
        self.assertGreater(result.real_ci95[0], 0.0)
        # the shuffled (planted-null) variant must NOT also be CI-positive
        self.assertLessEqual(result.null_ci95[0], 0.0)


class TestPureNoise(unittest.TestCase):
    """Context is independent random noise unrelated to outcome -> NO_ADD."""

    def test_no_add(self):
        def ctx_fn(strength, outcome, p_true, rng):
            return rng.uniform(0.2, 0.8)  # unrelated to strength/outcome

        rows = _make_rows(n_games=60, ticks=6, base_noise=0.15, context_fn=ctx_fn, seed=2)
        result = cg.evaluate(rows)
        self.assertEqual(result.verdict, cg.VERDICT_NO_ADD)
        self.assertEqual(result.label, "")


class TestPlantedNullFail(unittest.TestCase):
    """context_prob carries NO per-game skill at all -- it is just a single GLOBAL
    CONSTANT (the corpus-wide outcome rate) applied to every row, beating a badly
    miscalibrated base. A whole-game shuffle cannot touch a value that is already
    identical across every game, so the shuffled variant "improves" exactly as much
    as the real one -> the improvement is a flexibility/leak artifact, not per-game
    skill -> PLANTED_NULL_FAIL -> SCOUTING_ONLY. This is the realistic failure mode
    the planted-null exists to catch: a context layer that looks skillful only
    because it recovers the population base rate, not because it reads any game."""

    def test_planted_null_fail(self):
        rng = random.Random(9)
        rows = []
        outcomes = []
        for g in range(80):
            strength = rng.uniform(-2.0, 2.0)
            p_true = 1.0 / (1.0 + pow(2.718281828, -strength))
            outcome = 1 if rng.random() < p_true else 0
            outcomes.append(outcome)
            # base is badly miscalibrated: pushed AWAY from the true probability.
            base_p = (min(max(p_true + 0.4, 0.01), 0.99) if p_true < 0.5
                      else min(max(p_true - 0.4, 0.01), 0.99))
            for t in range(6):
                rows.append({"game_id": "G%03d" % g, "state_ts": t, "base_prob": base_p,
                             "context_prob": None, "context_id": "fixture", "outcome": outcome})
        corpus_rate = round(sum(outcomes) / len(outcomes), 4)
        for r in rows:
            r["context_prob"] = corpus_rate  # identical constant on every row/game

        result = cg.evaluate(rows)
        self.assertEqual(result.verdict, cg.VERDICT_PLANTED_NULL_FAIL)
        self.assertEqual(result.label, "SCOUTING_ONLY")
        self.assertGreater(result.null_ci95[0], 0.0)
        self.assertGreater(result.real_ci95[0], 0.0)


class TestFloorsAndHygiene(unittest.TestCase):
    def test_insufficient_below_floors(self):
        rows = _make_rows(n_games=5, ticks=2, base_noise=0.2,
                           context_fn=lambda s, o, p, r: p, seed=4)
        result = cg.evaluate(rows)
        self.assertEqual(result.verdict, cg.VERDICT_INSUFFICIENT)
        self.assertTrue(any("floors" in c for c in result.caveats))

    def test_malformed_rows_excluded_and_counted(self):
        rows = _make_rows(n_games=40, ticks=8, base_noise=0.2,
                           context_fn=lambda s, o, p, r: p, seed=5)
        bad = [
            {"game_id": "BAD1", "state_ts": 0, "base_prob": 1.5, "context_prob": 0.5,
             "context_id": "x", "outcome": 1},
            {"game_id": "BAD2", "state_ts": 0, "base_prob": 0.5, "context_prob": 0.5,
             "context_id": "x", "outcome": 2},
            {"game_id": "BAD3", "state_ts": 0},
        ]
        result = cg.evaluate(rows + bad)
        self.assertEqual(result.n_excluded_rows, 3)
        self.assertTrue(any("excluded" in c for c in result.caveats))

    def test_seed_is_deterministic_across_calls(self):
        rows = _make_rows(n_games=40, ticks=8, base_noise=0.2,
                           context_fn=lambda s, o, p, r: p, seed=6)
        r1 = cg.evaluate(rows)
        r2 = cg.evaluate(rows)
        self.assertEqual(r1.seed_used, r2.seed_used)
        self.assertEqual(r1.real_delta, r2.real_delta)
        self.assertEqual(r1.null_delta, r2.null_delta)

    def test_no_llm_calls_no_edge_claim(self):
        rows = _make_rows(n_games=40, ticks=8, base_noise=0.2,
                           context_fn=lambda s, o, p, r: p, seed=7)
        result = cg.evaluate(rows)
        self.assertFalse(result.edge_claimed)


if __name__ == "__main__":
    unittest.main()
