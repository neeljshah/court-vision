"""
brain_crosslinks.py — Cross-link pass for the person-free intelligence brain.

Appends / replaces a "## Related" section on each intelligence note in
vault/_Organized/<SPORT>/, turning the tree from islands into a linked graph.

Public API:
    build_crosslinks(organized_root, write=True) -> dict
    Returns: {"n_files_scanned", "n_linked", "by_sport": {...}, "note"}

No pandas, no network, no edge claims. Pure filesystem + string ops. Idempotent.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import NamedTuple

SPORTS = ("NBA", "MLB", "Soccer", "Tennis")

# Tokens that must never appear in a generated link target.
_EDGE_RE = re.compile(
    r"\b(edge|bet|wager|roi|clv|kelly|sharp|odds|vig|pick|arb|player|person)\b",
    re.IGNORECASE,
)
_RELATED_HDR = "## Related"

# node_type → affinitive node types (priority order)
_AFFINITY: dict[str, tuple[str, ...]] = {
    "Driver":    ("WhatWins", "Mechanism", "Archetype", "Index"),
    "Mechanism": ("Driver", "WhatWins", "Archetype", "Scheme"),
    "Archetype": ("Scheme", "WhatWins", "Mechanism", "Driver"),
    "Scheme":    ("Archetype", "Mechanism", "WhatWins"),
    "Trend":     ("WhatWins", "Driver", "Scheme", "Index"),
    "Identity":  ("Archetype", "Scheme", "WhatWins"),
    "WhatWins":  ("Driver", "Mechanism", "Archetype"),
    "Digest":    ("WhatWins", "Driver", "Mechanism", "Index"),
    "Validated": ("WhatWins", "Index"),
    "Index":     ("WhatWins", "Digest"),
}


class NoteInfo(NamedTuple):
    path: Path
    sport: str
    node_type: str   # Driver|Mechanism|Archetype|Scheme|Trend|Identity|
                     # WhatWins|Digest|Index|Validated
    tokens: frozenset  # lowercase alpha tokens from stem


def _tokens(path: Path) -> frozenset:
    return frozenset(re.findall(r"[a-z]+", path.stem.lower()))


def _classify(md: Path, sport_root: Path) -> str:
    parts = md.relative_to(sport_root).parts
    if len(parts) == 1:
        return {"_WhatWins.md": "WhatWins", "_Digest.md": "Digest",
                "_Index.md": "Index", "_Validated_Improvements.md": "Validated",
                }.get(parts[0], "")
    folder = parts[0]
    return {"Drivers": "Driver", "Mechanisms": "Mechanism",
            "Archetypes": "Archetype", "Schemes": "Scheme",
            "Trends": "Trend", "Teams": "Identity"}.get(folder, "")


def _collect(sport_root: Path) -> list[NoteInfo]:
    notes = []
    for md in sport_root.rglob("*.md"):
        nt = _classify(md, sport_root)
        if nt:
            notes.append(NoteInfo(md, sport_root.name, nt, _tokens(md)))
    return notes


def _overlap(a: NoteInfo, b: NoteInfo) -> float:
    u = a.tokens | b.tokens
    return len(a.tokens & b.tokens) / len(u) if u else 0.0


def _safe_link(from_path: Path, target: Path) -> str | None:
    if _EDGE_RE.search(target.stem):
        return None
    try:
        rel = target.relative_to(from_path.parent).as_posix()
    except ValueError:
        # Compute manual relative path when parents diverge.
        common_len = sum(1 for a, b in zip(from_path.parent.parts, target.parts)
                        if a == b)
        up = len(from_path.parent.parts) - common_len
        rel = "../" * up + "/".join(target.parts[common_len:])
    return f"[[{rel}|{target.stem}]]"


def _pick_links(note: NoteInfo, pool: list[NoteInfo]) -> list[Path]:
    seen = {note.path}
    picked: list[Path] = []

    def add(p: Path) -> None:
        if p not in seen and p.exists() and not _EDGE_RE.search(p.stem):
            seen.add(p); picked.append(p)

    by_type: dict[str, list[NoteInfo]] = {}
    for c in pool:
        if c.path != note.path:
            by_type.setdefault(c.node_type, []).append(c)

    # Anchor: sport _Index then _WhatWins.
    for c in by_type.get("Index", []):
        add(c.path)
    if note.node_type != "WhatWins":
        for c in by_type.get("WhatWins", []):
            add(c.path)

    # Affine types by overlap.
    for atype in _AFFINITY.get(note.node_type, ()):
        if len(picked) >= 6:
            break
        for c in sorted(by_type.get(atype, []),
                        key=lambda x: _overlap(note, x), reverse=True):
            if len(picked) >= 6:
                break
            add(c.path)

    # Fill remainder.
    for c in sorted([c for c in pool if c.path not in seen],
                    key=lambda x: _overlap(note, x), reverse=True):
        if len(picked) >= 6:
            break
        if not _EDGE_RE.search(c.path.stem):
            add(c.path)

    return picked[:6]


def _related_block(note: NoteInfo, link_paths: list[Path]) -> str:
    lines = [_RELATED_HDR, ""]
    for lp in link_paths:
        lk = _safe_link(note.path, lp)
        if lk:
            lines.append(f"- {lk}")
    lines.append("")
    return "\n".join(lines)


def _strip_related(text: str) -> str:
    """Remove an existing ## Related section (everything from the header to EOF
    or the next ## heading), so replacement is idempotent."""
    marker = f"\n\n{_RELATED_HDR}"
    idx = text.find(marker)
    if idx == -1:
        # Try start-of-string edge case.
        if text.startswith(_RELATED_HDR):
            idx = 0
            return ""
        return text
    # Keep everything before the marker; find next ## heading after it.
    before = text[:idx]
    after = text[idx + len(marker):]
    # Look for next top-level/section heading after the Related block.
    next_hdr = re.search(r"\n##", after)
    if next_hdr:
        return before + "\n\n" + after[next_hdr.start() + 1:]
    return before


