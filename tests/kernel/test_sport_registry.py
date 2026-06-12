"""Tests for kernel.config.context.SportContext and kernel.config.registry.

Hermetic, offline.  No heavy imports (stdlib + typing + dataclasses + importlib
only — no numpy, pandas, torch, nba_api).

Test matrix
-----------
1. Build a minimal toy SportContext, register_sport it, get_sport(its id)
   returns it; register is idempotent.
2. load_sport works on a TEMP toy domain package: create a tmp dir with
   <toy>/config.py defining SPORT_CONTEXT, put it on sys.path, call
   load_sport("<toy>"), assert it returns the context.  Cleans up
   sys.path + sys.modules afterward.
3. get_sport() with no arg uses DEFAULT_SPORT_ID / env variable:
   - env override path (COURTVISION_SPORT set to registered sport)
   - unknown default raises cleanly
4. Unknown sport_id raises a clear error (not a bare ImportError).
5. Grep assertion: no file under kernel/ contains a literal
   ``import domains`` or ``from domains`` — proves R10 compliance.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional

import pytest

# ---------------------------------------------------------------------------
# Units under test
# ---------------------------------------------------------------------------

from kernel.config.atlas_schema import AtlasSchema
from kernel.config.clock import GameClockConfig
from kernel.config.context import SportContext
from kernel.config.entities import EntityRegistry
from kernel.config.game_state import GameStateConfig
from kernel.config.pbp import CanonicalEvent, LeagueClient, PBPEventMapper
from kernel.config.registry import (
    DEFAULT_SPORT_ID,
    _REGISTRY,
    get_sport,
    list_sports,
    load_sport,
    register_sport,
    unregister_sport,
)
from kernel.config.roster import PositionSchema, RosterConfig
from kernel.config.stats import SportStatRegistry, StatSpec


# ===========================================================================
# Helpers — minimal stub implementations of the kernel protocols
# ===========================================================================

class _StubPBPMapper:
    """Minimal PBPEventMapper stub that satisfies the runtime_checkable protocol."""

    def to_canonical(self, raw_event: Any) -> CanonicalEvent:
        raise NotImplementedError

    def iter_game(self, game_id: str) -> Iterator[CanonicalEvent]:
        return iter([])

    def possession_side(self, event: CanonicalEvent) -> Optional[str]:
        return None


class _StubLeagueClient:
    """Minimal LeagueClient stub that satisfies the runtime_checkable protocol."""

    def get_schedule(self, season: str) -> Any:
        return []

    def get_box_score(self, game_id: str) -> Any:
        return {}

    def get_pbp(self, game_id: str) -> Any:
        return []

    def get_roster(self, team_id: str, season: str) -> Any:
        return []

    def get_player_gamelog(self, player_id: str, season: str) -> Any:
        return []

    def get_availability(self, player_id: str, game_id: str) -> Any:
        return None


class _StubEntityRegistry:
    """Minimal EntityRegistry stub that satisfies the runtime_checkable protocol."""

    sport_id: str = "toyball"

    def resolve_team(self, token: str) -> str:
        raise KeyError(token)

    def resolve_player(self, token: Any) -> str:
        raise KeyError(token)

    def parse_game_id(self, game_id: str) -> dict:
        return {"season": "2025", "kind": "regular", "seq": 0}

    def season_of(self, d: Any) -> str:
        return "2025"

    def entity_key(self, kind: str, ident: Any) -> str:
        return f"{kind}:{ident}"

    def book_aliases(self) -> Mapping[str, str]:
        return {}


def _make_toyball_stat_registry(sport_id: str = "toyball") -> SportStatRegistry:
    """Build a minimal SportStatRegistry for the toy sport."""
    return SportStatRegistry(
        sport_id=sport_id,
        stats={
            "score_units": StatSpec(
                name="score_units",
                kind="count",
                display="Score Units",
                sigma_default=2.5,
            ),
            "grabs": StatSpec(
                name="grabs",
                kind="count",
                display="Grabs",
                sigma_default=1.0,
            ),
        },
        box_score_mapping={"SCORE": "score_units", "GRABS": "grabs"},
        score_stat="score_units",
        minutes_equiv=None,
    )


def _make_toyball_context(sport_id: str = "toyball") -> SportContext:
    """Construct a minimal SportContext for the toy sport.

    Uses ``frozen=True`` dataclass fields only — no heavy deps.
    """
    stats = _make_toyball_stat_registry(sport_id)
    clock = GameClockConfig(n_periods=2, period_len_sec=600, ot_len_sec=300)
    roster = RosterConfig(
        on_field_count=3,
        roster_size=6,
        season_length_games=20,
        positions=PositionSchema(positions=("F", "M", "D")),
    )
    game_state = GameStateConfig(
        blowout_margin=10.0,
        clutch_margin=3.0,
        clutch_remaining_sec=120.0,
        garbage_margin=15.0,
        competitive_margin=8.0,
        final_margin_sigma=5.0,
        winprob_promotion_period=2,
    )
    atlas = AtlasSchema(sport_id=sport_id)

    return SportContext(
        stats=stats,
        clock=clock,
        roster=roster,
        game_state=game_state,
        pbp_mapper=_StubPBPMapper(),  # type: ignore[arg-type]
        league_client=_StubLeagueClient(),  # type: ignore[arg-type]
        entities=_StubEntityRegistry(),  # type: ignore[arg-type]
        source_tiers={"test_feed": 1},
        atlas_schema=atlas,
    )


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    """Ensure each test starts with a clean registry for the toy sport_ids.

    We do NOT wipe the entire registry (other tests or imports might have
    registered real sports), but we remove any toy entries we create so
    tests are isolated.
    """
    toy_ids = {"toyball", "toyball_alt", "loaded_toy"}
    yield
    for sid in toy_ids:
        unregister_sport(sid)


# ===========================================================================
# Test 1: register_sport, get_sport, idempotency
# ===========================================================================

class TestRegisterAndGetSport:
    """register_sport + get_sport round-trip."""

    def test_register_and_retrieve(self) -> None:
        ctx = _make_toyball_context("toyball")
        register_sport(ctx)
        retrieved = get_sport("toyball")
        assert retrieved is ctx

    def test_register_is_idempotent(self) -> None:
        """Calling register_sport twice for the same id is a no-op."""
        ctx1 = _make_toyball_context("toyball")
        ctx2 = _make_toyball_context("toyball")
        # ctx1 and ctx2 are equal by value but different objects
        register_sport(ctx1)
        register_sport(ctx2)  # second call must not overwrite
        assert get_sport("toyball") is ctx1
        assert get_sport("toyball") is not ctx2

    def test_list_sports_includes_registered(self) -> None:
        ctx = _make_toyball_context("toyball")
        register_sport(ctx)
        assert "toyball" in list_sports()

    def test_sport_id_property(self) -> None:
        ctx = _make_toyball_context("toyball")
        assert ctx.sport_id == "toyball"

    def test_artifact_dir_path(self) -> None:
        ctx = _make_toyball_context("toyball")
        assert ctx.artifact_dir == Path("data") / "toyball"

    def test_capability_flags_defaults(self) -> None:
        ctx = _make_toyball_context("toyball")
        # Optional fields default to None → capability flags False
        assert not ctx.has_court()
        assert not ctx.has_speed()
        assert not ctx.has_dataset_builder()
        assert not ctx.has_trainer_hook()

    def test_context_is_frozen(self) -> None:
        """SportContext must be frozen — no field re-assignment allowed."""
        import dataclasses
        ctx = _make_toyball_context("toyball")
        with pytest.raises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            ctx.atlas_schema = AtlasSchema(sport_id="x")  # type: ignore[misc]


# ===========================================================================
# Test 2: load_sport via a TEMP toy domain package
# ===========================================================================

class TestLoadSport:
    """load_sport discovers SPORT_CONTEXT from a dynamic domain package."""

    def test_load_sport_from_tmp_package(self, tmp_path: Path) -> None:
        """load_sport finds SPORT_CONTEXT in a temp package on sys.path.

        We temporarily evict the real ``domains`` package from sys.modules so
        importlib re-discovers the one under tmp_path first.  Everything is
        restored in the finally block regardless of outcome.
        """
        sport_id = "loaded_toy"

        # Create domains/loaded_toy/__init__.py and config.py under tmp_path
        domains_dir = tmp_path / "domains"
        pkg_dir = domains_dir / sport_id
        pkg_dir.mkdir(parents=True)
        (domains_dir / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

        # Write config.py that builds a SportContext using only kernel imports
        config_code = textwrap.dedent(f"""\
            from __future__ import annotations
            from kernel.config.context import SportContext
            from kernel.config.atlas_schema import AtlasSchema
            from kernel.config.clock import GameClockConfig
            from kernel.config.game_state import GameStateConfig
            from kernel.config.roster import PositionSchema, RosterConfig
            from kernel.config.stats import SportStatRegistry, StatSpec

            class _PBP:
                def to_canonical(self, e): raise NotImplementedError
                def iter_game(self, g): return iter([])
                def possession_side(self, e): return None

            class _LC:
                def get_schedule(self, s): return []
                def get_box_score(self, g): return {{}}
                def get_pbp(self, g): return []
                def get_roster(self, t, s): return []
                def get_player_gamelog(self, p, s): return []
                def get_availability(self, p, g): return None

            class _ER:
                sport_id = {sport_id!r}
                def resolve_team(self, t): raise KeyError(t)
                def resolve_player(self, t): raise KeyError(t)
                def parse_game_id(self, g): return {{"season": "2025", "kind": "regular", "seq": 0}}
                def season_of(self, d): return "2025"
                def entity_key(self, k, i): return f"{{k}}:{{i}}"
                def book_aliases(self): return {{}}

            SPORT_CONTEXT = SportContext(
                stats=SportStatRegistry(
                    sport_id={sport_id!r},
                    stats={{
                        "score_units": StatSpec(
                            name="score_units", kind="count",
                            display="Score Units", sigma_default=2.5,
                        ),
                    }},
                    box_score_mapping={{"SCORE": "score_units"}},
                    score_stat="score_units",
                    minutes_equiv=None,
                ),
                clock=GameClockConfig(n_periods=2, period_len_sec=600, ot_len_sec=300),
                roster=RosterConfig(
                    on_field_count=3, roster_size=6, season_length_games=20,
                    positions=PositionSchema(positions=("F", "M", "D")),
                ),
                game_state=GameStateConfig(
                    blowout_margin=10.0, clutch_margin=3.0,
                    clutch_remaining_sec=120.0, garbage_margin=15.0,
                    competitive_margin=8.0, final_margin_sigma=5.0,
                    winprob_promotion_period=2,
                ),
                pbp_mapper=_PBP(),
                league_client=_LC(),
                entities=_ER(),
                source_tiers={{"test_feed": 1}},
                atlas_schema=AtlasSchema(sport_id={sport_id!r}),
            )
        """)
        (pkg_dir / "config.py").write_text(config_code, encoding="utf-8")

        # Snapshot the real domains modules so we can restore them after the test.
        saved_domains_modules: Dict[str, Any] = {
            k: v for k, v in sys.modules.items()
            if k == "domains" or k.startswith("domains.")
        }

        # Inject tmp_path at the front of sys.path and clear real domains cache
        # so importlib discovers the tmp package first.
        sys.path.insert(0, str(tmp_path))
        for key in list(saved_domains_modules.keys()):
            sys.modules.pop(key, None)

        ctx: Optional[SportContext] = None
        try:
            ctx = load_sport(sport_id)
        finally:
            # Restore sys.path
            try:
                sys.path.remove(str(tmp_path))
            except ValueError:
                pass
            # Evict any toy-domain modules we loaded
            for key in list(sys.modules.keys()):
                if key == "domains" or key.startswith("domains."):
                    del sys.modules[key]
            # Restore original domains modules
            sys.modules.update(saved_domains_modules)
            unregister_sport(sport_id)

        assert ctx is not None
        assert isinstance(ctx, SportContext)
        assert ctx.sport_id == sport_id

    def test_load_sport_unknown_module_raises_value_error(self) -> None:
        """An unknown sport_id raises ValueError (not a bare ImportError)."""
        with pytest.raises(ValueError, match="Cannot import domain package"):
            load_sport("__nonexistent_sport_xyz__")

    def test_load_sport_missing_sport_context_attr_raises_key_error(
        self, tmp_path: Path
    ) -> None:
        """A module that exists but lacks SPORT_CONTEXT raises KeyError.

        The test creates a toy domain package, inserts it onto sys.path, and
        temporarily evicts the existing ``domains`` package from sys.modules
        so importlib re-discovers the one under tmp_path first.  Everything is
        restored in the finally block.
        """
        sport_id = "loaded_toy"
        domains_dir = tmp_path / "domains"
        pkg_dir = domains_dir / sport_id
        pkg_dir.mkdir(parents=True)
        (domains_dir / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
        # config.py deliberately has no SPORT_CONTEXT
        (pkg_dir / "config.py").write_text("# intentionally empty\n", encoding="utf-8")

        # Snapshot sys.modules keys that begin with "domains" so we can
        # restore them after the test.
        saved_domains_modules: Dict[str, Any] = {
            k: v for k, v in sys.modules.items() if k == "domains" or k.startswith("domains.")
        }

        sys.path.insert(0, str(tmp_path))
        # Evict the real domains package so importlib sees our tmp one first.
        for key in list(saved_domains_modules.keys()):
            sys.modules.pop(key, None)

        try:
            with pytest.raises(KeyError, match="SPORT_CONTEXT"):
                load_sport(sport_id)
        finally:
            # Remove tmp_path from sys.path
            try:
                sys.path.remove(str(tmp_path))
            except ValueError:
                pass
            # Evict any toy-domain modules we loaded
            for key in list(sys.modules.keys()):
                if key == "domains" or key.startswith("domains."):
                    del sys.modules[key]
            # Restore original domains modules
            sys.modules.update(saved_domains_modules)
            unregister_sport(sport_id)


# ===========================================================================
# Test 3: get_sport() default resolution — env override + unknown default
# ===========================================================================

class TestGetSportDefaults:
    """get_sport() without argument resolves via env / DEFAULT_SPORT_ID."""

    def test_env_override_resolves_registered_sport(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """COURTVISION_SPORT env variable is respected by get_sport()."""
        ctx = _make_toyball_context("toyball")
        register_sport(ctx)
        monkeypatch.setenv("COURTVISION_SPORT", "toyball")
        retrieved = get_sport()
        assert retrieved is ctx

    def test_env_override_unknown_sport_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """COURTVISION_SPORT pointing to an unregistered sport raises KeyError."""
        monkeypatch.setenv("COURTVISION_SPORT", "__not_a_real_sport__")
        with pytest.raises(KeyError):
            get_sport()

    def test_no_env_unknown_default_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When DEFAULT_SPORT_ID is not registered, get_sport() raises KeyError."""
        # Ensure the env var is absent so we fall through to DEFAULT_SPORT_ID
        monkeypatch.delenv("COURTVISION_SPORT", raising=False)
        # Ensure DEFAULT_SPORT_ID ("basketball_nba") is NOT in the registry
        # (it may or may not be registered; remove it for this test then restore)
        had_default = DEFAULT_SPORT_ID in _REGISTRY
        saved_ctx = _REGISTRY.get(DEFAULT_SPORT_ID)
        unregister_sport(DEFAULT_SPORT_ID)
        try:
            with pytest.raises(KeyError, match=DEFAULT_SPORT_ID):
                get_sport()
        finally:
            if had_default and saved_ctx is not None:
                register_sport(saved_ctx)

    def test_explicit_none_falls_through_to_default_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Passing sport_id=None is the same as calling get_sport() with no arg."""
        monkeypatch.delenv("COURTVISION_SPORT", raising=False)
        had_default = DEFAULT_SPORT_ID in _REGISTRY
        saved_ctx = _REGISTRY.get(DEFAULT_SPORT_ID)
        unregister_sport(DEFAULT_SPORT_ID)
        try:
            with pytest.raises(KeyError):
                get_sport(sport_id=None)
        finally:
            if had_default and saved_ctx is not None:
                register_sport(saved_ctx)


# ===========================================================================
# Test 4: unknown sport_id raises a clear, descriptive error
# ===========================================================================

class TestUnknownSportErrors:
    """Requesting an unregistered sport raises clearly, not with a bare ImportError."""

    def test_get_sport_unknown_raises_key_error_with_message(self) -> None:
        with pytest.raises(KeyError) as exc_info:
            get_sport("__totally_unknown__")
        # The error message should name the sport_id
        assert "__totally_unknown__" in str(exc_info.value)

    def test_get_sport_error_lists_registered_sports(self) -> None:
        """The KeyError message should list registered sports for diagnostics."""
        ctx = _make_toyball_context("toyball")
        register_sport(ctx)
        with pytest.raises(KeyError) as exc_info:
            get_sport("__unknown_sport__")
        msg = str(exc_info.value)
        # The error message is inside the KeyError repr (wrapped in quotes)
        assert "Registered sports" in msg or "toyball" in msg

    def test_load_sport_unknown_is_value_error_not_import_error(self) -> None:
        """load_sport wraps ImportError as ValueError — callers get a clear message."""
        with pytest.raises(ValueError) as exc_info:
            load_sport("__no_such_sport_package__")
        # Must NOT be a bare ImportError
        assert exc_info.type is ValueError
        assert "__no_such_sport_package__" in str(exc_info.value)


# ===========================================================================
# Test 5: R10 compliance grep — kernel/ contains NO literal 'import domains'
#         or 'from domains' statement
# ===========================================================================

class TestR10ImportCompliance:
    """Prove the kernel never imports domains.* by a literal statement."""

    # Pattern that matches literal import statements of domains (not strings)
    # We allow the pattern inside comments and strings (docstrings, test code),
    # but it MUST NOT appear as actual Python import syntax in kernel/*.py.
    #
    # The regex matches:
    #   import domains           (bare import)
    #   from domains             (from-import)
    #   import domains.anything  (submodule)
    #   from domains.anything    (submodule from-import)
    #
    # It deliberately does NOT match:
    #   "import domains"        (string literal in a docstring / test)
    #   # import domains        (comment)
    #   importlib.import_module("domains.xxx")  (string-driven, R10-compliant)
    _IMPORT_PATTERN: re.Pattern = re.compile(
        r"^(?:from|import)\s+domains\b", re.MULTILINE
    )

    def _kernel_python_files(self) -> list[Path]:
        """Return all .py files under kernel/ in the repository."""
        repo_root = Path(__file__).parents[2]
        kernel_dir = repo_root / "kernel"
        assert kernel_dir.is_dir(), (
            f"kernel/ directory not found at {kernel_dir}; "
            "run this test from the repository root."
        )
        return list(kernel_dir.rglob("*.py"))

    def test_no_literal_import_domains_in_kernel(self) -> None:
        """No kernel .py file may contain a literal 'import domains' or
        'from domains' statement (R10 compliance)."""
        offending: list[str] = []
        for py_file in self._kernel_python_files():
            source = py_file.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(source.splitlines(), start=1):
                stripped = line.lstrip()
                # Skip comment lines
                if stripped.startswith("#"):
                    continue
                if self._IMPORT_PATTERN.match(stripped):
                    offending.append(f"{py_file}:{lineno}: {line.rstrip()}")

        assert not offending, (
            "R10 VIOLATION — kernel files contain literal 'import domains' / "
            "'from domains' statements (the kernel must NEVER import domains "
            "by literal name — use importlib.import_module with a string):\n"
            + "\n".join(offending)
        )

    def test_kernel_files_found(self) -> None:
        """Sanity check: ensure we found at least a few kernel .py files."""
        files = self._kernel_python_files()
        assert len(files) >= 5, (
            f"Expected to find ≥5 kernel .py files, found {len(files)}. "
            "Check the repository structure."
        )
