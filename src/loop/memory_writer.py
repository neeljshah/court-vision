"""MEMORY-WRITER -- persist durable findings to auto-memory + the Obsidian vault.

Implements ARM-B persistence step: a validated signal or atlas discovery is written
to the cross-conversation auto-memory layer (``~/.claude/.../memory/``) with the
YAML frontmatter described in spec_intel_memory.md section 3.1, an index line
added/refreshed in MEMORY.md, an optional vault atlas note, and PLAYER/TEAM index
refresh via ``scripts/loop/build_profile_indices.py``.

DEDUP is the hard rule: SHARPEN an existing note, never duplicate.
"""
from __future__ import annotations

import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

MEMORY_DIR = Path.home() / ".claude" / "projects" / "C--Users-neelj" / "memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
ROOT = Path(__file__).resolve().parents[2]
VAULT = ROOT / "vault"

_PYTHON = sys.executable

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _note_path(note_type: str, slug: str) -> Path:
    """Return the canonical path for a memory note."""
    return MEMORY_DIR / f"{note_type}_{slug}.md"


def _build_frontmatter(note_type: str, slug: str, title: str,
                        origin_session_id: Optional[str]) -> str:
    """Return the YAML frontmatter block as a string."""
    sid = origin_session_id or "auto"
    return (
        f"---\n"
        f"name: {note_type}_{slug}\n"
        f'description: "{title}"\n'
        f"metadata:\n"
        f"  node_type: memory\n"
        f"  type: {note_type}\n"
        f"  originSessionId: {sid}\n"
        f"---\n"
    )


def _render_note(note_type: str, slug: str, title: str, body: str,
                 origin_session_id: Optional[str]) -> str:
    """Render the full note content."""
    fm = _build_frontmatter(note_type, slug, title, origin_session_id)
    return f"{fm}\n# {title}\n\n{body.strip()}\n"


def _find_existing_note(slug: str, note_type: str) -> Optional[Path]:
    """Locate an existing topic note for dedup (by ``<note_type>_<slug>.md``)."""
    candidate = _note_path(note_type, slug)
    if candidate.exists():
        return candidate
    # Also search for any file ending with ``_<slug>.md`` in the memory dir to
    # handle note_type mismatches (e.g. project vs feedback for the same slug).
    for p in MEMORY_DIR.glob(f"*_{slug}.md"):
        if p.is_file():
            return p
    return None


def _sharpened_body(existing_path: Path, new_body: str,
                     as_of: Optional[str] = None) -> str:
    """Merge an existing note body with a new update.

    Strategy: keep the existing body and APPEND a dated update section so
    history is preserved, provenance accumulates, and we never wipe prior content.
    This matches the "sharpen not duplicate" contract.
    """
    existing = existing_path.read_text(encoding="utf-8")
    # Strip the frontmatter + H1 title to get the existing body text.
    body_match = re.search(r"^---\n.*?---\n+# .+?\n+(.+)$", existing,
                            re.DOTALL | re.MULTILINE)
    existing_body = body_match.group(1).strip() if body_match else existing.strip()
    date_str = as_of or _dt.date.today().isoformat()
    update_section = (
        f"\n\n---\n*Updated {date_str}*\n\n{new_body.strip()}"
    )
    # Avoid appending identical content (idempotent re-runs).
    if new_body.strip() in existing_body:
        return existing_body
    return existing_body + update_section


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_finding(*, slug: str, title: str, body: str, note_type: str = "project",
                  index_line: str, origin_session_id: Optional[str] = None,
                  dry_run: bool = False) -> Path:
    """Write/UPDATE a durable auto-memory topic note + refresh the MEMORY.md index line.

    Args:
        slug:              topic slug; file becomes ``<note_type>_<slug>.md``.
        title:             human title for the H1 header and index link.
        body:              markdown body (real numbers, paths, as-of/provenance, gotchas).
        note_type:         "project" | "feedback" | "reference".
        index_line:        the <=200-char one-liner for ``## Recent feedback`` in MEMORY.md.
        origin_session_id: UUID written into the frontmatter originSessionId field.
        dry_run:           render and return the path but do NOT write any files.

    Returns:
        Path of the written/updated note file (even in dry_run mode).

    Notes:
        DEDUP: if a note for this slug already exists it is SHARPENED (update
        appended) rather than overwritten wholesale, so prior provenance is kept.
    """
    dest = _note_path(note_type, slug)
    existing = _find_existing_note(slug, note_type)

    if existing is not None and existing.exists():
        # SHARPEN: preserve the existing frontmatter + body, append update.
        existing_text = existing.read_text(encoding="utf-8")
        fm_match = re.match(r"(---\n.*?---\n)", existing_text, re.DOTALL)
        existing_fm = fm_match.group(1) if fm_match else _build_frontmatter(
            note_type, slug, title, origin_session_id
        )
        merged_body = _sharpened_body(existing, body)
        h1_match = re.search(r"# (.+?)\n", existing_text)
        existing_title = h1_match.group(1).strip() if h1_match else title
        content = f"{existing_fm}\n# {existing_title}\n\n{merged_body}\n"
        dest = existing  # write back to the existing path (may differ from dest)
    else:
        content = _render_note(note_type, slug, title, body, origin_session_id)

    if not dry_run:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        refresh_memory_index(index_line, slug=slug, title=title, dry_run=False)

    return dest


