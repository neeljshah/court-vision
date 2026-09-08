"""Focused S297 tests for sealing, DNP mixture, rotation grain, and as-of behavior."""
import hashlib

import numpy as np

from scripts.platformkit import s297_minutes_dnp_distribution as s297
from scripts.platformkit.eval_gate.cpcv_vector_distribution import cpcv_evaluate_vector_distributional


def _state(game: str, player: int, day: int, minutes: float) -> dict:
    stamp = "2024-01-{0:02d}T12:00:00".format(day)
    return {"game_id": game, "state_ts": stamp, "stable_key": "{0}|{1}".format(game, player),
            "home": "player:{0}".format(player), "away": "team:A", "player_id": player,
            "features": {"minutes_prior": 0.0}, "feature_avail": {"minutes_prior": "2023-12-01T12:00:00"},
            "outcome_vector": (minutes, float(minutes == 0))}


def test_s297_seal_normalized_and_dnp_future_rotation_overtime() -> None:
    raw = s297.PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, suffix = raw.split(b"SEAL_SHA256:", 1)
    assert hashlib.sha256(prefix).hexdigest() == suffix.splitlines()[0].strip().decode("ascii")

    train = [_state("past", 7, 1, 12.0), _state("future_plant", 7, 3, 99.0), _state("past_dnp", 8, 1, 0.0)]
    forecast = s297._forecast(train, [{"state_ts": "2024-01-02T12:00:00", "stable_key": "test|7", "player_id": 7}])[0]
    assert forecast["asof_max_ts"] == "2024-01-01T12:00:00"
    assert max(forecast["candidate"]) == 12.0, "future-row plant cannot supply a draw"
    assert forecast["candidate_positive_q"] == [12.0, 12.0, 12.0]
    dnp_score = s297._score(forecast, (0.0, 1.0))
    assert dnp_score["candidate_minutes_crps"] >= 0.0
    assert dnp_score["candidate_dnp_brier"] >= 0.0

    states = []
    for day, game in enumerate(("short_rotation", "overtime", "final"), start=1):
        for player in range(7):
            minutes = 53.0 if game == "overtime" and player == 0 else (0.0 if player == 6 else 18.0 + player)
            states.append(_state(game, 100 + player, day, minutes))
    records = cpcv_evaluate_vector_distributional(states, s297._forecast, s297._score, n_groups=3,
        n_test_groups=1, embargo_days=1, strict_redaction=True, allow_keys=("stable_key", "player_id"))
    assert len(records) == 21 and len({record["stable_key"] for record in records}) == 21
    assert any(record["game_id"] == "overtime" for record in records)
    assert all(np.isfinite(record["scores"]["candidate_minutes_crps"]) for record in records)
    assert set(fold["status"] for fold in s297._folds(records).values()) == {"INSUFFICIENT"}
