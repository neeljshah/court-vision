"""Per-file test for the G296 merge harness (sealed rules R3, R4, R6, R8, R10)."""
import csv
import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "g296_merge", ROOT / "scripts" / "platformkit" / "tracking" / "g296_merge.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def _pts(coords):
    return [{"person_index": i + 1, "xy": xy} for i, xy in enumerate(coords)]


def test_frame_indices_match_the_formula():
    assert M.FRAMES == [round(i * 174429 / 23) for i in range(24)]
    assert len(M.FRAMES) == 24 and M.FRAMES[0] == 0 and M.FRAMES[-1] == 174429


def test_sealed_constants():
    assert M.RADIUS == 50.0
    assert M.ADJUDICATE_ABOVE == 4.0


def test_pass_csv_headers_are_the_sealed_schema():
    assert M.HEADER == ["source_frame", "person_index", "role", "feet_visible",
                        "foot_x_px", "foot_y_px", "confidence", "note"]
    assert M.GT_HEADER == ["frame_id", "player_ordinal", "x", "y", "source",
                           "distance_px", "note"]
    for d in (M.A_DIR, M.B_DIR):
        with open(ROOT / d / "located_players.csv", newline="", encoding="utf-8") as fh:
            assert next(csv.reader(fh)) == M.HEADER


def test_match_is_one_to_one_and_globally_optimal():
    # Greedy would pair A1 with B1 (d=10) and strand A2; Hungarian takes the min sum.
    a = _pts([(0.0, 0.0), (30.0, 0.0)])
    b = _pts([(10.0, 0.0), (40.0, 0.0)])
    pairs, ao, bo = M.match(a, b, 50.0)
    assert sorted((i, j) for i, j, _ in pairs) == [(0, 0), (1, 1)]
    assert ao == [] and bo == []
    assert len({i for i, _, _ in pairs}) == len(pairs)
    assert len({j for _, j, _ in pairs}) == len(pairs)


def test_radius_breaks_a_pair_and_returns_both_sides_unmatched():
    a = _pts([(0.0, 0.0)])
    b = _pts([(0.0, 50.0), (0.0, 50.001)])
    pairs, ao, bo = M.match(a, b, 50.0)
    assert len(pairs) == 1 and math.isclose(pairs[0][2], 50.0)   # exactly at the radius keeps
    pairs, ao, bo = M.match(a, _pts([(0.0, 50.001)]), 50.0)
    assert pairs == [] and ao == [0] and bo == [0]               # just outside breaks both


def test_empty_side_yields_no_pairs():
    assert M.match([], _pts([(1.0, 1.0)]), 50.0) == ([], [], [0])
    assert M.match(_pts([(1.0, 1.0)]), [], 50.0) == ([], [0], [])


def test_percentile_endpoints():
    assert M.percentile([1.0, 2.0, 3.0], 0.5) == 2.0
    assert M.percentile([1.0, 2.0, 3.0], 0.0) == 1.0
    assert M.percentile([1.0, 2.0, 3.0], 1.0) == 3.0


def test_ground_truth_bookkeeping():
    """Every landed row carries a sealed source; ordinals are contiguous per frame."""
    path = ROOT / "docs" / "evidence" / "tracking" / "g296_ground_truth_2026-09-07.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        assert rdr.fieldnames == M.GT_HEADER
        rows = list(rdr)
    assert rows, "ground-truth set is empty"
    by_frame = {}
    for r in rows:
        assert r["source"] in ("agreed", "adjudicated_A", "adjudicated_B", "dropped")
        assert r["note"], "every row states why it was accepted or dropped"
        assert 0 <= int(r["x"]) <= 1919 and 0 <= int(r["y"]) <= 1079
        if r["source"] == "dropped":
            assert int(r["player_ordinal"]) == 0
        else:
            by_frame.setdefault(int(r["frame_id"]), []).append(int(r["player_ordinal"]))
        if r["distance_px"]:
            d = float(r["distance_px"])
            assert d <= M.RADIUS                       # R3: nothing matched beyond the radius
            if d <= M.ADJUDICATE_ABOVE:
                assert r["source"] == "agreed"         # R6: inside tolerance is never adjudicated
            else:
                assert r["source"] != "agreed"         # R6: outside tolerance is always adjudicated
    for frame, ords in by_frame.items():
        assert sorted(ords) == list(range(1, len(ords) + 1)), frame
