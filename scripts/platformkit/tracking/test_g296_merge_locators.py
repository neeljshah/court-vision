"""Per-file test for the G296 two-locator merge: matching, radius, and the conservative consensus."""
import csv

from scripts.platformkit.tracking.g296_merge_locators import (
    MATCH_RADIUS_PX,
    agreement,
    consensus,
    load_points,
    match_frame,
)

HEADER = [
    "source_frame", "person_index", "role", "feet_visible",
    "foot_x_px", "foot_y_px", "confidence", "note",
]


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)


def test_feet_not_visible_is_counted_not_guessed_into_a_position(tmp_path):
    # A player whose feet are occluded must never acquire a coordinate; it is counted apart.
    path = tmp_path / "a.csv"
    _write(path, [
        [1, 0, "player_on_court", "true", "100", "200", "confident", ""],
        [1, 1, "player_on_court", "false", "", "", "guess", "occluded"],
        [1, 2, "official", "true", "300", "400", "confident", ""],
    ])
    located, no_coord = load_points(path)
    assert located[1] == [(100.0, 200.0, "confident")]  # the official is excluded by role
    assert no_coord == 1


def test_matching_respects_the_radius_and_is_one_to_one():
    a = [(0.0, 0.0, "confident"), (500.0, 0.0, "confident")]
    b = [(10.0, 0.0, "confident"), (0.0, 5.0, "approximate")]
    pairs, used_a, used_b = match_frame(a, b, radius=MATCH_RADIUS_PX)
    # a[0] pairs with its nearest (b[1] at 5 px); b[0] at 10 px cannot reuse a[0], and a[1]
    # is 490 px away, so b[0] stays unmatched rather than pairing across the radius.
    assert len(pairs) == 1
    assert used_a == {0} and used_b == {1}
    assert pairs[0][2] == 5.0
    assert match_frame(a, b, radius=1.0)[0] == []  # nothing pairs inside 1 px


def test_agreement_and_consensus_keep_only_what_both_passes_saw(tmp_path):
    _write(tmp_path / "g296a_located_players_artifact" / "located_players.csv", [
        [7, 0, "player_on_court", "true", "100", "200", "confident", ""],
        [7, 1, "player_on_court", "true", "900", "200", "confident", ""],
    ])
    _write(tmp_path / "g296b_located_players_artifact" / "located_players.csv", [
        [7, 0, "player_on_court", "true", "120", "200", "approximate", ""],
    ])
    a = tmp_path / "g296a_located_players_artifact" / "located_players.csv"
    b = tmp_path / "g296b_located_players_artifact" / "located_players.csv"
    result = agreement(a, b)
    assert (result["matched_pairs"], result["pass_a_only"], result["pass_b_only"]) == (1, 1, 0)
    assert result["jaccard"] == 0.5
    assert result["median_offset_px"] == 20.0
    rows = consensus(a, b)
    # Consensus is the midpoint of what BOTH saw; the point only pass A saw is dropped.
    assert len(rows) == 1
    assert (rows[0]["foot_x_px"], rows[0]["foot_y_px"]) == (110.0, 200.0)
