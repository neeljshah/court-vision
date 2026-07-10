"""Per-file tests for scripts.platformkit.io_atomic.

Proves the crash-safety contract that the 4 torn-write call sites now rely on:
  * write_json_atomic / write_text_atomic leave NO torn file when the write
    fails mid-flight -- a reader sees either the OLD complete file or nothing,
    never a half-written one, and no stray tmp is left behind.
  * append_jsonl_atomic NEVER leaves a partial line, even on a mid-write crash,
    and the resulting file parses line-by-line (the shape the readers expect).
"""
from __future__ import annotations

import builtins
import json

import pytest

from scripts.platformkit.io_atomic import (
    append_jsonl_atomic,
    write_json_atomic,
    write_text_atomic,
)


def _tmp_leftovers(d):
    return [p.name for p in d.iterdir() if p.name.startswith(".tmp_")]


def test_write_json_atomic_roundtrip_and_shape(tmp_path):
    p = tmp_path / "state.json"
    write_json_atomic(p, {"b": 2, "a": 1})
    # sort_keys=True by default -> deterministic shape readers can diff.
    assert p.read_text(encoding="utf-8") == '{"a": 1, "b": 2}'
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    assert _tmp_leftovers(tmp_path) == []


def test_write_json_atomic_trailing_newline(tmp_path):
    p = tmp_path / "diag.json"
    write_json_atomic(p, {"x": 1}, trailing_newline=True)
    body = p.read_text(encoding="utf-8")
    assert body.endswith("\n")
    assert json.loads(body) == {"x": 1}


def test_write_json_atomic_no_torn_file_on_midwrite_failure(tmp_path):
    """A crash mid-write must not corrupt the existing file nor leave a tmp."""
    p = tmp_path / "ledger.json"
    write_json_atomic(p, {"v": "original"})
    original = p.read_text(encoding="utf-8")

    real_open = builtins.open

    def boom(*args, **kwargs):  # fail only the tmp write, like a crash
        fh = real_open(*args, **kwargs)
        if len(args) >= 2 and "w" in str(args[1]):
            fh.write("PARTIAL")  # write some bytes then blow up before replace
            raise OSError("simulated mid-write crash")
        return fh

    import os as _os
    # mkstemp uses os.open + os.fdopen; patch fdopen's write path instead.
    real_fdopen = _os.fdopen

    def boom_fdopen(fd, *a, **k):
        fh = real_fdopen(fd, *a, **k)
        orig_write = fh.write

        def crashing_write(s):
            orig_write("PARTIAL")  # land partial bytes in the TMP, not target
            raise OSError("simulated mid-write crash")

        fh.write = crashing_write  # type: ignore[assignment]
        return fh

    _os.fdopen = boom_fdopen  # type: ignore[assignment]
    try:
        with pytest.raises(OSError):
            write_json_atomic(p, {"v": "new"})
    finally:
        _os.fdopen = real_fdopen  # type: ignore[assignment]

    # Target untouched + still valid; partial bytes never visible; tmp cleaned.
    assert p.read_text(encoding="utf-8") == original
    assert json.loads(p.read_text(encoding="utf-8")) == {"v": "original"}
    assert _tmp_leftovers(tmp_path) == []


def test_write_text_atomic_roundtrip(tmp_path):
    p = tmp_path / "lines.jsonl"
    body = '{"a": 1}\n{"a": 2}\n'
    write_text_atomic(p, body, encoding="ascii")
    assert p.read_text(encoding="ascii") == body
    rows = [json.loads(ln) for ln in p.read_text(encoding="ascii").splitlines() if ln]
    assert rows == [{"a": 1}, {"a": 2}]


def test_append_jsonl_atomic_builds_valid_jsonl(tmp_path):
    p = tmp_path / "feed.jsonl"
    append_jsonl_atomic(p, {"i": 0})
    append_jsonl_atomic(p, {"i": 1})
    append_jsonl_atomic(p, {"i": 2})
    text = p.read_text(encoding="ascii")
    assert text.endswith("\n")
    rows = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    assert rows == [{"i": 0}, {"i": 1}, {"i": 2}]
    # every line is complete -- no split row
    for ln in text.splitlines():
        json.loads(ln)


