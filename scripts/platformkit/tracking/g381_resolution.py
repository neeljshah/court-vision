"""Fixed G381 digest-token grammar and A1 git-history resolution."""
from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

FULL_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
SHORT_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{8,63}(?![0-9a-fA-F])")
FOREIGN_ROOT = re.compile(r"^/c/Users/neelj/nba-track-a\\d+/(.+)$", re.I)


@dataclass(frozen=True)
class Hit:
    """One classified digest token."""
    status: str
    reason: str
    named_path: str
    candidates: str
    form: str = ""


def tokens(line: str) -> list[tuple[str, int]]:
    """The sealed grammar: full hex anywhere, short hex only on sha lines."""
    found = [(match.group(), match.start()) for match in FULL_RE.finditer(line)]
    if re.search(r"sha", line, re.I):
        found.extend((match.group(), match.start()) for match in SHORT_RE.finditer(line)
                     if len(match.group()) < 64)
    return sorted(set(found), key=lambda item: item[1])


def nearest_path(line: str, position: int) -> str:
    """Return the nearest path-like backtick span on a line, or NONE."""
    values = [(match.group(1), match.start(1), match.end(1)) for match in re.finditer(r"`([^`]+)`", line)
              if not FULL_RE.fullmatch(match.group(1)) and not SHORT_RE.fullmatch(match.group(1))
              and any(mark in match.group(1) for mark in ("/", "\\", "."))]
    if not values:
        return "NONE"
    return min(values, key=lambda value: min(abs(position - value[1]), abs(position - value[2])))[0]


def canonical_path(path: str) -> tuple[str, bool]:
    """Strip a citation line range and identify an absolute/pod path."""
    path = re.sub(r":\d+(?:-\d+)?$", "", path)
    match = FOREIGN_ROOT.match(path.replace("\\", "/"))
    if match:
        return match.group(1), False
    return path.replace("\\", "/"), path.startswith("/") or bool(re.match(r"^[A-Za-z]:[\\/]", path))


def run(repo: Path, args: list[str]) -> bytes:
    """Run a read-only Git command against the selected repository."""
    return subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).stdout


@lru_cache(maxsize=None)
def blob_id(repo: Path, commit: str, path: str) -> str | None:
    """Return a committed blob id using a finite Git invocation."""
    try:
        return run(repo, ["rev-parse", "--verify", "%s:%s" % (commit, path)]).decode().strip()
    except subprocess.CalledProcessError:
        return None


@lru_cache(maxsize=None)
def raw_blob(repo: Path, object_id: str) -> bytes:
    """Read each raw blob once, keyed by immutable object id."""
    return run(repo, ["cat-file", "-p", object_id])


@lru_cache(maxsize=None)
def blob(repo: Path, commit: str, path: str) -> bytes | None:
    """Read a committed blob as raw bytes, never from the worktree."""
    object_id = blob_id(repo, commit, path)
    return raw_blob(repo, object_id) if object_id is not None else None


def close_batches() -> None:
    """Retain a no-op teardown hook after replacing the batch reader."""


def digest(data: bytes) -> str:
    """Return the A1-required SHA-256 of raw blob bytes."""
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=None)
def all_tree_objects(repo: Path, commit: str) -> tuple[tuple[str, str], ...]:
    """Enumerate one complete commit tree, preserving path-to-blob identity."""
    try:
        text = run(repo, ["ls-tree", "-rz", commit])
    except subprocess.CalledProcessError:
        return ()
    objects = []
    for item in text.split(b"\0"):
        if not item:
            continue
        metadata, path = item.split(b"\t", 1)
        parts = metadata.split()
        if len(parts) >= 3 and parts[1] == b"blob":
            objects.append((path.decode("utf-8", "surrogateescape"), parts[2].decode("ascii")))
    return tuple(objects)


