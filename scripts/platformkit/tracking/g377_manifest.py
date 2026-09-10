"""G377 dependency manifest: every file the four landed memos name or their readers open.

Two mechanical rules only, sealed in g377_prereg_2026-09-10.md section 3.  M1 scans a
landed memo for path tokens; M2 scans each reader module for quoted string literals.
Nothing enters by judgement and nothing is dropped: a token that resolves to no file is
recorded with its status and its file:line reference, never discarded.

Usage:
    python -m scripts.platformkit.tracking.g377_manifest --repo <path> --out <csv>
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
from pathlib import Path

CLOSURES = (
    ("G363", "g363_ball_coverage_2026-09-09", "g363_"),
    ("G364", "g364_learned_court_presence_2026-09-09", "g364_"),
    ("G367", "g367_init_symmetry_2026-09-09", "g367_"),
    ("G370", "g370_admission_v0_2026-09-09", "g370_"),
)
EVIDENCE = "docs/evidence/tracking"
READER_DIR = "scripts/platformkit/tracking"
EXTENSIONS = (".csv", ".json", ".jsonl", ".md", ".npz", ".parquet", ".pt", ".pth",
              ".png", ".jpg", ".svg", ".sha256", ".txt", ".py")
ROOTS = ("docs/", "scripts/", "src/", "tests/", "kernel/", "api/", "intel/", "data/",
         "models/", "domains/", "config/", "workspace/")
TOKEN_RE = re.compile(r"[A-Za-z0-9_./-]+")
LITERAL_RE = re.compile(r"'([^'\n]*)'|\"([^\"\n]*)\"")
FIELDS = ("closure", "path", "role", "status", "rule", "required_by", "bytes", "tracked",
          "off_pod_source", "present_off_pod", "present_on_pod", "digest")

NOT_A_PATH = "NOT_A_PATH"
POD_ABSOLUTE = "POD_ABSOLUTE"
UNRESOLVED = "UNRESOLVED_PATHLIKE"
DIRECTORY_REF = "DIRECTORY_REF"
TEMPLATE = "TEMPLATE_FRAGMENT"
RESOLVED = "RESOLVED_TRACKED"
UNTRACKED = "RESOLVED_UNTRACKED"
FILE_STATUSES = (RESOLVED, UNTRACKED, POD_ABSOLUTE, UNRESOLVED)
NON_FILE = (NOT_A_PATH, DIRECTORY_REF, TEMPLATE)


def tracked_paths(repo: Path) -> dict[str, tuple[str, int]]:
    """Every path on master with its blob object id and byte size, from one ls-tree."""
    out = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "-l", "master"],
                         capture_output=True, text=True, check=True).stdout
    table: dict[str, tuple[str, int]] = {}
    for line in out.splitlines():
        meta, _tab, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 4 and parts[1] == "blob":
            table[path] = (parts[2], int(parts[3]))
    return table


def is_pathlike(token: str) -> bool:
    """Sealed step (e) labelling: a token that can name a file at all."""
    return (token.endswith(EXTENSIONS) or token.startswith(ROOTS)
            or token.startswith("/") or token.endswith("/"))


def normalise(token: str) -> str:
    """Strip the leading dot/slash run a memo writes as a shorthand prefix."""
    return token.lstrip("./").rstrip(",;:.")


def memo_tokens(text: str) -> list[tuple[int, str]]:
    """M1: every path token in a landed memo, with its line number."""
    hits = []
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        for match in TOKEN_RE.finditer(line):
            token = match.group(0)
            if "/" in token or token.endswith(EXTENSIONS):
                hits.append((number, token))
    return hits


def reader_tokens(text: str) -> list[tuple[int, str]]:
    """M2: every quoted string literal that can name a file, with its line number."""
    hits = []
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        for match in LITERAL_RE.finditer(line):
            token = match.group(1) if match.group(1) is not None else match.group(2)
            if token and ("/" in token or token.endswith(EXTENSIONS)):
                hits.append((number, token))
    return hits


def suffix_match(token: str, closure_dir: str, tracked: dict[str, tuple[str, int]]) -> str:
    """Disclosed step (f): resolve when the token is a suffix of exactly one tracked path.

    Tried inside the closure evidence tree first, then repository-wide.  A token matching two or
    more tracked paths is ambiguous and stays UNRESOLVED: a guess would be an inferred identity.
    """
    tail = "/" + token
    for scope in (closure_dir + "/", ""):
        found = [path for path in tracked if path.startswith(scope) and path.endswith(tail)]
        if len(found) == 1:
            return found[0]
    return ""


def resolve(token: str, closure_dir: str, repo: Path,
            tracked: dict[str, tuple[str, int]]) -> tuple[str, str]:
    """Sealed resolution (a)-(e) plus the disclosed unique-suffix fallback (f)."""
    raw = token
    if raw.startswith("/"):
        return raw, POD_ABSOLUTE
    if any(mark in raw for mark in "{}%"):
        return raw, TEMPLATE
    token = normalise(raw)
    if not token:
        return raw, NOT_A_PATH
    for candidate in (token, closure_dir + "/" + token):
        if candidate in tracked:
            return candidate, RESOLVED
    if not is_pathlike(token):
        return raw, NOT_A_PATH
    for candidate in (token, closure_dir + "/" + token):
        if (repo / candidate).is_file():
            return candidate, UNTRACKED
        if (repo / candidate).is_dir():
            return candidate.rstrip("/") + "/", DIRECTORY_REF
    if token.endswith("/"):
        for candidate in (closure_dir + "/" + token, token):
            if any(name.startswith(candidate) for name in tracked):
                return candidate, RESOLVED
        return token, UNRESOLVED
    found = suffix_match(token, closure_dir, tracked)
    if found:
        return found, RESOLVED
    return token, TEMPLATE if token.startswith("_") else UNRESOLVED


def role_of(path: str) -> str:
    """A reporting label only; no bar depends on it."""
    lower = path.lower()
    if "prereg" in lower:
        return "prereg"
    if lower.startswith("tests/") or "/test_" in lower:
        return "test"
    if lower.endswith(".py"):
        return "code"
    if "ledger" in lower:
        return "ledger"
    if lower.endswith((".jpg", ".png", ".svg")):
        return "native_pixels"
    if lower.endswith((".pt", ".pth")):
        return "weights"
    if any(word in lower for word in ("rating", "adjudic", "label", "agreement", "reference")):
        return "reference"
    if any(word in lower for word in ("predict", "score", "arms", "decision", "confusion")):
        return "prediction"
    return "artifact"


def expand(path: str, status: str, closure_dir: str,
           tracked: dict[str, tuple[str, int]]) -> list[tuple[str, str]]:
    """A directory token INSIDE the closure evidence tree expands to its tracked files.

    The sealed rule names `sheets/dev/`, `raters/` and `strips/` -- all evidence-directory
    subtrees.  A directory token outside that tree (`src/`, `api/`) is a prose reference to a
    tree the row did not write, so it is recorded as DIRECTORY_REF and never expanded: expanding
    it would put thousands of unrelated files in the denominator (B9).
    """
    if not path.endswith("/"):
        return [(path, status)]
    inside = path.startswith(closure_dir + "/") or path.startswith(EVIDENCE + "/")
    if not inside:
        return [(path, DIRECTORY_REF)]
    children = sorted(name for name in tracked if name.startswith(path))
    return [(name, RESOLVED) for name in children] or [(path, UNRESOLVED)]


def build(repo: Path, key: str, stem: str, prefix: str,
          tracked: dict[str, tuple[str, int]]) -> list[dict[str, object]]:
    """One closure's manifest: M1 over its memo, M2 over every reader module."""
    closure_dir = EVIDENCE + "/" + stem
    sources: list[tuple[str, str, list[tuple[int, str]]]] = []
    memo = EVIDENCE + "/" + stem + ".md"
    sources.append(("M1", memo, memo_tokens((repo / memo).read_text(encoding="utf-8"))))
    for module in sorted((repo / READER_DIR).glob(prefix + "*.py")):
        rel = READER_DIR + "/" + module.name
        sources.append(("M2", rel, reader_tokens(module.read_text(encoding="utf-8"))))
    rows: dict[str, dict[str, object]] = {}
    for rule, origin, hits in sources:
        for number, token in hits:
            path, status = resolve(token, closure_dir, repo, tracked)
            for name, state in expand(path, status, closure_dir, tracked):
                entry = rows.setdefault(name, {"closure": key, "path": name,
                                               "role": role_of(name), "status": state,
                                               "rule": rule, "required_by": [],
                                               "bytes": tracked.get(name, ("", -1))[1],
                                               "tracked": int(name in tracked)})
                if rule not in str(entry["rule"]).split("|"):
                    entry["rule"] = str(entry["rule"]) + "|" + rule
                reference = "%s:%d" % (origin, number)
                if reference not in entry["required_by"]:
                    entry["required_by"].append(reference)
    for entry in rows.values():
        entry["required_by"] = "|".join(entry["required_by"][:6])
    return [rows[name] for name in sorted(rows)]


