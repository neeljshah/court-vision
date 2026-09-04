"""Focused construct and archived-differential checks for S281."""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.ingame import s281_ingame_momentum_microstructure as s281


def test_strictly_prior_momentum_and_archived_brier() -> None:
    prior = pd.DataFrame({"game_id": ["g", "g", "g", "g", "g"], "ts": [0, 30, 60, 90, 211], "score_home": [0, 3, 7, 7, 7], "score_away": [0, 0, 0, 0, 0]})
    planted = pd.concat([prior, pd.DataFrame({"game_id": ["g"], "ts": [270], "score_home": [9], "score_away": [0]})], ignore_index=True)
    original, changed = s281.add_momentum(prior), s281.add_momentum(planted)
    assert original.loc[4, ["run_120s", "run_just_ended"]].equals(changed.loc[4, ["run_120s", "run_just_ended"]])
    assert original["run_120s"].tolist() == [0.0, 0.0, 3.0, 7.0, 0.0]
    assert original["run_just_ended"].tolist() == [0, 0, 0, 0, 1]
    s281.verify_preregistration()
    paired = pd.read_csv(s281.EVIDENCE / (s281.STEM + "_state_differentials.csv"))
    summary = json.loads((s281.EVIDENCE / (s281.STEM + "_summary.json")).read_text(encoding="ascii"))
    pooled = summary["metrics"]["pooled"]
    assert abs(paired["loss_recal_null"].mean() - pooled["recal_null_brier"]) < 1e-12
    assert abs(paired["loss_recal_null_plus_momentum"].mean() - pooled["recal_null_plus_momentum_brier"]) < 1e-12
