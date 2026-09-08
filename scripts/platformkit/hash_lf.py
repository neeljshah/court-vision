"""Checkout-invariant SHA-256 for text artifacts.

`core.autocrlf` is true on the Windows build box, so a committed text blob is LF in the
git object store and on the pod but CRLF in the local working tree. A SHA-256 taken over
raw file bytes is therefore a function of the CHECKOUT, not of the content: an audit that
seals a text artifact by raw bytes cannot be re-executed from a clone whose line endings
differ from the machine that sealed it (G326; the defect was found by the G303 verifier at
the `detections_sha256` assertion in `scripts/platformkit/tracking/g298_audit.py`).

Use `sha256_lf` for any artifact git may translate (.md .csv .json .txt .py). Keep raw
`hashlib.sha256(path.read_bytes())` for binaries -- video, images, weights, parquet -- where
git stores the bytes verbatim and normalization would be wrong.

A committed seal is only reproducible through this helper if it was itself taken on LF bytes.
Switching an existing site to `sha256_lf` REQUIRES checking that first: see the hash-delta rule
in `docs/evidence/tracking/g326_prereg_2026-09-07.md`. Never edit a committed seal to make an
assertion pass.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_lf(path: Path | str) -> str:
    """SHA-256 of the file's bytes with CRLF line endings normalized to LF.

    Byte-level, so it makes no encoding assumption and is idempotent on LF bytes. A lone CR
    is left alone: git's own text translation only rewrites CRLF, and matching it exactly is
    what keeps this digest equal to the one the object store would produce.
    """
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
