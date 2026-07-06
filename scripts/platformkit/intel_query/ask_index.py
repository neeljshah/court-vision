"""Lazy per-family `.index.jsonl` routing for ask.py's TOP_N fast path
(spec sec 4 SERVING AT SCALE, LANE L-D).

Split out of ask.py to respect the <=300 LOC/file rail (ask.py was already
552 lines before this lane touched it -- same precedent as
claims_validator.py -> claims_validator_batch.py). ask.py imports
`index_top_n_lookup` and calls it BEFORE its own `load_verified_claims()`
full-load path; a None return means "the index path cannot answer this
question," and the caller must fall through to the existing full-load
behavior unchanged -- this module never decides "unanswerable" itself.

Never weakens VERIFIED-only: an index line with verdict != VERIFIED is
skipped exactly as `load_verified_claims` already skips non-VERIFIED rows.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.platformkit.intel_query.claims_index import discover_families, is_index_fresh

VERIFIED = "VERIFIED"


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def seek_claim_row(claims_path: Path, byte_offset: int) -> dict[str, Any] | None:
    """Read exactly ONE line at byte_offset from claims_path. None on any
    I/O trouble (missing file, offset past EOF after a concurrent rewrite,
    malformed JSON) -- caller must fall back to full load, never crash."""
    try:
        with open(claims_path, "rb") as f:
            f.seek(byte_offset)
            line = f.readline()
        return json.loads(line)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def index_top_n_lookup(parsed, claims_dir: Path, repo_root: Path) -> dict[str, Any] | None:
    """Spec sec 4 fast path: route via each family's small `.index.jsonl`
    instead of `load_verified_claims`'s full O(all-claims) parse. Returns
    the SAME winning claim ROW `load_verified_claims` + `_answer_top_n`
    would have picked (kind=ranking, VERIFIED, most-recent computed_at
    among metric/window-matching candidates), or None if the index path
    cannot answer -- callers must then fall back to the full-load path,
    never treat None as "unanswerable" themselves.

    A family is skipped (not treated as an error) when: no fresh index
    exists for it (is_index_fresh False covers missing/stale/malformed),
    or no VERIFIED index line matches the question's hints. Skipping is
    fail-open PER FAMILY, matching load_verified_claims' own per-store
    fail-open convention -- one stale/missing index never blocks another
    family's fresh index from answering.
    """
    best_row: dict[str, Any] | None = None
    best_claims_path: Path | None = None
    best_computed_at = ""
    for family in discover_families(claims_dir):
        if not is_index_fresh(family, claims_dir):
            continue
        index_path = claims_dir / f"{family}.index.jsonl"
        claims_path = claims_dir / f"{family}.jsonl"
        try:
            with open(index_path, "r", encoding="ascii", errors="strict") as f:
                index_lines = f.readlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in index_lines:
            line = line.strip()
            if not line:
                continue
            try:
                idx_row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if idx_row.get("verdict") != VERIFIED:
                continue
            if parsed.metric_hints and idx_row.get("metric") not in parsed.metric_hints:
                continue
            if parsed.window_hint and idx_row.get("window") != parsed.window_hint:
                continue
            computed_at = idx_row.get("computed_at") or ""
            if computed_at <= best_computed_at:
                continue
            candidate_row = seek_claim_row(claims_path, idx_row.get("byte_offset", 0))
            if candidate_row is None or candidate_row.get("kind") != "ranking":
                continue
            best_row, best_claims_path, best_computed_at = candidate_row, claims_path, computed_at
    if best_row is None:
        return None
    return dict(
        best_row,
        _validator_source=_display_path(claims_dir / f"{best_claims_path.stem}_validation.json", repo_root),
        _producer_source=_display_path(best_claims_path, repo_root),
    )
