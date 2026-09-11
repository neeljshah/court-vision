"""Preparation-time integrity helpers for the G403 sealed preregistration."""

from __future__ import annotations

import hashlib
from pathlib import Path


SEAL_PREFIX = "SEAL sha256 "


def lf_normalize(raw: bytes) -> bytes:
    """Return the contract's LF-normalized representation of a text artifact."""
    return raw.replace(b"\r\n", b"\n")


def prereg_seal(path: Path) -> str:
    """Compute the SHA-256 over LF bytes above a preregistration seal line."""
    normalized = lf_normalize(path.read_bytes())
    marker = b"\n" + SEAL_PREFIX.encode("ascii")
    marker_at = normalized.rfind(marker)
    if marker_at < 0:
        raise ValueError("missing-prereg-seal")
    body = normalized[: marker_at + 1]
    return hashlib.sha256(body).hexdigest()


def asserted_prereg_seal(path: Path) -> str:
    """Return the seal recorded in a preregistration after verifying its shape."""
    normalized = lf_normalize(path.read_bytes())
    lines = normalized.splitlines()
    if not lines or not lines[-1].startswith(SEAL_PREFIX.encode("ascii")):
        raise ValueError("seal-must-be-final-line")
    value = lines[-1][len(SEAL_PREFIX):].decode("ascii")
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("invalid-prereg-seal")
    return value


def verify_prereg_seal(path: Path) -> bool:
    """Verify a preregistration without relying on repository staging or history."""
    return prereg_seal(path) == asserted_prereg_seal(path)
