import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from scripts.platformkit.tracking.g220c_amateur_footage import (
    CANDIDATES, LOCAL_CAP_BYTES, MERGING_SELECTOR, POD_CAP_BYTES, SECTION_SECONDS,
    SECTION_TIMEOUT_SECONDS, WHOLE_FETCH_TIMEOUT_SECONDS,
    _command, section_for,
)
from scripts.platformkit.section_fallback import section_seconds


def test_construct_selector_and_caps_are_fixed():
    assert [item.youtube_id for item in CANDIDATES] == [
        "jh3fnwMi7dM", "qpZfGp_fScU", "1MwO3CDkeeM", "3asBuhRd_LI",
        "lAs8JaoWNwg", "XwpLBtt1G2g",
    ]
    assert SECTION_SECONDS == 960
    assert LOCAL_CAP_BYTES == 20_000_000_000
    assert POD_CAP_BYTES == 4_000_000_000
    assert SECTION_TIMEOUT_SECONDS == 90
    assert WHOLE_FETCH_TIMEOUT_SECONDS == 900
    assert all(section_seconds(section_for(item))[1] == SECTION_SECONDS for item in CANDIDATES)


def test_command_uses_merging_selector_and_optional_section():
    command = _command(CANDIDATES[0], Path("clip.mp4"), "*00:10:00-00:26:00", 1234)
    assert command[command.index("-f") + 1] == MERGING_SELECTOR
    assert MERGING_SELECTOR == (
        "bv*[protocol*=m3u8][height<=1080][height>=720]+ba[protocol*=m3u8]"
    )
    assert command[command.index("--download-sections") + 1] == "*00:10:00-00:26:00"
    assert command[command.index("--max-filesize") + 1] == "1234"
    whole = _command(CANDIDATES[0], Path("whole.mp4"), None, 1234)
    assert "--download-sections" not in whole


def test_timeout_terminates_only_its_own_process_tree():
    from scripts.platformkit.tracking.g220c_amateur_footage import _run

    process = Mock(pid=123, communicate=Mock(side_effect=[subprocess.TimeoutExpired([], 1), ("", "")]))
    with patch("scripts.platformkit.tracking.g220c_amateur_footage.subprocess.Popen", return_value=process), \
         patch("scripts.platformkit.tracking.g220c_amateur_footage.subprocess.run") as kill:
        with pytest.raises(subprocess.TimeoutExpired):
            _run(["yt-dlp"], 1)
    assert kill.call_args.args[0] == ["taskkill", "/PID", "123", "/T", "/F"]
