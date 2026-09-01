"""Adapter_run must actually request the image-space path, or it is inert."""
from scripts.platformkit.adapter_run import IMAGE_SPACE, PLAYER_ONLY, ADAPTERS


def test_soccer_is_asked_for_image_space():
    """The court path emits 0 rows for soccer; without this the detector's
    output is discarded and the provenance work never runs in production."""
    assert "soccer" in IMAGE_SPACE


def test_image_space_sports_are_known_adapters():
    assert IMAGE_SPACE <= set(ADAPTERS) | PLAYER_ONLY


def test_adapter_run_passes_the_flag():
    source = open("scripts/platformkit/adapter_run.py", encoding="utf-8").read()
    assert 'options["image_space"] = True' in source
