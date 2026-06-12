"""tests/kernel/test_no_sport_tokens.py — Sport-token grep guard for kernel/.

Asserts that NO file under kernel/ contains sport-specific tokens in
executable code (NAME, OP, NUMBER tokens).  Docstrings and comments are
explicitly excluded because the kernel's own docstrings legitimately use NBA
examples (e.g. ``fg3m`` in kernel/config/stats.py's loop_targets docstring,
``NYK`` in kernel/config/entities.py's resolve_team docstring).

Guard mechanism
---------------
Uses ``tokenize`` to walk each .py file token-by-token.  Only tokens of
type ``NAME``, ``OP``, or ``NUMBER`` are inspected — ``STRING`` tokens
(which include docstrings) and ``COMMENT`` tokens are skipped entirely.

Whitelist mechanism
-------------------
Any source line that ends with a trailing comment matching
``# legacy-literal: CV_CFG_<something>`` is exempt from the guard.  This
supports the Phase 2 dual-path literals where a hardcoded sport token must
temporarily live in kernel/ code until the adapter migration is complete.
"""
from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path
from typing import List, NamedTuple

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Regex that matches sport-specific tokens forbidden in kernel CODE.
_SPORT_TOKEN_RE = re.compile(
    r"\b(nba_api|NYK|fg3m|EVENTMSGTYPE|PlayByPlayV2|0022\d)\b"
)

#: A trailing comment on the *source line* that whitelists the token.
#: Pattern: ``# legacy-literal: CV_CFG_<LABEL>``
_WHITELIST_TAG_RE = re.compile(r"#\s*legacy-literal:\s*CV_CFG_\w+")

#: Root of the kernel package, resolved relative to this test file.
_KERNEL_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent / "kernel"
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class Violation(NamedTuple):
    """A single forbidden sport-token found in kernel code."""

    path: Path
    lineno: int
    col: int
    token_string: str


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------

def _is_whitelisted_line(source_line: str) -> bool:
    """Return True if *source_line* carries a legacy-literal whitelist tag."""
    return bool(_WHITELIST_TAG_RE.search(source_line))


def _scan_file(path: Path) -> List[Violation]:
    """Scan *path* for forbidden sport tokens outside docstrings/comments.

    Returns a (possibly empty) list of :class:`Violation` instances.
    """
    source = path.read_text(encoding="utf-8", errors="replace")
    source_lines = source.splitlines()

    violations: List[Violation] = []

    try:
        tokens = list(
            tokenize.generate_tokens(io.StringIO(source).readline)
        )
    except tokenize.TokenError:
        # Unparseable file — skip gracefully; syntax tests catch this.
        return violations

    for tok in tokens:
        tok_type = tok.type
        tok_string = tok.string
        tok_lineno = tok.start[0]  # 1-indexed
        tok_col = tok.start[1]

        # Only inspect executable tokens; skip strings (incl. docstrings)
        # and comments.
        if tok_type in (tokenize.STRING, tokenize.COMMENT, tokenize.NEWLINE,
                        tokenize.NL, tokenize.INDENT, tokenize.DEDENT,
                        tokenize.ENCODING, tokenize.ENDMARKER):
            continue

        # Check whether the token string itself matches.
        if not _SPORT_TOKEN_RE.search(tok_string):
            continue

        # The token is a potential violation — check the whitelist tag.
        # source_lines is 0-indexed; tok_lineno is 1-indexed.
        raw_line = source_lines[tok_lineno - 1] if tok_lineno <= len(source_lines) else ""
        if _is_whitelisted_line(raw_line):
            continue

        violations.append(
            Violation(
                path=path,
                lineno=tok_lineno,
                col=tok_col,
                token_string=tok_string,
            )
        )

    return violations


