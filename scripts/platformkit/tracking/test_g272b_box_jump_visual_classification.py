from scripts.platformkit.tracking.g272b_box_jump_visual_classification import (
    CROP_HEIGHT,
    CROP_WIDTH,
    _crop,
    blind_order,
    select_evenly,
)


def _steps():
    return [
        {"source_frame": frame, "prior_source_frame": frame - 1, "track_id": frame % 7,
         "image_bottom_centre_displacement_px": 100.0, "speed_ft_per_s": 41.0}
        for frame in range(100, 196)
    ]


def test_even_sample_covers_every_time_bin_and_prefers_distinct_ids():
    sample = select_evenly(_steps(), sample_size=12)
    assert [row["time_bin"] for row in sample] == list(range(1, 13))
    assert len({row["track_id"] for row in sample}) >= 7
    assert sample[0]["source_frame"] < sample[-1]["source_frame"]
    ordered = blind_order(sample)
    assert sorted(row["blind_index"] for row in ordered) == list(range(1, 13))


def test_crop_is_fixed_size_and_keeps_the_retained_footpoint_at_centre():
    import numpy as np

    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    image[10, 10] = (1, 2, 3)
    crop = _crop(image, 10.0, 10.0)
    assert crop.shape == (CROP_HEIGHT, CROP_WIDTH, 3)
    assert tuple(crop[CROP_HEIGHT // 2, CROP_WIDTH // 2]) == (1, 2, 3)
