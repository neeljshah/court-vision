"""G336 harness checks on exhaustive hand-pinned constructs."""
import csv
import inspect
import json
import sys

import pytest

from scripts.platformkit.tracking import g336_capture, g336_run
from scripts.platformkit.tracking.g336_capture import RouteRefused
from scripts.platformkit.tracking.g336_track_id_continuity import (
    MAX_AGE, MAX_COST, _cell, associate, evaluator_records, evaluate_ticks, metrics,
)
from scripts.platformkit.tracking.g336_run import (
    _instance_rows, _premise_rows, _signature_choice, _starts,
)


def _det(frame, x, sig=(1.0, 0.0, 0.0)):
    return {"section": "s", "frame": frame, "team": "green", "score": 0.9,
            "bbox": [x, 0.0, x + 10.0, 20.0], "sig": list(sig)}


def test_fixed_candidate_parameters_are_preregistered():
    assert (MAX_COST, MAX_AGE) == (0.75, 30)


def test_unbounded_candidate_keeps_two_people_when_slot_cap_recycles_one_slot():
    # CONSTRUCT: production's one reusable slot would have to overwrite A with B on
    # frame 2. The candidate has no slot cap, so it retains A=1 and opens B=2.
    rows = associate([_det(1, 0), _det(2, 1), _det(2, 100), _det(3, 2), _det(3, 101)])
    ids_by_frame = {frame: sorted(r["instance_id"] for r in rows if r["frame"] == frame)
                    for frame in (1, 2, 3)}
    assert ids_by_frame == {1: [1], 2: [1, 2], 3: [1, 2]}
    assert sum(row["new_instance"] for row in rows) == 2


def test_metrics_use_named_frame_denominator_and_next_frame_switch_rule():
    rows = associate([_det(1, 0), _det(2, 1), _det(3, 2)])
    out = metrics(rows, evaluated_frames=3, raw_detections=rows, runtime_ms=6.0)
    assert out["instances"] == 1
    assert abs(out["fragmentation_ratio"] - 1 / 30) < 1e-12
    assert out["switch_proxy"] == 0
    assert out["n_frames"] == 3
    assert out["runtime_ms_per_frame"] == 2.0


def test_cpcv_records_one_stable_state_per_tick_with_two_arm_losses():
    states = []
    for index, section in enumerate(("a", "b", "c", "d")):
        states.extend(evaluate_ticks(section, [10, 20], {10: 2, 20: 1}, {10: 1, 20: 0}, index))
    rows = evaluator_records(states)
    assert len(rows) == 8
    assert len({row["tick_key"] for row in rows}) == 8
    assert all(abs(row["baseline_loss"] - row["candidate_loss"] - 0.1) < 1e-12 for row in rows)


def test_archived_instance_cells_are_six_digit_integers_and_starts_are_per_tick():
    rows = [{"section": "s", "frame": 4, "team": "green", "instance_id": 7,
             "new_instance": 1}, {"section": "s", "frame": 4, "team": "green",
                                    "instance_id": 7, "new_instance": 0}]
    assert _starts(rows) == {4: 1}
    assert _instance_rows("candidate", rows)[0] == {"arm": "candidate", "section": "s",
                                                      "frame": "000004", "team": "green",
                                                      "instance_id": "000007"}


def test_identical_observation_sets_drop_unassigned_from_both_arms():
    # CONSTRUCT: frame 2 carries an extra detection the route never assigned to a slot.
    # It must leave BOTH arms, so neither arm sees an observation the other cannot.
    raw = [{"section": "s", "frame": 1, "team": "green", "bbox": [0.0, 0.0, 10.0, 20.0],
            "sig": [1.0, 0.0, 0.0], "baseline_slot": 1},
           {"section": "s", "frame": 2, "team": "green", "bbox": [1.0, 0.0, 11.0, 20.0],
            "sig": [1.0, 0.0, 0.0], "baseline_slot": 1},
           {"section": "s", "frame": 2, "team": "green", "bbox": [90.0, 0.0, 100.0, 20.0],
            "sig": [1.0, 0.0, 0.0], "baseline_slot": None}]
    kept = [row for row in raw if row.get("baseline_slot") is not None]
    assert len(kept) == 2
    assert sorted(int(r["frame"]) for r in associate(kept)) == [1, 2]


def test_signature_is_osnet_only_when_every_observation_carries_one():
    full = [{"sig": [1.0, 0.0, 0.0], "deep": [0.5, 0.5]} for _ in range(2)]
    assert _signature_choice(full) == ("osnet", 1.0)
    assert full[0]["sig"] == [0.5, 0.5]
    mixed = [{"sig": [1.0, 0.0, 0.0], "deep": [0.5, 0.5]},
             {"sig": [1.0, 0.0, 0.0], "deep": None}]
    assert _signature_choice(mixed) == ("hsv", 0.5)
    assert mixed[0]["sig"] == [1.0, 0.0, 0.0]


