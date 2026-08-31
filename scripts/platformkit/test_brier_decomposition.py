"""Synthetic coverage for the Murphy decomposition comparison panel."""
from scripts.platformkit.brier_decomposition import decompose, panel


def test_identity_holds_and_shrunk_forecaster_is_flagged() -> None:
    outcomes = [0, 0, 0, 0, 1, 1, 1, 1]
    calibrated = [.9, .9, .9, .9, .1, .1, .1, .1]
    shrunk = [.5] * len(outcomes)
    result = decompose(calibrated, outcomes)
    assert abs(result["brier"] - (result["reliability"] - result["resolution"] + result["uncertainty"])) <= 1e-9
    output = panel({"calibrated": (calibrated, outcomes), "shrunk": (shrunk, outcomes)})
    shrunk_row = next(line for line in output.splitlines() if line.startswith("shrunk |"))
    assert "improvement may be shrink-to-base-rate -- verify resolution" in shrunk_row
