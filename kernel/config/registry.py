"""kernel.config.registry — sport registry + load_sport.

Process-global registry of ``SportContext`` instances, keyed by sport_id.
The kernel discovers domain packages by STRING sport-id only — it NEVER
contains a literal ``import domains`` or ``from domains`` statement.

Dependency rule (R10)
---------------------
``load_sport`` resolves ``domains.<sport_id>.config`` entirely through
``importlib.import_module`` with a string argument.  This preserves the
import-contract guard: a grep for ``import domains`` or ``from domains``
inside ``kernel/`` should return zero hits.

The test suite enforces this property with a grep assertion over all files
under ``kernel/``.

Reconciliation note (package naming)
-------------------------------------
``load_sport("basketball_nba")`` calls
``importlib.import_module("domains.basketball_nba.config")``.  The current
NBA skeleton lives at ``domains/nba/``.  P0-D-017 (NBA registration) must
settle whether to rename the package or alias the sport_id.  P0-D-010
(this file) only ships the generic mechanism; tests use a toy domain to
avoid the naming conflict entirely.

Default sport
-------------
The module-level constant ``DEFAULT_SPORT_ID`` is used by ``get_sport()``
when no ``sport_id`` argument is supplied and the ``COURTVISION_SPORT``
environment variable is not set.
"""
from __future__ import annotations

import importlib
import os
from typing import Dict, Optional

from kernel.config.context import SportContext

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Fallback sport_id used by ``get_sport()`` when neither the caller nor the
#: ``COURTVISION_SPORT`` environment variable specifies one.
DEFAULT_SPORT_ID: str = "basketball_nba"

# ---------------------------------------------------------------------------
# Internal registry store (module-level, not a singleton class)
# ---------------------------------------------------------------------------

# Sport-id → SportContext mapping.  Populated by ``register_sport`` and
# ``load_sport``; read by ``get_sport`` and ``list_sports``.
_REGISTRY: Dict[str, SportContext] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register_sport(ctx: SportContext) -> None:
    """Register a ``SportContext`` instance, keyed by ``ctx.sport_id``.

    Idempotent: calling ``register_sport`` for an already-registered
    sport_id is a no-op.  This allows adapters to call it at import time
    without raising on duplicate registrations (e.g. in tests that re-import
    an adapter module).

    Parameters
    ----------
    ctx : SportContext
        The fully-constructed sport context to register.

    Returns
    -------
    None
    """
    _REGISTRY.setdefault(ctx.sport_id, ctx)


def get_sport(sport_id: Optional[str] = None) -> SportContext:
    """Look up a registered ``SportContext`` by sport_id.

    Resolution order for ``sport_id``:

    1. The explicit ``sport_id`` argument (if provided and not ``None``).
    2. The ``COURTVISION_SPORT`` environment variable.
    3. The module constant ``DEFAULT_SPORT_ID`` (``"basketball_nba"``).

    Parameters
    ----------
    sport_id : str | None, optional
        Canonical sport identifier, e.g. ``"basketball_nba"``, ``"nfl"``.
        When ``None`` the environment variable / default are used.

    Returns
    -------
    SportContext
        The registered context for the resolved sport_id.

    Raises
    ------
    KeyError
        If the resolved sport_id has not been registered via
        ``register_sport`` or ``load_sport``.  The error message names
        the sport_id and lists the registered ids for diagnostics.
    """
    resolved = _resolve_sport_id(sport_id)
    if resolved not in _REGISTRY:
        registered = sorted(_REGISTRY.keys())
        raise KeyError(
            f"Sport {resolved!r} is not registered.  "
            f"Registered sports: {registered}.  "
            f"Call register_sport(ctx) or load_sport({resolved!r}) first."
        )
    return _REGISTRY[resolved]


