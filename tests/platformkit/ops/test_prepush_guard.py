"""S28 -- CONSTRUCT test for the pre-push guard (n = 5 enumerated cases).

Each case builds a throwaway git repo with a bare remote, plants one commit,
and drives scripts/hooks/prepush_guard.py with a faked pre-push stdin line.
Cases: (1) data/ touched, (2) vault/ touched, (3) credential literal added,
(4) clean docs commit, (5) non-fast-forward ref update.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / "scripts" / "hooks" / "prepush_guard.py"
REF = "refs/heads/master"
# Split so this test file itself does not match the guard's own pattern.
PLANTED = "API" + '_KEY = "abcdefghijklmnopqrstuvwxyz1234"'


def _git(cwd, *args):
    p = subprocess.run(["git"] + list(args), cwd=str(cwd),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "replace").strip()
    assert p.returncode == 0, "git %s failed: %s" % (" ".join(args), out)
    return out


def _commit(work, relpath, content, msg):
    path = work / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(work, "add", "--", relpath)
    _git(work, "commit", "-m", msg)
    return _git(work, "rev-parse", "HEAD")


def _setup(tmp_path):
    """A work repo with one clean commit already on the bare remote."""
    bare = tmp_path / "remote.git"
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], cwd=str(tmp_path),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True)
    _git(work, "init", "-b", "master")
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    _git(work, "config", "commit.gpgsign", "false")
    _git(work, "remote", "add", "origin", str(bare))
    base = _commit(work, "docs/base.md", "base\n", "base")
    _git(work, "push", "origin", "master")
    return work, base


PUBLIC_URL = "https://github.com/neeljshah/court-vision.git"
PRIVATE_URL = "https://github.com/neeljshah/court-vision-private.git"


def _run(work, local_sha, remote_sha, url=None):
    line = "%s %s %s %s\n" % (REF, local_sha, REF, remote_sha)
    argv = [sys.executable, str(GUARD)] + (["origin", url] if url else [])
    return subprocess.run(argv, cwd=str(work),
                          input=line.encode("ascii"),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _err(proc):
    return proc.stderr.decode("utf-8", "replace")


def test_case1_data_tree_refused(tmp_path):
    work, base = _setup(tmp_path)
    sha = _commit(work, "data/x.txt", "rows\n", "add data")
    p = _run(work, sha, base)
    assert p.returncode == 1, _err(p)
    assert "data/x.txt" in _err(p) and "private tree" in _err(p)


def test_case2_vault_tree_refused(tmp_path):
    work, base = _setup(tmp_path)
    sha = _commit(work, "vault/y.md", "note\n", "add vault note")
    p = _run(work, sha, base)
    assert p.returncode == 1, _err(p)
    assert "vault/y.md" in _err(p) and "private tree" in _err(p)


def test_case3_credential_literal_refused(tmp_path):
    work, base = _setup(tmp_path)
    sha = _commit(work, "scripts/conf.py", PLANTED + "\n", "add config")
    p = _run(work, sha, base)
    assert p.returncode == 1, _err(p)
    assert "credential" in _err(p) and "scripts/conf.py" in _err(p)
    # the guard names the pattern, it must not echo the value
    assert "abcdefghijklmnopqrstuvwxyz1234" not in _err(p)


def test_case4_clean_docs_commit_allowed(tmp_path):
    work, base = _setup(tmp_path)
    sha = _commit(work, "docs/ok.md", "clean note\n", "docs update")
    p = _run(work, sha, base)
    assert p.returncode == 0, _err(p)
    assert "1 commits scanned, clean" in _err(p)


def test_case5_non_fast_forward_refused(tmp_path):
    work, base = _setup(tmp_path)
    remote_sha = _commit(work, "docs/a.md", "a\n", "commit a")
    _git(work, "push", "origin", "master")
    _git(work, "reset", "--hard", base)
    local_sha = _commit(work, "docs/b.md", "b\n", "commit b")
    p = _run(work, local_sha, remote_sha)
    assert p.returncode == 1, _err(p)
    assert "non-fast-forward" in _err(p) and REF in _err(p)


# Cases 6-9: the PUBLIC remote only accepts a tip tree inside the allowlist
# (scripts/hooks/public_allowlist.txt); the private remote is unaffected.

def test_case6_engine_path_refused_on_the_public_remote(tmp_path):
    work, base = _setup(tmp_path)
    sha = _commit(work, "src/sim/engine.py", "x = 1\n", "engine code")
    p = _run(work, sha, base, url=PUBLIC_URL)
    assert p.returncode == 1, _err(p)
    assert "src/sim/engine.py" in _err(p) and "PUBLIC" in _err(p)


def test_case7_same_push_allowed_on_the_private_remote(tmp_path):
    work, base = _setup(tmp_path)
    sha = _commit(work, "src/sim/engine.py", "x = 1\n", "engine code")
    p = _run(work, sha, base, url=PRIVATE_URL)
    assert p.returncode == 0, _err(p)


def test_case8_public_tip_is_checked_as_a_tree_not_as_a_diff(tmp_path):
    # the engine file arrived in an EARLIER commit; a later docs-only commit is
    # still refused because the tip tree holds the engine path.
    work, base = _setup(tmp_path)
    mid = _commit(work, "api/main.py", "y = 2\n", "api code")
    _git(work, "push", "origin", "master")
    tip = _commit(work, "docs/ok.md", "clean\n", "docs only")
    p = _run(work, tip, mid, url=PUBLIC_URL)
    assert p.returncode == 1, _err(p)
    assert "api/main.py" in _err(p)


def test_case10_deleting_a_private_path_is_allowed(tmp_path):
    # a private file that reached the remote long ago must be removable: the
    # deletion cannot leak content, while re-adding or editing it is refused.
    work, base = _setup(tmp_path)
    _git(work, "config", "core.hooksPath", str(tmp_path / "nohooks"))
    added = _commit(work, "data/old.txt", "rows\n", "historic leak")
    _git(work, "push", "origin", "master")
    _git(work, "rm", "-q", "data/old.txt")
    _git(work, "commit", "-m", "remove it")
    tip = _git(work, "rev-parse", "HEAD")
    p = _run(work, tip, added, url=PUBLIC_URL)
    assert p.returncode == 0, _err(p)


def test_case9_allowlisted_tree_passes_on_the_public_remote(tmp_path):
    work, base = _setup(tmp_path)
    _commit(work, "docs/evidence/tracking/g1/memo.md", "memo\n", "memo")
    sha = _commit(work, "kernel/validation/m.py", "z = 3\n", "kernel sample")
    p = _run(work, sha, base, url=PUBLIC_URL)
    assert p.returncode == 0, _err(p)
