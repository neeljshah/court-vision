"""S678 ordering check: was the cited corpus manifest committed BEFORE the night record?

Read-only `git -C <repo>` calls; commit dates are self-asserted by the committer and are NEVER used.
BEFORE holds only when all three are true:
  1. the night record's FIRST add commit N (full history) exists;
  2. N's tree holds the manifest path with exactly the cited bytes (sha256 of the blob);
  3. some commit C != N in N's own history of the manifest path holds those same bytes
     (every commit listed by `git log N -- path` is N or an ancestor of N; C is also re-checked with
     `merge-base --is-ancestor`).
So a placeholder manifest rewritten after the night, a manifest deleted before the night and
re-added after it, and a manifest added in the same commit as the night record are all NOT_BEFORE.
The cited path and sha are ALWAYS read from the same night-record citation as committed in N
(`corpus_manifest` object, or both top-level); caller-supplied path and sha must equal it.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

SHA_LEN = 64
NIGHT_PARSE_ERRORS = 0


def _git(repo: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, "-c", "core.quotepath=off", *args],
                          capture_output=True, timeout=60, check=check)


def _blob(repo: str, commit: str, rel: str):
    """Bytes of <commit>:<rel>, or None when the path is absent in that commit."""
    out = _git(repo, "show", f"{commit}:{rel}", check=False)
    return out.stdout if out.returncode == 0 else None


def night_first_commit(repo: str, night_rel: str):
    out = _git(repo, "log", "--full-history", "--diff-filter=A", "--reverse", "--format=%H", "--", night_rel)
    lines = out.stdout.decode("ascii").split()
    return lines[0] if lines else None


def cited_manifest_from_night(repo: str, commit: str, night_rel: str):
    global NIGHT_PARSE_ERRORS
    raw = _blob(repo, commit, night_rel)
    try:
        record = json.loads(raw.decode("utf-8")) if raw is not None else None
    except (UnicodeDecodeError, ValueError):
        NIGHT_PARSE_ERRORS += 1
        return None
    if not isinstance(record, dict):
        return None
    citation = record.get("corpus_manifest") if isinstance(record.get("corpus_manifest"), dict) else record
    path, sha = citation.get("corpus_manifest_path"), citation.get("corpus_manifest_sha256")
    if not isinstance(path, str) or not path or not isinstance(sha, str) or len(sha) != SHA_LEN:
        return None
    return path, sha


def committed_before(repo: str, manifest_rel: str, night_rel: str, cited_sha=None) -> tuple:
    """(True, 'manifest_before_night') or (False, <named reason>)."""
    manifest_rel = manifest_rel.replace("\\", "/")
    night = night_first_commit(repo, night_rel)
    if night is None:
        return False, "night_not_committed"
    citation = cited_manifest_from_night(repo, night, night_rel)
    if citation is None:
        return False, "night_cites_no_manifest"
    night_path, night_sha = citation
    if manifest_rel != night_path:
        return False, "manifest_path_differs_from_night"
    if cited_sha is not None and cited_sha != night_sha:
        return False, "cited_sha_differs_from_night"
    cited_sha = night_sha
    at_night = _blob(repo, night, manifest_rel)
    if at_night is None or hashlib.sha256(at_night).hexdigest() != cited_sha:
        return False, "night_commit_lacks_cited_manifest"
    out = _git(repo, "log", "--full-history", "--format=%H", night, "--", manifest_rel)
    for commit in out.stdout.decode("ascii").split():
        if commit == night:
            continue
        raw = _blob(repo, commit, manifest_rel)
        if raw is None or hashlib.sha256(raw).hexdigest() != cited_sha:
            continue
        if _git(repo, "merge-base", "--is-ancestor", commit, night, check=False).returncode == 0:
            return True, "manifest_before_night"
    return False, "manifest_not_committed_before_night"
