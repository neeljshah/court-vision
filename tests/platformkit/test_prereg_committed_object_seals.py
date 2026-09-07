"""Behavioral tests for S303 committed-object preregistration selection."""
from __future__ import annotations

import hashlib
import stat
import subprocess
from pathlib import Path

import pytest

from scripts.platformkit.committed_object_checker import MAPPINGS, SealedMapping, main, select_mapping, select_object_bytes


ROOT = Path(__file__).resolve().parents[2]
SEALED_ANCHORS = (
    ("docs/evidence/harness/S261_ingame_headline_rederive_v2_attempt2_prereg_2026-09-04.md", b"Seal SHA-256 of the LF staged bytes above: "),
    ("docs/evidence/harness/S265_preregistration_incumbent_conformal_band_sample_2026-09-04.md", b"SEAL_SHA256:"),
    ("docs/evidence/harness/S268_distributional_evaluator_route_prereg_2026-09-04_attempt2.md", b"S268_ATTEMPT2_PREREG_SEAL_SHA256="),
    ("docs/evidence/harness/S270_attempt_1c_S82_prereg_2026-09-04_v2.md", b"SHA256_SEAL:"),
    ("docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_PREREG.md", b"seal_sha256:"),
    ("docs/evidence/harness/S274_mlb_distribution_evaluator_route_prereg_2026-09-04.md", b"S274_PREREG_SEAL_SHA256="),
)
LEGACY_READER_SHA256 = {
    "scripts/platformkit/test_s261_ingame_headline_rederive_v2_attempt2.py": "ff4e4401cedcecda6fb19a131ed2b7181b6acbe54d3ca87ef04c7f6b0121d05a",
    "scripts/platformkit/ingame/s272_ingame_tail_recal.py": "4bb4d92c3095bf0d109bc6e02361683624c0e9b39d4e4c3cf6dd02f622464d76",
    "scripts/platformkit/ingame/s277_ingame_market_staleness.py": "80d50e26ec4e49fa18ae12ec3ead9a42f2b63f334910caae646bce6d31b30fec",
    "tests/platformkit/ingame/test_s265_incumbent_conformal_band_sample.py": "23a00092d3b1f0cd506203d2b9c9fa833a52f712a0a2d000c947a240500cb1b1",
    "tests/platformkit/test_s268_distributional_evaluator_route.py": "d1bf707854dfc8496c23392accb5f0a400d2c42c0c3ea1db689ebff6e8b10578",
    "tests/platformkit/test_s270_ingame_power_feasibility.py": "0fe446199b2ae03d3f6798665fe8b42712851ff3b401d925153b1e79e4f944ec",
    "tests/platformkit/test_s273_mlb_ingame_latency_screen.py": "303930f758f355c50ba41d320e3aa067d6e8a63d85e5ac7edf79d527ca2aac5f",
    "tests/platformkit/test_s274_mlb_distribution_evaluator_route.py": "d156755adb1ef9b1b4308b6d88c216c70d23b3aae9d65882bec5a0e3fbbd4332",
}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(root), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def _init_repository(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "s303@example.invalid")
    _git(root, "config", "user.name", "S303 test")


def _write(root: Path, relative_path: str, body: bytes) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def _commit(root: Path, relative_path: str) -> None:
    _git(root, "add", relative_path)
    _git(root, "commit", "-m", "S303 fixture")


def _declared_seal(data: bytes, marker: bytes) -> tuple[bytes, str]:
    prefix, declared = data.rsplit(marker, 1)
    return prefix, declared.splitlines()[0].strip(b" .:`").decode("ascii")


@pytest.mark.parametrize("relative_path, marker", SEALED_ANCHORS)
def test_s303_committed_prereg_seals(relative_path: str, marker: bytes) -> None:
    selected = select_object_bytes(ROOT, relative_path)
    assert selected.source == "committed"
    assert selected.data is not None
    prefix, declared = _declared_seal(selected.data, marker)
    assert hashlib.sha256(prefix).hexdigest() == declared.lower()


