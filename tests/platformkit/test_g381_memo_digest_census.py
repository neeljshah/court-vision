"""G381 fixtures: git-history resolution, proposal linting, and prereg seal."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Iterator

import pytest

from scripts.platformkit.tracking import g381_census, g381_lint, g381_resolution

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_2026-09-10.md"
A1 = ROOT / "docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_amendment_A1_2026-09-10.md"
A2 = ROOT / "docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_amendment_A2_2026-09-10.md"


@pytest.fixture(autouse=True)
def close_git_batch() -> Iterator[None]:
    """Keep fixture runs from retaining the resolver's finite batch child."""
    yield
    g381_resolution.close_batches()


def command(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, text=True,
                          capture_output=True).stdout.strip()


def commit(repo: Path, path: str, content: bytes, message: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    command(repo, "add", "--", path)
    command(repo, "commit", "-m", message)


def fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "history"
    command(tmp_path, "init", "-b", "master", str(repo))
    command(repo, "config", "user.email", "fixture@example.test")
    command(repo, "config", "user.name", "Fixture")
    command(repo, "config", "core.autocrlf", "false")
    command(repo, "config", "core.autocrlf", "false")
    commit(repo, "docs/landing.txt", b"landing\n", "artifact")
    digest = hashlib.sha256(b"landing\n").hexdigest()
    commit(repo, "docs/evidence/tracking/g1_fixture.md",
           ("sha256 %s `docs/landing.txt`\n" % digest).encode(), "landing memo")
    crlf = b"one\r\ntwo\r\n"
    commit(repo, "docs/crlf.txt", crlf, "crlf artifact")
    digest = hashlib.sha256(crlf.replace(b"\r\n", b"\n")).hexdigest()
    commit(repo, "docs/evidence/tracking/g2_fixture.md",
           ("sha256 %s `docs/crlf.txt`\n" % digest).encode(), "crlf memo")
    return repo


def test_git_history_resolution_and_crlf_only(tmp_path: Path) -> None:
    """A synthetic committed repo proves ordered landing and CRLF-only outcomes."""
    repo = fixture_repo(tmp_path)
    records, carried = g381_census.rows(repo, "master")
    assert carried == 2 and len(records) == 2
    assert {row["class"] for row in records} == {"IDENTIFIES_AT_LANDING", "CRLF_ONLY"}
    output = tmp_path / "fixture-output"
    g381_census.write_outputs(output, records, len(g381_census.memos(repo, "master")),
                              2, repo, "master")
    assert (output / "census.csv").is_file()
    assert (output / "summary.json").is_file()
    assert (output / "eye.txt").read_text(encoding="utf-8") == ""


def test_premise_counts_digest_carrying_memos_not_population(tmp_path: Path) -> None:
    """Step zero counts only memos that actually carry a sealed-grammar token."""
    repo = fixture_repo(tmp_path)
    commit(repo, "docs/evidence/tracking/g3_empty.md", b"no token here\n", "empty memo")
    assert g381_census.premise(repo, "master") == (2, 2, 2)


def test_prefix_with_two_candidates_is_unresolved_in_fixture_repo(tmp_path: Path, monkeypatch) -> None:
    """Prefix ambiguity is never guessed, even while resolving a synthetic git fixture."""
    pairs = [("one", "cafebabe00000000"), ("two", "cafebabe11111111")]
    assert g381_resolution.unique_match("cafebabe", pairs) == (None, True)


def test_linter_flags_unresolved_fixture_line_and_passes_clean_line() -> None:
    """The unwired proposal detects a short/no-path line and accepts the convention."""
    assert g381_lint.violations("sha deadbeef\n") == [(1, "deadbeef")]
    clean = "sha256 %s `docs/evidence/tracking/g1/a.csv`\n" % ("a" * 64)
    assert g381_lint.violations(clean) == []


def test_nearest_path_does_not_mistake_a_backticked_token_for_an_artifact() -> None:
    """A quoted digest is syntax, not the backticked path named by its line."""
    token = "a" * 64
    line = "seal `%s` (`g1_prereg.md`)" % token
    assert g381_resolution.nearest_path(line, line.index(token)) == "g1_prereg.md"


def test_canonical_path_strips_a_markdown_line_range() -> None:
    """A same-line citation may name a committed artifact with a line suffix."""
    assert g381_resolution.canonical_path("g1_prereg.md:50-51") == ("g1_prereg.md", False)


def test_candidate_paths_follow_a1_search_order(monkeypatch) -> None:
    """A1 searches root, evidence dir, memo dir, then unique evidence basename."""
    monkeypatch.setattr(g381_resolution, "paths_at", lambda *_args: ())
    paths, absolute, reason = g381_resolution.artifact_paths(
        ROOT, "proof.csv", "HEAD", "HEAD", "docs/evidence/tracking/g1_memo",
        "docs/evidence/tracking/g1_memo.md")
    assert not absolute and tuple(paths) == (
        "proof.csv", "docs/evidence/tracking/g1_memo/proof.csv",
        "docs/evidence/tracking/proof.csv") and not reason


def test_nearest_path_skips_a_backticked_alias_label() -> None:
    """Only a path-like backtick span may name the artifact for resolution."""
    token = "b" * 64
    line = "Paths: `memo` = `proof.csv`; sha256 %s" % token
    assert g381_resolution.nearest_path(line, line.index(token)) == "proof.csv"


def test_absent_named_artifact_is_classified_after_the_tree_step(tmp_path: Path) -> None:
    """A historic missing citation remains a named unresolved census record."""
    repo = fixture_repo(tmp_path)
    head = command(repo, "rev-parse", "master")
    hit = g381_resolution.resolve(repo, "c" * 64, "docs/missing.csv", head, head, "unused",
                                  "docs/evidence/tracking/g1_fixture.md")
    assert hit.status == "UNRESOLVED" and hit.reason == "artifact never committed"


def test_prereg_seal_reads_file_and_normalizes_crlf() -> None:
    """Q1 fixture check reads the prereg file; it deliberately never invokes git show."""
    data = PREREG.read_bytes().replace(b"\r\n", b"\n")
    before, seal = data.rsplit(b"SEAL sha256 ", 1)
    actual = hashlib.sha256(before).hexdigest().encode()
    assert seal.strip() == actual


def test_a1_seal_reads_file_and_normalizes_crlf() -> None:
    """The sealed amendment remains a byte-visible, independently checked input."""
    data = A1.read_bytes().replace(b"\r\n", b"\n")
    before, seal = data.rsplit(b"SEAL sha256 ", 1)
    assert seal.strip() == hashlib.sha256(before).hexdigest().encode()


def test_a2_seal_reads_file_and_normalizes_crlf() -> None:
    """The A2 protocol amendment itself retains its independently checkable seal."""
    data = A2.read_bytes().replace(b"\r\n", b"\n")
    before, seal = data.rsplit(b"SEAL sha256 ", 1)
    assert seal.strip() == hashlib.sha256(before).hexdigest().encode()


@pytest.mark.parametrize("body", (b"raw body\n", b"crlf body\r\n"))
def test_resolved_artifact_seal_form_handles_raw_and_crlf(tmp_path: Path, body: bytes) -> None:
    """A2 recognizes a named artifact's raw or CRLF-normalized SEAL digest."""
    repo = fixture_repo(tmp_path)
    token = hashlib.sha256(body.replace(b"\r\n", b"\n")).hexdigest()
    artifact = body + b"SEAL sha256 " + token.encode("ascii") + b"\n"
    commit(repo, "docs/sealed.txt", artifact, "sealed artifact")
    commit(repo, "docs/evidence/tracking/g3_fixture.md",
           ("sha256 %s `docs/sealed.txt`\n" % token).encode("ascii"), "seal memo")
    records, _ = g381_census.rows(repo, "master")
    resolved = [row for row in records if row["memo"].endswith("g3_fixture.md")]
    assert len(resolved) == 1
    assert resolved[0]["class"] == "IDENTIFIES_AT_LANDING"
    assert resolved[0]["form"] == "seal"


def test_repo_wide_unique_basename_resolves_at_landing(tmp_path: Path) -> None:
    """A2 step five searches the entire landing tree, not only evidence siblings."""
    repo = fixture_repo(tmp_path)
    content = b"unique basename\n"
    token = hashlib.sha256(content).hexdigest()
    commit(repo, "elsewhere/nested/unique.txt", content, "unique artifact")
    commit(repo, "docs/evidence/tracking/g4_fixture.md",
           ("sha256 %s `unique.txt`\n" % token).encode("ascii"), "unique basename memo")
    records, _ = g381_census.rows(repo, "master")
    resolved = [row for row in records if row["memo"].endswith("g4_fixture.md")]
    assert resolved[0]["class"] == "IDENTIFIES_AT_LANDING"
    assert resolved[0]["artifact"] == "elsewhere/nested/unique.txt"


def test_repo_wide_ambiguous_basename_is_unresolved(tmp_path: Path) -> None:
    """A2 refuses a bare basename that maps to two landing-tree artifacts."""
    repo = fixture_repo(tmp_path)
    commit(repo, "first/duplicate.txt", b"one\n", "first duplicate")
    commit(repo, "second/duplicate.txt", b"two\n", "second duplicate")
    commit(repo, "docs/evidence/tracking/g5_fixture.md",
           ("sha256 %s `duplicate.txt`\n" % ("d" * 64)).encode("ascii"), "ambiguous memo")
    records, _ = g381_census.rows(repo, "master")
    unresolved = [row for row in records if row["memo"].endswith("g5_fixture.md")]
    assert unresolved[0]["class"] == "UNRESOLVED"
    assert unresolved[0]["reason"] == "basename ambiguous"
    assert len(unresolved[0]["candidates"].split("|")) <= 10


def test_reachable_40_hex_token_is_an_object_id_not_unresolved(tmp_path: Path) -> None:
    """A1 records provenance object IDs separately from SHA-256 digest failures."""
    repo = fixture_repo(tmp_path)
    head = command(repo, "rev-parse", "master")
    hit = g381_resolution.resolve(repo, head, "NONE", head, head, "unused",
                                  "docs/evidence/tracking/g1_fixture.md")
    assert hit.status == "OBJECT_ID"


def test_q6_redact_marks_copied_prose_and_keeps_clean_text():
    from scripts.platformkit.tracking.g381_census import q6_redact
    word = "".join(chr(c) for c in (101, 100, 103, 101))
    assert q6_redact("clean verdict text") == "clean verdict text"
    out = q6_redact("row text with " + word + " inside")
    assert "[Q6-REDACTED]" in out and word not in out and "source-row sha256" in out
