"""stop_window.py — Loop STOP-window tool (EXECUTION_HARNESS §6.5).

DRY-RUN by default.  Pass --execute to make real changes.
Set CV_STOP_DIR env var in tests to redirect all file ops away from the real
data/registry/ directory.  Never runs run_loop.py — that is the orchestrator's job.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_state  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SNAPSHOT_TARGETS = ["state.json", "roadmap.json"]  # relative to registry_dir()

_EXTRA_TARGETS = [ROOT / ".planning" / "loop" / "orchestrator_checkpoint.json"]
_BASELINES_DIR = ROOT / ".planning" / "platform" / "baselines"


# ---------------------------------------------------------------------------
# Registry dir indirection — safety mechanism
# ---------------------------------------------------------------------------

def registry_dir() -> Path:
    """Return the registry dir, honouring CV_STOP_DIR override."""
    return Path(os.environ.get("CV_STOP_DIR", str(ROOT / "data" / "registry")))


def stop_file() -> Path:
    """Return the Path of the STOP sentinel inside registry_dir()."""
    return registry_dir() / "STOP"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str | None:
    """Streamed SHA-256 hex of *path*, or None if missing."""
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def snapshot(phase: str) -> dict:
    """Compute SHA-256 of each snapshot target that exists.

    Writes result to .planning/platform/baselines/phase<phase>_loop_state.json
    (build artifact — never touches the real registry).
    """
    shas: dict[str, str | None] = {}
    for name in SNAPSHOT_TARGETS:
        shas[name] = sha256_file(registry_dir() / name)
    for p in _EXTRA_TARGETS:
        shas[p.name] = sha256_file(p)

    result: dict = {
        "phase": phase,
        "shas": shas,
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
    }
    _BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    with (_BASELINES_DIR / f"phase{phase}_loop_state.json").open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    return result


# ---------------------------------------------------------------------------
# open_window
# ---------------------------------------------------------------------------

def open_window(phase: str, execute: bool = False) -> dict:
    """Pause the signal loop by creating the STOP sentinel file.

    If execute=False (default): DRY-RUN — print plan, change nothing.
    If execute=True: create STOP, write snapshot, update harness state.
    """
    sf = stop_file()

    if not execute:
        plan = {
            "action": "open",
            "would_create": str(sf),
            "execute": False,
            "note": "DRY-RUN — pass --execute to actually create the STOP file",
        }
        print(json.dumps(plan, indent=2))
        return plan

    # mkdir only for temp/test dirs; real data/registry must already exist
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(
        f"STOP by stop_window.py open_window(phase={phase!r}) "
        f"at {dt.datetime.now().isoformat(timespec='seconds')}\n",
        encoding="utf-8",
    )
    snap = snapshot(phase)

    state = harness_state.load()
    harness_state.set_phase(state, phase, stop_window="open")
    harness_state.save(state)
    harness_state.append_ledger("stop_window_open", phase=phase, stop_file=str(sf))

    result = {"action": "open", "stop_file": str(sf), "execute": True, "snapshot": snap}
    print(json.dumps(result, indent=2))
    return result


# ---------------------------------------------------------------------------
# close_window
# ---------------------------------------------------------------------------

def close_window(phase: str, execute: bool = False) -> dict:
    """Resume the signal loop by removing the STOP sentinel file.

    If execute=False (default): DRY-RUN — print plan, change nothing.
    If execute=True: remove STOP (if present), update harness state.

    NOTE: Does NOT run run_loop.py — that is the orchestrator's responsibility.
    # TODO (orchestrator): run `python scripts/loop/run_loop.py --once`
    #   after close, then assert iteration_count == pre_close + 1.
    """
    sf = stop_file()

    if not execute:
        plan = {
            "action": "close",
            "would_remove": str(sf),
            "would_run_next": "python scripts/loop/run_loop.py --once  [orchestrator's job]",
            "would_assert": "+1 iteration in harness state",
            "execute": False,
            "note": "DRY-RUN — pass --execute to actually remove the STOP file",
        }
        print(json.dumps(plan, indent=2))
        return plan

    if not sf.exists():
        warning = {
            "warning": "no stop window open",
            "stop_file": str(sf),
            "note": "close_window found no STOP file — refusing to proceed.",
        }
        print(json.dumps(warning, indent=2))
        return warning

    sf.unlink()

    state = harness_state.load()
    harness_state.set_phase(state, phase, stop_window=None)
    harness_state.save(state)
    harness_state.append_ledger("stop_window_close", phase=phase)

    result = {
        "action": "close",
        "stop_file_removed": str(sf),
        "execute": True,
        "next_step": (
            "orchestrator: python scripts/loop/run_loop.py --once "
            "then assert iteration_count == pre_close_iteration + 1"
        ),
    }
    print(json.dumps(result, indent=2))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Loop STOP-window tool (EXECUTION_HARNESS §6.5).\n"
            "DRY-RUN by default — pass --execute to make real changes.\n"
            "Set CV_STOP_DIR to override the registry dir (always in tests)."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--open", metavar="PHASE", dest="open_phase",
                   help="Open STOP window for build phase (e.g. 3).")
    g.add_argument("--close", metavar="PHASE", dest="close_phase",
                   help="Close the STOP window for build phase.")
    p.add_argument("--execute", action="store_true", default=False,
                   help="Actually create/remove STOP and update harness state.")
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()
    if args.open_phase is not None:
        open_window(args.open_phase, execute=args.execute)
    else:
        close_window(args.close_phase, execute=args.execute)
