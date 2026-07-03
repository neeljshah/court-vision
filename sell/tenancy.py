"""sell.tenancy -- per-tenant filesystem isolation.

Every tenant gets a private namespace rooted at::

    data/frontend/sell/tenants/<tenant>/

No tenant can read or write into another tenant's namespace. The helpers here
enforce that by normalising the tenant ID (strip, lowercase, allow only safe
chars) and verifying the resolved path stays inside the tenant's own root before
any operation.

INVARIANTS: <=300 LOC; ASCII only; no secrets; no $-edge field; never writes
data/registry/; raises TenancyError on any isolation violation (never silently
leaks cross-tenant).
"""
from __future__ import annotations

import os
import pathlib
import re
from typing import Optional

# --------------------------------------------------------------------------- #
# Root path configuration                                                      #
# --------------------------------------------------------------------------- #

#: Filesystem root that contains all per-tenant state.  Override in tests by
#: patching sell.tenancy.TENANTS_ROOT or by constructing a Namespace directly
#: with an explicit root argument.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TENANTS_ROOT: pathlib.Path = _REPO_ROOT / "data" / "frontend" / "sell" / "tenants"

#: Safe tenant ID: only lowercase alphanum, dash, and underscore; 1-64 chars.
_SAFE_ID_RE = re.compile(r"^[a-z0-9_-]{1,64}$")


class TenancyError(Exception):
    """Raised when an isolation boundary would be crossed."""


# --------------------------------------------------------------------------- #
# Tenant ID normalisation                                                      #
# --------------------------------------------------------------------------- #

def _normalise(tenant: str) -> str:
    """Lowercase, strip, validate. Raises TenancyError if not safe."""
    if not isinstance(tenant, str):
        raise TenancyError("tenant must be a string, got %r" % type(tenant).__name__)
    normed = tenant.strip().lower()
    if not _SAFE_ID_RE.match(normed):
        raise TenancyError(
            "tenant ID %r is not safe (must match [a-z0-9_-]{1,64})" % normed
        )
    return normed


# --------------------------------------------------------------------------- #
# Namespace -- per-tenant path helper                                          #
# --------------------------------------------------------------------------- #

class Namespace:
    """Scoped filesystem namespace for a single tenant.

    All paths returned by this object are guaranteed to be descendants of the
    tenant's root directory. Any attempt to escape (via ../.. or absolute path
    injection) raises TenancyError and no I/O is performed.

    Args:
        tenant: The tenant identifier (normalised on construction).
        root:   Override base directory (defaults to TENANTS_ROOT; for tests).
    """

    def __init__(self, tenant: str, *, root: Optional[pathlib.Path] = None) -> None:
        self._tenant = _normalise(tenant)
        self._base = (root or TENANTS_ROOT) / self._tenant

    @property
    def tenant(self) -> str:
        """The normalised tenant ID."""
        return self._tenant

    @property
    def root(self) -> pathlib.Path:
        """The tenant's private root directory (may not exist yet)."""
        return self._base

    def resolve(self, relative: str) -> pathlib.Path:
        """Resolve *relative* to the tenant root; raise TenancyError if it escapes.

        Args:
            relative: A relative path segment (e.g. "usage.jsonl").

        Returns:
            Absolute pathlib.Path guaranteed to be under this tenant's root.

        Raises:
            TenancyError: if the resolved path is outside the tenant root.
        """
        if not relative or not isinstance(relative, str):
            raise TenancyError("relative path must be a non-empty string")
        candidate = (self._base / relative).resolve()
        # Resolve the tenant base too (it may not exist yet, so use the
        # parent chain -- pathlib.resolve with strict=False is Python 3.6+)
        base_resolved = self._base.resolve() if self._base.exists() else (
            self._base.parent.resolve() / self._base.name
        )
        try:
            candidate.relative_to(base_resolved)
        except ValueError:
            raise TenancyError(
                "path %r escapes tenant root for %r" % (str(candidate), self._tenant)
            )
        return candidate

    def ensure_dir(self, relative: str = "") -> pathlib.Path:
        """Create *relative* subdir (and parents) under the tenant root.

        Args:
            relative: Sub-path to create; empty string -> tenant root itself.

        Returns:
            The created (or already existing) directory path.
        """
        if relative:
            target = self.resolve(relative)
        else:
            target = self._base
        target.mkdir(parents=True, exist_ok=True)
        return target

    def path(self, relative: str) -> pathlib.Path:
        """Return an isolation-checked path without creating it.

        Alias for :meth:`resolve` for callers that only need the path.
        """
        return self.resolve(relative)


# --------------------------------------------------------------------------- #
# Module-level convenience                                                     #
# --------------------------------------------------------------------------- #

def namespace_for(tenant: str, *, root: Optional[pathlib.Path] = None) -> Namespace:
    """Return a :class:`Namespace` for *tenant* (validates and normalises ID).

    This is the primary entry point: ``namespace_for("acme")`` gives a scoped
    filesystem handle that tenant A can never use to reach tenant B's data.
    """
    return Namespace(tenant, root=root)


def tenant_root(tenant: str, *, root: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Return the root directory for *tenant* (path not guaranteed to exist).

    Shorthand for ``namespace_for(tenant).root``.
    """
    return namespace_for(tenant, root=root).root


__all__ = [
    "TENANTS_ROOT",
    "TenancyError",
    "Namespace",
    "namespace_for",
    "tenant_root",
]
