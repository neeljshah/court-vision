"""S301 tests for opt-in unique evaluator-state keys."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from scripts.platformkit.eval_gate.cpcv_distribution import cpcv_evaluate_distributional
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.walkforward import walk_forward


_ROOT = Path(__file__).resolve().parents[3]
_PREREG = _ROOT / "docs/evidence/harness/S301_unique_state_key_routes_2026-09-04_prereg.md"
_DUPLICATE_KEY = "duplicate-game|2024-01-01T19:00:00"


def _state(game_id: str, state_ts: str, ordinal: int) -> dict:
    return {
        "game_id": game_id, "state_ts": state_ts,
        "home": f"home-{ordinal}", "away": f"away-{ordinal}",
        "features": {"x": float(ordinal)},
        "feature_avail": {"x": state_ts[:10] + "T00:00:00"},
        "devig_close_prob": 0.5, "outcome": ordinal % 2,
    }


def _fixture(simultaneous: bool) -> list[dict]:
    second_game = "simultaneous-b" if simultaneous else "duplicate-game"
    return [
        _state("duplicate-game" if not simultaneous else "simultaneous-a",
               "2024-01-01T19:00:00", 0),
        _state(second_game, "2024-01-01T19:00:00", 1),
        _state("g2", "2024-01-05T19:00:00", 2),
        _state("g3", "2024-01-09T19:00:00", 3),
    ]


def _probability(train: list[dict], test: dict, select_inside: bool) -> float:
    return 0.5


def _distribution(train: list[dict], test: dict, select_inside: bool) -> tuple[float, float]:
    return (0.25, 0.75)


def _distribution_score(forecast: tuple[float, ...], outcome: float) -> dict[str, float]:
    return {"calibration_loss": (sum(forecast) / len(forecast) - outcome) ** 2}


def _walk(states: list[dict], guard: bool | None) -> list[dict]:
    kwargs = {} if guard is None else {"guard_state_keys": guard}
    return walk_forward(states, _probability, **kwargs).records


def _cpcv(states: list[dict], guard: bool | None) -> list[dict]:
    kwargs = {} if guard is None else {"guard_state_keys": guard}
    return cpcv_evaluate(states, _probability, n_groups=3, n_test_groups=1,
                         embargo_days=1, **kwargs)


def _distributional(states: list[dict], guard: bool | None) -> list[dict]:
    kwargs = {} if guard is None else {"guard_state_keys": guard}
    return cpcv_evaluate_distributional(
        states, _distribution, _distribution_score, n_groups=3,
        n_test_groups=1, embargo_days=1, **kwargs,
    )


_ROUTES = [
    ("walk_forward", _walk, "p_model"),
    ("cpcv_evaluate", _cpcv, "p_model"),
    ("cpcv_evaluate_distributional", _distributional, "calibration_loss"),
]


def _record_loss(record: dict, field: str) -> float:
    if field == "p_model":
        return (record[field] - record["y"]) ** 2
    return record[field]


def test_preregistration_seal_uses_normalized_file_bytes() -> None:
    raw = _PREREG.read_bytes().replace(b"\r\n", b"\n")
    above, seal = raw.split(b"Seal-SHA256: ", maxsplit=1)
    assert hashlib.sha256(above).hexdigest() == seal.strip().decode("ascii")


@pytest.mark.parametrize(("route_name", "route", "loss_field"), _ROUTES)
def test_duplicate_state_key_raises(route_name, route, loss_field) -> None:
    with pytest.raises(ValueError, match=rf"^duplicate state key: {re.escape(_DUPLICATE_KEY)}$"):
        route(_fixture(simultaneous=False), True)


@pytest.mark.parametrize(("route_name", "route", "loss_field"), _ROUTES)
def test_simultaneous_distinct_games_are_accepted(route_name, route, loss_field) -> None:
    assert len(route(_fixture(simultaneous=True), True)) == 4


@pytest.mark.parametrize(("route_name", "route", "loss_field"), _ROUTES)
def test_guard_off_reproduces_fixture_score_byte_identically(route_name, route, loss_field) -> None:
    baseline = route(_fixture(simultaneous=True), None)
    candidate = route(_fixture(simultaneous=True), False)
    assert json.dumps(baseline, sort_keys=True, separators=(",", ":")) == json.dumps(
        candidate, sort_keys=True, separators=(",", ":")
    )
    deltas = [
        abs(_record_loss(before, loss_field) - _record_loss(after, loss_field))
        for before, after in zip(baseline, candidate)
    ]
    assert max(deltas) == 0.0
