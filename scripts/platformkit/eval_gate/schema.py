"""Golden-set schema + validation for the eval gate (blueprint N1).

Self-contained (stdlib only). validate_golden() enforces the leak guard
(every feature's availability_date must be strictly before the prediction time)
plus coverage of the fragile regimes. A frozen golden set of ~100 states makes
the gate reproducible by a skeptic offline in < 60s.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List

if __package__:
    from .walkforward import LeakError, assert_vintage
else:
    from walkforward import LeakError, assert_vintage

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
    if not 90 <= len(states) <= 120:
        raise LeakError(f"golden set size {len(states)} out of [90,120]")
    seen = set()
    for s in states:
        for k in REQUIRED:
            if k not in s:
                raise LeakError(f"missing field {k} in state {s.get('game_id')}")
        if s["outcome"] not in (0, 1):
            raise LeakError(f"bad outcome in {s['game_id']}")
        if not 0.0 <= s["devig_close_prob"] <= 1.0:
            raise LeakError(f"bad devig_close_prob in {s['game_id']}")
        if not 0.0 <= s["truth_wp"] <= 1.0:
            raise LeakError(f"bad truth_wp in {s['game_id']}")
        if not s["feature_avail"]:
            raise LeakError(f"empty feature_avail in {s['game_id']}")
        if set(s["features"]) != set(s["feature_avail"]):
            raise LeakError(f"feature_avail keys do not match features in {s['game_id']}")
        assert_vintage(s)
        key = (s["game_id"], s["state_ts"])
        if key in seen:
            raise LeakError(f"duplicate state {key}")
        seen.add(key)
    regimes = {s["regime"] for s in states}
    for r in REQUIRED_REGIMES:
        if r not in regimes:
            raise LeakError(f"coverage gap: regime {r} missing")
