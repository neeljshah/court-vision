"""G396 prepare-only gates for the third-rater qualification protocol."""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.tracking import g334_seal
from scripts.platformkit.tracking import g396_prepare, g396_protocol as protocol, g396_score

PREREG = Path("docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/g396_prereg_2026-09-11.md")


def _points(offset: float = 0.0):
    return ((10.0, offset), (130.0, offset), (70.0, offset))


def _rows(astra_bad: int = 0):
    truth = protocol.Band((0.0, 0.0), (200.0, 0.0))
    return [{"control_id": "c%02d" % index, "truth": truth, "sol": _points(),
             "astra": None if index < astra_bad else _points()} for index in range(30)]


def _fragment(y: float, name: str) -> protocol.Fragment:
    return protocol.Fragment(1, "LANE_LINE", (0.0, y), (120.0, y), (60.0, y), name)


def test_prereg_seal_normalizes_lf_from_the_file():
    assert PREREG.exists() and g334_seal.verify_seal(PREREG)


def test_old_new_control_join_is_rejected():
    row = {"image_sha256": "same", "source_context": "c", "tile_index": "1", "x1": "0", "y1": "0", "x2": "90", "y2": "0"}
    assert not g396_prepare.controls_disjoint([row], [dict(row)])


def test_one_rater_failure_blocks_real_dispatch():
    assert not protocol.qualification(_rows(astra_bad=4))["real_dispatch_allowed"]


def test_missing_response_and_finite_band_overrun_fail():
    truth = protocol.Band((0.0, 0.0), (200.0, 0.0))
    assert not protocol.control_passes(truth, None)
    assert not protocol.control_passes(truth, ((-1.0, 0.0), (130.0, 0.0), (70.0, 0.0)))


def test_displaced_parallel_band_fails_pairing():
    assert not protocol.pair_compatible(_fragment(0.0, "sol"), _fragment(8.0, "astra"))


def test_pair_audit_token_cannot_be_reused():
    used: set[str] = set()
    pair = (_fragment(0.0, "sol"), _fragment(0.0, "astra"))
    assert protocol.audit_pair("pair-1", pair, lambda _point: 0.0, used)
    assert not protocol.audit_pair("pair-1", pair, lambda _point: 0.0, used)


def test_scorer_repeats_from_raw_answers():
    truth = {"c": protocol.Band((0.0, 0.0), (200.0, 0.0))}
    answers = {"sol": {"c": _points()}, "astra": {"c": _points()}}
    assert g396_score.repeatable(truth, answers)


def test_practice_batches_go_only_to_the_fresh_rater(tmp_path):
    from scripts.platformkit.tracking import g396_controls
    records = [{"control_id": "G396_PRACTICE_%03d" % index, "image": "x.png", "tile_index": "1",
                "offset_x": "0", "offset_y": "0"} for index in range(30)]
    written = g396_controls.write_batches(records, tmp_path, tmp_path, "practice", ("astra",))
    assert set(written) == {"astra"} and len(written["astra"]) == 3
    assert all(len(Path(path).read_text().strip().splitlines()) == 10 for path in written["astra"])


def test_real_pairing_is_stable_and_rejects_a_displaced_band(tmp_path):
    import json
    from scripts.platformkit.tracking import g396_real
    for rater, y in (("astra", 0.0), ("sol", 1.0)):
        d = tmp_path / ("real_" + rater)
        d.mkdir()
        (d / "G396_001.json").write_text(json.dumps({"state": "VISIBLE", "fragments": [
            {"tile": 1, "family": "LANE_LINE",
             "points": {"p1": [10, 100 + y], "p2": [200, 100 + y], "p3": [100, 100 + y]}}]}))
        (d / "G396_002.json").write_text(json.dumps({"state": "VISIBLE", "fragments": [
            {"tile": 1, "family": "LANE_LINE",
             "points": {"p1": [10, 100 + 9 * y], "p2": [200, 100 + 9 * y], "p3": [100, 100 + 9 * y]}}]}))
    dirs = {r: tmp_path / ("real_" + r) for r in ("astra", "sol")}
    out = g396_real.pair_contexts(["G396_001", "G396_002"], dirs)
    assert len(out[0]["pairs"]) == 1 and out[1]["pairs"] == []


def test_render_repeat_digest_manifest_covers_every_landed_render():
    import csv
    import json

    evidence = PREREG.parent
    repeats = json.loads((evidence / "repeats.json").read_text(encoding="utf-8"))
    trees = {path.name: path for path in (evidence / "renders").iterdir() if path.is_dir()}
    assert set(repeats["render_trees"]) == set(trees)
    assert all(set(repeats["render_trees"][name]) >= {"process_1", "process_2", "matches_landed"}
               for name in trees)
    with (evidence / "renders_repeat_digests.csv").open(encoding="ascii", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == sum(1 for tree in trees.values() for path in tree.rglob("*") if path.is_file())
