"""Hand-pinned S322 semantics and cached-logit ablation checks."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.s322_prior_ablation import _fit, paired_bootstrap
from scripts.platformkit.ingame.s322_semantics_trace import CRITERIA, select_boundary_states, trace_state


def _state(**changes: object) -> dict[str, object]:
    state: dict[str, object] = {
        "state_key": "g1:120", "game_id": "g1", "elapsed_s": 120,
        "home_score": 42, "away_score": 40, "seconds_remaining": 2760,
        "period": 4, "is_overtime": 0, "output_side": "home",
        "p_home": 0.65, "p_away": 0.35,
    }
    state.update(changes)
    return state


def test_trace_catches_polarity_and_overtime_clock_plants() -> None:
    assert trace_state(_state())["status"] == "PASS"
    polarity = trace_state(_state(output_side="away"))
    assert polarity["status"] == "FAIL" and polarity["home_polarity"] == "FAIL"
    overtime = trace_state(_state(period=5, is_overtime=0, seconds_remaining=-1))
    assert overtime["status"] == "FAIL"
    assert overtime["overtime"] == "FAIL" and overtime["clock"] == "FAIL"


def test_boundary_selection_spans_the_ordered_index_not_a_head_slice() -> None:
    n = 200
    rows = []
    for i in range(n):
        home, away, period, overtime = 10, 8, 4, 0
        if i == 60:
            home, away = 5, 5  # tied
        if i == 120:
            home, away = 40, 10  # |margin| >= 15
        if i == 150:
            period, overtime = 5, 1  # overtime
        venue = "ARENA_A" if i < 100 else "ARENA_B"
        rows.append({
            "state_key": f"g{i}:0", "game_id": f"g{i}", "elapsed_s": i,
            "timestamp_utc": f"{i:04d}", "home_score": home, "away_score": away,
            "period": period, "is_overtime": overtime, "venue": venue,
        })
    states, ranks, report = select_boundary_states(rows, n=30)
    assert len(states) == 30 and len(set(ranks)) == 30
    assert max(ranks) >= 0.5 * n
    distinct_buckets = {kind for kind, (_, picked) in report.items() if picked > 0}
    assert len(distinct_buckets) >= 5


def test_round_robin_draws_from_every_dense_bucket_each_pass() -> None:
    """A dense tied+margin15 span must not starve later buckets (b7 gap): 20 overtime
    rows and 2 venues still each get picked, unlike the old sequential-exhaustion fill."""
    rows = []
    for i in range(200):
        if i < 100:
            home, away, venue = 10, 10, "ARENA_A"  # dense tied bucket
        elif i < 180:
            home, away, venue = 40, 5, "ARENA_A"  # dense |margin| >= 15 bucket
        else:
            home, away, venue = 10, 8, "ARENA_B"  # 20 overtime rows
        period, overtime = (5, 1) if i >= 180 else (4, 0)
        rows.append({
            "state_key": f"g{i}:0", "game_id": f"g{i}", "elapsed_s": i,
            "timestamp_utc": f"{i:04d}", "home_score": home, "away_score": away,
            "period": period, "is_overtime": overtime, "venue": venue,
        })
    _, _, report = select_boundary_states(rows, n=30)
    for kind in CRITERIA:
        assert report[kind][1] >= 1, f"{kind} bucket starved: {report}"


def test_boundary_states_are_the_true_min_max_ts_rows() -> None:
    """The primary schema's timestamp lives in ``ts`` (no timestamp/timestamp_utc column);
    game_id is deliberately reverse-sorted so a missing ``ts`` alias would pick the wrong
    earliest/latest state."""
    rows = [{
        "state_key": f"g{39 - i:02d}:{i}", "game_id": f"g{39 - i:02d}", "elapsed_s": i,
        "ts": str(2000 + i), "home_score": 10, "away_score": 8,
    } for i in range(40)]
    states, ranks, _ = select_boundary_states(rows, n=30)
    assert states[0]["ts"] == "2000" and ranks[0] == 0
    assert states[1]["ts"] == "2039" and ranks[1] == 39


def test_ablation_fit_and_paired_brier_delta_are_pinned() -> None:
    rows = []
    for probability, outcome in ((0.2, 0), (0.4, 0), (0.6, 1), (0.8, 1)):
        rows.extend({"features": {"p_sim": probability, "p_m0": probability}, "outcome": outcome}
                    for _ in range(3))
    beta = _fit(rows, use_m0=False)
    assert beta == pytest.approx([0.000000, 17.804701], abs=1e-6)
    archived = [
        {"cluster_id": "g1", "loss_null": 0.25, "loss_temperature_intercept": 0.04},
        {"cluster_id": "g2", "loss_null": 0.25, "loss_temperature_intercept": 0.09},
        {"cluster_id": "g3", "loss_null": 0.25, "loss_temperature_intercept": 0.16},
        {"cluster_id": "g4", "loss_null": 0.25, "loss_temperature_intercept": 0.25},
    ]
    delta = np.mean([row["loss_null"] - row["loss_temperature_intercept"] for row in archived])
    assert delta == pytest.approx(0.115)
    assert paired_bootstrap(archived, "temperature_intercept", draws=200, seed=7) == pytest.approx((0.0225, 0.1850))
    assert brier([0.2, 0.8], [0.0, 1.0]) == pytest.approx(0.04)


def test_preregistration_seal_normalizes_crlf_without_git() -> None:
    path = Path("docs/evidence/harness/S322_sim_diagnostics_2026-09-08_preregistration.md")
    body, seal = path.read_bytes().replace(b"\r\n", b"\n").split(b"SEAL sha256 ", 1)
    assert hashlib.sha256(body).hexdigest() == seal.decode("ascii").strip()
