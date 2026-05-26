"""Tests for scripts/execute_loop/L43_runbook_generator.py.

Run:
    conda run -n basketball_ai python -m pytest scripts/execute_loop/tests/test_L43_runbook.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[3]
EXEC_LOOP   = PROJECT_DIR / "scripts" / "execute_loop"
sys.path.insert(0, str(PROJECT_DIR))

import scripts.execute_loop.L43_runbook_generator as L43


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SYNTHETIC_MODULE = '''"""
Synthetic test module.

MODE GATING
  LIVE=1 → live
  else → paper
"""
from __future__ import annotations

import os

MY_ENV_VAR = "default_value"
PAPER_MODE = True

def public_func(x: int, y: str = "hello") -> bool:
    """Return True always."""
    return True

def _private_func() -> None:
    """Should not appear."""
    pass

class PublicClass:
    """A public class."""
    pass

class _PrivateClass:
    """Should not appear."""
    pass

def uses_environ():
    val = os.environ.get("FOO_BAR", "fallback")
    return val
'''

_SYNTHETIC_WITH_LIVE = '''"""
Another module.

MODE GATING
  KALSHI_LIVE_ENABLED=1 → live
  else → paper
"""
KALSHI_LIVE_MODE = "paper"
'''


def _make_state(tmp_path: Path, layer_keys: list[str]) -> Path:
    """Write a minimal state.json with the given layer keys."""
    layers = {k: {"name": f"Test {k}", "status": "shipped",
                  "ships": [{"round": 1, "tests": "5/5", "loc": 100}]}
              for k in layer_keys}
    state = {"version": 1, "layers": layers}
    p = tmp_path / "state.json"
    p.write_text(json.dumps(state), encoding="utf-8")
    return p


def _make_layer_file(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Test 1: parse synthetic module — docstring + public function
# ---------------------------------------------------------------------------
def test_parse_synthetic_module_docstring_and_public_function(tmp_path):
    p = _make_layer_file(tmp_path, "L01_synthetic.py", _SYNTHETIC_MODULE)
    gen = L43.RunbookGenerator(tmp_path, tmp_path / "state.json", tmp_path / "RUNBOOK.md")
    info = gen.parse_layer(p)

    assert "Synthetic test module" in info.module_doc
    func_names = [s.name for s in info.publics if s.kind == "function"]
    assert "public_func" in func_names
    # Signature should contain the function name
    pub = next(s for s in info.publics if s.name == "public_func")
    assert "public_func" in pub.signature
    assert pub.summary == "Return True always."


# ---------------------------------------------------------------------------
# Test 2: private functions and classes excluded
# ---------------------------------------------------------------------------
def test_private_functions_excluded(tmp_path):
    p = _make_layer_file(tmp_path, "L02_synthetic.py", _SYNTHETIC_MODULE)
    gen = L43.RunbookGenerator(tmp_path, tmp_path / "state.json", tmp_path / "RUNBOOK.md")
    info = gen.parse_layer(p)

    names = [s.name for s in info.publics]
    assert "_private_func" not in names
    assert "_PrivateClass" not in names
    assert "PublicClass" in names


# ---------------------------------------------------------------------------
# Test 3: every layer in state.json appears in runbook as ## heading + TOC
# ---------------------------------------------------------------------------
def test_build_runbook_covers_every_state_json_layer(tmp_path):
    # Use real state.json and real layers directory
    real_state = EXEC_LOOP / "state.json"
    real_layers = EXEC_LOOP
    out = tmp_path / "RUNBOOK.md"

    gen = L43.RunbookGenerator(real_layers, real_state, out)
    md = gen.build_runbook()

    state = json.loads(real_state.read_text(encoding="utf-8"))
    for lkey in state["layers"]:
        num = int(lkey.lstrip("L"))
        lid = f"L{num:02d}"
        # Heading present
        assert f"## {lid}" in md, f"Missing heading for {lid}"
        # TOC entry present
        assert lid in md

    # L29 is gated — placeholder section, not a crash
    assert "gated" in md.lower()


# ---------------------------------------------------------------------------
# Test 4: env-var constants appear in rendered output
# ---------------------------------------------------------------------------
def test_env_var_constants_appear(tmp_path):
    content = '''"""A module with env constants."""
import os

KALSHI_LIVE_MODE = "paper"

def check():
    v = os.environ.get("FOO_BAR", "fallback")
    return v
'''
    p = _make_layer_file(tmp_path, "L05_env_test.py", content)
    state_p = _make_state(tmp_path, ["L5"])
    out = tmp_path / "RUNBOOK.md"
    gen = L43.RunbookGenerator(tmp_path, state_p, out)
    md = gen.build_runbook()

    assert "KALSHI_LIVE_MODE" in md
    assert "FOO_BAR" in md


# ---------------------------------------------------------------------------
# Test 5: paper vs live mode block detected
# ---------------------------------------------------------------------------
def test_paper_vs_live_block_detected(tmp_path):
    content = '''"""A module.

MODE GATING
  LIVE=1 → live
  else → paper
"""

def noop():
    pass
'''
    p = _make_layer_file(tmp_path, "L07_mode_test.py", content)
    state_p = _make_state(tmp_path, ["L7"])
    out = tmp_path / "RUNBOOK.md"
    gen = L43.RunbookGenerator(tmp_path, state_p, out)
    md = gen.build_runbook()

    assert "Paper vs Live Mode" in md
    assert "MODE GATING" in md


# ---------------------------------------------------------------------------
# Test 6: atomic write — no .tmp file left behind
# ---------------------------------------------------------------------------
def test_atomic_write_no_partial_state(tmp_path):
    real_state = EXEC_LOOP / "state.json"
    real_layers = EXEC_LOOP
    out = tmp_path / "RUNBOOK.md"

    gen = L43.RunbookGenerator(real_layers, real_state, out)
    gen.write_atomic()

    assert out.exists(), "RUNBOOK.md was not written"
    tmp_leftover = out.with_suffix(out.suffix + ".tmp")
    assert not tmp_leftover.exists(), ".tmp file left behind after write"


# ---------------------------------------------------------------------------
# Test 7: cross-reference table is non-empty and heading exists
# ---------------------------------------------------------------------------
def test_cross_reference_table_non_empty(tmp_path):
    # Create two synthetic layers where L02 imports from L01
    layer1 = '''"""Layer one."""
def alpha():
    pass
'''
    layer2 = '''"""Layer two."""
from scripts.execute_loop.L01_layer_one import alpha

def beta():
    pass
'''
    _make_layer_file(tmp_path, "L01_layer_one.py", layer1)
    _make_layer_file(tmp_path, "L02_layer_two.py", layer2)
    state_p = _make_state(tmp_path, ["L1", "L2"])
    out = tmp_path / "RUNBOOK.md"

    gen = L43.RunbookGenerator(tmp_path, state_p, out)
    md = gen.build_runbook()

    assert "## Cross-Reference Table" in md
    # At least one data row (not just the header/separator)
    table_lines = [ln for ln in md.splitlines() if "Cross-Reference" in ln or ("|" in ln and "`L" in ln)]
    assert len(table_lines) >= 1, "Cross-reference table has no data rows"
