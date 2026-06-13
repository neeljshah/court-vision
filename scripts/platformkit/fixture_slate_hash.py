"""fixture_slate_hash.py — G2 byte-identical fixture slate hasher (P0-B-002a).

Canonicalises and SHA-256-hashes the three G2 surfaces:
  * pregame_joint
  * ingame_replay
  * prop_predict

Real surface runners are INJECTED (P0-B-002b). Default stubs raise
NotImplementedError so the module is always import-safe.

CLI
---
Capture:
    python scripts/platformkit/fixture_slate_hash.py --capture --out PATH

Compare:
    python scripts/platformkit/fixture_slate_hash.py --compare BASELINE

Exit code: 0 = clean, 1 = divergence (surfaces listed) or error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict

# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------

_FLOAT_PRECISION = 1e-9  # changes smaller than ~1e-12 are invisible after round


def _round_float(value: float) -> float:
    """Round a float to the nearest multiple of _FLOAT_PRECISION."""
    return round(value / _FLOAT_PRECISION) * _FLOAT_PRECISION


def _canonicalize(obj: Any) -> Any:
    """Recursively normalise *obj* into a JSON-serialisable canonical form.

    * floats rounded to 1e-9
    * dicts key-sorted recursively
    * lists/tuples preserved in order (element-wise normalised)
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return _round_float(obj)
    if isinstance(obj, int):
        return obj
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return {k: _canonicalize(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_canonicalize(v) for v in obj]
    # Fallback: convert to string so the hash is still deterministic.
    return str(obj)


def canonical_hash(obj: Any) -> str:
    """Return the deterministic SHA-256 hex digest of *obj*.

    Floats are rounded to 1e-9, dicts key-sorted, then JSON-serialised with
    no extra whitespace before hashing.  Two calls with the same logical value
    always produce identical digests; a change ≥ 1e-9 flips the digest.
    """
    canonical = _canonicalize(obj)
    serialised = json.dumps(canonical, separators=(",", ":"), sort_keys=False)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Default stub runners (import-safe; replaced at injection time)
# ---------------------------------------------------------------------------

def _stub_pregame_joint() -> Any:
    raise NotImplementedError(
        "real runner deferred to P0-B-002b"
    )


def _stub_ingame_replay() -> Any:
    raise NotImplementedError(
        "real runner deferred to P0-B-002b"
    )


def _stub_prop_predict() -> Any:
    raise NotImplementedError(
        "real runner deferred to P0-B-002b"
    )


_DEFAULT_RUNNERS: Dict[str, Callable[[], Any]] = {
    "pregame_joint": _stub_pregame_joint,
    "ingame_replay": _stub_ingame_replay,
    "prop_predict": _stub_prop_predict,
}

# Authoritative surface names (order preserved for readability in JSON output).
SURFACE_NAMES = ("pregame_joint", "ingame_replay", "prop_predict")


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def hash_slate(
    surface_runners: Dict[str, Callable[[], Any]] | None = None,
) -> Dict[str, str]:
    """Hash all three fixture surfaces and return ``{surface_name: sha256}``.

    Parameters
    ----------
    surface_runners:
        Mapping of surface name → zero-argument callable that returns the
        surface output (nested dict/list of numbers).  Missing names fall back
        to the default stubs (which raise ``NotImplementedError``).  Pass your
        real runners here to exercise the surfaces; the stubs are intentionally
        deferred to P0-B-002b.

    Returns
    -------
    dict
        ``{"pregame_joint": "<sha256>", "ingame_replay": "<sha256>",
           "prop_predict": "<sha256>"}`` — always exactly these three keys.
    """
    runners = dict(_DEFAULT_RUNNERS)
    if surface_runners:
        runners.update(surface_runners)

    results: Dict[str, str] = {}
    for name in SURFACE_NAMES:
        runner = runners[name]
        output = runner()
        results[name] = canonical_hash(output)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fixture_slate_hash",
        description=(
            "G2 byte-identical fixture slate hasher. "
            "Capture surface hashes or compare against a baseline."
        ),
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--capture",
        action="store_true",
        help="Run all surface runners, hash outputs, write JSON to --out.",
    )
    mode.add_argument(
        "--compare",
        metavar="BASELINE",
        help=(
            "Re-hash all surfaces and compare against BASELINE JSON. "
            "Exits non-zero if any surface hash diverges."
        ),
    )
    p.add_argument(
        "--out",
        metavar="PATH",
        default=None,
        help="Output path for --capture (default: stdout only).",
    )
    return p


def _capture(out: str | None) -> int:
    """Run all surface runners, print hashes, optionally write to *out*."""
    try:
        hashes = hash_slate()
    except NotImplementedError as exc:
        print(f"ERROR: surface runner raised NotImplementedError: {exc}", file=sys.stderr)
        print(
            "Real runners must be injected (P0-B-002b) before --capture can succeed.",
            file=sys.stderr,
        )
        return 1

    payload = json.dumps(hashes, indent=2)
    print(payload)

    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        print(f"Wrote slate hashes → {path}", file=sys.stderr)

    return 0


def _compare(baseline_path: str) -> int:
    """Re-hash surfaces, compare against *baseline_path*, report divergences."""
    path = Path(baseline_path)
    if not path.exists():
        print(f"ERROR: baseline file not found: {path}", file=sys.stderr)
        return 1

    try:
        baseline: Dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: could not read baseline: {exc}", file=sys.stderr)
        return 1

    try:
        current = hash_slate()
    except NotImplementedError as exc:
        print(f"ERROR: surface runner raised NotImplementedError: {exc}", file=sys.stderr)
        return 1

    diverged = []
    for name in SURFACE_NAMES:
        b = baseline.get(name)
        c = current.get(name)
        if b != c:
            diverged.append(name)
            print(
                f"DIVERGED  {name}\n"
                f"  baseline : {b}\n"
                f"  current  : {c}"
            )

    if diverged:
        print(
            f"\nFAIL — {len(diverged)} surface(s) diverged: {', '.join(diverged)}",
            file=sys.stderr,
        )
        return 1

    print(f"OK — all {len(SURFACE_NAMES)} surfaces byte-identical to baseline.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.capture:
        return _capture(args.out)
    if args.compare:
        return _compare(args.compare)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
