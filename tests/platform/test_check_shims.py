"""test_check_shims.py — Acceptance tests for scripts/platformkit/check_shims.py.

Test matrix
-----------
1.  discover_shims: em-dash/en-dash/hyphen SHIM marker on line 1 detected.
2.  discover_shims: marker on line 2, or missing entirely, NOT detected.
3.  check_shim: valid Form-B shim (__all__ matches actual symbols) → ok=True.
4.  check_shim: broken Form-B shim (__all__ names ghost symbol) → ok=False.
5.  check_shim: inert shim (no import-as, no __all__) → ok=True.
6.  check_shim: unreadable path → ok=False.
7.  check_all: empty/no-shim dir → [].
8.  check_pickles: valid .pkl dict → ok=True.
9.  check_pickles: corrupt .pkl → ok=False.
10. check_pickles: PICKLE_SKIP match → skipped=True, ok=True.
11. check_pickles: empty dir → [].
12. report_unused: log with shim import → hit returned with line number.
13. report_unused: clean log / empty list → [].
14. ShimResult / PickleResult __str__ format.

All fixtures in tmp_path — never touch real data/models. No torch.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platformkit"))

from check_shims import (  # noqa: E402
    ShimResult, PickleResult,
    check_shim, check_all, check_pickles, discover_shims, report_unused,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _w(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def _pkl(tmp_path: Path, name: str, obj) -> Path:
    p = tmp_path / name
    with p.open("wb") as fh:
        pickle.dump(obj, fh)
    return p


def _bad_pkl(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x00\xFF not valid pickle")
    return p


# ---------------------------------------------------------------------------
# 1-2. discover_shims
# ---------------------------------------------------------------------------

class TestDiscoverShims:
    def test_em_dash_detected(self, tmp_path: Path) -> None:
        s = _w(tmp_path, "s.py", "# — SHIM\npass\n")
        assert s in discover_shims(tmp_path)

    def test_hyphen_detected(self, tmp_path: Path) -> None:
        s = _w(tmp_path, "s2.py", "# - SHIM\npass\n")
        assert s in discover_shims(tmp_path)

    def test_en_dash_detected(self, tmp_path: Path) -> None:
        s = _w(tmp_path, "s3.py", "# – SHIM\npass\n")
        assert s in discover_shims(tmp_path)

    def test_no_marker_not_detected(self, tmp_path: Path) -> None:
        _w(tmp_path, "plain.py", "def f(): pass\n")
        assert discover_shims(tmp_path) == []

    def test_marker_on_line2_not_detected(self, tmp_path: Path) -> None:
        _w(tmp_path, "late.py", '"""Doc."""\n# — SHIM\npass\n')
        assert discover_shims(tmp_path) == []

    def test_mixed_returns_only_marked(self, tmp_path: Path) -> None:
        s1 = _w(tmp_path, "a.py", "# — SHIM\npass\n")
        s2 = _w(tmp_path, "b.py", "# - SHIM\npass\n")
        _w(tmp_path, "c.py", "x = 1\n")
        found = discover_shims(tmp_path)
        assert s1 in found and s2 in found and len(found) == 2


# ---------------------------------------------------------------------------
# 3-6. check_shim
# ---------------------------------------------------------------------------

class TestCheckShim:
    def test_form_b_valid(self, tmp_path: Path) -> None:
        shim = _w(tmp_path, "fb.py", """\
# — SHIM
__all__ = ["alpha", "beta"]

def alpha(): return 1
def beta(): return 2
""")
        r = check_shim(shim)
        assert r.ok, f"Expected ok=True: {r}"

    def test_form_b_broken_ghost_symbol(self, tmp_path: Path) -> None:
        shim = _w(tmp_path, "fb_bad.py", """\
# — SHIM
__all__ = ["alpha", "ghost"]

def alpha(): return 1
# ghost never defined
""")
        r = check_shim(shim)
        assert not r.ok, f"Expected ok=False (ghost in __all__): {r}"
        assert "ghost" in r.message

    def test_inert_shim_passes(self, tmp_path: Path) -> None:
        shim = _w(tmp_path, "inert.py", """\
