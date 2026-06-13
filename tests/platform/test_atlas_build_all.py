"""tests.platform.test_atlas_build_all — Tests for the multi-sport atlas driver (core).

Verifies:
1. build_all.main(["--sport","all","--out",...]) writes _Hub.md.
2. The hub contains [[wikilinks]] to each sport index.
3. --sport filter selects only the requested sport.
4. A missing sport module is skipped gracefully (no crash, exit 0).
5. write_hub is idempotent.
6. Tournaments/ built for tennis; Seasons/ built for soccer/mlb/nba.
All output goes to tmp_path — no file is written to the committed tree.

--full flag tests live in test_atlas_build_all_full.py.
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
    _SPORT_MANIFEST,
    _derive_domain,
    main,
    write_hub,
)

# ---------------------------------------------------------------------------
# Helpers
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


def _patch_all_adapters(note_count: int = 2):
    """Patch every adapter + h2h/playstyle/archetype/tournament/seasons sibling into sys.modules."""
    patches = {}
    for _sid, _name, adapter_module, _ in _SPORT_MANIFEST:
        mod = types.ModuleType(adapter_module)
        mod.build_atlas = _make_stub_builder("stub", note_count, index=True)  # type: ignore
        patches[adapter_module] = mod

        domain = _derive_domain(adapter_module)
        if domain in _H2H_DOMAINS:
            h2h_name = f"domains.{domain}.atlas_h2h"
            h2h_mod = types.ModuleType(h2h_name)
            h2h_mod.build_h2h = _make_stub_builder("h2h", 2)  # type: ignore
            patches[h2h_name] = h2h_mod

        if domain in _PLAYSTYLE_DOMAINS:
            ps_name = f"domains.{domain}.atlas_playstyles"
            ps_mod = types.ModuleType(ps_name)
            ps_mod.build_playstyles = _make_stub_builder("ps", 2)  # type: ignore
            patches[ps_name] = ps_mod
        elif domain == _ARCHETYPE_DOMAIN:
            arc_name = f"domains.{domain}.memory_atlas_archetypes"
            arc_mod = types.ModuleType(arc_name)
            arc_mod.build_archetypes = _make_stub_builder("arc", 2)  # type: ignore
            patches[arc_name] = arc_mod

        if domain in _TOURNAMENT_DOMAINS:
            trn_name = f"domains.{domain}.atlas_tournaments"
            trn_mod = types.ModuleType(trn_name)
            trn_mod.build_tournaments = _make_stub_builder("trn", 2)  # type: ignore
            patches[trn_name] = trn_mod

        if domain in _SEASONS_DOMAINS:
            sea_name = f"domains.{domain}.atlas_seasons"
            sea_mod = types.ModuleType(sea_name)
            sea_mod.build_seasons = _make_stub_builder("sea", 2)  # type: ignore
            patches[sea_name] = sea_mod
        elif domain == _SEASONS_NBA_DOMAIN:
            sea_name = f"domains.{domain}.memory_atlas_seasons"
            sea_mod = types.ModuleType(sea_name)
            sea_mod.build_seasons = _make_stub_builder("sea", 2)  # type: ignore
            patches[sea_name] = sea_mod

    return mock.patch.dict("sys.modules", patches)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_build_all_writes_hub(tmp_path: Path) -> None:
    """main() with --sport all must write a non-empty _Hub.md."""
    out_dir = tmp_path / "Sports"
    with _patch_all_adapters():
        exit_code = main(["--sport", "all", "--out", str(out_dir)])
    assert exit_code == 0, f"Expected exit 0, got {exit_code}"
    hub = out_dir / "_Hub.md"
    assert hub.exists() and hub.stat().st_size > 0


def test_hub_contains_sport_wikilinks(tmp_path: Path) -> None:
    """_Hub.md must contain [[<Sport>/_Index]] for each sport."""
    out_dir = tmp_path / "Sports"
    with _patch_all_adapters():
        main(["--sport", "all", "--out", str(out_dir)])
    hub_text = (out_dir / "_Hub.md").read_text(encoding="utf-8")
    for _, display_name, _, _ in _SPORT_MANIFEST:
        link = f"[[{display_name}/_Index]]"
        assert link in hub_text, f"Hub missing {link!r}.\n{hub_text[:800]}"


def test_sport_filter_selects_one_sport(tmp_path: Path) -> None:
    """--sport tennis must build only Tennis/ and still write _Hub.md."""
    out_dir = tmp_path / "Sports"
    called: List[str] = []

    stub_modules = {}
    for _sid, display_name, adapter_module, _ in _SPORT_MANIFEST:
        mod = types.ModuleType(adapter_module)
        def _spy(out_dir: Path, dn=display_name, **_kw) -> List[Path]:
            called.append(dn)
            out_dir.mkdir(parents=True, exist_ok=True)
            p = out_dir / "_Index.md"
            p.write_text(f"# {dn}\n", encoding="utf-8")
            return [p]
        mod.build_atlas = _spy  # type: ignore
        stub_modules[adapter_module] = mod

    with mock.patch.dict("sys.modules", stub_modules):
        # --with-named exercises the base (named) atlas path (gated off by the
        # person-free default); this test verifies sport FILTERING on that path.
        exit_code = main(["--sport", "tennis", "--out", str(out_dir), "--with-named"])

    assert exit_code == 0
    assert called == ["Tennis"], f"Expected only Tennis; got {called}"
    assert (out_dir / "_Hub.md").exists()


def test_missing_sport_module_skipped_gracefully(tmp_path: Path) -> None:
    """When a sport adapter cannot be imported, driver must skip it, not crash."""
    out_dir = tmp_path / "Sports"
    tennis_mod = types.ModuleType("domains.tennis.atlas")
    tennis_mod.build_atlas = _make_stub_builder("stub", 1, index=True)  # type: ignore
    absent = [
        "domains.soccer.atlas", "domains.mlb.atlas",
        "domains.basketball_nba.memory_atlas",
    ]
    cleaned = {k: v for k, v in sys.modules.items() if k not in absent}
    with mock.patch.dict(
        "sys.modules",
        {**cleaned, "domains.tennis.atlas": tennis_mod},
        clear=True,
    ):
        exit_code = main(["--sport", "all", "--out", str(out_dir)])
    assert exit_code == 0, f"Expected exit 0 (graceful skip), got {exit_code}"
    assert (out_dir / "_Hub.md").exists(), "_Hub.md must be written even when sports skipped"


def test_write_hub_is_idempotent(tmp_path: Path) -> None:
    """Calling write_hub twice must not raise and the file must be valid."""
    out_dir = tmp_path / "Sports"
    built = [("tennis_atp", "Tennis", 3), ("soccer_fd", "Soccer", 5)]
    hub1 = write_hub(out_dir, built)
    hub2 = write_hub(out_dir, built)
    assert hub1 == hub2
    text = hub2.read_text(encoding="utf-8")
    assert "[[Tennis/_Index]]" in text
    assert "[[Soccer/_Index]]" in text
    assert "#sport" in text and "#memory-graph" in text


def test_hub_links_to_nba_vault(tmp_path: Path) -> None:
    """_Hub.md must link to [[Home]] (NBA vault entry point)."""
    hub = write_hub(tmp_path / "Sports", [])
    text = hub.read_text(encoding="utf-8")
    assert "[[Home]]" in text, f"Hub missing [[Home]].\n{text[:600]}"


def test_unknown_sport_arg_returns_error(tmp_path: Path) -> None:
    """Unrecognised --sport value must exit with code 1."""
    assert main(["--sport", "cricket", "--out", str(tmp_path / "Sports")]) == 1


def test_h2h_notes_built_for_capable_sports(tmp_path: Path) -> None:
    """build_h2h stubs produce Matchups/ for tennis/soccer/mlb; NBA skipped.

    Matchups are a NAMED family (gated off by the person-free default), so this
    capability test runs the opt-in --with-named path.
    """
    out_dir = tmp_path / "Sports"
    with _patch_all_adapters(note_count=2):
        exit_code = main(["--sport", "all", "--out", str(out_dir), "--with-named"])
    assert exit_code == 0
    for sport_name, sub in [
        ("Tennis", out_dir / "Tennis" / "Matchups"),
        ("Soccer", out_dir / "Soccer" / "Matchups"),
        ("MLB",    out_dir / "MLB" / "Matchups"),
    ]:
        assert sub.exists(), f"{sport_name}: Matchups/ missing at {sub}"
        assert list(sub.glob("*.md")), f"{sport_name}: Matchups/ has no .md notes"
    nba_matchups = out_dir / "Basketball_NBA" / "Matchups"
    assert not nba_matchups.exists(), f"Basketball_NBA should NOT have Matchups/: {nba_matchups}"


def test_derive_domain_extracts_correctly() -> None:
    """_derive_domain strips domains. prefix and trailing module name."""
    cases = [
        ("domains.tennis.atlas", "tennis"),
        ("domains.soccer.atlas", "soccer"),
        ("domains.mlb.atlas", "mlb"),
        ("domains.basketball_nba.memory_atlas", "basketball_nba"),
    ]
    for module_str, expected in cases:
        assert _derive_domain(module_str) == expected, f"Failed for {module_str}"


def test_playstyles_and_archetypes_built(tmp_path: Path) -> None:
    """Playstyles/ built for tennis/soccer/mlb; Archetypes/ built for NBA."""
    out_dir = tmp_path / "Sports"
    with _patch_all_adapters(note_count=2):
        exit_code = main(["--sport", "all", "--out", str(out_dir)])
    assert exit_code == 0
    for sport_name, sub in [
        ("Tennis", out_dir / "Tennis" / "Playstyles"),
        ("Soccer", out_dir / "Soccer" / "Playstyles"),
        ("MLB",    out_dir / "MLB" / "Playstyles"),
    ]:
        assert sub.exists(), f"{sport_name}: Playstyles/ missing at {sub}"
        assert list(sub.glob("*.md")), f"{sport_name}: Playstyles/ has no .md notes"
    nba_arc = out_dir / "Basketball_NBA" / "Archetypes"
    assert nba_arc.exists(), f"Basketball_NBA: Archetypes/ missing at {nba_arc}"
    assert list(nba_arc.glob("*.md")), "Basketball_NBA: Archetypes/ has no .md notes"
    nba_ps = out_dir / "Basketball_NBA" / "Playstyles"
    assert not nba_ps.exists(), f"Basketball_NBA should NOT have Playstyles/: {nba_ps}"


def test_tournaments_built_for_tennis_only(tmp_path: Path) -> None:
    """Tournaments/ built for tennis; no other sport gets a Tournaments/ directory.

    Tournaments are a NAMED family (person-free default gates them off); this
    capability test runs the opt-in --with-named path.
    """
    out_dir = tmp_path / "Sports"
    with _patch_all_adapters(note_count=2):
        exit_code = main(["--sport", "all", "--out", str(out_dir), "--with-named"])
    assert exit_code == 0
    tennis_trn = out_dir / "Tennis" / "Tournaments"
    assert tennis_trn.exists(), f"Tennis: Tournaments/ missing at {tennis_trn}"
    assert list(tennis_trn.glob("*.md")), "Tennis: Tournaments/ has no .md notes"
    for sport_name in ("Soccer", "MLB", "Basketball_NBA"):
        no_trn = out_dir / sport_name / "Tournaments"
        assert not no_trn.exists(), f"{sport_name} should NOT have Tournaments/: {no_trn}"


def test_seasons_built_for_soccer_mlb_nba(tmp_path: Path) -> None:
    """Seasons/ built for soccer, mlb, and basketball_nba; tennis has no Seasons/.

    Seasons are a NAMED family (person-free default gates them off); this
    capability test runs the opt-in --with-named path.
    """
    out_dir = tmp_path / "Sports"
    with _patch_all_adapters(note_count=2):
        exit_code = main(["--sport", "all", "--out", str(out_dir), "--with-named"])
    assert exit_code == 0
    for sport_name in ("Soccer", "MLB", "Basketball_NBA"):
        sea = out_dir / sport_name / "Seasons"
        assert sea.exists(), f"{sport_name}: Seasons/ missing at {sea}"
        assert list(sea.glob("*.md")), f"{sport_name}: Seasons/ has no .md notes"
    tennis_sea = out_dir / "Tennis" / "Seasons"
    assert not tennis_sea.exists(), f"Tennis should NOT have Seasons/: {tennis_sea}"
