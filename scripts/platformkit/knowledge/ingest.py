"""scripts.platformkit.knowledge.ingest -- walk vault + memory -> list[NoteChunk].

One chunk per note (no sub-chunking; vault notes are already atomic concept nodes).
Sources: vault/_Organized/{NBA,MLB,Soccer,Tennis}, _Index digests (VAULT_INDEX),
and the auto-memory dir (MEMORY) so "what do we know about X" can pull from memory.

Each note -> NoteChunk with a deterministic OFFLINE contextual prefix (situating
sentence from sport+category+title+tags). The Haiku-Batches upgrade replaces the
prefix only (set chunk.contextual then call build_embed_text); see contextual.py.

ASCII only. Per-file test: tests/test_ingest.py
"""
from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import config

try:
    import yaml as _yaml

    def _load_yaml(text: str) -> dict:
        try:
            return _yaml.safe_load(text) or {}
        except Exception:
            return {}
except ImportError:  # pragma: no cover - PyYAML is normally present
    def _load_yaml(text: str) -> dict:
        out: dict = {}
        for line in text.splitlines():
            m = re.match(r"^(\w[\w\-]*):\s*(.*)", line)
            if not m:
                continue
            key, val = m.group(1), m.group(2).strip()
            if val.startswith("[") and val.endswith("]"):
                out[key] = [i.strip().strip("\"'") for i in val[1:-1].split(",")
                            if i.strip()]
            elif val:
                out[key] = val
        return out


@dataclass
class NoteChunk:
    """One atomic chunk == one vault note or memory file."""
    note_id: str            # "NBA/Archetypes/3_and_d_wing" | "MEMORY/feedback_foo"
    sport: str              # NBA | MLB | Soccer | Tennis | VAULT_INDEX | MEMORY
    category: str           # folder name, e.g. "Archetypes" | "_Index" | "memory"
    title: str              # H1 (or stem fallback)
    tags: List[str] = field(default_factory=list)
    body: str = ""          # markdown minus frontmatter
    related: List[str] = field(default_factory=list)  # ## Related wikilink stems
    contextual: str = ""    # situating prefix (offline template or Haiku)
    embed_text: str = ""    # contextual + title + body (BM25/TF-IDF surface)
    content_sha256: str = ""
    mtime: float = 0.0
    embedded_with: str = "tfidf-baseline"


_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_WIKI_RE = re.compile(r"\[\[([^|\]#]+)")
_RELATED_RE = re.compile(r"##\s+Related\b.*?(?=^##|\Z)", re.DOTALL | re.MULTILINE)
# The conceptual core of a note (high signal for conceptual queries); the rest of
# the body (Stat Signature numbers, Conditions) adds noise so it stays single-weight.
_CORE_RE = re.compile(
    r"##\s+(?:Summary|Mechanism|Concept|Definition)\b(.*?)(?=^##|\Z)",
    re.DOTALL | re.MULTILINE)


def _core_text(body: str) -> str:
    return " ".join(m.strip() for m in _CORE_RE.findall(body))


def _ascii(text: str) -> str:
    return text.encode("ascii", errors="replace").decode("ascii")


def _split_frontmatter(raw: str):
    m = _FM_RE.match(raw)
    if not m:
        return {}, raw
    return _load_yaml(m.group(1)), raw[m.end():]


def _first_h1(body: str) -> str:
    m = _H1_RE.search(body)
    return m.group(1).strip() if m else ""


def _extract_related(body: str) -> List[str]:
    sec = _RELATED_RE.search(body)
    if not sec:
        return []
    return [lnk.strip().replace("\\", "/").split("/")[-1]
            for lnk in _WIKI_RE.findall(sec.group(0)) if lnk.strip()]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def _offline_prefix(chunk: NoteChunk) -> str:
    tags_str = ", ".join(chunk.tags[:4]) if chunk.tags else "concept"
    return _ascii(config.CTX_TEMPLATE.format(
        sport=chunk.sport, title=chunk.title, category=chunk.category, tags=tags_str))


def build_embed_text(chunk: NoteChunk) -> str:
    """contextual prefix + (weighted) title + (weighted) conceptual core + full body.

    The title is the strongest discriminator for these atomic concept nodes, so it
    is repeated TITLE_WEIGHT times; the Summary/Mechanism core is repeated CORE_WEIGHT
    times to lift the conceptual vocabulary over the numeric Stat-Signature noise; the
    full body adds recall depth. Call after (re)setting chunk.contextual."""
    prefix = chunk.contextual or _offline_prefix(chunk)
    title_block = "\n".join([chunk.title] * config.TITLE_WEIGHT) if chunk.title else ""
    core = _core_text(chunk.body)
    core_block = "\n".join([core] * config.CORE_WEIGHT) if core else ""
    parts = (prefix, title_block, core_block, chunk.body)
    return _ascii("\n".join(p for p in parts if p))


