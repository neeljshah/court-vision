from scripts.platformkit.tracking.g286_what_is_at_footpoint import (
    CROP_HEIGHT,
    CROP_WIDTH,
    direction,
    inside_crop,
)


def test_crop_membership_and_direction_use_the_declared_native_pixel_geometry() -> None:
    point = {"foot_x_px": 500.0, "foot_y_px": 500.0}
    assert inside_crop(point, {"foot_x_px": 756.0, "foot_y_px": 820.0})
    assert not inside_crop(point, {"foot_x_px": 756.1, "foot_y_px": 820.0})
    assert (CROP_WIDTH, CROP_HEIGHT) == (512, 640)
    assert direction(point, {"foot_x_px": 500.0, "foot_y_px": 400.0}) == "BELOW"
    assert direction(point, {"foot_x_px": 800.0, "foot_y_px": 500.0}) == "LEFT"
