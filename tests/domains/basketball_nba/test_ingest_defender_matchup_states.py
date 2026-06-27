"""Tests for domains.basketball_nba.ingest_defender_matchup_states.

SMALL synthetic defender-matchup corpus only (a handful of defender-games). Fast,
low-RAM, never touches the real 37k-row on-disk corpus. Verifies:
  - schema   : frozen base cols present + additive as-of cols + diagnostics; row count.
  - leak-free : a row's *_asof never reflects its OWN game; mutating a LATER game's
                realized totals does NOT change an earlier game's as-of value.
  - as-of-monotonic : state uses ONLY strictly-prior games (shift1); first game per
                defender has NaN as-of + def_n_prior == 0; prior-N window is bounded.
  - parity   : the SINGLE builder produces an identical column set + dtypes regardless
                of how the corpus is sliced -> a feature cannot silently read 0.0 at
                inference (train == inference parity).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.basketball_nba.ingest_defender_matchup_states import (
    ASOF_COLS,
    BASE_COLS,
    DIAG_COLS,
    OUTPUT_COLS,
    build_defender_matchup_states,
)

PID_A, PID_B = 1001, 2002


def _m(gid, date, pid, tri, mins, pts, fgm, fga, fg3m, fg3a, blk, sw):
    return {
        "game_id": gid, "game_date": date, "season": "TST",
        "def_player_id": pid, "def_player_name": f"P{pid}", "def_team_tricode": tri,
        "matchup_minutes_total": mins, "partial_possessions": 50.0,
        "points_allowed": pts, "fg_made_allowed": fgm, "fg_attempted_allowed": fga,
        "fg3_made_allowed": fg3m, "fg3_attempted_allowed": fg3a,
        "switches_on": sw, "blocks_matchup": blk, "help_blocks": 0,
        "matchups_count": 5, "fg_pct_allowed": (fgm / fga if fga else 0.0),
        "fg3_pct_allowed": (fg3m / fg3a if fg3a else 0.0),
    }


@pytest.fixture
def corpus():
    """Defender A has 3 games (dates 1,3,5); defender B has 1 game (date 3)."""
    rows = [
        _m("G1", "2025-01-01", PID_A, "BOS", 20.0, 10, 4, 10, 1, 3, 1, 0),
        _m("G1", "2025-01-01", PID_B, "ATL", 18.0, 14, 6, 12, 2, 5, 0, 1),
        _m("G2", "2025-01-03", PID_A, "BOS", 24.0, 20, 8, 16, 2, 4, 2, 1),
        _m("G3", "2025-01-05", PID_A, "BOS", 22.0, 16, 6, 14, 1, 2, 0, 0),
    ]
    return pd.DataFrame(rows)


def _build(df, **kw):
    return build_defender_matchup_states(corpus=df, write=False, **kw)


# --------------------------------------------------------------------------- schema
def test_schema_frozen_base_and_additive(corpus):
    out = _build(corpus)
    assert list(out.columns) == list(OUTPUT_COLS)
    for c in BASE_COLS:
        assert c in out.columns, f"frozen base col missing: {c}"
    for c in ASOF_COLS:
        assert c in out.columns, f"additive as-of col missing: {c}"
    for c in DIAG_COLS:
        assert c in out.columns
    # one row per defender-game in the corpus
    assert len(out) == len(corpus)
    assert out["def_n_prior"].dtype.kind == "i"
    assert out["def_player_id"].dtype.kind == "i"


# ------------------------------------------------------------------- as-of monotonic
def test_first_game_per_defender_is_nan_zero_prior(corpus):
    out = _build(corpus)
    # defender A's first game (G1, date 1) and B's only game must have n_prior == 0
    a1 = out[(out.def_player_id == PID_A) & (out.game_id == "G1")].iloc[0]
    b1 = out[(out.def_player_id == PID_B)].iloc[0]
    assert a1["def_n_prior"] == 0
    assert b1["def_n_prior"] == 0
    for c in ASOF_COLS:
        if c == "def_n_prior":
            continue
        assert pd.isna(a1[c]), f"{c} should be NaN at first game"
        assert pd.isna(b1[c]), f"{c} should be NaN for single-game defender"


def test_asof_uses_only_prior_games(corpus):
    out = _build(corpus)
    # A's 2nd game (G2) as-of must equal A's G1 REALIZED rates (exactly 1 prior game).
    g1 = corpus[(corpus.def_player_id == PID_A) & (corpus.game_id == "G1")].iloc[0]
    g2 = out[(out.def_player_id == PID_A) & (out.game_id == "G2")].iloc[0]
    assert g2["def_n_prior"] == 1
    assert g2["def_priorN_fg_pct_allowed_asof"] == pytest.approx(g1["fg_made_allowed"] / g1["fg_attempted_allowed"])
    assert g2["def_priorN_blocks_per_game_asof"] == pytest.approx(g1["blocks_matchup"])
    assert g2["def_priorN_matchup_min_asof"] == pytest.approx(g1["matchup_minutes_total"])
    # A's 3rd game (G3) as-of = mean over G1+G2 (2 prior games), pooled rate.
    g2r = corpus[(corpus.def_player_id == PID_A) & (corpus.game_id == "G2")].iloc[0]
    g3 = out[(out.def_player_id == PID_A) & (out.game_id == "G3")].iloc[0]
    assert g3["def_n_prior"] == 2
    exp_fg = (g1["fg_made_allowed"] + g2r["fg_made_allowed"]) / (
        g1["fg_attempted_allowed"] + g2r["fg_attempted_allowed"])
    assert g3["def_priorN_fg_pct_allowed_asof"] == pytest.approx(exp_fg)


def test_prior_n_window_is_bounded(corpus):
    # With prior_n=1, A's G3 as-of must reflect ONLY G2 (the single most recent prior),
    # NOT a season-final all-time mean -> proves no season-aggregate leak.
    out = _build(corpus, prior_n=1)
    g2r = corpus[(corpus.def_player_id == PID_A) & (corpus.game_id == "G2")].iloc[0]
    g3 = out[(out.def_player_id == PID_A) & (out.game_id == "G3")].iloc[0]
    assert g3["def_n_prior"] == 1
    assert g3["def_priorN_fg_pct_allowed_asof"] == pytest.approx(
        g2r["fg_made_allowed"] / g2r["fg_attempted_allowed"])


# --------------------------------------------------------------------------- leak-free
def test_future_game_change_does_not_leak_into_earlier_asof(corpus):
    base = _build(corpus)
    g2_before = base[(base.def_player_id == PID_A) & (base.game_id == "G2")].iloc[0][
        list(ASOF_COLS)].to_dict()

    # Mutate a STRICTLY LATER game (G3) realized totals to extreme values.
    poisoned = corpus.copy()
    mask = (poisoned.def_player_id == PID_A) & (poisoned.game_id == "G3")
    for c in ("points_allowed", "fg_made_allowed", "fg_attempted_allowed",
              "blocks_matchup", "matchup_minutes_total"):
        poisoned.loc[mask, c] = 999
    after = _build(poisoned)
    g2_after = after[(after.def_player_id == PID_A) & (after.game_id == "G2")].iloc[0][
        list(ASOF_COLS)].to_dict()

    # G2's as-of (which only sees G1) must be UNCHANGED by poisoning the future G3.
    for c in ASOF_COLS:
        assert g2_before[c] == pytest.approx(g2_after[c], nan_ok=True), (
            f"future leak detected via {c}")


def test_realized_diag_is_current_game_not_a_feature(corpus):
    out = _build(corpus)
    g2 = out[(out.def_player_id == PID_A) & (out.game_id == "G2")].iloc[0]
    src = corpus[(corpus.def_player_id == PID_A) & (corpus.game_id == "G2")].iloc[0]
    # realized_* mirror THIS game's totals; they live alongside but separate from *_asof.
    assert g2["realized_points_allowed"] == pytest.approx(src["points_allowed"])
    assert g2["realized_blocks_matchup"] == pytest.approx(src["blocks_matchup"])
    # and the as-of feature for the same row does NOT equal this game's realized rate
    # (it reflects the prior game G1 instead).
    assert g2["def_priorN_fg_pct_allowed_asof"] != pytest.approx(
        src["fg_made_allowed"] / src["fg_attempted_allowed"])


# --------------------------------------------------------------------------- parity
def test_train_inference_parity_same_columns_and_dtypes(corpus):
    """The SINGLE builder must emit an identical schema regardless of slice, so a
    feature cannot silently read 0.0 between a 'train' build and an 'inference' build."""
    full = _build(corpus)
    # 'inference' slice: one defender only -> same columns + dtypes, no missing feature.
    one = _build(corpus[corpus.def_player_id == PID_A].reset_index(drop=True))
    assert list(full.columns) == list(one.columns)
    assert full.dtypes.astype(str).to_dict() == one.dtypes.astype(str).to_dict()
    for c in ASOF_COLS:
        assert c in one.columns
    # determinism: re-running the same input yields identical values (no hidden state).
    again = _build(corpus)
    pd.testing.assert_frame_equal(full, again)


def test_empty_corpus_yields_schema_only(corpus):
    empty = corpus.iloc[0:0]
    out = _build(empty)
    assert list(out.columns) == list(OUTPUT_COLS)
    assert len(out) == 0
