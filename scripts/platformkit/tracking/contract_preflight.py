"""contract_preflight.py -- Q08 shared contract preflight linter.

Nine mechanical checks every landable row must survive before ~/bin/lane_commit.py
seals a commit: banned vocabulary, CRLF, LOC cap, additive schema, head-slice census,
spec-threshold byte match, a PROPOSED diff applying cleanly, a removed/renamed
artifact path (the G386 class), and row duplication (the G372 class). The last two
live in contract_preflight_extra.py to keep this file under the 300 LOC rail.

Check 1 reuses g334_seal's canonical four-word ban (character-code patterns, never
spelled literally) for the word scan, which stays strict on purpose: a memo that
narrates its own scan terms in prose is a real hit, not a false one, because the
rail forbids spelling the words even in a sentence declaring their absence. The
retracted-figure scan is stricter than g334_seal's: any run of 32+ hex characters
(a digest) is masked out before scanning, and a figure must be bounded by a
non-alphanumeric character on both sides, so it can never fire inside a SHA-256
hex string. The two allowed exceptions -- the JSON/CSV field name and this rule
file's own path -- are assembled from character codes at runtime so this file
never spells them either.

CLI: python -m scripts.platformkit.tracking.contract_preflight --paths <files...>
     [--base master] [--spec <spec file>] [--proposed <diff file>]
     [--loc-exempt <glob>]... [--json <out>]
Exit 0 on pass, 3 on any FAIL. One line per check: "PASS|FAIL <check> <detail>".
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import io
import json
import re
import subprocess
from pathlib import Path

from scripts.platformkit.tracking.contract_preflight_extra import (
    check_removed_artifact, check_row_duplication,
)
from scripts.platformkit.tracking.g334_seal import BANNED_NUMBERS, BARE_INTEGER, BARE_LABEL, WORD_RE


def _word(*codes: int) -> str:
    return "".join(chr(code) for code in codes)


# The two Q6 exceptions -- assembled at runtime, never spelled as a plain literal.
EXC_FIELD = _word(101, 100, 103, 101) + "_" + _word(99, 108, 97, 105, 109, 101, 100)
EXC_PATH = ".claude/rules/no-" + _word(101, 100, 103, 101) + "-claims.md"

SEALED_KEY_RE = re.compile(r"(sealed|selected|drawn)_(keys|windows|frames|sections)$")
THRESHOLD_LINE_RE = re.compile(r"^(THRESHOLD|BAR|ACCEPTANCE RULE)\b")
NUMERIC_LITERAL_RE = re.compile(r"-?\d+(?:\.\d+)?%?")
CHECK_NAMES = ("vocab", "crlf", "loc", "schema", "head_slice", "spec_threshold", "proposed",
               "removed_artifact", "row_duplication")

DIGEST_RE = re.compile(r"[0-9a-fA-F]{32,}")
_ALNUM_BOUND = r"(?<![A-Za-z0-9])(%s)(?![A-Za-z0-9])"
# Figures must be bounded by non-alphanumeric characters on both sides (never inside a digest).
NUMBER_RE = re.compile(_ALNUM_BOUND % "|".join(n.replace(".", r"\.") for n in BANNED_NUMBERS))
BARE_RE = re.compile(_ALNUM_BOUND % re.escape(BARE_INTEGER))


def _mask(line: str) -> str:
    line = line.replace(EXC_PATH, " " * len(EXC_PATH)).replace(EXC_FIELD, " " * len(EXC_FIELD))
    return DIGEST_RE.sub(lambda m: " " * len(m.group(0)), line)


def check_vocab(paths: list[Path]) -> tuple[bool, str, list[dict]]:
    hits: list[dict] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        for lineno, raw in enumerate(text.split("\n"), start=1):
            masked = _mask(raw)
            for regex, kind in ((WORD_RE, "word"), (NUMBER_RE, "number"), (BARE_RE, BARE_LABEL)):
                for match in regex.finditer(masked):
                    hits.append({"path": path.as_posix(), "line": lineno, "kind": kind,
                                 "text": match.group(0)})
    ok = not hits
    detail = ("clean over %d files" % len(paths) if ok else
              "%d hit(s), first %s:%d %s %r" % (len(hits), hits[0]["path"], hits[0]["line"],
                                                 hits[0]["kind"], hits[0]["text"]))
    return ok, detail, hits


def _autocrlf_setting() -> str:
    result = subprocess.run(["git", "config", "--get", "core.autocrlf"],
                             capture_output=True, text=True)
    return result.stdout.strip().lower() or "false"


def _index_eol(path: Path) -> str | None:
    """The git index-side eol tag (lf/crlf/mixed/-text) for a tracked path, else None."""
    result = subprocess.run(["git", "ls-files", "--eol", "--", path.as_posix()],
                             capture_output=True, text=True)
    line = result.stdout.strip()
    if not line:
        return None
    first = line.split()[0]
    return first.split("/", 1)[1] if "/" in first else None


def check_crlf(paths: list[Path]) -> tuple[bool, str, list[dict]]:
    """Tracked files: FAIL only when the INDEX side is crlf. Untracked files: PASS with a
    note (core.autocrlf normalizes on add) unless core.autocrlf is false, in which case
    scan raw bytes -- this covers the sealed-digest landmine without the checkout artifact."""
    autocrlf = _autocrlf_setting()
    bad, untracked_notes = [], []
    for path in paths:
        eol = _index_eol(path)
        if eol is not None:
            if eol == "crlf":
                bad.append({"path": path.as_posix(), "reason": "index i/crlf"})
            continue
        if autocrlf != "false":
            untracked_notes.append(path.as_posix())
            continue
        if b"\r\n" in path.read_bytes():
            bad.append({"path": path.as_posix(), "reason": "raw bytes (untracked, autocrlf=false)"})
    ok = not bad
    if ok:
        detail = "no index-side CRLF over %d file(s)" % len(paths)
        if untracked_notes:
            detail += "; %d untracked, core.autocrlf normalizes on add" % len(untracked_notes)
    else:
        detail = "; ".join("%s (%s)" % (d["path"], d["reason"]) for d in bad[:5])
    return ok, detail, bad


def check_loc(paths: list[Path], exempt: list[str]) -> tuple[bool, str, list[dict]]:
    over = []
    for path in paths:
        if path.suffix != ".py" or any(fnmatch.fnmatch(path.as_posix(), g) for g in exempt):
            continue
        n = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        if n > 300:
            over.append({"path": path.as_posix(), "lines": n})
    ok = not over
    detail = "all .py <= 300 LOC" if ok else "; ".join("%s=%d" % (d["path"], d["lines"]) for d in over)
    return ok, detail, over


def _keys_of(text: str, suffix: str) -> set[str] | None:
    if suffix == ".json":
        try:
            data = json.loads(text)
        except ValueError:
            return None
        if isinstance(data, dict):
            return set(data.keys())
        if isinstance(data, list):
            keys: set[str] = set()
            for item in data:
                if isinstance(item, dict):
                    keys |= set(item.keys())
            return keys
        return None
    if suffix == ".csv":
        header = next(csv.reader(io.StringIO(text)), None)
        return set(header) if header else None
    return None


def check_schema(paths: list[Path], base: str) -> tuple[bool, str, list[dict]]:
    problems, notes = [], []
    for path in paths:
        if path.suffix not in (".json", ".csv"):
            continue
        cur = _keys_of(path.read_text(encoding="utf-8", errors="replace"), path.suffix)
        if cur is None:
            continue
        shown = subprocess.run(["git", "show", "%s:%s" % (base, path.as_posix())],
                                capture_output=True, text=True)
        if shown.returncode != 0:
            notes.append("%s new (no %s baseline)" % (path.as_posix(), base))
            continue
        base_keys = _keys_of(shown.stdout, path.suffix)
        if base_keys is None:
            continue
        removed = base_keys - cur
        if removed:
            problems.append({"path": path.as_posix(), "removed": sorted(removed)})
    ok = not problems
    detail = ("; ".join(notes) if notes else "additive over checked artifacts") if ok else "; ".join(
        "%s removed %s" % (d["path"], d["removed"]) for d in problems)
    return ok, detail, problems


def check_head_slice(paths: list[Path]) -> tuple[bool, str, list[dict]]:
    hits = []
    for path in paths:
        if path.suffix != ".json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            match = SEALED_KEY_RE.search(key)
            if not match or not isinstance(value, list):
                continue
            eligible_key = "eligible_" + match.group(2)
            eligible = data.get(eligible_key)
            if not isinstance(eligible, list):
                continue
            n = len(value)
            if n and n < len(eligible) and value == eligible[:n]:
                hits.append({"path": path.as_posix(), "key": key, "eligible_key": eligible_key,
                             "n": n, "eligible_n": len(eligible)})
    ok = not hits
    detail = "no head slices" if ok else "; ".join(
        "%s:%s is %s[:%d] of %d" % (d["path"], d["key"], d["eligible_key"], d["n"], d["eligible_n"])
        for d in hits)
    return ok, detail, hits


def check_spec_threshold(spec_path: Path | None, paths: list[Path]) -> tuple[bool, str, list[str]]:
    if spec_path is None:
        return True, "no --spec given", []
    literals: set[str] = set()
    for line in spec_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if THRESHOLD_LINE_RE.match(line):
            literals |= set(NUMERIC_LITERAL_RE.findall(line))
    if not literals:
        return True, "no THRESHOLD/BAR/ACCEPTANCE RULE lines in spec", []
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in paths)
    missing = sorted(lit for lit in literals if lit not in corpus)
    ok = not missing
    detail = "%d literal(s) matched" % len(literals) if ok else "missing " + ", ".join(missing)
    return ok, detail, missing


def check_proposed(diff_path: Path | None) -> tuple[bool, str, int | None]:
    if diff_path is None:
        return True, "no --proposed given", None
    result = subprocess.run(["git", "apply", "--check", str(diff_path)],
                             capture_output=True, text=True)
    ok = result.returncode == 0
    detail = "applies cleanly" if ok else (result.stderr.strip()[:300] or "git apply --check failed")
    return ok, detail, result.returncode


def run(args: argparse.Namespace) -> int:
    paths = [Path(p) for p in args.paths]
    spec_path = Path(args.spec) if args.spec else None
    proposed_path = Path(args.proposed) if args.proposed else None
    results = {
        "vocab": check_vocab(paths),
        "crlf": check_crlf(paths),
        "loc": check_loc(paths, args.loc_exempt or []),
        "schema": check_schema(paths, args.base),
        "head_slice": check_head_slice(paths),
        "spec_threshold": check_spec_threshold(spec_path, paths),
        "proposed": check_proposed(proposed_path),
        "removed_artifact": check_removed_artifact(paths, args.base),
        "row_duplication": check_row_duplication(paths),
    }
    all_ok = True
    for name in CHECK_NAMES:
        ok, detail, _ = results[name]
        all_ok = all_ok and ok
        print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))
    if args.json:
        summary = {name: {"pass": results[name][0], "detail": results[name][1]} for name in CHECK_NAMES}
        summary["ok"] = all_ok
        Path(args.json).write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n",
                                    encoding="ascii", newline="\n")
    return 0 if all_ok else 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contract_preflight")
    parser.add_argument("--paths", nargs="+", required=True)
    parser.add_argument("--base", default="master")
    parser.add_argument("--spec")
    parser.add_argument("--proposed")
    parser.add_argument("--loc-exempt", action="append", default=[])
    parser.add_argument("--json")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
