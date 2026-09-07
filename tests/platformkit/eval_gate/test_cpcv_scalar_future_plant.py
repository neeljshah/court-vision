"""S302: a scalar CPCV score must change if its future plant is unpurged."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from scripts.platformkit.eval_gate import cpcv_engine


_ROOT = Path(__file__).resolve().parents[3]
_PREREG = _ROOT / "docs/evidence/harness/S302_prereg_2026-09-04.md"


def _state(game_id: str, timestamp: str, home: str, away: str,
           group: str, plant_label: int, outcome: int) -> dict:
    return {
        "game_id": game_id,
        "state_ts": timestamp,
        "home": home,
        "away": away,
        "frozen_group": group,
        "features": {"label_revealing_future_plant": plant_label},
        "feature_avail": {
            "label_revealing_future_plant": timestamp[:10] + "T00:00:00",
        },
        "devig_close_prob": 0.5,
        "truth_wp": 0.5,
        "outcome": outcome,
    }


def _fixture_states() -> list[dict]:
    return [
        _state("g0", "2024-07-01T19:00:00", "AAA", "BBB", "g0", 0, 0),
        _state("g1", "2024-07-02T19:00:00", "CCC", "DDD", "g1", 0, 1),
        _state("g2", "2024-07-03T18:00:00", "AAA", "EEE", "g2", 1, 1),
        _state("g3", "2024-07-04T19:00:00", "FFF", "GGG", "g3", 0, 0),
    ]


def _target_result(records: list[dict]) -> dict:
    target = [record for record in records if record["game_id"] == "g0"]
    assert len(target) == 1
    return target[0]


def test_preregistration_seal_is_lf_normalized() -> None:
    """Bind this construct to the preregistration bytes preceding its seal."""
    normalized = _PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal_line = normalized.split(b"Seal-SHA256: ", maxsplit=1)
    expected = seal_line.splitlines()[0].decode("ascii")
    assert hashlib.sha256(prefix).hexdigest() == expected


def test_future_same_team_plant_is_score_sensitive(monkeypatch) -> None:
    """The disabled-purge control must expose the +47-hour future plant."""
    states = _fixture_states()
    train_ids: dict[str, set[str]] = {}

    def score_from_train(train: list[dict], test: dict, _: bool) -> float:
        ids = {state["game_id"] for state in train}
        if test["game_id"] == "g0":
            train_ids["g0"] = ids
            has_revealing_plant = any(
                state["features"]["label_revealing_future_plant"] == state["outcome"] == 1
                for state in train
            )
            return 0.9 if has_revealing_plant else 0.5
        return 0.5

    real_records = cpcv_engine.cpcv_evaluate(
        states, score_from_train, n_groups=4, n_test_groups=1, embargo_days=1,
        group_key="frozen_group",
    )
    real_probability = _target_result(real_records)["p_model"]
    real_train = train_ids["g0"]

    monkeypatch.setattr(cpcv_engine, "_blocked_indices", lambda *_: set())
    control_records = cpcv_engine.cpcv_evaluate(
        states, score_from_train, n_groups=4, n_test_groups=1, embargo_days=1,
        group_key="frozen_group",
    )
    control_probability = _target_result(control_records)["p_model"]
    control_train = train_ids["g0"]
    difference = control_probability - real_probability
    metrics = {
        "construct_cases": 1,
        "control_cases": 1,
        "control_target_probability": control_probability,
        "control_target_train_ids": sorted(control_train),
        "difference": difference,
        "engine_sha256": hashlib.sha256(
            Path(cpcv_engine.__file__).read_bytes()
        ).hexdigest(),
        "plant_absent_from_real_target_train": "g2" not in real_train,
        "real_target_probability": real_probability,
        "real_target_train_ids": sorted(real_train),
        "target_game_id": "g0",
    }
    evidence_path = os.environ.get("S302_EVIDENCE_JSON")
    if evidence_path:
        Path(evidence_path).write_text(
            json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    print("S302 real_purge_target_probability=%.1f" % real_probability)
    print("S302 disabled_purge_target_probability=%.1f" % control_probability)
    print("S302 control_minus_real=%.1f" % difference)
    print("S302 plant_absent_from_real_target_train=%s" % ("g2" not in real_train))
    assert "g2" not in real_train
    assert real_probability == 0.5
    assert "g2" in control_train
    assert difference != 0.0
