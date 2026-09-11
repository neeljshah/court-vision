"""G388 preparation controls: finite bands, pairing, audits, and sealed text checks."""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.tracking import g334_seal
from scripts.platformkit.tracking import g388_protocol as protocol
from scripts.platformkit.tracking import g388_q6_scan

PREREG = Path("docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/g388_prereg_2026-09-11.md")


def _fragment(first=(0.0, 0.0), second=(120.0, 0.0), third=(60.0, 0.0), fragment_id="a"):
    return protocol.Fragment(0, "SIDELINE", first, second, third, fragment_id)


def _controls(bad: int = 0) -> list[dict[str, object]]:
    truth = protocol.Band((0.0, 0.0), (240.0, 0.0))
    points = ((20.0, 0.0), (200.0, 0.0), (100.0, 0.0))
    return [{"context_key": "c%02d" % index, "truth": truth, "rater_a": points,
             "rater_b": None if index < bad else points} for index in range(30)]


def test_prereg_seal_reads_the_file_and_normalizes_lf():
    assert PREREG.exists()
    assert g334_seal.verify_seal(PREREG)


def test_same_band_pairs_without_endpoint_agreement():
    left = _fragment((0.0, 0.0), (120.0, 0.0), (60.0, 0.0))
    right = _fragment((40.0, 0.0), (180.0, 0.0), (100.0, 0.0), "b")
    assert protocol.pair_fragments([left], [right]) == [(left, right)]


def test_parallel_band_is_not_a_pair():
    left = _fragment()
    right = _fragment((0.0, 8.0), (120.0, 8.0), (60.0, 8.0), "parallel")
    assert protocol.pair_fragments([left], [right]) == []


def test_tile_native_transform_roundtrip_without_rescaling():
    tile = (639.5, 539.25)
    offset = (1280.0, 540.0)
    native = protocol.tile_to_native(tile, offset)
    assert native == (1919.5, 1079.25)
    assert protocol.native_to_tile(native, offset) == tile


def test_control_failure_blocks_real_scoring_bar():
    result = protocol.controls_qualify(_controls(bad=4))
    assert result["passed"] == 26
    assert result["qualified"] is False


def test_control_requires_span_and_an_interior_third_click():
    truth = protocol.Band((0.0, 0.0), (240.0, 0.0))
    assert not protocol.control_passes(truth, ((10.0, 0.0), (20.0, 0.0), (15.0, 0.0)))
    assert not protocol.control_passes(truth, ((10.0, 0.0), (200.0, 0.0), (10.0, 0.0)))


def test_independent_third_point_rejects_off_line_fragment():
    assert protocol.fragment_valid(_fragment())
    assert not protocol.fragment_valid(_fragment(third=(60.0, 3.1)))


def test_audit_is_pair_specific_and_does_not_reuse_a_previous_pass():
    first = (_fragment(), _fragment(fragment_id="b"))
    second = (_fragment(fragment_id="c"), _fragment(fragment_id="d"))
    assert protocol.audit_pair(first, lambda _point: 0.0)
    assert not protocol.audit_pair(second, lambda _point: 3.1)


def test_even_selection_is_unique_and_inclusive():
    indices = protocol.selected_indices()
    assert len(indices) == 30 and len(set(indices)) == 30
    assert (indices[0], indices[-1]) == (0, 48)


def test_scanner_has_positive_and_negative_controls(tmp_path: Path):
    positive = tmp_path / "positive.txt"
    negative = tmp_path / "negative.txt"
    positive.write_text("measured " + "ed" + "ge" + " wording\n", encoding="ascii")
    negative.write_text("calibration wording only\n", encoding="ascii")
    assert g388_q6_scan.scan_paths([positive])
    assert g388_q6_scan.scan_paths([negative]) == []


def test_real_tables_account_for_every_context_including_absent_ones():
    from scripts.platformkit.tracking import g388_score

    left = protocol.Fragment(1, "BASELINE", (0.0, 0.0), (200.0, 0.0), (90.0, 0.0), "a")
    right = protocol.Fragment(1, "BASELINE", (40.0, 2.0), (300.0, 2.0), (170.0, 2.0), "b")
    results = [
        {"context_id": "G388_001", "terra_state": "VISIBLE", "sol_state": "VISIBLE",
         "terra_fragments": [left], "sol_fragments": [right],
         "pairs": [(left, right)], "family_disagreement": False},
        {"context_id": "G388_002", "terra_state": "ABSENT", "sol_state": "ABSENT",
         "terra_fragments": [], "sol_fragments": [], "pairs": [], "family_disagreement": False},
    ]
    pairs, frames = g388_score.real_tables(results, {"G388_001": "YES", "G388_002": "NO"})
    assert len(frames) == 2 and len(pairs) == 1
    assert frames[1]["pairs"] == "0" and frames[1]["claude_visibility"] == "NO"
    assert pairs[0]["audited_same_band"] == "PENDING"
