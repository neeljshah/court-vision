"""Per-file test for knowledge.validate_research_wave1. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/knowledge/test_validate_research_wave1.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.knowledge import validate_research_wave1 as vrw


def test_verdict_rule_uses_per_hypothesis_min_effect():
    assert vrw._verdict(0.001, 0.10, "compassionate_umpire_count_zone") == "CONFIRMED_LOCAL"
    assert vrw._verdict(0.5, 0.10, "compassionate_umpire_count_zone") == "NULL_LOCAL"
    assert vrw._verdict(0.001, 0.01, "compassionate_umpire_count_zone") == "NULL_LOCAL"  # below 0.05 bar
    assert vrw._verdict(None, 0.10, "same_type_repeat_whiff") == "NOT_TESTABLE"


def test_compassionate_umpire_direction_on_synthetic_pitcher_vs_hitter_counts():
    """Pitcher's counts (0-2/1-2) get far fewer called strikes than hitter's
    counts (3-0/3-1) -- synthetic frame with that gap baked in should CONFIRM."""
    rng = np.random.default_rng(1)
    rows = []
    for i in range(300):
        rows.append({"zone": 12, "description": "called_strike" if rng.random() < 0.05 else "ball",
                     "balls": 0, "strikes": 2})
    for i in range(300):
        rows.append({"zone": 12, "description": "called_strike" if rng.random() < 0.35 else "ball",
                     "balls": 3, "strikes": 0})
    df = pd.DataFrame(rows)
    r = vrw.compassionate_umpire_count_zone(df, "h1")
    assert r["verdict"] == "CONFIRMED_LOCAL"
    assert r["effect"] < 0  # pitcher's-count rate lower than hitter's-count rate


def test_of_alignment_premise_fix_uses_strategic_only_no_shaded_value():
    fake = pd.DataFrame({
        "bb_type": ["fly_ball"] * 20,
        "events": (["double"] * 6 + ["field_out"] * 14),
        "of_fielding_alignment": (["Strategic"] * 10 + ["Standard"] * 10),
    })
    r = vrw.of_alignment_xbh_suppression(fake, "h1")
    assert r["n"] == 20
    assert "no 'Shaded' value exists" in r["note"]


def test_same_type_repeat_whiff_computes_prior_pitch_type_within_pa():
    df = pd.DataFrame({
        "game_pk": [1, 1, 1, 2, 2],
        "at_bat_number": [1, 1, 1, 1, 1],
        "pitch_number": [1, 2, 3, 1, 2],
        "pitch_type": ["FF", "FF", "SL", "SL", "CH"],
        "description": ["ball", "swinging_strike", "foul", "ball", "swinging_strike"],
    })
    r = vrw.same_type_repeat_whiff(df, "h1")
    # pitch1/pitch4 have no prior pitch (dropped); pitch2 (FF after FF, same, whiff),
    # pitch3 (SL after FF, diff, foul) and pitch5 (CH after SL, diff, whiff) remain -> n=3
    assert r["n"] == 3


def test_run_writes_nine_edge_free_rows_three_checks_x_h1_h2_combined(monkeypatch):
    rng = np.random.default_rng(2)
    n = 400
    dates = pd.to_datetime("2025-04-01") + pd.to_timedelta(rng.integers(0, 150, n), unit="D")
    fake = pd.DataFrame({
        "game_date": dates, "game_pk": np.arange(n), "at_bat_number": [1] * n,
        "pitch_number": [1] * n, "zone": [12] * n, "balls": [0] * n, "strikes": [2] * n,
        "description": rng.choice(["ball", "called_strike"], n),
        "bb_type": ["fly_ball"] * n, "events": ["field_out"] * n,
        "of_fielding_alignment": ["Standard"] * n, "pitch_type": ["FF"] * n,
    })
    written = []
    monkeypatch.setattr(vrw, "append_jsonl_atomic", lambda path, row: written.append(row))
    monkeypatch.setattr(vrw, "load_season", lambda season=2025: fake)

    rows = vrw.run()
    assert len(rows) == 9  # 3 checks x (h1, h2, combined)
    assert len(written) == 9
    assert all(r["edge_claimed"] is False and r["sport"] == "mlb" for r in rows)
    combined = [r for r in rows if r["hypothesis"].endswith("__combined")]
    assert len(combined) == 3
    assert all(c["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL", "PROVISIONAL", "NOT_TESTABLE"} for c in combined)
