"""test_api_boot.py — Gate G4: offline API boot + route-breadth smoke test.

Verifies:
  (a) api.main imports and boots offline without network access.
  (b) GET / returns non-5xx.
  (c) Route count matches the BASELINE_ROUTE_COUNT captured at first-green.
  (d) Per-router breadth: one param-free GET per prefix group is non-5xx
      (4xx is acceptable; 5xx = import/boot/runtime crash = real fail).

Belt-and-suspenders: NBA_OFFLINE=1 is set at module level BEFORE api.main
is imported, in addition to the setdefault() already in api/main.py.

Performance contract (default run):
  - ONE module-scoped TestClient → startup fires exactly once.
  - Heavy board-builders (/cv, /games, /g3) are probed only when
    CV_GATE_HEAVY_PROBES=1; default-off so the suite runs in < 60s.
  - SSE/streaming routes (/sse/*) are skipped by default with a recorded
    reason: they return 200+stream (not 5xx) and holding a live SSE
    connection blocks the shared TestClient's shutdown by ~55s.
    They are covered by the route-count assertion (registered = importable).
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

# ── Heavy route gate: set CV_GATE_HEAVY_PROBES=1 to probe /cv, /games, /g3 ──
_HEAVY_PROBES_ON: bool = os.environ.get("CV_GATE_HEAVY_PROBES") == "1"

# Groups whose *shortest* param-free root is known to take >15s (board builders).
# When _HEAVY_PROBES_ON is False these are skipped-with-record (pytest.skip).
_HEAVY_GROUPS: frozenset = frozenset({"cv", "games", "g3"})

# Groups that map to streaming (SSE) endpoints.  Skipped unconditionally:
# they return HTTP 200 + a live stream (not 5xx) and holding the connection
# blocks the shared TestClient shutdown by ~55s.  Crash coverage = route-count
# assertion (the handler must at least import and register successfully).
_SSE_GROUPS: frozenset = frozenset({"sse"})


# ---------------------------------------------------------------------------
# Module-scoped shared TestClient — startup/shutdown fire exactly ONCE
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """Shared TestClient for the whole module — FastAPI lifespan fires once."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Hermetic fixture — restore model-metrics files + verify after the run
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="module")
def _restore_model_metrics():
    """Keep the gate hermetic: restore any tracked data/models/*.json bytes the
    app rewrote while booting/probing so the test never leaves a working-tree diff.

    Teardown asserts the restored bytes equal the original snapshot so callers
    can confirm the fixture actually worked (not just fire-and-forget).
    """
    yield
    mismatches: List[str] = []
    for _p, _data in _MODELS_SNAPSHOT.items():
        try:
            current = _p.read_bytes()
            if current != _data:
                _p.write_bytes(_data)
                # Verify the write landed correctly
                restored = _p.read_bytes()
                if restored != _data:
                    mismatches.append(str(_p))
        except OSError:
            pass
    assert not mismatches, (
        f"Hermetic restore failed for {len(mismatches)} file(s): {mismatches}. "
        "data/models/*.json may have been left modified."
    )


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
# Collect probe cases at module import time
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


# ---------------------------------------------------------------------------
# Core assertions (primary)
# ---------------------------------------------------------------------------

def test_app_imports_offline() -> None:
    """(a) api.main must import without network access."""
    # The import at module level already proves this; reaching here = pass.
    assert app is not None


def test_root_non_5xx(client: TestClient) -> None:
    """(b) GET / must not return a 5xx response (crash indicator)."""
    response = client.get("/")
    assert response.status_code < 500, (
        f"GET / returned {response.status_code} — api.main may have a boot-time crash"
    )


def test_health_non_5xx(client: TestClient) -> None:
    """GET /health must not return 5xx (route is defined in api.main)."""
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

@pytest.mark.parametrize("seg,path", _PROBE_CASES, ids=[f"{s}:{p}" for s, p in _PROBE_CASES])
def test_per_router_non_5xx(seg: str, path: str, client: TestClient) -> None:
    """(d) Each prefix group's cheapest param-free GET must not 5xx.

    4xx responses (auth, not found, bad request) are acceptable offline.
    5xx means a crash/uncaught exception in the handler — a real failure.

    Heavy groups (/cv, /games, /g3) are skipped unless CV_GATE_HEAVY_PROBES=1.
    SSE groups (/sse/*) are skipped unconditionally — they return 200+stream (not
    5xx) and holding a live SSE connection blocks the shared client shutdown by
    ~55s; crash coverage is provided by the route-count assertion.
    """
    if seg in _HEAVY_GROUPS and not _HEAVY_PROBES_ON:
        pytest.skip(
            f"Heavy board-builder group {seg!r} skipped "
            "(set CV_GATE_HEAVY_PROBES=1 to probe)"
        )

    if seg in _SSE_GROUPS:
        pytest.skip(
            f"SSE/streaming group {seg!r} skipped to avoid blocking shared client "
            "shutdown; handler is import-verified by route-count assertion"
        )

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
    total_groups = len(groups)
    heavy_skipped = sum(1 for seg in groups if seg in _HEAVY_GROUPS and not _HEAVY_PROBES_ON)
    sse_skipped = sum(1 for seg in groups if seg in _SSE_GROUPS)
    probed_active = total_groups - heavy_skipped - sse_skipped
    skipped_param = _SKIPPED_PARAM_ROUTES
    total_get = sum(
        1 for r in app.routes if "GET" in (getattr(r, "methods", None) or set())
    )
    print(
        f"\nRoute probe coverage: "
        f"probed {probed_active} groups "
        f"({heavy_skipped} heavy skipped [CV_GATE_HEAVY_PROBES={int(_HEAVY_PROBES_ON)}], "
        f"{sse_skipped} SSE skipped [import-verified by route-count]) "
        f"from {total_get} GET routes across {total_groups} groups; "
        f"skipped {skipped_param} param-bearing GET routes (no assertion on those)"
    )
    assert total_groups > 0, "Expected at least one param-free GET group to probe"
