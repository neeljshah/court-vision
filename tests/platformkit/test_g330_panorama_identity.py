"""G330 -- census grouping, premise gate, proxy arithmetic and the additive sidecar guard.

Hand-pinned synthetic construct only: no pod, no footage, no cv2, no model.
"""
import json

from scripts.platformkit.tracking.g330_panorama_identity import (
    claimed_stem, collisions, frac, group_by_sha, pad6, pano_provenance_fields,
    parse_census_line, premise_holds, write_pano_provenance,
)

SHA_A = "a" * 64
SHA_B = "b" * 64

# Hand-pinned construct: three files carry SHA_A -- the general fallback plus two per-video
# cache entries claiming DIFFERENT videos -- and one file carries SHA_B on its own.
ROWS = [
    {"sha256": SHA_A, "bytes": 10, "mtime": "1", "path": "r/pano_enhanced.png", "stem": "-"},
    {"sha256": SHA_A, "bytes": 10, "mtime": "2", "path": "r/panos/pano_nba__g1.png",
     "stem": "nba__g1"},
    {"sha256": SHA_A, "bytes": 10, "mtime": "3", "path": "r/panos/pano_nba__g2.png",
     "stem": "nba__g2"},
    {"sha256": SHA_B, "bytes": 20, "mtime": "4", "path": "r/panos/pano_nba__g3.png",
     "stem": "nba__g3"},
]


def test_claimed_stem_reads_the_video_out_of_the_path():
    assert claimed_stem("r/panos/pano_nba__0022400909_s4453.png") == "nba__0022400909_s4453"
    assert claimed_stem("r/pano_enhanced.png") == "-"
    assert claimed_stem("r/pano.png") == "-"
    assert claimed_stem("r/court_map.png") == "-"


def test_parse_census_line_keeps_the_pipe_fields():
    row = parse_census_line("%s|1865583|1788831730.0|/w/resources/panos/pano_nba__g9.png" % SHA_A)
    assert row["sha256"] == SHA_A
    assert row["bytes"] == 1865583
    assert row["stem"] == "nba__g9"


def test_group_by_sha_and_collisions_are_hand_pinned():
    groups = group_by_sha(ROWS)
    assert len(groups) == 2
    assert len(groups[SHA_A]) == 3
    assert len(groups[SHA_B]) == 1
    hits = collisions(ROWS)
    assert len(hits) == 1
    assert hits[0]["sha256"] == SHA_A
    assert hits[0]["size"] == 3
    # The general fallback claims no video, so it is not counted as a claimed stem.
    assert hits[0]["stems"] == ["nba__g1", "nba__g2"]


def test_premise_gate_is_true_only_on_a_cross_video_collision():
    assert premise_holds(ROWS) is True
    distinct = [ROWS[0], ROWS[3]]
    assert premise_holds(distinct) is False
    # Two copies claiming the SAME video are not a premise hit.
    same_video = [dict(ROWS[1]), dict(ROWS[1], path="r/panos/copy.png", stem="nba__g1")]
    assert premise_holds(same_video) is False


def test_proxy_arithmetic_formatting_is_padded_and_fractional():
    assert pad6(0) == "000000"
    assert pad6(7) == "000007"
    assert pad6(1865583) == "1865583"
    assert frac(37, 120) == "37/120"
    assert frac(0, 0) == "0/0"


def test_sidecar_guard_adds_new_fields_only(tmp_path):
    pano = tmp_path / "pano_enhanced.png"
    pano.write_bytes(b"not really a png")
    fields = pano_provenance_fields("data/footage_corpus/nba__g1_s60.mp4", str(pano))
    assert set(fields) == {"pano_path", "pano_sha256", "pano_is_general_fallback", "video_stem"}
    assert fields["pano_is_general_fallback"] is True
    assert fields["video_stem"] == "nba__g1_s60"
    assert len(fields["pano_sha256"]) == 64
    built = tmp_path / "pano_nba__g1_s60.png"
    built.write_bytes(b"different bytes")
    other = pano_provenance_fields("nba__g1_s60.mp4", str(built))
    assert other["pano_is_general_fallback"] is False
    assert other["pano_sha256"] != fields["pano_sha256"]


def test_sidecar_guard_writes_one_json_file(tmp_path):
    pano = tmp_path / "pano_enhanced.png"
    pano.write_bytes(b"bytes")
    dest = write_pano_provenance(tmp_path / "run", "nba__g1_s60.mp4", str(pano))
    assert dest.name == "pano_provenance.json"
    loaded = json.loads(dest.read_text())
    assert loaded["pano_is_general_fallback"] is True
    assert loaded["video_stem"] == "nba__g1_s60"


# --- attempt 2: the salted selection rule and the held-out split (hand-pinned) -------------

from scripts.platformkit.tracking.g330_attempt2 import (  # noqa: E402
    SALT, eval_indices, game_id, heldout_split, heldout_stats, rank_key, reprojection_errors,
    select_sections,
)

# Hand-pinned candidate corpus: five eligible sections over three games, plus one section
# below the height gate that must never be selected.
CANDIDATES = [
    ("nba__0022400909_s4453.mp4", 720),
    ("nba__0022400909_s5217.mp4", 720),
    ("nba__0022401198_s2784.mp4", 720),
    ("nba__0022500081_s4812.mp4", 720),
    ("basketball__nbl-WTEUwPcy7X8_s90.mp4", 1080),
    ("nba__0022500575_s1500.mp4", 360),
]