@lru_cache(maxsize=None)
def tree_objects(repo: Path, commit: str, directory: str) -> tuple[tuple[str, str], ...]:
    """Select an evidence subtree from the cached complete commit tree."""
    prefix = directory.rstrip("/") + "/" if directory else ""
    return tuple((path, object_id) for path, object_id in all_tree_objects(repo, commit)
                 if path.startswith(prefix))


@lru_cache(maxsize=None)
def tree_pairs(repo: Path, commit: str, directory: str) -> tuple[tuple[str, str], ...]:
    """Hash each enumerated evidence blob once, keyed by its Git object id."""
    objects = tree_objects(repo, commit, directory)
    return tuple((path, digest(raw_blob(repo, object_id))) for path, object_id in objects)


def paths_at(repo: Path, commit: str, directory: str) -> tuple[str, ...]:
    """Return cached evidence-tree paths without hashing their blob contents."""
    return tuple(path for path, _ in tree_objects(repo, commit, directory))


def candidate_paths(named: str, memo_path: str, evidence_dir: str) -> tuple[str, ...]:
    """Return A1's first three path candidates, before evidence basename lookup."""
    return (named, (Path(evidence_dir) / named).as_posix(),
            (Path(memo_path).parent / named).as_posix())


def artifact_paths(repo: Path, named: str, landing: str, head: str, evidence_dir: str,
                   memo_path: str) -> tuple[list[str], bool, str]:
    """Resolve A1/A2 named paths, including the whole-landing-tree basename step."""
    if named == "NONE":
        return [], False, ""
    raw, absolute = canonical_path(named)
    if absolute:
        return [named], True, ""
    candidates = list(dict.fromkeys(candidate_paths(raw, memo_path, evidence_dir)))
    for path in candidates:
        if blob_id(repo, landing, path) is not None or blob_id(repo, head, path) is not None:
            return [path], False, ""
    matches = sorted(path for path in paths_at(repo, landing, evidence_dir)
                     if Path(path).name == Path(raw).name)
    if len(matches) == 1:
        return [matches[0]], False, ""
    whole_matches = sorted(path for path, _ in all_tree_objects(repo, landing)
                           if Path(path).name == Path(raw).name)
    if len(whole_matches) == 1:
        return [whole_matches[0]], False, ""
    if len(whole_matches) >= 2:
        return whole_matches, False, "basename ambiguous"
    return candidates, False, ""


def unique_match(token: str, pairs: list[tuple[str, str]]) -> tuple[str | None, bool]:
    """Return matching path or ambiguity; prefixes span all candidates."""
    found = [(path, value) for path, value in pairs if value.startswith(token.lower())]
    values = {value for _, value in found}
    return (found[0][0], False) if len(values) == 1 else (None, len(values) > 1)


def _digest_paths(repo: Path, commit: str, paths: list[str]) -> list[tuple[str, str]]:
    """Hash candidate blobs as raw bytes at one committed revision."""
    return [(path, digest(data)) for path in paths if (data := blob(repo, commit, path)) is not None]


def seal_pairs(repo: Path, commit: str, paths: list[str]) -> list[tuple[str, str]]:
    """Hash bytes above a line beginning ``SEAL sha256``, raw and LF-normalized."""
    pairs = []
    for path in paths:
        data = blob(repo, commit, path)
        match = re.search(br"(?m)^SEAL sha256\b", data or b"")
        if match:
            before = data[:match.start()]
            pairs.extend(((path, digest(before)), (path, digest(before.replace(b"\r\n", b"\n")))))
    return pairs


def compact_candidates(pairs: list[tuple[str, str]]) -> str:
    """Return at most ten path/digest candidates for unresolved-row inspection."""
    unique = list(dict.fromkeys((path, value) for path, value in pairs))[:10]
    return "|".join("%s:%s" % (path, value[:12]) for path, value in unique)


@lru_cache(maxsize=None)
def object_reachable(repo: Path, object_id: str, landing: str) -> bool:
    """Classify a reachable commit or blob without materialising its full graph."""
    try:
        kind = run(repo, ["cat-file", "-t", object_id]).decode().strip()
    except subprocess.CalledProcessError:
        return False
    if kind == "commit":
        return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", object_id, landing],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if kind != "blob":
        return False
    return bool(run(repo, ["log", "-1", "--format=%H", "--find-object=" + object_id, landing]).strip())


