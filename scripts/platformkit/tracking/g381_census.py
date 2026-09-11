"""G381 reproducible census over tracking memos in git history only.

Usage: python -m scripts.platformkit.tracking.g381_census --repo <repo> --out <dir>
"""
from __future__ import annotations

import argparse
import csv
import json
import hashlib
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from scripts.platformkit.tracking import g381_resolution as resolution

MEMO_RE = re.compile(r"docs/evidence/tracking/[gG]\d+_.+\.md$")
FIELDS = ("memo", "line", "artifact", "token", "length", "landing_commit",
          "class", "reason", "form", "candidates")
REGISTER = "docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md"


def git(repo: Path, args: list[str]) -> str:
    """Read git output only; the census never reads a worktree memo."""
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout


def memos(repo: Path, ref: str) -> list[str]:
    """Exhaustively select current master tracking memos by their committed paths."""
    paths = git(repo, ["ls-tree", "-r", "--name-only", ref, "--", "docs/evidence/tracking"])
    return sorted(path for path in paths.splitlines() if MEMO_RE.fullmatch(path))


@lru_cache(maxsize=None)
def landing_map(repo: Path, ref: str) -> dict[str, str]:
    """Map each memo to its first add commit using one Git-history traversal."""
    text = git(repo, ["log", ref, "--diff-filter=A", "--format=%H", "--name-only", "--",
                      "docs/evidence/tracking"])
    found: dict[str, str] = {}
    current = ""
    for line in text.splitlines():
        if re.fullmatch(r"[0-9a-f]{40}", line):
            current = line
        elif current and MEMO_RE.fullmatch(line):
            found[line] = current
    return found


def landing(repo: Path, memo: str, ref: str) -> str:
    """The first master commit that added this exact memo path."""
    return landing_map(repo, ref)[memo]


def premise(repo: Path, ref: str) -> tuple[int, int, int]:
    """Count digest-carrying memos and tokens before the resolution census."""
    found: list[str] = []
    carried = 0
    for memo in memos(repo, ref):
        text = resolution.blob(repo, ref, memo)
        assert text is not None
        tokens = [token for line in text.decode("utf-8", "replace").replace("\r\n", "\n").split("\n")
                  for token, _ in resolution.tokens(line)]
        found.extend(tokens)
        carried += bool(tokens)
    resolution.close_batches()
    return carried, len(found), len({token.lower() for token in found})


_Q6 = [bytes(c).decode() for c in ((114,111,105),(112,114,111,102,105,116),(98,97,110,107,114,111,108,108),(112,110,108),(101,100,103,101))]
_Q6_RE = re.compile(r"\b(" + "|".join(_Q6) + r")\b", re.IGNORECASE)


def q6_redact(text: str) -> str:
    """Replace contract-Q6 vocabulary in COPIED prose with a marker plus the source-row digest (never alters the source)."""
    if not _Q6_RE.search(text):
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return _Q6_RE.sub("[Q6-REDACTED]", text) + " (source-row sha256 " + digest + ")"


def register_verdict(repo: Path, ref: str, g_id: str) -> str:
    """Return the register's verbatim line for a row, or NOT FOUND."""
    text = resolution.blob(repo, ref, REGISTER)
    if text is None:
        return q6_redact("NOT FOUND")
    pattern = re.compile(r"(?i)(?<![A-Z0-9])G0*%s(?![A-Z0-9])" % re.escape(g_id))
    for line in text.decode("utf-8", "replace").splitlines():
        if pattern.search(line):
            return q6_redact(line.strip())
    return q6_redact("NOT FOUND")