def test_game_id_strips_only_the_section_suffix():
    assert game_id("nba__0022400909_s4453.mp4") == "nba__0022400909"
    assert game_id("basketball__nbl-WTEUwPcy7X8_s90.mp4") == "basketball__nbl-WTEUwPcy7X8"
    assert game_id("not_a_section.txt") == "not_a_section.txt"


def test_rank_key_is_the_sealed_salted_digest():
    # Pinned by hand from the sealed salt; a changed salt must change the order.
    assert rank_key("nba__0022500081_s4812.mp4").startswith("10efbb5798d8a0b4")
    assert rank_key("basketball__nbl-WTEUwPcy7X8_s90.mp4").startswith("005958e35b7c845d")
    assert rank_key("nba__0022500081_s4812.mp4", "other-salt") != rank_key(
        "nba__0022500081_s4812.mp4", SALT)


def test_selection_takes_distinct_games_by_the_salted_rank_and_is_not_a_head_slice():
    picked = select_sections(CANDIDATES)
    assert picked == ["basketball__nbl-WTEUwPcy7X8_s90.mp4",
                      "nba__0022500081_s4812.mp4",
                      "nba__0022401198_s2784.mp4"]
    assert len({game_id(name) for name in picked}) == 3
    # The prohibited head slice would keep the first three sorted names; this rule does not.
    head = sorted(name for name, height in CANDIDATES if height >= 720)[:3]
    assert picked != head
    # The section below the height gate is never eligible.
    assert "nba__0022500575_s1500.mp4" not in picked


def test_selection_falls_through_to_the_next_game_when_a_game_is_absent():
    thinned = [row for row in CANDIDATES if not row[0].startswith("nba__0022500081")]
    picked = select_sections(thinned)
    assert picked[0] == "basketball__nbl-WTEUwPcy7X8_s90.mp4"
    assert len({game_id(name) for name in picked}) == 3
    assert "nba__0022500081_s4812.mp4" not in picked


def test_eval_indices_span_the_file_and_never_start_at_the_head():
    idx = eval_indices(3957)
    assert len(idx) == 40
    assert idx[0] == 49 and idx[1] == 147 and idx[-1] == 3871
    assert idx[0] > 0
    assert idx[-1] > 0.9 * 3957
    assert eval_indices(6527)[0] == 81 and eval_indices(6527)[-1] == 6438


def test_heldout_split_is_even_fit_and_odd_held():
    fit, held = heldout_split(9)
    assert fit == [0, 2, 4, 6, 8]
    assert held == [1, 3, 5, 7]
    assert not set(fit) & set(held)
    assert heldout_split(3) == ([0, 2], [1])


def test_reprojection_errors_are_hand_pinned_under_a_known_translation():
    homography = [[1.0, 0.0, 10.0], [0.0, 1.0, 20.0], [0.0, 0.0, 1.0]]
    errors = reprojection_errors(homography, [(0.0, 0.0), (5.0, 5.0)],
                                 [(10.0, 20.0), (15.0, 75.0)])
    assert abs(errors[0]) < 1e-6
    assert abs(errors[1] - 50.0) < 1e-6


FRAME_PTS = [(10, 10), (300, 40), (80, 220), (420, 180), (150, 90), (500, 260),
             (60, 300), (360, 320), (230, 150), (470, 60), (120, 400), (400, 430)]


def _pano_pts():
    """Exact translation by (10, 20); three of the six HELD-OUT points are pushed 50 px off it.

    Half the held-out set off by 50 px puts the median between the two groups, so the median is
    pinned by the construct rather than by one arbitrary point.
    """
    shifted = [(x + 10, y + 20) for x, y in FRAME_PTS]
    for odd in (7, 9, 11):
        shifted[odd] = (shifted[odd][0] + 50, shifted[odd][1])
    return shifted


def test_heldout_stats_scores_the_half_that_did_not_fit_it():
    import pytest
    pytest.importorskip("cv2")
    stats = heldout_stats(FRAME_PTS, _pano_pts(), 5.0)
    assert stats["n_fit"] == 6 and stats["n_held"] == 6
    # Every FIT correspondence is exact, so the in-sample mask is full.
    assert stats["fit_inliers"] == 6
    # Three held-out points sit on the same translation; three were pushed 50 px away.
    assert stats["held_inliers"] == 3
    assert abs(stats["held_median_px"] - 25.0) < 1e-3


def test_heldout_stats_declines_a_frame_whose_halves_are_too_short():
    import pytest
    pytest.importorskip("cv2")
    assert heldout_stats(FRAME_PTS[:6], _pano_pts()[:6], 5.0) is None


def test_recorder_keeps_capturing_after_a_drain():
    """Regression: a drain that rebinds the list orphans the wrapper closure and drops every
    later call, so one arm looked as though it had never fitted a homography at all."""
    import pytest
    pytest.importorskip("cv2")
    import cv2
    import numpy as np
    from scripts.platformkit.tracking.g330_attempt2 import MatchRecorder
    src = np.float32(FRAME_PTS).reshape(-1, 1, 2)
    dst = np.float32(_pano_pts()).reshape(-1, 1, 2)
    original = cv2.findHomography
    with MatchRecorder() as recorder:
        assert cv2.findHomography is not original
        cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        first = recorder.drain()
        cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        second = recorder.drain()
    assert len(first) == 1
    assert len(second) == 2
    assert recorder.drain() == []
    assert cv2.findHomography is original