def _apply(path: Path, block: str, write: bool) -> bool:
    original = path.read_text(encoding="utf-8")
    base = _strip_related(original).rstrip()
    new_body = base + "\n\n" + block
    if new_body == original:
        return False
    if write:
        path.write_text(new_body, encoding="utf-8")
    return True


def build_crosslinks(organized_root, write: bool = True) -> dict:
    """
    Walk vault/_Organized/<SPORT>/ and append/replace a ## Related section.

    Args:
        organized_root: Path to vault/_Organized/
        write: False = compute link plan only (dry-run, no file changes).
    Returns:
        {"n_files_scanned", "n_linked", "by_sport": {...}, "note"}
    """
    root = Path(organized_root)
    by_sport: dict[str, dict] = {}
    total_scanned = total_linked = 0

    for sport in SPORTS:
        sport_root = root / sport
        if not sport_root.is_dir():
            continue
        notes = _collect(sport_root)
        linked = 0
        for note in notes:
            lp = _pick_links(note, notes)
            if lp:
                changed = _apply(note.path, _related_block(note, lp), write)
                if changed or not write:
                    linked += 1
        by_sport[sport] = {"scanned": len(notes), "linked": linked}
        total_scanned += len(notes)
        total_linked += linked

    return {
        "n_files_scanned": total_scanned,
        "n_linked": total_linked,
        "by_sport": by_sport,
        "note": (
            "Intelligence / calibration only — NOT a market edge. "
            "Cross-links are concept/structure links, not predictions."
        ),
    }


if __name__ == "__main__":  # pragma: no cover
    import argparse, json
    p = argparse.ArgumentParser(description="Cross-link intelligence notes.")
    p.add_argument("organized_root", help="Path to vault/_Organized/")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    print(json.dumps(build_crosslinks(a.organized_root, write=not a.dry_run), indent=2))
