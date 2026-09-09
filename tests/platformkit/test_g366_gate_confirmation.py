"""Synthetic self-check for the G366 fresh-set, plant, v2 and reach rules."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.platformkit.liveness_metrics import compute_liveness_metrics, thresholds_for
from scripts.platformkit.tracking.g359_held_position import collapse_held
from scripts.platformkit.tracking.g366_confirm import (
    PLANT_GATE, V2_COLUMNS, V2_GATE, V2_THRESHOLD, plant_count, plant_tracks,
    reach_table, rejection, v2_row, v2_status,
)
from scripts.platformkit.tracking.g366_fresh import census, even_indices, even_pick

REPO_ROOT = Path(__file__).resolve().parents[2]
PREREG = (REPO_ROOT / "docs/evidence/tracking"
          / "g366_gate_confirmation_2026-09-09/g366_prereg_2026-09-09.md")
SEALED_V1 = 8.408436


def _moving_table(tracks: int = 4, frames: int = 10) -> pd.DataFrame:
    """Every player track advances one pixel per frame; one ball row per frame."""
    rows = [{"cls": "player", "frame": frame, "track_id": track, "team": "home",
             "x": 10.0 * track + frame, "y": 5.0 * track + frame, "scorable": False}
            for track in range(1, tracks + 1) for frame in range(frames)]
    rows += [{"cls": "ball", "frame": frame, "track_id": -1, "team": "home",
              "x": 7.0, "y": 7.0, "scorable": False} for frame in range(frames)]
    return pd.DataFrame(rows)


def _gate_row(gate: str, status: str, measurement: str = "", mode: str = "M0",
              arm: str = "A0", reason: str = "reason") -> dict[str, str]:
    return {"arm": arm, "mode": mode, "gate": gate, "status": status,
            "reason": reason, "measurement": measurement}


def test_v2_is_additive_and_the_sealed_v1_threshold_is_untouched() -> None:
    assert thresholds_for("basketball")["median_step_distance_max"] == SEALED_V1
    assert V2_THRESHOLD > SEALED_V1                     # a strictly wider max-direction bar
    cell = {"section_name": "s", "arm": "A0", "mode": "M1", "gate": V2_GATE,
            "measurement": "100.0", "threshold": str(SEALED_V1), "status": "PASS"}
    row = v2_row(cell)
    assert tuple(row) == V2_COLUMNS                     # additive columns, none renamed
    assert row["status_v1"] == "PASS" and row["threshold_v1"] == str(SEALED_V1)
    assert row["status_v2"] == "REJECT" and row["direction"] == "max"
    assert v2_status("REJECT", "10.0") == "PASS"        # inside the candidate, outside v1
    assert v2_status("PASS", "1.0") == "PASS"
    for carried in ("NOT_APPLICABLE", "MEASURED_NO_BAR", "UNIDENTIFIABLE", "REFUSED"):
        assert v2_status(carried, "") == carried        # v2 invents no status of its own


def test_not_applicable_never_passes_a_required_gate() -> None:
    rows = [_gate_row("oob", "NOT_APPLICABLE", reason="court_space_required") for _ in range(3)]
    rows += [_gate_row(V2_GATE, "PASS", "1.0"), _gate_row(V2_GATE, "NOT_APPLICABLE")]
    table = {(row["gate"], row["mode"]): row for row in reach_table(rows)}
    blocked = table[("oob", "M0")]
    assert blocked["pass_n"] == "000000" and blocked["not_applicable_n"] == "000003"
    assert blocked["share_reachable"] == "0.000000"
    assert blocked["causes"] == "court_space_required"
    mixed = table[(V2_GATE, "M0")]
    assert mixed["pass_n"] == "000001" and mixed["not_applicable_n"] == "000001"
    assert mixed["share_reachable"] == "0.500000"
    assert rejection(rows, "A0", V2_GATE, "M0")["n"] == 1   # excluded from the denominator


def _write_section(root: Path, name: str, frames: int = 200) -> None:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"frame": frame, "player_id": 1, "x_position": float(frame),
                   "y_position": 2.0} for frame in range(frames)]).to_csv(
        directory / "tracking_data.csv", index=False)
    pd.DataFrame([{"frame": frame, "ball_x2d_px": 1.0, "ball_y2d_px": 2.0}
                  for frame in range(frames)]).to_csv(
        directory / "ball_tracking.csv", index=False)


def test_the_fresh_set_is_disjoint_from_the_sealed_set_by_section_and_by_game(
        tmp_path: Path) -> None:
    sealed = tmp_path / "sealed.csv"
    pd.DataFrame([{"section_name": "bbbbbbbbbbb_s20", "game_id": "bbbbbbbbbbb"},
                  {"section_name": "ccccccccccc_s99", "game_id": "ccccccccccc"}]).to_csv(
        sealed, index=False)
    names = ["aaaaaaaaaaa_s10", "bbbbbbbbbbb_s20", "ccccccccccc_s30",
             "ddddddddddd_s40", "notpinnable"]
    for name in names:
        _write_section(tmp_path / "sections", name)
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("".join(json.dumps(
        {"game_id": name, "status": "tracked", "evaluated_frames": 200, "stride": 3,
         "decoded_frames": 600, "finished_at": 1788900000 if name.startswith("d") else 1789000000})
        + "\n" for name in names), encoding="utf-8")

    rows = {row["section_name"]: row for row in
            census(ledger, tmp_path / "sections", sealed, tmp_path / "fresh_sections.csv")}
    assert rows["aaaaaaaaaaa_s10"]["eligible"] == "1"
    assert rows["bbbbbbbbbbb_s20"]["ineligible_reason"] == "section_in_sealed_set"
    assert rows["ccccccccccc_s30"]["ineligible_reason"] == "game_in_sealed_set"
    assert rows["ddddddddddd_s40"]["ineligible_reason"] == "not_fresh"
    assert rows["notpinnable"]["ineligible_reason"] == "not_source_pinnable"
    assert all(row["eligible"] == "0" for name, row in rows.items() if name != "aaaaaaaaaaa_s10")
    assert rows["aaaaaaaaaaa_s10"]["tracking_sha256"] and rows["aaaaaaaaaaa_s10"]["offset_s"] == "10"


def test_the_stationary_plant_raises_the_share_under_both_arms() -> None:
    base = _moving_table()
    assert compute_liveness_metrics(base, "basketball").stationary_track_share == 0.0
    count = plant_count(4)
    assert count == 3                                  # max(3, ceil(0.30 * 4))
    spiked = plant_tracks(base, count)
    expected = count / (4 + count)
    threshold = thresholds_for("basketball")["stationary_track_share_max"]
    assert expected > threshold                        # the plant clears the bar by design
    assert compute_liveness_metrics(spiked, "basketball").stationary_track_share == expected
    collapsed, dropped = collapse_held(spiked)
    assert dropped == count * 9                        # 10 frames, first row of each run kept
    assert compute_liveness_metrics(collapsed, "basketball").stationary_track_share == expected
    assert len(base) == 4 * 10 + 10                    # the original table was not modified
    assert PLANT_GATE == "stationary_track_share"


def test_the_even_sampler_never_returns_a_head_slice() -> None:
    indices = even_indices(68, 30)                     # the G358 fix 1c rule, k = 2
    assert len(indices) == 34 and indices[0] == 0 and indices[-1] == 66
    assert even_indices(37, 30) == list(range(37))     # n <= 40 is a CONSTRUCT, k = 1
    assert even_indices(0, 30) == []
    picked = even_pick(list(range(50)), 10)
    assert len(picked) == 10 and picked[0] == 0 and picked[-1] == 49
    assert even_pick(list(range(6)), 10) == list(range(6))
    for n, target in ((68, 30), (91, 30), (50, 10), (53, 10)):
        assert max(even_indices(n, target)) >= n - max(n // target, 1)


def test_the_preregistration_seal_covers_every_line_above_it() -> None:
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    parts = raw.split(b"\n")
    assert parts[-1] == b"" and parts[-2].startswith(b"SEAL sha256 ")
    body = b"\n".join(parts[:-2]) + b"\n"
    assert hashlib.sha256(body).hexdigest() == parts[-2].split()[-1].decode("ascii")
