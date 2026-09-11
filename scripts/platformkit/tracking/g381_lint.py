"""Unwired proposed linter for the G381 same-line digest convention."""
from __future__ import annotations

import argparse
from pathlib import Path

from scripts.platformkit.tracking import g381_census, g381_resolution as resolution


def violations(text: str) -> list[tuple[int, str]]:
    """Flag digest-bearing lines lacking one full token and a same-line path."""
    out = []
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        for token, position in resolution.tokens(line):
            if len(token) != 64 or resolution.nearest_path(line, position) == "NONE":
                out.append((number, token))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="G381 proposed digest convention linter")
    parser.add_argument("memo", type=Path, nargs="?")
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--ref", default="HEAD")
    args = parser.parse_args()
    if args.repo is None:
        if args.memo is None:
            parser.error("memo or --repo is required")
        sources = [(str(args.memo), args.memo.read_text(encoding="utf-8"))]
    else:
        sources = [(memo, resolution.blob(args.repo, args.ref, memo).decode("utf-8", "replace"))
                   for memo in g381_census.memos(args.repo, args.ref)]
    total = 0
    for name, text in sources:
        for number, token in violations(text):
            total += 1
            print("G381_LINT %s:%d %s" % (name, number, token))
    print("G381_LINT_SUMMARY memos=%d violations=%d" % (len(sources), total))
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
