"""G319 -- is a count a memo reports recomputable from committed bytes?

Find every count a memo states over a mutable source and every committed
artifact it names, then say per count whether one of those artifacts reproduces
the number. The rule applied is `docs/evidence/tracking/CENSUS_RULE.md`.
Parsing is heuristic: the check reports what it could not parse, never guesses.

    python scripts/platformkit/tracking/census_recomputable.py MEMO [MEMO ...] \
        [--root REPO] [--csv OUT.csv] [--label MEMO=ROW] [--construct-only] [--txt-header]
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.platformkit.env_sidecar import write as write_env_sidecar  # noqa: E402

# G62: the modules whose content determines this census; the repo is never hashed whole.
ENV_MODULES = ("scripts/platformkit/tracking/census_recomputable.py",)

RECOMPUTABLE = "RECOMPUTABLE"
NOT_RECOMPUTABLE = "NOT RECOMPUTABLE"
UNPARSED = "UNPARSED"
ABSENT = "ABSENT"
# G332, additive: an artifact DOES reproduce the number, but only through a list of records
# that carries none of what CENSUS_RULE.md clause 2 (lines 10-14) asks of a snapshot list.
UNVERIFIED_SNAPSHOT = "UNVERIFIED_SNAPSHOT"
NO_NOUN = "line names no source noun"
NO_SNAPSHOT = ("reproduced only by a list of records without the sha256, timestamp, row "
               "count or chain CENSUS_RULE clause 2 requires")

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
HEX64_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
SHA_KEY_RE = re.compile(r"sha256", re.IGNORECASE)
TIME_KEY_RE = re.compile(r"(time|date|utc|stamp|when|^at$|_at$)", re.IGNORECASE)


def _tracked(root: Path, construct_only: bool = False) -> list[str]:
    """The repository index. A git failure RAISES with the git error unless `construct_only`
    asks for the filesystem walk -- silently walking let an artifact in NO index pass as
    committed, which is the whole thing this check exists to refuse."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files"], check=True,
                             capture_output=True, text=True, timeout=120).stdout
        paths = [line.strip() for line in out.splitlines() if line.strip()]
        if paths or not construct_only:
            return paths
    except Exception as exc:
        if not construct_only:
            raise RuntimeError("git ls-files failed under %s: %s"
                               % (root, getattr(exc, "stderr", None) or exc)) from exc
    return [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]


def _resolve(token: str, index: list[str]) -> list[str]:
    token = token.replace("\\", "/").lstrip("./")
    if not token:
        return []
    if "/" in token:
        return [p for p in index if p == token or p.endswith("/" + token)]
    return [p for p in index if p.rsplit("/", 1)[-1] == token]


def _entry_verifies(entry: dict) -> bool:
    """CENSUS_RULE clause 2: per snapshot, a sha256 (64 hex), a timestamp and a row count."""
    def carries(pattern, ok) -> bool:
        return any(pattern.search(str(k)) and ok(v) for k, v in entry.items())

    return (carries(SHA_KEY_RE, lambda v: isinstance(v, str) and bool(HEX64_RE.match(v)))
            and carries(TIME_KEY_RE, lambda v: v not in (None, "", [], {}))
            and carries(COUNT_KEY_RE,
                        lambda v: isinstance(v, int) and not isinstance(v, bool)))


def snapshot_list_ok(entries: list) -> bool:
    """Is this list of records a committed hash-chained snapshot list (CENSUS_RULE 2)?

    SHAPE ONLY. It cannot see clause 3's ORDER, and two entries carrying the SAME sha256
    would satisfy the chain. ponytail: shape check, not a proof of provenance."""
    if not all(_entry_verifies(entry) for entry in entries):
        return False
    return all({v for v in a.values() if isinstance(v, str) and HEX64_RE.match(v)}
               & {v for v in b.values() if isinstance(v, str)}
               for a, b in zip(entries, entries[1:]))


def _json_split(node: object, key: str = "", trusted: bool = True) -> tuple[set, set]:
    """(verified, unverified) integers this document reproduces. A list whose entries are
    ALL objects is a snapshot-list candidate: its LENGTH and the count-keyed integers inside
    it are verified only when the list itself verifies."""
    good: set[int] = set()
    bad: set[int] = set()
    if isinstance(node, dict):
        for sub_key, value in node.items():
            found, unsure = _json_split(value, str(sub_key), trusted)
            good |= found
            bad |= unsure
    elif isinstance(node, list):
        here = trusted
        if node and all(isinstance(item, dict) for item in node):
            here = trusted and snapshot_list_ok(node)
        (good if here else bad).add(len(node))
        for value in node:
            found, unsure = _json_split(value, key, here)
            good |= found
            bad |= unsure
    elif isinstance(node, int) and not isinstance(node, bool) and COUNT_KEY_RE.search(key):
        (good if trusted else bad).add(node)
    return good, bad


