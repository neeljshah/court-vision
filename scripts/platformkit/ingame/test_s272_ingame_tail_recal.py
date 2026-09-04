"""Focused archive-reconstruction test for S272; run this file only."""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.eval_gate.scoring import ece
from scripts.platformkit.ingame import s272_ingame_tail_recal as s272


def test_s272_prereg_seal_and_later_season_archive_recompute() -> None:
    s272._verify_prereg()
    csv_path = s272.EVIDENCE / (s272.STEM + "_paired_losses.csv")
    summary_path = s272.EVIDENCE / (s272.STEM + "_summary.json")
    assert csv_path.stat().st_size < 200_000_000
    paired = pd.read_csv(csv_path)
    summary = json.loads(summary_path.read_text(encoding="ascii"))
    season = "2025-26"
    all_game = paired[(paired["record_type"] == "all_game") & (paired["season"] == season)]
    tail = paired[(paired["record_type"] == "tail_tick") & (paired["season"] == season)]
    expected = summary["season_metrics"][season]
    for arm in ("candidate", "incumbent"):
        all_brier = all_game["loss_" + arm + "_sum"].sum() / all_game["n_ticks"].sum()
        tail_brier = tail["loss_" + arm].mean()
        tail_ece = ece(tail[arm], tail["outcome_home_win"])
        assert abs(all_brier - expected["all"][arm + "_brier"]) < 1e-12
        assert abs(tail_brier - expected["tail"][arm + "_brier"]) < 1e-12
        assert abs(tail_ece - expected["tail"][arm + "_ece"]) < 1e-12