def write_vault_atlas_note(*, name: str, body: str, moc: str = "MOC-Research",
                           dry_run: bool = False) -> Optional[Path]:
    """Write/UPDATE ``vault/Intelligence/<name>_Atlas.md`` and link it in the MOC
    and ``vault/Intelligence/_Vault_Index.md``.

    Returns ``None`` (no-op) if the vault directory is absent (fresh clone).

    Args:
        name:    Atlas display name (e.g. "Shot_Profile"); used for filename + wikilink.
        body:    Markdown body of the atlas note.
        moc:     Which MOC file to link from (e.g. "MOC-Research").
        dry_run: Skip all file writes.
    """
    intel_dir = VAULT / "Intelligence"
    if not VAULT.exists() or not intel_dir.exists():
        return None

    note_path = intel_dir / f"{name}_Atlas.md"

    if not dry_run:
        if note_path.exists():
            # SHARPEN: append an update section.
            existing_body = _sharpened_body(note_path, body)
            date_str = _dt.date.today().isoformat()
            # Re-read the whole file to preserve header.
            existing_text = note_path.read_text(encoding="utf-8")
            h1_match = re.search(r"# .+?\n", existing_text)
            header = h1_match.group(0) if h1_match else f"# {name} Atlas\n"
            note_path.write_text(
                f"# {name} Atlas\n\n{existing_body}\n", encoding="utf-8"
            )
        else:
            note_path.write_text(
                f"# {name} Atlas\n\n{body.strip()}\n", encoding="utf-8"
            )

        # Link in vault_index if not already present.
        vault_index = intel_dir / "_Vault_Index.md"
        _add_vault_index_link(vault_index, name)

        # Link in MOC.
        moc_path = VAULT / f"{moc}.md"
        _add_moc_link(moc_path, name)

    return note_path


