"""Gate-time reader of the frozen golden fixture (blueprint N1).

Self-contained (stdlib only, ASCII). load_golden() reads the frozen
tests/fixtures/golden/game_states.json and runs the schema's leak + coverage
guard on every load. It never touches real data/, never calls the builder
(gen_golden), and never mutates the states (walk_forward / schema both consume
the plain dicts as emitted by the builder, which carries home/away).

PROVENANCE: the fixture is a SYNTHETIC reproducibility/regression anchor, NOT a
real calibration claim.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import List

try:
    from schema import validate_golden, REQUIRED  # bare run from eval_gate cwd
except ImportError:
    from .schema import validate_golden, REQUIRED  # python -m package run

# default path resolved RELATIVE TO REPO ROOT, not cwd (robust under -m and bare run)
_REPO_ROOT = Path(__file__).resolve().parents[3]  # eval_gate->platformkit->scripts->ROOT
DEFAULT_GOLDEN = _REPO_ROOT / "tests" / "fixtures" / "golden" / "game_states.json"


def load_golden(path=None) -> List[dict]:
    """Read + validate the frozen golden fixture; return plain dicts (no mutation)."""
    p = Path(path) if path else DEFAULT_GOLDEN
    if not p.exists():
        raise FileNotFoundError(f"golden fixture missing: {p}")
    with open(p, "r", encoding="ascii") as fh:
        payload = json.load(fh)
    states = payload["states"] if isinstance(payload, dict) else payload
    validate_golden(states)  # leak + coverage guard runs on every load
    return states


def golden_path() -> str:
    """Absolute path to the default frozen golden fixture."""
    return str(DEFAULT_GOLDEN)
