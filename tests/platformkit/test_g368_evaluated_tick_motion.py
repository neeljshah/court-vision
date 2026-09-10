"""G368 -- the two synthetic controls, the run census, the fall-through, the seal.

Run ALONE:
    python3 -m pytest tests/platformkit/test_g368_evaluated_tick_motion.py -q -p no:cacheprovider
NEVER a full pytest.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from scripts.platformkit.tracking import g368_controls_strips as extra
from scripts.platformkit.tracking import g368_tick_motion as core

ROOT = Path(__file__).resolve().parents[2]
PREREG = (ROOT / "docs" / "evidence" / "tracking"
          / "g368_evaluated_tick_motion_2026-09-09" / "g368_prereg_2026-09-09.md")
SEAL_PREFIX = "SEAL sha256 "


def _load(frame: pd.DataFrame, tmp_path: Path, name: str = "s") -> pd.DataFrame:
    path = tmp_path / name / "tracking_data.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")
    return core.load(path)


def _rows(spec: list[tuple[int, int, int, int, str]]) -> pd.DataFrame:
    """(tick, track, x, y, confidence) -> a table with exactly the producer's columns."""
    return pd.DataFrame([
        {"frame": tick * 6, "player_id": track, "x_position": x, "y_position": y,
         "confidence": confidence, "bbox_x1": str(x - 1), "bbox_y1": str(y - 1),
         "bbox_x2": str(x + 1), "bbox_y2": str(y + 1)}
        for tick, track, x, y, confidence in spec])


def test_control_k1_every_tick_moves(tmp_path):
    table = _load(extra.synthetic(False), tmp_path, "k1")
    census = core.census(table)
    assert core._f(core.motion_of(table)["motion_share"]) == core._f(1.0)
    assert census["held_runs_n"] == core._i(0)
    assert census["held_steps_n"] == core._i(0)


def test_control_k2_planted_coast_is_fully_attributed(tmp_path):
    table = _load(extra.synthetic(True), tmp_path, "k2")
    census = core.census(table)
    assert census["held_runs_n"] == core._i(1)
    assert census["run_len_max"] == core._i(extra.PLANT_LEN)
    assert census["held_steps_n"] == core._i(extra.PLANT_LEN - 1)
    steps = core.classify(table)
    steps = steps.loc[steps.ne("")]
    assert len(steps) == extra.PLANT_LEN - 1
    assert int((steps == "COAST_LOST").sum()) == len(steps), "the plant must attribute 100 pct"
    assert int((steps == "UNATTRIBUTED").sum()) == 0


def test_control_k2_ball_carry_over_attributes_to_the_flagged_branch():
    steps, share = extra.ball_carry_share(extra.synthetic_ball(True))
    assert steps == extra.PLANT_LEN - 1
    assert core._f(share) == core._f(1.0)
    clean_steps, _ = extra.ball_carry_share(extra.synthetic_ball(False))
    assert clean_steps == 0, "an unplanted ball table must carry no held step"


def test_run_length_census_on_a_constructed_table(tmp_path):
    # track 1: a run of 3 then a run of 2; track 2: never repeats.
    spec = [(0, 1, 10, 10, "1.0"), (1, 1, 10, 10, "1.0"), (2, 1, 10, 10, "1.0"),
            (3, 1, 50, 50, "1.0"), (4, 1, 60, 60, "1.0"), (5, 1, 60, 60, "1.0")]
    spec += [(tick, 2, 100 + tick, 200 + tick, "1.0") for tick in range(6)]
    census = core.census(_load(_rows(spec), tmp_path))
    assert census["held_runs_n"] == core._i(2)
    assert census["run_len_max"] == core._i(3)
    assert census["held_steps_n"] == core._i(3)         # 2 from the triple, 1 from the pair
    assert census["tick_share_in_runs_ge2"] == core._f(5 / 12)
    assert census["tick_share_in_runs_ge5"] == core._f(0.0)


def test_motion_share_counts_tick_pairs_not_rows(tmp_path):
    # 4 ticks; on the pair 1->2 nothing moves, on 0->1 and 2->3 something does.
    spec = [(0, 1, 10, 10, "1.0"), (1, 1, 20, 20, "1.0"),
            (2, 1, 20, 20, "1.0"), (3, 1, 30, 30, "1.0")]
    measured = core.motion_of(_load(_rows(spec), tmp_path))
    assert measured["ticks"] == 4
    assert measured["tick_pairs"] == 3
    assert measured["moved_pairs"] == 2
    assert core._f(measured["motion_share"]) == core._f(2 / 3)


def test_a_track_present_on_only_one_tick_cannot_move_a_pair(tmp_path):
    # track 2 appears once, on tick 1; the 0->1 pair must stay unmoved.
    spec = [(0, 1, 10, 10, "1.0"), (1, 1, 10, 10, "1.0"), (1, 2, 99, 99, "1.0")]
    measured = core.motion_of(_load(_rows(spec), tmp_path))
    assert measured["moved_pairs"] == 0, "only tracks present at BOTH ticks may move a pair"


