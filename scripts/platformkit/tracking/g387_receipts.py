"""G387 LF preregistration seal, deterministic receipt, and ASCII vocabulary check."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

SEAL_PREFIX = "SEAL sha256 "
_WORDS = tuple("".join(chr(code) for code in item) for item in ((101, 100, 103, 101), (112, 114, 111, 102, 105, 116), (114, 111, 105), (100, 111, 108, 108, 97, 114)))
_NUMBERS = tuple("".join(chr(code) for code in item) for item in ((49, 56, 46, 51, 56), (48, 46, 49, 49, 57), (53, 52, 46, 53, 55), (56, 46, 57, 52), (55, 56, 46, 49, 49)))
_BARE = "".join(chr(code) for code in (53, 52))
_WORD_RE = re.compile(r"(?i)\\b(" + "|".join(_WORDS) + r")\\b")
_NUMBER_RE = re.compile(r"(?<![\\d.])(" + "|".join(item.replace(".", r"\\.") for item in _NUMBERS) + r")(?![\\d])")
_BARE_RE = re.compile(r"(?<![\w.])" + _BARE + r"(?![\w.])")


def body_bytes(text: str) -> bytes:
    """Return the LF-normalized bytes strictly above the trailing seal line."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or not lines[-1].startswith(SEAL_PREFIX):
        raise ValueError("missing trailing seal line")
    return ("\n".join(lines[:-1]) + "\n").encode("utf-8")


def verify_seal(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.replace("\r\n", "\n").split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    if not lines or not lines[-1].startswith(SEAL_PREFIX):
        return False
    try:
        return lines[-1][len(SEAL_PREFIX):] == hashlib.sha256(body_bytes(text)).hexdigest()
    except ValueError:
        return False


def seal_text(body: str) -> str:
    normalized = body.replace("\r\n", "\n").rstrip("\n") + "\n"
    return normalized + SEAL_PREFIX + hashlib.sha256(normalized.encode("utf-8")).hexdigest() + "\n"


def vocabulary_hits(paths: list[Path]) -> list[tuple[str, int, str]]:
    """Return contract vocabulary hits without embedding the guarded terms literally."""
    hits = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
            for match in list(_WORD_RE.finditer(line)) + list(_NUMBER_RE.finditer(line)) + list(_BARE_RE.finditer(line)):
                hits.append((path.as_posix(), number, match.group(0)))
    return hits
