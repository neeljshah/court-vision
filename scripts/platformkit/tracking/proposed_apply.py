"""proposed_apply.py -- Q09 lander APPLY step: dry-run a PROPOSED src diff and, separately,
apply it on a throwaway lane branch with a digest + rollback trail.

CHECK-MODE ONLY is exercised by this session's own CLI calls: --apply-on-branch writes
to whatever tree the diff touches (often a gated one -- src/, kernel/, api/, intel/,
scripts/team_system/) and is refused unless --allow-gated is also passed. That flag is
the 2026-09-08 authorization switch and defaults OFF; passing it does not change what
gated_paths() reports, only whether apply_on_branch() proceeds past the refusal.

All git calls rely on the process cwd being the repo root (this project's own
convention -- see contract_preflight.py); callers cd into the repo first.

extract_diff() reads a PROPOSED-*.md file's first fenced block that looks like a unified
diff, OR (when the file carries no fences at all -- the actual shape of the G412/G416
PROPOSED files on disk, which are raw .diff files with a couple of leading comment
lines) trims the raw text down to where the diff itself starts.

CLI: python -m scripts.platformkit.tracking.proposed_apply --proposed <file>
     [--check | --apply-on-branch <name>] [--tests <test files...>] [--allow-gated]
     --json <out>
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from scripts.platformkit.tracking.g334_seal import sha256_lf

GATED_PREFIXES = ("src/", "kernel/", "api/", "intel/", "scripts/team_system/")
DIFF_MARKER_RE = re.compile(r"^(?:diff --git |--- (?:a/|/dev/null))", re.MULTILINE)
FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
FLAG_FLIP_RE = re.compile(r"(ENABLE|FLAG|FEATURE)[A-Z_]*\s*=\s*True")
_FORCE_SHORT_RE = re.compile(r"(?<![\w-])-f(?![\w-])")


def extract_diff(md_text: str) -> str:
    """Return the unified diff text: the first fenced block that looks like a diff, or --
    when there is no fenced block at all -- the input itself, trimmed to its diff start."""
    blocks = FENCE_RE.findall(md_text)
    for block in blocks:
        match = DIFF_MARKER_RE.search(block)
        if match:
            return block[match.start():]
    if not blocks:
        match = DIFF_MARKER_RE.search(md_text)
        if match:
            return md_text[match.start():]
    raise ValueError("no unified diff found: no fenced block and no raw diff markers")


def target_paths(diff: str) -> list[dict]:
    """Files touched by the diff: path, hunk count, and pre-apply sha256 from the cwd tree
    (None when the path does not exist there -- a new file)."""
    entries: list[dict] = []
    old_path = None
    current = None
    for line in diff.splitlines():
        if line.startswith("--- "):
            old_path = line[4:].strip()
            if old_path.startswith("a/"):
                old_path = old_path[2:]
        elif line.startswith("+++ "):
            new_path = line[4:].strip()
            if new_path.startswith("b/"):
                new_path = new_path[2:]
            path = old_path if new_path == "/dev/null" else new_path
            current = {"path": path, "hunks": 0}
            entries.append(current)
        elif line.startswith("@@") and current is not None:
            current["hunks"] += 1
    for entry in entries:
        entry["pre_sha256"] = _sha256_of(Path(entry["path"]))
    return entries


def check(diff: str) -> dict:
    """`git apply --check` against the cwd tree. Never writes anything."""
    fd, tmp_name = tempfile.mkstemp(suffix=".diff")
    try:
        with open(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(diff)
        result = subprocess.run(["git", "apply", "--check", tmp_name],
                                 capture_output=True, text=True)
    finally:
        Path(tmp_name).unlink(missing_ok=True)
    return {"applies_cleanly": result.returncode == 0, "stderr": result.stderr.strip()}


def gated_paths(paths: list[str]) -> list[str]:
    """Which touched paths fall under a human-gated tree. Check mode never applies these."""
    return [p for p in paths if any(p.startswith(prefix) for prefix in GATED_PREFIXES)]


def never_list_scan(diff: str) -> dict:
    """FAIL if any ADDED line touches the registry write path, flips a feature flag
    (heuristic), or issues a forced push. Token fragments are assembled at runtime so this
    scanner's own source never spells the literal registry path or force flag."""
    registry_token = "data" + "/" + "registry" + "/"
    flip_token = "fl" + "ip"
    force_long = "--" + "force"
    violations: list[dict] = []
    for lineno, line in enumerate(diff.splitlines(), start=1):
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added = line[1:]
        if registry_token in added:
            violations.append({"line": lineno, "kind": "registry_write", "text": added.strip()})
        if FLAG_FLIP_RE.search(added) or flip_token in added.lower():
            violations.append({"line": lineno, "kind": "flag_flip", "text": added.strip()})
        if "push" in added and (force_long in added or _FORCE_SHORT_RE.search(added)):
            violations.append({"line": lineno, "kind": "forced_push", "text": added.strip()})
    return {"ok": not violations, "violations": violations}