def test_an_unattributed_run_stays_unattributed(tmp_path):
    frame = _rows([(0, 1, 10, 10, "1.0"), (1, 1, 10, 10, ""), (2, 1, 10, 10, "")])
    steps = core.classify(_load(frame, tmp_path))
    steps = steps.loc[steps.ne("")]
    assert len(steps) == 2
    assert set(steps) == {"UNATTRIBUTED"}, "a blank confidence must not be reclassified"


def test_a_blank_previous_bbox_falls_through_to_unattributed(tmp_path):
    frame = _rows([(0, 1, 10, 10, "1.0"), (1, 1, 10, 10, "0.8")])
    frame.loc[0, ["bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"]] = ""
    steps = core.classify(_load(frame, tmp_path))
    steps = steps.loc[steps.ne("")]
    assert list(steps) == ["UNATTRIBUTED"], "absent evidence outranks every other class"


def test_the_sealed_class_order_puts_coast_ahead_of_a_frozen_box(tmp_path):
    # confidence below 1.0 AND an identical box: C2 wins over C3 by the sealed order.
    frame = _rows([(0, 1, 10, 10, "1.0"), (1, 1, 10, 10, "0.933")])
    steps = core.classify(_load(frame, tmp_path))
    assert list(steps.loc[steps.ne("")]) == ["COAST_LOST"]


def test_a_fresh_detection_with_a_moving_box_is_clamp_or_subpixel(tmp_path):
    frame = _rows([(0, 1, 10, 10, "1.0"), (1, 1, 10, 10, "1.0")])
    frame.loc[1, ["bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"]] = ["5", "5", "15", "15"]
    steps = core.classify(_load(frame, tmp_path))
    assert list(steps.loc[steps.ne("")]) == ["CLAMP_OR_SUBPIXEL"]


def test_m1_removes_the_tail_of_a_held_run_and_keeps_its_first_row(tmp_path):
    spec = [(0, 1, 10, 10, "1.0"), (1, 1, 10, 10, "0.8"), (2, 1, 10, 10, "0.8"),
            (3, 1, 40, 40, "1.0")]
    runs, report = core.run_report(_load(_rows(spec), tmp_path))
    assert runs["COAST_LOST"] == 1
    assert report["dropped"] == 2, "M1 must drop exactly the two repeated rows"
    assert report["outcome"]["COAST_LOST"]["REMOVED_TAIL"] == 1
    assert report["outcome"]["COAST_LOST"]["SPLIT"] == 0


def test_coast_row_share_counts_moving_coasts_too(tmp_path):
    # a coasted row that MOVES is still a coast and must be counted.
    spec = [(0, 1, 10, 10, "1.0"), (1, 1, 20, 20, "0.8"), (2, 1, 30, 30, "0.8")]
    table = _load(_rows(spec), tmp_path)
    assert core.census(table)["held_steps_n"] == core._i(0)
    assert int(core.coast_rows(table).sum()) == 2


def test_strip_sampling_is_even_and_never_a_head_slice():
    names = ["s{:03d}".format(index) for index in range(100)]
    picked = extra.pick_sections(names)
    assert len(picked) == extra.STRIP_N
    assert picked[0] == "s000" and picked[-1] == "s090"
    assert picked == sorted(picked)
    assert extra.pick_sections(names[:4]) == names[:4]


def test_the_strip_track_choice_is_deterministic(tmp_path):
    spec = [(0, 1, 10, 10, "1.0"), (1, 1, 11, 11, "1.0"), (0, 2, 20, 20, "1.0")]
    table = _load(_rows(spec), tmp_path)
    assert extra.pick_track(table) == "1"
    svg = extra.strip_svg(table, "1", "sec")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert svg.isascii(), "a strip must be ASCII"


def test_absent_and_present_sections_are_both_reported(tmp_path):
    _load(extra.synthetic(False), tmp_path, "present")
    sections = tmp_path / "sections.csv"
    sections.write_text("section_name\npresent\nmissing\n", encoding="ascii")

    class Args:
        pass

    args = Args()
    args.sections, args.tracking_root = str(sections), str(tmp_path)
    args.corpus, args.append, args.ledger = "TEST", False, ""
    args.out = str(tmp_path / "motion.csv")
    core.cmd_motion(args)
    written = pd.read_csv(args.out, dtype=str, keep_default_na=False)
    assert set(written["status"]) == {"PRESENT", "ABSENT"}
    absent = written.loc[written["section_name"] == "missing"].iloc[0]
    assert absent["motion_share"] == "", "an absent section may never enter a share"


def test_the_bars_are_the_values_the_spec_carries():
    assert core.PREMISE_MOTION_MIN == 0.90
    assert core.ATTRIBUTION_BAR == 0.95
    assert core.PROPOSAL_TRIGGER == 0.20
    assert extra.STRIPS_MAX_BYTES == 200 * 1024
    assert extra.STRIP_N == 10


def test_the_preregistration_seal_covers_every_line_above_it():
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    body, _, seal = raw.rpartition(b"\n" + SEAL_PREFIX.encode())
    assert seal, "the preregistration must end with a seal line"
    assert hashlib.sha256(body + b"\n").hexdigest() == seal.decode("ascii").strip()
