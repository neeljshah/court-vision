"""G363 rails: one-to-one matching, the even sampler, Wilson sanity and the seal.

Synthetic inputs only -- no frame, section or corpus file is opened here.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.platformkit.tracking.g363_ball_coverage import (
    MIN_SPACING, even_indices, read_csv, select_sections, split_for,
)
from scripts.platformkit.tracking.g363_score import match, score_arm, wilson

REPO = Path(__file__).resolve().parents[2]
PREREG = REPO / "docs/evidence/tracking/g363_ball_coverage_2026-09-09/g363_prereg_2026-09-09.md"
SEAL_PREFIX = "SEAL sha256 "


def _frame(key="k", height="1080", game="g", split="heldout"):
    return {"frame_key": key, "split": split, "height": height, "sheet_scale": "1.0",
            "game": game, "competition": "nba"}


def _prediction(key="k", x="100", y="100", arm="A0", rank="0", history="OBSERVED"):
    return {"arm": arm, "split": "heldout", "frame_key": key, "rank": rank,
            "tick_history": history, "x": x, "y": y}


def test_duplicate_prediction_is_a_false_positive():
    refs = [(100.0, 100.0, 20.0)]
    matched = match(refs, [(100.0, 100.0), (100.0, 100.0)], 1.0)
    assert len(matched) == 1, "one reference can absorb only one prediction"
    summary, rows = score_arm("A0", "heldout", [_frame()],
                              {"k": {"label": "VISIBLE", "cx": 100.0, "cy": 100.0,
                                     "diameter": 20.0}},
                              [_prediction(), _prediction()])
    assert (summary["tp"], summary["fp"]) == (1, 1)
    assert rows[0]["n_predictions"] == 2


def test_prediction_on_an_unknown_frame_is_a_false_positive():
    for label in ("UNKNOWN", "ABSENT"):
        summary, _ = score_arm("A0", "heldout", [_frame()],
                               {"k": {"label": label, "cx": None, "cy": None, "diameter": None}},
                               [_prediction()])
        assert (summary["tp"], summary["fp"]) == (0, 1), label
    assert summary["fp_per_absent"] == 1.0


def test_inferred_history_rows_are_never_scored():
    summary, _ = score_arm("A0", "heldout", [_frame()],
                           {"k": {"label": "VISIBLE", "cx": 100.0, "cy": 100.0, "diameter": 20.0}},
                           [_prediction(history="INFERRED", rank="-1")])
    assert (summary["tp"], summary["fp"]) == (0, 0)
    assert summary["abstention"] == 1.0


def test_distance_is_normalised_to_720p():
    refs = [(100.0, 100.0, 0.0)]
    preds = [(104.0, 100.0)]
    assert match(refs, preds, 720.0 / 1080.0), "4 native px at 1080p is 2.67 px at 720p"
    assert not match(refs, preds, 720.0 / 720.0), "4 px at 720p is outside the 3 px floor"


def test_even_sampler_is_not_a_head_slice():
    n_frames, count = 3900, 16
    indices = even_indices(n_frames, count, "abcdefghijk_s1500")
    spacing = n_frames // count
    assert len(set(indices)) == count
    assert indices == sorted(indices)
    assert min(indices) >= 2, "two causal neighbours must exist before the first index"
    assert max(indices) - min(indices) >= 0.9 * n_frames, "the sample must span the section"
    assert n_frames - max(indices) <= 2 * spacing, "the sample must reach the tail"
    assert set(indices) != set(range(min(indices), min(indices) + count))


def test_sampler_rejects_a_spacing_below_the_sealed_minimum():
    try:
        even_indices(MIN_SPACING * 4 - 1, 4, "abcdefghijk_s10")
    except ValueError:
        return
    raise AssertionError("a spacing below the sealed minimum must raise")


def test_splits_are_game_disjoint():
    rows = []
    games = [chr(ord("a") + index) * 11 for index in range(12)]
    for game in games:
        for offset in (100, 200, 300, 400):
            section = f"{game}_s{offset}"
            rows.append({"section": section, "game": game, "competition": "nba", "eligible": "1",
                         "split": split_for(game), "select_key": hashlib.sha256(
                             section.encode()).hexdigest()})
    development = {row["game"] for row in select_sections(rows, "development", 12)}
    heldout = {row["game"] for row in select_sections(rows, "heldout", 12)}
    assert development and heldout, "the sealed split rule must populate both sides"
    assert not development & heldout, "no game may appear in both splits"
    assert development | heldout == set(games)
    assert all(split_for(row["game"]) == row["split"] for row in rows)


def test_wilson_interval_sanity():
    assert wilson(0, 0) == (0.0, 1.0)
    low, high = wilson(50, 100)
    assert 0.0 < low < 0.5 < high < 1.0
    assert wilson(100, 100)[0] < 1.0
    assert wilson(95, 100)[0] > wilson(90, 100)[0]


def test_prereg_seal_matches_the_bytes_above_it():
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    body, _, seal = raw.rpartition(b"\n" + SEAL_PREFIX.encode())
    assert seal, "the preregistration must end with a seal line"
    recorded = seal.decode("ascii").strip()
    assert hashlib.sha256(body + b"\n").hexdigest() == recorded


def test_e6_alias_materializes_the_legacy_float_reader_value(tmp_path):
    table = tmp_path / "predictions.csv"
    table.write_text("score_e6\n000180054\n", encoding="utf-8", newline="\n")
    assert read_csv(table) == [{"score_e6": "000180054", "score": "0.180054"}]


def test_score_is_read_directly_when_the_additive_alias_is_present(tmp_path):
    table = tmp_path / "predictions.csv"
    table.write_text("score,score_e6\n+0.180054000,000180054\n", encoding="utf-8", newline="\n")
    assert read_csv(table) == [{"score": "+0.180054000", "score_e6": "000180054"}]
