"""Focused S328 runner rails; no parquet replay is invoked."""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.ingame import s328_run_replay as runner


def test_full_precision_null_coefficients_match_pinned_s310_rows() -> None:
    """The frozen tuple reproduces two S310-landed 2025-26 probabilities."""
    pinned = (
        ("401812483", 1759596905, 0.125, 0.1414996181158637),
        ("401812716", 1760484844, 0.7150000000000001, 0.7075318603520642),
    )
    lookup = {(game_id, ts): raw for game_id, ts, raw, _expected in pinned}
    arm = runner.make_n_arm(lookup)
    for game_id, ts, raw, expected in pinned:
        frame = pd.DataFrame({"game_id": [game_id], "ts": [ts], "market_prob": [raw]})
        state = {"game_id": game_id, "ts": ts, "state_ts": "2025-10-04T16:55:05+00:00"}
        assert abs(arm(frame, state, None) - expected) < 1e-9


def test_twenty_state_survival_routes_each_arm_through_cpcv(monkeypatch) -> None:
    """Survival uses the shared evaluator instead of direct per-row scoring."""
    records = []
    outcomes = {}
    for index in range(20):
        game_id, ts = "g%02d" % index, 1735689600 + index * 86400
        outcomes[game_id] = index % 2
        for arm, probability in (("N", 0.30 + index / 100.0),
                                 ("S320_SUBSTITUTE", 0.35 + index / 100.0)):
            records.append({"state_id": index, "game_id": game_id, "state_ts_s": ts,
                            "delay_seconds": 0, "arm": arm,
                            "p_delay_probability": probability})
    calls = []
    shared = runner.cpcv_evaluate

    def observed(*args, **kwargs):
        calls.append(kwargs)
        return shared(*args, **kwargs)

    monkeypatch.setattr(runner, "cpcv_evaluate", observed)
    table = runner.survival_table(pd.DataFrame(records), outcomes)
    assert len(calls) == 2
    assert all(call["embargo_days"] == 1 for call in calls)
    assert table.loc[0, "n_states"] == 20
    assert table.loc[0, "n_cpcv_records_count"] == 20
