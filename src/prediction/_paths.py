"""src/prediction/_paths.py — R31_X2 shared worktree-aware path resolver.

Extends the R21_N1 pattern (originally in `src/prediction/prop_pergame.py`)
into a shared utility so all production loaders use one consistent
resolution policy. Without this, gitignored model artifacts (m2_family/,
residual_heads/, props_pg_*.json) and data caches (data/cache/) don't
exist in fresh `.claude/worktrees/<wt>/` checkouts and production code
silently load-fails — every prediction returns None or empty.

Resolution order (all helpers):
    1. The named env var override (operator-controlled; absolute path),
       if set and the path exists.
    2. `<PROJECT_DIR>/<subdir>` (the worktree's own copy), if a `canary`
       file/subdir exists there (so we only "promote" a populated dir).
    3. If we're inside `.claude/worktrees/<wt>/`, walk up to the host repo
       and check `<host>/<subdir>` for the same canary.
    4. Fall back to the default `<PROJECT_DIR>/<subdir>` (downstream
       graceful-miss logic still applies — we just didn't FIND anything
       populated).

Public helpers:
    resolve_dir(subdir, *, env_var=None, canary=None, project_dir=None)
        Generic resolver. Used by every loader.
    resolve_model_dir(*, canary="props_pg_pts.json", project_dir=None)
        Returns the prop / game / residual / availability `data/models/`
        directory, honoring `NBA_MODEL_DIR` first then `NBA_DATA_DIR`.
    resolve_data_dir(subdir, *, env_var=None, canary=None, project_dir=None)
        Returns a directory under `<project>/data/<subdir>` (cache, nba, ...)
        honoring `NBA_DATA_DIR` first.
    host_repo_root(project_dir=None) -> Optional[str]
        Returns the host repo root when running inside a worktree, else
        None.

Backwards-compatibility contract:
    With no env vars set AND a populated local subdir, every helper
    returns the local default — i.e. same behaviour as today.

NB: `_paths.py` underscore prefix marks it as an internal stable module
within `src.prediction`. Other modules (src.dfs, src.execution, ...) are
NOT touched per the R31_X2 hard rules.
"""
from __future__ import annotations

import os
from typing import Optional

# Default project root — three levels up from this file
# (src/prediction/_paths.py).
_DEFAULT_PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

_WORKTREE_MARKER = "/.claude/worktrees/"


def _norm(path: str) -> str:
    """OS-agnostic forward-slashed normpath for worktree marker matching."""
    return os.path.normpath(path).replace("\\", "/")


def host_repo_root(project_dir: Optional[str] = None) -> Optional[str]:
    """Return the host repo root when `project_dir` is a worktree, else None.

    A worktree's PROJECT_DIR matches `.../<host>/.claude/worktrees/<name>`;
    the host repo root is everything before `/.claude/worktrees/`.
    """
    pd = project_dir or _DEFAULT_PROJECT_DIR
    norm = _norm(pd)
    if _WORKTREE_MARKER not in norm:
        return None
    return norm.split(_WORKTREE_MARKER, 1)[0]


def resolve_dir(
    subdir: str,
    *,
    env_var: Optional[str] = None,
    canary: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> str:
    """Resolve a project-relative subdirectory with worktree-aware fallback.

    Args:
        subdir:      Path relative to project root, e.g. ``"data/models"``.
                     Forward slashes are normalised to the host OS.
        env_var:     Optional env-var name. When set AND the path exists
                     AND is a directory, returned immediately.
        canary:      Optional filename (or subdir name) inside the target.
                     Used as the "is this dir populated?" probe. When None,
                     any existing dir wins. When given, the dir is only
                     accepted if it contains the canary.
        project_dir: Override the auto-detected project root (tests pass
                     a tmp dir here).

    Returns:
        Absolute path. If nothing populated is found, returns the
        default ``<project>/<subdir>`` (callers retain graceful-miss
        semantics).
    """
    pd = project_dir or _DEFAULT_PROJECT_DIR

    # 1. Explicit env override — operator wins.
    if env_var:
        env_val = os.environ.get(env_var)
        if env_val and os.path.isdir(env_val):
            return env_val

    # 1b. NBA_DATA_DIR umbrella override — applies to any data/* subdir.
    #     The umbrella points to the data ROOT (the parent of models/,
    #     cache/, nba/, ...), so we splice the post-``data/`` portion of
    #     subdir onto it. Example: NBA_DATA_DIR=/foo/data, subdir=data/models
    #     -> /foo/data/models.
    data_env = os.environ.get("NBA_DATA_DIR")
    if data_env and os.path.isdir(data_env):
        # Split subdir into "data/<rest>"; if subdir isn't under data/, the
        # umbrella doesn't apply.
        norm_sub = subdir.replace("\\", "/").lstrip("./")
        if norm_sub.startswith("data/"):
            rest = norm_sub[len("data/"):]
            candidate = (
                os.path.join(data_env, rest) if rest
                else data_env
            )
            if os.path.isdir(candidate):
                # If a canary is required, only accept when present.
                if canary is None or os.path.exists(
                    os.path.join(candidate, canary)
                ):
                    return candidate

    # 2. Local default — the worktree's own copy.
    default = os.path.join(pd, *subdir.replace("\\", "/").split("/"))
    if os.path.isdir(default):
        if canary is None or os.path.exists(os.path.join(default, canary)):
            return default

    # 3. Worktree fallback — walk up to the host repo.
    host = host_repo_root(pd)
    if host is not None:
        host_path = os.path.join(host, *subdir.replace("\\", "/").split("/"))
        if os.path.isdir(host_path):
            if canary is None or os.path.exists(
                os.path.join(host_path, canary)
            ):
                return host_path

    # 4. Nothing populated — return the default so callers' graceful-miss
    #    logic kicks in unchanged.
    return default


def resolve_model_dir(
    *,
    canary: Optional[str] = "props_pg_pts.json",
    project_dir: Optional[str] = None,
    env_var: str = "NBA_MODEL_DIR",
) -> str:
    """Resolve `data/models/` with worktree-aware fallback.

    Backwards-compatible shim for the original R21_N1 helper. The default
    canary (`props_pg_pts.json`) preserves the exact behaviour the
    `prop_pergame.py` resolver shipped — present iff base-learner
    artifacts are on disk in this dir.

    Callers that need a different canary (e.g. m2_family/manifest.json,
    residual_heads/pts.lgb) can override.
    """
    return resolve_dir(
        "data/models",
        env_var=env_var,
        canary=canary,
        project_dir=project_dir,
    )


def resolve_data_dir(
    subdir: str,
    *,
    env_var: Optional[str] = None,
    canary: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> str:
    """Resolve a `data/<subdir>` path (e.g. ``"cache"``, ``"nba"``).

    Honours `NBA_DATA_DIR` umbrella + per-call `env_var`. Same fallback
    chain as `resolve_dir`.
    """
    sub = subdir.replace("\\", "/").lstrip("/")
    if not sub.startswith("data/"):
        sub = "data/" + sub
    return resolve_dir(
        sub,
        env_var=env_var,
        canary=canary,
        project_dir=project_dir,
    )
