"""Teacher-to-student calibration gate.

Preregistered verdict rule (not sealed for a real trial today): TEACHES only
when the student improves Brier by at least 0.004 over an empirical-Bayes
ID fixed-effect baseline, its game-clustered DM 95 percent confidence interval
excludes zero, its launch-K-deflated p-value is below 0.05, and adding IDs to
the student changes Brier by no more than 0.004.  INSUFFICIENT applies below
30 effective observations or 20 game clusters; every other result is NULL.

The preregistered SHA-256 is persisted before the first metric and the supplied
ledger is charged before any score.  This module is a harness only: no real
teacher is sealed by it until the S26 blocker is resolved.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.backtest_runner import _charge_ledger
from scripts.platformkit.eval_gate.deflated_metrics import deflated_p
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.eval_gate.walkforward import assert_vintage, walk_forward
from scripts.platformkit.ingame.gap_effective_n import (
    effective_sample_size,
    intraclass_correlation,
)

_DELTA_BRIER_BAR = 0.004
_P_BAR = 0.05
_MIN_N_EFF = 30.0
_MIN_CLUSTERS = 20
_DEFAULT_OUTPUT_DIR = Path("data/cache/eval_gate")
_PREREG_RULE = (
    "TEACHES iff delta_brier >= 0.004 vs id fixed effects; DM 95 pct CI "
    "excludes 0; deflated_p < 0.05 at launch K; and "
    "brier(student)-brier(student+ids) <= 0.004. INSUFFICIENT iff n_eff < 30 "
    "or clusters < 20; otherwise NULL."
)
_PREREG_SHA256 = hashlib.sha256(_PREREG_RULE.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class StudentVerdict:
    """Result of one preregistered teacher-to-student comparison."""

    verdict: str
    delta_brier: float
    dm_ci: tuple[float, float]
    raw_p: float
    deflated_p: float
    k_cumulative: int
    n_eff: float
    detail: dict


def _id_summary(train: Sequence[dict], id_key: str, prior_strength: float) -> tuple[dict, float]:
    if prior_strength <= 0.0:
        raise ValueError("prior_strength must be positive")
    if not train:
        return {}, 0.5
    outcomes = np.asarray([row["outcome"] for row in train], dtype=float)
    mean = float(outcomes.mean())
    groups: dict[object, list[float]] = {}
    for row in train:
        groups.setdefault(row.get(id_key), []).append(float(row["outcome"]))
    effects = {
        key: (sum(values) - len(values) * mean) / (len(values) + prior_strength)
        for key, values in groups.items()
    }
    return effects, mean


def id_fixed_effect_baseline(
    train: Sequence[dict], test: dict, id_key: str = "player_id", prior_strength: float = 50.0
) -> float:
    """Predict with a train-only empirical-Bayes per-ID deviation from global rate."""
    effects, mean = _id_summary(train, id_key, prior_strength)
    return float(np.clip(mean + effects.get(test.get(id_key), 0.0), 0.0, 1.0))


def _student_only(
    train: Sequence[dict], test: dict, student_fn: Callable[[list[dict], dict, bool], float], id_key: str
) -> float:
    """Keep the student arm blind to the identifier used by the control arms."""
    train_view = [{key: value for key, value in row.items() if key != id_key} for row in train]
    test_view = {key: value for key, value in test.items() if key != id_key}
    return float(student_fn(train_view, test_view, True))


def _student_plus_ids(
    train: Sequence[dict], test: dict, student_fn: Callable[[list[dict], dict, bool], float], id_key: str,
    prior_strength: float = 50.0,
) -> float:
    """Add the train-only EB ID residual to the student's probability."""
    student_p = _student_only(train, test, student_fn, id_key)
    effects, _mean = _id_summary(train, id_key, prior_strength)
    return float(np.clip(student_p + effects.get(test.get(id_key), 0.0), 0.0, 1.0))


def _registered_inputs(student_fn: Callable) -> object:
    return getattr(student_fn, "registered_inputs", getattr(student_fn, "input_registry", None))


def _assert_runtime_pure(student_fn: Callable) -> None:
    """Refuse a student declaring any registered input unavailable at runtime."""
    registered = _registered_inputs(student_fn)
    if registered is None:
        return
    entries = registered.items() if isinstance(registered, dict) else enumerate(registered)
    for name, metadata in entries:
        available = metadata.get("runtime_available") if isinstance(metadata, dict) else getattr(
            metadata, "runtime_available", None
        )
        if available is False:
            raise ValueError(f"student input {name!r} is registered runtime_available=False")


