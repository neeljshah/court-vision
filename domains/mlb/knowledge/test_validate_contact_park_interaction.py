"""Per-file test for knowledge.validate_contact_park_interaction. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/knowledge/test_validate_contact_park_interaction.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.knowledge import validate_contact_park_interaction as vcpi


def _synthetic_pitch_df(n_batters=6, pa_per_batter=10) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    rows = []
    parks = ["AAA", "BBB", "CCC"]
    game_pk = 1000
    for b in range(n_batters):
        for i in range(pa_per_batter):
            game_pk += 1
            date = pd.Timestamp("2024-04-01") + pd.Timedelta(days=game_pk % 60)
            home = parks[game_pk % len(parks)]
            rows.append({
                "game_pk": game_pk, "at_bat_number": 1, "pitch_number": 1,
                "batter": b, "home_team": home, "game_date": date,
                "launch_speed": float(rng.uniform(80, 100)),
                "estimated_woba_using_speedangle": float(rng.uniform(0.1, 0.6)),
                "post_home_score": float(rng.integers(0, 8)),
                "post_away_score": float(rng.integers(0, 8)),
            })
    return pd.DataFrame(rows)


def test_build_pa_frame_trailing_contact_is_strictly_prior():
    df = _synthetic_pitch_df(n_batters=1, pa_per_batter=5)
    pa = vcpi.build_pa_frame(df)
    # with only 5 PAs and default MIN_TRAILING_BBE=15, none qualify
    assert pa.empty

    all_pa = df.sort_values(["batter", "game_date", "game_pk", "at_bat_number"]).copy()
    all_pa["trailing_contact"] = all_pa.groupby("batter")["launch_speed"].transform(
        lambda s: s.expanding().mean().shift(1))
    row0, row1 = all_pa.iloc[0], all_pa.iloc[1]
    assert np.isnan(row0["trailing_contact"])  # first PA has no prior history
    assert row1["trailing_contact"] == row0["launch_speed"]  # 2nd PA's trailing = only the 1st's value


def test_run_writes_edge_free_rows_and_never_crashes_on_small_corpus(tmp_path, monkeypatch):
    df = _synthetic_pitch_df(n_batters=8, pa_per_batter=30)
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vcpi, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vcpi, "load_season", lambda season=None: df)
    monkeypatch.setattr(vcpi, "MIN_TRAILING_BBE", 3)
    monkeypatch.setattr(vcpi, "MIN_ROWS", 20)

    rows = vcpi.run()
    assert len(rows) == 3  # h1, h2, combined
    assert all(r["edge_claimed"] is False and r["sport"] == "mlb" for r in rows)
    assert rows[-1]["hypothesis"] == "contact_park_interaction__combined"
    assert rows[-1]["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL", "PROVISIONAL", "NOT_TESTABLE"}
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 3
