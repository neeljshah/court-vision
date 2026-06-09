"""Single-authority build checks for the ``src.brain`` package.

ROADMAP phase: P0.3 — build-check assertions (ARCHITECTURE.md §3).

Three public functions:
  check_flag_registry()   — asserts every FLAGS entry has default=False, non-empty
                            phase, and non-empty gate.
  check_weight_authority() — classifies engine-weight / reliability JSONs against
                             the canonical authority table from ARCHITECTURE.md §3.
                             Hard-fails only if the source of control_brain.py or
                             flags.py introduces a second brain-written weight JSON.
                             Pre-existing legacy files under data/ are listed
                             informally (no hard failure).
  run_all()               — runs both checks; returns a report dict with ok=True.

All checks are static/structural (source-text grep + os.path scan).
Pure stdlib only; no torch / pandas / numpy.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(_HERE)                        # src/
_ROOT = os.path.dirname(_SRC)                        # repo root

_FLAGS_PY = os.path.join(_HERE, "flags.py")
_CONTROL_BRAIN_PY = os.path.join(_HERE, "control_brain.py")
_DATA_DIR = os.path.join(_ROOT, "data")

# ---------------------------------------------------------------------------
# Authority table — ARCHITECTURE.md §3
# ---------------------------------------------------------------------------

# The ONE file the brain is allowed to WRITE engine weights to.
_ALLOWED_WRITE_TARGET = "engine_reliability_weights.json"

# Input files (brain may READ, never independently re-create as a WRITE authority).
_INPUT_ONLY: frozenset[str] = frozenset({
    "ensemble_weights_proposal.json",
    "brain_regime_weights.json",    # season-2 stub — does not exist yet
    "reliability_export.json",      # calibration_registry export (D05 output)
})

# The single allowed brain-written weight file (absolute path).
_ALLOWED_WRITE_PATH = os.path.join(
    _ROOT, "data", "cache", "team_system", _ALLOWED_WRITE_TARGET
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _read_source(path: str) -> str:
    """Return the text of a source file; raise FileNotFoundError if absent."""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _find_json_files(base_dir: str, pattern: str) -> List[str]:
    """Walk *base_dir* and return all .json paths whose basename matches *pattern*
    (compiled as a case-insensitive regex against the filename only).
    Returns an empty list if *base_dir* does not exist.
    """
    if not os.path.isdir(base_dir):
        return []
    rx = re.compile(pattern, re.IGNORECASE)
    found: List[str] = []
    for dirpath, _dirs, files in os.walk(base_dir):
        for fname in files:
            if fname.endswith(".json") and rx.search(fname):
                found.append(os.path.join(dirpath, fname))
    return sorted(found)


def _extract_write_targets(source: str) -> List[str]:
    """Return JSON filenames referenced in an ``open(...)`` write context.

    Looks for patterns like:
        open(..., "w")   open(..., "wb")   open(..., mode="w")
    near a JSON filename string — conservative static approximation.
    """
    # Find all open() calls that include a write mode
    write_calls = re.findall(
        r'open\s*\([^)]*?["\']([^"\']+\.json)["\'][^)]*?["\']w[b]?["\'][^)]*?\)',
        source,
        re.DOTALL,
    )
    # Also catch: open(PATH, "w") where PATH is a variable name already holding a .json filename.
    # We look for the variable name assigned to a .json literal near a write open().
    write_calls_2 = re.findall(
        r'open\s*\(\s*\w+\s*,\s*["\']w[b]?["\']\s*\)',
        source,
    )
    # For the second pattern we cannot know the filename statically, but we can
    # check the variable assignments for .json literals nearby.
    # Collect all variable assignments ending in .json
    assigned_json_vars: Dict[str, str] = {}
    for m in re.finditer(
        r'(\w+)\s*=\s*os\.path\.join\([^)]*?["\']([^"\']+\.json)["\'][^)]*?\)',
        source,
    ):
        assigned_json_vars[m.group(1)] = os.path.basename(m.group(2))
    for m in re.finditer(
        r'(\w+)\s*=\s*["\']([^"\']+\.json)["\']',
        source,
    ):
        assigned_json_vars[m.group(1)] = os.path.basename(m.group(2))

    result: List[str] = [os.path.basename(p) for p in write_calls]

    for raw in write_calls_2:
        # extract variable name from the open() call
        var_m = re.search(r'open\s*\(\s*(\w+)', raw)
        if var_m:
            var = var_m.group(1)
            if var in assigned_json_vars:
                result.append(assigned_json_vars[var])

    return result


# ---------------------------------------------------------------------------
# check_flag_registry
# ---------------------------------------------------------------------------

def check_flag_registry() -> None:
    """Assert that every flag in ``flags.FLAGS`` satisfies the architecture invariants.

    Invariants checked (ARCHITECTURE.md §1 / §3):
    - ``default`` is exactly ``False`` (never True).
    - ``phase`` is a non-empty string.
    - ``gate`` is a non-empty string.

    Raises
    ------
    AssertionError
        On the first violation found, with a human-readable message.
    """
    # Import lazily to avoid circular dependency issues at module load.
    from brain.flags import FLAGS  # type: ignore[import]

    for name, meta in FLAGS.items():
        assert meta.get("default") is False, (
            f"Flag {name!r}: 'default' must be exactly False "
            f"(got {meta.get('default')!r}). "
            "ARCHITECTURE.md §1: all flags default OFF unconditionally."
        )
        phase = meta.get("phase", "")
        assert isinstance(phase, str) and phase.strip(), (
            f"Flag {name!r}: 'phase' must be a non-empty string "
            f"(got {phase!r})."
        )
        gate = meta.get("gate", "")
        assert isinstance(gate, str) and gate.strip(), (
            f"Flag {name!r}: 'gate' must be a non-empty string "
            f"(got {gate!r})."
        )


# ---------------------------------------------------------------------------
# check_weight_authority
# ---------------------------------------------------------------------------

def check_weight_authority() -> Dict[str, Any]:
    """Verify the single-authority engine-weight discipline (ARCHITECTURE.md §3).

    Hard assertions (will raise ``AssertionError``):
    1. ``control_brain.py`` does NOT open any weight JSON for writing other than
       the single allowed write target (``engine_reliability_weights.json``).
       (Today it only reads the file — this must remain true.)
    2. ``flags.py`` does NOT introduce a second brain-written weight JSON.

    Informational (no hard failure):
    - Lists any ``*weight*.json`` or ``*reliability*.json`` files found under
      ``data/`` to surface legacy / pre-existing artefacts.

    Returns
    -------
    dict
        Keys:
        ``allowed_write_target``, ``inputs_only``, ``legacy_data_files``,
        ``control_brain_write_targets``, ``flags_write_targets``,
        ``violations``, ``ok`` (bool).
    """
    cb_source = _read_source(_CONTROL_BRAIN_PY)
    flags_source = _read_source(_FLAGS_PY)

    cb_write_targets = _extract_write_targets(cb_source)
    flags_write_targets = _extract_write_targets(flags_source)

    # Hard check: control_brain.py must not write any weight JSON other than
    # the allowed target.
    violations: List[str] = []
    for fname in cb_write_targets:
        if fname != _ALLOWED_WRITE_TARGET:
            violations.append(
                f"control_brain.py opens '{fname}' for writing — "
                f"only '{_ALLOWED_WRITE_TARGET}' is the allowed brain-written "
                "weight file (ARCHITECTURE.md §3)."
            )

    # Hard check: flags.py must not write any weight JSON at all.
    for fname in flags_write_targets:
        violations.append(
            f"flags.py opens '{fname}' for writing — "
            "flags.py must not write any engine-weight JSON."
        )

    assert not violations, (
        "Weight authority violation(s) detected:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )

    # Informational: scan data/ for legacy weight/reliability JSONs.
    legacy_candidates = _find_json_files(
        _DATA_DIR,
        r"(weight|reliability|regime|proposal|ensemble_weight)",
    )
    # Exclude the single canonical allowed file from the legacy list.
    legacy_data_files = [
        p for p in legacy_candidates
        if os.path.basename(p) != _ALLOWED_WRITE_TARGET
    ]

    return {
        "allowed_write_target": _ALLOWED_WRITE_TARGET,
        "allowed_write_path": _ALLOWED_WRITE_PATH,
        "inputs_only": sorted(_INPUT_ONLY),
        "legacy_data_files": legacy_data_files,
        "control_brain_write_targets": cb_write_targets,
        "flags_write_targets": flags_write_targets,
        "violations": violations,
        "ok": True,
    }


# ---------------------------------------------------------------------------
# run_all
# ---------------------------------------------------------------------------

def run_all() -> Dict[str, Any]:
    """Run all build checks and return a summary report.

    Returns
    -------
    dict
        ``ok``: True if all checks passed (raises on failure, so True here
        means all checks passed).
        ``checks``: sub-report dict from each check.

    Raises
    ------
    AssertionError
        If any check fails.
    """
    check_flag_registry()
    weight_report = check_weight_authority()

    return {
        "ok": True,
        "checks": {
            "flag_registry": {
                "ok": True,
                "detail": "All FLAGS entries have default=False, non-empty phase+gate.",
            },
            "weight_authority": weight_report,
        },
    }


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    report = run_all()
    import json
    print(json.dumps(report, indent=2, default=str))
    print("\nbuild_checks: all OK.")
