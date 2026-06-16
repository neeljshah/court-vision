"""scripts.platformkit.knowledge.text_utils -- dependency-free tokenizer + stemmer.

The vault concept notes and the natural-language queries use different surface forms
of the same idea ("deters" vs "deterrence", "blocking" vs "blocked", "shooting" vs
"shooter"). With no nltk/sentence-transformers available, a light deterministic
suffix stemmer collapses those forms so the TF-IDF lanes match them. It is applied
IDENTICALLY to the corpus and to queries (a callable passed as TfidfVectorizer's
`tokenizer`, so it must be a top-level importable function for pickling).

This module emits NO probability/odds/edge. ASCII only.
"""
from __future__ import annotations

import re
from typing import List

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9-]+")

# Order matters: try longer suffixes first. Keep stems >= 3 chars.
_SUFFIXES = (
    "ization", "iveness", "fulness", "ousness", "ational", "tional",
    "ation", " players", "player", "ments", " ness", "ingly", "edly",
    "ement", "ences", " ence", "ances", "ance", "ically", "ical",
    "ities", "ity", "ing", "ed", "ly", "es", "s", "er", "ers",
    "ness", "ment", "ence", "ance",
)


def _stem_atom(tok: str) -> str:
    """Strip a common English suffix once (longest match), keeping >=3-char stems."""
    for suf in _SUFFIXES:
        suf = suf.strip()
        if len(suf) >= 1 and tok.endswith(suf) and len(tok) - len(suf) >= 3:
            base = tok[: -len(suf)]
            # collapse a trailing doubled consonant (running -> run)
            if len(base) >= 4 and base[-1] == base[-2] and base[-1] not in "aeiou":
                base = base[:-1]
            return base
    return tok


def _stem(tok: str) -> List[str]:
    """Stem one raw token -> list of stems. A hyphenated compound yields the whole
    stemmed compound AND each stemmed part, so "rest-defense" matches a query with
    separate "rest" and "defense" words (and vice-versa)."""
    if "-" in tok:
        parts = [p for p in tok.split("-") if p]
        out = ["-".join(_stem_atom(p) for p in parts)]
        if len(parts) > 1:
            out += [_stem_atom(p) for p in parts]
        return out
    return [_stem_atom(tok)]


def stem_tokenizer(text: str) -> List[str]:
    """TfidfVectorizer-compatible tokenizer: lowercase -> word tokens -> stems.

    Must be a module-level function so a fitted vectorizer pickles cleanly.
    """
    out: List[str] = []
    for t in _WORD_RE.findall(text.lower()):
        out.extend(_stem(t))
    return out


def query_terms(text: str) -> List[str]:
    """Stemmed content tokens of a query (for the exact title/category boost)."""
    return stem_tokenizer(text)
