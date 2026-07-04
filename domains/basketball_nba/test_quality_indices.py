"""Per-file pytest for quality_indices.py / quality_indices_score.py.

Run ONLY as:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_quality_indices.py -q

NEVER run the full suite (freezes the box).
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba.quality_indices import (
    QUALIFY_MIN_FGA,
    QUALIFY_MIN_GAMES,
    SCORER_WEIGHTS,
    SHOOTER_WEIGHTS,
    _parse_struct,
    aggregate_season,
    qualifying_pool,
)
from domains.basketball_nba.quality_indices_score import (
    build_percentile_table,
    percentile_rank,
    run,
    score_index,
)


def test_spec_weights_frozen_shooter():
    """FROZEN per basketball_truth_spec.json -- any drift here is a spec violation."""
    assert SHOOTER_WEIGHTS == {
        "EFFICIENCY": 0.30, "DIFFICULTY": 0.30, "GRAVITY": 0.25, "VOLUME": 0.15,
    }
    assert abs(sum(SHOOTER_WEIGHTS.values()) - 1.0) < 1e-9


def test_spec_weights_frozen_scorer():
    assert SCORER_WEIGHTS == {
        "VOLUME_LOAD": 0.30, "EFFICIENCY": 0.25,
        "CREATION_DIFFICULTY": 0.25, "CONTEXT_ROBUSTNESS": 0.20,
    }
    assert abs(sum(SCORER_WEIGHTS.values()) - 1.0) < 1e-9


def test_qualifying_floors_frozen():
    assert QUALIFY_MIN_GAMES == 20
    assert QUALIFY_MIN_FGA == 200


def test_parse_struct_handles_json_string_and_none():
    assert _parse_struct('{"a": 1}') == {"a": 1}
    assert _parse_struct(None) == {}
    assert _parse_struct(float("nan")) == {}
    assert _parse_struct("not json") == {}
    assert _parse_struct({"already": "dict"}) == {"already": "dict"}


def test_percentile_rank_basic_range_and_order():
    s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
    pct = percentile_rank(s)
    assert pct.iloc[0] == 0.0
    assert pct.iloc[-1] == 1.0
    assert (pct.diff().dropna() > 0).all()


def test_percentile_rank_invert_flips_order():
    s = pd.Series([10.0, 20.0, 30.0])
    pct = percentile_rank(s, invert=True)
    assert pct.iloc[0] == 1.0
    assert pct.iloc[-1] == 0.0


def test_percentile_rank_nan_stays_nan():
    s = pd.Series([10.0, float("nan"), 30.0])
    pct = percentile_rank(s)
    assert pd.isna(pct.iloc[1])
    assert pct.iloc[0] == 0.0
    assert pct.iloc[2] == 1.0


def test_qualifying_pool_applies_floors():
    agg = pd.DataFrame({
        "player_id": [1, 2, 3],
        "player_name": ["A", "B", "C"],
        "games": [20, 19, 25],
        "fga": [200, 500, 199],
    })
    pool = qualifying_pool(agg)
    assert set(pool["player_id"]) == {1}


def test_aggregate_season_derives_rates():
    df = pd.DataFrame({
        "game_id": [1, 2], "date": pd.to_datetime(["2024-11-01", "2024-11-02"]),
        "season": ["2024-25", "2024-25"], "player_id": [1, 1], "player_name": ["A", "A"],
        "fgm": [5, 5], "fga": [10, 10], "fg3m": [2, 2], "fg3a": [4, 4],
        "ftm": [2, 2], "fta": [2, 2], "pts": [14, 14],
    })
    agg = aggregate_season(df, season="2024-25")
    row = agg.iloc[0]
    assert row["games"] == 2
    assert row["fga"] == 20
    assert abs(row["efg_pct"] - ((10 + 0.5 * 4) / 20)) < 1e-9


def test_score_index_pillar_dropout_renormalizes_and_reports_coverage():
    """If a whole pillar is missing for a player, remaining weights renormalize
    and coverage < 1.0 is reported (spec Section 2.5) -- never silently
    dropped or presented as full-confidence."""
    t = pd.DataFrame({
        "player_id": [1, 2],
        "player_name": ["A", "B"],
        "games": [40, 40],
        "naive_comp": [0.6, 0.6],
    })
    pct = pd.DataFrame({
        "ts_pct": [1.0, 1.0], "efg_pct": [1.0, 1.0], "shot_quality_ts": [1.0, 1.0],
        "pullup_combined_freq": [1.0, float("nan")], "pullup_pnr_ppp": [1.0, float("nan")],
        "late_clock_shots_pg": [1.0, float("nan")], "unassisted_share_3pm": [1.0, float("nan")],
        "off_dribble_3_proxy": [1.0, float("nan")],
        "gravity_score": [1.0, 1.0], "cs_gravity_efg": [1.0, 1.0], "spotup_ppp": [1.0, 1.0],
        "fg3a_per_game": [1.0, 1.0], "fga_per_game": [1.0, 1.0],
    })
    out = score_index(t, pct, "shooter")
    row_full = out[out["player_id"] == 1].iloc[0]
    row_missing_difficulty = out[out["player_id"] == 2].iloc[0]
    assert row_full["coverage"] == 1.0
    assert row_missing_difficulty["coverage"] == pytest.approx(1.0 - 0.30, abs=1e-9)
    # both scores should still be ~1.0 (all available pillars are perfect) since
    # renormalization divides by available weight, not total weight
    assert row_full["shooter_quality_v1"] == pytest.approx(1.0, abs=1e-6)
    assert row_missing_difficulty["shooter_quality_v1"] == pytest.approx(1.0, abs=1e-6)


def test_run_on_real_disk_data_smoke():
    """Integration smoke test against the real on-disk 2024-25 parquets.
    Verifies the documented 329-qualifier population and that both indices
    produce a full-coverage top-10 (spec's own live-verified inventory)."""
    res = run()
    assert len(res.factor_table) == 329
    assert len(res.shooter) == 329
    assert len(res.scorer) == 329
    assert res.shooter["shooter_quality_v1"].notna().sum() > 300
    assert res.scorer["scorer_quality_v1"].notna().sum() > 300
    # face-validity diagnostic values (reported, not asserted as "correct"):
    # the spec's own worked example (Section 1): Ellis's naive_comp (0.6882)
    # beats Curry's (0.6517) even though Curry shoots on ~2.7x the volume
    # against tougher defense -- verify that documented inversion is real
    # on-disk, not a spec typo, before trusting the gate that is meant to fix it.
    curry = res.shooter[res.shooter["player_name"] == "Stephen Curry"].iloc[0]
    ellis = res.shooter[res.shooter["player_name"] == "Keon Ellis"].iloc[0]
    assert ellis["naive_comp"] > curry["naive_comp"]
    assert ellis["naive_comp"] == pytest.approx(0.6882, abs=1e-3)
    assert curry["naive_comp"] == pytest.approx(0.6517, abs=1e-3)
    # and shooter_quality_v1 (DECLARED weights, not tuned) puts Curry ahead of
    # Ellis -- reported here as the documented outcome, not a target that was
    # fit for; see quality_validity_gate for whether this is PREDICTIVE.
    assert curry["shooter_quality_v1"] > ellis["shooter_quality_v1"]
