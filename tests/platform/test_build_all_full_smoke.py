"""tests.platform.test_build_all_full_smoke — Hermetic smoke for the full graph build.

Part 1 – SMOKE: build_all.main(["--sport","all","--full","--out",tmp]):
  (a) exit 0  (b) _Hub.md written  (c) all META generators ran  (d) absent extra skipped cleanly.
Part 2 – GRAPH-HEALTH on synthetic vault:
  (a) GRAPH-INTEGRITY PASS + PERSON-FREE PASS for a clean tree.
  (b) PERSON-FREE FAIL when [[Players/X]] present.
No real-corpus reads; no network; single-process; fast + deterministic.
"""
from __future__ import annotations

import pathlib
import re
import sys
import types
from typing import List
from unittest import mock

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.atlas.build_all import (
    _EXTRA_GENS, _META_GENS, _SPORT_MANIFEST, _derive_domain, main,
)
from scripts.platformkit.atlas.graph_health import build_graph_health


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _make_stub_builder(prefix: str, note_count: int = 2, index: bool = False):
    def _build(out_dir: pathlib.Path, **_kw) -> List[pathlib.Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        written = [out_dir / f"{prefix}_{i}.md" for i in range(note_count)]
        for p in written:
            p.write_text(f"# {p.stem}\n", encoding="utf-8")
        if index:
            idx = out_dir / "_Index.md"
            idx.write_text("# Index\n", encoding="utf-8")
            written.append(idx)
        return written
    return _build


def _write(base: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _build_full_patches(out_dir: pathlib.Path):
    """Build sys.modules patch dict + shared meta_called list for --full smoke."""
    patches: dict = {}
    meta_called: List[str] = []

    for _sid, _name, adapter_module, _ in _SPORT_MANIFEST:
        mod = types.ModuleType(adapter_module)
        mod.build_atlas = _make_stub_builder("stub", 2, index=True)  # type: ignore[attr-defined]
        patches[adapter_module] = mod

        domain = _derive_domain(adapter_module)
        for sibling, fn_attr, prefix in [
            (f"domains.{domain}.atlas_h2h",              "build_h2h",       "h2h"),
            (f"domains.{domain}.atlas_playstyles",        "build_playstyles", "ps"),
            (f"domains.{domain}.memory_atlas_archetypes", "build_archetypes", "arc"),
            (f"domains.{domain}.atlas_tournaments",       "build_tournaments","trn"),
            (f"domains.{domain}.atlas_seasons",           "build_seasons",    "sea"),
            (f"domains.{domain}.memory_atlas_seasons",    "build_seasons",    "sea"),
        ]:
            if sibling not in patches:
                patches[sibling] = types.ModuleType(sibling)
            setattr(patches[sibling], fn_attr, _make_stub_builder(prefix, 1))

    for (gen_domain, mod_suffix, fn_name, subdir, _kwarg) in _EXTRA_GENS:
        full_mod = f"domains.{gen_domain}.{mod_suffix}"
        if full_mod not in patches:
            patches[full_mod] = types.ModuleType(full_mod)
        captured_sub = subdir

        def _stub_extra(od: pathlib.Path, sd: str = captured_sub, **_kw: object) -> List[pathlib.Path]:
            od.mkdir(parents=True, exist_ok=True)
            p = od / f"extra_{sd}.md"
            p.write_text(f"# {sd}\n", encoding="utf-8")
            return [p]

        setattr(patches[full_mod], fn_name, _stub_extra)

    for meta_mod, meta_fn in _META_GENS:
        full_meta = f"scripts.platformkit.atlas.{meta_mod}"
        m = types.ModuleType(full_meta)
        meta_out = out_dir / f"_{meta_mod}.md"

        def _stub_meta(
            vault_sports_dir: pathlib.Path = out_dir,
            fn: str = meta_fn,
            p: pathlib.Path = meta_out,
        ) -> pathlib.Path:
            meta_called.append(fn)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"# {fn}\n", encoding="utf-8")
            return p

        setattr(m, meta_fn, _stub_meta)
        patches[full_meta] = m

    return patches, meta_called


# ===========================================================================
# Part 1 — Full-graph smoke
# ===========================================================================

class TestBuildAllFullSmoke:
    """build_all --sport all --full exits cleanly, writes hub, runs all META."""

    def test_exit_code_zero(self, tmp_path: pathlib.Path) -> None:
        out_dir = tmp_path / "Sports"
        patches, _ = _build_full_patches(out_dir)
        with mock.patch.dict("sys.modules", patches):
            code = main(["--sport", "all", "--full", "--out", str(out_dir)])
        assert code == 0, f"Expected exit 0 with --full, got {code}"

    def test_hub_written_and_non_empty(self, tmp_path: pathlib.Path) -> None:
        out_dir = tmp_path / "Sports"
        patches, _ = _build_full_patches(out_dir)
        with mock.patch.dict("sys.modules", patches):
            main(["--sport", "all", "--full", "--out", str(out_dir)])
        hub = out_dir / "_Hub.md"
        assert hub.exists() and hub.stat().st_size > 0, "_Hub.md missing or empty"

    def test_hub_contains_all_sport_names(self, tmp_path: pathlib.Path) -> None:
        out_dir = tmp_path / "Sports"
        patches, _ = _build_full_patches(out_dir)
        with mock.patch.dict("sys.modules", patches):
            main(["--sport", "all", "--full", "--out", str(out_dir)])
        content = (out_dir / "_Hub.md").read_text(encoding="utf-8")
        for _sid, display_name, _mod, _corpus in _SPORT_MANIFEST:
            assert display_name in content, f"Hub missing sport: {display_name}"

    def test_all_meta_generators_ran(self, tmp_path: pathlib.Path) -> None:
        out_dir = tmp_path / "Sports"
        patches, meta_called = _build_full_patches(out_dir)
        with mock.patch.dict("sys.modules", patches):
            main(["--sport", "all", "--full", "--out", str(out_dir)])
        expected = {fn for _, fn in _META_GENS}
        assert expected == set(meta_called), f"Meta generators not called: {expected - set(meta_called)}"

    def test_absent_extra_generator_skipped_gracefully(self, tmp_path: pathlib.Path) -> None:
        out_dir = tmp_path / "Sports"
        patches, _ = _build_full_patches(out_dir)
        first_extra_mod = f"domains.{_EXTRA_GENS[0][0]}.{_EXTRA_GENS[0][1]}"
        patches.pop(first_extra_mod, None)
        with mock.patch.dict("sys.modules", patches):
            code = main(["--sport", "all", "--full", "--out", str(out_dir)])
        assert code == 0
        assert (out_dir / "_Hub.md").exists()

    def test_full_flag_off_skips_meta_generators(self, tmp_path: pathlib.Path) -> None:
        out_dir = tmp_path / "Sports"
        patches, meta_called = _build_full_patches(out_dir)
        with mock.patch.dict("sys.modules", patches):
            code = main(["--sport", "all", "--out", str(out_dir)])
        assert code == 0
        assert meta_called == [], f"META generators ran without --full: {meta_called}"


# ===========================================================================
# Part 2 — graph_health verdicts on synthetic vault
# ===========================================================================

def _report(vault_dir: pathlib.Path) -> str:
    return build_graph_health(vault_dir).read_text(encoding="utf-8")


def _gi_verdict(text: str) -> str:
    m = re.search(r"GRAPH-INTEGRITY verdict\s*\|\s*\*\*([^*]+)\*\*", text)
    assert m, f"GRAPH-INTEGRITY verdict row missing:\n{text[:600]}"
    return m.group(1).strip()


def _pf_verdict(text: str) -> str:
    m = re.search(r"PERSON-FREE verdict\s*\|\s*\*\*([^*]+)\*\*", text)
    if not m:
        m = re.search(r"PERSON-FREE:\s+(\S+)", text)
    assert m, f"PERSON-FREE verdict missing:\n{text[:600]}"
    return m.group(1).strip()


def _person_count(text: str) -> int:
    m = re.search(r"Person-bearing notes\s*\|\s*\*\*(\d+)\*\*", text)
    assert m, f"Person-bearing notes row missing:\n{text[:600]}"
    return int(m.group(1))


def _dangling_fixable(text: str) -> int:
    m = re.search(r"Dangling — fixable\s*\|\s*(\d+)", text)
    assert m, f"Dangling fixable row missing:\n{text[:600]}"
    return int(m.group(1))


@pytest.fixture()
def clean_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    _write(tmp_path, "Soccer/_Index.md",  "# Soccer\n\n[[Teams/ManCity]] · [[Home]]\n")
    _write(tmp_path, "Soccer/Teams/ManCity.md", "# ManCity\n\n[[_Index]]\n")
    _write(tmp_path, "Tennis/_Index.md",  "# Tennis\n\nBest-of-3 sets.\n")
    return tmp_path


@pytest.fixture()
def vault_with_player_link(tmp_path: pathlib.Path) -> pathlib.Path:
    _write(tmp_path, "Soccer/_Index.md",  "# Soccer\n\n[[Teams/ManCity]]\n")
    _write(tmp_path, "Soccer/Teams/ManCity.md", "# ManCity\n\n[[_Index]] · [[Players/SomeStar]]\n")
    return tmp_path


class TestGraphHealthOnSyntheticVault:
    """graph_health verdicts on tiny, fully controlled vault trees."""

    def test_graph_integrity_pass_clean(self, clean_vault: pathlib.Path) -> None:
        assert _gi_verdict(_report(clean_vault)) == "PASS"

    def test_fixable_dangling_zero_clean(self, clean_vault: pathlib.Path) -> None:
        assert _dangling_fixable(_report(clean_vault)) == 0

    def test_person_free_pass_clean(self, clean_vault: pathlib.Path) -> None:
        text = _report(clean_vault)
        assert _person_count(text) == 0
        assert "PASS" in _pf_verdict(text)

    def test_person_free_fail_with_players_link(self, vault_with_player_link: pathlib.Path) -> None:
        text = _report(vault_with_player_link)
        assert _person_count(text) >= 1
        assert "FAIL" in _pf_verdict(text)

    def test_graph_integrity_not_crashed_with_players_link(
            self, vault_with_player_link: pathlib.Path) -> None:
        verdict = _gi_verdict(_report(vault_with_player_link))
        assert "PASS" in verdict or "FAIL" in verdict  # report generates, verdict key exists

    def test_report_file_written(self, clean_vault: pathlib.Path) -> None:
        out = build_graph_health(clean_vault)
        assert out.exists() and out.name == "_Graph_Health.md"

    def test_missing_vault_dir_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_graph_health(tmp_path / "does_not_exist")
