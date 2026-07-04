"""Per-file test for domains.mlb.sp_velo_materialize.

Covers: (a) the date+team-pair game join incl. ambiguous-doubleheader drop, (b) the
AS-OF velo_decline math (trailing-last-15 minus first-15, NaN before window fills,
never sees a future pitch), (c) starter isolation (a reliever's pitches never enter the
proxy), (d) the honest BLOCKED path when release_speed coverage is too thin, and
(e) a real-corpus smoke check (skips cleanly if data/ is absent, e.g. fresh clone).
Run ONLY this file: python -m pytest domains/mlb/test_sp_velo_materialize.py -q
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from domains.mlb import sp_velo_materialize as M


# --------------------------------------------------------------------------- fixtures
def _espn_df(game_id, date, home, away, n_pitches_per_side=20):
    rows = []
    idx = 0
    for label_prefix in ("top1", "bottom1"):
        for i in range(n_pitches_per_side):
            rows.append({
                "game_id": game_id, "date": date, "home_team": home, "away_team": away,
                "asof_idx": idx, "half_inning_label": label_prefix,
                "sp_pitch_count_prior": i, "state_diff": 0.0 + 0.05 * i,
                "frac_elapsed": (idx + 1) / (2 * n_pitches_per_side), "p0": 0.5,
                "outcome": 1,
            })
            idx += 1
    return pd.DataFrame(rows)


def _statcast_df(game_pk, date, home, away, starter_home, starter_away,
                  n_pitches=20, velos=None):
    rows = []
    for topbot, sp in (("Top", starter_home), ("Bottom", starter_away)):
        vs = velos or [95.0 - 0.1 * i for i in range(n_pitches)]
        for i, v in enumerate(vs):
            rows.append({
                "game_pk": game_pk, "game_date": date, "home_team": home, "away_team": away,
                "inning": 1, "inning_topbot": topbot, "at_bat_number": i // 4 + 1,
                "pitch_number": i % 4 + 1, "pitcher": sp, "release_speed": v,
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- (a) join
def test_match_games_resolves_simple_pair():
    espn = _espn_df("2022-04-07-ARI-SDG-7", "2022-04-07", "ARI", "SDG")
    sc = _statcast_df(661362, "2022-04-07", "AZ", "SD", 100, 200)
    m = M.match_games(espn, sc)
    assert m == {"2022-04-07-ARI-SDG-7": 661362}


def test_match_games_drops_ambiguous_doubleheader():
    e1 = _espn_df("2022-04-07-ARI-SDG-1", "2022-04-07", "ARI", "SDG")
    e2 = _espn_df("2022-04-07-ARI-SDG-2", "2022-04-07", "ARI", "SDG")
    espn = pd.concat([e1, e2], ignore_index=True)
    sc = _statcast_df(661362, "2022-04-07", "AZ", "SD", 100, 200)
    m = M.match_games(espn, sc)
    assert m == {}  # 2 espn games match 1 statcast key -> ambiguous, dropped


def test_match_games_no_match_is_empty_not_guessed():
    espn = _espn_df("2022-04-07-ARI-SDG-7", "2022-04-07", "ARI", "SDG")
    sc = _statcast_df(661362, "2022-04-08", "AZ", "SD", 100, 200)  # different date
    assert M.match_games(espn, sc) == {}


# --------------------------------------------------------------------------- (b) velo_decline
def test_velo_decline_nan_before_window_fills():
    velos = [95.0] * 30
    out = M._velo_decline_series(velos, window=15)
    assert all(math.isnan(v) for v in out[:14])
    assert not math.isnan(out[14])


def test_velo_decline_zero_when_flat():
    velos = [95.0] * 30
    out = M._velo_decline_series(velos, window=15)
    assert abs(out[14]) < 1e-9
    assert abs(out[29]) < 1e-9


def test_velo_decline_negative_when_slower_late():
    velos = [95.0] * 15 + [90.0] * 15
    out = M._velo_decline_series(velos, window=15)
    # at i=29, trailing-15 = pitches[15:30] = all 90.0, baseline(first15)=95.0
    # spec formula is trailing - early, so a real velocity DROP is NEGATIVE.
    assert out[29] < -4.9


def test_velo_decline_only_uses_pitches_up_to_i_asof():
    """Changing a LATER pitch's velocity must not change an EARLIER index's value."""
    velos_a = [95.0] * 20 + [70.0] * 5
    velos_b = [95.0] * 20 + [10.0] * 5  # later pitches drastically different
    out_a = M._velo_decline_series(velos_a, window=15)
    out_b = M._velo_decline_series(velos_b, window=15)
    assert out_a[19] == out_b[19]  # index 19 unaffected by pitches 20..24


# --------------------------------------------------------------------------- (c) starter isolation
def test_build_states_uses_only_starter_pitches(tmp_path):
    espn_dir = tmp_path / "espn"
    sc_dir = tmp_path / "statcast"
    espn_dir.mkdir()
    sc_dir.mkdir()
    espn = _espn_df("2022-04-07-ARI-SDG-7", "2022-04-07", "ARI", "SDG", n_pitches_per_side=20)
    espn["season"] = 2022
    espn.to_parquet(espn_dir / "mlb_pitch_states__2022.parquet", index=False)

    # side has starter (id=100) throw 18 pitches then a reliever (id=999) throw 2 more.
    rows = []
    for i in range(18):
        rows.append({"game_pk": 661362, "game_date": "2022-04-07", "home_team": "AZ",
                     "away_team": "SD", "inning": 1, "inning_topbot": "Top",
                     "at_bat_number": i // 4 + 1, "pitch_number": i % 4 + 1,
                     "pitcher": 100, "release_speed": 95.0 - 0.1 * i})
    for i in range(18, 20):
        rows.append({"game_pk": 661362, "game_date": "2022-04-07", "home_team": "AZ",
                     "away_team": "SD", "inning": 1, "inning_topbot": "Top",
                     "at_bat_number": i // 4 + 1, "pitch_number": i % 4 + 1,
                     "pitcher": 999, "release_speed": 60.0})  # reliever, wildly different
    for i in range(20):  # away side, single pitcher throughout
        rows.append({"game_pk": 661362, "game_date": "2022-04-07", "home_team": "AZ",
                     "away_team": "SD", "inning": 1, "inning_topbot": "Bottom",
                     "at_bat_number": i // 4 + 1, "pitch_number": i % 4 + 1,
                     "pitcher": 200, "release_speed": 93.0})
    sc = pd.DataFrame(rows)
    sc.to_parquet(sc_dir / "statcast__2022_overlap.parquet", index=False)

    df, cov = M.build_states(2022, espn_dir=str(espn_dir), statcast_dir=str(sc_dir))
    assert cov["statcast_on_disk"] and cov["espn_on_disk"]
    home_rows = df[df["pitch_side"] == "home"]
    assert set(home_rows["proxy_pitcher"].unique()) == {100}   # never 999 (the reliever)
    assert home_rows["pitch_index"].max() <= 17                # never reaches the reliever's slots


# --------------------------------------------------------------------------- (d) honest BLOCKED
def test_materialize_blocked_when_no_seasons_on_disk(tmp_path):
    res = M.materialize(seasons=(2099,), espn_dir=str(tmp_path), statcast_dir=str(tmp_path))
    assert res["status"] == "BLOCKED"
    assert res["reason"] == "NO_USABLE_SEASON"


def test_materialize_blocked_on_thin_coverage(tmp_path, monkeypatch):
    espn_dir = tmp_path / "espn"
    sc_dir = tmp_path / "statcast"
    espn_dir.mkdir()
    sc_dir.mkdir()
    espn = _espn_df("2022-04-07-ARI-SDG-7", "2022-04-07", "ARI", "SDG", n_pitches_per_side=20)
    espn["season"] = 2022
    espn.to_parquet(espn_dir / "mlb_pitch_states__2022.parquet", index=False)
    # Statcast overlap present but release_speed mostly NaN -> thin coverage.
    sc = _statcast_df(661362, "2022-04-07", "AZ", "SD", 100, 200)
    sc.loc[sc.index[:-2], "release_speed"] = np.nan
    sc.to_parquet(sc_dir / "statcast__2022_overlap.parquet", index=False)
    res = M.materialize(seasons=(2022,), espn_dir=str(espn_dir), statcast_dir=str(sc_dir))
    assert res["status"] == "BLOCKED"
    assert res["reason"] == "RELEASE_SPEED_COVERAGE_TOO_THIN"


# --------------------------------------------------------------------------- (e) real corpus smoke
def test_real_on_disk_corpus_materializes_or_honestly_blocks():
    res = M.materialize()
    assert res["status"] in {"OK", "BLOCKED"}
    if res["status"] == "OK":
        assert res["n_states"] > 0
        assert 0.0 <= res["velo_decline_coverage"] <= 1.0
        df = M.load()
        assert "as_of" in df.columns and "corpus_id" in df.columns
        assert (df["corpus_id"] == M.CORPUS_ID).all()
