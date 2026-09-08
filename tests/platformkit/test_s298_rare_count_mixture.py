import json
from datetime import datetime

import numpy as np
import pandas as pd
import psutil
import pytest

from scripts.platformkit import s298_rare_count_mixture as route
from scripts.platformkit import s298_pmf_shards


def test_s298_pmfs_seal_and_strict_prior_features() -> None:
    text = route.PREREG.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    assert route._seal(route.PREREG, "S298_PREREG_SEAL_SHA256=") == text.split("S298_PREREG_SEAL_SHA256=", 1)[1].strip()
    supplement_text = route.SUPPLEMENT.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    assert route._seal(route.SUPPLEMENT, "S298_SUPPLEMENT_SEAL_SHA256=") == supplement_text.split("S298_SUPPLEMENT_SEAL_SHA256=", 1)[1].strip()
    for family in route.FAMILIES:
        pmf = route._pmf(np.array([0, 0, 1, 2, 0], dtype=int), family)
        assert np.isfinite(pmf).all()
        assert (pmf >= 0).all()
        assert abs(float(pmf.sum()) - 1.0) <= 1e-12
        assert np.isfinite(float(pmf[-1]))
    frame = pd.DataFrame({"game_id": ["g1"], "player_id": [1], "date": ["2025-01-02"],
                          "team": ["T"], "stl": [0], "blk": [0]})
    state = route._states(frame)[0]
    assert state["outcome_vector"] == (0, 0)
    assert datetime.fromisoformat(state["feature_avail"]["strict_prior_marker"]) < datetime.fromisoformat(state["state_ts"])


def _record(split_id: int, game_id: str) -> dict:
    pmf = route._pmf(np.array([0, 0, 1, 2, 0], dtype=int), "poisson")
    scores = {}
    for stat in route.STATS:
        for family in route.FAMILIES:
            prefix = stat + "_" + family
            scores.update({prefix + "_log": 0.5, prefix + "_rps": 0.25,
                           prefix + "_zero_abs_error": 0.1, prefix + "_pit": 0.4})
    pmfs = {stat: {family: pmf for family in route.FAMILIES} for stat in route.STATS}
    return {"split_id": split_id, "game_id": game_id, "ts": "2025-01-02T12:00:00",
            "stable_key": game_id + "|1", "n_train": 100, "scores": scores,
            "forecast": {"pmfs": pmfs, "asof_n": 5, "used_player_prior": 1,
                         "inner_selected_family": {stat: "nb2" for stat in route.STATS}}}


def test_s298_secondary_and_per_fold_rail() -> None:
    records = [_record(0, "g{0}".format(index)) for index in range(30)]
    outcomes = {record["stable_key"]: (0, 1) for record in records}
    rows = route._secondary(records, outcomes)
    assert len(rows) == len(route.STATS) * len(route.FAMILIES)
    for row in rows:
        assert row["n_scored_states"] == 30
        for key in ("mean_rps", "zero_reliability_abs_error", "pit_mean", "pit_ks_uniform"):
            assert np.isfinite(row[key])
    folds = route._per_fold(records)
    assert folds == [{"split_id": 0, "n_states": 30, "n_game_clusters": 30, "n_train": 100}]
    try:
        route._per_fold(records[:29])
    except AssertionError as error:
        assert "game clusters" in str(error)
    else:
        raise AssertionError("per-fold cluster rail did not fire below 30")


def test_s298_pmf_shards_stream_reconstruction() -> None:
    if psutil.virtual_memory().available < 1024 ** 3:
        pytest.skip("less than 1 GB RAM available; skipping PMF shard reconstruction")
    digest = s298_pmf_shards.load_pmf_shards()
    assert digest == s298_pmf_shards.CANONICAL_DECOMPRESSED_SHA256
    manifest = s298_pmf_shards.shard_manifest()
    assert manifest["canonical_row_count"] == s298_pmf_shards.CANONICAL_ROW_COUNT
    assert len(manifest["shards"]) == 8
    assert sum(shard["rows"] for shard in manifest["shards"]) == s298_pmf_shards.CANONICAL_ROW_COUNT
    committed = json.loads((route.OUT / ("S298_rare_count_mixture_" + route.DATE + ".json")).read_text(encoding="utf-8"))
    assert s298_pmf_shards.pmf_shard_artifacts()["pmf_shards"] == committed["artifacts"]["pmf_shards"]
