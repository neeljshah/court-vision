"""Scratch-only controls for the G386 one-pass capture contract."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g386_pin_copy import pin_copy_one_pass, release_staging


@pytest.fixture
def rotating_corpus(tmp_path: Path) -> dict[str, Path]:
    """A synthetic rotating corpus; all replacements and loss stay under tmp_path."""
    source = tmp_path / "corpus" / "section.bin"
    source.parent.mkdir()
    source.write_bytes(b"native-reader-bytes")
    return {"source": source, "scratch": tmp_path / "scratch", "receiver": tmp_path / "receiver"}


def _probe(path: Path) -> str:
    return "stream:%d" % path.stat().st_size


def _decoded(_: Path) -> bool:
    return True


def test_source_vanishing_between_pin_and_copy_is_lost(rotating_corpus: dict[str, Path]) -> None:
    source = rotating_corpus["source"]
    record = pin_copy_one_pass(source, rotating_corpus["scratch"], rotating_corpus["receiver"],
                               "ledger:1", "lost", probe=_probe, after_pin=source.unlink,
                               receiver_decode=_decoded)
    assert record.status == "LOST"
    assert not list(rotating_corpus["scratch"].glob("*"))


def test_replaced_path_is_changed_not_a_substitute(rotating_corpus: dict[str, Path]) -> None:
    source = rotating_corpus["source"]

    def replace() -> None:
        replacement = source.with_suffix(".new")
        replacement.write_bytes(b"replacement")
        replacement.replace(source)

    record = pin_copy_one_pass(source, rotating_corpus["scratch"], rotating_corpus["receiver"],
                               "ledger:2", "replaced", probe=_probe, after_pin=replace,
                               receiver_decode=_decoded)
    assert record.status == "CHANGED"
    assert record.receipt is None


def test_truncated_open_handle_is_short_read(rotating_corpus: dict[str, Path]) -> None:
    source = rotating_corpus["source"]
    record = pin_copy_one_pass(source, rotating_corpus["scratch"], rotating_corpus["receiver"],
                               "ledger:3", "short", probe=_probe,
                               before_copy=lambda: source.write_bytes(b"short"), receiver_decode=_decoded)
    assert record.status == "SHORT_READ"
    assert record.receipt is None


def test_receiver_corruption_cannot_be_captured(rotating_corpus: dict[str, Path]) -> None:
    receiver = rotating_corpus["receiver"]

    def corrupt() -> None:
        temporary = next(receiver.glob("*.tmp"))
        temporary.write_bytes(b"corrupt")

    record = pin_copy_one_pass(rotating_corpus["source"], rotating_corpus["scratch"], receiver,
                               "ledger:4", "corrupt", probe=_probe, receiver_corrupt=corrupt,
                               receiver_decode=_decoded)
    assert record.status == "RECEIVER_MISMATCH"
    assert record.receipt is not None


def test_retry_receipts_are_versioned_and_staging_waits_for_receipt(rotating_corpus: dict[str, Path]) -> None:
    args = rotating_corpus
    first = pin_copy_one_pass(args["source"], args["scratch"], args["receiver"], "ledger:5", "one", _probe,
                              receiver_decode=_decoded)
    second = pin_copy_one_pass(args["source"], args["scratch"], args["receiver"], "ledger:6", "two", _probe,
                               receiver_decode=_decoded)
    assert first.status == second.status == "CAPTURED"
    assert first.receipt is not None and second.receipt is not None
    assert first.receipt.version_id != second.receipt.version_id
    assert Path(first.staged_path).is_file() and Path(second.staged_path).is_file()
    assert release_staging(first)
    assert not Path(first.staged_path).exists()


def test_byte_valid_undecodable_receiver_content_is_not_captured(rotating_corpus: dict[str, Path]) -> None:
    record = pin_copy_one_pass(rotating_corpus["source"], rotating_corpus["scratch"],
                               rotating_corpus["receiver"], "ledger:7", "undecodable", _probe,
                               receiver_decode=lambda _: False)
    assert record.status == "COPY_UNDECODABLE"
    assert record.receipt is not None
    assert not record.receipt.acknowledged
    assert record.receipt.receiver_sha256 == record.source_sha256


def test_prereg_seal_reads_file_and_normalizes_lf() -> None:
    prereg = Path(__file__).parents[2] / "docs/evidence/tracking/g386_pin_copy_one_pass_2026-09-10/g386_prereg_2026-09-10.md"
    raw = prereg.read_bytes().replace(b"\r\n", b"\n")
    above, seal = raw.split(b"SEAL sha256 ", maxsplit=1)
    import hashlib

    assert hashlib.sha256(above).hexdigest() == seal.decode("ascii").strip()


def test_even_draw_spans_the_whole_pool_and_is_never_a_head_slice() -> None:
    from scripts.platformkit.tracking.g386_capture_run import even_draw

    pool = list(range(33))
    picks = even_draw(pool, 30)
    assert len(picks) == 30 and picks[0] == 0 and picks[-1] == 32
    assert picks != pool[:30]
    assert even_draw(list(range(5)), 30) == list(range(5))


def test_section_parser_accepts_sport_prefixed_and_bare_stems() -> None:
    from scripts.platformkit.tracking.g386_capture_run import _parse

    assert _parse("ncaa_basketball__GtwFiAa1gXI_s2538") == ("GtwFiAa1gXI", 2538)
    assert _parse("9sq-YMlIo9Q_s90") == ("9sq-YMlIo9Q", 90)
    assert _parse("no_section_here") is None


def test_manifest_export_is_byte_identical_across_repeats(tmp_path: Path) -> None:
    from scripts.platformkit.tracking.g386_controls import EXPORT_FIELDS, export_manifest

    row = ",".join(EXPORT_FIELDS) + "\n" + ",".join(["v%d" % i for i in range(len(EXPORT_FIELDS))]) + "\n"
    (tmp_path / "source_identity.csv").write_text(row, encoding="ascii")
    first = export_manifest(tmp_path, tmp_path / "one.json")
    second = export_manifest(tmp_path, tmp_path / "two.json")
    assert first == second
    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()


def test_batch_append_keeps_rows_an_earlier_batch_wrote(tmp_path: Path) -> None:
    """A22/A1 batches capture in 10s; appending must never drop an earlier batch."""
    from scripts.platformkit.tracking.g386_capture_run import _write
    out = tmp_path / "attempts.csv"
    _write(out, [{"attempt_id": "a01", "status": "CAPTURED"}], append=True)
    _write(out, [{"attempt_id": "a02", "status": "LOST"}], append=True)
    rows = list(csv.DictReader(out.open(encoding="ascii")))
    assert [row["attempt_id"] for row in rows] == ["a01", "a02"]
    assert rows[1]["status"] == "LOST"


def test_off_pod_retained_object_that_is_not_video_is_not_decoded(tmp_path: Path) -> None:
    """A byte-verified retained object still fails the PC decode it must pass."""
    from scripts.platformkit.tracking.g386_pc_receiver import retain_row
    objects = tmp_path / "objects"
    objects.mkdir()
    payload = b"not-a-container-" + b"z" * 4096
    (objects / "section.mp4").write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()
    row = retain_row({"receiver_sha256": sha, "source_path": "/pod/section.mp4"}, 1.0, objects)
    assert (row["retained"], row["pc_readback_match"], row["pc_decode_ok"]) == (1, 1, 0)
    assert row["retained_bytes"] == len(payload)


def test_off_pod_object_that_was_never_pulled_is_not_retained(tmp_path: Path) -> None:
    from scripts.platformkit.tracking.g386_pc_receiver import retain_row
    row = retain_row({"receiver_sha256": "x", "source_path": "/pod/missing.mp4"}, 1.0, tmp_path)
    assert (row["retained"], row["pc_readback_match"], row["retained_path"]) == (0, 0, "")


def test_raw_frame_digest_of_a_non_video_object_is_empty(tmp_path: Path) -> None:
    """The decoder-independent frame digest must not invent pixels for junk bytes."""
    from scripts.platformkit.tracking.g386_pc_receiver import raw_frame_digest
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"still-not-a-container")
    assert raw_frame_digest(junk, 1.0) == ""