def parse_note(path: Path, sport: str, root: Path) -> NoteChunk:
    """Parse one .md file into a NoteChunk (ASCII-clean). note_id = sport/relpath."""
    try:
        raw = _ascii(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        raw = ""
    fm, body = _split_frontmatter(raw)
    title = _ascii(_first_h1(body) or path.stem.replace("_", " ").replace("-", " "))
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    tags = [str(t) for t in (tags or [])]
    try:
        rel = str(path.relative_to(root).with_suffix("")).replace("\\", "/")
        note_id = f"{sport}/{rel}"
    except ValueError:
        note_id = f"{sport}/{path.stem}"
    chunk = NoteChunk(
        note_id=note_id, sport=sport, category=path.parent.name, title=title,
        tags=tags, body=body, related=_extract_related(body),
        content_sha256=_sha256(raw),
        mtime=path.stat().st_mtime if path.exists() else 0.0)
    chunk.embed_text = build_embed_text(chunk)
    return chunk


def _walk(root: Path, sport: str, force_category: Optional[str] = None,
          recurse: bool = True) -> List[NoteChunk]:
    if not root.is_dir():
        return []
    files = sorted(root.rglob("*.md") if recurse else root.glob("*.md"))
    out: List[NoteChunk] = []
    for md in files:
        try:
            c = parse_note(md, sport, root)
            if force_category:
                c.category = force_category
            out.append(c)
        except Exception as exc:  # noqa: BLE001
            print(f"[ingest] WARN skip {md}: {exc}", file=sys.stderr)
    return out


def walk_sport(sport: str, vault_root: Optional[Path] = None) -> List[NoteChunk]:
    vr = vault_root or config.VAULT_ROOT
    return _walk(vr / sport, sport)


def walk_index(vault_root: Optional[Path] = None) -> List[NoteChunk]:
    vr = vault_root or config.VAULT_ROOT
    return _walk(vr / "_Index", "VAULT_INDEX", force_category="_Index")


def walk_memory(memory_dir: Optional[Path] = None) -> List[NoteChunk]:
    md = memory_dir or config.MEMORY_DIR
    if not md.is_dir():
        print(f"[ingest] WARN memory dir missing: {md}", file=sys.stderr)
        return []
    return _walk(md, "MEMORY", force_category="memory", recurse=False)


def build_corpus(sports: Optional[tuple] = None, include_index: bool = True,
                 include_memory: bool = True, vault_root: Optional[Path] = None,
                 memory_dir: Optional[Path] = None) -> List[NoteChunk]:
    """Walk all sources -> flat list[NoteChunk]."""
    if sports is None:
        sports = config.SPORTS
    chunks: List[NoteChunk] = []
    for sport in sports:
        sc = walk_sport(sport, vault_root)
        print(f"[ingest] {sport}: {len(sc)} notes", file=sys.stderr)
        chunks.extend(sc)
    if include_index:
        ic = walk_index(vault_root)
        print(f"[ingest] VAULT_INDEX: {len(ic)} notes", file=sys.stderr)
        chunks.extend(ic)
    if include_memory:
        mc = walk_memory(memory_dir)
        print(f"[ingest] MEMORY: {len(mc)} notes", file=sys.stderr)
        chunks.extend(mc)
    print(f"[ingest] total: {len(chunks)} chunks", file=sys.stderr)
    return chunks


def save_corpus_parquet(chunks: List[NoteChunk], out_path: Path) -> None:
    import pandas as pd
    rows = [{
        "note_id": c.note_id, "sport": c.sport, "category": c.category,
        "title": c.title, "tags": c.tags, "body": c.body, "related": c.related,
        "contextual": c.contextual, "embed_text": c.embed_text,
        "content_sha256": c.content_sha256, "mtime": c.mtime,
        "embedded_with": c.embedded_with,
    } for c in chunks]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(str(out_path), index=False)
    print(f"[ingest] saved {len(rows)} rows -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    corpus = build_corpus()
    print(f"Ingested {len(corpus)} notes")
    save_corpus_parquet(corpus, config.CORPUS_PARQUET)
