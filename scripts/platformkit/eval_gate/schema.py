"""Golden-set schema + validation for the eval gate (blueprint N1).

Self-contained (stdlib only). validate_golden() enforces the leak guard
(every feature's availability_date must be strictly before the prediction time)
plus coverage of the fragile regimes. A frozen golden set of ~100 states makes
the gate reproducible by a skeptic offline in < 60s.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List

GOLDEN_SCHEMA_VERSION = 1

REQUIRED = (
    "game_id", "season", "sport", "regime", "game_date", "state_ts",
    "features", "feature_avail", "devig_close_prob", "truth_wp", "outcome",
)

# fragile regimes that must be represented so the gate exercises them
REQUIRED_REGIMES = ("pregame", "q4", "blowout", "foul_trouble")


@dataclass(frozen=True)
class GameState:
    game_id: str
    season: str
    sport: str
    regime: str
    game_date: str               # ISO date of tip (prediction-time boundary)
    state_ts: str                # ISO datetime of the state (== game_date for pregame)
    features: Dict[str, float]
    feature_avail: Dict[str, str]  # feature -> ISO date it became known
    devig_close_prob: float        # Shin-devigged close (the reference forecaster)
    truth_wp: float                # empirical/replay WP for the state's bucket
    outcome: int                   # realized binary outcome (0/1), the scoring label


def validate_golden(states: List[dict]) -> None:
    """Raise AssertionError on any leak, malformed field, dup, or coverage gap."""
    assert 90 <= len(states) <= 120, f"golden set size {len(states)} out of [90,120]"
    seen = set()
    for s in states:
        for k in REQUIRED:
            assert k in s, f"missing field {k} in state {s.get('game_id')}"
        assert s["outcome"] in (0, 1), f"bad outcome in {s['game_id']}"
        assert 0.0 <= s["devig_close_prob"] <= 1.0, f"bad devig_close_prob in {s['game_id']}"
        assert 0.0 <= s["truth_wp"] <= 1.0, f"bad truth_wp in {s['game_id']}"
        # LEAK GUARD: every feature must be known strictly before the prediction time
        for f, avail in s["feature_avail"].items():
            assert avail < s["state_ts"], (
                f"LEAK: feature {f} availability {avail} >= state_ts "
                f"{s['state_ts']} in {s['game_id']}"
            )
        key = (s["game_id"], s["state_ts"])
        assert key not in seen, f"duplicate state {key}"
        seen.add(key)
    regimes = {s["regime"] for s in states}
    for r in REQUIRED_REGIMES:
        assert r in regimes, f"coverage gap: regime {r} missing"
