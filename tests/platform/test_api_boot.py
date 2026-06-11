"""test_api_boot.py — Gate G4: offline API boot + route-breadth smoke test.

Verifies:
  (a) api.main imports and boots offline without network access.
  (b) GET / returns non-5xx.
  (c) Route count matches the BASELINE_ROUTE_COUNT captured at first-green.
  (d) Per-router breadth: one param-free GET per prefix group is non-5xx
      (4xx is acceptable; 5xx = import/boot/runtime crash = real fail).

Belt-and-suspenders: NBA_OFFLINE=1 is set at module level BEFORE api.main
is imported, in addition to the setdefault() already in api/main.py.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

# ── Path setup (mirrors conftest.py so this file can also run standalone) ──
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ── Snapshot tracked model-metrics BEFORE booting (boot/probe can rewrite them) ─
_MODELS_DIR = _REPO_ROOT / "data" / "models"
_MODELS_SNAPSHOT: Dict[Path, bytes] = {}
if _MODELS_DIR.is_dir():
    for _p in _MODELS_DIR.glob("*.json"):
        try:
            _MODELS_SNAPSHOT[_p] = _p.read_bytes()
        except OSError:
            pass

# ── Force offline BEFORE importing api.main ─────────────────────────────────
os.environ["NBA_OFFLINE"] = "1"

import pytest
from fastapi.testclient import TestClient

from api.main import app  # noqa: E402 — must come after NBA_OFFLINE is set

# ── Baseline: captured at first-green run (2026-06-11). ─────────────────────
# Update this constant intentionally when routes are added or removed.
BASELINE_ROUTE_COUNT: int = 104


@pytest.fixture(autouse=True, scope="module")
def _restore_model_metrics():
    """Keep the gate hermetic: restore any tracked data/models/*.json bytes the
    app rewrote while booting/probing, so the test never leaves a working-tree diff."""
    yield
    for _p, _data in _MODELS_SNAPSHOT.items():
        try:
            if _p.read_bytes() != _data:
                _p.write_bytes(_data)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_param_free(path: str) -> bool:
    """Return True when the path contains no {placeholder} segments."""
    return "{" not in path


def _first_segment(path: str) -> str:
    """Return the first non-empty path segment (e.g. '/api/foo' -> 'api')."""
    parts = [p for p in path.split("/") if p]
    return parts[0] if parts else ""


def _param_free_gets_by_group() -> Dict[str, List[str]]:
    """Build a dict mapping first-segment → [param-free GET paths]."""
    groups: Dict[str, List[str]] = defaultdict(list)
    for route in app.routes:
        path: str = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if "GET" not in methods:
            continue
        if not _is_param_free(path):
            continue
        seg = _first_segment(path)
        groups[seg].append(path)
    return dict(groups)


def _count_param_routes() -> int:
    """Count GET routes that require path parameters (for skip reporting)."""
    skipped = 0
    for route in app.routes:
        path: str = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if "GET" in methods and not _is_param_free(path):
            skipped += 1
    return skipped


# ---------------------------------------------------------------------------
# Core assertions (primary)
# ---------------------------------------------------------------------------

def test_app_imports_offline() -> None:
    """(a) api.main must import without network access."""
    # The import at module level already proves this; reaching here = pass.
    assert app is not None


def test_root_non_5xx() -> None:
    """(b) GET / must not return a 5xx response (crash indicator)."""
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/")
    assert response.status_code < 500, (
        f"GET / returned {response.status_code} — api.main may have a boot-time crash"
    )


def test_health_non_5xx() -> None:
    """GET /health must not return 5xx (route is defined in api.main)."""
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/health")
    assert response.status_code < 500, (
        f"GET /health returned {response.status_code}"
    )


def test_route_count_matches_baseline() -> None:
    """(c) Total route count must equal BASELINE_ROUTE_COUNT.

    A deviation means routes were added or removed intentionally — update
    the constant when that happens.
    """
    actual = len(app.routes)
    assert actual == BASELINE_ROUTE_COUNT, (
        f"Route count changed: expected {BASELINE_ROUTE_COUNT}, got {actual}. "
        "Update BASELINE_ROUTE_COUNT in this file if the change is intentional."
    )


# ---------------------------------------------------------------------------
# Breadth probe (best-effort, one route per prefix group)
# ---------------------------------------------------------------------------

def _collect_probe_cases() -> List[Tuple[str, str]]:
    """Return list of (group_segment, path) pairs — one per group, sorted."""
    groups = _param_free_gets_by_group()
    cases: List[Tuple[str, str]] = []
    for seg in sorted(groups.keys()):
        paths = groups[seg]
        # Prefer shorter paths (more likely to be stable roots)
        paths_sorted = sorted(paths, key=lambda p: (len(p), p))
        cases.append((seg, paths_sorted[0]))
    return cases


_PROBE_CASES = _collect_probe_cases()
_SKIPPED_PARAM_ROUTES = _count_param_routes()


@pytest.mark.parametrize("seg,path", _PROBE_CASES, ids=[f"{s}:{p}" for s, p in _PROBE_CASES])
def test_per_router_non_5xx(seg: str, path: str) -> None:
    """(d) Each prefix group's cheapest param-free GET must not 5xx.

    4xx responses (auth, not found, bad request) are acceptable offline.
    5xx means a crash/uncaught exception in the handler — a real failure.
    """
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(path)
    assert response.status_code < 500, (
        f"GET {path} (group={seg!r}) returned {response.status_code} — "
        "handler crashed; check logs for traceback"
    )


# ---------------------------------------------------------------------------
# Informational: report skipped param routes (no assertion — just visible)
# ---------------------------------------------------------------------------

def test_report_probe_coverage() -> None:
    """Log probe coverage so CI output is self-documenting."""
    groups = _param_free_gets_by_group()
    probed = len(groups)
    skipped = _SKIPPED_PARAM_ROUTES
    total_get = sum(
        1 for r in app.routes if "GET" in (getattr(r, "methods", None) or set())
    )
    print(
        f"\nRoute probe coverage: "
        f"probed {probed} groups from {total_get} GET routes; "
        f"skipped {skipped} param-bearing GET routes (no assertion on those)"
    )
    assert probed > 0, "Expected at least one param-free GET group to probe"
