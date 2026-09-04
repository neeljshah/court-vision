"""Focused checks for G249's remote court-corner survey command."""
from scripts.platformkit.tracking import g249_court_corner_survey as subject


def test_remote_survey_is_evenly_spaced_and_never_seeks() -> None:
    command = subject.remote_survey_command(60)
    assert command[:2] == ["ssh", "config.pod"]
    assert "select=not(mod(n\\,60))" in command[2]
    assert "scale=640:360" in command[2]
    assert " -ss " not in command[2]


def test_remote_survey_rejects_nonpositive_stride() -> None:
    try:
        subject.remote_survey_command(0)
    except ValueError as error:
        assert str(error) == "stride must be positive"
    else:
        raise AssertionError("zero stride was accepted")


def test_local_probe_rejects_nonpositive_sample_count(tmp_path) -> None:
    try:
        subject.write_local_probe_sheet(tmp_path / "missing.mp4", tmp_path / "sheet.jpg", 0)
    except ValueError as error:
        assert str(error) == "samples must be positive"
    else:
        raise AssertionError("zero sample count was accepted")
