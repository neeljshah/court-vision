"""Focused G372 sidecar and preregistration contract tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g372_source_sidecar import (
    SIDE_FIELDS, append_claim, parse_ffprobe, sha256_file, terminal_failure, write_sidecar,
)


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g372_inline_source_pinning_2026-09-10/g372_prereg_2026-09-10.md"


def _payload() -> dict:
    return {"source_path": "clip.mp4", "source_sha256": "a" * 64, "source_bytes": 9,
            "ffprobe": {"status": "OK"}, "crop_rule": "TOPCUT=60",
            "route_digest": {"route.py": "b" * 64}, "weight_digest": {},
            "deploy_manifest_sha256": "c" * 64, "claim_utc": "2026-09-10T00:00:00Z",
            "daemon_pid": 1, "terminal_diagnostic": ""}


def _seal(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    prefix = data[:data.index(b"SEAL sha256 ")]
    return hashlib.sha256(prefix).hexdigest()


def test_g372_sidecar_schema_and_immutable_write(tmp_path: Path) -> None:
    target = tmp_path / "identity.json"
    write_sidecar(target, _payload())
    assert tuple(json.loads(target.read_text()).keys()) == tuple(sorted(SIDE_FIELDS))
    with pytest.raises(FileExistsError):
        write_sidecar(target, _payload())


def test_g372_byte_flip_changes_sha256(tmp_path: Path) -> None:
    target = tmp_path / "source.bin"
    target.write_bytes(b"abcdef")
    before = sha256_file(target)
    target.write_bytes(b"abcxef")
    assert sha256_file(target) != before


def test_g372_deterministic_fixed_input_writes(tmp_path: Path) -> None:
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    write_sidecar(first, _payload())
    write_sidecar(second, _payload())
    assert first.read_bytes() == second.read_bytes()


def test_g372_negative_pts_fallback_is_estimate() -> None:
    probe = parse_ffprobe(json.dumps({"streams": [{"start_time": "-2.0"}],
                                      "frames": [{"pts_time": "-3.0"}]}))
    assert probe["first_pts"] == "-2.0"
    assert probe["start_time_kind"] == "ESTIMATE"


def test_g372_claim_journal_covers_failed_reservation(tmp_path: Path) -> None:
    journal, sidecar = tmp_path / "claims.jsonl", tmp_path / "identity.json"
    append_claim(journal, terminal_failure("fiba-video_s90", sidecar, "hash_error"))
    row = json.loads(journal.read_text())
    assert row["state"] == "TERMINAL_ERROR"
    assert row["source_identity_path"] == str(sidecar)


def test_g372_preregistration_seal_normalizes_crlf() -> None:
    line = next(line for line in PREREG.read_text().splitlines() if line.startswith("SEAL sha256 "))
    assert _seal(PREREG) == line.removeprefix("SEAL sha256 ")
