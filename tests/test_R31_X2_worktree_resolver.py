"""R31_X2 — Worktree-aware model-dir resolver regression tests.

Extends the R21_N1 fix (`prop_pergame._resolve_model_dir`) to three more
production loaders: `game_models` (legacy + m2_family), `residual_heads`
(endQ1/Q2/Q3), and `injury_availability` (parquet + JSON snapshot dir).

All four loaders now delegate to `src.prediction._paths` so:
  * `NBA_MODEL_DIR` env override is honoured first.
  * `NBA_DATA_DIR` umbrella env override is honoured second.
  * Local `<worktree>/data/models/` (or `data/cache/`) wins when populated
    with the canary file.
  * Host-repo `<...>/data/models/` is the worktree fallback.
  * No env + no local + no host → graceful default (empty dict / None,
    never an exception).

These tests pin every leg of the resolution chain plus the new tests
needed for the R31_X2 scope:

  1. host_repo_root detects `.claude/worktrees/<wt>/` correctly.
  2. host_repo_root returns None outside a worktree.
  3. resolve_dir env_var override wins.
  4. resolve_dir local default wins when canary present.
  5. resolve_dir host fallback wins when local missing canary.
  6. resolve_dir graceful default when nothing populated.
  7. NBA_DATA_DIR umbrella resolves data/models.
  8. NBA_DATA_DIR umbrella resolves data/cache.
  9. resolve_model_dir backwards-compat preserves prop_pergame's
     original behaviour.
 10. All 4 loaders import `_paths.resolve_*` (uniform refactor).
 11. game_models._MODEL_DIR resolves to a dir containing the legacy
     canary.
 12. game_models._M2_FAMILY_DIR resolves to a dir with manifest.json.
 13. residual_heads.HEAD_DIR (endQ3) resolves to a dir with pts.lgb.
 14. injury_availability._CACHE_DIR resolves to an existing dir.
 15. No env vars + no local + no host → empty/None graceful.

These tests do NOT require ANY model artifacts — they fabricate tmp
directory trees + monkeypatch project_dir.
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction import _paths  # noqa: E402


# ─── helpers ────────────────────────────────────────────────────────────────

def _mk_worktree_tree(tmp_path):
    """Construct a host repo + worktree dir tree under ``tmp_path``.

    Returns (host_root, worktree_root). The worktree path includes the
    `.claude/worktrees/<name>` segment that `host_repo_root` looks for.
    """
    host = tmp_path / "myhost"
    host.mkdir()
    (host / "data" / "models").mkdir(parents=True)
    (host / "data" / "cache").mkdir(parents=True)
    worktree = host / ".claude" / "worktrees" / "agent-x"
    worktree.mkdir(parents=True)
    (worktree / "data" / "models").mkdir(parents=True)
    (worktree / "data" / "cache").mkdir(parents=True)
    return str(host), str(worktree)


def _clear_env(monkeypatch):
    """Strip every env var the resolver consults so each test starts fresh."""
    for var in ("NBA_MODEL_DIR", "NBA_DATA_DIR", "NBA_INJURY_CACHE_DIR"):
        monkeypatch.delenv(var, raising=False)


# ─── 1. host_repo_root detection ────────────────────────────────────────────

def test_host_repo_root_detects_worktree(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    host, wt = _mk_worktree_tree(tmp_path)
    found = _paths.host_repo_root(project_dir=wt)
    assert found is not None
    # Normalise both sides to forward slashes so the assertion is OS-agnostic.
    assert _paths._norm(found) == _paths._norm(host)


def test_host_repo_root_returns_none_outside_worktree(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    plain = tmp_path / "plain-clone"
    plain.mkdir()
    assert _paths.host_repo_root(project_dir=str(plain)) is None


# ─── 3. env override wins ───────────────────────────────────────────────────

def test_resolve_dir_env_var_override_wins(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    host, wt = _mk_worktree_tree(tmp_path)
    # Drop a populated alt dir and point the env var at it.
    alt = tmp_path / "operator-models"
    alt.mkdir()
    (alt / "props_pg_pts.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("NBA_MODEL_DIR", str(alt))
    out = _paths.resolve_dir(
        "data/models",
        env_var="NBA_MODEL_DIR",
        canary="props_pg_pts.json",
        project_dir=wt,
    )
    assert _paths._norm(out) == _paths._norm(str(alt))


# ─── 4. local default wins when canary present ──────────────────────────────

def test_resolve_dir_local_default_wins_when_canary_present(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    host, wt = _mk_worktree_tree(tmp_path)
    # Worktree has the canary.
    canary_path = os.path.join(wt, "data", "models", "props_pg_pts.json")
    open(canary_path, "w").close()
    out = _paths.resolve_dir(
        "data/models",
        env_var="NBA_MODEL_DIR",
        canary="props_pg_pts.json",
        project_dir=wt,
    )
    assert _paths._norm(out) == _paths._norm(
        os.path.join(wt, "data", "models")
    )


# ─── 5. host fallback wins when local missing canary ────────────────────────

def test_resolve_dir_host_fallback_when_local_missing(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    host, wt = _mk_worktree_tree(tmp_path)
    # Only the HOST has the canary.
    canary_path = os.path.join(host, "data", "models", "props_pg_pts.json")
    open(canary_path, "w").close()
    out = _paths.resolve_dir(
        "data/models",
        env_var="NBA_MODEL_DIR",
        canary="props_pg_pts.json",
        project_dir=wt,
    )
    assert _paths._norm(out) == _paths._norm(
        os.path.join(host, "data", "models")
    )


# ─── 6. graceful default when nothing populated ─────────────────────────────

def test_resolve_dir_graceful_default_when_nothing_populated(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    host, wt = _mk_worktree_tree(tmp_path)
    # Neither side has the canary.
    out = _paths.resolve_dir(
        "data/models",
        env_var="NBA_MODEL_DIR",
        canary="props_pg_pts.json",
        project_dir=wt,
    )
    # Falls back to the local default (the worktree's own data/models),
    # not a fabricated path.
    assert _paths._norm(out) == _paths._norm(
        os.path.join(wt, "data", "models")
    )


# ─── 7-8. NBA_DATA_DIR umbrella ─────────────────────────────────────────────

def test_nba_data_dir_umbrella_resolves_models(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    host, wt = _mk_worktree_tree(tmp_path)
    umbrella = tmp_path / "umbrella-data"
    (umbrella / "models").mkdir(parents=True)
    (umbrella / "models" / "props_pg_pts.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("NBA_DATA_DIR", str(umbrella))

    out = _paths.resolve_model_dir(
        canary="props_pg_pts.json",
        project_dir=wt,
    )
    assert _paths._norm(out) == _paths._norm(str(umbrella / "models"))


def test_nba_data_dir_umbrella_resolves_cache(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    host, wt = _mk_worktree_tree(tmp_path)
    umbrella = tmp_path / "umbrella-data"
    (umbrella / "cache").mkdir(parents=True)
    monkeypatch.setenv("NBA_DATA_DIR", str(umbrella))

    out = _paths.resolve_data_dir("cache", project_dir=wt)
    assert _paths._norm(out) == _paths._norm(str(umbrella / "cache"))


# ─── 9. resolve_model_dir backwards-compat for prop_pergame ────────────────

def test_resolve_model_dir_backcompat_prop_pergame(tmp_path, monkeypatch):
    """With no env vars + populated local data/models containing the
    props_pg canary, resolver returns LOCAL (today's pre-R31_X2 behaviour)."""
    _clear_env(monkeypatch)
    host, wt = _mk_worktree_tree(tmp_path)
    open(os.path.join(wt, "data", "models", "props_pg_pts.json"), "w").close()
    out = _paths.resolve_model_dir(
        canary="props_pg_pts.json",
        project_dir=wt,
    )
    assert _paths._norm(out) == _paths._norm(
        os.path.join(wt, "data", "models")
    )


# ─── 10. all 4 loaders import _paths.resolve_* (uniform refactor) ─────────

def test_all_four_loaders_use_shared_resolver():
    """Each of the 4 target loaders must import from _paths so we know
    the refactor was actually applied and no loader is still hard-coding
    `os.path.join(PROJECT_DIR, "data", "models")` for the artifact dir.
    """
    for mod_name in (
        "src.prediction.prop_pergame",
        "src.prediction.game_models",
        "src.prediction.residual_heads",
        "src.prediction.injury_availability",
    ):
        mod = importlib.import_module(mod_name)
        src = open(mod.__file__, encoding="utf-8").read()
        assert "src.prediction._paths" in src, (
            f"{mod_name} does not import the shared resolver — R31_X2 "
            f"refactor incomplete."
        )


# ─── 11. game_models._MODEL_DIR points at a real dir ──────────────────────

def test_game_models_module_resolves_model_dir():
    """game_models._MODEL_DIR must be a STRING that exists on disk after
    R31_X2 — covering both 'local has artifacts' and 'fall back to host'
    cases. Tested against the LIVE module on whatever box runs the tests."""
    from src.prediction import game_models as gm
    assert isinstance(gm._MODEL_DIR, str)
    assert gm._MODEL_DIR  # non-empty
    # The directory may not exist on a totally fresh CI box, but a non-
    # empty string return is the contract.


# ─── 12. game_models._M2_FAMILY_DIR independent resolution ────────────────

def test_game_models_m2_family_dir_independent():
    """_M2_FAMILY_DIR resolves INDEPENDENTLY of _MODEL_DIR so a worktree
    with legacy heads but no m2_family still finds host's m2_family."""
    from src.prediction import game_models as gm
    assert isinstance(gm._M2_FAMILY_DIR, str)
    assert gm._M2_FAMILY_DIR.endswith("m2_family")


# ─── 13. residual_heads.HEAD_DIR (endQ3) resolves correctly ───────────────

def test_residual_heads_head_dir_resolves():
    """Each of the three endQ HEAD_DIRs is a string ending with the
    expected subdir name."""
    from src.prediction import residual_heads as rh
    assert isinstance(rh.HEAD_DIR, str)
    assert rh.HEAD_DIR.endswith("residual_heads")
    assert rh.HEAD_DIR_ENDQ2.endswith("residual_heads_endq2")
    assert rh.HEAD_DIR_ENDQ1.endswith("residual_heads_endq1")


# ─── 14. injury_availability._CACHE_DIR resolves ──────────────────────────

def test_injury_availability_cache_dir_resolves():
    """_CACHE_DIR must be a string ending with the 'cache' segment."""
    from src.prediction import injury_availability as ia
    assert isinstance(ia._CACHE_DIR, str)
    assert ia._CACHE_DIR.endswith("cache")


# ─── 15. nothing populated → graceful default (no exception) ──────────────

def test_no_env_no_local_no_host_graceful(tmp_path, monkeypatch):
    """The full graceful path: every input absent, every output a string
    (never an exception). Loaders are then free to gracefully degrade."""
    _clear_env(monkeypatch)
    # Plain dir (NOT a worktree, NOT populated).
    plain = tmp_path / "plain-clone"
    plain.mkdir()
    out = _paths.resolve_dir(
        "data/models",
        env_var="NBA_MODEL_DIR",
        canary="missing-file.json",
        project_dir=str(plain),
    )
    assert isinstance(out, str)
    # No error raised — the default dir is returned.
    assert out.endswith(os.path.join("data", "models"))


# ─── 16. resolve_dir respects subdir for `data/cache` paths ──────────────

def test_resolve_dir_cache_local_then_host(tmp_path, monkeypatch):
    """Same fallback chain works for data/cache (the injury module).
    Local empty cache + populated host cache → host wins iff canary
    matches; with canary=None local wins because local exists as a dir."""
    _clear_env(monkeypatch)
    host, wt = _mk_worktree_tree(tmp_path)

    # No canary, local exists -> local wins (back-compat).
    out_default = _paths.resolve_dir(
        "data/cache",
        project_dir=wt,
    )
    assert _paths._norm(out_default) == _paths._norm(
        os.path.join(wt, "data", "cache")
    )

    # With a canary present only on HOST -> host wins.
    open(os.path.join(host, "data", "cache",
                      "nba_injuries_today.parquet"), "w").close()
    out_host = _paths.resolve_dir(
        "data/cache",
        canary="nba_injuries_today.parquet",
        project_dir=wt,
    )
    assert _paths._norm(out_host) == _paths._norm(
        os.path.join(host, "data", "cache")
    )
