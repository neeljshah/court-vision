"""Per-file test for gate_run_mlb_espn_box.

Honest contract:
  (1) on the REAL sparse on-disk box (~3 weeks) the verdict is INSUFFICIENT_DATA with
      machinery_ready=True -- we NEVER fabricate a REJECT/SHIP on un-gateable data.
  (2) on a SYNTHETIC >=2-season corpus the gateable path RUNS and the PLANTED-NULL noise
      column REJECTS through the identical proven core -> the gate has teeth.
  (3) the base is strictly-prior (leak-free): the first game carries no prior signal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit import gate_run_mlb_espn_box as G
from domains.mlb.asof_espn_box import ASOF_FEATURES


def test_real_disk_data_is_insufficient_not_fabricated():
    res = G.run()
    # only ~300 current-season rows on disk -> honestly un-gateable
    assert res["verdict"] == "INSUFFICIENT_DATA"
    assert res["machinery_ready"] is True
    assert res["n_rows_on_disk"] < res["min_gateable"]
    assert "$" not in str(res)  # NO dollar/edge field anywhere


def _synth_box(n_games: int = 760, n_teams: int = 30, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    strength = {t: rng.normal(0, 0.5) for t in range(n_teams)}
    rows = []
    for i in range(n_games):
        h, a = rng.choice(n_teams, size=2, replace=False)
        lam_h = np.exp(1.4 + strength[h] - strength[a] + 0.06)  # small HFA
        lam_a = np.exp(1.4 + strength[a] - strength[h])
        hs, as_ = int(rng.poisson(lam_h)), int(rng.poisson(lam_a))
        gdate = (pd.Timestamp("2022-04-01") + pd.Timedelta(days=i // 5)).strftime("%Y%m%d")
        row = {"event_id": f"E{i:05d}", "date": gdate,
               "home_abbr": f"T{h:02d}", "away_abbr": f"T{a:02d}",
               "home_score": float(hs), "away_score": float(as_)}
        for f in ASOF_FEATURES:  # box stats are PURE NOISE here -> must reject
            row[f"home_{f}"] = float(rng.integers(0, 12))
            row[f"away_{f}"] = float(rng.integers(0, 12))
        rows.append(row)
    df = pd.DataFrame(rows)
    df["date"] = df["date"].astype(str)
    return df.sort_values("date", kind="mergesort").reset_index(drop=True)


def test_gateable_path_runs_and_planted_null_rejects():
    box = _synth_box()
    res = G.run(box=box, seed=1)
    assert res["verdict"] != "INSUFFICIENT_DATA"      # the gate actually ran
    assert res["null_rejects"] is True                # the noise tripwire fired
    # pure-noise box stats must NOT ship through a trustworthy gate
    assert res["verdict"] in ("REJECT", "INVALID_BASE", "NOT_TESTABLE")
    assert "$" not in str(res)


def test_leakfree_base_first_game_has_no_prior():
    box = _synth_box(n_games=40)
    merged = G.build_corpus(box, seed=0)
    # p_poisson exists and is a valid probability everywhere (prior-only, no NaN leak-fill)
    p = merged["p_poisson"].to_numpy(float)
    assert ((p >= 0.0) & (p <= 1.0)).all()
    # the earliest game's base falls back to the neutral 0.5 (no prior games yet)
    assert abs(float(merged.iloc[0]["p_poisson"]) - 0.5) < 1e-9