def _window(states: Sequence[dict]) -> tuple[str, str, str]:
    if not states:
        raise ValueError("states must not be empty")
    ordered = sorted(states, key=lambda row: row["state_ts"])
    sport = str(ordered[0].get("sport", "all"))
    return sport, ordered[0]["state_ts"][:10], ordered[-1]["state_ts"][:10]


def _output_path(name: str, output_dir: Path | None) -> Path:
    if not name or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in name):
        raise ValueError("name must contain only letters, digits, underscores, or hyphens")
    return (output_dir or _DEFAULT_OUTPUT_DIR) / f"student_gate_{name}.json"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii")


def run_student_gate(
    states: list[dict],
    student_fn: Callable[[list[dict], dict, bool], float],
    *,
    id_key: str = "player_id",
    prior_strength: float = 50.0,
    ledger_path: Path,
    charge_spec: str,
    name: str,
    output_dir: Path | None = None,
) -> StudentVerdict:
    """Run the three-arm, leak-checked teacher-to-student calibration comparison."""
    _assert_runtime_pure(student_fn)
    for state in states:
        assert_vintage(state)
    sport, start, end = _window(states)
    artifact = _output_path(name, output_dir)
    prereg = {"prereg_rule": _PREREG_RULE, "prereg_sha256": _PREREG_SHA256, "status": "PREREG_SEALED"}
    _write(artifact, prereg)
    charge = _charge_ledger(ledger_path, charge_spec, sport, start, end)
    prereg.update({"k_cumulative": int(charge["k_cumulative"]), "ledger_row": charge})
    _write(artifact, prereg)

    baseline = walk_forward(
        states, lambda train, test, _inside: id_fixed_effect_baseline(train, test, id_key, prior_strength)
    )
    student = walk_forward(states, lambda train, test, _inside: _student_only(train, test, student_fn, id_key))
    student_ids = walk_forward(
        states, lambda train, test, _inside: _student_plus_ids(
            train, test, student_fn, id_key, prior_strength
        )
    )
    y = [row["y"] for row in baseline.records]
    base_p = [row["p_model"] for row in baseline.records]
    student_p = [row["p_model"] for row in student.records]
    student_ids_p = [row["p_model"] for row in student_ids.records]
    briers = {"id_baseline": brier(base_p, y), "student": brier(student_p, y), "student_plus_ids": brier(student_ids_p, y)}
    differentials = [(base - truth) ** 2 - (candidate - truth) ** 2 for base, candidate, truth in zip(base_p, student_p, y)]
    game_ids = [row["game_id"] for row in baseline.records]
    dm = diebold_mariano(differentials, game_ids)
    residuals = np.asarray(student_p, dtype=float) - np.asarray(y, dtype=float)
    residual_frame = pd.DataFrame({"game": game_ids, "loss_differential": residuals})
    rho = intraclass_correlation(residual_frame)
    ess = effective_sample_size(residual_frame)
    n_eff = float(ess["n_eff"])
    deflated = deflated_p(dm.p_value, int(charge["k_cumulative"]))
    delta = float(briers["id_baseline"] - briers["student"])
    id_delta = float(briers["student"] - briers["student_plus_ids"])
    if n_eff < _MIN_N_EFF or dm.n_clusters < _MIN_CLUSTERS:
        verdict = "INSUFFICIENT"
    elif delta >= _DELTA_BRIER_BAR and dm.ci95[0] > 0.0 and deflated < _P_BAR and id_delta <= _DELTA_BRIER_BAR:
        verdict = "TEACHES"
    else:
        verdict = "NULL"
    detail = {
        "arm_briers": briers,
        "student_minus_student_ids_brier": id_delta,
        "clusters": dm.n_clusters,
        "icc": float(rho),
        "n_rows": len(y),
        "ledger_row": charge,
    }
    result = StudentVerdict(verdict, delta, dm.ci95, dm.p_value, deflated, int(charge["k_cumulative"]), n_eff, detail)
    payload = {
        **prereg,
        **asdict(result),
        "arm_briers": briers,
        "dm_ci": list(result.dm_ci),
    }
    _write(artifact, payload)
    return result


__all__ = ["StudentVerdict", "id_fixed_effect_baseline", "run_student_gate"]
