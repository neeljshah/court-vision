"""scripts.platformkit.atlas.obsidian_emit — Sport-blind Obsidian-emit primitives.

Shared across all atlas generators so the ~20 duplicated helpers live in one place.

Public API
----------
slug(name) -> str
    Filesystem-safe slug: strip non-[\\w\\s-] chars, collapse whitespace to ``_``.

frontmatter(fields) -> str
    Render a YAML-frontmatter block (``---\\n...\\n---``) from an ordered mapping.
    Scalar values are written verbatim; list values become YAML list items
    (``  - item`` per line).  Pre-quoted strings (already wrapped in ``".."``)
    are emitted as-is.

write_note(path, body) -> pathlib.Path
    Idempotent note writer: mkdir -p + write_text utf-8.  Returns the path.

md_table(headers, rows) -> str
    GitHub-flavoured markdown table string (no trailing newline).

PROMOTION DISCIPLINE
--------------------
- Stdlib only (no numpy, pandas, or domain imports).
- F5-clean: zero imports from src.* / kernel.* / domains.* / scripts.platformkit.*.
- Sport-blind: no sport tokens, no betting/edge language.
- Every function has a known-value doctest comment for test_obsidian_emit.py.
"""
from __future__ import annotations

import pathlib
import re
from typing import Any, Dict, List, Sequence, Union

# ---------------------------------------------------------------------------
# Slug
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^\w\s-]")
_SPACE_RE = re.compile(r"[\s]+")


def slug(name: str) -> str:
    """Return a filesystem-safe slug from a display name.

    Removes characters that are not word chars, spaces, or hyphens; then
    collapses all whitespace runs to a single underscore.

    Examples::

        slug("Roger Federer")   -> "Roger_Federer"
        slug("ATP 2025!")       -> "ATP_2025"
        slug("  spaces  ")      -> "spaces"
        slug("O'Brien")         -> "OBrien"
    """
    s = _SLUG_RE.sub("", name).strip()
    return _SPACE_RE.sub("_", s)


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

def frontmatter(fields: Dict[str, Any]) -> str:
    """Render YAML frontmatter from an ordered dict.

    Rules (matching the format used by atlas_render.py):
    - Opening and closing ``---`` delimiters are included.
    - List values are rendered as indented YAML sequences::

          tags:
            - sport/tennis
            - atlas/index

    - All other values are written as ``key: value`` with no extra quoting.
      If you need a quoted value (e.g. ``corpus_span: "a → b"``), pass the
      pre-quoted string as the value (e.g. ``'"a → b"'``).

    Returns the full block including delimiters, with a trailing newline on
    the closing ``---`` line (i.e. the result ends with ``---\\n``).

    Example::

        frontmatter({"surface": "Hard", "tags": ["sport/tennis"]})
        # -> "---\\nsurface: Hard\\ntags:\\n  - sport/tennis\\n---"
    """
    lines: List[str] = ["---"]
    for key, val in fields.items():
        if isinstance(val, list):
            lines.append(f"{key}:")
            for item in val:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Note writer
# ---------------------------------------------------------------------------

def write_note(path: Union[str, pathlib.Path], body: str) -> pathlib.Path:
    """Write *body* to *path*, creating parent directories as needed.

    Idempotent: re-running with the same content overwrites the file with
    identical bytes (no append, no merge).

    Parameters
    ----------
    path:
        Destination file path (str or Path).
    body:
        Complete file content including trailing newline.

    Returns
    -------
    pathlib.Path
        The resolved path that was written.
    """
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Markdown table
# ---------------------------------------------------------------------------

def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Return a GitHub-flavoured markdown table string (no trailing newline).

    Parameters
    ----------
    headers:
        Column header labels.
    rows:
        Sequence of row sequences; each cell is converted to ``str``.

    Returns
    -------
    str
        The table as a string (no trailing newline).

    Example::

        md_table(["Name", "Elo"], [["Djokovic", 2100], ["Alcaraz", 2050]])
        # -> "| Name | Elo |\\n|------|-----|\\n| Djokovic | 2100 |\\n| Alcaraz | 2050 |"
    """
    header_cells = " | ".join(str(h) for h in headers)
    sep_cells = " | ".join("-" * max(len(str(h)), 3) for h in headers)
    lines: List[str] = [
        f"| {header_cells} |",
        f"|{sep_cells}|",
    ]
    for row in rows:
        cell_str = " | ".join(str(c) for c in row)
        lines.append(f"| {cell_str} |")
    return "\n".join(lines)


__all__ = ["slug", "frontmatter", "write_note", "md_table"]
