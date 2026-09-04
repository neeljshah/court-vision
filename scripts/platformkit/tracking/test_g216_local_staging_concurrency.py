"""Focused tests for G216's safe reuse of the G200 route harness."""
from scripts.platformkit.tracking.g216_local_staging_concurrency import (
    STAGE_PREFIX,
    _reads_are_valid,
    _stage_is_valid,
    cleanup_script,
    read_script,
    stage_script,
)


def test_g216_scripts_stage_one_file_measure_direct_reads_and_clean_only_own_path() -> None:
    stage_dir = f"{STAGE_PREFIX}unit"
    stage = stage_script(stage_dir)
    reads = read_script(stage_dir)
    cleanup = cleanup_script(stage_dir)

    assert "--reflink=never" in stage
    assert "source_md5" in stage and "staged_md5" in stage
    assert "network_single" in reads and "local_four" in reads
    assert "iflag=direct" in reads and "dd if=\"$INPUT\" of=/dev/null" in reads
    assert 'rm", "-f", "--", staged' in cleanup
    assert "rmdir" in cleanup and 'rm", "-f", "--", staged' in cleanup


def test_g216_accepts_only_parity_checked_stages_and_successful_direct_reads() -> None:
    stage = {"copy_exit_code": 0, "source_size_bytes": 7, "staged_size_bytes": 7,
             "source_md5": "abc", "staged_md5": "abc"}
    assert _stage_is_valid(stage, 0)
    assert not _stage_is_valid({**stage, "staged_md5": "def"}, 0)
    assert _reads_are_valid({"measurements": [{"jobs": [{"exit_code": 0}]}]})
    assert not _reads_are_valid({"measurements": [{"jobs": [{"exit_code": 1}]}]})
