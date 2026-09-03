"""S159 acceptance test for relative links in public entry-point Markdown."""
from __future__ import annotations

import posixpath
import re
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[3]
ENTRY_POINTS = (
    "README.md",
    "docs/INDEX.md",
    "docs/PUBLIC_EVIDENCE.md",
    "docs/JOB_EVIDENCE_PACKET.md",
    "docs/INTELLIGENCE.md",
    "docs/PLATFORM.md",
    "CLAUDE.md",
    "AGENTS.md",
)
_INLINE_LINK = re.compile(
    r"!?\[[^\]\n]*\]\(\s*(?:<([^>]+)>|([^\s)]+))"
)
_REFERENCE_LINK = re.compile(
    r"^\s*\[[^\]]+\]:\s*(?:<([^>]+)>|(\S+))",
    re.MULTILINE,
)
_EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "data:")


def _tracked_paths() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    }


def _relative_targets(markdown: str) -> list[str]:
    targets: list[str] = []
    for match in (*_INLINE_LINK.finditer(markdown), *_REFERENCE_LINK.finditer(markdown)):
        raw = (match.group(1) or match.group(2)).strip()
        if raw.startswith("#") or raw.lower().startswith(_EXTERNAL_SCHEMES):
            continue
        target = unquote(raw.split("#", 1)[0].split("?", 1)[0])
        if target:
            targets.append(target.replace("\\", "/"))
    return targets


def test_entry_point_relative_links_are_tracked() -> None:
    tracked = _tracked_paths()
    broken: list[str] = []

    for source in ENTRY_POINTS:
        assert source in tracked, f"entry point is not tracked: {source}"
        markdown = (ROOT / source).read_text(encoding="utf-8")
        base = str(PurePosixPath(source).parent)
        for target in _relative_targets(markdown):
            resolved = posixpath.normpath(posixpath.join(base, target))
            exists = resolved in tracked or any(
                path.startswith(resolved.rstrip("/") + "/") for path in tracked
            )
            if not exists:
                broken.append(f"{source} -> {target} ({resolved})")

    assert broken == [], "broken relative links:\n" + "\n".join(broken)
