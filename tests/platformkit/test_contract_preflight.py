"""Behavioral tests for the Q08 contract preflight linter -- one pass/fail pair per
check (9 pairs), plus a test that the scanner's own source passes check 1.

Banned-token fixtures are built by referencing g334_seal's canonical patterns and
contract_preflight's own exception constants, never by spelling a literal here.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.platformkit.tracking import contract_preflight as cp
from scripts.platformkit.tracking.g334_seal import BANNED_NUMBERS, BANNED_WORDS, BARE_INTEGER

ROOT = Path(__file__).resolve().parents[2]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)


def _init_repo(root: Path) -> None:
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "q08@example.invalid")
    _git(root, "config", "user.name", "Q08 test")


def _commit(root: Path, relpath: str, text: str) -> None:
    (root / relpath).write_text(text, encoding="utf-8", newline="\n")
    _git(root, "add", relpath)
    _git(root, "commit", "-q", "-m", "fixture: " + relpath)


# -- check 1: banned vocabulary + retracted figures ------------------------------

def test_vocab_pass(tmp_path: Path) -> None:
    path = tmp_path / "clean.md"
    path.write_text("nothing here but the field " + cp.EXC_FIELD +
                     " and the path " + cp.EXC_PATH + "\n", encoding="utf-8")
    ok, _detail, hits = cp.check_vocab([path])
    assert ok and hits == []


def test_vocab_fail(tmp_path: Path) -> None:
    path = tmp_path / "dirty.md"
    path.write_text("a claim used the word %s here\n" % BANNED_WORDS[0], encoding="utf-8")
    ok, _detail, hits = cp.check_vocab([path])
    assert not ok and hits


def test_vocab_pass_ignores_bare_figure_inside_hex_digest(tmp_path: Path) -> None:
    # A 64-char SHA-256 hex digest that happens to contain the bare two-digit figure
    # flanked by hex letters must not fire -- the G375/G381/G397/G408 false-positive class.
    digest = "a" * 20 + BARE_INTEGER + "b" * (64 - 20 - len(BARE_INTEGER))
    assert len(digest) == 64
    path = tmp_path / "hashes.md"
    path.write_text("SHA-256 %s artifact.csv\n" % digest, encoding="utf-8")
    ok, _detail, hits = cp.check_vocab([path])
    assert ok and hits == []


def test_scanner_source_passes_vocab_check() -> None:
    ok, detail, hits = cp.check_vocab([ROOT / "scripts/platformkit/tracking/contract_preflight.py"])
    assert ok, detail
    assert hits == []


# -- check 2: CRLF (index-side for tracked files; raw bytes only for untracked
#    files under core.autocrlf=false) ------------------------------------------------

def test_crlf_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "lf.txt", "line one\nline two\n")
    monkeypatch.chdir(repo)
    ok, _detail, bad = cp.check_crlf([Path("lf.txt")])
    assert ok and bad == []


def test_crlf_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "crlf.txt").write_bytes(b"line one\r\nline two\r\n")
    _git(repo, "add", "crlf.txt")
    _git(repo, "commit", "-q", "-m", "fixture: forced CRLF, index side")
    monkeypatch.chdir(repo)
    ok, _detail, bad = cp.check_crlf([Path("crlf.txt")])
    assert not ok and bad and bad[0]["reason"] == "index i/crlf"


def test_crlf_untracked_autocrlf_true_passes_with_note(tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(repo, "config", "core.autocrlf", "true")
    (repo / "untracked.txt").write_bytes(b"line one\r\nline two\r\n")
    monkeypatch.chdir(repo)
    ok, detail, bad = cp.check_crlf([Path("untracked.txt")])
    assert ok and bad == [] and "untracked" in detail


# -- check 3: LOC cap ----------------------------------------------------------------

def test_loc_pass(tmp_path: Path) -> None:
    path = tmp_path / "small.py"
    path.write_text("\n".join("x = %d" % i for i in range(10)) + "\n", encoding="utf-8")
    ok, _detail, over = cp.check_loc([path], [])
    assert ok and over == []


def test_loc_fail(tmp_path: Path) -> None:
    path = tmp_path / "big.py"
    path.write_text("\n".join("x = %d" % i for i in range(301)) + "\n", encoding="utf-8")
    ok, _detail, over = cp.check_loc([path], [])
    assert not ok and over
    exempt_ok, _detail2, exempt_over = cp.check_loc([path], ["*big.py"])
    assert exempt_ok and exempt_over == []


# -- check 4: additive schema vs master ---------------------------------------------

def test_schema_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "artifact.json", json.dumps({"a": 1, "b": 2}))
    (repo / "artifact.json").write_text(json.dumps({"a": 1, "b": 2, "c": 3}), encoding="utf-8")
    monkeypatch.chdir(repo)
    ok, _detail, problems = cp.check_schema([Path("artifact.json")], "master")
    assert ok and problems == []


def test_schema_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "artifact.json", json.dumps({"a": 1, "b": 2}))
    (repo / "artifact.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    monkeypatch.chdir(repo)
    ok, _detail, problems = cp.check_schema([Path("artifact.json")], "master")
    assert not ok and problems and problems[0]["removed"] == ["b"]


# -- check 5: head-slice census -------------------------------------------------------

def test_head_slice_pass(tmp_path: Path) -> None:
    path = tmp_path / "census.json"
    path.write_text(json.dumps({"eligible_frames": [1, 2, 3, 4], "sealed_frames": [2, 4]}),
                     encoding="utf-8")
    ok, _detail, hits = cp.check_head_slice([path])
    assert ok and hits == []


def test_head_slice_fail(tmp_path: Path) -> None:
    path = tmp_path / "census.json"
    path.write_text(json.dumps({"eligible_frames": [1, 2, 3, 4], "sealed_frames": [1, 2]}),
                     encoding="utf-8")
    ok, _detail, hits = cp.check_head_slice([path])
    assert not ok and hits


# -- check 6: spec threshold byte match ----------------------------------------------

def test_spec_threshold_pass(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text("ACCEPTANCE RULE: n >= 30 games per sport\n", encoding="utf-8")
    memo = tmp_path / "memo.md"
    memo.write_text("the corpus carried 30 games in this window\n", encoding="utf-8")
    ok, _detail, missing = cp.check_spec_threshold(spec, [memo])
    assert ok and missing == []


def test_spec_threshold_fail(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text("ACCEPTANCE RULE: n >= 30 games per sport\n", encoding="utf-8")
    memo = tmp_path / "memo.md"
    memo.write_text("the corpus carried games in this window\n", encoding="utf-8")
    ok, _detail, missing = cp.check_spec_threshold(spec, [memo])
    assert not ok and "30" in missing


# -- check 7: PROPOSED diff applies cleanly ------------------------------------------

def test_proposed_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "tracked.txt", "line one\n")
    diff = repo / "change.diff"
    diff.write_text(
        "--- a/tracked.txt\n+++ b/tracked.txt\n@@ -1 +1,2 @@\n line one\n+line two\n",
        encoding="utf-8", newline="\n")
    monkeypatch.chdir(repo)
    ok, _detail, code = cp.check_proposed(diff)
    assert ok and code == 0


def test_proposed_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "tracked.txt", "line one\n")
    diff = repo / "change.diff"
    diff.write_text(
        "--- a/tracked.txt\n+++ b/tracked.txt\n@@ -1 +1,2 @@\n line that does not exist\n+line two\n",
        encoding="utf-8", newline="\n")
    monkeypatch.chdir(repo)
    ok, _detail, code = cp.check_proposed(diff)
    assert not ok and code != 0


# -- one retracted-figure fixture, for good measure alongside the word fixture -------

def test_vocab_fail_on_retracted_figure(tmp_path: Path) -> None:
    path = tmp_path / "figure.csv"
    path.write_text("run,value\n1,%s\n" % BANNED_NUMBERS[0], encoding="utf-8")
    ok, _detail, hits = cp.check_vocab([path])
    assert not ok and hits


# -- check 8: removed/renamed artifact vs master (the G386 class) -------------------

def test_removed_artifact_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "docs" / "evidence").mkdir(parents=True)
    _init_repo(repo)
    _commit(repo, "docs/evidence/summary.json", json.dumps({"a": 1}))
    (repo / "docs/evidence/summary.json").write_text(json.dumps({"a": 1, "b": 2}), encoding="utf-8")
    _git(repo, "add", "docs/evidence/summary.json")
    _git(repo, "commit", "-q", "-m", "additive change only")
    monkeypatch.chdir(repo)
    ok, _detail, hits = cp.check_removed_artifact([Path("docs/evidence/summary.json")], "master~1")
    assert ok and hits == []


def test_removed_artifact_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "docs" / "evidence").mkdir(parents=True)
    _init_repo(repo)
    _commit(repo, "docs/evidence/old_receipt.csv", "a,b\n1,2\n")
    (repo / "docs/evidence/old_receipt.csv").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "delete the receipt without an alias")
    monkeypatch.chdir(repo)
    ok, _detail, hits = cp.check_removed_artifact([], "master~1")
    assert not ok and hits and hits[0]["status"].startswith("D")


# -- check 9: row duplication (the G372 class) ---------------------------------------

def test_row_duplication_pass(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    rows = [{"game_id": "g%d" % i, "value": i} for i in range(10)]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    ok, _detail, hits = cp.check_row_duplication([path])
    assert ok and hits == []


def test_row_duplication_fail_on_duplicate_rows(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    rows = [{"game_id": "g1", "value": 1}] * 9 + [{"game_id": "g2", "value": 2}]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    ok, _detail, hits = cp.check_row_duplication([path])
    assert not ok and hits


def test_row_duplication_fail_on_repeated_key_column(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    lines = ["game_id,value"] + ["g1,%d" % i for i in range(10)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, _detail, hits = cp.check_row_duplication([path])
    assert not ok and hits
