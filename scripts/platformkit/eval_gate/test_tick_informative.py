"""Per-file test for the S87 tick-informativeness pass. Run from the repo root:

    python -m pytest scripts/platformkit/eval_gate/test_tick_informative.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.eval_gate.tick_informative import (
    _ARTIFACTS, _CACHE, attach_informative_summary, flag_ticks, requote,
)


def _frame() -> pd.DataFrame:
    # g1: t0 new, t1 fully held, t2 market moves, t2 duplicate ts, t3 model-only moves.
    return pd.DataFrame(
        {
            "game": ["g1", "g1", "g1", "g1", "g1", "g2", "g2"],
            "timestamp": ["t0", "t1", "t2", "t2", "t3", "t0", "t1"],
            "market": [0.50, 0.50, 0.60, 0.60, 0.60, 0.40, 0.40],
            "model": [0.50, 0.50, 0.50, 0.50, 0.55, 0.40, 0.41],
            "loss_differential": [0.01, 0.00, -0.02, -0.02, 0.03, 0.02, -0.01],
        }
    )


def test_flags_and_counts():
    flagged, summary = flag_ticks(_frame(), loss_col="loss_differential")
    assert list(flagged["is_dup"]) == [False, False, False, True, False, False, False]
    assert list(flagged["is_held_market"]) == [False, True, False, True, True, False, True]
    assert list(flagged["is_held_model"]) == [False, True, True, True, False, False, False]
    # informative = not a duplicate AND (market moved OR model moved)
    assert list(flagged["is_informative"]) == [True, False, True, False, True, True, True]
    assert summary["n"] == 7 and summary["n_dup"] == 1
    assert summary["n_held_market"] == 4 and summary["n_held_model"] == 3
    assert summary["n_held_both"] == 2 and summary["n_informative"] == 5
    assert summary["n_games"] == 2


def test_first_tick_of_a_game_is_never_held():
    flagged, _ = flag_ticks(_frame())
    firsts = flagged.groupby("game", sort=False).head(1)
    assert not firsts["is_held_market"].any() and not firsts["is_held_model"].any()
    assert firsts["is_informative"].all()


def test_pure_and_reuses_the_icc_helper():
    frame = _frame()
    before = frame.copy()
    _, summary = flag_ticks(frame, loss_col="loss_differential")
    pd.testing.assert_frame_equal(frame, before)          # input untouched
    assert summary["n_eff_icc"] is not None and 0 < summary["n_eff_icc"] <= summary["n_informative"]
    assert flag_ticks(frame)[1]["n_eff_icc"] is None       # no loss column -> no invented ESS


def test_missing_column_raises():
    with pytest.raises(ValueError, match="missing required columns"):
        flag_ticks(_frame().drop(columns=["market"]))


@pytest.mark.parametrize("name", sorted(_ARTIFACTS))
def test_requote_reproduces_the_published_ci(name):
    spec = _ARTIFACTS[name]
    if not (_CACHE / spec["csv"]).exists() or not (_CACHE / spec["json"]).exists():
        pytest.skip("local-only archived artifact absent: %s" % spec["csv"])
    row = requote(name)
    # Q9: the published CI must come back out of the archived series before the
    # informative-subset CI beside it may be read at all.
    assert row["published_ci_reproduced_from_series"] is True
    assert row["after_informative"]["n"] == row["tick_flags"]["n_informative"]
    assert row["after_informative"]["n"] <= row["before_all_rows"]["n"]


# --- S87b: the helper, and one real writer wired to it ------------------------


def test_attach_informative_summary_adds_the_triple_without_touching_the_headline():
    artifact = {"verdict": "SCREEN_NULL", "dm": {"ci95": [-0.1, 0.2]}}
    frame = _frame()
    out = attach_informative_summary(artifact, frame, "loss_differential")
    block = out["tick_informative"]
    assert artifact is out and out["dm"]["ci95"] == [-0.1, 0.2]      # headline untouched
    assert out["verdict"] == "SCREEN_NULL"
    assert (block["n"], block["n_informative"]) == (7, 5)
    assert block["n_eff_icc"] is not None and block["ci95_informative"] is not None
    assert len(block["ci95_informative"]) == 2
    assert list(frame.columns) == list(_frame().columns)             # input frame not mutated


def test_attach_is_row_order_independent():
    shuffled = _frame().iloc[[6, 2, 0, 5, 4, 3, 1]].reset_index(drop=True)
    a, b = {}, {}
    attach_informative_summary(a, _frame(), "loss_differential")
    attach_informative_summary(b, shuffled, "loss_differential")
    assert a["tick_informative"]["n_informative"] == b["tick_informative"]["n_informative"]
    assert a["tick_informative"]["ci95_informative"] == b["tick_informative"]["ci95_informative"]


def test_attach_reports_no_ci_when_one_cluster():
    one = _frame()[_frame()["game"] == "g1"].reset_index(drop=True)
    block = attach_informative_summary({}, one, "loss_differential")["tick_informative"]
    assert block["ci95_informative"] is None
    assert block["ci95_informative_absent_because"]
    assert block["n"] == 5 and block["n_informative"] == 3            # the triple still reported


def test_s80_writer_reports_the_triple_on_a_synthetic_scored_frame():
    """The S80 SCREEN writer's own score() -- the wiring, not the corpus."""
    from types import SimpleNamespace

    from scripts.platformkit.eval_gate import s80_player_grain_screen as s80

    n = 8
    scored = pd.DataFrame({
        "game": ["g1"] * 4 + ["g2"] * 4,
        "timestamp": ["t0", "t1", "t2", "t3"] * 2,
        "date": ["2026-07-09"] * n,
        "outcome": [1, 1, 0, 0, 1, 0, 1, 0],
        "pitcher_id": list(range(n)),
        "z": [0.1] * n, "z_std": [0.1] * n, "beta": [0.0] * n, "weight": [1.0] * n,
        # market/model repeat within g1 (held) and move within g2 (informative)
        "market_prob": [0.55, 0.55, 0.55, 0.55, 0.50, 0.52, 0.54, 0.56],
        "p_incumbent": [0.60] * 4 + [0.50, 0.53, 0.55, 0.57],
        "p_candidate": [0.60, 0.60, 0.60, 0.60, 0.51, 0.54, 0.56, 0.58],
    })
    part = SimpleNamespace(basis="game", seed=0, screen_sha256="a" * 8, verdict_sha256="b" * 8,
                           screen_ids=["g1", "g2"], verdict_ids=[])
    summary, series = s80.score(scored, [], part, embargo_days=1)
    block = summary["tick_informative"]
    assert block["n"] == len(series) == n
    assert block["n_informative"] == 5                # g1 t1..t3 held on both sides
    assert block["n_held_market"] == 3 and block["n_dup"] == 0
    assert block["n_eff_icc"] is not None
    assert len(block["ci95_informative"]) == 2
    # the published CI is untouched -- the informative one is a SECOND number beside it
    assert summary["dm"]["ci95"] != block["ci95_informative"]