def resolve(repo: Path, token: str, named: str, landing: str, head: str, evidence_dir: str,
            memo_dir: str = "") -> Hit:
    """Apply amended A2 resolution order; first matching class wins."""
    paths, absolute, name_reason = artifact_paths(repo, named, landing, head, evidence_dir, memo_dir)
    if absolute:
        return Hit("UNRESOLVED", "pod-only or absolute path", named, "tried=absolute:%s" % named)
    if name_reason:
        pairs = _digest_paths(repo, landing, paths)
        return Hit("UNRESOLVED", name_reason, named, compact_candidates(pairs))
    landing_pairs = _digest_paths(repo, landing, paths)
    head_pairs = _digest_paths(repo, head, paths)
    landing_seals = seal_pairs(repo, landing, paths)
    head_seals = seal_pairs(repo, head, paths)
    crlf_landing = [(path, digest(data.replace(b"\r\n", b"\n"))) for path in paths
                    if (data := blob(repo, landing, path)) is not None]
    crlf_head = [(path, digest(data.replace(b"\r\n", b"\n"))) for path in paths
                 if (data := blob(repo, head, path)) is not None]
    tried_pairs = landing_pairs + landing_seals + head_pairs + head_seals + crlf_landing + crlf_head
    for status, form, pairs in (("IDENTIFIES_AT_LANDING", "raw", landing_pairs),
                                ("IDENTIFIES_AT_LANDING", "seal", landing_seals),
                                ("IDENTIFIES_AT_HEAD_ONLY", "raw", head_pairs),
                                ("IDENTIFIES_AT_HEAD_ONLY", "seal", head_seals),
                                ("CRLF_ONLY", "crlf", crlf_landing),
                                ("CRLF_ONLY", "crlf", crlf_head)):
        path, ambiguous = unique_match(token.lower(), pairs)
        if path:
            return Hit(status, "", path, compact_candidates(tried_pairs), form)
        if ambiguous:
            return Hit("UNRESOLVED", "prefix ambiguous", named, compact_candidates(tried_pairs))
    all_tree = [pair for commit in (landing, head) for pair in tree_pairs(repo, commit, evidence_dir)]
    evidence_seals = [pair for commit in (landing, head)
                      for pair in seal_pairs(repo, commit, list(paths_at(repo, commit, evidence_dir)))]
    memo_paths = [memo_dir] if memo_dir else []
    memo_pairs = [pair for commit in (landing, head) for pair in _digest_paths(repo, commit, memo_paths)]
    memo_seals = [pair for commit in (landing, head) for pair in seal_pairs(repo, commit, memo_paths)]
    unnamed_pairs = all_tree + memo_pairs
    tried_pairs += unnamed_pairs + evidence_seals + memo_seals
    path, ambiguous = unique_match(token.lower(), unnamed_pairs)
    if path:
        return Hit("ARTIFACT_UNNAMED", "", path, compact_candidates(tried_pairs), "raw")
    if ambiguous:
        return Hit("UNRESOLVED", "prefix ambiguous", named, compact_candidates(tried_pairs))
    path, ambiguous = unique_match(token.lower(), evidence_seals + memo_seals)
    if path:
        return Hit("ARTIFACT_UNNAMED", "", path, compact_candidates(tried_pairs), "seal")
    if ambiguous:
        return Hit("UNRESOLVED", "prefix ambiguous", named, compact_candidates(tried_pairs))
    if len(token) == 40 and object_reachable(repo, token.lower(), landing):
        return Hit("OBJECT_ID", "", named, compact_candidates(tried_pairs), "object_id")
    reason = "artifact never committed" if named == "NONE" or not landing_pairs and not head_pairs else "token is not a digest"
    return Hit("UNRESOLVED", reason, named, compact_candidates(tried_pairs))
