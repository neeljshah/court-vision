"""Prepare-only contract tests for G399."""
from pathlib import Path

from scripts.platformkit.tracking import g334_seal
from scripts.platformkit.tracking import g399_prepare, g399_protocol as protocol


PREREG = Path("docs/evidence/tracking/g399_qualified_paint_larger_sample_2026-09-11/g399_prereg_2026-09-11.md")


def _fragment(rater: str, y: float) -> protocol.Fragment:
    return protocol.Fragment(rater, 1, "LANE_LINE", (0.0, y), (120.0, y), (60.0, y), rater + str(y))


def test_prereg_seal_reads_lf_normalized_file():
    assert PREREG.exists() and g334_seal.verify_seal(PREREG)


def test_pts_targets_use_earlier_tie_and_reject_duplicate():
    assert protocol.planned_targets(0.0, 90.0, [20.0, 40.0, 50.0, 70.0]) == (20.0, 50.0)
    try:
        protocol.planned_targets(0.0, 9.0, [4.0])
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate PTS must remain a planned failure")


def test_displaced_parallel_band_fails_pairing():
    assert not protocol.pair_compatible(_fragment("astra", 0.0), _fragment("sol", 7.0))


def test_audit_token_isolated_per_pair():
    used: set[str] = set()
    pair = (_fragment("astra", 0.0), _fragment("sol", 0.0))
    assert protocol.audit_pair("pair-1", pair, lambda _point: 0.0, used)
    assert not protocol.audit_pair("pair-1", pair, lambda _point: 0.0, used)


def test_full_planned_denominator_keeps_absent_decode_rows(tmp_path):
    source = tmp_path / "source_identity.csv"
    source.write_text("attempt_id,source_path,source_sha256,source_bytes\na01,/missing/a.mp4,abc,10\n", encoding="ascii")
    receipt = g399_prepare.source_receipts(source)
    assert len(receipt) == 1 and receipt[0]["status"] == "ABSENT"


def test_configuration_drift_blocks_dispatch(tmp_path):
    instruction = tmp_path / "instruction.md"
    instruction.write_text("fixed\n", encoding="ascii")
    runtime = tmp_path / "runtime.json"
    runtime.write_text('{"astra":{"config_reasoning_effort":"high"},"sol":{"config_reasoning_effort":"medium"}}', encoding="ascii")
    receipt = g399_prepare.runtime_receipt({"astra": instruction, "sol": instruction}, runtime)
    assert not receipt["holds"]


def test_necessary_supply_is_not_sufficient_for_fit_or_validation():
    assert g399_prepare.supply_verdict(29, 30) == "NOT VALIDATED"
    assert g399_prepare.supply_verdict(30, 29) == "CLOSED AT LIMIT"
    assert g399_prepare.supply_verdict(30, 30) == "DONE_NECESSARY_ONLY"


def test_q6_scan_exempts_opaque_digest_but_not_prose(tmp_path):
    from scripts.platformkit.tracking import g399_q6_scan
    clean = tmp_path / "clean.txt"
    clean.write_text("a" * 64 + "\n", encoding="ascii")
    assert g399_q6_scan.hits(clean) == 0
    dirty = tmp_path / "dirty.txt"
    dirty.write_text("ed" + "ge\n", encoding="ascii")
    assert g399_q6_scan.hits(dirty) == 1


def test_q6_scan_keeps_numeric_claims_but_exempts_named_data(tmp_path):
    from scripts.platformkit.tracking import g399_q6_scan
    datum = "".join(("5", "4"))
    claim = tmp_path / "claim.json"
    claim.write_text('{"recovery_rate": ' + datum + "}\n", encoding="ascii")
    assert g399_q6_scan.hits(claim) == 1
    coordinate = tmp_path / "coordinate.json"
    coordinate.write_text('{"native_x": ' + datum + "}\n", encoding="ascii")
    assert g399_q6_scan.hits(coordinate) == 0


def _frag(rater: str, y: float, tile: int = 1, family: str = "LANE_LINE") -> protocol.Fragment:
    return protocol.Fragment(rater, tile, family, (0.0, y), (120.0, y), (60.0, y),
                             "%s_%s_%s" % (rater, tile, y))


def test_decoded_census_parses_trailing_empty_ffprobe_field():
    from scripts.platformkit.tracking import g399_measure as measure
    assert measure._pts_values("3.286611,\n3.320278,\nN/A\n\n") == {3.286611, 3.320278}


def test_frozen_order_is_competition_video_section_digest(tmp_path):
    from scripts.platformkit.tracking import g399_measure as measure
    rows = [{"attempt_id": "a2", "source_path": "/p/nba__X_s900.mp4", "source_sha256": "b",
             "ytid": "X", "offset": "900"},
            {"attempt_id": "a1", "source_path": "/p/nba__X_s90.mp4", "source_sha256": "a",
             "ytid": "X", "offset": "90"},
            {"attempt_id": "a3", "source_path": "/p/bare_s90.mp4", "source_sha256": "c",
             "ytid": "Y", "offset": "90"}]
    ordered = measure.frozen_order(rows, tmp_path)
    assert [item["attempt_id"] for item in ordered] == ["a1", "a2", "a3"]
    assert ordered[0]["competition"] == "nba" and ordered[2]["competition"] == "unlabelled"


