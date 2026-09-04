from scripts.platformkit.tracking.g285_per_person_recall import validate_verdicts, wilson


def test_wilson_known_value():
    result = wilson(218, 524)
    assert round(result["estimate"], 6) == 0.416031
    assert round(result["lower"], 6) == 0.374588
    assert round(result["upper"], 6) == 0.458695


def test_verdict_validation_allows_two_markers_on_one_player():
    frames = [{"blind_id": "1", "players_visible_on_court": "2"}]
    markers = [{"blind_id": "1", "marker_index": "0"}, {"blind_id": "1", "marker_index": "1"}]
    people = [
        {"blind_id": "1", "player_slot": "1", "verdict": "MATCHED", "marker_index": "0", "near_boundary": "NO"},
        {"blind_id": "1", "player_slot": "2", "verdict": "UNMATCHED", "marker_index": "", "near_boundary": "NO"},
    ]
    marker_verdicts = [
        {"blind_id": "1", "marker_index": "0", "verdict": "MATCHED", "player_slot": "1"},
        {"blind_id": "1", "marker_index": "1", "verdict": "MATCHED", "player_slot": "1"},
    ]
    validate_verdicts(frames, markers, people, marker_verdicts)
