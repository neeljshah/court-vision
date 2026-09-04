"""Per-file checks for the offline S229 interaction screen."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit import s229_matchup_player_vs_defender as s229


def _frame() -> pd.DataFrame:
    rng = np.random.default_rng(229)
    rows = []
    for day in range(50):
        for player in range(8):
            scheme, opponent = rng.normal(), rng.normal()
            residual = 0.2 * scheme - 0.1 * opponent + 0.4 * scheme * opponent + rng.normal(0, 0.1)
            rows.append({"player_id": player, "game_id": "g%03d" % day,
                         "game_date": (pd.Timestamp("2024-01-01") + pd.Timedelta(days=day)).strftime("%Y-%m-%d"), "residual": residual,
                         s229.SCHEME: scheme, s229.OPPONENT: opponent,
                         s229.INTERACTION: scheme * opponent,
                         "null_interaction": rng.normal() * opponent})
    return pd.DataFrame(rows).sort_values(["game_date", "game_id"]).reset_index(drop=True)


def test_only_interaction_distinguishes_candidate_and_null_path(tmp_path, monkeypatch):
    assert s229.CANDIDATE_COLUMNS[:-1] == s229.BASE_COLUMNS
    frame = _frame()
    folds = list(s229.purged_date_folds(frame))
    for _, train, test in folds:
        assert pd.to_datetime(train["game_date"]).max() < pd.to_datetime(test["game_date"]).min() - pd.Timedelta(days=1)
    scored = s229.walk_forward(frame)
    series, result = s229.summarize(scored)
    assert len(series) >= 30
    assert set(["base_prediction", "candidate_prediction", "null_prediction"]).issubset(scored)
    assert result["candidate"]["rmse"] < result["base"]["rmse"]
    assert np.isfinite(result["null"]["rmse"])
    target = frame[["player_id", "game_date", "residual"]].rename(columns={"game_date": "date"})
    target["pred_pts_decomp"] = 10.0
    target["target_pts"] = 10.0 + target.pop("residual")
    target["fold"] = 0
    scheme = frame[["player_id", "game_date", s229.SCHEME]]
    opponent = frame[["player_id", "game_date", s229.OPPONENT]]
    schedule = frame[["player_id", "game_date", "game_id"]]
    null = scheme.copy()
    null[s229.SCHEME] = np.linspace(-1.0, 1.0, len(null))
    paths = {"PTS": tmp_path / "pts.parquet", "DEF": tmp_path / "def.parquet",
             "NULL": tmp_path / "null.parquet", "OPP": tmp_path / "opp.parquet",
             "SCHEDULE": tmp_path / "schedule.parquet"}
    target.to_parquet(paths["PTS"], index=False)
    scheme.to_parquet(paths["DEF"], index=False)
    null.to_parquet(paths["NULL"], index=False)
    opponent.to_parquet(paths["OPP"], index=False)
    schedule.to_parquet(paths["SCHEDULE"], index=False)
    for name, path in paths.items():
        monkeypatch.setattr(s229, name, path)
    loaded, coverage = s229.load_frame(s229.NULL)
    assert coverage["null_rows"] == len(null)
    assert coverage["direct_sidecar_join"] == len(null)
    assert loaded["null_interaction"].notna().all()