def _json_ints(node: object, key: str = "") -> set[int]:
    """B2: the landed flat set -- every integer the document reproduces, unsplit."""
    good, bad = _json_split(node, key)
    return good | bad


def _lines(path: Path) -> int:
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        return sum(1 for line in handle if line.strip())


def artifact_scan(path: Path, txt_header: bool = False) -> tuple[set, set]:
    """(verified, unverified) integers this committed artifact reproduces.

    A TXT artifact contributes its non-blank LINE COUNT only: the header subtraction is a
    CSV rule the sealed prereg never extended to TXT, and `txt_header` restores it."""
    name = path.name.lower()
    try:
        if name.endswith(".json"):
            return _json_split(json.loads(path.read_text(encoding="utf-8",
                                                         errors="replace")))
        count = _lines(path)
        if name.endswith(".jsonl") or (name.endswith(".txt") and not txt_header):
            return {count}, set()
        return {count, max(count - 1, 0)}, set()
    except Exception:
        return set(), set()


def _artifact_values(path: Path, txt_header: bool = False) -> set[int]:
    """B2: the landed flat set, verified and unverified together."""
    good, bad = artifact_scan(path, txt_header)
    return good | bad


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


def scan_memo(memo: str, root: Path, construct_only: bool = False,
              txt_header: bool = False) -> dict:
    """Sweep one memo. Returns its per-count rows and per-verdict totals."""
    memo_path = root / memo
    if not memo_path.is_file():
        return {"memo": memo, "exists": False, "artifacts": [], "rows": [], "n": 0,
                "totals": {ABSENT: 1}, "note": "no committed path for this memo"}

    text = memo_path.read_text(encoding="utf-8", errors="replace")
    index = _tracked(root, construct_only)
    artifacts: dict[str, tuple] = {}
    for token in dict.fromkeys(ARTIFACT_RE.findall(text)):
        for hit in _resolve(token, index):
            if hit != memo and hit not in artifacts:
                artifacts[hit] = artifact_scan(root / hit, txt_header)
    available: dict[int, str] = {}
    unverified: dict[int, str] = {}
    for hit, (values, unsure) in sorted(artifacts.items()):
        for value in values:
            available.setdefault(value, hit)
        for value in unsure:
            unverified.setdefault(value, hit)

    rows: list[dict] = []
    for count in _counts(text):
        missing = sorted({c for c in count["components"] if c not in available})
        used = sorted({available[c] for c in count["components"] if c in available})
        if not count["has_source"]:
            verdict, missing, used, reason = UNPARSED, [], [], NO_NOUN
        elif not missing:
            verdict, reason = RECOMPUTABLE, ""
        elif all(component in unverified for component in missing):
            verdict, reason = UNVERIFIED_SNAPSHOT, NO_SNAPSHOT
            used = sorted(set(used) | {unverified[c] for c in missing})
        else:
            verdict = NOT_RECOMPUTABLE
            reason = ("no committed artifact the memo names reproduces every component"
                      if artifacts else "the memo names no committed artifact")
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
    parser.add_argument("--no-env-sidecar", action="store_true",
                        help="skip the G62 environment.json sidecar (output then matches master)")
    parser.add_argument("--construct-only", action="store_true",
                        help="walk the filesystem when git has no index (CONSTRUCTS only)")
    parser.add_argument("--txt-header", action="store_true",
                        help="also offer a TXT line count less one header row")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    labels = dict(item.split("=", 1) for item in args.label)
    reports = [scan_memo(memo, root, args.construct_only, args.txt_header)
               for memo in args.memos]
    for report in reports:
        print(f'{labels.get(report["memo"], "?")} | {report["memo"]} | '
              f'n={report["n"]} | {report["totals"]} {report["note"]}')
    if args.csv:
        write_csv(reports, Path(args.csv), labels)
        if not args.no_env_sidecar:
            write_env_sidecar(Path(args.csv).parent, modules=ENV_MODULES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
