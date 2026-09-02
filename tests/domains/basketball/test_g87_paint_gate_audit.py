"""Focused regression check for the committed G87 hand-geometry replay."""

from pathlib import Path

from scripts.platformkit.g87_paint_gate_audit import evaluate_all, load_hand_marks


def test_g87_replays_exactly_twelve_manual_four_line_marks() -> None:
    marks = load_hand_marks()
    results = evaluate_all()

    assert len(marks) == len(results) == 12
    assert all(set(mark["lines"]) == {"baseline", "free_throw", "lane_low", "lane_high"} for mark in marks)
    assert all(result["gate"] in {"PASS", "parallel", "orthogonal", "post_angle"} for result in results)
    assert [(result["frame_index"], result["verdict"], result["gate"]) for result in results] == [
        (19200, "PASS", "PASS"), (1560, "PASS", "PASS"), (2483, "REJECT", "parallel"),
        (5760, "PASS", "PASS"), (192, "PASS", "PASS"), (3648, "PASS", "PASS"),
        (11904, "PASS", "PASS"), (8448, "PASS", "PASS"), (13632, "PASS", "PASS"),
        (360, "PASS", "PASS"), (2640, "PASS", "PASS"), (4080, "PASS", "PASS"),
    ]
    evidence_dir = Path("docs/evidence/tracking/g87_paint_gate")
    assert (evidence_dir / "measurements.csv").is_file()
    assert len(list((evidence_dir / "renders").glob("*.jpg"))) == 12
