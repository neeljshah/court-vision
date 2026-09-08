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