def write(rows: list[dict[str, object]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def restore_fields(rows: list[dict[str, object]], hashes: Path, missing: Path) -> None:
    """Add receipt source, presence, and digest fields without changing manifest labels."""
    with hashes.open(encoding="ascii", newline="") as handle:
        restored = {(row["closure"], row["path"]): row for row in csv.DictReader(handle)}
    with missing.open(encoding="ascii", newline="") as handle:
        absent = {(row["closure"], row["path"]) for row in csv.DictReader(handle)}
    for row in rows:
        prior = restored.get((str(row["closure"]), str(row["path"])))
        row.update({"off_pod_source": "", "present_off_pod": "", "present_on_pod": "", "digest": ""})
        if prior:
            row.update({"off_pod_source": prior["source"], "present_off_pod": 1,
                        "present_on_pod": int(prior["sha256_pod"] not in ("POD_ABSENT", "POD_UNREACHABLE")),
                        "bytes": prior["bytes"], "digest": prior["sha256_restored"]})
        elif (str(row["closure"]), str(row["path"])) in absent:
            row.update({"present_off_pod": 0, "present_on_pod": 0})


def main() -> int:
    parser = argparse.ArgumentParser(description="G377 dependency manifest")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--restore-hashes", type=Path)
    parser.add_argument("--missing", type=Path)
    args = parser.parse_args()
    tracked = tracked_paths(args.repo)
    rows: list[dict[str, object]] = []
    for key, stem, prefix in CLOSURES:
        current = build(args.repo, key, stem, prefix, tracked)
        rows.extend(current)
        named = [row for row in current if row["status"] in FILE_STATUSES]
        print("MANIFEST %s tokens=%d files_named=%d not_a_path=%d" % (
            key, len(current), len(named), len(current) - len(named)))
    if args.restore_hashes or args.missing:
        if not (args.restore_hashes and args.missing):
            raise ValueError("--restore-hashes and --missing are required together")
        restore_fields(rows, args.restore_hashes, args.missing)
    write(rows, args.out)
    print("MANIFEST_TOTAL rows=%d out=%s" % (len(rows), args.out.as_posix()))
    return 0


def demo() -> None:
    """Self-check: the two token rules and the pathlike label behave as sealed."""
    assert memo_tokens("see docs/a/b.csv and 125/125 here")[0][1] == "docs/a/b.csv"
    assert ("125/125" in [t for _n, t in memo_tokens("125/125")])
    assert not is_pathlike("125/125") and is_pathlike("docs/x") and is_pathlike("b.csv")
    assert reader_tokens('x = "recovery.csv"') == [(1, "recovery.csv")]
    assert reader_tokens("y = 'plain'") == []
    assert normalise(".../g1/x.md") == "g1/x.md"
    assert role_of("a/g367_prereg_2026.md") == "prereg" and role_of("a/b.jpg") == "native_pixels"
    print("g377_manifest demo OK")


if __name__ == "__main__":
    raise SystemExit(main())