def test_append_jsonl_atomic_no_partial_line_on_midwrite_failure(tmp_path):
    p = tmp_path / "feed.jsonl"
    append_jsonl_atomic(p, {"i": 0})
    append_jsonl_atomic(p, {"i": 1})
    before = p.read_text(encoding="ascii")

    import os as _os
    real_fdopen = _os.fdopen

    def boom_fdopen(fd, *a, **k):
        fh = real_fdopen(fd, *a, **k)
        orig_write = fh.write

        def crashing_write(s):
            orig_write(s[: max(1, len(s) // 2)])  # land a HALF line in the tmp
            raise OSError("simulated mid-write crash")

        fh.write = crashing_write  # type: ignore[assignment]
        return fh

    _os.fdopen = boom_fdopen  # type: ignore[assignment]
    try:
        with pytest.raises(OSError):
            append_jsonl_atomic(p, {"i": 2})
    finally:
        _os.fdopen = real_fdopen  # type: ignore[assignment]

    after = p.read_text(encoding="ascii")
    assert after == before  # target untouched -> no partial line ever visible
    rows = [json.loads(ln) for ln in after.splitlines() if ln.strip()]
    assert rows == [{"i": 0}, {"i": 1}]
    assert _tmp_leftovers(tmp_path) == []


def test_append_jsonl_atomic_heals_pre_existing_torn_tail(tmp_path):
    """If a legacy bare-append left a torn tail, the new row starts a fresh line."""
    p = tmp_path / "feed.jsonl"
    p.write_text('{"i": 0}\n{"i": 1}', encoding="ascii")  # no trailing newline
    append_jsonl_atomic(p, {"i": 2})
    rows = [json.loads(ln) for ln in p.read_text(encoding="ascii").splitlines() if ln.strip()]
    assert rows == [{"i": 0}, {"i": 1}, {"i": 2}]


def test_append_jsonl_atomic_stamps_run_ts_only_for_validation_ledger(tmp_path):
    """E14: domains/*/knowledge validate_*.py + M07 reval all write files named
    exactly validation_ledger.jsonl through this one function -- that's the
    single shared point that gets an auto run_ts stamp so a same-corpus reval
    is distinguishable from a silent duplicate. Every other jsonl target
    (feed.jsonl, cost_ledger.jsonl, etc.) must be byte-shape-unchanged."""
    ledger = tmp_path / "validation_ledger.jsonl"
    append_jsonl_atomic(ledger, {"hypothesis": "b2b_rest_penalty", "verdict": "NULL_LOCAL"})
    row = json.loads(ledger.read_text(encoding="ascii").splitlines()[0])
    assert row["hypothesis"] == "b2b_rest_penalty"
    assert "run_ts" in row and row["run_ts"].endswith("Z")

    # A caller-supplied run_ts is never clobbered.
    other = tmp_path / "sub" / "validation_ledger.jsonl"
    append_jsonl_atomic(other, {"hypothesis": "x", "run_ts": "PRESET"})
    row2 = json.loads(other.read_text(encoding="ascii").splitlines()[0])
    assert row2["run_ts"] == "PRESET"

    # A differently-named ledger (every non-knowledge caller) is untouched.
    p = tmp_path / "feed.jsonl"
    append_jsonl_atomic(p, {"i": 0})
    row3 = json.loads(p.read_text(encoding="ascii").splitlines()[0])
    assert "run_ts" not in row3


def test_append_jsonl_atomic_skips_content_duplicate_in_validation_ledger(tmp_path):
    """Forward guard (docs/research/ledger_dedupe_audit_2026-07-10.md): a
    re-run of the same validator against an unchanged corpus must not grow
    the ledger -- only run_ts differs, so the append is a no-op."""
    ledger = tmp_path / "validation_ledger.jsonl"
    append_jsonl_atomic(ledger, {"hypothesis": "b2b_rest_penalty", "verdict": "NULL_LOCAL", "n": 100})
    append_jsonl_atomic(ledger, {"hypothesis": "b2b_rest_penalty", "verdict": "NULL_LOCAL", "n": 100})
    rows = [json.loads(ln) for ln in ledger.read_text(encoding="ascii").splitlines() if ln.strip()]
    assert len(rows) == 1  # second append was a content-duplicate -> skipped

    # A genuinely different row (different n) still appends normally.
    append_jsonl_atomic(ledger, {"hypothesis": "b2b_rest_penalty", "verdict": "NULL_LOCAL", "n": 200})
    rows = [json.loads(ln) for ln in ledger.read_text(encoding="ascii").splitlines() if ln.strip()]
    assert len(rows) == 2

    # A non-ledger jsonl file is NOT guarded -- byte-identical rows both land.
    feed = tmp_path / "feed.jsonl"
    append_jsonl_atomic(feed, {"i": 0})
    append_jsonl_atomic(feed, {"i": 0})
    feed_rows = [json.loads(ln) for ln in feed.read_text(encoding="ascii").splitlines() if ln.strip()]
    assert len(feed_rows) == 2
