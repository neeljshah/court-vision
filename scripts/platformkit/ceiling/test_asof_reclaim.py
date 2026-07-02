"""Per-file test for the autonomous asof reclaim sweep + daemon.

Acceptance criteria
-------------------
1. _normalize:
   a. Flattens the eval {real,planted_null,truncation} into one verdict row with
      brier_base/brier_cand/dm_p/feat_weight and the control booleans.
   b. A SHIP whose planted-null does NOT collapse is downgraded to SHIP_REVIEW.
   c. A SHIP whose truncation flips is downgraded to SHIP_REVIEW.
   d. No $ / ROI / edge field anywhere in the row.
2. sweep: isolates a failing candidate (records ERROR, keeps going) -- one bad
   gate never kills the run.
3. daemon.run: honors should_stop / max_ticks and never raises out of a failing
   sweep (the loop survives a raising sweep_fn).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/ceiling/test_asof_reclaim.py -q
"""
from __future__ import annotations

from scripts.platformkit.ceiling import asof_reclaim_sweep as S
from scripts.platformkit.ceiling import asof_reclaim_daemon as D


def _res(verdict, null_v="REJECT", trunc_v=None):
    trunc_v = verdict if trunc_v is None else trunc_v
    return {
        "feature": "x", "n_rows": 100, "cov_total": 50, "cov_pct": 50.0,
        "real": {"verdict": verdict, "n_cov_test": 30, "brier_base": 0.20,
                 "brier_cand": 0.19, "brier_delta": 0.01, "dm_p": 0.01,
                 "feat_weight": 0.3},
        "planted_null": {"verdict": null_v},
        "truncation": {"verdict": trunc_v},
    }


def test_normalize_shape_and_no_dollar():
    spec = S.GateSpec("nba", "x", lambda: _res("REJECT"))
    row = S._normalize(spec, _res("REJECT"))
    for k in ("sport", "signal", "verdict", "brier_base", "brier_cand",
              "brier_delta", "dm_p", "feat_weight", "null_collapses",
              "truncation_invariant"):
        assert k in row
    assert row["verdict"] == "REJECT"
    banned = {"roi", "pnl", "p_l", "edge", "profit", "dollars", "units"}
    assert not (banned & {k.lower() for k in row})


def test_ship_downgraded_when_null_not_collapse():
    spec = S.GateSpec("nba", "x", lambda: None)
    row = S._normalize(spec, _res("SHIP", null_v="SHIP"))
    assert row["verdict"] == "SHIP_REVIEW"


def test_ship_downgraded_when_truncation_flips():
    spec = S.GateSpec("nba", "x", lambda: None)
    row = S._normalize(spec, _res("SHIP", null_v="REJECT", trunc_v="REJECT"))
    assert row["verdict"] == "SHIP_REVIEW"


def test_clean_ship_survives_both_controls():
    spec = S.GateSpec("nba", "x", lambda: None)
    row = S._normalize(spec, _res("SHIP", null_v="REJECT", trunc_v="SHIP"))
    assert row["verdict"] == "SHIP"


def test_sweep_isolates_failing_candidate(monkeypatch):
    def _boom():
        raise RuntimeError("gate blew up")

    good = S.GateSpec("nba", "ok", lambda: _res("REJECT"))
    bad = S.GateSpec("mlb", "boom", _boom)
    monkeypatch.setattr(S, "registry", lambda: [good, bad])
    rows = S.sweep(log_ledger=False, write_scoreboard=False)
    verds = {r["signal"]: r["verdict"] for r in rows}
    assert verds["ok"] == "REJECT"
    assert verds["boom"] == "ERROR"          # isolated, did not kill the sweep


def test_daemon_respects_max_ticks_and_survives_raise():
    calls = {"n": 0}

    def _raising_sweep():
        calls["n"] += 1
        raise ValueError("sweep failed")

    ticks = D.run(sweep_fn=_raising_sweep, sleep=lambda s: None, max_ticks=3)
    assert ticks == 3                         # survived 3 raising sweeps
    assert calls["n"] == 3


def test_daemon_should_stop_breaks_first():
    ran = {"n": 0}

    def _sweep():
        ran["n"] += 1
        return []

    ticks = D.run(sweep_fn=_sweep, sleep=lambda s: None, should_stop=lambda: True)
    assert ticks == 0
    assert ran["n"] == 0
