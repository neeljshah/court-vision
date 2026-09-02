from pathlib import Path

from scripts.platformkit.detection.deterministic import build_soccer_packet_detector, read_packet_frame
from scripts.platformkit.soccer_s1_adjudication_packet import _valid_detection_count


def test_packet_detector_count_is_repeatable_on_five_frames() -> None:
    root = Path("scripts/platformkit/a1_artifacts/soccer_s1/frames")
    frames = [root / ("S1_%04d.jpg" % index) for index in range(1, 6)]
    detector = build_soccer_packet_detector()
    first = [_valid_detection_count(detector(read_packet_frame(path))) for path in frames]
    second = [_valid_detection_count(detector(read_packet_frame(path))) for path in frames]
    assert first == second
