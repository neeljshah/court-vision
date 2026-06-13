"""tests.platform.test_atlas_build_all — Tests for the multi-sport atlas driver.

Verifies:
1. ``build_all.main(["--sport", "all", "--out", ...])`` writes ``_Hub.md``.
2. The hub contains ``[[wikilinks]]`` to each sport index.
3. The ``--sport`` filter selects only the requested sport.
4. A missing sport module is skipped gracefully (no crash, exit 0).
5. ``write_hub`` is idempotent (can be called twice without error).

All output goes to ``tmp_path`` — no file is written to the committed tree.
"""
from __future__ import annotations

import sys
import textwrap
import types
from pathlib import Path
from typing import List
from unittest import mock

import pytest

# Ensure repo root is importable (covers bare pytest invocations)
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platform.atlas.build_all import (
    _SPORT_MANIFEST,
    _derive_domain,
    main,
    write_hub,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_build_atlas(note_count: int = 3):
    """Return a stub ``build_atlas`` that creates *note_count* placeholder files."""

    def _build(out_dir: Path, corpus_dir: Path = Path("data")) -> List[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        written: List[Path] = []
        for i in range(note_count):
            p = out_dir / f"stub_note_{i}.md"
            p.write_text(f"# stub {i}\n", encoding="utf-8")
            written.append(p)
        # Always write an _Index note so hub wikilinks resolve
        idx = out_dir / "_Index.md"
        idx.write_text("# Index\n", encoding="utf-8")
        written.append(idx)
        return written

    return _build


def _stub_build_h2h(note_count: int = 2):
    """Return a stub ``build_h2h`` that creates *note_count* placeholder Matchups notes."""

    def _build(out_dir: Path, corpus_dir: Path = Path("data")) -> List[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        written: List[Path] = []
        for i in range(note_count):
            p = out_dir / f"stub_h2h_{i}.md"
            p.write_text(f"# H2H stub {i}\n", encoding="utf-8")
            written.append(p)
        return written

    return _build


# Sports that have a real atlas_h2h (all except basketball_nba)
_H2H_DOMAINS = {"tennis", "soccer", "mlb"}


def _patch_all_adapters(note_count: int = 2):
    """Context manager: patch every adapter module and its atlas_h2h sibling.

    For domains that have a real ``atlas_h2h`` (tennis, soccer, mlb) the stub
    module is also injected under ``domains.<domain>.atlas_h2h``.  The NBA
    domain is intentionally left without an ``atlas_h2h`` stub so the
    graceful-skip path is exercised every time.
    """
    patches = {}
    for sid, display_name, adapter_module, _ in _SPORT_MANIFEST:
        stub_mod = types.ModuleType(adapter_module)
        stub_mod.build_atlas = _stub_build_atlas(note_count)  # type: ignore[attr-defined]
        patches[adapter_module] = stub_mod

        domain = _derive_domain(adapter_module)
        if domain in _H2H_DOMAINS:
            h2h_mod_name = f"domains.{domain}.atlas_h2h"
            h2h_mod = types.ModuleType(h2h_mod_name)
            h2h_mod.build_h2h = _stub_build_h2h(2)  # type: ignore[attr-defined]
            patches[h2h_mod_name] = h2h_mod

    return mock.patch.dict("sys.modules", patches)


# ---------------------------------------------------------------------------
# Test 1 — build all sports → _Hub.md is written
# ---------------------------------------------------------------------------


def test_build_all_writes_hub(tmp_path: Path) -> None:
    """main() with --sport all must write _Hub.md inside the output directory."""
    out_dir = tmp_path / "Sports"
    with _patch_all_adapters():
        exit_code = main(["--sport", "all", "--out", str(out_dir)])

    assert exit_code == 0, f"Expected exit code 0, got {exit_code}"
    hub = out_dir / "_Hub.md"
    assert hub.exists(), f"_Hub.md not found at {hub}"
    assert hub.stat().st_size > 0, "_Hub.md is empty"


# ---------------------------------------------------------------------------
# Test 2 — hub contains [[wikilinks]] to each sport index
# ---------------------------------------------------------------------------


def test_hub_contains_sport_wikilinks(tmp_path: Path) -> None:
    """_Hub.md must contain a [[<Sport>/_Index]] wikilink for each sport."""
    out_dir = tmp_path / "Sports"
    with _patch_all_adapters():
        main(["--sport", "all", "--out", str(out_dir)])

    hub_text = (out_dir / "_Hub.md").read_text(encoding="utf-8")

    for _, display_name, _, _ in _SPORT_MANIFEST:
        expected_link = f"[[{display_name}/_Index]]"
        assert expected_link in hub_text, (
            f"Hub is missing wikilink {expected_link!r}.\n"
            f"Hub content (first 800 chars):\n{hub_text[:800]}"
        )


# ---------------------------------------------------------------------------
# Test 3 — --sport filter builds only the requested sport
# ---------------------------------------------------------------------------


def test_sport_filter_selects_one_sport(tmp_path: Path) -> None:
    """--sport tennis must build only Tennis/ and still write _Hub.md."""
    out_dir = tmp_path / "Sports"

    called: List[str] = []

    def make_spy(display_name: str, note_count: int = 1):
        def _build(out_dir: Path, corpus_dir: Path = Path("data")) -> List[Path]:
            called.append(display_name)
            out_dir.mkdir(parents=True, exist_ok=True)
            p = out_dir / "_Index.md"
            p.write_text(f"# {display_name}\n", encoding="utf-8")
            return [p]
        return _build

    stub_modules = {}
    for sid, display_name, adapter_module, _ in _SPORT_MANIFEST:
        mod = types.ModuleType(adapter_module)
        mod.build_atlas = make_spy(display_name)  # type: ignore[attr-defined]
        stub_modules[adapter_module] = mod

    with mock.patch.dict("sys.modules", stub_modules):
        exit_code = main(["--sport", "tennis", "--out", str(out_dir)])

    assert exit_code == 0
    assert called == ["Tennis"], (
        f"Expected only Tennis to be built; got {called}"
    )
    # Hub should still be written
    assert (out_dir / "_Hub.md").exists()


# ---------------------------------------------------------------------------
# Test 4 — missing sport module is skipped gracefully (no crash)
# ---------------------------------------------------------------------------


def test_missing_sport_module_skipped_gracefully(tmp_path: Path) -> None:
    """When a sport adapter cannot be imported the driver must skip it, not crash."""
    out_dir = tmp_path / "Sports"

    # Patch only tennis; leave soccer/mlb/nba absent from sys.modules so the
    # normal ImportError path triggers for them.
    tennis_mod = types.ModuleType("domains.tennis.atlas")
    tennis_mod.build_atlas = _stub_build_atlas(1)  # type: ignore[attr-defined]

    # Ensure the three other adapter modules are NOT in sys.modules
    absent = [
        "domains.soccer.atlas",
        "domains.mlb.atlas",
        "domains.basketball_nba.memory_atlas",
    ]
    cleaned = {k: v for k, v in sys.modules.items() if k not in absent}

    with mock.patch.dict(
        "sys.modules",
        {**cleaned, "domains.tennis.atlas": tennis_mod},
        clear=True,
    ):
        exit_code = main(["--sport", "all", "--out", str(out_dir)])

    # Must not crash — exit 0 is acceptable even if most sports skipped
    assert exit_code == 0, f"Expected exit 0 (graceful skip), got {exit_code}"

    hub = out_dir / "_Hub.md"
    assert hub.exists(), "_Hub.md must be written even when some sports skipped"


# ---------------------------------------------------------------------------
# Test 5 — write_hub is idempotent
# ---------------------------------------------------------------------------


def test_write_hub_is_idempotent(tmp_path: Path) -> None:
    """Calling write_hub twice must not raise and the file must be valid."""
    out_dir = tmp_path / "Sports"
    built = [
        ("tennis_atp", "Tennis", 3),
        ("soccer_fd", "Soccer", 5),
    ]
    hub1 = write_hub(out_dir, built)
    hub2 = write_hub(out_dir, built)
    assert hub1 == hub2
    text = hub2.read_text(encoding="utf-8")
    assert "[[Tennis/_Index]]" in text
    assert "[[Soccer/_Index]]" in text
    assert "#sport" in text
    assert "#memory-graph" in text


# ---------------------------------------------------------------------------
# Test 6 — hub always links to the NBA vault
# ---------------------------------------------------------------------------


def test_hub_links_to_nba_vault(tmp_path: Path) -> None:
    """_Hub.md must contain a link to the existing NBA vault Home note."""
    out_dir = tmp_path / "Sports"
    hub = write_hub(out_dir, [])
    text = hub.read_text(encoding="utf-8")
    assert "[[Home]]" in text, (
        "Hub must link to [[Home]] (NBA vault entry point).\n"
        f"Hub content (first 600 chars):\n{text[:600]}"
    )


# ---------------------------------------------------------------------------
# Test 7 — unknown --sport argument returns exit code 1
# ---------------------------------------------------------------------------


def test_unknown_sport_arg_returns_error(tmp_path: Path) -> None:
    """An unrecognised --sport value must exit with code 1."""
    out_dir = tmp_path / "Sports"
    exit_code = main(["--sport", "cricket", "--out", str(out_dir)])
    assert exit_code == 1, f"Expected exit 1 for unknown sport, got {exit_code}"


# ---------------------------------------------------------------------------
# Test 8 — build_h2h is called for H2H-capable sports; NBA is skipped cleanly
# ---------------------------------------------------------------------------


def test_h2h_notes_built_for_capable_sports(tmp_path: Path) -> None:
    """build_h2h stubs must produce Matchups/ notes for tennis/soccer/mlb.

    Basketball_NBA has no atlas_h2h — its Matchups/ directory must NOT be
    created (graceful-skip), and the overall exit code must still be 0.
    """
    out_dir = tmp_path / "Sports"
    with _patch_all_adapters(note_count=2):
        exit_code = main(["--sport", "all", "--out", str(out_dir)])

    assert exit_code == 0, f"Expected exit code 0, got {exit_code}"

    # Sports with H2H support → Matchups/ directory must contain stub notes
    h2h_sport_dirs = {
        "Tennis": out_dir / "Tennis" / "Matchups",
        "Soccer": out_dir / "Soccer" / "Matchups",
        "MLB":    out_dir / "MLB" / "Matchups",
    }
    for sport_name, matchups_dir in h2h_sport_dirs.items():
        assert matchups_dir.exists(), (
            f"{sport_name}: expected Matchups/ dir at {matchups_dir}"
        )
        md_files = list(matchups_dir.glob("*.md"))
        assert md_files, (
            f"{sport_name}: Matchups/ dir exists but contains no .md notes"
        )

    # NBA has no atlas_h2h — its Matchups/ must not have been created
    nba_matchups = out_dir / "Basketball_NBA" / "Matchups"
    assert not nba_matchups.exists(), (
        f"Basketball_NBA should NOT have a Matchups/ dir (no atlas_h2h), "
        f"but found {nba_matchups}"
    )


# ---------------------------------------------------------------------------
# Test 9 — _derive_domain correctly extracts domain from adapter_module
# ---------------------------------------------------------------------------


def test_derive_domain_extracts_correctly() -> None:
    """_derive_domain must strip the 'domains.' prefix and the trailing module name."""
    assert _derive_domain("domains.tennis.atlas") == "tennis"
    assert _derive_domain("domains.soccer.atlas") == "soccer"
    assert _derive_domain("domains.mlb.atlas") == "mlb"
    assert _derive_domain("domains.basketball_nba.memory_atlas") == "basketball_nba"
