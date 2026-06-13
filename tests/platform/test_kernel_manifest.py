"""tests/platform/test_kernel_manifest.py — unit tests for kernel_manifest.py.

Tests the freeze/check/delta logic on synthetic file sets plus a smoke test
against the real §4.1 kernel file list.

Run with:
    python -m pytest tests/platform/test_kernel_manifest.py -q --timeout=120

No network calls, no torch, no FastAPI imports.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
import importlib, sys, os

# Ensure the repo root is on sys.path so the import resolves.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.proof_tennis.kernel_manifest import (  # noqa: E402
    KERNEL_FILES,
    _FLAGLINE_FILE,
    _ALLOWED_FLAG_NAME,
    check_manifest,
    compute_manifest,
    main as km_main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 1. compute_manifest — basic freeze on synthetic files
# ---------------------------------------------------------------------------

class TestComputeManifest:
    def test_returns_dict_with_all_files(self, tmp_path: Path) -> None:
        """compute_manifest returns one entry per file with correct sha256."""
        files = ["a.py", "b.py", "c.py"]
        contents = ["alpha", "beta", "gamma"]
        for rel, text in zip(files, contents):
            _write(tmp_path / rel, text)

        result = compute_manifest(files, repo_root=tmp_path)

        assert set(result.keys()) == set(files)
        for rel, text in zip(files, contents):
            expected = hashlib.sha256(text.encode()).hexdigest()
            assert result[rel] == expected, f"hash mismatch for {rel}"

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        """Missing file raises FileNotFoundError (manifest list drift)."""
        _write(tmp_path / "exists.py", "content")
        with pytest.raises(FileNotFoundError, match="MISSING"):
            compute_manifest(["exists.py", "ghost.py"], repo_root=tmp_path)

    def test_empty_file_list(self, tmp_path: Path) -> None:
        """Empty file list returns empty dict."""
        result = compute_manifest([], repo_root=tmp_path)
        assert result == {}


# ---------------------------------------------------------------------------
# 2. check_manifest — violation detection
# ---------------------------------------------------------------------------

class TestCheckManifest:
    def test_clean_returns_empty(self) -> None:
        """Identical frozen/current → no violations."""
        frozen = {"a.py": "aaa", "b.py": "bbb"}
        current = {"a.py": "aaa", "b.py": "bbb"}
        assert check_manifest(frozen, current) == []

    def test_changed_file_flagged(self) -> None:
        """Changed hash → that file is in violations."""
        frozen = {"a.py": "aaa", "b.py": "bbb"}
        current = {"a.py": "aaa", "b.py": "CHANGED"}
        violations = check_manifest(frozen, current)
        assert "b.py" in violations
        assert "a.py" not in violations

    def test_multiple_changes(self) -> None:
        """Multiple changed files → all appear in violations."""
        frozen = {"a.py": "x", "b.py": "y", "c.py": "z"}
        current = {"a.py": "X", "b.py": "Y", "c.py": "z"}
        violations = check_manifest(frozen, current)
        assert set(violations) == {"a.py", "b.py"}

    def test_key_missing_from_current(self) -> None:
        """File present in frozen but absent from current → violation."""
        frozen = {"a.py": "aaa", "b.py": "bbb"}
        current = {"a.py": "aaa"}
        violations = check_manifest(frozen, current)
        assert "b.py" in violations

    def test_extra_key_in_current(self) -> None:
        """File absent from frozen but present in current → violation."""
        frozen = {"a.py": "aaa"}
        current = {"a.py": "aaa", "new.py": "nnn"}
        violations = check_manifest(frozen, current)
        assert "new.py" in violations


# ---------------------------------------------------------------------------
# 3. Freeze → check round-trip (CLI via main())
# ---------------------------------------------------------------------------

class TestFreezeThenCheck:
    """Freeze/check round-trip using compute_manifest + check_manifest directly
    on synthetic file sets (avoids km_main which uses the real KERNEL_FILES)."""

    def test_freeze_then_check_clean(self, tmp_path: Path) -> None:
        """Freeze then immediately check = 0 violations."""
        files = ["x/gate.py", "x/signal.py", "x/ledger.py"]
        for f in files:
            _write(tmp_path / f, "# content of " + f)

        manifest_path = tmp_path / "manifest.sha256"
        frozen = compute_manifest(files, repo_root=tmp_path)
        manifest_path.write_text(json.dumps(frozen, indent=2), encoding="utf-8")

        current = compute_manifest(files, repo_root=tmp_path)
        violations = check_manifest(frozen, current)
        assert violations == []

    def test_check_detects_mutation(self, tmp_path: Path) -> None:
        """Mutating a file after freeze → check returns it as a violation."""
        files = ["a.py", "b.py"]
        for f in files:
            _write(tmp_path / f, "original")

        frozen = compute_manifest(files, repo_root=tmp_path)

        # Mutate one file.
        (tmp_path / "a.py").write_text("mutated", encoding="utf-8")

        current = compute_manifest(files, repo_root=tmp_path)
        violations = check_manifest(frozen, current)
        assert "a.py" in violations
        assert "b.py" not in violations

    def test_check_missing_manifest_exits_1(self, tmp_path: Path) -> None:
        """km_main --check with a nonexistent manifest file exits 1."""
        rc = km_main([
            "--check",
            "--manifest", str(tmp_path / "nonexistent.sha256"),
        ])
        assert rc == 1


# ---------------------------------------------------------------------------
# 4. Allowed-flagline delta logic (unit-level, no real flags.py needed)
# ---------------------------------------------------------------------------

class TestAllowedFlaglineDelta:
    """Test _is_flagline_delta_allowed via the check_manifest + main() path."""

    def _make_flags_content(self, include_cv_domain: bool) -> str:
        """Build a minimal synthetic flags.py-like content."""
        base = (
            'from __future__ import annotations\n'
            'FLAGS = {\n'
            '    "CV_EXISTING_FLAG": {\n'
            '        "default": False,\n'
            '    },\n'
        )
        if include_cv_domain:
            base += (
                f'    "{_ALLOWED_FLAG_NAME}": {{\n'
                '        "default": False,\n'
                '        "desc": "Tennis domain flag.",\n'
                '    },\n'
            )
        base += '}\n'
        return base

    def test_flagline_delta_allowed_with_flag(self, tmp_path: Path) -> None:
        """Adding only CV_DOMAIN_TENNIS block to flags.py passes when --allow-flagline."""
        from scripts.platformkit.proof_tennis.kernel_manifest import (
            _is_flagline_delta_allowed,
            _sha256_file,
        )

        flags_file = tmp_path / _FLAGLINE_FILE
        # Write the "before" version and capture its on-disk hash.
        _write(flags_file, self._make_flags_content(include_cv_domain=False))
        frozen_hash = _sha256_file(flags_file)

        # Now write the version WITH the flag.
        _write(flags_file, self._make_flags_content(include_cv_domain=True))

        result = _is_flagline_delta_allowed(frozen_hash, _FLAGLINE_FILE, tmp_path)
        assert result is True, "Expected allowed when only CV_DOMAIN_TENNIS was added"

    def test_flagline_delta_rejected_for_other_change(self, tmp_path: Path) -> None:
        """Changing a different line in flags.py is NOT allowed even with --allow-flagline."""
        from scripts.platformkit.proof_tennis.kernel_manifest import (
            _is_flagline_delta_allowed,
            _sha256_file,
        )

        original = self._make_flags_content(include_cv_domain=False)
        flags_file = tmp_path / _FLAGLINE_FILE
        _write(flags_file, original)
        frozen_hash = _sha256_file(flags_file)

        # Mutate an existing flag (not an addition of CV_DOMAIN_TENNIS).
        mutated = original.replace('"default": False', '"default": True')
        _write(flags_file, mutated)

        result = _is_flagline_delta_allowed(frozen_hash, _FLAGLINE_FILE, tmp_path)
        assert result is False, "Non-flagline delta must not be allowed"

    def test_identical_content_returns_true(self, tmp_path: Path) -> None:
        """If file is byte-identical the function returns True (trivially allowed)."""
        from scripts.platformkit.proof_tennis.kernel_manifest import (
            _is_flagline_delta_allowed,
            _sha256_file,
        )

        content = self._make_flags_content(include_cv_domain=False)
        flags_file = tmp_path / _FLAGLINE_FILE
        _write(flags_file, content)
        frozen_hash = _sha256_file(flags_file)

        result = _is_flagline_delta_allowed(frozen_hash, _FLAGLINE_FILE, tmp_path)
        assert result is True


# ---------------------------------------------------------------------------
# 5. Smoke test — real §4.1 file list (compute_manifest on real tree)
# ---------------------------------------------------------------------------

class TestRealKernelManifest:
    def test_compute_manifest_real_tree(self) -> None:
        """compute_manifest on the real §4.1 file list returns a dict with
        all present files; absent files are xfailed with a recorded note.
        """
        missing: list[str] = []
        present: list[str] = []
        for rel in KERNEL_FILES:
            path = _REPO_ROOT / Path(rel)
            if path.exists():
                present.append(rel)
            else:
                missing.append(rel)

        if missing:
            # Record which files are missing — this is the documented-gap note.
            notes = "\n".join(f"  ABSENT: {f}" for f in missing)
            pytest.xfail(
                f"Smoke test: {len(missing)} §4.1 file(s) absent from tree "
                f"(manifest list drift — update KERNEL_FILES or create the file):\n{notes}"
            )

        result = compute_manifest(present, repo_root=_REPO_ROOT)
        assert len(result) == len(present)
        for rel in present:
            assert rel in result
            assert len(result[rel]) == 64, f"expected sha256 hex for {rel}"

    def test_all_kernel_files_are_strings(self) -> None:
        """KERNEL_FILES constant is a list of non-empty strings."""
        assert isinstance(KERNEL_FILES, list)
        assert len(KERNEL_FILES) > 0
        for item in KERNEL_FILES:
            assert isinstance(item, str) and len(item) > 0
