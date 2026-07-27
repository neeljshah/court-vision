"""supervisor.config -- load boot profiles from config/boot/*.json.

A boot profile is a tiny JSON document that selects + tunes a manifest:

    {
      "profile": "backend",          # which manifest() profile to build
      "include_ui": false,           # convenience alias (false => "backend")
      "log_dir": "logs",
      "services": ["m1_producer"],   # optional ProcSpec NAME allowlist
      "global_env": {"NBA_AI_SUPERVISED": "1"}
    }

``load_profile(name="default")`` reads ``config/boot/<name>.json`` and returns a
validated :class:`BootProfile`. A MISSING or GARBAGE profile NEVER crashes at
runtime: it logs a warning and returns the built-in safe default (full stack,
``logs/`` log dir, no extra env). This is deliberate -- an always-on boot must
not die because someone fat-fingered a config file.

Stdlib-only, ASCII-only, <=300 LOC. Never writes ``data/registry/``; never
flips a flag on.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from supervisor.manifest import ProcSpec, manifest

logger = logging.getLogger("supervisor.config")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BOOT_DIR = _REPO_ROOT / "config" / "boot"

_KNOWN_PROFILES = ("default", "backend", "paper")
_DEFAULT_LOG_DIR = "logs"


@dataclass(frozen=True)
class BootProfile:
    """A resolved, safe boot profile.

    name        -- the profile file name requested.
    profile     -- the manifest() profile to build ("default" | "backend").
    log_dir     -- where child stdout/stderr/pid files go (relative to repo).
    global_env  -- env applied to every child (per-ProcSpec env still wins).
    source      -- "file" | "fallback-missing" | "fallback-garbage";
                   lets the boot driver report HOW the profile was resolved.
    """

    name: str = "default"
    profile: str = "default"
    log_dir: str = _DEFAULT_LOG_DIR
    global_env: Dict[str, str] = field(default_factory=dict)
    source: str = "fallback-missing"
    services: Tuple[str, ...] = ()

    def specs(self) -> List[ProcSpec]:
        """The ordered, DAG-validated ProcSpec list for this profile."""
        return manifest(self.profile, services=list(self.services) or None)


def _safe_default(name: str, source: str) -> BootProfile:
    """The built-in fallback profile -- full stack, never raises."""
    return BootProfile(
        name=name, profile="default", log_dir=_DEFAULT_LOG_DIR,
        global_env={}, source=source,
    )


def _coerce(name: str, data: Dict[str, Any]) -> BootProfile:
    """Build a BootProfile from a parsed JSON dict, tolerating bad fields."""
    # profile: explicit "profile" key wins; else "include_ui": false => backend.
    profile = str(data.get("profile", "")).strip().lower()
    if profile not in _KNOWN_PROFILES:
        include_ui = data.get("include_ui", True)
        profile = "default" if include_ui else "backend"

    log_dir = data.get("log_dir", _DEFAULT_LOG_DIR)
    if not isinstance(log_dir, str) or not log_dir.strip():
        log_dir = _DEFAULT_LOG_DIR

    raw_env = data.get("global_env", {})
    global_env: Dict[str, str] = {}
    if isinstance(raw_env, dict):
        for k, v in raw_env.items():
            try:
                global_env[str(k)] = str(v)
            except Exception:  # noqa: BLE001 -- skip an unstringable entry
                continue

    # services: optional NAME ALLOWLIST (see manifest()). A non-list, or a list
    # with no usable strings, means "no allowlist" -> the whole profile.
    raw_services = data.get("services", [])
    services: List[str] = []
    if isinstance(raw_services, list):
        services = [str(v).strip() for v in raw_services if str(v).strip()]

    return BootProfile(
        name=name, profile=profile, log_dir=log_dir.strip(),
        global_env=global_env, source="file", services=tuple(services),
    )


def profile_path(name: str) -> Path:
    """Path to ``config/boot/<name>.json`` (not guaranteed to exist)."""
    safe = "".join(c for c in str(name) if c.isalnum() or c in ("-", "_")) or "default"
    return _BOOT_DIR / ("%s.json" % safe)


def load_profile(name: str = "default", *, boot_dir: Path = _BOOT_DIR) -> BootProfile:
    """Load + validate the boot profile *name*. NEVER raises.

    Resolution:
      * file missing            -> safe default (source="fallback-missing")
      * file unparseable/garbage-> safe default (source="fallback-garbage")
      * file ok                 -> coerced profile (source="file")
    """
    safe = "".join(c for c in str(name) if c.isalnum() or c in ("-", "_")) or "default"
    path = Path(boot_dir) / ("%s.json" % safe)
    if not path.exists():
        logger.info("supervisor.config: boot profile %r absent (%s); using default",
                    safe, path)
        return _safe_default(safe, "fallback-missing")
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except Exception as exc:  # noqa: BLE001 -- corrupt JSON / read error
        logger.warning("supervisor.config: boot profile %r garbage (%s: %s); "
                       "using default", safe, type(exc).__name__, exc)
        return _safe_default(safe, "fallback-garbage")
    if not isinstance(data, dict):
        logger.warning("supervisor.config: boot profile %r is not an object; "
                       "using default", safe)
        return _safe_default(safe, "fallback-garbage")
    return _coerce(safe, data)


def list_profiles(*, boot_dir: Path = _BOOT_DIR) -> List[str]:
    """Names of the boot profiles present on disk (sorted)."""
    d = Path(boot_dir)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))
