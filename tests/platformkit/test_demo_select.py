from scripts.platformkit.demo_render import Observation
from scripts.platformkit.demo_select import (
    court_polygon_share,
    npb_person_box_wide,
    precompute_wide_flags,
    select_wide_window,
)


def test_selector_rejects_denser_closeup_window() -> None:
    rows = {frame: [Observation(frame, "a", "player", 1.0, 1.0)] for frame in range(8)}
    rows.update({frame: [Observation(frame, "b", "player", 1.0, 1.0)] * 3 for frame in range(8, 16)})
    result = select_wide_window(rows, {frame: frame < 8 for frame in range(16)}, (0, 8), 8)
    assert result.start_frame == 0
    assert result.wide_fraction == 1.0


def test_npb_small_people_and_court_polygon_gate() -> None:
    assert npb_person_box_wide(((0, 0, 10, 10),) * 4, 100)
    assert not npb_person_box_wide(((0, 0, 10, 16),) * 4, 100)
    import numpy as np

    assert court_polygon_share(np.zeros((10, 10, 3), dtype=np.uint8), np.array(((0, 0), (9, 0), (9, 9), (0, 9)))) > 0.9


def test_precompute_decodes_once_at_coarse_stride() -> None:
    import numpy as np

    class Capture:
        def __init__(self) -> None:
            self.reads = 0
            self.grabs = 0

        def read(self) -> tuple[bool, np.ndarray]:
            frame = np.full((1, 1, 3), self.reads, dtype=np.uint8)
            self.reads += 1
            return True, frame

        def grab(self) -> bool:
            self.grabs += 1
            return True

    capture = Capture()
    flags = precompute_wide_flags(capture, 10, lambda frame: bool(frame[0, 0, 0] % 2), 3)  # type: ignore[arg-type]
    assert capture.reads == 4
    assert capture.grabs == 6
    assert flags == {0: False, 3: True, 6: False, 9: True}
