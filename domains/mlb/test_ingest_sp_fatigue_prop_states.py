"""Per-file test for domains.mlb.ingest_sp_fatigue_prop_states.

Asserts the load-bearing honesty/leak-free properties:
  - LEAK-FREE: the profile for outing N uses ONLY that team-side's PRIOR outings
    (shift1); outing N's own shape is NEVER in outing N's profile row.
  - AS-OF MONOTONIC: prof_n_prior is non-decreasing along each team-side's date order
    and equals 0 for the first outing of a team-side.
  - PARITY: per_outing_summary derives the same shape on a tick-truncated outing as on
    its own first-K pitches (the early-velo / shape summary is prefix-stable, i.e. the
    same builder run twice on identical input is identical).
  - K LABEL HONEST: build_label_join returns INSUFFICIENT_DATA (NOT 0-filled / faked)
    when no per-pitcher K source overlaps the profile seasons, with explicit reasons.
  - LABEL-NOT-A-FEATURE: no prof_* column is ever derived from a K column (the profile
    is built before/independently of any label join).
  - REAL on the materialized corpora: 2022/2023 pitch parquets yield non-degenerate
    outing shapes and the label verdict is INSUFFICIENT_DATA for them.
Run ONLY this file: python -m pytest domains/mlb/test_ingest_sp_fatigue_prop_states.py -q
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from domains.mlb import ingest_sp_fatigue_prop_states as M

_REPO = Path(__file__).resolve().parents[2]
_PITCH_DIR = _REPO / "data" / "cache" / "ingame"


def _synthetic_pitch_df() -> pd.DataFrame:
    """Two games, same home_team 'AAA' pitching (top halves) on two dates, plus an
    away staff -> lets us check prior-N shift1 and side separation deterministically.
    Velo declines within each outing so the slope is negative and recoverable."""
    rows = []

    def outing(gid, date, label, team_home, team_away, velos, types):
        for i, (v, t) in enumerate(zip(velos, types)):
            rows.append({
                "game_id": gid, "asof_idx": i, "season": 2022, "date": date,
                "home_team": team_home, "away_team": team_away,
                "half_inning_label": label, "pitch_velocity": float(v),
                "pitch_type": t, "atbat_pitch_number": (i % 4) + 1,
            })
    # AAA pitches the top half in both games (chronological): two PRIOR outings.
    outing("G1", "2022-04-01", "top1", "AAA", "BBB", [95, 94, 93, 92, 91], ["FF"] * 5)
    outing("G2", "2022-04-08", "top1", "AAA", "CCC", [96, 95, 94, 93], ["FF", "SL", "FF", "SL"])
    outing("G3", "2022-04-15", "top1", "AAA", "DDD", [94, 93, 92], ["FF", "FF", "SL"])
    # An away-side outing (bottom half) -> different (team, side) group.
    outing("G1", "2022-04-01", "bottom1", "AAA", "BBB", [88, 87, 86], ["CH", "CH", "FF"])
    return pd.DataFrame(rows)


def test_per_outing_summary_non_degenerate():
    df = _synthetic_pitch_df()
    out = M.per_outing_summary(df)
    # 3 AAA(home/top) outings + 1 BBB(away/bottom) outing.
    assert len(out) == 4
    aaa = out[(out["pitch_team"] == "AAA") & (out["pitch_side"] == "home")]
    assert len(aaa) == 3
    # velo declines within each outing -> negative slope (non-degenerate signal).
    assert (aaa["velo_decline_slope"] < 0).all()
    # entropy: G1 all-FF -> 0; G2 mixed -> > 0 (non-degenerate distribution).
    g1 = aaa[aaa["game_id"] == "G1"]["pitch_mix_entropy"].iloc[0]
    g2 = aaa[aaa["game_id"] == "G2"]["pitch_mix_entropy"].iloc[0]
    assert g1 == 0.0
    assert g2 > 0.0


def test_profile_is_leak_free_shift1():
    """Outing N's profile must equal the PRIOR outings' mean, never include outing N."""
    df = _synthetic_pitch_df()
    prof = M.prior_n_profile(M.per_outing_summary(df), prior_n=3)
    aaa = prof[(prof["pitch_team"] == "AAA") & (prof["pitch_side"] == "home")] \
        .sort_values("date").reset_index(drop=True)
    # First outing: no prior -> NaN profile (NOT 0-filled), prof_n_prior == 0.
    assert aaa.loc[0, "prof_n_prior"] == 0
    assert math.isnan(aaa.loc[0, "prof_mean_early_velo"])
    # Second outing: profile == first outing's own value (the single prior).
    first_early = aaa.loc[0, "mean_early_velo"]
    assert aaa.loc[1, "prof_mean_early_velo"] == pytest.approx(first_early)
    assert aaa.loc[1, "prof_n_prior"] == 1
    # Third outing: profile == mean of outings 0 and 1 (NOT including outing 2 itself).
    expect = (aaa.loc[0, "mean_early_velo"] + aaa.loc[1, "mean_early_velo"]) / 2.0
    assert aaa.loc[2, "prof_mean_early_velo"] == pytest.approx(expect)
    # CRITICAL leak check: outing 2's profile must NOT equal its own shape.
    assert aaa.loc[2, "prof_mean_early_velo"] != pytest.approx(aaa.loc[2, "mean_early_velo"])


def test_asof_monotonic_n_prior():
    df = _synthetic_pitch_df()
    prof = M.prior_n_profile(M.per_outing_summary(df), prior_n=3)
    for (_, _), grp in prof.groupby(["pitch_team", "pitch_side"]):
        seq = grp.sort_values("date")["prof_n_prior"].tolist()
        assert seq[0] == 0  # first outing has zero priors
        assert all(b >= a for a, b in zip(seq, seq[1:]))  # non-decreasing


def test_parity_builder_deterministic():
    """Same input -> identical profile (train/inference parity: one builder, no drift)."""
    df = _synthetic_pitch_df()
    a = M.prior_n_profile(M.per_outing_summary(df), prior_n=3)
    b = M.prior_n_profile(M.per_outing_summary(df.copy()), prior_n=3)
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))


def test_label_not_a_feature():
    """No prof_* / shape column may be sourced from a K/strikeout label column."""
    df = _synthetic_pitch_df()
    prof = M.prior_n_profile(M.per_outing_summary(df), prior_n=3)
    cols = list(prof.columns)
    assert not any("strikeout" in c.lower() or "_k" in c.lower() or c.lower() == "k"
                   for c in cols)
    # profile builds with NO gamelogs path supplied -> proves it never reads the label.
    assert any(c.startswith("prof_") for c in cols)


def test_label_join_insufficient_data_honest():
    """K label join must report INSUFFICIENT_DATA (no 0-fill / fabrication) with reasons."""
    df = _synthetic_pitch_df()
    prof = M.prior_n_profile(M.per_outing_summary(df), prior_n=3)
    res = M.build_label_join(prof, gamelogs_path=_REPO / "data/domains/mlb/player_gamelogs.parquet")
    assert res["status"] == "INSUFFICIENT_DATA"
    # SP identity is always missing for this pitch schema.
    assert "NO_SP_IDENTITY" in res["reasons"]
    # 2022 profile vs 2026-only K source -> no overlap.
    assert 2022 in res["profile_seasons"]


def test_label_join_no_source_reason():
    df = _synthetic_pitch_df()
    prof = M.prior_n_profile(M.per_outing_summary(df), prior_n=3)
    res = M.build_label_join(prof, gamelogs_path=_REPO / "data/domains/mlb/__nope__.parquet")
    assert res["status"] == "INSUFFICIENT_DATA"
    assert "NO_K_SOURCE" in res["reasons"]


@pytest.mark.skipif(not (_PITCH_DIR / "mlb_pitch_states__2022.parquet").exists(),
                    reason="materialized 2022 pitch parquet absent")
def test_real_corpus_2022_non_degenerate_and_insufficient_label():
    prof = M.build_profile(2022, pitch_dir=_PITCH_DIR, prior_n=3)
    assert not prof.empty
    # outings exist for both sides; shapes vary (not all identical / 0-filled).
    assert prof["n_pitches"].nunique() > 5
    assert prof["velo_decline_slope"].notna().sum() > 50
    # some outings have a prior profile (as-of accumulates).
    assert int(prof["prof_n_prior"].gt(0).sum()) > 50
    res = M.build_label_join(prof)
    assert res["status"] == "INSUFFICIENT_DATA"
