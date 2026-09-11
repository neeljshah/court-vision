"""Preparation-only record builders for the G411 exact-PTS audit."""
from __future__ import annotations

import hashlib
from pathlib import Path


G401_DRAW = "docs/evidence/tracking/g401_fps_cap_duration_shadow_2026-09-11/draw.csv"
G408_ROOT = "docs/evidence/tracking/g408_pts_duration_stop_proposal_2026-09-11"
PREREG = "docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/prereg.md"


def resolve_worktree_path(path_text: str, root: Path) -> Path:
    """Resolve a cited worktree-prefixed path under this worktree root."""
    normalized = path_text.replace("\\", "/")
    marker = "/nba-track-"
    if marker in normalized:
        tail = normalized.split(marker, 1)[1]
        slash = tail.find("/")
        if slash >= 0:
            normalized = tail[slash + 1:]
    candidate = Path(normalized)
    return candidate if candidate.is_absolute() else root / candidate


def sha256_path(path: Path) -> str:
    """Hash one file without opening a store directory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prereg_seal_is_valid(path: Path) -> bool:
    """Validate a prereg file after normalizing CRLF to LF, never via git."""
    payload = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    seal_prefix = b"\nSEAL sha256 "
    position = payload.rfind(seal_prefix)
    if position < 0:
        return False
    declared = payload[position + len(seal_prefix):].strip()
    if len(declared) != 64:
        return False
    return hashlib.sha256(payload[:position + 1]).hexdigest().encode("ascii") == declared


def preparation_inventory(root: Path) -> dict[str, object]:
    """Return paths needed by the later finisher; this does no measurement."""
    required = (G401_DRAW, G408_ROOT + "/paired_stops.csv", PREREG)
    return {"mode": "PREPARE_ONLY", "required_paths": list(required),
            "missing_paths": [item for item in required if not (root / item).exists()],
            "prereg_seal_valid": prereg_seal_is_valid(root / PREREG)}