def test_native_conversion_uses_the_frozen_tile_offsets():
    from scripts.platformkit.tracking import g399_score as scoring
    assert scoring.to_native(5, [10, 20]) == (650.0, 560.0)
    assert scoring.to_native(1, [0, 0]) == (0.0, 0.0)


def test_symmetric_line_distance_is_the_binding_maximum():
    from scripts.platformkit.tracking import g399_score as scoring
    assert scoring.symmetric_line_px(_frag("astra", 0.0), _frag("sol", 4.0)) == 4.0


def test_pairing_consumes_each_fragment_once_and_archives_the_rest():
    from scripts.platformkit.tracking import g399_score as scoring
    left = [_frag("astra", 0.0), _frag("astra", 200.0)]
    right = [_frag("sol", 1.0)]
    pairs, unmatched = scoring.freeze_pairs("G399_001", left, right)
    assert len(pairs) == 1 and pairs[0]["symmetric_line_px"] == 1.0
    assert [item.fragment_id for item in unmatched] == ["astra_1_200.0"]


def test_a_different_family_or_tile_never_pairs():
    from scripts.platformkit.tracking import g399_score as scoring
    assert scoring.freeze_pairs("c", [_frag("astra", 0.0)], [_frag("sol", 0.0, family="BASELINE")])[0] == []
    assert scoring.freeze_pairs("c", [_frag("astra", 0.0)], [_frag("sol", 0.0, tile=2)])[0] == []


def test_audit_points_are_nine_evenly_spaced_native_points():
    from scripts.platformkit.tracking import g399_score as scoring
    points = scoring.audit_points(_frag("astra", 10.0))
    assert len(points) == protocol.AUDIT_POINTS
    assert points[0] == (0.0, 10.0) and points[-1] == (120.0, 10.0)
    assert points[1][0] - points[0][0] == 15.0


def test_render_point_grid_decodes_a_boundary_patch(tmp_path):
    import cv2
    import numpy as np
    from scripts.platformkit.tracking import g399_score as scoring
    source, output = tmp_path / "source.png", tmp_path / "grid.jpg"
    cv2.imencode(".png", np.full((1080, 1920, 3), 255, dtype=np.uint8))[1].tofile(str(source))
    fragment = protocol.Fragment("astra", 1, "LANE_LINE", (0.0, 0.0), (8.0, 0.0),
                                 (4.0, 0.0), "boundary")
    receipt = scoring.render_point_grid(source, fragment, output)
    decoded = cv2.imdecode(np.fromfile(str(output), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert receipt["half_px"] == 24 and decoded is not None and decoded.shape == (1152, 1152, 3)
    assert decoded[0, 0].max() < 10 and decoded[300, 300].min() > 240


def test_recovery_counts_a_state_once_and_needs_both_fragment_audits():
    from scripts.platformkit.tracking import g399_score as scoring
    pairs = [{"pair_id": "p1", "context_id": "G399_001"}, {"pair_id": "p2", "context_id": "G399_001"},
             {"pair_id": "p3", "context_id": "G399_002"}]
    audits = {"p1": {"same_band": "YES", "astra_points": 9, "sol_points": 8},
              "p2": {"same_band": "YES", "astra_points": 9, "sol_points": 9},
              "p3": {"same_band": "YES", "astra_points": 9, "sol_points": 7}}
    result = scoring.recovery(pairs, audits)
    assert result["recovered_states"] == ["G399_001"] and len(result["passed_pairs"]) == 2


def test_an_unaudited_or_wrong_band_candidate_is_never_recovery():
    from scripts.platformkit.tracking import g399_score as scoring
    pairs = [{"pair_id": "p1", "context_id": "G399_001"}, {"pair_id": "p2", "context_id": "G399_002"}]
    audits = {"p2": {"same_band": "NO", "astra_points": 9, "sol_points": 9}}
    assert scoring.recovery(pairs, audits)["recovered_states"] == []


def test_measured_tables_keep_the_full_planned_denominator():
    import csv
    directory = PREREG.parent
    per_frame = list(csv.DictReader((directory / "per_frame.csv").open(encoding="ascii")))
    selection = list(csv.DictReader((directory / "selection.csv").open(encoding="ascii")))
    visibility = list(csv.DictReader((directory / "visibility.csv").open(encoding="ascii")))
    assert len(selection) == 60 and len(visibility) == 60 and len(per_frame) == 60
    assert {row["context_id"] for row in per_frame} == {row["context_id"] for row in selection}


def test_measured_sources_are_all_native_1080p_and_byte_exact():
    import csv
    directory = PREREG.parent
    receipts = list(csv.DictReader((directory / "source_receipts.csv").open(encoding="ascii")))
    bounds = list(csv.DictReader((directory / "pts_bounds.csv").open(encoding="ascii")))
    assert len(receipts) == 30 and all(row["status"] == "MATCH" for row in receipts)
    assert len(bounds) == 30
    assert all(row["width"] == "1920" and row["height"] == "1080" for row in bounds)
    assert all(int(row["n_decoded"]) <= int(row["n_packets"]) for row in bounds)


def test_measured_summary_separates_every_denominator():
    import json
    summary = json.loads((PREREG.parent / "summary.json").read_text(encoding="ascii"))
    assert summary["planned_states"] == 60
    for key in ("recovered_of_planned", "recovered_of_decoded", "recovered_of_visible"):
        assert summary[key]["denominator"] is not None
    assert summary["verdict"] == g399_prepare.supply_verdict(
        summary["decoded_states"], summary["recovered_of_planned"]["passed"])
