"""scripts/loop/reset_loop_state.py — Re-arm the idle autonomous loop.

The loop goes IDLE when ``held_out_spent`` is True *and* every hypothesis in
``defer_attempts`` has reached ``max_attempts``.  This CLI edits
``.planning/loop/orchestrator_checkpoint.json`` so the orchestrator treats the
next iteration as a fresh start: it clears the spent held-out flag and/or drops
maxed-out defer entries, leaving iteration count and ``last_run`` intact.

Usage examples::

    # default: clear held_out + drop maxed defers, show before/after, WRITE
    python scripts/loop/reset_loop_state.py

    # dry-run: print diff only, write nothing
    python scripts/loop/reset_loop_state.py --dry-run

    # drop ALL defer entries (not just maxed ones)
    python scripts/loop/reset_loop_state.py --clear-defers all

    # only drop maxed defers, keep held_out_spent as-is
    python scripts/loop/reset_loop_state.py --keep-held-out

    # custom max-attempts threshold (e.g. the loop was configured at 5)
    python scripts/loop/reset_loop_state.py --max-attempts 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Literal

# Compute the checkpoint path relative to this file's repo root so the default
# works regardless of the caller's cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CHECKPOINT = _REPO_ROOT / ".planning" / "loop" / "orchestrator_checkpoint.json"

_DEFAULT_CKPT: Dict = {
    "iterations": 0,
    "held_out_spent": False,
    "defer_attempts": {},
}


def load_checkpoint(path: str) -> dict:
    """Load the orchestrator checkpoint JSON; return the default dict if absent or corrupt.

    Args:
        path: Absolute path to ``orchestrator_checkpoint.json``.

    Returns:
        A dict with at minimum the keys ``iterations``, ``held_out_spent``,
        and ``defer_attempts``.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("checkpoint is not a JSON object")
        # Fill any missing keys with defaults (defensive for partial writes).
        out: dict = dict(_DEFAULT_CKPT)
        out.update(data)
        return out
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return dict(_DEFAULT_CKPT)


def reset_state(
    ckpt: dict,
    *,
    clear_held_out: bool = True,
    clear_defers: Literal["maxed", "all", "none"] = "maxed",
    max_attempts: int = 3,
) -> dict:
    """Return a NEW checkpoint dict with the idle conditions cleared.

    Does NOT mutate the input dict.

    Args:
        ckpt:            The current checkpoint (as returned by :func:`load_checkpoint`).
        clear_held_out:  When True, set ``held_out_spent`` to False so the loop
                         re-evaluates the held-out set on the next iteration.
        clear_defers:    Strategy for ``defer_attempts``:
                         - ``"maxed"`` — drop only entries whose count >= ``max_attempts``.
                         - ``"all"``   — drop every entry (full reset).
                         - ``"none"``  — keep all entries unchanged.
        max_attempts:    The per-signal defer cap used by the orchestrator (default 3).

    Returns:
        A new dict with the same ``iterations`` and ``last_run`` but updated
        ``held_out_spent`` / ``defer_attempts`` according to the chosen strategy.
    """
    new_ckpt = dict(ckpt)  # shallow copy — defer_attempts rebuilt below

    if clear_held_out:
        new_ckpt["held_out_spent"] = False

    old_defers: dict = ckpt.get("defer_attempts", {})
    if clear_defers == "all":
        new_ckpt["defer_attempts"] = {}
    elif clear_defers == "maxed":
        new_ckpt["defer_attempts"] = {
            k: v for k, v in old_defers.items() if v < max_attempts
        }
    else:  # "none"
        new_ckpt["defer_attempts"] = dict(old_defers)

    return new_ckpt


def save_checkpoint(ckpt: dict, path: str) -> None:
    """Atomically write ``ckpt`` to ``path`` (write to .tmp then os.replace).

    Creates parent directories if needed.

    Args:
        ckpt: The checkpoint dict to persist.
        path: Destination file path.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(ckpt, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

def _diff_summary(before: dict, after: dict, max_attempts: int) -> str:
    """Return a human-readable before/after summary."""
    lines = []

    old_ho = before.get("held_out_spent", False)
    new_ho = after.get("held_out_spent", False)
    if old_ho != new_ho:
        lines.append(f"  held_out_spent : {old_ho} -> {new_ho}")
    else:
        lines.append(f"  held_out_spent : {old_ho} (unchanged)")

    old_d: dict = before.get("defer_attempts", {})
    new_d: dict = after.get("defer_attempts", {})
    dropped = {k: v for k, v in old_d.items() if k not in new_d}
    kept = {k: v for k, v in new_d.items()}
    lines.append(f"  defer_attempts : {len(old_d)} entries -> {len(new_d)} entries")
    if dropped:
        lines.append(f"    dropped ({len(dropped)}):")
        for k, v in sorted(dropped.items()):
            flag = " [MAXED]" if v >= max_attempts else ""
            lines.append(f"      {k}: {v}{flag}")
    if kept:
        lines.append(f"    kept ({len(kept)}):")
        for k, v in sorted(kept.items()):
            lines.append(f"      {k}: {v}")

    lines.append(f"  iterations     : {after.get('iterations')} (preserved)")
    lr = after.get("last_run")
    if lr:
        lines.append(f"  last_run       : {lr} (preserved)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    """Entry point for the reset-loop-state CLI.

    Returns:
        0 on success, 1 on fatal error.
    """
    parser = argparse.ArgumentParser(
        prog="reset_loop_state",
        description="Re-arm the idle autonomous loop by editing orchestrator_checkpoint.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path",
        default=str(_DEFAULT_CHECKPOINT),
        help="Path to orchestrator_checkpoint.json (default: repo .planning/loop/).",
    )
    parser.add_argument(
        "--clear-defers",
        choices=["maxed", "all", "none"],
        default="maxed",
        dest="clear_defers",
        help=(
            "Which defer_attempts entries to remove: "
            "'maxed' (default) drops entries at max-attempts; "
            "'all' empties the dict; 'none' keeps all."
        ),
    )
    parser.add_argument(
        "--keep-held-out",
        action="store_true",
        default=False,
        dest="keep_held_out",
        help="If set, do NOT clear held_out_spent (leave it as-is).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        dest="dry_run",
        help="Print the before/after diff but write nothing.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        dest="max_attempts",
        help="Per-signal defer cap used by the orchestrator (default 3).",
    )

    args = parser.parse_args(argv)
    before = load_checkpoint(args.path)
    after = reset_state(
        before,
        clear_held_out=not args.keep_held_out,
        clear_defers=args.clear_defers,
        max_attempts=args.max_attempts,
    )

    print("[reset_loop_state] BEFORE:")
    print(_diff_summary(before, before, args.max_attempts))
    print()
    print("[reset_loop_state] AFTER (proposed):")
    print(_diff_summary(after, after, args.max_attempts))
    print()
    print("[reset_loop_state] CHANGES:")
    print(_diff_summary(before, after, args.max_attempts))

    if args.dry_run:
        print()
        print("[reset_loop_state] DRY-RUN: nothing written.")
        return 0

    # Write .bak of the original first, then save the new state atomically.
    bak_path = args.path + ".bak"
    try:
        save_checkpoint(before, bak_path)
        print(f"\n[reset_loop_state] Backup written to: {bak_path}")
    except Exception as exc:
        print(f"[reset_loop_state] WARNING: could not write backup: {exc}", file=sys.stderr)

    save_checkpoint(after, args.path)
    print(f"[reset_loop_state] Checkpoint updated: {args.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