def refresh_memory_index(index_line: str, *, slug: Optional[str] = None,
                          title: Optional[str] = None,
                          dry_run: bool = False) -> None:
    """Insert/replace ONE index line under ``## Recent feedback`` (dedup by slug).

    The line is replaced if an existing line links to ``<*_slug>.md``; otherwise
    it is prepended immediately after the ``## Recent feedback`` header so the
    most-recent finding appears first.

    Args:
        index_line: the <=200-char one-liner (should contain a ``[title](file.md)`` link).
        slug:       used for dedup matching; if None, dedup is skipped.
        title:      optional title for building a default link text; unused if
                    ``index_line`` is already well-formed.
        dry_run:    do not write.
    """
    if not MEMORY_INDEX.exists():
        return  # MEMORY.md absent (fresh clone) — no-op.

    text = MEMORY_INDEX.read_text(encoding="utf-8")
    lines = text.split("\n")

    # Find the insertion header.
    header_pattern = re.compile(r"^##\s+Recent feedback", re.IGNORECASE)
    header_idx: Optional[int] = None
    for i, ln in enumerate(lines):
        if header_pattern.match(ln.strip()):
            header_idx = i
            break

    if header_idx is None:
        # No ## Recent feedback section — append one.
        lines.append("")
        lines.append("## Recent feedback")
        lines.append(f"- {index_line}")
        if not dry_run:
            MEMORY_INDEX.write_text("\n".join(lines), encoding="utf-8")
        return

    # Remove existing line that references the same slug/file (dedup).
    slug_pattern = re.compile(
        rf"[({slug})]" if slug else r"NOMATCH^"
    )
    file_ref = f"{slug}.md" if slug else None

    new_lines: List[str] = []
    removed = False
    for i, ln in enumerate(lines):
        if i > header_idx and file_ref and file_ref in ln:
            removed = True  # drop the old line
        else:
            new_lines.append(ln)
    lines = new_lines

    # Re-find the header index after possible removal.
    for i, ln in enumerate(lines):
        if header_pattern.match(ln.strip()):
            header_idx = i
            break

    # Insert after the header line (prepend to the list so most-recent is first).
    new_entry = f"- {index_line}"
    lines.insert(header_idx + 1, new_entry)

    if not dry_run:
        MEMORY_INDEX.write_text("\n".join(lines), encoding="utf-8")


def refresh_profile_indices(*, dry_run: bool = False) -> Dict[str, Any]:
    """Regenerate PLAYER_INDEX/TEAM_INDEX by running ``scripts/loop/build_profile_indices.py``.

    Returns a dict with keys ``{"player_index": Path, "team_index": Path, "rc": int}``.
    If the script is absent or dry_run=True, returns a stub with ``rc=-1``.
    """
    script = ROOT / "scripts" / "loop" / "build_profile_indices.py"
    player_index = ROOT / "data" / "cache" / "profiles" / "PLAYER_INDEX.json"
    team_index = ROOT / "data" / "cache" / "profiles" / "TEAM_INDEX.json"

    if dry_run or not script.exists():
        return {"player_index": player_index, "team_index": team_index, "rc": -1,
                "note": "dry_run or script absent"}

    env = {"NBA_OFFLINE": "1", **{k: v for k, v in
            __import__("os").environ.items()}}
    result = subprocess.run(
        [_PYTHON, str(script)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    return {
        "player_index": player_index,
        "team_index": team_index,
        "rc": result.returncode,
        "stdout": result.stdout[-2000:] if result.stdout else "",
        "stderr": result.stderr[-1000:] if result.stderr else "",
    }


# ---------------------------------------------------------------------------
# Private vault-link helpers
# ---------------------------------------------------------------------------

def _add_vault_index_link(vault_index_path: Path, name: str) -> None:
    """Append a wikilink for ``name`` to the vault index if not already present."""
    if not vault_index_path.exists():
        return
    text = vault_index_path.read_text(encoding="utf-8")
    link = f"[[{name}_Atlas]]"
    if link in text:
        return  # already linked — idempotent
    # Append under a Loop-generated section.
    section_header = "## Loop-Generated Atlases"
    if section_header not in text:
        text = text.rstrip() + f"\n\n{section_header}\n"
    text = text.rstrip() + f"\n- {link}\n"
    vault_index_path.write_text(text, encoding="utf-8")


def _add_moc_link(moc_path: Path, name: str) -> None:
    """Append a wikilink for ``name`` to the given MOC file if not already present."""
    if not moc_path.exists():
        return
    text = moc_path.read_text(encoding="utf-8")
    link = f"[[Intelligence/{name}_Atlas]]"
    if link in text:
        return
    section_header = "## Loop-Generated Atlases"
    if section_header not in text:
        text = text.rstrip() + f"\n\n{section_header}\n"
    text = text.rstrip() + f"\n{link}\n"
    moc_path.write_text(text, encoding="utf-8")
