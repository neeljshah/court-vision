"""Unit tests for the numeral registration probe's fail-closed contracts."""
import cv2
import numpy as np

from domains.football.tracking.numeral_registration import NumeralRead, _value, solve


def test_digits_accept_valid_joined_or_split_field_numerals() -> None:
    assert _value("30") == 30
    assert _value("3") == 30
    assert _value("99") is None


def test_point_solver_holds_out_one_recognized_numeral() -> None:
    field_to_image = np.array(((2.0, 0.0, 20.0), (0.0, 1.5, 10.0), (0.0, 0.0, 1.0)))
    image_to_field = np.linalg.inv(field_to_image)
    readings = []
    for number in (10, 20, 30, 40):
        point = np.array((number * 3.0, 27.0, 1.0))
        pixel = field_to_image @ point
        pixel /= pixel[2]
        line = image_to_field.T @ np.array((1.0, 0.0, -number * 3.0))
        readings.append(NumeralRead(number, .95, (pixel[0] - 4, pixel[1] - 4.5, 8, 9), line))
    result = solve(readings, side=-1)
    assert result.homography is not None
    assert result.used == 3
    assert result.held_out_error_ft is not None and result.held_out_error_ft < 1e-3
    assert result.scale_error_pct is not None and result.scale_error_pct < 1e-3


def test_solver_rejects_fewer_than_three_recognized_numerals() -> None:
    line = np.array((1.0, 0.0, -30.0))
    result = solve([NumeralRead(10, .9, (20, 30, 8, 6), line)], side=-1)
    assert result.homography is None
    assert result.used == 0
