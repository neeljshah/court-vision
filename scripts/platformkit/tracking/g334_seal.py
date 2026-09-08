"""G334 seal and vocabulary scan -- the two checks this row runs before every commit.

`seal` computes the SHA-256 over the LF-normalised bytes ABOVE a trailing `SEAL sha256 <hex>` line,
which is the rule stated in the preregistration. `scan` is the contract Q6 vocabulary and digit
check: the four banned words at word boundaries, and the retracted numeric strings.

Every banned token below is written as a concatenation of two fragments ON PURPOSE, so that this
file -- which defines the ban -- does not itself contain a single one of the literals and can be
scanned along with everything else it guards, with no exception list to maintain.

Usage:
    python -m scripts.platformkit.tracking.g334_seal seal   <path>   # append or rewrite the seal
    python -m scripts.platformkit.tracking.g334_seal verify <path>   # exit 1 unless the seal holds
    python -m scripts.platformkit.tracking.g334_seal scan   <path>...  # exit 1 on any hit
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

SEAL_PREFIX = "SEAL sha256 "
BANNED_WORDS = ("ed" + "ge", "pro" + "fit", "r" + "oi", "dol" + "lar")
BANNED_NUMBERS = ("18." + "38", "0." + "119", "5" + "4.57", "8." + "94", "78." + "11")
BARE_INTEGER = "5" + "4"
WORD_RE = re.compile(r"(?i)\b(" + "|".join(BANNED_WORDS) + r")\b")
# Anchored so a longer run of digits -- a zero-padded six-digit CSV cell, say -- is never a hit.
NUMBER_RE = re.compile(r"(?<![\d.])(" + "|".join(n.replace(".", r"\.") for n in BANNED_NUMBERS)
                       + r")(?![\d])")
BARE_RE = re.compile(r"(?<![\d.])" + BARE_INTEGER + r"(?![\d.])")
BARE_LABEL = "bare-integer"


def body_of(text: str) -> str:
    """The bytes the seal covers: everything above a trailing SEAL line, LF-normalised."""
    lf = text.replace("\r\n", "\n")
    lines = lf.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    if lines and lines[-1].startswith(SEAL_PREFIX):
        lines.pop()
    return "".join(line + "\n" for line in lines)


def seal_hex(text: str) -> str:
    return hashlib.sha256(body_of(text).encode("utf-8")).hexdigest()


def sha256_lf(path: Path) -> str:
    """SHA-256 of a file's LF-normalised bytes -- the form every memo table quotes."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def apply_seal(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    digest = seal_hex(text)
    path.write_text(body_of(text) + SEAL_PREFIX + digest + "\n", encoding="utf-8", newline="\n")
    return digest


def verify_seal(path: Path) -> bool:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = [line for line in text.split("\n") if line != ""]
    if not lines or not lines[-1].startswith(SEAL_PREFIX):
        return False
    return lines[-1][len(SEAL_PREFIX):].strip() == seal_hex(text)


def scan_text(text: str) -> list:
    """Every banned-word and banned-number hit, as (line number, kind, matched text)."""
    hits = []
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        for match in WORD_RE.finditer(line):
            hits.append((number, "word", match.group(0)))
        for match in NUMBER_RE.finditer(line):
            hits.append((number, "number", match.group(0)))
        for match in BARE_RE.finditer(line):
            hits.append((number, BARE_LABEL, match.group(0)))
    return hits


def main(argv) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    action, paths = argv[1], [Path(p) for p in argv[2:]]
    if action == "seal":
        for path in paths:
            print("SEALED %s %s" % (path.name, apply_seal(path)))
        return 0
    if action == "verify":
        bad = [p for p in paths if not verify_seal(p)]
        for path in paths:
            print("SEAL %s %s" % ("BROKEN" if path in bad else "HOLDS", path.name))
        return 1 if bad else 0
    if action == "scan":
        total = 0
        for path in paths:
            hits = scan_text(path.read_text(encoding="utf-8", errors="replace"))
            total += len(hits)
            print("SCAN %s hits=%d" % (path.as_posix(), len(hits)))
            for number, kind, text in hits:
                print("  %s:%d %s %r" % (path.as_posix(), number, kind, text))
        print("SCAN_TOTAL_HITS %d over %d files" % (total, len(paths)))
        return 1 if total else 0
    print("unknown action %r" % action)
    return 2


def demo() -> None:
    """Self-check: the seal round-trips, the scan catches one of each kind, and this file is clean."""
    text = "alpha\nbeta\n"
    assert body_of(text) == text
    assert body_of(text + SEAL_PREFIX + "deadbeef\n") == text
    assert seal_hex(text + SEAL_PREFIX + "x\n") == seal_hex(text)
    assert seal_hex("a\r\nb\r\n") == seal_hex("a\nb\n")
    dirty = "an %s here\n%s there\n%s alone\n" % (
        BANNED_WORDS[0].capitalize(), BANNED_NUMBERS[0], BARE_INTEGER)
    assert {kind for _n, kind, _t in scan_text(dirty)} == {"word", "number", BARE_LABEL}
    assert scan_text("ledger 000054 1.545 123.38 0.1191\n") == []
    assert scan_text(Path(__file__).read_text(encoding="utf-8")) == []
    print("g334_seal demo OK")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "demo":
        demo()
    else:
        sys.exit(main(sys.argv))
