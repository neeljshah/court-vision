"""S17 CONSTRUCT test: 3 enumerated decay-monitor cases, synthetic + seeded.

Denominator = 3 (thin / drifted / stable). No sampling, no external corpus.
"""
from datetime import datetime, timedelta

from scripts.platformkit.eval_gate.decay_monitors import (
    ALARM, INSUFFICIENT, OK, monitor_all,
)

NOW = "2026-09-03T00:00:00"
_NOW_DT = datetime.fromisoformat(NOW)
PROBS = [0.25, 0.40, 0.55, 0.70, 0.85, 0.35, 0.60, 0.75]
OUTCOMES = [0, 0, 1, 1, 1, 0, 1, 1]
PHASES = ["Q1", "Q2", "Q3", "Q4"]


def _row(i, days_ago, phase, gap, game_id):
    """One settled row. `gap` plants the |prob - p_close| distance directly."""
    prob = PROBS[i % 8]
    return {
        "ts": (_NOW_DT - timedelta(days=days_ago)).isoformat(),
        "prob": prob,
        "outcome": OUTCOMES[i % 8],
        "p_close": round(prob + gap, 6),
        "game_phase": phase,
        "month": "01",          # pinned so month never differs between windows
        "game_id": game_id,
    }


def _window(n, start_days_ago, end_days_ago, phase_fn, gap_fn, tag):
    """n rows spread evenly over [start_days_ago, end_days_ago), one game each."""
    step = (start_days_ago - end_days_ago) / n
    return [
        _row(i, start_days_ago - i * step, phase_fn(i), gap_fn(start_days_ago - i * step),
             "%s-g%d" % (tag, i))
        for i in range(n)
    ]


def test_thin_window_all_insufficient():
    """Case 1: 9 games x 10 rows, loss constant within game -> rho 1, n_eff 9."""
    rows = []
    for g in range(9):
        for t in range(10):
            r = _row(g, 3.0 + 0.01 * t, "Q1", 0.08, "g%d" % g)
            rows.append(r)          # prob/outcome fixed per game -> zero within-game variance
    result = monitor_all(rows, NOW, fit_window_rows=[])
    assert set(result) == {"calibration_decay", "crowding", "regime_drift"}
    assert [m.status for m in result.values()] == [INSUFFICIENT] * 3
    n_eff = result["crowding"].n_eff
    assert 8.0 <= n_eff <= 10.0, n_eff


def test_drifted_window_crowding_and_regime_alarm():
    """Case 2: trailing gap collapses to 0.02 vs first-30d 0.10; phases shift Q1 -> Q4."""
    fit = _window(240, 180, 90, lambda i: "Q1" if i % 10 < 7 else "Q4",
                  lambda d: 0.10, "fit")
    mon = _window(240, 88, 0, lambda i: "Q1" if i % 10 < 2 else "Q4",
                  lambda d: 0.02 if d < 30 else 0.10, "mon")
    result = monitor_all(mon, NOW, fit_window_rows=fit)
    assert result["crowding"].status == ALARM, result["crowding"]
    assert result["regime_drift"].status == ALARM, result["regime_drift"]
    assert result["crowding"].n_eff >= 30.0
    assert result["regime_drift"].stat < 0.05


def test_stable_window_all_ok():
    """Case 3: identical gap, identical phase mix, identical loss cycle -> no alarm."""
    fit = _window(240, 180, 90, lambda i: PHASES[i % 4], lambda d: 0.08, "fit")
    mon = _window(240, 88, 0, lambda i: PHASES[i % 4], lambda d: 0.08, "mon")
    result = monitor_all(mon, NOW, fit_window_rows=fit)
    assert [m.status for m in result.values()] == [OK] * 3, result