# — SHIM
# Just a comment, no import-as, no __all__
x = 42
""")
        r = check_shim(shim)
        assert r.ok, f"Inert shim should pass: {r}"

    def test_unreadable_path_fails(self, tmp_path: Path) -> None:
        r = check_shim(tmp_path / "ghost.py")
        assert not r.ok
        assert "Cannot read" in r.message or not r.ok  # fail gracefully


# ---------------------------------------------------------------------------
# 7. check_all: empty dir
# ---------------------------------------------------------------------------

class TestCheckAll:
    def test_empty_dir(self, tmp_path: Path) -> None:
        assert check_all(tmp_path) == []

    def test_non_shim_files_ignored(self, tmp_path: Path) -> None:
        _w(tmp_path, "normal.py", "def f(): pass\n")
        assert check_all(tmp_path) == []


# ---------------------------------------------------------------------------
# 8-11. check_pickles
# ---------------------------------------------------------------------------

class TestCheckPickles:
    def test_valid_dict_pkl(self, tmp_path: Path) -> None:
        _pkl(tmp_path, "model.pkl", {"accuracy": 0.95})
        results = check_pickles(tmp_path)
        assert len(results) == 1 and results[0].ok

    def test_corrupt_pkl_flagged(self, tmp_path: Path) -> None:
        _bad_pkl(tmp_path, "bad.pkl")
        results = check_pickles(tmp_path)
        assert len(results) == 1 and not results[0].ok

    def test_good_and_corrupt(self, tmp_path: Path) -> None:
        _pkl(tmp_path, "good.pkl", [1, 2, 3])
        _bad_pkl(tmp_path, "bad.pkl")
        results = check_pickles(tmp_path)
        assert len(results) == 2
        assert any(r.ok and not r.skipped for r in results)
        assert any(not r.ok for r in results)

    def test_skip_pattern(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _bad_pkl(tmp_path, "legacy_v1_old.pkl")
        import check_shims as cs
        monkeypatch.setattr(cs, "PICKLE_SKIP",
                            [("legacy_v1_*.pkl", "Pre-refactor stale.")])
        results = cs.check_pickles(tmp_path)
        assert len(results) == 1
        assert results[0].skipped and results[0].ok

    def test_non_skip_pattern_tested(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _bad_pkl(tmp_path, "new_model.pkl")
        import check_shims as cs
        monkeypatch.setattr(cs, "PICKLE_SKIP", [("legacy_*.pkl", "stale.")])
        results = cs.check_pickles(tmp_path)
        assert not results[0].skipped and not results[0].ok

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        assert check_pickles(tmp_path) == []


# ---------------------------------------------------------------------------
# 12-13. report_unused
# ---------------------------------------------------------------------------

class TestReportUnused:
    def test_shim_import_detected(self, tmp_path: Path) -> None:
        log = _w(tmp_path, "a.log", "INFO start\nimport shim_legacy_mod\nINFO done\n")
        hits = report_unused([log])
        assert len(hits) == 1 and "shim_legacy_mod" in hits[0]

    def test_from_shim_import_detected(self, tmp_path: Path) -> None:
        log = _w(tmp_path, "b.log", "from shims.v1 import api\n")
        hits = report_unused([log])
        assert len(hits) == 1 and ":1:" in hits[0]

    def test_line_number_in_hit(self, tmp_path: Path) -> None:
        log = _w(tmp_path, "c.log", "line1\nimport shim_x\nline3\n")
        hits = report_unused([log])
        assert ":2:" in hits[0]

    def test_clean_log_no_hits(self, tmp_path: Path) -> None:
        log = _w(tmp_path, "clean.log", "INFO OK\nDEBUG processing\n")
        assert report_unused([log]) == []

    def test_empty_list(self) -> None:
        assert report_unused([]) == []

    def test_nonexistent_log_skipped(self, tmp_path: Path) -> None:
        assert report_unused([tmp_path / "ghost.log"]) == []


# ---------------------------------------------------------------------------
# 14. __str__ format
# ---------------------------------------------------------------------------

class TestStrFormat:
    def test_shim_ok(self) -> None:
        assert "[OK]" in str(ShimResult("/a.py", True, "fine"))

    def test_shim_fail(self) -> None:
        assert "[FAIL]" in str(ShimResult("/a.py", False, "bad"))

    def test_pickle_skip(self) -> None:
        assert "[SKIP]" in str(PickleResult("/m.pkl", True, "skip", skipped=True))

    def test_pickle_ok(self) -> None:
        assert "[OK]" in str(PickleResult("/m.pkl", True, "ok"))

    def test_pickle_fail(self) -> None:
        assert "[FAIL]" in str(PickleResult("/m.pkl", False, "fail"))