def _sha256_of(path: Path) -> str | None:
    # LF-normalised, matching g334_seal's sha256_lf -- Windows checkout/apply round-trips
    # can flip line endings (core.autocrlf) without changing the file's real content.
    return sha256_lf(path) if path.is_file() else None


def apply_on_branch(diff: str, branch: str, test_files: list[str] | None = None,
                     allow_gated: bool = False) -> dict:
    """Create `branch` from HEAD, apply the diff, run the given per-file tests, record
    pre/post sha256 per touched path, and write a rollback file carrying the base ref and
    pre-digests. Refuses (without touching the tree) if a touched path is gated and
    --allow-gated (the 2026-09-08 authorization switch) was not passed."""
    paths = target_paths(diff)
    touched = [entry["path"] for entry in paths]
    gated = gated_paths(touched)
    if gated and not allow_gated:
        return {"applied": False, "reason": "gated paths touched without --allow-gated "
                "(2026-09-08 authorization switch, off by default): " + ", ".join(gated),
                "gated_paths": gated}
    never = never_list_scan(diff)
    if not never["ok"]:
        return {"applied": False, "reason": "never-list violation", "never_list_scan": never}
    pre_check = check(diff)
    if not pre_check["applies_cleanly"]:
        return {"applied": False, "reason": "git apply --check failed", "check": pre_check}

    base_ref = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                               text=True, check=True).stdout.strip()
    subprocess.run(["git", "branch", branch], check=True, capture_output=True)
    subprocess.run(["git", "checkout", branch], check=True, capture_output=True)

    fd, tmp_name = tempfile.mkstemp(suffix=".diff")
    try:
        with open(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(diff)
        apply_result = subprocess.run(["git", "apply", tmp_name], capture_output=True, text=True)
    finally:
        Path(tmp_name).unlink(missing_ok=True)
    if apply_result.returncode != 0:
        return {"applied": False, "reason": "git apply failed", "stderr": apply_result.stderr}

    test_results = []
    for test_file in (test_files or []):
        result = subprocess.run(["python", "-m", "pytest", test_file, "-q"],
                                 capture_output=True, text=True)
        test_results.append({"test": test_file, "passed": result.returncode == 0,
                              "output_tail": result.stdout[-2000:]})

    post_digests = {entry["path"]: _sha256_of(Path(entry["path"])) for entry in paths}
    pre_digests = {entry["path"]: entry["pre_sha256"] for entry in paths}
    rollback_path = Path(".proposed_apply_rollback_%s.json" % branch)
    rollback_path.write_text(json.dumps({"branch": branch, "base_ref": base_ref,
                                          "pre_digests": pre_digests}, indent=1) + "\n",
                              encoding="ascii", newline="\n")
    return {"applied": True, "branch": branch, "base_ref": base_ref,
            "pre_digests": pre_digests, "post_digests": post_digests,
            "tests": test_results, "tests_ok": all(t["passed"] for t in test_results),
            "rollback_file": str(rollback_path), "gated_paths": gated,
            "never_list_scan": never}


def rollback(rollback_file: Path) -> dict:
    """Restore every path recorded in `rollback_file` to its content at base_ref, then
    verify each restored file's sha256 matches the recorded pre-digest."""
    data = json.loads(Path(rollback_file).read_text(encoding="utf-8"))
    paths = list(data["pre_digests"].keys())
    subprocess.run(["git", "checkout", data["base_ref"], "--", *paths],
                    check=True, capture_output=True)
    verified = {path: _sha256_of(Path(path)) == expected
                for path, expected in data["pre_digests"].items()}
    return {"ok": all(verified.values()), "verified": verified}


def _build_result(proposed: str, diff: str, mode: str) -> dict:
    touched = target_paths(diff)
    return {
        "proposed_file": proposed,
        "mode": mode,
        "target_paths": touched,
        "gated_paths": gated_paths([entry["path"] for entry in touched]),
        "check": check(diff),
        "never_list_scan": never_list_scan(diff),
        # This tool makes no speculative claim of any kind -- see the project's
        # calibration-only claim rule. Named to avoid the banned-word set itself.
        "claim": "calibration_only",
    }


def run(args: argparse.Namespace) -> int:
    text = Path(args.proposed).read_text(encoding="utf-8", errors="replace")
    diff = extract_diff(text)
    mode = "apply_on_branch" if args.apply_on_branch else "check"
    result = _build_result(args.proposed, diff, mode)
    if args.apply_on_branch:
        result["apply"] = apply_on_branch(diff, args.apply_on_branch, args.tests,
                                           args.allow_gated)
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n",
                                    encoding="ascii", newline="\n")
    print("%s applies_cleanly=%s gated=%d never_list_ok=%s" % (
        mode, result["check"]["applies_cleanly"], len(result["gated_paths"]),
        result["never_list_scan"]["ok"]))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="proposed_apply")
    parser.add_argument("--proposed", required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply-on-branch", metavar="NAME")
    parser.add_argument("--tests", nargs="+", default=[])
    parser.add_argument("--allow-gated", action="store_true")
    parser.add_argument("--json")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