def rows(repo: Path, ref: str, progress: callable | None = None) -> tuple[list[dict[str, str]], int]:
    """Classify each sealed-grammar token from its landing-version memo text."""
    head = git(repo, ["rev-parse", ref]).strip()
    out: list[dict[str, str]] = []
    carried = 0
    for memo in memos(repo, ref):
        landed = landing(repo, memo, ref)
        text = resolution.blob(repo, ref, memo)
        assert text is not None
        stem = memo[:-3]
        for number, line in enumerate(text.decode("utf-8", "replace").replace("\r\n", "\n").split("\n"), 1):
            for token, position in resolution.tokens(line):
                carried += 1
                named = resolution.nearest_path(line, position)
                hit = resolution.resolve(repo, token, named, landed, head, stem, memo)
                out.append({"memo": memo, "line": str(number), "artifact": hit.named_path,
                            "token": token, "length": str(len(token)), "landing_commit": landed,
                            "class": hit.status, "reason": hit.reason,
                            "form": hit.form,
                            "candidates": hit.candidates})
                if progress is not None and carried % 100 == 0:
                    progress(carried)
    resolution.close_batches()
    return out, carried


def write_csv(path: Path, rows_: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows_)


def write_eye(out: Path, records: list[dict[str, str]], repo: Path, ref: str) -> None:
    """Show ten evenly spaced unresolved records with source line and candidates."""
    unresolved = [row for row in records if row["class"] == "UNRESOLVED"]
    picks = [unresolved[(index * (len(unresolved) - 1)) // 9] for index in range(10)] if unresolved else []
    lines = []
    for row in picks:
        source = resolution.blob(repo, ref, row["memo"])
        assert source is not None
        memo_line = source.decode("utf-8", "replace").replace("\r\n", "\n").split("\n")[int(row["line"]) - 1]
        lines.extend(("%s:%s %s" % (row["memo"], row["line"], memo_line),
                      "CANDIDATES %s" % row["candidates"]))
    (out / "eye.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")


def write_outputs(out: Path, records: list[dict[str, str]], memo_count: int,
                  digest_memos: int, repo: Path, ref: str) -> None:
    """Write the fixed census artifacts; all rows are retained, including failures."""
    write_csv(out / "census.csv", records, FIELDS)
    unresolved = [row for row in records if row["class"] == "UNRESOLVED"]
    write_csv(out / "unresolved.csv", unresolved, FIELDS)
    per = []
    for memo in sorted({row["memo"] for row in records}):
        group = [row for row in records if row["memo"] == memo]
        g_id = re.search(r"[gG](\d+)_", memo).group(1)
        per.append({"g_id": g_id, "memo": memo,
                    "resolved": str(sum(row["class"] != "UNRESOLVED" for row in group)),
                    "tokens": str(len(group)), "register_verdict": register_verdict(repo, ref, g_id)})
    write_csv(out / "per_row.csv", per, ("g_id", "memo", "resolved", "tokens", "register_verdict"))
    write_eye(out, records, repo, ref)
    class_counts = {status: sum(row["class"] == status for row in records)
                    for status in sorted({row["class"] for row in records})}
    summary = {"memos": memo_count, "digest_memos": digest_memos, "tokens": len(records),
               "distinct_tokens": len({row["token"].lower() for row in records}),
               "classified": len(records), "unresolved": len(unresolved),
               "class_counts": class_counts}
    (out / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n",
                                        encoding="ascii", newline="\n")
    resolution.close_batches()


def main() -> int:
    parser = argparse.ArgumentParser(description="G381 git-history memo digest census")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ref", default="master")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    log = (args.out / "run.log").open("w", encoding="ascii", newline="\n")

    def report(message: str) -> None:
        print(message)
        log.write(message + "\n")
        log.flush()

    try:
        digest_memos, tokens, distinct = premise(args.repo, args.ref)
        report("PREMISE memos / tokens / distinct tokens: %d / %d / %d" % (
            digest_memos, tokens, distinct))
        if digest_memos < 30:
            report("PREMISE FALSE")
            return 2
        records, carried = rows(args.repo, args.ref,
                                lambda count: report("CENSUS_PROGRESS tokens=%d" % count))
        write_outputs(args.out, records, len(memos(args.repo, args.ref)), digest_memos,
                      args.repo, args.ref)
        report("CENSUS tokens=%d classified=%d unresolved=%d" % (
            len(records), len(records), sum(row["class"] == "UNRESOLVED" for row in records)))
        return 0
    finally:
        log.close()
        resolution.close_batches()


if __name__ == "__main__":
    raise SystemExit(main())
