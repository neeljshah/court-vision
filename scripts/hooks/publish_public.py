#!/usr/bin/env python
"""Export the public subset of the full tree into the public-repo worktree.

The full tree lives on `master` in the main working directory and is pushed to
the PRIVATE repository. The PUBLIC repository (origin) only ever receives the
paths allowed by scripts/hooks/public_allowlist.txt. This script makes the
public worktree's tree equal to allowlist(source tree) and commits the result;
it never pushes. Run the gates, then push from the worktree:

    python scripts/hooks/publish_public.py            # stage + commit the export
    git -C ../court-vision-public push origin public-master:master

Refuses when origin/master is not already merged into the source branch, so a
direct push to the public repo (the analytics lanes) is never overwritten.
Stdlib only, ASCII only.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prepush_guard import is_public_path, load_allowlist  # noqa: E402


def git(cwd, *args, data=None):
    p = subprocess.run(["git"] + list(args), cwd=cwd, input=data,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        sys.exit("git %s failed: %s" % (" ".join(args[:3]),
                                        p.stderr.decode("utf-8", "replace")))
    return p.stdout.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="master")
    ap.add_argument("--worktree", default=os.path.join("..", "court-vision-public"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    main_dir = git(".", "rev-parse", "--show-toplevel").strip()
    wt = os.path.abspath(os.path.join(main_dir, a.worktree))
    if not os.path.isdir(wt):
        sys.exit("public worktree missing: " + wt)

    git(main_dir, "fetch", "origin", "master")
    if subprocess.run(["git", "merge-base", "--is-ancestor", "origin/master",
                       a.source], cwd=main_dir).returncode != 0:
        sys.exit("origin/master is not merged into %s -- run `git merge "
                 "origin/master` there first (never overwrite a direct push)"
                 % a.source)
    git(wt, "merge", "--ff-only", "origin/master")

    rules = load_allowlist()
    src = [p for p in git(main_dir, "ls-tree", "-r", "--name-only", "-z",
                          a.source).split(chr(0)) if p]
    keep = [p for p in src if is_public_path(p, rules)]
    have = [p for p in git(wt, "ls-files", "-z").split(chr(0)) if p]
    drop = sorted(set(have) - set(keep))
    print("source %s: %d paths, %d public; worktree has %d, dropping %d"
          % (a.source, len(src), len(keep), len(have), len(drop)))
    if a.dry_run:
        return
    nul = chr(0).encode("ascii")
    if drop:
        git(wt, "rm", "-q", "--pathspec-from-file=-", "--pathspec-file-nul",
            data=nul.join(p.encode("utf-8") for p in drop))
    git(wt, "checkout", a.source, "--pathspec-from-file=-", "--pathspec-file-nul",
        data=nul.join(p.encode("utf-8") for p in keep))
    if not git(wt, "status", "--porcelain").strip():
        print("public tree already matches; nothing to commit")
        return
    sha = git(main_dir, "rev-parse", "--short", a.source).strip()
    git(wt, "commit", "-q", "-m", "publish: sync the public tree from %s" % sha)
    print("committed in %s -- run the gates, then push public-master:master" % wt)


if __name__ == "__main__":
    main()
