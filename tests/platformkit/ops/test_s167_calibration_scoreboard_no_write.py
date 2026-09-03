"""Construct coverage for S167's read-only scoreboard CLI path."""

from scripts.platformkit import calibration_scoreboard as scoreboard
from scripts.platformkit import calibration_scoreboard_cli


def test_no_write_flag_passes_false_to_scoreboard_builder(monkeypatch, capsys) -> None:
    """The opt-in CLI flag preserves computation while disabling both artifact writers."""
    seen: dict[str, bool] = {}

    def fake_builder(*, write: bool):
        seen["write"] = write
        return [{
            "sport": "NBA",
            "baseline": {"n": 2, "ece": 0.2},
            "improved": {"n": 2, "ece": 0.1},
            "method": "construct",
        }]

    monkeypatch.setattr(scoreboard, "build_calibration_scoreboard", fake_builder)

    assert scoreboard.main(["--no-write"]) == 0
    assert seen == {"write": False}
    assert "Artifact not written (--no-write)." in capsys.readouterr().out

    assert calibration_scoreboard_cli.main([]) == 0
    assert seen == {"write": True}
    assert capsys.readouterr().out.endswith("Artifact written.\n")
