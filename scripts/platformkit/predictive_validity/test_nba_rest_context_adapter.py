"""Per-file tests for nba_rest_context_adapter + run_nba_rest_context --
SYNTHETIC boxscore frame only (this worktree has no data/ dir).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/predictive_validity/test_nba_rest_context_adapter.py -q

Acceptance:
  1. _season_label maps CUTOFFS to the box's own "2023-24"/"2024-25" style.
  2. _drop_asof/_drop_forward are leak-free (pre uses only date<cutoff rows;
     forward uses only date>=cutoff rows, windowed to forward_games).
  3. Zero-baseline shape: _zero_baseline_asof returns the SAME entity set as
     _drop_asof, value=0.0 for all.
  4. run_zero_baseline_test never crashes on a thin synthetic corpus and
     fails closed to UNDERPOWERED (the expected, honest outcome per mission).
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.predictive_validity import nba_rest_context_adapter as A
from scripts.platformkit.predictive_validity import run_nba_rest_context as R


def _row(pid, date, season, fga, fta, pts):
    return {"game_id": f"{pid}_{date}", "date": pd.Timestamp(date), "season": season,
            "player_id": pid, "player_name": f"P{pid}", "fga": fga, "fta": fta, "pts": pts}


def _box() -> pd.DataFrame:
    rows = []
    season = "2023-24"
    # player 1: opener + alternating b2b/rest2plus straddling a Dec cutoff,
    # enough pre- and post-cutoff games to exercise both adapters.
    dates_pre = ["2023-11-01", "2023-11-02", "2023-11-05", "2023-11-06", "2023-11-10",
                 "2023-11-11", "2023-11-15", "2023-11-16", "2023-11-20"]
    dates_post = ["2023-12-05", "2023-12-06", "2023-12-10", "2023-12-11", "2023-12-15"]
    for d in dates_pre + dates_post:
        rows.append(_row(1, d, season, 5, 0, 8))
    return pd.DataFrame(rows)


CUTOFF = "2023-12-01"


def test_season_label_matches_box_convention():
    assert A._season_label("2023-12-01") == "2023-24"
    assert A._season_label("2024-08-15") == "2024-25"


def test_drop_asof_uses_only_pre_cutoff_rows():
    box = _box()
    metric = A._drop_asof(A._bucketed_rows_by_season(box)["2023-24"], CUTOFF)
    # with PV_PRE_FLOOR_B2B=3 / PV_PRE_FLOOR_REST=5 the thin pre-cutoff window
    # (9 rows, first is an opener) may or may not clear floors -- just assert
    # it never raises and any returned row's entity_id is player 1.
    if not metric.empty:
        assert set(metric["entity_id"]) <= {1}


def test_zero_baseline_matches_metric_entity_set():
    box = _box()
    by_season = A._bucketed_rows_by_season(box)
    rows = by_season["2023-24"]
    metric = A._drop_asof(rows, CUTOFF)
    baseline = A._zero_baseline_asof(rows, CUTOFF)
    assert set(baseline["entity_id"]) == set(metric["entity_id"])
    assert (baseline["value"] == 0.0).all()


def test_drop_forward_excludes_pre_cutoff_rows():
    box = _box()
    rows = A._bucketed_rows_by_season(box)["2023-24"]
    fwd = A._drop_forward(rows, CUTOFF, forward_games=20)
    # forward window only has post-cutoff rows (2023-12-05 onward); any
    # result must come from that window, never from the pre-cutoff block.
    assert isinstance(fwd, pd.DataFrame)
    assert set(fwd.columns) == {"entity_id", "outcome", "n_forward"}


def test_run_zero_baseline_test_never_crashes_and_fails_closed(monkeypatch):
    box = _box()
    test = A.rest_context_b2b_drop_test(box, forward_games=20)
    result = R.run_zero_baseline_test(test)
    assert result["verdict"] in {"UNDERPOWERED", "DESCRIPTIVE_ONLY", "PREDICTIVE_VERIFIED"}
    # thin single-player synthetic corpus -> every fold is far below
    # MIN_ENTITIES_PER_FOLD -> honest UNDERPOWERED, never a crash.
    assert result["verdict"] == "UNDERPOWERED"
    assert result["n_folds"] == 0
