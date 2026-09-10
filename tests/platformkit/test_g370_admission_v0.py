"""Focused synthetic contract tests for the G370 admission v0 preparation."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import pandas as pd

from scripts.platformkit.tracking import g370_controls
from scripts.platformkit.tracking.g370_export import write_export_hashes
from scripts.platformkit.tracking.g370_schema import (ADMISSION_COLUMNS, admission_status_for,
                                                        new_admission_row, task_mask_for,
                                                        validate_admission_row)
from scripts.platformkit.tracking.g370_scorer import _observation, _state_key
from scripts.platformkit.tracking.g370_ticks import tick_verification


def _track(source: str, observed: bool) -> dict:
    return {"track_id": 7, "track_generation": None, "bbox_px": None, "xy_px": [1, 2],
            "position_source": source, "producer_branch_file_line": None,
            "attribution_evidence_sha256": None, "last_observed_pts": None, "age_s": None,
            "observed": observed}


def _row(source: str = "DETECTION", observed: bool = True) -> dict:
    statuses = {"position": "PASS", "geometry": "NOT_APPLICABLE"}
    bars = {"position": True, "geometry": False}
    return new_admission_row(game_id="fixture", section_id="fixture_s1", frame_index=1,
                              geometry_status="IMAGE_ONLY", track_observations=[_track(source, observed)],
                              ball_observations=[], gate_status_by_task=statuses,
                              gate_scores_m1={}, task_mask=task_mask_for(statuses, bars, bars),
                              admission_status=admission_status_for(statuses, bars, bars))


def test_schema_validation_and_held_never_observed() -> None:
    row = _row()
    validate_admission_row(row, {"position": True}, {"position": True})
    assert set(ADMISSION_COLUMNS).issubset(row)
    assert _observation({"position_source": "HELD"})["observed"] is False
    with pytest.raises(ValueError, match="labels HELD as observed"):
        validate_admission_row(_row("HELD", True), {"position": True}, {"position": True})


def test_absent_evidence_disables_only_its_task() -> None:
    bars = {"position": True, "geometry": False}
    masks = task_mask_for({"position": "PASS", "geometry": "ABSENT"}, bars, bars)
    assert masks == {"position": True, "geometry": False}


def test_coast_plant_uses_real_collapsed_v0_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    source = pd.DataFrame([{ "frame": frame, "player_id": player,
                             "x_position": player * 100 + frame * frame,
                             "y_position": player * 100 + frame * frame + 1,
                             "ball_x2d": 20, "ball_y2d": 30}
                           for frame in range(20) for player in range(1, 6)])
    frozen = g370_controls.corrupt_before_adaptation(source, "FROZEN")
    coast = g370_controls.corrupt_before_adaptation(source, "COAST")
    assert not coast.equals(frozen)
    monkeypatch.setattr(g370_controls, "load_merged", lambda *_: source)
    result = g370_controls.control_result({"section_id": "s1", "tracking_path": "players.csv",
                                             "ball_path": "ball.csv"}, "COAST")
    assert result["status"] == "UNIDENTIFIABLE"
    assert result["detected"] == 0
    visible = pd.DataFrame([{ "frame": frame, "player_id": player,
                              "x_position": 0 if player == 1 else 100,
                              "y_position": 0 if player == 1 else 100,
                              "ball_x2d": 20, "ball_y2d": 30}
                            for frame in range(20) for player in range(1, 6)])
    monkeypatch.setattr(g370_controls, "load_merged", lambda *_: visible)
    rejected = g370_controls.control_result({"section_id": "s1", "tracking_path": "players.csv",
                                               "ball_path": "ball.csv"}, "ID_MERGE")
    assert rejected["status"] == "REJECT"
    assert rejected["detected"] == 1


def test_coast_plant_rejects_a_fully_held_track(monkeypatch: pytest.MonkeyPatch,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    held = pd.DataFrame([{ "frame": frame, "player_id": player,
                           "x_position": player * 10, "y_position": player * 10 + 1}
                          for frame in range(4) for player in range(1, 3)])
    with pytest.raises(ValueError, match="coast plant unconstructible"):
        g370_controls.corrupt_before_adaptation(held, "COAST")
    monkeypatch.setattr(g370_controls, "load_merged", lambda *_: held)
    result = g370_controls.control_result({"section_id": "held", "tracking_path": "players.csv",
                                            "ball_path": "ball.csv"}, "COAST")
    assert result["status"] == "UNIDENTIFIABLE"
    assert "PLANT-UNCONSTRUCTIBLE section=held kind=COAST" in capsys.readouterr().out


def test_coast_plant_advances_past_held_positions() -> None:
    half_held = pd.DataFrame([{ "frame": frame, "player_id": player,
                                "x_position": player * 10 + (0 if frame < 2 else 3),
                                "y_position": player * 10 + (0 if frame < 2 else 3)}
                               for frame in range(4) for player in range(1, 3)])
    coast = g370_controls.corrupt_before_adaptation(half_held, "COAST")
    frozen = g370_controls.corrupt_before_adaptation(half_held, "FROZEN")
    assert not coast.equals(frozen)
    player_one = coast.loc[coast["player_id"].eq(1)]
    assert player_one["x_position"].tolist() == [4, 7, 10, 13]
    assert player_one["y_position"].tolist() == [4, 7, 10, 13]


def test_task_mask_stays_disabled_when_a_control_bar_is_unmet() -> None:
    masks = task_mask_for({"position": "PASS"}, {"position": False}, {"position": True})
    assert masks == {"position": False}
    assert task_mask_for({"position": "PASS"}) == {"position": False}


def test_row_bars_cannot_enable_a_mask_without_artifact_bars() -> None:
    row = _row()
    row["gate_scores_m1"] = {"control_bar_by_task": {"position": True},
                             "plant_bar_by_task": {"position": True}}
    with pytest.raises(ValueError, match="task mask"):
        validate_admission_row(row)


def test_measured_bars_require_sealed_denominators_and_rates(tmp_path: Path) -> None:
    controls = tmp_path / "controls.csv"
    controls.write_text("task,game_id,usable,status\n" + "\n".join(
        "position,g{},true,{}".format(index % 10, "REJECT" if index == 0 else "PASS")
        for index in range(30)) + "\n", encoding="utf-8")
    plants = tmp_path / "plants.csv"
    plants.write_text("task,kind,identifiable,detected\n" + "\n".join(
        "position,{},true,true".format(kind) for kind in ("FROZEN", "ID_MERGE") for _ in range(30)
    ) + "\nposition,COAST,false,false\n", encoding="utf-8")
    assert g370_controls.measured_bars(controls, plants) == ({"position": True}, {"position": False})
    report = g370_controls.plant_bar_report(plants)["position"]
    assert report["COAST"] == (0, None)
    assert report["ID_MERGE"] == (30, 1.0)


def test_ticks_use_explicit_override_or_g359_implied_stride() -> None:
    tick_id, verified, _ = tick_verification(pd.DataFrame({"evaluated_tick_id": [0]}), {}, 17)
    assert (tick_id, verified) == (0, True)
    tick_id, verified, _ = tick_verification(pd.DataFrame({"is_evaluated_tick": [True]}), {}, 17)
    assert (tick_id, verified) == (17, True)
    tick_id, verified, _ = tick_verification(pd.DataFrame({"is_evaluated_tick": [0]}), {}, 17)
    assert (tick_id, verified) == (None, False)
    tick_id, verified, source = tick_verification(pd.DataFrame(),
                                                   {"ledger": {"decoded_frames": 60, "evaluated_frames": 10}}, 6)
    assert (tick_id, verified) == (1, True)
    assert source["implied_stride"] == 6
    tick_id, verified, _ = tick_verification(pd.DataFrame(),
                                              {"ledger_decoded_frames": 60,
                                               "ledger_evaluated_frames": 10}, 6)
    assert (tick_id, verified) == (1, True)


def test_composite_state_key_matches_preregistration() -> None:
    row = {"game_id": "game", "section_id": "section", "frame_index": 17, "evaluated_tick_id": "tick"}
    assert _state_key(row) == "game:section:17:tick"


def test_two_exports_are_byte_identical(tmp_path: Path) -> None:
    hashes = write_export_hashes([_row()], tmp_path / "admission_rows.csv",
                                 {"position": True}, {"position": True})
    assert len(hashes) == 2
    assert len(set(hashes.values())) == 1
    assert (tmp_path / "export_hashes.json").exists()


def test_parquet_empty_dicts_fall_back_to_csv(tmp_path: Path) -> None:
    hashes = write_export_hashes([_row()], tmp_path / "admission_rows.parquet",
                                 {"position": True}, {"position": True})
    assert len(hashes) == 2
    assert set(hashes) == {"admission_rows.csv", "admission_rows_repeat.csv"}
    assert not (tmp_path / "admission_rows.parquet").exists()


def test_preregistration_seal_normalizes_crlf_to_lf() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "docs/evidence/tracking/g370_admission_v0_2026-09-09/g370_prereg_2026-09-09.md"
    payload = path.read_bytes().replace(b"\r\n", b"\n")
    before, seal = payload.rsplit(b"SEAL sha256 ", 1)
    assert hashlib.sha256(before).hexdigest() == seal.strip().decode("ascii")


def test_even_pick_spans_the_whole_decision_ordering() -> None:
    from scripts.platformkit.tracking.g370_strips import even_pick
    picks = even_pick(1000, 30)
    assert len(picks) == 30 and picks[0] == 0 and picks[-1] == 999
    assert even_pick(5, 30) == [0, 1, 2, 3, 4]


def test_schedule_is_declared_from_the_ledger_not_from_rows() -> None:
    from scripts.platformkit.tracking.g370_manifest import _schedule
    assert _schedule({"stride": 3, "evaluated_frames": 4}) == ([0, 3, 6, 9], "")
    assert _schedule({"stride": 3}) == ([], "ledger_cadence_absent")
    assert _schedule({"stride": 0, "evaluated_frames": 4}) == ([], "ledger_cadence_non_positive")
