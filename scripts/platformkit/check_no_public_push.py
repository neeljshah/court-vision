"""check_no_public_push.py — Pre-push tripwire: block pushes to the public remote.

Enforces the NEVER-PUSH-TO-PUBLIC invariant (CLAUDE.md / EXECUTION_HARNESS §8):
while any phase is open in .planning/platform/build_state.json, a push to the
public ``origin`` remote (neeljshah/court-vision) is blocked.

Usage::
    python scripts/platformkit/check_no_public_push.py --check origin   # exit 1
    python scripts/platformkit/check_no_public_push.py --check private  # exit 0

Git pre-push hook: symlink to .git/hooks/pre-push; git calls it as
``pre-push <remote-name> <remote-URL>`` with refs on stdin.

Exit codes: 0=allowed, 1=blocked, 2=fatal.
READ-ONLY: never performs a push, never writes any file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Canonical URL fragment that identifies the public court-vision repo.
_PUBLIC_URL_FRAGMENT: str = "neeljshah/court-vision"

#: Remote names that are always treated as the public remote.
_PUBLIC_REMOTE_NAMES: frozenset[str] = frozenset({"origin"})

#: Statuses that count as "closed / finished" — any other status is open.
_DONE_STATUSES: frozenset[str] = frozenset({"done"})

#: Path to the build-state file relative to the repo root.
_BUILD_STATE_REL: str = ".planning/platform/build_state.json"


# ---------------------------------------------------------------------------
# Repo-root detection
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    """Walk up from this file to find the repo root (contains CLAUDE.md)."""
    c = Path(__file__).resolve()
    for _ in range(10):
        c = c.parent
        if (c / "CLAUDE.md").exists():
            return c
    raise RuntimeError("check_no_public_push: repo root not found (CLAUDE.md missing)")


# ---------------------------------------------------------------------------
# Build-state reader
# ---------------------------------------------------------------------------

def _load_open_phases(state_path: Path) -> List[Tuple[str, str]]:
    """Return [(phase_id, status)] for every phase whose status is not 'done'."""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return [
        (str(pid), pdata.get("status", "unknown"))
        for pid, pdata in state.get("phases", {}).items()
        if pdata.get("status", "unknown") not in _DONE_STATUSES
    ]


# ---------------------------------------------------------------------------
# Remote classifier
# ---------------------------------------------------------------------------

def _is_public_remote(remote_name: str, remote_url: str = "") -> bool:
    """Return True if *remote_name* or *remote_url* identifies the public repo."""
    return (
        remote_name in _PUBLIC_REMOTE_NAMES
        or bool(remote_url and _PUBLIC_URL_FRAGMENT in remote_url)
    )


# ---------------------------------------------------------------------------
# Core decision
# ---------------------------------------------------------------------------

def check_push_allowed(
    remote_name: str,
    remote_url: str,
    state_path: Path,
) -> Tuple[bool, str]:
    """Return (allowed, reason) — True/message if push may proceed, False/message if blocked."""
    if not _is_public_remote(remote_name, remote_url):
        return (
            True,
            f"Remote '{remote_name}' is not the public origin — push allowed.",
        )

    try:
        open_phases = _load_open_phases(state_path)
    except FileNotFoundError:
        # State file absent → treat as unknown-open (safe-fail: block).
        return (
            False,
            f"BLOCKED: state file not found at {state_path}; "
            "cannot confirm all phases are done — refusing push to public origin "
            "as a safety default.",
        )
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError, ValueError) as exc:
        return (
            False,
            f"BLOCKED: failed to parse {state_path}: {exc}; "
            "refusing push to public origin as a safety default.",
        )

    if open_phases:
        summary = ", ".join(
            f"Phase {pid}({st})" for pid, st in open_phases[:5]
        )
        if len(open_phases) > 5:
            summary += f" … +{len(open_phases) - 5} more"
        return (
            False,
            f"BLOCKED: push to public remote '{remote_name}' refused — "
            f"{len(open_phases)} open phase(s): {summary}.  "
            "Close all phases before pushing platform work to the public repo.",
        )

    return (
        True,
        f"All phases done — push to '{remote_name}' is allowed.",
    )


# ---------------------------------------------------------------------------
# Git pre-push hook entry point
# ---------------------------------------------------------------------------

def run_as_hook(argv: List[str]) -> int:
    """Run as a git pre-push hook (argv = [remote-name, remote-url]; refs on stdin)."""
    if len(argv) < 2:
        print(
            "check_no_public_push (hook): expected args <remote-name> <remote-url>; "
            "got fewer — allowing push (cannot determine target).",
            file=sys.stderr,
        )
        return 0

    remote_name = argv[0]
    remote_url = argv[1] if len(argv) > 1 else ""

    # Consume stdin as required by the git pre-push protocol.
    try:
        for _ in sys.stdin:
            pass
    except (OSError, IOError):
        pass

    try:
        repo_root = _find_repo_root()
    except RuntimeError as exc:
        print(f"check_no_public_push (hook): {exc}", file=sys.stderr)
        return 2

    state_path = repo_root / _BUILD_STATE_REL
    allowed, reason = check_push_allowed(remote_name, remote_url, state_path)

    if allowed:
        print(f"check_no_public_push: {reason}", file=sys.stderr)
        return 0

    print(f"\ncheck_no_public_push: {reason}\n", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point: ``--check <remote>`` mode or git pre-push hook invocation."""
    if argv is None:
        argv = sys.argv[1:]

    # Detect git hook invocation: git calls ``pre-push <remote> <url>``
    # without any ``--`` flags.  If the first arg is not a flag, treat as hook.
    if argv and not argv[0].startswith("-"):
        return run_as_hook(argv)

    parser = argparse.ArgumentParser(
        prog="check_no_public_push",
        description=(
            "Pre-push tripwire: block pushes to the public origin "
            "while any platform phase is open."
        ),
    )
    parser.add_argument(
        "--check",
        metavar="REMOTE",
        required=True,
        help=(
            "Remote name to check (e.g. 'origin', 'private'). "
            "Exits 1 if remote is public AND a phase is open; 0 otherwise."
        ),
    )
    parser.add_argument(
        "--remote-url",
        metavar="URL",
        default="",
        help="Optional push URL of the remote (for URL-based matching).",
    )
    parser.add_argument(
        "--state",
        metavar="PATH",
        default=None,
        help=f"Override path to build_state.json (default: <repo>/{_BUILD_STATE_REL}).",
    )
    args = parser.parse_args(argv)

    if args.state:
        state_path = Path(args.state)
    else:
        try:
            repo_root = _find_repo_root()
        except RuntimeError as exc:
            print(f"FATAL: {exc}", file=sys.stderr)
            return 2
        state_path = repo_root / _BUILD_STATE_REL

    allowed, reason = check_push_allowed(args.check, args.remote_url, state_path)

    if allowed:
        print(f"check_no_public_push: {reason}")
        return 0

    print(f"\ncheck_no_public_push: {reason}\n", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
