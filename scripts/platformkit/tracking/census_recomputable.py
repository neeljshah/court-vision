"""G319 -- is a count a memo reports recomputable from committed bytes?

Find every count a memo states over a mutable source and every committed
artifact it names, then say per count whether one of those artifacts reproduces
the number. The rule applied is `docs/evidence/tracking/CENSUS_RULE.md`.
Parsing is heuristic: the check reports what it could not parse, never guesses.

    python scripts/platformkit/tracking/census_recomputable.py MEMO [MEMO ...] \
        [--root REPO] [--csv OUT.csv] [--label MEMO=ROW]
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
from pathlib import Path

RECOMPUTABLE = "RECOMPUTABLE"
NOT_RECOMPUTABLE = "NOT RECOMPUTABLE"
UNPARSED = "UNPARSED"
ABSENT = "ABSENT"
NO_NOUN = "line names no source noun"

# Two or more integers joined by slashes, not touching a word character, a dot,
# a colon or another slash -- which is what drops file paths and clock times.
SEQ_RE = re.compile(r"(?<![\w.:/])\d{1,9}(?:\s*/\s*\d{1,9})+(?![\w.:/])")
N_RE = re.compile(r"(?<![\w])n\s*=\s*(\d{1,9})(?![\w.])", re.IGNORECASE)
SOURCE_RE = re.compile(
    r"\b(ledgers?|rows?|files?|frames?|clips?|records?|segments?|runs?|games?"
    r"|lines?|jobs?|entry|entries|snapshots?|census|corpus|ids?|cells?"
    r"|observations?|detections?|memos?|artifacts?)\b", re.IGNORECASE)
ARTIFACT_RE = re.compile(r"[A-Za-z0-9_./\\-]+\.(?:csv\.gz|csv|jsonl|json|tsv|txt|gz)\b")
COUNT_KEY_RE = re.compile(
    r"(rows?|count|total|files?|frames?|records?|lines?|len|size|segments?"
    r"|runs?|clips?|entries|groups?|ids?|^n$|_n$)", re.IGNORECASE)


def _tracked(root: Path) -> list[str]:
    """The repository index, or a filesystem walk when there is no index."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files"], check=True,
                             capture_output=True, text=True, timeout=120).stdout
        paths = [line.strip() for line in out.splitlines() if line.strip()]
        if paths:
            return paths
    except Exception:
        pass
    return [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]


def _resolve(token: str, index: list[str]) -> list[str]:
    token = token.replace("\\", "/").lstrip("./")
    if not token:
        return []
    if "/" in token:
        return [p for p in index if p == token or p.endswith("/" + token)]
    return [p for p in index if p.rsplit("/", 1)[-1] == token]


def _json_ints(node: object, key: str = "") -> set[int]:
    found: set[int] = set()
    if isinstance(node, dict):
        for sub_key, value in node.items():
            found |= _json_ints(value, str(sub_key))
    elif isinstance(node, list):
        found.add(len(node))
        for value in node:
            found |= _json_ints(value, key)
    elif isinstance(node, int) and not isinstance(node, bool) and COUNT_KEY_RE.search(key):
        found.add(node)
    return found


def _lines(path: Path) -> int:
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        return sum(1 for line in handle if line.strip())


def _artifact_values(path: Path) -> set[int]:
    """Integers this committed artifact reproduces, by recount or entry."""
    name = path.name.lower()
    try:
        if name.endswith(".json"):
            return _json_ints(json.loads(path.read_text(encoding="utf-8", errors="replace")))
        count = _lines(path)
        if name.endswith(".jsonl"):
            return {count}
        return {count, max(count - 1, 0)}
    except Exception:
        return set()


def _counts(text: str) -> list[dict]:
    """Every count-shaped token, with its line number and its components."""
    found: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        source = bool(SOURCE_RE.search(line))
        for match in SEQ_RE.finditer(line):
            parts = [int(part) for part in re.findall(r"\d+", match.group(0))]
            found.append({"line": lineno, "kind": "fraction",
                          "components": parts, "has_source": source})
        for match in N_RE.finditer(line):
            found.append({"line": lineno, "kind": "n_equals",
                          "components": [int(match.group(1))], "has_source": source})
    return found


def scan_memo(memo: str, root: Path) -> dict:
    """Sweep one memo. Returns its per-count rows and per-verdict totals."""
    memo_path = root / memo
    if not memo_path.is_file():
        return {"memo": memo, "exists": False, "artifacts": [], "rows": [], "n": 0,
                "totals": {ABSENT: 1}, "note": "no committed path for this memo"}

    text = memo_path.read_text(encoding="utf-8", errors="replace")
    index = _tracked(root)
    artifacts: dict[str, set[int]] = {}
    for token in dict.fromkeys(ARTIFACT_RE.findall(text)):
        for hit in _resolve(token, index):
            if hit != memo and hit not in artifacts:
                artifacts[hit] = _artifact_values(root / hit)
    available: dict[int, str] = {}
    for hit, values in sorted(artifacts.items()):
        for value in values:
            available.setdefault(value, hit)

    rows: list[dict] = []
    for count in _counts(text):
        missing = sorted({c for c in count["components"] if c not in available})
        used = sorted({available[c] for c in count["components"] if c in available})
        if not count["has_source"]:
            verdict, missing, used, reason = UNPARSED, [], [], NO_NOUN
        elif missing:
            verdict = NOT_RECOMPUTABLE
            reason = ("no committed artifact the memo names reproduces every component"
                      if artifacts else "the memo names no committed artifact")
        else:
            verdict, reason = RECOMPUTABLE, ""
        rows.append({"memo": memo, "line": count["line"], "kind": count["kind"],
                     "components": count["components"], "verdict": verdict,
                     "missing": missing, "artifacts": used, "reason": reason})

    totals: dict[str, int] = {}
    for row in rows:
        totals[row["verdict"]] = totals.get(row["verdict"], 0) + 1
    return {"memo": memo, "exists": True, "artifacts": sorted(artifacts), "rows": rows,
            "n": len(rows), "totals": totals, "note": ""}


def write_csv(reports: list[dict], out: Path, labels: dict[str, str]) -> None:
    """One line per count; every integer cell zero-padded to six digits."""
    def pad(value: int) -> str:
        return f"{value:06d}"

    lines = ["row,memo,line,kind,components,verdict,missing,artifacts"]
    for report in reports:
        label = labels.get(report["memo"], "")
        if not report["exists"]:
            lines.append(f'{label},{report["memo"]},{pad(0)},none,,{ABSENT},,')
            continue
        for row in report["rows"]:
            lines.append(",".join([
                label, row["memo"], pad(row["line"]), row["kind"],
                "|".join(pad(c) for c in row["components"]), row["verdict"],
                "|".join(pad(c) for c in row["missing"]), "|".join(row["artifacts"])]))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G319 census-recomputability check")
    parser.add_argument("memos", nargs="+")
    parser.add_argument("--root", default=".")
    parser.add_argument("--csv", default="")
    parser.add_argument("--label", action="append", default=[])
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    labels = dict(item.split("=", 1) for item in args.label)
    reports = [scan_memo(memo, root) for memo in args.memos]
    for report in reports:
        print(f'{labels.get(report["memo"], "?")} | {report["memo"]} | '
              f'n={report["n"]} | {report["totals"]} {report["note"]}')
    if args.csv:
        write_csv(reports, Path(args.csv), labels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
