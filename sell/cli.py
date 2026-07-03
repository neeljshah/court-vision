"""sell.cli -- build / verify the signed CLV track-record artifact.

Usage::

    python -m sell.cli build     # build from the CLV scoreboard, sign, write
    python -m sell.cli verify    # load the artifact and verify its signature

The artifact is written to data/frontend/sell/track_record.signed.json (the same
gitignored/local-only data tree as the CLV ledger). build REUSES the vetted
scoreboard / clv_ledger (no CLV recomputation) and the signed envelope is
honesty-linted before it is written. The signing secret comes ONLY from
SELL_API_SECRET in the environment; without it the record is written UNSIGNED
(and verify reports it as unsigned), never silently presented as signed.

INVARIANTS: build only under sell/; <=300 LOC; ASCII only; no secrets in code;
never writes data/registry/; never pushes origin.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from sell.signing import is_signed as _is_signed
from sell.signing import verify as _verify
from sell.track_record import build_track_record, sign_track_record

#: Canonical artifact path: same data/ tree as the CLV ledger (local-only).
_HERE = Path(__file__).resolve().parent
DEFAULT_ARTIFACT = (
    _HERE.parent / "data" / "frontend" / "sell" / "track_record.signed.json"
)


def _atomic_write(dest: Path, payload: str) -> Path:
    """Write *payload* to *dest* atomically via tmp file + os.replace."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_name, str(dest))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return dest


def cmd_build(out_path: Optional[Path] = None) -> int:
    """Build, sign, honesty-lint, and write the track-record artifact.

    Returns a process exit code (0 on success). The signed envelope is written
    even when unsigned (no secret) so the artifact always reflects the current
    paper trail; the signing status is reported to stderr.
    """
    dest = Path(out_path) if out_path is not None else DEFAULT_ARTIFACT
    tr = build_track_record()
    signed = sign_track_record(tr)  # raises if not honesty-clean
    payload = json.dumps(signed, indent=2, sort_keys=True, default=str) + "\n"
    _atomic_write(dest, payload)
    status = "SIGNED" if _is_signed(signed) else "UNSIGNED (no SELL_API_SECRET)"
    sys.stderr.write(
        "wrote track record [%s] n_settled=%s -> %s\n"
        % (status, signed.get("n_settled"), dest)
    )
    return 0


def cmd_verify(in_path: Optional[Path] = None) -> int:
    """Load the artifact and verify its HMAC signature.

    Returns 0 iff the artifact exists, parses, and its signature verifies under
    SELL_API_SECRET. An unsigned or tampered artifact returns a non-zero code.
    """
    src = Path(in_path) if in_path is not None else DEFAULT_ARTIFACT
    if not src.exists():
        sys.stderr.write("no artifact at %s (run: build)\n" % src)
        return 2
    try:
        record: Dict[str, Any] = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("cannot read artifact %s: %s\n" % (src, exc))
        return 2
    if not _is_signed(record):
        sys.stderr.write(
            "artifact is UNSIGNED (no SELL_API_SECRET at build time): %s\n" % src
        )
        return 3
    if _verify(record):
        sys.stderr.write("signature OK: %s\n" % src)
        return 0
    sys.stderr.write("signature INVALID (tampered or wrong secret): %s\n" % src)
    return 4


def main(argv: Optional[list] = None) -> int:
    """Dispatch the build / verify subcommand. Returns a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else ""
    if cmd == "build":
        return cmd_build()
    if cmd == "verify":
        return cmd_verify()
    sys.stderr.write("usage: python -m sell.cli build|verify\n")
    return 64  # EX_USAGE


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
