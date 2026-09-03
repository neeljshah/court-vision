"""Census every exception handler in the run_clip route and say what it swallows.

Static only: parses with `ast`, runs nothing, imports nothing from `src/`.
A handler is SILENT when its whole body is `pass`/`continue`/`return`-with-no-log,
which makes a real failure indistinguishable from normal operation.

Emits one CSV row per handler so the classification work is data, not memory.
"""
from __future__ import annotations

import argparse
import ast
import csv
import sys
from pathlib import Path

ROUTE_FILES = [
    "src/pipeline/unified_pipeline.py",
    "src/tracking/advanced_tracker.py",
    "src/tracking/color_reid.py",
    "src/tracking/court_detector.py",
    "src/tracking/rectify_court.py",
    "src/tracking/video_handler.py",
    "scripts/run_clip.py",
]

_LOG_CALLS = ("print", "warn", "warning", "error", "log", "logger", "raise")


def _exc_name(handler: ast.ExceptHandler) -> str:
    if handler.type is None:
        return "BARE"
    try:
        return ast.unparse(handler.type)
    except Exception:  # pragma: no cover - ast.unparse is stdlib >=3.9
        return "?"


def _body_kind(handler: ast.ExceptHandler) -> str:
    """Classify the handler body: what does it do with the failure?"""
    body = handler.body
    if len(body) == 1:
        node = body[0]
        if isinstance(node, ast.Pass):
            return "pass"
        if isinstance(node, ast.Continue):
            return "continue"
        if isinstance(node, ast.Break):
            return "break"
        if isinstance(node, ast.Return):
            return "return"
    src = " ".join(ast.dump(n) for n in body).lower()
    if "raise" in src:
        return "reraise"
    if any(tok in src for tok in _LOG_CALLS):
        return "logged"
    return "other"


def _is_silent(kind: str) -> bool:
    return kind in {"pass", "continue", "break", "return"}


def _enclosing(tree: ast.AST) -> dict[int, str]:
    """Map every line number to the innermost enclosing def/class name."""
    owner: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end = getattr(node, "end_lineno", node.lineno)
            for line in range(node.lineno, end + 1):
                owner[line] = node.name
    return owner


def census(repo: Path, files: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rel in files:
        path = repo / rel
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
        owner = _enclosing(tree)
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            kind = _body_kind(node)
            guarded = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
            rows.append({
                "file": rel,
                "line": node.lineno,
                "function": owner.get(node.lineno, "<module>"),
                "catches": _exc_name(node),
                "body_kind": kind,
                "silent": _is_silent(kind),
                "source": guarded,
            })
    rows.sort(key=lambda r: (r["file"], r["line"]))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    rows = census(args.repo, ROUTE_FILES)
    silent = [r for r in rows if r["silent"]]
    bare_silent = [r for r in silent if r["catches"] in ("BARE", "Exception")]

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="", encoding="ascii", errors="replace") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    print("handlers          %d" % len(rows))
    print("silent            %d" % len(silent))
    print("silent AND broad  %d   (catches BARE or Exception)" % len(bare_silent))
    for r in bare_silent:
        print("  %s:%d  %s()  catches %s -> %s"
              % (r["file"], r["line"], r["function"], r["catches"], r["body_kind"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
