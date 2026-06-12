"""Tests for kernel.config.stats — StatSpec + SportStatRegistry.

Hermetic, offline.  No heavy imports (stdlib + typing + dataclasses only).
Covers:
  1. StatSpec is frozen (FrozenInstanceError on attribute set).
  2. StatSpec.__post_init__ rejects unknown kind.
  3. SportStatRegistry is frozen.
  4. target_names() preserves insertion order.
  5. priced_order() filters correctly and preserves order.
  6. spec() returns the correct StatSpec / raises on unknown name.
  7. loop_targets == the exact 12-tuple from src/loop/signal.py:29-30
     (element-by-element equality AND order).
"""
from __future__ import annotations

import dataclasses

import pytest

from kernel.config.stats import SportStatRegistry, StatSpec

# ---------------------------------------------------------------------------
# Helpers — build the canonical NBA-shaped registry from literals
# ---------------------------------------------------------------------------

_NBA_STATS_DEF: list[tuple[str, str, str, float, bool, bool, tuple[str, ...]]] = [
    # (name, kind, display, sigma_default, priced, higher_is_better, correlated_with)
    ("pts",  "count",      "Points",          6.0, True,  True,  ("reb", "ast")),
    ("reb",  "count",      "Rebounds",        3.0, True,  True,  ("pts",)),
    ("ast",  "count",      "Assists",         2.5, True,  True,  ("pts",)),
    ("fg3m", "count",      "3-Pointers Made", 1.5, True,  True,  ()),
    ("stl",  "count",      "Steals",          0.8, True,  True,  ()),
    ("blk",  "count",      "Blocks",          0.7, True,  True,  ()),
    ("tov",  "count",      "Turnovers",       1.2, True,  False, ()),
]

_NBA_BOX_MAPPING: dict[str, str] = {
    "PTS": "pts", "REB": "reb", "AST": "ast",
    "FG3M": "fg3m", "STL": "stl", "BLK": "blk", "TOV": "tov",
}


def _make_nba_registry() -> SportStatRegistry:
    """Build a minimal NBA-shaped SportStatRegistry from literals."""
    stats: dict[str, StatSpec] = {}
    for name, kind, display, sigma, priced, hib, corr in _NBA_STATS_DEF:
        stats[name] = StatSpec(
            name=name,
            kind=kind,
            display=display,
            sigma_default=sigma,
            priced=priced,
            higher_is_better=hib,
            correlated_with=corr,
        )
    return SportStatRegistry(
        sport_id="nba",
        stats=stats,
        box_score_mapping=_NBA_BOX_MAPPING,
        score_stat="pts",
        minutes_equiv="minutes",
    )


# ---------------------------------------------------------------------------
# The authoritative 12-tuple from src/loop/signal.py:29-30
# ---------------------------------------------------------------------------

_EXPECTED_LOOP_TARGETS: tuple[str, ...] = (
    "pts", "reb", "ast", "fg3m", "stl", "blk", "tov",
    "minutes", "total", "winprob", "usage", "sigma",
)


# ===========================================================================
# 1. StatSpec — frozen
# ===========================================================================

