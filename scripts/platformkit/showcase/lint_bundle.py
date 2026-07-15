"""Lint a showcase bundle dir against SPEC.md 'Hard rails'. Stdlib only.

Usage: python scripts/platformkit/showcase/lint_bundle.py <bundle_dir>
Exit 0 = clean. Exit 1 = violations printed to stdout.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BANNED_TOKENS = ("roi", "bankroll", "pnl", "profit", "edge_pct")
BANNED_NUMBERS = ("18.38", "0.119", "78.11", "8.94", "54.57")
SECRET_KEY_RE = re.compile(r"(api_key|secret|token|password)", re.IGNORECASE)
MAX_BUNDLE_BYTES = 15 * 1024 * 1024

_token_res = [re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in BANNED_TOKENS]
_number_res = [re.compile(r"\b" + re.escape(n) + r"\b") for n in BANNED_NUMBERS]


def _check_text_bans(text: str, rel: str) -> list[str]:
    violations = []
    for tok, rx in zip(BANNED_TOKENS, _token_res):
        if rx.search(text):
            violations.append(f"{rel}: banned token '{tok}' found")
    for num, rx in zip(BANNED_NUMBERS, _number_res):
        if rx.search(text):
            violations.append(f"{rel}: banned retracted number '{num}' found")
    if "+54%" in text:
        violations.append(f"{rel}: banned retracted string '+54%' found")
    return violations


def _walk_secrets(obj, rel: str, path: str = "") -> list[str]:
    violations = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            cur = f"{path}.{key}" if path else str(key)
            if isinstance(key, str) and SECRET_KEY_RE.search(key):
                if isinstance(val, str) and val.strip():
                    violations.append(f"{rel}: secret-looking key '{cur}' has a non-empty value")
            violations.extend(_walk_secrets(val, rel, cur))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            violations.extend(_walk_secrets(item, rel, f"{path}[{i}]"))
    return violations


def _walk_receipts(obj, rel: str, path: str = "") -> list[str]:
    violations = []
    if isinstance(obj, dict):
        if "claim" in obj and "value" in obj:
            label = obj.get("label")
            artifact = obj.get("artifact")
            if not (isinstance(label, str) and label.strip()):
                violations.append(f"{rel}: receipt at '{path or '.'}' missing non-empty 'label'")
            if not (isinstance(artifact, str) and artifact.strip()):
                violations.append(f"{rel}: receipt at '{path or '.'}' missing non-empty 'artifact'")
        for key, val in obj.items():
            violations.extend(_walk_receipts(val, rel, f"{path}.{key}" if path else str(key)))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            violations.extend(_walk_receipts(item, rel, f"{path}[{i}]"))
    return violations


def lint_bundle(bundle_dir: Path) -> list[str]:
    """Return a list of violation strings for the bundle dir. Empty = clean."""
    bundle_dir = Path(bundle_dir)
    violations: list[str] = []

    if not bundle_dir.is_dir():
        return [f"{bundle_dir}: not a directory"]

    total_bytes = 0
    json_files = sorted(bundle_dir.rglob("*.json"))

    for path in bundle_dir.rglob("*"):
        if path.is_file():
            try:
                total_bytes += path.stat().st_size
            except OSError:
                violations.append(f"{path}: unreadable for size check (fail-closed)")

    if total_bytes >= MAX_BUNDLE_BYTES:
        violations.append(
            f"bundle total size {total_bytes} bytes >= {MAX_BUNDLE_BYTES} byte cap"
        )

    for path in json_files:
        rel = str(path.relative_to(bundle_dir))
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            violations.append(f"{rel}: unreadable ({exc}) -- fail-closed")
            continue

        violations.extend(_check_text_bans(text, rel))

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            violations.append(f"{rel}: malformed JSON ({exc})")
            continue

        violations.extend(_walk_receipts(data, rel))
        violations.extend(_walk_secrets(data, rel))

    return violations


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python lint_bundle.py <bundle_dir>")
        return 1
    violations = lint_bundle(Path(argv[1]))
    if violations:
        for v in violations:
            print(v)
        return 1
    print("clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
