"""Acceptance tests for the PBP-only T1-T4, S2 tempo pack."""
import numpy as np
import pandas as pd

from scripts.platformkit.signals.tempo_pbp_asof import (
    MIN_SCORE_STATE_PRIOR_POSSESSIONS,
    OUTPUT_COLUMNS,
    RUNTIME_COLUMNS,
    RUNTIME_TAG,
    build_tempo_pbp_asof,
)


def _rows(count: int, game_id: str = "g1", start_order: int = 1) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": game_id,
                "game_date": "2026-01-01",
                "event_order": start_order + index,
                "team_id": "A",
                "elapsed_seconds": 1800 + index * 20,
                "possession_seconds": 12.0 + index,
                "score_margin": -12.0,
            }
            for index in range(count)
        ]
    )


def test_score_state_never_uses_pooled_fallback_below_minimum():
    features = build_tempo_pbp_asof(_rows(3))
    assert MIN_SCORE_STATE_PRIOR_POSSESSIONS == 5
    assert features["tempo_by_score_state_asof"].isna().all()


def test_in_game_columns_are_truncation_invariant():
    full = pd.concat([_rows(6), _rows(4, "g2")], ignore_index=True)
    truncated = full.iloc[:4].copy()
    at_time = build_tempo_pbp_asof(truncated)
    later = build_tempo_pbp_asof(full).iloc[:4].reset_index(drop=True)
    for column in ("tempo_by_score_state_asof", "garbage_time_exposure_prior_asof"):
        assert np.allclose(at_time[column], later[column], equal_nan=True)


def test_target_row_is_excluded_and_debuts_are_nan():
    rows = pd.concat([_rows(6), _rows(1, "target")], ignore_index=True)
    baseline = build_tempo_pbp_asof(rows)
    extreme = rows.copy()
    extreme.loc[6, "possession_seconds"] = 9_999.0
    changed = build_tempo_pbp_asof(extreme)
    for column in OUTPUT_COLUMNS:
        assert np.allclose(
            [baseline.loc[6, column]], [changed.loc[6, column]], equal_nan=True
        )
        assert pd.isna(baseline.loc[0, column])


def test_runtime_contract_and_expected_feature_values():
    rows = _rows(7)
    rows.loc[6, "elapsed_seconds"] = 2200
    rows.loc[6, "score_margin"] = 22.0
    features = build_tempo_pbp_asof(rows)
    assert RUNTIME_TAG == "RUNTIME"
    assert RUNTIME_COLUMNS == OUTPUT_COLUMNS
    assert features.loc[1, "possession_seconds_p50_asof"] == 12.0
    assert features.loc[6, "garbage_time_exposure_prior_asof"] == 0.0
    assert features.loc[5, "tempo_by_score_state_asof"] > 0.0
