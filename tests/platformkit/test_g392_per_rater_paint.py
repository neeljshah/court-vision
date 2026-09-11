"""G392 prepare-only invariants for qualification and isolated audits."""
from __future__ import annotations

import csv
from pathlib import Path

from scripts.platformkit.tracking import g334_seal
from scripts.platformkit.tracking import g392_prepare
from scripts.platformkit.tracking import g392_protocol as protocol

PREREG = Path("docs/evidence/tracking/g392_per_rater_paint_qualification_2026-09-11/g392_prereg_2026-09-11.md")


def _points(offset: float = 0.0):
    return ((10.0, offset), (130.0, offset), (70.0, offset))


def _rows(terra_bad: int = 0, sol_bad: int = 0):
    truth = protocol.Band((0.0, 0.0), (200.0, 0.0))
    return [{"control_id": "c%02d" % index, "truth": truth,
             "terra": None if index < terra_bad else _points(),
             "sol": None if index < sol_bad else _points()} for index in range(30)]


def _fragment(y: float = 0.0, first_x: float = 0.0, second_x: float = 120.0, name: str = "a"):
    return protocol.Fragment(1, "LANE_LINE", (first_x, y), (second_x, y), ((first_x + second_x) / 2, y), name)


def test_prereg_seal_reads_the_file_and_normalizes_lf():
    assert PREREG.exists()
    assert g334_seal.verify_seal(PREREG)


def test_one_rater_failure_blocks_real_dispatch():
    result = protocol.qualification(_rows(terra_bad=4))
    assert result["per_rater"]["terra"] == 26
    assert result["real_dispatch_allowed"] is False


def test_planted_thirty_pixel_displacement_fails():
    truth = protocol.Band((0.0, 0.0), (200.0, 0.0))
    assert not protocol.control_passes(truth, _points(30.0))


def test_arbitrary_extent_along_the_same_band_passes_pairing():
    assert protocol.pair_fragments([_fragment(0.0, 0.0, 120.0)], [_fragment(0.0, 40.0, 180.0, "b")])


def test_parallel_wrong_band_fails_pairing():
    assert protocol.pair_fragments([_fragment()], [_fragment(8.0, name="parallel")]) == []


def test_audit_pairs_are_isolated():
    good = (_fragment(), _fragment(name="b"))
    bad = (_fragment(name="c"), _fragment(name="d"))
    assert protocol.audit_pair(good, lambda _point: 0.0)
    assert not protocol.audit_pair(bad, lambda _point: 3.1)


def test_successor_scan_ignores_json_lists(tmp_path: Path):
    (tmp_path / "list.json").write_text("[]\n", encoding="ascii")
    assert g392_prepare._qualified_successors(tmp_path) == []


def test_control_sets_share_no_pixel_or_truth_tuple():
    from scripts.platformkit.tracking import g392_controls
    root = PREREG.parent
    practice = list(csv.DictReader((root / "practice" / "truth.csv").open(encoding="utf-8", newline="")))
    qualification = list(csv.DictReader((root / "qualification" / "truth.csv").open(encoding="utf-8", newline="")))
    assert len(practice) == len(qualification) == 30
    assert g392_controls.disjoint(practice, qualification)["disjoint"]


def test_a_missing_response_is_a_failure_not_unknown_paint(tmp_path: Path):
    from scripts.platformkit.tracking import g392_score
    truth_row = {"control_id": "G392_X", "control_set": "qualification", "tile_index": "1",
                 "offset_x": "0", "offset_y": "0", "angle_degrees": "0.0",
                 "x1": "0", "y1": "0", "x2": "200", "y2": "0"}
    row = g392_score.score_row(truth_row, tmp_path, "terra")
    assert row["passed"] == "0" and row["fail_reason"] == "NO_RESPONSE"


def test_a_failing_rater_is_named_excluded(tmp_path: Path):
    from scripts.platformkit.tracking import g392_score
    rows = [{"rater": "terra", "control_id": "c%02d" % i, "passed": "0" if i < 5 else "1",
             "answered": "1", "conversion_ok": "1", "perp_p1": "0.5", "perp_p2": "0.5",
             "perp_p3": "0.5", "angle_error_deg": "0.1", "fail_reason": ""} for i in range(30)]
    rows += [dict(row, rater="sol", passed="1", fail_reason="") for row in rows]
    summary = g392_score.summarise(rows)
    assert summary["excluded"] == ["terra"] and summary["qualified"] is False
