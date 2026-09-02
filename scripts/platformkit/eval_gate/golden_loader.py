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
import hashlib
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

# S40b (prior red team, agent 1.2): validate_golden is STRUCTURAL -- a schema-valid hand
# edit to the fixture silently redefines what "gate green" means, because nothing pinned
# the bytes. This seal is the frozen anchor's identity; it is checked only for the DEFAULT
# fixture, so a caller passing its own path (tests, alternative corpora) is unaffected.
# Regenerating the fixture with gen_golden is expected to break this on purpose: recompute
# the digest and commit it in the SAME change as the new fixture.
GOLDEN_SHA256 = "fe9298fc5aef80b10a799d547057374b291c4bb465fb1cf3e3aae2ed03cbcbf2"


def load_golden(path=None) -> List[dict]:
    """Read + validate the frozen golden fixture; return plain dicts (no mutation)."""
    p = Path(path) if path else DEFAULT_GOLDEN
    if not p.exists():
        raise FileNotFoundError(f"golden fixture missing: {p}")
    if path is None:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest != GOLDEN_SHA256:
            raise ValueError(
                f"golden fixture seal mismatch: {p}\nexpected {GOLDEN_SHA256}\n"
                f"     got {digest}\nthe frozen anchor changed; regenerate deliberately and "
                "commit the new GOLDEN_SHA256 with it."
            )
    with open(p, "r", encoding="ascii") as fh:
        payload = json.load(fh)
    states = payload["states"] if isinstance(payload, dict) else payload
    validate_golden(states)  # leak + coverage guard runs on every load
    return states


def golden_path() -> str:
    """Absolute path to the default frozen golden fixture."""
    return str(DEFAULT_GOLDEN)
