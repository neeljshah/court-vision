"""Focused unit tests for G129 mechanism classification."""
from scripts.platformkit.g129_more_candidates_mechanism import classify_loss


def test_classify_loss_names_the_first_changed_stage() -> None:
    assert classify_loss("g120_merge", 3)[0] == "pre-group fragment merge"
    assert classify_loss("g123_clahe", 0)[0] == "LSD proposal generation"