# --- S130: the flags are neither string-exact nor order-dependent ----------------

def test_the_same_instant_spelled_two_ways_is_one_tick():
    """Reproduced: `...Z` and `...+00:00` read as two ticks, n_dup 1 where 2 is right."""
    frame = pd.DataFrame({
        "game": ["g1", "g1", "g1"],
        "timestamp": ["2026-09-03T00:00:00Z", "2026-09-03T00:00:00+00:00",
                      "2026-09-03T00:01:00Z"],
        "market": [0.5, 0.5, 0.6], "model": [0.5, 0.6, 0.7]})
    _, summary = flag_ticks(frame)
    assert summary["n_dup"] == 1 and summary["n_informative"] == 2


def test_a_partly_parsing_ts_column_falls_back_rather_than_inventing_dups():
    """All-or-nothing on purpose: half a column of NaT would collapse every unparsed
    row into ONE tick, which deletes real ticks instead of merging spellings."""
    frame = pd.DataFrame({
        "game": ["g1", "g1", "g1"],
        "timestamp": ["2026-09-03T00:00:00Z", "not-a-timestamp", "also-not-one"],
        "market": [0.5, 0.5, 0.5], "model": [0.5, 0.6, 0.7]})
    _, summary = flag_ticks(frame)
    assert summary["n_dup"] == 0 and summary["n_informative"] == 3


def test_a_non_timestamp_ts_column_still_works():
    """A synthetic t0/t1 column must not collapse to NaT and become one big duplicate."""
    frame = pd.DataFrame({"game": ["g1"] * 3, "timestamp": ["t0", "t1", "t2"],
                          "market": [0.5, 0.6, 0.7], "model": [0.5, 0.6, 0.7]})
    _, summary = flag_ticks(frame)
    assert summary["n_dup"] == 0 and summary["n_informative"] == 3


def test_flag_ticks_is_row_order_independent():
    """Reproduced: the same six rows gave n_informative 6 in tick order and 2 reordered,
    because `requote` -- unlike `attach_informative_summary` -- never sorted."""
    frame = pd.DataFrame({
        "game": ["g1"] * 6, "timestamp": ["t0", "t1", "t2", "t3", "t4", "t5"],
        "market": [0.5, 0.6, 0.5, 0.6, 0.5, 0.6],
        "model": [0.5, 0.6, 0.5, 0.6, 0.5, 0.6],
        "loss_differential": [0.01, -0.02, 0.03, -0.01, 0.02, 0.0]})
    _, ordered = flag_ticks(frame, loss_col="loss_differential")
    _, scrambled = flag_ticks(frame.iloc[[0, 2, 4, 1, 3, 5]].reset_index(drop=True),
                              loss_col="loss_differential")
    assert ordered == scrambled and ordered["n_informative"] == 6


def test_interleaved_games_are_grouped_before_the_held_test():
    frame = pd.DataFrame({
        "game": ["g1", "g2", "g1", "g2"], "timestamp": ["t0", "t0", "t1", "t1"],
        "market": [0.5, 0.4, 0.6, 0.4], "model": [0.5, 0.4, 0.6, 0.4]})
    flagged, summary = flag_ticks(frame)
    assert list(flagged["game"]) == ["g1", "g1", "g2", "g2"]
    assert summary["n_informative"] == 3 and summary["n_held_market"] == 1


def test_the_reserved_scratch_column_is_refused_not_clobbered():
    frame = pd.DataFrame({"game": ["g1"], "timestamp": ["t0"], "market": [0.5],
                          "model": [0.5], "_tick_ts_key": ["mine"]})
    with pytest.raises(ValueError, match="reserved"):
        flag_ticks(frame)