def test_premise_rows_archive_recomputes_the_bottom_centre_in_milli_pixels():
    row = _premise_rows("s", [{"frame": "4", "player_id": "3", "bbox_x1": "1.5",
                               "bbox_y1": "0.0", "bbox_x2": "2.5", "bbox_y2": "20.25"}])[0]
    assert row == {"section": "s", "frame": "000004", "player_id": "000003",
                   "bbox_x1_milli_px": "001500", "bbox_y1_milli_px": "000000",
                   "bbox_x2_milli_px": "002500", "bbox_y2_milli_px": "020250"}


def _fake_capture(section, video, height, start, cap, output, raw_path):
    # CONSTRUCT: the route's own production preflight refuses two sections. There is
    # no bypass, so those sections must be recorded refused and never scored.
    if section.endswith(("575", "592")):
        raise RouteRefused(4)
    raw = [{"section": section, "frame": f, "team": "green", "score": 0.9,
            "bbox": [float(f), 0.0, f + 10.0, 20.0], "sig": [1.0, 0.0, 0.0],
            "deep": None, "baseline_slot": 1} for f in (1, 2, 3)]
    rows = [{"frame": str(f), "player_id": "1", "team": "green", "bbox_x1": str(float(f)),
             "bbox_y1": "0.0", "bbox_x2": str(f + 10.0), "bbox_y2": "20.0"} for f in (1, 2, 3)]
    return raw, rows, 3.0, 300.0


def test_refused_sections_are_recorded_and_never_scored(tmp_path, monkeypatch):
    monkeypatch.setattr(g336_run, "capture_section", _fake_capture)
    assert g336_run.run(tmp_path) == 0
    with (tmp_path / "premise.csv").open(newline="", encoding="utf-8") as handle:
        gates = {row["section"]: row["route_gate"] for row in csv.DictReader(handle)}
    assert gates == {"nba_0081": "pass", "nba_0575": "refused_exit_4",
                     "nba_0592": "refused_exit_4", "wnba_5l4": "pass"}
    with (tmp_path / "metrics.csv").open(newline="", encoding="utf-8") as handle:
        summary = list(csv.DictReader(handle))
    assert len(summary) == 4
    assert {row["section"] for row in summary} == {"nba_0081", "wnba_5l4"}
    assert {row["arm"] for row in summary} == {"baseline", "candidate"}
    assert all(int(row["n_ticks"]) == 3 for row in summary)


def test_numeric_cells_pad_integers_and_trim_floats_to_six_places():
    assert [_cell(v) for v in (10.0, 20, 0.0, 10.5, 0.045, 0.037777777777777785)] == [
        "000010", "000020", "000000", "10.5", "0.045", "0.037778"]
    assert _cell(None) is None and _cell("000004") == "000004"


def test_bypass_preflight_true_is_rejected_without_touching_the_route(tmp_path):
    # CONSTRUCT (B2): a caller built against the pre-fix-1b signature must fail loudly,
    # not silently run the production route with its preflight neutralised.
    with pytest.raises(ValueError, match="bypass_preflight is void"):
        g336_capture.capture_section("s", "v", 720, 90, 540, tmp_path, tmp_path / "r.jsonl",
                                     bypass_preflight=True)


def test_legacy_bypassed_status_is_mapped_to_refused_before_the_scored_cache_is_read(
        tmp_path, monkeypatch):
    # CONSTRUCT (B4): a stale cache from the deleted preflight-bypass path claims
    # scored=True under the legacy "bypassed_exit_4" token. No raw/tracking files back
    # it, so reading it as scored would crash -- proving it is mapped and skipped instead.
    (tmp_path / "nba_0575_meta.json").write_text(json.dumps(
        {"route_gate": "bypassed_exit_4", "scored": True, "assoc_ms": 1.0, "route_wall_ms": 1.0}))
    monkeypatch.setattr(g336_run, "capture_section", _fake_capture)
    assert g336_run.run(tmp_path) == 0
    with (tmp_path / "premise.csv").open(newline="", encoding="utf-8") as handle:
        gates = {row["section"]: row["route_gate"] for row in csv.DictReader(handle)}
    assert gates["nba_0575"] == "refused_exit_4"
    with (tmp_path / "metrics.csv").open(newline="", encoding="utf-8") as handle:
        summary = list(csv.DictReader(handle))
    assert "nba_0575" not in {row["section"] for row in summary}


def test_cap_and_offset_defaults_equal_the_sealed_amendment_540(monkeypatch, tmp_path):
    assert inspect.signature(g336_run.run).parameters["offset"].default == 90
    assert inspect.signature(g336_run.run).parameters["cap"].default == 540
    seen = {}

    def fake_capture_section(section, video, source_height, start, cap, output, raw_path):
        seen["cap"] = cap
        raise RouteRefused(4)

    monkeypatch.setattr(g336_capture, "capture_section", fake_capture_section)
    monkeypatch.setattr(sys, "argv", ["g336_capture.py", "--section", "s", "--video", "v",
                                      "--height", "720", "--output", str(tmp_path / "o"),
                                      "--raw", str(tmp_path / "r.jsonl")])
    with pytest.raises(RouteRefused):
        g336_capture.main()
    assert seen["cap"] == 540
