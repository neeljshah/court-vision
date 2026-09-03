#!/usr/bin/env python
"""Audit and append provenance to untraceable system-ledger rows."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[3]
DEFAULT_LEDGER = REPO / "docs" / "evidence" / "RESULTS_LEDGER_SYSTEM.md"
DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s*\|")
SHA_RE = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{7,40}(?![0-9A-Fa-f])")
MEMO_RE = re.compile(r"docs/evidence/harness/[A-Za-z0-9_.-]+\.md")
SID_RE = re.compile(r"\bS\d{1,3}[a-z]?\b", re.IGNORECASE)
VERDICT_RE = re.compile(
    r"\b(?:ACCEPT|REJECT|CLOSED AT LIMIT|NOT VALIDATED|FALSIFIED|NULL|"
    r"BEHIND|AHEAD|LANDED)\b",
    re.IGNORECASE,
)


def _git(repo: Path, *args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def _sha_tokens(text: str) -> list[str]:
    return [match.group(0) for match in SHA_RE.finditer(text)]


def _resolving_commits(repo: Path, tokens: Iterable[str]) -> set[str]:
    unique = list(dict.fromkeys(tokens))
    if not unique:
        return set()
    output = _git(
        repo,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype)",
        input_text="\n".join(unique) + "\n",
    )
    answers = output.splitlines()
    return {
        token
        for token, answer in zip(unique, answers)
        if re.fullmatch(r"[0-9a-f]{40} commit", answer)
    }


def _first_added_commit(repo: Path, paths: Iterable[str]) -> str | None:
    for path in paths:
        output = _git(repo, "log", "--diff-filter=A", "--format=%H", "--", path)
        commits = [line.strip() for line in output.splitlines() if line.strip()]
        if commits:
            return commits[0]
    return None


def _first_verdict_commit(repo: Path, sids: Iterable[str]) -> str | None:
    for sid in sids:
        output = _git(
            repo,
            "log",
            "--format=%H%x09%s",
            "--regexp-ignore-case",
            f"--grep={sid}",
        )
        exact_sid = re.compile(rf"\b{re.escape(sid)}\b", re.IGNORECASE)
        for record in output.splitlines():
            sha, separator, subject = record.partition("\t")
            if separator and exact_sid.search(subject) and VERDICT_RE.search(subject):
                return sha
    return None


def _recovery(repo: Path, line: str) -> dict[str, str]:
    memo_sha = _first_added_commit(repo, dict.fromkeys(MEMO_RE.findall(line)))
    if memo_sha:
        return {"class": "a", "value": memo_sha}
    verdict_sha = _first_verdict_commit(repo, dict.fromkeys(SID_RE.findall(line)))
    if verdict_sha:
        return {"class": "b", "value": verdict_sha}
    return {"class": "c", "value": "uncommitted:no_recoverable_commit"}


def audit_ledger(ledger: Path, repo: Path) -> dict[str, Any]:
    """Audit every dated ledger row and build its provenance recovery plan."""
    text = ledger.read_bytes().decode("utf-8")
    physical_lines = text.splitlines()
    data_rows = [
        (number, line)
        for number, line in enumerate(physical_lines, start=1)
        if DATA_RE.match(line)
    ]
    all_tokens = [token for _, line in data_rows for token in _sha_tokens(line)]
    resolved = _resolving_commits(repo, all_tokens)
    histogram: Counter[int] = Counter()
    untraceable: list[tuple[int, str]] = []
    final_resolves = 0
    hook_lines = 0
    hook_resolves = 0

    for number, line in data_rows:
        fields = line.split("|")
        histogram[len(fields)] += 1
        line_resolves = any(token in resolved for token in _sha_tokens(line))
        if any(token in resolved for token in _sha_tokens(fields[-1])):
            final_resolves += 1
        if len(fields) > 1 and fields[1].strip() == "hook":
            hook_lines += 1
            hook_resolves += int(line_resolves)
        if not line_resolves and "uncommitted:" not in line:
            untraceable.append((number, line))

    recoveries = [
        {"line_number": number, **_recovery(repo, line)}
        for number, line in untraceable
    ]
    recovery_lines = {
        label: [
            item["line_number"] for item in recoveries if item["class"] == label
        ]
        for label in ("a", "b", "c")
    }
    count = len(data_rows)
    return {
        "physical_lines": len(physical_lines),
        "data_lines": count,
        "final_field_resolves": final_resolves,
        "final_field_resolves_pct": round(100.0 * final_resolves / count, 2),
        "untraceable_count": len(untraceable),
        "untraceable_pct": round(100.0 * len(untraceable) / count, 2),
        "untraceable_line_numbers": [number for number, _ in untraceable],
        "field_count_histogram": {
            str(key): histogram[key] for key in sorted(histogram)
        },
        "hook_lines": hook_lines,
        "hook_lines_resolvable": hook_resolves,
        "recovery_split": {label: len(lines) for label, lines in recovery_lines.items()},
        "recovery_line_numbers": recovery_lines,
        "not_verified_line_numbers": recovery_lines["c"],
        "_recoveries": recoveries,
    }


def public_summary(audit: dict[str, Any]) -> dict[str, Any]:
    """Return the stable JSON report without internal fix values."""
    return {key: value for key, value in audit.items() if not key.startswith("_")}


def apply_fixes(ledger: Path, audit: dict[str, Any]) -> None:
    """Append one provenance field to each currently untraceable row."""
    recoveries = {
        item["line_number"]: item["value"] for item in audit["_recoveries"]
    }
    original = ledger.read_bytes()
    parts = original.splitlines(keepends=True)
    fixed: list[bytes] = []
    for number, raw_line in enumerate(parts, start=1):
        value = recoveries.get(number)
        if value is None:
            fixed.append(raw_line)
            continue
        ending = b"\r\n" if raw_line.endswith(b"\r\n") else b"\n" if raw_line.endswith(b"\n") else b""
        body = raw_line[: len(raw_line) - len(ending)] if ending else raw_line
        fixed.append(body + f" | {value}".encode("ascii") + ending)
    ledger.write_bytes(b"".join(fixed))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="append recovered provenance")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--repo", type=Path, default=REPO)
    return parser


def main() -> int:
    args = _parser().parse_args()
    before = audit_ledger(args.ledger, args.repo)
    if not args.fix:
        print(json.dumps(public_summary(before), indent=2, sort_keys=True))
        return 0
    apply_fixes(args.ledger, before)
    after = audit_ledger(args.ledger, args.repo)
    print(
        json.dumps(
            {"before": public_summary(before), "after": public_summary(after)},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