def collect_kernel_violations() -> List[Violation]:
    """Walk all .py files under kernel/ and collect violations."""
    all_violations: List[Violation] = []
    for py_file in sorted(_KERNEL_ROOT.rglob("*.py")):
        all_violations.extend(_scan_file(py_file))
    return all_violations


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNoSportTokens:
    """Guard: kernel/ code must be sport-blind."""

    def test_kernel_tree_is_clean(self) -> None:
        """Assert zero sport-token violations in the live kernel/ tree.

        This test intentionally exercises the docstring-exclusion path:
        kernel/config/stats.py contains ``fg3m`` only inside a docstring
        (``loop_targets`` returns doc and ``SportStatRegistry`` class doc),
        and kernel/config/entities.py contains ``NYK`` only inside docstrings.
        Both files must pass cleanly here.
        """
        violations = collect_kernel_violations()
        if violations:
            lines = [
                f"  {v.path.relative_to(_KERNEL_ROOT)}:{v.lineno}:{v.col}  {v.token_string!r}"
                for v in violations
            ]
            detail = "\n".join(lines)
            pytest.fail(
                f"Found {len(violations)} sport-token violation(s) in kernel/ code "
                f"(docstrings/comments excluded):\n{detail}"
            )

    def test_docstring_tokens_are_not_flagged(self) -> None:
        """Specifically verify that stats.py and entities.py are not flagged.

        These two files are known to contain NBA examples (fg3m, NYK) inside
        their docstrings.  The tokenize-based guard must pass them cleanly.
        """
        stats_py = _KERNEL_ROOT / "config" / "stats.py"
        entities_py = _KERNEL_ROOT / "config" / "entities.py"

        for path in (stats_py, entities_py):
            assert path.exists(), f"Expected kernel file missing: {path}"
            violations = _scan_file(path)
            assert violations == [], (
                f"{path.name} should have zero code violations "
                f"(all tokens are in docstrings); got: {violations}"
            )

    def test_planted_bare_token_is_caught(self, tmp_path: Path) -> None:
        """Negative test: a sport token in executable code must be detected.

        We write a temp .py file with a bare ``fg3m`` token as a variable
        name (not inside a string or comment), scan it directly, and assert
        the guard catches it.  The file is created under tmp_path (outside
        kernel/) so no stray file is left in kernel/ afterward.
        """
        fake_kernel_file = tmp_path / "fake_kernel_module.py"
        fake_kernel_file.write_text(
            'from __future__ import annotations\n\nfg3m = 0\n',
            encoding="utf-8",
        )

        violations = _scan_file(fake_kernel_file)
        assert len(violations) >= 1, (
            "Expected the scanner to catch 'fg3m' as a bare NAME token "
            "in executable code, but got zero violations."
        )
        assert any(v.token_string == "fg3m" for v in violations), (
            f"Expected a violation with token_string='fg3m'; got: {violations}"
        )

    def test_planted_nba_api_token_is_caught(self, tmp_path: Path) -> None:
        """Negative test: ``nba_api`` import token must be detected."""
        fake_file = tmp_path / "fake_nba_import.py"
        fake_file.write_text(
            "import nba_api\n",
            encoding="utf-8",
        )

        violations = _scan_file(fake_file)
        assert any(v.token_string == "nba_api" for v in violations), (
            f"Expected 'nba_api' violation; got: {violations}"
        )

    def test_whitelist_tag_exempts_token(self, tmp_path: Path) -> None:
        """A line tagged ``# legacy-literal: CV_CFG_STATS`` must be allowed.

        This validates the whitelist mechanism even though no such lines
        exist yet in the current kernel tree.  A synthetic file is used so
        the kernel/ tree is never touched.
        """
        tagged_file = tmp_path / "fake_dual_path.py"
        tagged_file.write_text(
            'from __future__ import annotations\n\n'
            'NYK = "some-legacy-constant"  # legacy-literal: CV_CFG_STATS\n'
            'other_var = 1\n',
            encoding="utf-8",
        )

        violations = _scan_file(tagged_file)
        assert violations == [], (
            f"A line tagged with '# legacy-literal: CV_CFG_STATS' should be "
            f"exempt from the guard; got violations: {violations}"
        )

    def test_whitelist_requires_correct_prefix(self, tmp_path: Path) -> None:
        """A partial or misspelled tag must NOT exempt the token."""
        bad_tag_file = tmp_path / "fake_bad_tag.py"
        bad_tag_file.write_text(
            'from __future__ import annotations\n\n'
            'NYK = "bad"  # legacy-literal: WRONG_PREFIX\n',
            encoding="utf-8",
        )

        violations = _scan_file(bad_tag_file)
        assert any(v.token_string == "NYK" for v in violations), (
            "A misspelled whitelist tag should NOT exempt the token; "
            f"got violations: {violations}"
        )

    def test_no_stray_files_in_kernel(self) -> None:
        """Confirm that no test-generated stray files exist under kernel/."""
        stray = list(_KERNEL_ROOT.rglob("fake_*.py"))
        assert stray == [], (
            f"Stray file(s) found under kernel/ after tests: {stray}"
        )