class TestStatSpecFrozen:
    def test_frozen_raises_on_set(self) -> None:
        """Setting any attribute on a StatSpec must raise FrozenInstanceError."""
        spec = StatSpec(
            name="pts", kind="count", display="Points", sigma_default=6.0
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.name = "reb"  # type: ignore[misc]

    def test_frozen_raises_on_new_attr(self) -> None:
        """Assigning a brand-new attribute must also raise (frozen dataclass)."""
        spec = StatSpec(
            name="pts", kind="count", display="Points", sigma_default=6.0
        )
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            spec.custom = "x"  # type: ignore[attr-defined]


# ===========================================================================
# 2. StatSpec — kind validation
# ===========================================================================

class TestStatSpecKindValidation:
    @pytest.mark.parametrize("kind", ["count", "continuous", "binary", "interval"])
    def test_valid_kinds_accepted(self, kind: str) -> None:
        spec = StatSpec(name="x", kind=kind, display="X", sigma_default=1.0)  # type: ignore[arg-type]
        assert spec.kind == kind

    @pytest.mark.parametrize("bad_kind", ["ratio", "categorical", "COUNT", "", "Count"])
    def test_invalid_kind_raises(self, bad_kind: str) -> None:
        with pytest.raises(ValueError, match="kind must be one of"):
            StatSpec(name="x", kind=bad_kind, display="X", sigma_default=1.0)  # type: ignore[arg-type]


# ===========================================================================
# 3. SportStatRegistry — frozen
# ===========================================================================

class TestSportStatRegistryFrozen:
    def test_frozen_raises_on_set(self) -> None:
        """Setting any attribute on SportStatRegistry must raise FrozenInstanceError."""
        reg = _make_nba_registry()
        with pytest.raises(dataclasses.FrozenInstanceError):
            reg.sport_id = "nfl"  # type: ignore[misc]

    def test_frozen_stats_dict_is_not_reassignable(self) -> None:
        reg = _make_nba_registry()
        with pytest.raises(dataclasses.FrozenInstanceError):
            reg.stats = {}  # type: ignore[misc]


# ===========================================================================
# 4. target_names() — insertion order preserved
# ===========================================================================

class TestTargetNames:
    def test_returns_tuple(self) -> None:
        reg = _make_nba_registry()
        assert isinstance(reg.target_names(), tuple)

    def test_length(self) -> None:
        reg = _make_nba_registry()
        assert len(reg.target_names()) == 7

    def test_insertion_order(self) -> None:
        """target_names() must match the insertion order of the stats dict."""
        reg = _make_nba_registry()
        expected = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
        assert reg.target_names() == expected

    def test_element_by_element(self) -> None:
        reg = _make_nba_registry()
        names = reg.target_names()
        expected = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
        for i, (got, want) in enumerate(zip(names, expected)):
            assert got == want, f"Position {i}: expected {want!r}, got {got!r}"


# ===========================================================================
# 5. priced_order() — filters and preserves order
# ===========================================================================

class TestPricedOrder:
    def test_all_nba_stats_priced(self) -> None:
        """All 7 NBA stats have priced=True so priced_order() equals target_names()."""
        reg = _make_nba_registry()
        assert reg.priced_order() == reg.target_names()

    def test_unpriced_stat_excluded(self) -> None:
        """A stat with priced=False must not appear in priced_order()."""
        stats = {
            "pts": StatSpec(name="pts", kind="count", display="Points", sigma_default=6.0, priced=True),
            "hidden": StatSpec(name="hidden", kind="binary", display="Hidden", sigma_default=0.5, priced=False),
            "ast": StatSpec(name="ast", kind="count", display="Assists", sigma_default=2.5, priced=True),
        }
        reg = SportStatRegistry(
            sport_id="test",
            stats=stats,
            box_score_mapping={},
            score_stat="pts",
        )
        assert reg.priced_order() == ("pts", "ast")
        assert "hidden" not in reg.priced_order()

    def test_priced_order_returns_tuple(self) -> None:
        reg = _make_nba_registry()
        assert isinstance(reg.priced_order(), tuple)


# ===========================================================================
# 6. spec() — lookup by name
# ===========================================================================

class TestSpec:
    def test_spec_returns_correct_stat(self) -> None:
        reg = _make_nba_registry()
        pts = reg.spec("pts")
        assert pts.name == "pts"
        assert pts.kind == "count"
        assert pts.sigma_default == 6.0

    def test_spec_unknown_raises_key_error(self) -> None:
        reg = _make_nba_registry()
        with pytest.raises(KeyError):
            reg.spec("passing_yards")

    @pytest.mark.parametrize("name", ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"])
    def test_spec_roundtrip_all_nba(self, name: str) -> None:
        """spec(name).name must equal name for every registered NBA stat."""
        reg = _make_nba_registry()
        assert reg.spec(name).name == name


# ===========================================================================
# 7. loop_targets — exact 12-tuple, element-by-element equality AND order
# ===========================================================================

class TestLoopTargets:
    def test_returns_tuple(self) -> None:
        reg = _make_nba_registry()
        assert isinstance(reg.loop_targets, tuple)

    def test_length(self) -> None:
        reg = _make_nba_registry()
        assert len(reg.loop_targets) == 12, (
            f"Expected 12 targets (7 stats + 5 meta), got {len(reg.loop_targets)}"
        )

    def test_exact_equality(self) -> None:
        """loop_targets must be byte-identical to TARGETS in src/loop/signal.py:29-30."""
        reg = _make_nba_registry()
        assert reg.loop_targets == _EXPECTED_LOOP_TARGETS, (
            f"loop_targets mismatch:\n"
            f"  got:      {reg.loop_targets}\n"
            f"  expected: {_EXPECTED_LOOP_TARGETS}"
        )

    def test_element_by_element(self) -> None:
        """Assert each position individually for clear failure messages."""
        reg = _make_nba_registry()
        got = reg.loop_targets
        assert len(got) == len(_EXPECTED_LOOP_TARGETS), (
            f"Length mismatch: got {len(got)}, expected {len(_EXPECTED_LOOP_TARGETS)}"
        )
        for i, (g, e) in enumerate(zip(got, _EXPECTED_LOOP_TARGETS)):
            assert g == e, (
                f"loop_targets[{i}]: expected {e!r}, got {g!r}\n"
                f"  full got:      {got}\n"
                f"  full expected: {_EXPECTED_LOOP_TARGETS}"
            )

    def test_stat_portion_matches_target_names(self) -> None:
        """The stat portion of loop_targets must equal target_names()."""
        reg = _make_nba_registry()
        n = len(reg.target_names())
        assert reg.loop_targets[:n] == reg.target_names()

    def test_meta_portion_is_fixed(self) -> None:
        """The meta-target tail must be the fixed 5-tuple regardless of stat count."""
        reg = _make_nba_registry()
        n = len(reg.target_names())
        assert reg.loop_targets[n:] == ("minutes", "total", "winprob", "usage", "sigma")

    def test_loop_targets_not_modifiable(self) -> None:
        """loop_targets returns an immutable tuple — tuple assignment must fail."""
        reg = _make_nba_registry()
        targets = reg.loop_targets
        with pytest.raises(TypeError):
            targets[0] = "other"  # type: ignore[index]
