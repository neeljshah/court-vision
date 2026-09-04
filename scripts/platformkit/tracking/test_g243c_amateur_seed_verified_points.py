"""Focused checks for the G243c frame-exact remote decode helper."""
from scripts.platformkit.tracking import g243c_amateur_seed_verified_points as subject


def test_remote_command_uses_select_without_input_side_seek() -> None:
    command = subject.remote_decode_command(123)
    assert command[:2] == ["ssh", "config.pod"]
    assert "select=eq(n\\,123)" in command[2]
    assert " -ss " not in command[2]


def test_remote_command_rejects_negative_frame() -> None:
    try:
        subject.remote_decode_command(-1)
    except ValueError as error:
        assert str(error) == "frame must be non-negative"
    else:
        raise AssertionError("negative frame was accepted")


def test_survey_command_has_even_stride_selection() -> None:
    command = subject.remote_survey_command(60)
    assert "select=not(mod(n\\,60))" in command[2]
    assert "scale=320:180" in command[2]
