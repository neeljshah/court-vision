"""Construct fixture for S268's distributional CPCV route.

Run: python -m pytest tests/platformkit/test_s268_distributional_evaluator_route.py -q -p no:cacheprovider
"""
from __future__ import annotations

import random
import csv
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from scripts.platformkit.eval_gate.cpcv_distribution import cpcv_evaluate_distributional
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/harness/S268_distributional_evaluator_route_prereg_2026-09-04_attempt2.md"
PAIRED = ROOT / "docs/evidence/harness/S268_distributional_evaluator_route_mlb_paired_losses_2026-09-04_attempt2.csv"
ENGINE = ROOT / "scripts/platformkit/eval_gate/cpcv_engine.py"
MASTER_ENGINE_SHA256 = "e9fe694a721658a067bd452911b7f95627897ba4d6c6dccd86cc080f9fa6935c"


def _state(game_id: str, stamp: datetime, home: str, away: str, outcome: int,
           features: dict[str, float]) -> dict:
    return {
        "game_id": game_id, "state_ts": stamp.isoformat(), "home": home, "away": away,
        "features": features,
        "feature_avail": {name: stamp.replace(hour=0, minute=0, second=0).isoformat()
                          for name in features},
        "devig_close_prob": 0.5, "truth_wp": 0.5, "outcome": outcome,
    }


def _fixture() -> list[dict]:
    rng = random.Random(268)
    start = datetime(2024, 1, 1, 19)
    target_index = 14
    states = []
    for index in range(32):
        stamp = start + timedelta(days=index)
        is_target = index == target_index
        states.append(_state(
            "target" if is_target else "regular-{0}".format(index), stamp,
            "TARGET" if is_target else "HOME-{0}".format(index),
            "OPPONENT" if is_target else "AWAY-{0}".format(index),
            1 if is_target else rng.randrange(2), {"x": rng.random()},
        ))
    target = states[target_index]
    states.append(_state(
        "planted-leak", datetime.fromisoformat(target["state_ts"]) + timedelta(hours=47),
        "TARGET", "LEAK-OPPONENT", rng.randrange(2),
        {"x": rng.random(), "planted_label": float(target["outcome"])},
    ))
    return states


def test_fixture_matches_scalar_brier_and_proves_purge_changes_the_score():
    states = _fixture()
    seen = {"honest": False, "leaky": False}

    def forecast(train: list[dict], test: dict, select_inside: bool) -> list[float]:
        if test["game_id"] != "target":
            return [0.5]
        planted = [row for row in train if row["game_id"] == "planted-leak"]
        if planted:
            seen["leaky"] = True
            return [planted[0]["features"]["planted_label"]]
        seen["honest"] = True
        return [0.5]

    def scalar(train: list[dict], test: dict, select_inside: bool) -> float:
        return forecast(train, test, select_inside)[0]

    def brier(samples: tuple[float, ...], outcome: float) -> dict[str, float]:
        return {"brier": (samples[0] - outcome) ** 2}

    kwargs = {"n_groups": 33, "n_test_groups": 1, "embargo_days": 1}
    honest = cpcv_evaluate_distributional(states, forecast, brier, **kwargs)
    scalar_records = cpcv_evaluate(states, scalar, **kwargs)
    honest_brier = sum(record["brier"] for record in honest) / len(honest)
    scalar_brier = sum((record["p_model"] - record["y"]) ** 2 for record in scalar_records) / len(scalar_records)
    assert len(honest) == len(scalar_records) == 33
    assert abs(honest_brier - scalar_brier) <= 1e-9
    assert seen["honest"] and not seen["leaky"]

    leaky = cpcv_evaluate_distributional(
        states, forecast, brier, **kwargs, debug_disable_purge=True)
    leaky_brier = sum(record["brier"] for record in leaky) / len(leaky)
    honest_target = next(record["brier"] for record in honest if record["game_id"] == "target")
    leaky_target = next(record["brier"] for record in leaky if record["game_id"] == "target")
    assert seen["leaky"]
    assert honest_brier != leaky_brier
    assert leaky_target < honest_target


def test_attempt2_seal_identity_and_real_archive_structure():
    normalized = PREREG.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    marker = b"S268_ATTEMPT2_PREREG_SEAL_SHA256="
    prefix, declared = normalized.split(marker, 1)
    assert hashlib.sha256(prefix).hexdigest() == declared.splitlines()[0].decode("ascii")
    assert hashlib.sha256(ENGINE.read_bytes()).hexdigest() == MASTER_ENGINE_SHA256

    with PAIRED.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len({row["row_index"] for row in rows}) == 3000
    assert len({row["game_id"] for row in rows}) == 3000
    assert len({row["cluster_date"] for row in rows}) == 777
    required = {
        "cluster_date", "row_index", "game_id", "ts", "forecast_samples_json", "n_train",
        "archived_crps", "new_crps", "delta_crps", "archived_pinball_q10",
        "new_pinball_q10", "delta_pinball_q10", "archived_pinball_q50",
        "new_pinball_q50", "delta_pinball_q50", "archived_pinball_q90",
        "new_pinball_q90", "delta_pinball_q90",
    }
    assert rows and required.issubset(rows[0])
