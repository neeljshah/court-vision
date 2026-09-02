"""G88 regression coverage for modal-stride-adjacent jump maxima."""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.tracking_harness import SPORTS, evaluate


def _game() -> pd.DataFrame:
    rows = []
    for frame in range(100):
        for track_id in range(10):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": 10.0 + 5.0 * track_id + 0.02 * frame, "y": 25.0,
                         "coordinate_space": "court_feet"})
        rows.append({"frame": frame, "track_id": 99, "cls": "ball", "x": 47.0,
                     "y": 25.0, "coordinate_space": "court_feet"})
    return pd.DataFrame(rows)


def test_g88_uses_modal_stride_adjacent_max_and_preserves_the_basketball_bar() -> None:
    teleport = _game()
    teleport.loc[(teleport["cls"] == "player") & (teleport["track_id"] == 0)
                 & (teleport["frame"] == 50), "x"] = 50.0
    report = evaluate(teleport, "basketball")

    assert SPORTS["basketball"]["jump_p95_max"] == SPORTS["basketball"]["jump_max_max"] == 6.0
    assert report.jump_p95 == 0.02
    assert report.jump_max == 39.02
    assert report.jump_max_modal_stride_frames == 1
    assert not report.passed
    assert "jump_max 39.02 > 6.00" in report.failures

    reappearance = _game()
    keep = ~((reappearance["cls"] == "player") & (reappearance["track_id"] == 0)
             & reappearance["frame"].between(31, 97))
    reappearance = reappearance.loc[keep].copy()
    reappearance.loc[(reappearance["cls"] == "player") & (reappearance["track_id"] == 0)
                     & reappearance["frame"].isin([98, 99]), "x"] = [50.0, 50.02]
    report = evaluate(reappearance, "basketball")

    assert report.passed, report.failures
    assert report.jump_max == 0.02
    assert report.jump_max_modal_stride_frames == 1

    ambiguous_rows = []
    for frame in range(40):
        ambiguous_rows.append({"frame": frame, "track_id": 99, "cls": "ball", "x": 47.0,
                               "y": 25.0, "coordinate_space": "court_feet"})
    for track_id in range(10):
        for frame in (0, 2, 5, 7, 10, 12, 15):
            ambiguous_rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                                   "x": 10.0 + track_id + frame * 0.02, "y": 25.0,
                                   "coordinate_space": "court_feet"})
    ambiguous = evaluate(pd.DataFrame(ambiguous_rows), "basketball")

    assert ambiguous.jump_max is None
    assert ambiguous.jump_max_modal_stride_frames is None
    assert "jump_max unmeasurable: no unique positive modal frame stride" in ambiguous.failures
