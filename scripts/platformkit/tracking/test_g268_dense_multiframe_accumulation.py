"""Focused synthetic checks for G268's all-frame objective."""

import numpy as np

from scripts.platformkit.tracking.g268_dense_multiframe_accumulation import LINES, joint_fit, line, project, write_contact_sheet


def test_joint_fit_recovers_one_map_from_dense_frame_specific_support() -> None:
    truth = np.array(((0.05, 0.01, 2.0), (-0.004, 0.11, -40.0), (0.00003, 0.001, 1.0)))
    maps, items = {}, []
    for frame in range(41):
        motion = np.array(((1.0, 0.0, frame * 0.3), (0.0, 1.0, frame * 0.1), (0.0, 0.0, 1.0)))
        maps[frame] = (motion, {})
        current_to_court = truth @ np.linalg.inv(motion)
        for name, endpoints in LINES:
            court = np.asarray(endpoints, float)
            points = np.linspace(court[0], court[1], 11)
            items.append({"frame": frame, "primitive": name, "image_support_px": project(points, np.linalg.inv(current_to_court))})
    fitted, result = joint_fit(items, maps, truth * np.array(((1.01, 1, 1), (1, 0.99, 1), (1, 1, 1))))
    assert result.success
    assert result.cost < 0.01
    for _name, endpoints in LINES:
        court = np.linspace(np.asarray(endpoints)[0], np.asarray(endpoints)[1], 11)
        mapped = project(project(court, np.linalg.inv(truth)), fitted)
        assert np.max(np.abs(mapped @ line(np.asarray(endpoints))[:2] + line(np.asarray(endpoints))[2])) < 0.01


def test_contact_sheet_accepts_five_even_frames(tmp_path) -> None:
    images = {frame: np.zeros((1080, 1920, 3), dtype=np.uint8) for frame in (1, 2, 3, 4, 5)}
    output = tmp_path / "context.jpg"
    write_contact_sheet(images, output)
    assert output.exists()