@pytest.mark.parametrize("mapping", MAPPINGS, ids=lambda item: item.sealed_path)
def test_s303_each_mapping_selects_committed_content_when_working_file_is_dirty(tmp_path: Path, mapping: SealedMapping) -> None:
    """Each audited mapping proves committed-byte selection, not name enumeration."""
    _init_repository(tmp_path)
    committed = ("committed bytes for " + mapping.sealed_path + "\n").encode("ascii")
    dirty = ("dirty bytes for " + mapping.sealed_path + "\n").encode("ascii")
    working_path = _write(tmp_path, mapping.sealed_path, committed)
    _commit(tmp_path, mapping.sealed_path)
    working_path.write_bytes(dirty)

    selected = select_mapping(tmp_path, mapping)

    assert selected.source == "committed"
    assert selected.data == committed
    assert selected.data != working_path.read_bytes()
    assert hashlib.sha256(selected.data).hexdigest() == hashlib.sha256(committed).hexdigest()


def test_s303_fallback_requires_absent_head_path_in_repository_with_committed_head(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _init_repository(tmp_path)
    _write(tmp_path, "tracked.md", b"committed head\n")
    _commit(tmp_path, "tracked.md")
    fallback = b"working fallback\n"
    _write(tmp_path, "fallback.md", fallback)

    selected = select_object_bytes(tmp_path, "fallback.md")
    assert selected.source == "fallback"
    assert selected.data == fallback
    assert main(["--root", str(tmp_path), "fallback.md"]) == 0
    assert "FALLBACK fallback.md " in capsys.readouterr().out


def test_s303_absent_head_path_is_reported_absent_not_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _init_repository(tmp_path)
    _write(tmp_path, "tracked.md", b"committed head\n")
    _commit(tmp_path, "tracked.md")

    selected = select_object_bytes(tmp_path, "absent.md")
    assert selected.source == "absent"
    assert selected.data is None
    assert main(["--root", str(tmp_path), "absent.md"]) == 0
    assert capsys.readouterr().out == "ABSENT absent.md -\n"


def test_s303_non_repository_bad_revision_and_unreadable_object_are_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    non_repository = tmp_path / "not-a-repository"
    non_repository.mkdir()
    assert main(["--root", str(non_repository), "missing.md"]) == 2
    assert "ERROR:" in capsys.readouterr().err

    repository = tmp_path / "repository"
    repository.mkdir()
    _init_repository(repository)
    relative_path = "sealed.md"
    _write(repository, relative_path, b"committed object\n")
    _commit(repository, relative_path)
    assert main(["--root", str(repository), "--revision", "BADREV", relative_path]) == 2
    assert relative_path in capsys.readouterr().err

    blob_id = _git(repository, "rev-parse", "HEAD:" + relative_path).stdout.decode("ascii").strip()
    blob_path = repository / ".git" / "objects" / blob_id[:2] / blob_id[2:]
    assert blob_path.is_file()
    blob_path.chmod(stat.S_IREAD | stat.S_IWRITE)
    blob_path.write_bytes(b"not a readable git object")
    assert main(["--root", str(repository), relative_path]) == 2
    assert relative_path in capsys.readouterr().err


def test_s303_legacy_readers_are_byte_identical() -> None:
    """Hash committed HEAD bytes, not working-tree bytes (checkout line endings vary)."""
    assert tuple(LEGACY_READER_SHA256) == tuple(mapping.reader_path for mapping in MAPPINGS)
    for relative_path, expected in LEGACY_READER_SHA256.items():
        committed = select_object_bytes(ROOT, relative_path)
        assert committed.source == "committed"
        assert committed.data is not None
        assert hashlib.sha256(committed.data).hexdigest() == expected

        # Second check: on-disk bytes with CRLF normalized to LF must match too,
        # so this test passes under both a CRLF (core.autocrlf=true) and an LF checkout.
        on_disk_lf = (ROOT / relative_path).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(on_disk_lf).hexdigest() == expected