def load_sport(sport_id: str) -> SportContext:
    """Discover, import, and register a domain package by string sport_id.

    Uses ``importlib.import_module(f"domains.{sport_id}.config")`` to
    locate the domain package.  The module must expose a module-level
    attribute ``SPORT_CONTEXT`` that is a ``SportContext`` instance.

    If the domain package is already imported (i.e. ``sys.modules`` already
    contains the module key), ``importlib.import_module`` returns the cached
    module, making repeated calls fast.

    The returned context is also registered via ``register_sport``, so
    subsequent ``get_sport(sport_id)`` calls succeed without re-importing.

    **Kernel R10 compliance:** this function uses a STRING argument to
    ``importlib.import_module`` — there is NO literal ``import domains`` or
    ``from domains`` statement anywhere in this file or in
    ``kernel/config/context.py``.

    Parameters
    ----------
    sport_id : str
        Canonical sport identifier.  The domain package must be importable
        as ``domains.<sport_id>.config`` and must define ``SPORT_CONTEXT``.
        Example: ``"basketball_nba"`` resolves to
        ``domains.basketball_nba.config.SPORT_CONTEXT``.

    Returns
    -------
    SportContext
        The loaded and registered context.

    Raises
    ------
    KeyError
        If the ``domains.<sport_id>.config`` module does not expose a
        ``SPORT_CONTEXT`` attribute.
    ValueError
        If the domain package cannot be imported (module not found, syntax
        error, etc.) or if ``SPORT_CONTEXT`` is not a ``SportContext``
        instance.

    Notes
    -----
    The kernel never embeds the NBA package path directly.  Callers must
    use the string sport_id mechanism.

    Correct (R10 compliant)::

        ctx = load_sport("basketball_nba")

    Wrong — literal domain imports are forbidden in kernel code.
    Do not write ``from domains.X import Y`` or ``import domains.X``
    anywhere in the kernel/ package.

    The R10 guard (``tests/kernel/test_sport_registry.py``) asserts that no
    file under ``kernel/`` contains a literal Python ``from domains`` or
    ``import domains`` statement.  Strings and docstrings that merely
    *mention* the pattern are intentionally excluded by the guard (it skips
    comment lines; the guard does not parse string literals but the examples
    above use backtick inline-code formatting which does not start with the
    Python keywords ``from``/``import``).
    """
    module_path = f"domains.{sport_id}.config"
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ValueError(
            f"Cannot import domain package {module_path!r} for sport_id "
            f"{sport_id!r}.  Ensure 'domains/{sport_id}/__init__.py' and "
            f"'domains/{sport_id}/config.py' exist and are importable.  "
            f"Original error: {exc}"
        ) from exc

    try:
        ctx = module.SPORT_CONTEXT
    except AttributeError as exc:
        raise KeyError(
            f"Domain package {module_path!r} does not define a "
            f"'SPORT_CONTEXT' attribute.  Add "
            f"'SPORT_CONTEXT: SportContext = SportContext(...)' "
            f"to domains/{sport_id}/config.py."
        ) from exc

    if not isinstance(ctx, SportContext):
        raise ValueError(
            f"domains.{sport_id}.config.SPORT_CONTEXT must be a "
            f"SportContext instance, got {type(ctx)!r}."
        )

    register_sport(ctx)
    return ctx


def list_sports() -> tuple[str, ...]:
    """Return a sorted tuple of all currently registered sport_ids.

    Returns
    -------
    tuple[str, ...]
        Sorted sport identifiers.
    """
    return tuple(sorted(_REGISTRY.keys()))


def unregister_sport(sport_id: str) -> None:
    """Remove a sport from the registry.

    Intended for use in tests only — production code should never
    unregister a sport after startup.

    Parameters
    ----------
    sport_id : str
        The sport_id to remove.  A no-op if the sport is not registered.
    """
    _REGISTRY.pop(sport_id, None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_sport_id(sport_id: Optional[str]) -> str:
    """Resolve the effective sport_id from argument → env → default.

    Parameters
    ----------
    sport_id : str | None
        Explicit argument; ``None`` triggers env / default resolution.

    Returns
    -------
    str
        The resolved non-empty sport_id string.
    """
    if sport_id is not None:
        return sport_id
    env_sport = os.environ.get("COURTVISION_SPORT", "").strip()
    if env_sport:
        return env_sport
    return DEFAULT_SPORT_ID
