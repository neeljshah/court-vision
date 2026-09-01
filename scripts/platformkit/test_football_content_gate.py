from scripts.platformkit.football_content_gate import FootballFrameEvidence, decide


def test_repeated_yard_lines_are_required_for_acceptance():
    verdict = decide([
        FootballFrameEvidence(0.35, 8), FootballFrameEvidence(0.30, 7),
        FootballFrameEvidence(0.28, 3),
    ])

    assert verdict.decision == "accept"
    assert verdict.reason == "repeated_yard_line_structure"


def test_green_soccer_like_structure_is_rejected_fail_closed():
    verdict = decide([FootballFrameEvidence(0.45, 3)] * 5)

    assert verdict.decision == "reject"
    assert verdict.reason == "yard_line_structure_absent_fail_closed"


def test_non_field_and_missing_samples_are_rejected_fail_closed():
    assert decide([FootballFrameEvidence(0.01, 0)] * 3).reason == "no_field_surface_fail_closed"
    assert decide([]).reason == "no_readable_sample_fail_closed"
