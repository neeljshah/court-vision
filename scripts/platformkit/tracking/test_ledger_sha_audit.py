"""Focused construct test for the S191 ledger SHA audit."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.platformkit.tracking.ledger_sha_audit import (
    apply_fixes,
    audit_ledger,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, path: str, content: str, subject: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", "--", path)
    _git(repo, "commit", "-m", subject)
    return _git(repo, "rev-parse", "HEAD")


def test_audit_and_fix_are_exhaustive_additive_and_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "S191 Test")
    _git(repo, "config", "user.email", "s191@test.invalid")

    base_sha = _commit(repo, "README.md", "fixture\n", "initial fixture")
    memo_path = "docs/evidence/harness/S01_fixture.md"
    memo_sha = _commit(repo, memo_path, "memo\n", "add S01 memo")
    verdict_sha = _commit(repo, "s02.txt", "result\n", "S02 ACCEPT fixture")
    ledger = repo / "docs" / "evidence" / "RESULTS_LEDGER_SYSTEM.md"
    rows = [
        "Format: date | area | gap | metric | verdict | commit",
        f"2026-09-04 | hook | S00 | ok | LANDED | {base_sha[:9]}",
        f"2026-09-04 | harness | S01 | memo {memo_path} | LANDED | PENDING",
        "2026-09-04 | harness | S02 | result | ACCEPT | PENDING_SHA",
        "2026-09-04 | harness | S03 | no artifact | NOT VALIDATED | none",
    ]
    ledger.parent.mkdir(parents=True, exist_ok=True)
    original = ("\r\n".join(rows) + "\r\n").encode("utf-8")
    ledger.write_bytes(original)

    before = audit_ledger(ledger, repo)
    assert before["data_lines"] == 4
    assert before["final_field_resolves"] == 1
    assert before["untraceable_line_numbers"] == [3, 4, 5]
    assert before["recovery_split"] == {"a": 1, "b": 1, "c": 1}
    assert before["_recoveries"] == [
        {"line_number": 3, "class": "a", "value": memo_sha},
        {"line_number": 4, "class": "b", "value": verdict_sha},
        {
            "line_number": 5,
            "class": "c",
            "value": "uncommitted:no_recoverable_commit",
        },
    ]

    apply_fixes(ledger, before)
    fixed = ledger.read_bytes()
    fixed_lines = fixed.splitlines(keepends=True)
    original_lines = original.splitlines(keepends=True)
    assert fixed_lines[0] == original_lines[0]
    assert fixed_lines[1] == original_lines[1]
    for index in (2, 3, 4):
        assert fixed_lines[index].startswith(original_lines[index][:-2] + b" | ")
        assert fixed_lines[index].endswith(b"\r\n")

    after = audit_ledger(ledger, repo)
    assert after["untraceable_count"] == 0
    assert after["final_field_resolves"] == 3
    once = ledger.read_bytes()
    apply_fixes(ledger, after)
    assert ledger.read_bytes() == once
