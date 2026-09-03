"""S206 focused tests. Run only this file."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.foundry import ingame_screen_wnba as S


def test_s206_loader_premise_and_asof_guard_hold_on_the_one_joined_store():
    rows = S.load_rows()
    facts = S.premise(rows)
    assert (facts["joined_ticks"], facts["joined_games"]) == (18650, 85)
    assert (facts["inplay_denominator"], facts["in_span_ticks"]) == (186736, 19456)
    assert (facts["age_median_s"], facts["age_p90_s"], facts["age_above_300"]) == (15.0, 132.0, 0)
    assert facts["games_in_span_at_least_100"] == 84
    assert facts["settled_priced_events"] == facts["inplay_priced_events"] == 98
    assert len(S.assert_tick_asof(S.causal_source(rows), S.build_features, probes=8)) == 8


def test_s206_stern_term_is_current_state_only_and_scoring_archives_recomputable_losses(tmp_path):
    rows = S.load_rows()
    source = S.causal_source(rows.iloc[:3].reset_index(drop=True))
    source.loc[:, ["period", "game_clock_s", "margin"]] = [[1.0, 600.0, 10.0], [4.0, 1.0, -2.0], [5.0, 300.0, 3.0]]
    feature = S.build_features(source)[S.FEATURE].to_numpy()
    assert np.allclose(feature, [10.0 / np.sqrt(2400.0), -2.0, 3.0 / np.sqrt(300.0)])
    report, scored = S.screen(rows)
    assert report["n_scored_games"] >= 30 and report["n_scored_ticks"] == len(scored)
    assert report["unscored_joined_ticks"] + report["n_scored_ticks"] == len(rows)
    assert report["bar"] == 0.004 and len(report["reliability"]["market"]) == 10
    csv_path, json_path = S.write_artifacts(report, scored, out=tmp_path)
    archived = pd.read_csv(csv_path)
    assert json_path.exists() and len(archived) == len(scored)
    for name in ("market", "null", "candidate"):
        assert np.isclose(((archived["p_" + name] - archived["y"]) ** 2).mean()
                          if name != "market" else archived["loss_market"].mean(),
                          report["brier_" + name])
    assert np.isclose(archived["delta_null_minus_candidate"].mean(), report["improvement_vs_null"])
    assert set(Path(csv_path).read_text(encoding="ascii").splitlines()[0].split(",")) >= {
        "game", "timestamp", "loss_null", "loss_candidate", "loss_market"}
