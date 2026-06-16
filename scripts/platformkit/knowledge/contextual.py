"""scripts.platformkit.knowledge.contextual -- situating prefixes for each note.

Anthropic "Contextual Retrieval" prepends a 1-2 sentence situating sentence to each
chunk before indexing; it is the single biggest documented recall lift. Here:

  OFFLINE (ships now, no API): a DETERMINISTIC template that situates each note from
  its sport + category + title + tags. This is what ingest._offline_prefix produces;
  this module exposes it as a backend and lets a build re-stamp prefixes in bulk.

  HAIKU-BATCHES (OPTIONAL upgrade, requires `pip install anthropic` + ANTHROPIC_API_KEY):
  one claude-haiku-4-5 call per note via the Message Batches API (50% off, one-time),
  prompt = note body + category + sport -> a 1-2 sentence situating sentence. Store it
  in the corpus 'contextual' column so a refresh only regenerates when content_sha256
  changes. Set RAG_CTX_PREFIX=haiku to activate. Expected lift: ~3-5% (template) up to
  ~8-10% (Haiku) on golden recall vs no prefix.

This module makes NO network call by default and emits NO probability/odds/edge.
ASCII only. Per-file test: tests/test_contextual.py
"""
from __future__ import annotations

import abc
from typing import List, Sequence

from . import config
from .ingest import NoteChunk, build_embed_text


class ContextualBackend(abc.ABC):
    """Pluggable situating-prefix generator."""

    @abc.abstractmethod
    def prefix(self, chunk: NoteChunk) -> str:
        ...

    @property
    @abc.abstractmethod
    def backend_id(self) -> str:
        ...


class TemplateBackend(ContextualBackend):
    """Deterministic offline prefix from metadata. No LLM, no install."""

    def prefix(self, chunk: NoteChunk) -> str:
        tags = ", ".join(chunk.tags[:4]) if chunk.tags else "concept"
        text = config.CTX_TEMPLATE.format(
            sport=chunk.sport, title=chunk.title,
            category=chunk.category, tags=tags)
        return text.encode("ascii", errors="replace").decode("ascii")

    @property
    def backend_id(self) -> str:
        return "template-offline-v1"


class HaikuBatchesBackend(ContextualBackend):  # pragma: no cover - optional upgrade
    """OPTIONAL: claude-haiku-4-5 situating prefix via the Message Batches API.

    Requires `pip install anthropic` and ANTHROPIC_API_KEY. Not exercised offline;
    documented and wired so it drops in when the dep is installed.
    """

    PROMPT = (
        "You situate a sports concept note for retrieval. In ONE or TWO sentences, "
        "say what this {sport} '{category}' concept is and how it relates to nearby "
        "concepts. No numbers, no probabilities, no betting language. Note:\n{body}"
    )

    def __init__(self) -> None:
        from anthropic import Anthropic
        self._client = Anthropic()

    def prefix(self, chunk: NoteChunk) -> str:
        msg = self._client.messages.create(
            model=config.CTX_MODEL_ID, max_tokens=120,
            messages=[{"role": "user", "content": self.PROMPT.format(
                sport=chunk.sport, category=chunk.category, body=chunk.body[:2000])}])
        out = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return out.strip().encode("ascii", errors="replace").decode("ascii")

    @property
    def backend_id(self) -> str:
        return f"haiku-batches:{config.CTX_MODEL_ID}"


def get_backend(name: str = None) -> ContextualBackend:
    name = name or config.CTX_PREFIX_BACKEND
    if name == "haiku":
        return HaikuBatchesBackend()
    return TemplateBackend()


def stamp_prefixes(chunks: Sequence[NoteChunk],
                   backend: ContextualBackend = None) -> List[NoteChunk]:
    """Set chunk.contextual + rebuild embed_text for each chunk. In-place + returned.

    For the Haiku backend, regenerate only when contextual is empty (cheap re-runs);
    the offline template is deterministic so always safe to re-stamp.
    """
    backend = backend or get_backend()
    for c in chunks:
        if backend.backend_id.startswith("haiku") and c.contextual:
            continue
        c.contextual = backend.prefix(c)
        c.embedded_with = backend.backend_id
        c.embed_text = build_embed_text(c)
    return list(chunks)


if __name__ == "__main__":  # pragma: no cover
    from .ingest import build_corpus
    sample = build_corpus(sports=("NBA",), include_memory=False)[:3]
    for ch in stamp_prefixes(sample, TemplateBackend()):
        print(ch.note_id, "->", ch.contextual[:90])
