"""Adapter_run must actually request the image-space path, or it is inert."""
from scripts.platformkit.adapter_run import ADAPTERS, IMAGE_SPACE, PLAYER_ONLY, TEACHER_META


def test_soccer_is_asked_for_image_space():
    """The court path emits 0 rows for soccer; without this the detector's
    output is discarded and the provenance work never runs in production."""
    assert "soccer" in IMAGE_SPACE


def test_uncalibratable_broadcast_sports_are_asked_for_image_space():
    assert {"baseball", "basketball", "football"} <= IMAGE_SPACE


def test_basketball_is_registered_for_player_only_image_space_output():
    assert ADAPTERS["basketball"] == (
        "domains.basketball.tracking.adapter", "BasketballAdapter"
    )
    assert "basketball" in PLAYER_ONLY


def test_image_space_sports_are_known_adapters():
    assert IMAGE_SPACE <= set(ADAPTERS) | PLAYER_ONLY


def test_adapter_run_passes_the_flag():
    source = open("scripts/platformkit/adapter_run.py", encoding="utf-8").read()
    assert 'options["image_space"] = True' in source


def test_baseball_requests_and_persists_teacher_metadata():
    source = open("scripts/platformkit/adapter_run.py", encoding="utf-8").read()
    assert TEACHER_META == {"baseball"}
    assert 'options["compute_command"] = True' in source
    assert "write_teacher_meta(teacher_metadata, game_id, sport, output_dir)" in source


def test_adapter_run_has_a_bounded_frame_override_for_real_clip_measurements():
    source = open("scripts/platformkit/adapter_run.py", encoding="utf-8").read()
    assert 'parser.add_argument("--max-frames", type=int, default=30000)' in source


def test_adapter_run_maps_probed_dimensions_to_harness_resolution_metadata():
    source = open("scripts/platformkit/adapter_run.py", encoding="utf-8").read()
    assert 'metadata["resolution"] = "{}x{}".format(width, height)' in source


def test_adapter_ball_telemetry_declarations_match_detector_capabilities():
    from scripts.platformkit.adapter_run import BALL_TELEMETRY_AVAILABLE

    assert BALL_TELEMETRY_AVAILABLE["tennis"] is True
    assert all(BALL_TELEMETRY_AVAILABLE[sport] is False for sport in (
        "soccer", "baseball", "football", "basketball", "wnba",
        "ncaa_basketball", "nba",
    ))
