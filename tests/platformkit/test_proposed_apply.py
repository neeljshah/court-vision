"""Behavioral tests for the Q09 proposed_apply module: extract_diff, never_list_scan,
check() against a throwaway repo, and apply_on_branch + rollback byte-exactness.

Mirrors test_contract_preflight.py's throwaway-repo helpers.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.platformkit.tracking import contract_preflight as cp
from scripts.platformkit.tracking import proposed_apply as pa

ROOT = Path(__file__).resolve().parents[2]

SAMPLE_DIFF = (
    "--- a/sample.txt\n+++ b/sample.txt\n@@ -1 +1,2 @@\n line one\n+line two\n"
)
STALE_DIFF = (
    "--- a/sample.txt\n+++ b/sample.txt\n@@ -1 +1,2 @@\n line that does not exist\n+line two\n"
)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)


def _init_repo(root: Path) -> None:
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "q09@example.invalid")
    _git(root, "config", "user.name", "Q09 test")


def _commit(root: Path, relpath: str, text: str) -> None:
    (root / relpath).write_text(text, encoding="utf-8", newline="\n")
    _git(root, "add", relpath)
    _git(root, "commit", "-q", "-m", "fixture: " + relpath)


# -- extract_diff: picks the fenced block that is actually a diff -------------------

def test_extract_diff_picks_the_diff_block_among_two_fences() -> None:
    md = (
        "# a proposal\n\n"
        "some prose, then a code sample:\n\n"
        "```python\nprint('not a diff')\n```\n\n"
        "and the real patch:\n\n"
        "```diff\n" + SAMPLE_DIFF + "```\n"
    )
    diff = pa.extract_diff(md)
    assert diff.startswith("--- a/sample.txt")
    assert "+line two" in diff


def test_extract_diff_trims_leading_comments_on_a_raw_diff_file() -> None:
    # The real G412/G416 files on disk: no fences, a couple of leading "# ..." lines.
    raw = "# G412 PROPOSED additive receipt. APPLIED NOWHERE.\n\n" + SAMPLE_DIFF
    diff = pa.extract_diff(raw)
    assert diff.startswith("--- a/sample.txt")


def test_extract_diff_raises_when_nothing_looks_like_a_diff() -> None:
    with pytest.raises(ValueError):
        pa.extract_diff("just prose, no fences, no diff markers\n")


# -- never_list_scan: registry write and flag-flip heuristics -----------------------

def test_never_list_scan_fails_on_registry_write_line() -> None:
    diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1,2 @@\n old\n+open('data/registry/out.parquet', 'w')\n"
    result = pa.never_list_scan(diff)
    assert not result["ok"]
    assert any(v["kind"] == "registry_write" for v in result["violations"])


def test_never_list_scan_fails_on_flag_flip_line() -> None:
    diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1,2 @@\n old\n+ENABLE_LIVE_WRITES = True\n"
    result = pa.never_list_scan(diff)
    assert not result["ok"]
    assert any(v["kind"] == "flag_flip" for v in result["violations"])


def test_never_list_scan_passes_clean_diff() -> None:
    result = pa.never_list_scan(SAMPLE_DIFF)
    assert result["ok"] and result["violations"] == []


# -- check(): git apply --check against a throwaway repo (cwd) ----------------------

def test_check_applies_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "sample.txt", "line one\n")
    monkeypatch.chdir(repo)
    result = pa.check(SAMPLE_DIFF)
    assert result["applies_cleanly"] and result["stderr"] == ""


def test_check_fails_on_stale_diff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "sample.txt", "line one\n")
    monkeypatch.chdir(repo)
    result = pa.check(STALE_DIFF)
    assert not result["applies_cleanly"] and result["stderr"]


# -- target_paths / gated_paths -------------------------------------------------------

def test_target_paths_counts_hunks_and_pre_digest(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "sample.txt", "line one\n")
    monkeypatch.chdir(repo)
    entries = pa.target_paths(SAMPLE_DIFF)
    assert entries == [{"path": "sample.txt", "hunks": 1,
                         "pre_sha256": pa._sha256_of(Path("sample.txt"))}]


def test_gated_paths_flags_src_and_leaves_others() -> None:
    assert pa.gated_paths(["src/tracking/advanced_tracker.py", "scripts/platformkit/x.py"]) == [
        "src/tracking/advanced_tracker.py"]


# -- apply_on_branch + rollback: byte-exact restore ----------------------------------

def test_apply_on_branch_records_digests_and_rollback_is_byte_exact(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(repo, "config", "core.autocrlf", "false")  # keep raw bytes stable for the byte check below
    _commit(repo, "sample.txt", "line one\n")
    monkeypatch.chdir(repo)
    original = (repo / "sample.txt").read_bytes()

    result = pa.apply_on_branch(SAMPLE_DIFF, "lane-test", test_files=[])
    assert result["applied"], result
    assert (repo / "sample.txt").read_bytes() != original
    assert result["post_digests"]["sample.txt"] is not None

    outcome = pa.rollback(Path(result["rollback_file"]))
    assert outcome["ok"]
    assert (repo / "sample.txt").read_bytes() == original


def test_apply_on_branch_refuses_gated_path_without_allow_gated(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    _init_repo(repo)
    _commit(repo, "src/x.py", "line one\n")
    monkeypatch.chdir(repo)
    diff = "--- a/src/x.py\n+++ b/src/x.py\n@@ -1 +1,2 @@\n line one\n+line two\n"
    result = pa.apply_on_branch(diff, "lane-gated", test_files=[])
    assert not result["applied"]
    assert result["gated_paths"] == ["src/x.py"]


# -- this module's own source carries none of the four banned words -----------------

def test_module_source_has_no_banned_words() -> None:
    ok, detail, hits = cp.check_vocab([ROOT / "scripts/platformkit/tracking/proposed_apply.py"])
    assert ok, detail
    assert hits == []
