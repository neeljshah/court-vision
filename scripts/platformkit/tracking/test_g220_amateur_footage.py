from pathlib import Path

from scripts.platformkit.tracking.g220_amateur_footage import (
    CANDIDATES,
    CAP_BYTES,
    FETCH_TIMEOUT_SECONDS,
    SECTION_SECONDS,
    download_command,
    section_for,
    write_records,
)
from scripts.platformkit.section_fallback import section_seconds


def test_reviewed_construct_is_exhaustive_and_bounded():
    assert [candidate.youtube_id for candidate in CANDIDATES] == [
        "jh3fnwMi7dM", "qpZfGp_fScU", "1MwO3CDkeeM", "3asBuhRd_LI",
        "lAs8JaoWNwg", "XwpLBtt1G2g",
    ]
    assert len(CANDIDATES) == 6
    assert SECTION_SECONDS == 960
    assert CAP_BYTES == 4_000_000_000
    assert FETCH_TIMEOUT_SECONDS == 30
    assert all(section_seconds(section_for(candidate))[1] == SECTION_SECONDS
               for candidate in CANDIDATES)


def test_command_uses_cookie_backed_section_and_remaining_cap():
    command = download_command(CANDIDATES[0], Path("clip.mp4"), "*00:10:00-00:26:00",
                               "b[height<=1080][height>=720]", 1234)
    assert "--cookies" in command
    assert command[command.index("--socket-timeout") + 1] == "20"
    assert command[command.index("--download-sections") + 1] == "*00:10:00-00:26:00"
    assert command[command.index("--max-filesize") + 1] == "1234"
    assert command[command.index("-f") + 1] == "b[height<=1080][height>=720]"


def test_record_writer_preserves_a_partial_audit(tmp_path: Path):
    records = tmp_path / "records.json"
    write_records(records, {"records": [{"outcome": "in_progress"}]})
    assert records.read_text(encoding="utf-8") == '{\n  "records": [\n    {\n      "outcome": "in_progress"\n    }\n  ]\n}\n'
