#!/usr/bin/env python
"""Git pre-push guard -- refuse a push that would leak a private tree or a secret.

Reads the standard pre-push stdin contract, one line per ref update:
    <local ref> <local sha> <remote ref> <remote sha>

Refuses (exit 1, reason on stderr) when, for any pushed range:
  (a) a commit adds or modifies a path under a private tree (data/, vault/,
      .planning/, docs/research/, docs/strategy/, .claude/, ROADMAP.md), a
      youtube cookie jar, or an auth.json under a .codex home;
  (b) a commit adds a line matching a credential pattern;
  (c) the ref update is a non-fast-forward (force-push is banned repo-wide).

A pure delete (local sha all zeros) is allowed. Allowed pushes exit 0 with one
line on stderr. Stdlib only, ASCII only, no side effects.
"""
import re
import subprocess
import sys

PRIVATE_PREFIXES = ("data/", "vault/", ".planning/", "docs/research/",
                    "docs/strategy/", ".claude/")

SECRET_PATTERNS = [
    ("sk- api key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("aws access key id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github personal token", re.compile(r"ghp_[A-Za-z0-9]{30,}")),
    ("slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("private key block",
     re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("assigned credential literal",
     re.compile(r"(api[_-]?key|secret|token|password)\s*[:=]\s*"
                r"['\"][A-Za-z0-9_\-]{16,}['\"]", re.IGNORECASE)),
]


def _git(args):
    p = subprocess.run(["git"] + args, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def _refuse(msg):
    sys.stderr.write("prepush_guard REFUSED: " + msg + "\n")
    sys.exit(1)


def _is_zero(sha):
    return bool(sha) and set(sha) == set("0")


def _bad_path(path):
    for pre in PRIVATE_PREFIXES:
        if path == pre.rstrip("/") or path.startswith(pre):
            return "private tree " + pre
    parts = path.split("/")
    base = parts[-1]
    if base == "ROADMAP.md":
        return "ROADMAP.md (local-only plan)"
    if "youtube_cookies" in base:
        return "cookie jar"
    if base == "auth.json" and any(p.startswith(".codex") for p in parts[:-1]):
        return "codex auth.json"
    return None


def _scan(sha):
    """Refuse if this commit touches a private path or adds a credential."""
    rc, names = _git(["diff-tree", "--no-commit-id", "--name-only", "-r",
                      "--root", sha])
    if rc != 0:
        _refuse("cannot read commit " + sha[:12])
    for path in names.split("\n"):
        path = path.strip()
        if not path:
            continue
        why = _bad_path(path)
        if why:
            _refuse("commit " + sha[:12] + " touches " + path + " -- " + why)
    # ponytail: merges add no content of their own; their parents are scanned.
    rc, diff = _git(["diff-tree", "--no-commit-id", "-r", "--root", "-p", sha])
    cur = "?"
    for line in diff.split("\n"):
        if line.startswith("+++ "):
            cur = line[4:].strip()
            if cur.startswith("b/"):
                cur = cur[2:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for label, rx in SECRET_PATTERNS:
            if rx.search(line):
                # ponytail: name the pattern and the file, never echo the value.
                _refuse("commit " + sha[:12] + " adds a " + label
                        + " in " + cur)


def _commits(local, remote):
    if not _is_zero(remote) and _git(["cat-file", "-e",
                                      remote + "^{commit}"])[0] == 0:
        rc, out = _git(["rev-list", remote + ".." + local])
    else:
        rc, out = _git(["rev-list", local, "--not", "--remotes"])
    if rc != 0:
        _refuse("git rev-list failed for " + local[:12])
    return [c for c in out.split() if c]


def main():
    total = 0
    for raw in sys.stdin.read().split("\n"):
        parts = raw.split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, remote_ref, remote_sha = parts
        if _is_zero(local_sha):
            continue  # pure delete
        if not _is_zero(remote_sha):
            known = _git(["cat-file", "-e", remote_sha + "^{commit}"])[0] == 0
            if known and _git(["merge-base", "--is-ancestor",
                               remote_sha, local_sha])[0] != 0:
                _refuse("non-fast-forward update to " + remote_ref
                        + " (force-push is banned; rebase instead)")
        for sha in _commits(local_sha, remote_sha):
            _scan(sha)
            total += 1
    sys.stderr.write("prepush_guard: %d commits scanned, clean\n" % total)
    sys.exit(0)


if __name__ == "__main__":
    main()
