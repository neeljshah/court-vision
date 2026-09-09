"""Construct tests for the G357 fix-1b even-sampling and id/competition helpers."""
import hashlib
from pathlib import Path

from scripts.platformkit.tracking.g357_fix1b_census import (
    base_game_id, competition_of, even_sample_indices,
)


def test_base_game_id_strips_segment_suffix_only() -> None:
    assert base_game_id("fiba-jFUMvm_epUE_s5410") == "fiba-jFUMvm_epUE"
    assert base_game_id("1zPhldjbJnU_s90") == "1zPhldjbJnU"
    assert base_game_id("no_suffix_here") == "no_suffix_here"


def test_competition_prefers_known_league_prefix_over_single_letter_false_positive() -> None:
    assert competition_of("fiba-jFUMvm_epUE_s5410", "basketball") == "fiba"
    assert competition_of("UPco-jzOoEg_s2796", "ncaa_basketball") == "UPco"
    # bare video ids with no recognized league prefix fall back to the ledger sport,
    # including ones that would false-positive match a naive "^[A-Za-z]+-" prefix regex.
    assert competition_of("1zPhldjbJnU_s90", "wnba") == "wnba"
    assert competition_of("N6xk3-abcdefghijk_s90", "ncaa_basketball") == "ncaa_basketball"


def test_even_sample_never_head_slices_and_spans_the_set() -> None:
    small = even_sample_indices(32)
    assert small == list(range(32))  # n <= 40: take ALL

    idx = even_sample_indices(61)
    assert len(idx) >= 30
    assert idx[0] <= 5 and idx[-1] >= 55  # spans start and end, not a head slice
    assert idx == sorted(set(idx))


def test_fix1b_prereg_seal_normalizes_crlf_without_git_history() -> None:
    path = Path("docs/evidence/tracking/g357_prereg_fix1b_2026-09-08.md")
    normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    body, seal = normalized.rsplit(b"SEAL sha256 ", 1)
    assert b"\n" not in seal.strip()
    assert hashlib.sha256(body).hexdigest() == seal.strip().decode("ascii")
