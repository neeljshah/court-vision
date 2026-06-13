"""tests.platform.test_atlas_build_all_full — Tests for the --full flag of the atlas driver.

Verifies:
1. --full calls extra generators (_EXTRA_GENS) for capable sports.
2. --full exits 0 when some extra modules are absent (graceful ImportError skip).
3. Without --full, extras and meta generators are NOT called (default mode unchanged).
All output goes to tmp_path — no file is written to the committed tree.

Core build/hub/filter/graceful-skip tests live in test_atlas_build_all.py.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import List
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.atlas.build_all import (
    _CAT,
    _EXTRA_GENS,
    _META_GENS,
    _SPORT_MANIFEST,
    _derive_domain,
    main,
)

# ---------------------------------------------------------------------------
# Helpers (duplicated from test_atlas_build_all.py — both files are self-contained)
# ---------------------------------------------------------------------------

_H2H_DOMAINS = {"tennis", "soccer", "mlb"}
_PLAYSTYLE_DOMAINS = {"tennis", "soccer", "mlb"}
_ARCHETYPE_DOMAIN = "basketball_nba"
_TOURNAMENT_DOMAINS = {"tennis"}
_SEASONS_DOMAINS = {"soccer", "mlb"}
_SEASONS_NBA_DOMAIN = "basketball_nba"


def _make_stub_builder(prefix: str, note_count: int = 2, index: bool = False):
    """Return a stub build_* callable that writes note_count placeholder .md files."""
    def _build(out_dir: Path, **_kwargs) -> List[Path]:
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


def _patch_full_adapters(tmp_out: Path):
    """Patch all base adapters PLUS stub extra + meta generators for --full testing."""
    patches = {}

    # Base adapters (same as _patch_all_adapters but inlined for clarity)
    for _sid, _name, adapter_module, _ in _SPORT_MANIFEST:
        mod = types.ModuleType(adapter_module)
        mod.build_atlas = _make_stub_builder("stub", 2, index=True)  # type: ignore
        patches[adapter_module] = mod

        domain = _derive_domain(adapter_module)
        for sibling, fn_attr, prefix in [
            (f"domains.{domain}.atlas_h2h",              "build_h2h",        "h2h"),
            (f"domains.{domain}.atlas_playstyles",        "build_playstyles",  "ps"),
            (f"domains.{domain}.memory_atlas_archetypes", "build_archetypes",  "arc"),
            (f"domains.{domain}.atlas_tournaments",       "build_tournaments", "trn"),
            (f"domains.{domain}.atlas_seasons",           "build_seasons",     "sea"),
            (f"domains.{domain}.memory_atlas_seasons",    "build_seasons",     "sea"),
        ]:
            m = types.ModuleType(sibling)
            setattr(m, fn_attr, _make_stub_builder(prefix, 1))
            patches[sibling] = m

    # Extra generators from _EXTRA_GENS
    extra_called: List[str] = []
    for (gen_domain, mod_suffix, fn_name, subdir, _kwarg) in _EXTRA_GENS:
        full_mod = f"domains.{gen_domain}.{mod_suffix}"
        if full_mod not in patches:
            m = types.ModuleType(full_mod)
            captured_subdir = subdir
            def _stub_extra(out_dir: Path, sd=captured_subdir, **_kw) -> List[Path]:
                out_dir.mkdir(parents=True, exist_ok=True)
                extra_called.append(sd)
                p = out_dir / f"extra_{sd}.md"
                p.write_text(f"# {sd}\n", encoding="utf-8")
                return [p]
            setattr(m, fn_name, _stub_extra)
            patches[full_mod] = m
        else:
            # Module already patched (multiple fns on same module) — add the fn
            m = patches[full_mod]
            captured_subdir = subdir
            def _stub_extra2(out_dir: Path, sd=captured_subdir, **_kw) -> List[Path]:
                out_dir.mkdir(parents=True, exist_ok=True)
                extra_called.append(sd)
                p = out_dir / f"extra_{sd}.md"
                p.write_text(f"# {sd}\n", encoding="utf-8")
                return [p]
            setattr(m, fn_name, _stub_extra2)

    # META generators from _META_GENS
    meta_called: List[str] = []
    for (meta_mod, meta_fn) in _META_GENS:
        full_meta = f"scripts.platformkit.atlas.{meta_mod}"
        m = types.ModuleType(full_meta)
        captured_fn = meta_fn
        meta_out = tmp_out / f"_{meta_mod}.md"
        def _stub_meta(vault_sports_dir: Path = tmp_out, fn=captured_fn, p=meta_out) -> Path:
            meta_called.append(fn)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"# {fn}\n", encoding="utf-8")
            return p
        setattr(m, meta_fn, _stub_meta)
        patches[full_meta] = m

    return mock.patch.dict("sys.modules", patches), extra_called, meta_called


# ---------------------------------------------------------------------------
# --full flag tests
# ---------------------------------------------------------------------------

def test_full_flag_runs_extra_generators(tmp_path: Path) -> None:
    """--full must call extra generators for sports present and skip absent ones gracefully."""
    out_dir = tmp_path / "Sports"
    out_dir.mkdir(parents=True, exist_ok=True)

    patch_ctx, extra_called, meta_called = _patch_full_adapters(out_dir)
    with patch_ctx:
        exit_code = main(["--sport", "all", "--out", str(out_dir), "--full"])

    assert exit_code == 0, f"Expected exit 0 with --full, got {exit_code}"
    # At least one extra subdir must have been built (StyleMatchups for tennis)
    assert "StyleMatchups" in extra_called, f"StyleMatchups not in extra_called: {extra_called}"
    assert "StyleTrends"   in extra_called, f"StyleTrends not in extra_called: {extra_called}"
    # META generators must have been called
    assert len(meta_called) == len(_META_GENS), (
        f"Expected {len(_META_GENS)} meta generators, called: {meta_called}"
    )
    # Hub must still be written
    assert (out_dir / "_Hub.md").exists(), "_Hub.md missing after --full run"


def test_full_flag_skips_absent_extras_gracefully(tmp_path: Path) -> None:
    """--full must exit 0 when some extra modules are absent (ImportError -> graceful skip)."""
    out_dir = tmp_path / "Sports"
    # Only wire base adapters + one real extra (tennis style_matchups) + meta stubs.
    # Leave soccer/mlb extras absent so ImportError path is exercised.
    patches: dict = {}
    for _sid, _name, adapter_module, _ in _SPORT_MANIFEST:
        mod = types.ModuleType(adapter_module)
        mod.build_atlas = _make_stub_builder("stub", 1, index=True)  # type: ignore
        patches[adapter_module] = mod

    # Stub tennis style_matchups only
    tennis_sm = types.ModuleType("domains.tennis.atlas_style_matchups")
    called: List[str] = []
    def _tennis_sm(out_dir: Path, **_kw) -> List[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        called.append("tennis_style_matchups")
        p = out_dir / "sm_note.md"
        p.write_text("# sm\n", encoding="utf-8")
        return [p]
    tennis_sm.build_style_matchups = _tennis_sm  # type: ignore
    patches["domains.tennis.atlas_style_matchups"] = tennis_sm

    # Stub meta generators minimally
    for meta_mod, meta_fn in _META_GENS:
        full_meta = f"scripts.platformkit.atlas.{meta_mod}"
        m = types.ModuleType(full_meta)
        meta_out = out_dir / f"_{meta_mod}.md"
        def _meta_stub(vault_sports_dir: Path = out_dir, p=meta_out) -> Path:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# meta\n", encoding="utf-8")
            return p
        setattr(m, meta_fn, _meta_stub)
        patches[full_meta] = m

    with mock.patch.dict("sys.modules", patches):
        exit_code = main(["--sport", "all", "--out", str(out_dir), "--full"])

    assert exit_code == 0, f"Expected exit 0 with absent extras, got {exit_code}"
    assert "tennis_style_matchups" in called, "Tennis style_matchups stub was not called"
    # StyleMatchups/ dir must exist for tennis
    assert (out_dir / "Tennis" / "StyleMatchups").exists(), "Tennis/StyleMatchups/ missing"


def test_full_flag_default_off_behavior_unchanged(tmp_path: Path) -> None:
    """Without --full, extras and meta are NOT called — default mode unchanged."""
    out_dir = tmp_path / "Sports"
    extra_called: List[str] = []

    patches: dict = {}
    for _sid, _name, adapter_module, _ in _SPORT_MANIFEST:
        mod = types.ModuleType(adapter_module)
        mod.build_atlas = _make_stub_builder("stub", 1, index=True)  # type: ignore
        patches[adapter_module] = mod

    # Wire tennis style_matchups — it must NOT be called without --full
    tennis_sm = types.ModuleType("domains.tennis.atlas_style_matchups")
    def _should_not_call(out_dir: Path, **_kw) -> List[Path]:
        extra_called.append("tennis_style_matchups")
        return []
    tennis_sm.build_style_matchups = _should_not_call  # type: ignore
    patches["domains.tennis.atlas_style_matchups"] = tennis_sm

    with mock.patch.dict("sys.modules", patches):
        exit_code = main(["--sport", "all", "--out", str(out_dir)])

    assert exit_code == 0
    assert extra_called == [], f"Extra generators must NOT run without --full; got {extra_called}"


# ---------------------------------------------------------------------------
# --with-catalogs flag tests
# ---------------------------------------------------------------------------

def _make_catalog_patches(cat_called: List[str], adapter_ok: bool = True) -> dict:
    """Stub all _CAT loader + catalog + joint modules.  Also stubs base adapters."""
    patches: dict = {}
    for _sid, _name, adapter_module, _ in _SPORT_MANIFEST:
        mod = types.ModuleType(adapter_module)
        mod.build_atlas = _make_stub_builder("stub", 1, index=True)  # type: ignore
        patches[adapter_module] = mod
    sentinel = object() if adapter_ok else None
    for (loader_mod, cat_mod, joint_mod, joint_fn, _, display, _) in _CAT:
        lmod = types.ModuleType(loader_mod)
        lmod._load_adapter = lambda _cd, s=sentinel: s  # type: ignore
        patches[loader_mod] = lmod
        cmod = types.ModuleType(cat_mod)
        def _rc(_a, _s, out_path=None, dn=display) -> None:
            cat_called.append(f"{dn}:run_catalog")
            if out_path: out_path.parent.mkdir(parents=True, exist_ok=True); out_path.write_text(f"# {dn}\n", encoding="utf-8")
        cmod.run_catalog = _rc  # type: ignore
        patches[cat_mod] = cmod
        jmod = types.ModuleType(joint_mod)
        def _rj(_a, _s, out_path=None, dn=display, jfn=joint_fn) -> None:
            cat_called.append(f"{dn}:{jfn}")
            if out_path: out_path.parent.mkdir(parents=True, exist_ok=True); out_path.write_text(f"# {dn} j\n", encoding="utf-8")
        setattr(jmod, joint_fn, _rj)
        patches[joint_mod] = jmod
    return patches


def test_with_catalogs_runs_catalog_functions(tmp_path: Path) -> None:
    """--with-catalogs must call run_catalog + run_joint_catalog for tennis/soccer/mlb."""
    out_dir = tmp_path / "Sports"
    cat_called: List[str] = []
    with mock.patch.dict("sys.modules", _make_catalog_patches(cat_called, adapter_ok=True)):
        exit_code = main(["--sport", "all", "--out", str(out_dir), "--with-catalogs"])
    assert exit_code == 0, f"Expected exit 0 with --with-catalogs, got {exit_code}"
    assert len(cat_called) == 6, f"Expected 6 catalog calls (3 sports × 2), got: {cat_called}"
    assert {c.split(":")[0] for c in cat_called} == {"Tennis", "Soccer", "MLB"}
    for display in ("Tennis", "Soccer", "MLB"):
        assert (out_dir / display / "Signals" / "_Catalog.md").exists(), f"{display}/_Catalog.md missing"
        assert (out_dir / display / "Signals" / "_Catalog_Joint.md").exists(), f"{display}/_Catalog_Joint.md missing"
    assert (out_dir / "_Hub.md").exists()


def test_with_catalogs_default_off(tmp_path: Path) -> None:
    """Without --with-catalogs the catalog functions must NOT be called."""
    out_dir = tmp_path / "Sports"
    cat_called: List[str] = []
    with mock.patch.dict("sys.modules", _make_catalog_patches(cat_called, adapter_ok=True)):
        exit_code = main(["--sport", "all", "--out", str(out_dir)])
    assert exit_code == 0
    assert cat_called == [], f"Catalogs must NOT run without --with-catalogs; got: {cat_called}"


def test_with_catalogs_skips_absent_corpus(tmp_path: Path) -> None:
    """--with-catalogs exits 0 and skips gracefully when _load_adapter returns None."""
    out_dir = tmp_path / "Sports"
    cat_called: List[str] = []
    with mock.patch.dict("sys.modules", _make_catalog_patches(cat_called, adapter_ok=False)):
        exit_code = main(["--sport", "all", "--out", str(out_dir), "--with-catalogs"])
    assert exit_code == 0, f"Expected exit 0 on absent corpus, got {exit_code}"
    assert cat_called == [], f"run_catalog must not be called when adapter is None; got: {cat_called}"
    assert (out_dir / "_Hub.md").exists()
