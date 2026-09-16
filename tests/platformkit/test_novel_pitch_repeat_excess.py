"""Tests for the count-conditioned repeat-pitch excess producer.

A synthetic plate-appearance fixture with hand-counted cells proves the two ways a pair
can silently go wrong -- a gap in pitch_number, and a pitch that leads the NEXT plate
appearance -- plus the leave-one-out expectation, the count-class mapping, the
swing-and-miss definition and the cluster resampler. Two further guards: the pre-pitch
count is measured rather than assumed, and a per-pair computation is identical whether
it is built from the whole season or from a truncated one. The last test reads the
COMMITTED artifact and fails on any non-ASCII byte or prohibited word.

Run: python -m pytest tests/platformkit/test_novel_pitch_repeat_excess.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.novel_pitch_repeat_excess import OUT_SHOWCASE
from scripts.platformkit.novel_pitch_repeat_pairs import (
    COUNT_CLASSES, MIN_PAIRS_PER_CELL, add_expectation, build_pairs, check_prepitch_count,
    cluster_means, codes_of, count_class, excess_panel, interval, load_pitches, multiplicities,
    pitch_family,
)

PROHIBITED = re.compile(
    r"(?<![A-Za-z0-9_])(edge|edges|bet|bets|betting|bettor|bettors|profit|profits|profitable|roi"
    r"|wager|wagers|wagering|bankroll|bankrolls|payout|payouts|dollar|dollars)(?![A-Za-z0-9_])",
    re.IGNORECASE)

# (game_pk, date, at_bat, pitch_number, pitcher, type code, balls, strikes, result, description, exit velocity)
FIXTURE = [
    # Plate appearance A: a called strike, then the SAME pitch again at 0-1.
    (1, "2025-04-01", 1, 1, 100, "FF", 0, 0, "S", "called_strike", None),
    (1, "2025-04-01", 1, 2, 100, "FF", 0, 1, "B", "swinging_strike", None),
    # B: the same opener, then a switch.
    (1, "2025-04-01", 2, 1, 100, "FF", 0, 0, "S", "called_strike", None),
    (1, "2025-04-01", 2, 2, 100, "SL", 0, 1, "B", "foul_tip", None),
    # C and D mirror A and B with the other type leading.
    (2, "2025-04-02", 1, 1, 100, "SL", 0, 0, "S", "called_strike", None),
    (2, "2025-04-02", 1, 2, 100, "FF", 0, 1, "X", "hit_into_play", 80.0),
    (2, "2025-04-02", 2, 1, 100, "SL", 0, 0, "S", "called_strike", None),
    (2, "2025-04-02", 2, 2, 100, "SL", 0, 1, "X", "swinging_strike_blocked", 100.0),
    # E: pitch_number 1 then 3. The gap must not be paired.
    (2, "2025-04-02", 3, 1, 100, "FF", 0, 0, "S", "called_strike", None),
    (2, "2025-04-02", 3, 3, 100, "FF", 0, 1, "B", "ball", None),
    # F: a pitchout code on the destination pitch, which is dropped as a non-pitch type.
    (2, "2025-04-02", 4, 1, 100, "FF", 0, 0, "S", "called_strike", None),
    (2, "2025-04-02", 4, 2, 100, "PO", 0, 1, "B", "pitchout", None),
]
COLUMNS = ["game_pk", "game_date", "at_bat_number", "pitch_number", "pitcher", "pitch_type",
           "balls", "strikes", "type", "description", "launch_speed"]
KEY = ["game_pk", "at_bat_number", "pitch_number"]


def _write(rows, tmp_path: Path, stem: str = "fx"):
    """Split a fixture into the pitch table and the outcome-code table on disk."""
    frame = pd.DataFrame(rows, columns=COLUMNS)
    pitch_path, code_path = tmp_path / (stem + "_p.parquet"), tmp_path / (stem + "_d.parquet")
    frame.drop(columns=["description"]).to_parquet(pitch_path, index=False)
    frame[KEY + ["description"]].to_parquet(code_path, index=False)
    return pitch_path, code_path


@pytest.fixture()
def pitches(tmp_path) -> pd.DataFrame:
    return load_pitches(*_write(FIXTURE, tmp_path))


@pytest.fixture()
def pairs(pitches) -> pd.DataFrame:
    return add_expectation(build_pairs(pitches))


def _by_pair(frame: pd.DataFrame) -> dict:
    return {tuple(row) for row in frame[KEY].itertuples(index=False, name=None)}


def test_count_class_reads_the_pre_pitch_count():
    assert count_class(0, 0) == COUNT_CLASSES[1] and count_class(2, 2) == COUNT_CLASSES[1]
    assert count_class(0, 1) == COUNT_CLASSES[2] and count_class(1, 2) == COUNT_CLASSES[2]
    assert count_class(1, 0) == COUNT_CLASSES[0] and count_class(3, 2) == COUNT_CLASSES[0]


def test_pitch_family_groups_the_standard_codes():
    assert [pitch_family(code) for code in ("FF", "SI", "FC")] == ["fastball"] * 3
    assert [pitch_family(code) for code in ("SL", "ST", "CU", "KC")] == ["breaking"] * 4
    assert [pitch_family(code) for code in ("CH", "FS")] == ["offspeed"] * 2
    assert pitch_family(None) == "other" and pitch_family("ZZ") == "other"


def test_a_gap_in_pitch_number_is_never_a_pair(pairs):
    # Plate appearance E holds pitch 1 and pitch 3; pairing them would invent a pitch.
    assert (2, 3, 3) not in _by_pair(pairs)
    assert pairs.attrs["coverage"]["adjacent_pairs"] == 4 + 1  # A, B, C, D and the pitchout pair


def test_the_first_pitch_of_the_next_at_bat_never_pairs_backwards(tmp_path):
    # pitch_number deliberately runs on across the boundary: 1, 2 then 3 in a NEW plate
    # appearance. A pair built on pitch_number alone would join 2 to 3.
    rows = [(9, "2025-05-01", 1, 1, 100, "FF", 0, 0, "S", "called_strike", None),
            (9, "2025-05-01", 1, 2, 100, "FF", 0, 1, "X", "hit_into_play", 90.0),
            (9, "2025-05-01", 2, 3, 100, "FF", 0, 0, "B", "ball", None),
            (9, "2025-05-01", 2, 4, 100, "FF", 1, 0, "B", "ball", None)]
    built = build_pairs(load_pitches(*_write(rows, tmp_path, "boundary")))
    assert _by_pair(built) == {(9, 1, 2), (9, 2, 4)}
    assert (9, 2, 3) not in _by_pair(built)


def test_unknown_and_non_pitch_types_are_dropped_with_a_reason(pairs):
    coverage = pairs.attrs["coverage"]
    assert coverage["dropped_unknown_or_non_pitch_type"] == 1
    assert (2, 4, 2) not in _by_pair(pairs)
    assert coverage["pairs_measured"] == 4
    assert coverage["dropped_pitcher_changed_mid_plate_appearance"] == 0


def test_leave_one_out_expectation_uses_the_other_pitches_only(pairs):
    # Four destination pitches at 0-1 for pitcher 100: FF, SL, FF, SL.
    rows = pairs.set_index(["game_pk", "at_bat_number"]).sort_index()
    assert list(rows["n_pitcher_count"]) == [4.0] * 4
    assert rows.loc[(1, 1), "expected_repeat"] == pytest.approx(1 / 3)   # repeat, so 1 of 3 others
    assert rows.loc[(1, 2), "expected_repeat"] == pytest.approx(2 / 3)   # switch, so 2 of 3 others
    assert rows.loc[(2, 1), "expected_repeat"] == pytest.approx(2 / 3)
    assert rows.loc[(2, 2), "expected_repeat"] == pytest.approx(1 / 3)
    assert list(rows["is_repeat"]) == [1.0, 0.0, 0.0, 1.0]
    assert rows["excess"].sum() == pytest.approx(0.0)


def test_a_pitcher_with_a_single_pitch_at_a_count_has_no_baseline(tmp_path):
    rows = [(5, "2025-04-03", 1, 1, 200, "FF", 0, 0, "S", "called_strike", None),
            (5, "2025-04-03", 1, 2, 200, "FF", 0, 1, "B", "ball", None)]
    built = add_expectation(build_pairs(load_pitches(*_write(rows, tmp_path, "solo"))))
    assert len(built) == 0
    assert built.attrs["coverage"]["dropped_only_pitch_at_that_count_for_that_pitcher"] == 1


def test_swing_and_miss_counts_only_a_missed_swing(pairs):
    rows = pairs.set_index(["game_pk", "at_bat_number"]).sort_index()
    assert list(rows["description"]) == ["swinging_strike", "foul_tip", "hit_into_play",
                                         "swinging_strike_blocked"]
    assert list(rows["is_whiff"]) == [1.0, 0.0, 0.0, 1.0]
    assert list(rows["is_called_or_whiff"]) == [1.0, 0.0, 0.0, 1.0]
    assert list(rows["is_weak_contact"]) == [0.0, 0.0, 1.0, 0.0]


def test_called_strike_joins_the_called_plus_swing_and_miss_rate(tmp_path):
    rows = [(7, "2025-04-04", 1, 1, 300, "FF", 0, 0, "S", "called_strike", None),
            (7, "2025-04-04", 1, 2, 300, "FF", 0, 1, "S", "called_strike", None),
            (7, "2025-04-04", 2, 1, 300, "FF", 0, 0, "S", "called_strike", None),
            (7, "2025-04-04", 2, 2, 300, "SL", 0, 1, "S", "foul", None)]
    built = build_pairs(load_pitches(*_write(rows, tmp_path, "csw")))
    assert list(built["is_whiff"]) == [0.0, 0.0]
    assert list(built["is_called_or_whiff"]) == [1.0, 0.0]


def test_the_pre_pitch_count_is_measured_not_assumed(pairs, pitches):
    check = pairs.attrs["prepitch_count_check"]
    assert check["verified"] is True
    assert check["balls_advance_agreement"] == 1.0 and check["strikes_advance_agreement"] == 1.0
    assert check["n_pairs_checked"] == 5
    broken = build_pairs(pitches).copy()
    broken.loc[broken.index[0], "balls"] = 3          # a post-pitch count would not advance this way
    assert check_prepitch_count(broken)["verified"] is False


def test_a_per_pair_computation_is_the_same_on_a_truncated_history(pitches):
    full = add_expectation(build_pairs(pitches)).set_index(KEY)
    early = pitches[pitches["game_date"] <= "2025-04-01"]
    half = add_expectation(build_pairs(early)).set_index(KEY)
    shared = sorted(set(half.index) & set(full.index))
    assert shared, "the truncated corpus must still carry pairs"
    for column in ("is_repeat", "count_class", "prev_family", "is_whiff"):
        assert list(half.loc[shared, column]) == list(full.loc[shared, column])
    # The leave-one-out baseline is a whole-corpus quantity by construction, so it MOVES.
    assert list(half["n_pitcher_count"]) != list(full.loc[shared, "n_pitcher_count"])


def test_the_resampler_draws_whole_games(pairs):
    weights = multiplicities(3, n_boot=50, seed=11)
    assert weights.shape == (3, 50)
    assert np.all(weights.sum(axis=0) == 3)
    values = np.array([1.0, 0.0, 1.0, 1.0])
    clusters = np.array([0, 0, 1, 1])
    point, counts, draws = cluster_means(values, np.zeros(4, dtype=int), clusters, 1,
                                         multiplicities(2, n_boot=200, seed=3))
    assert point[0] == pytest.approx(0.75) and counts[0] == 4
    assert set(np.round(np.unique(draws), 4)) <= {0.5, 0.75, 1.0}
    assert interval(draws[:, 0])[0] <= 0.75 <= interval(draws[:, 0])[1]


def test_a_thin_cell_keeps_its_count_and_publishes_no_estimate(pairs):
    frame, weights = pairs.copy(), multiplicities(2, n_boot=50, seed=5)
    frame["cluster"] = pd.factorize(frame["game_pk"])[0]
    cells, _ = excess_panel(frame, COUNT_CLASSES, "count_class", weights)
    ahead = [cell for cell in cells if cell["cell"] == COUNT_CLASSES[2]][0]
    assert ahead["n_pairs"] == 4 and ahead["n_pairs"] < MIN_PAIRS_PER_CELL
    assert ahead["masked"] is True and ahead["excess"] is None and ahead["ci95"] == [None, None]
    assert ahead["mask_reason"] == "fewer than %d pairs" % MIN_PAIRS_PER_CELL
    empty = [cell for cell in cells if cell["cell"] == COUNT_CLASSES[0]][0]
    assert empty["n_pairs"] == 0 and empty["mask_reason"] == "no pairs in this cell"


def test_an_unknown_label_fails_loudly(pairs):
    with pytest.raises(ValueError, match="outside"):
        codes_of(pairs, ["only one label"], "count_class")


def test_a_duplicated_outcome_code_row_is_refused(tmp_path):
    pitch_path, code_path = _write(FIXTURE, tmp_path, "dupe")
    codes = pd.read_parquet(code_path)
    pd.concat([codes, codes.iloc[[0]]], ignore_index=True).to_parquet(code_path, index=False)
    with pytest.raises(ValueError, match="duplicate keys"):
        load_pitches(pitch_path, code_path)


def test_the_committed_artifact_is_ascii_and_uses_the_published_vocabulary():
    raw = OUT_SHOWCASE.read_bytes()
    raw.decode("ascii")
    hits = PROHIBITED.findall(raw.decode("ascii"))
    assert hits == [], "prohibited words in the artifact: %s" % sorted(set(hits))
    artifact = json.loads(raw.decode("ascii"))
    assert artifact["descriptive_only"] is True
    assert [claim["id"] for claim in artifact["preregistered_claims"]] == [1, 2, 3]
    assert all(claim["verdict"] in {"CONFIRMED", "CONTRADICTED", "UNDECIDED"}
               for claim in artifact["preregistered_claims"])
    assert artifact["checks"]["prepitch_count_check"]["verified"] is True
    assert artifact["checks"]["raw_counts_absent"] == ["0-0"]
