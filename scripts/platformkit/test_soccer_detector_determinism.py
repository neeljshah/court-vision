import subprocess
import sys
from pathlib import Path



def _count_in_fresh_process(repo_root: Path, cwd: Path) -> str:
    script = """
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
sys.path.insert(0, str(repo_root))
from scripts.platformkit.detection.deterministic import build_soccer_packet_detector, read_packet_frame
from scripts.platformkit.soccer_s1_adjudication_packet import _valid_detection_count

frame_root = repo_root / 'scripts' / 'platformkit' / 'a1_artifacts' / 'soccer_s1' / 'frames'
detector = build_soccer_packet_detector()
counts = [_valid_detection_count(detector(read_packet_frame(frame_root / ('S1_%04d.jpg' % index)))) for index in range(1, 6)]
print(','.join(str(count) for count in counts))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(repo_root)],
        capture_output=True,
        check=True,
        cwd=cwd,
        text=True,
    )
    return result.stdout.strip().splitlines()[-1]


def test_packet_detector_count_is_repeatable_in_two_processes(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    first = _count_in_fresh_process(repo_root, tmp_path)
    second = _count_in_fresh_process(repo_root, tmp_path)
    assert first == second
