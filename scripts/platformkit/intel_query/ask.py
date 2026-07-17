"""ask(question) -> dict, answering ONLY from VERIFIED claims (mission spine 5).

Deterministic tool surface: an external LLM calls ask() like any other tool.
NO LLM call inside this module -- routing is families.classify (keyword/regex),
and answers come straight from claim rows an INDEPENDENT validator marked
VERIFIED. Sources joined per pair in CLAIM_SOURCE_PAIRS: a validation-summary
JSON (per-claim_id verdict) + the producer claims JSONL it validates (full
claim rows: criteria/ranking or gate_module/verdict, source_files, caveats).

HONEST UNANSWERABLE: no VERIFIED claim covers the question, or the family
can't be classified -> {"answerable": False, "reason": ..., "nearest_supported_families": [...]}.
Never falls back to raw computation; never answers from an UNVERIFIABLE/MISMATCH claim.

This module is the thin facade: claim loading + the ask() dispatcher live
here; the per-family answer formatters (top_n/entity_lookup/provenance/
gate_verdict + the best_x/shooter_profile hooks) live in ask_families.py,
and the FIT family (compose_fit) lives in ask_fit.py -- both split out to
respect the <=300 LOC/file rail and re-exported here so every existing
caller/test import path is unchanged.

CLI:
    python -m scripts.platformkit.intel_query.ask "Who are the top 5 best shooters (composite) in window=last_20?"
    python -m scripts.platformkit.intel_query.ask --demo
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterator

from scripts.platformkit.intel_query import ask_index
from scripts.platformkit.intel_query.families import (
    FAMILY_ENTITY_LOOKUP,
    FAMILY_GATE_VERDICT,
    FAMILY_PROVENANCE,
    FAMILY_TOP_N,
    classify,
    describe_families,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
INTEL_CLAIMS_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"

# The generic ask() dispatch (entity_lookup/provenance/gate_verdict) can't be
# scoped to a fixed store set the way the composers are -- it searches every
# store. Cap physical lines read PER FILE so a store that later grows to
# millions of rows can't OOM the surface. 100k comfortably exceeds every
# current store (largest is nba_player_box_rate at 59,710 lines), so this
# truncates nothing today -- it is forward-defense, not a behavior change.
# ponytail: a line cap; the fat store is few-huge-lines so scoping (below),
# not this cap, is what actually bounds today's memory.
_QUERY_SURFACE_MAX_LINES = 100_000

# One producer JSONL predates the "<stem>_validation.json in the same
# directory" naming convention every OTHER store follows, and its
# validation summary lives under data/frontend/ops/ instead. This is the
# ONE static fallback the discovery below applies -- every store added
# after this map was written (wnba/tennis_v3/catcher_framing/platoon_split/
# umpire_zone/nba_fit_ingredient/...) is found by the glob with zero
# registration here.
# (nba_shooting_claims.jsonl was REMOVED from this map 2026-07-07: its legacy
# shared path data/frontend/ops/intel_claims_validation.json had been
# clobbered by a later quality-claims validator run using the same
# DEFAULT_OUTPUT, silently hiding all 20 of its VERIFIED claims from ask().
# It now pairs with the convention-named in-directory
# nba_shooting_claims_validation.json like every other store.)
_LEGACY_VALIDATION_OVERRIDES: dict[str, Path] = {
    "gate_verdict_claims.jsonl": REPO_ROOT / "data" / "frontend" / "ops" / "intel_verdict_claims_validation.json",
}


def discover_claim_source_pairs(claims_dir: Path = INTEL_CLAIMS_DIR) -> tuple[tuple[Path, Path], ...]:
    """AUTOMATIC (validation-summary, producer-claims) discovery over EVERY
    *.jsonl file directly under claims_dir (data/cache/intel_claims/) -- so a
    new claim store lands in ask() the moment its producer + validator both
    write to disk, with NO per-store registration here. Every *.jsonl in
    this directory today (nba/wnba/tennis/mlb/soccer, 13 files) is a
    producer-claims file, not an incidental cache artifact, so this one
    glob is the whole discovery mechanism (the ONE fallback below is a
    static 2-entry override for names that predate the naming convention,
    not a second glob).

    Pairing rule: <stem>.jsonl pairs with <stem>_validation.json in the SAME
    directory if that file exists; else _LEGACY_VALIDATION_OVERRIDES (2
    pre-convention stores). A *.jsonl with NEITHER is silently skipped --
    unvalidated claims must stay invisible to ask(), not error the whole
    discovery pass (fail-open per-file, matching load_verified_claims'
    existing "missing validation JSON -> skip" behavior for a named pair).

    Deterministic order: sorted by claims-file name, so iteration order
    (and therefore any tie-break that depends on it) is stable across runs.
    """
    pairs: list[tuple[Path, Path]] = []
    if not claims_dir.exists():
        return tuple(pairs)
    for claims_path in sorted(claims_dir.glob("*.jsonl")):
        validation_path = _LEGACY_VALIDATION_OVERRIDES.get(claims_path.name)
        if validation_path is None:
            candidate = claims_path.with_name(claims_path.stem + "_validation.json")
            if candidate.exists():
                validation_path = candidate
        if validation_path is not None:
            pairs.append((validation_path, claims_path))
    return tuple(pairs)


# Populated once at import time (module-level constant, matching the old
# static-tuple contract every caller/test already expects) but produced by
# discover_claim_source_pairs's glob rather than a hand-maintained list.
CLAIM_SOURCE_PAIRS: tuple[tuple[Path, Path], ...] = discover_claim_source_pairs()


def pairs_for_claim_stores(store_names: tuple[str, ...],
                           pairs: tuple[tuple[Path, Path], ...] | None = None,
                           ) -> tuple[tuple[Path, Path], ...]:
    """Subset of claim-source pairs whose claims-file NAME is in store_names.
    Composers MUST load through this: bulk rate stores (nba_player_box_rate
    et al) are GBs, and a bare load_verified_claims() whole-loads every store
    (live MemoryError, 2026-07-07). pairs=None re-reads the CURRENT
    module-level CLAIM_SOURCE_PAIRS at call time (monkeypatch-safe, same
    contract as load_verified_claims)."""
    if pairs is None:
        pairs = CLAIM_SOURCE_PAIRS
    wanted = set(store_names)
    return tuple(p for p in pairs if p[1].name in wanted)


VERIFIED = "VERIFIED"


def _ascii_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _load_json(path: Path) -> dict[str, Any] | None:
    """Fail-open per-file: a missing OR malformed (mid-write/truncated/
    corrupt) validation-summary JSON must never crash ask() for every OTHER
    store -- treat it exactly like "not yet available" (None), same as the
    missing-file case. A shared validator output path can be caught
    mid-rewrite by a concurrent producer; that store's claims simply stay
    invisible this call, they do not take the whole surface down."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="ascii", errors="strict") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def _display_path(path: Path) -> str:
    """Repo-relative string when possible, else the raw path (fixtures
    live under a tmp_path outside REPO_ROOT)."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_jsonl(path: Path, max_lines: int | None = None) -> Iterator[dict[str, Any]]:
    """Per-LINE fail-open STREAMING reader: yields one parsed row at a time so
    a GB-scale store is never materialized whole. The old readlines() pulled a
    2.8GB store into a single str list -> the 2026-07-07 MemoryError; the
    caller filters row-by-row and keeps only what it wants. One malformed line
    (a concurrent writer caught mid-append/mid-flush) is skipped, not raised.
    `max_lines` caps physical lines READ per file (None = no cap): a full-scan
    consumer passes None; a query surface passes a cap so a store that grows to
    millions of lines can't run it out of memory."""
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="ascii", errors="strict") as f:
            for i, line in enumerate(f):
                if max_lines is not None and i >= max_lines:
                    return
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except (UnicodeDecodeError, OSError):
        return


def load_verified_claims(pairs: tuple[tuple[Path, Path], ...] | None = None,
                         max_lines_per_file: int | None = None) -> dict[str, dict[str, Any]]:
    """{claim_id: claim_row} for every claim_id whose validator verdict is
    exactly VERIFIED. A claim_id absent from (or non-VERIFIED in) its
    validation summary is NOT included -- MISMATCH/UNVERIFIABLE stays
    invisible to ask(). `pairs` lets a caller load a SUBSET of stores (see
    ask()'s top_n short-circuit); None (default) re-reads the CURRENT
    module-level CLAIM_SOURCE_PAIRS (not a function-def-time default, so
    tests that monkeypatch it still take effect).

    `max_lines_per_file` caps physical lines read per store (None = no cap,
    the DEFAULT): full-scan consumers (claims_coverage_report, the fit-sweep
    validators) need every row, so a default cap would silently truncate them.
    Query surfaces that can't scope to a fixed store set pass a cap instead."""
    if pairs is None:
        pairs = CLAIM_SOURCE_PAIRS
    verified: dict[str, dict[str, Any]] = {}
    for validation_path, claims_path in pairs:
        summary = _load_json(validation_path)
        if not summary:
            continue
        verified_ids = {
            d["claim_id"] for d in summary.get("details", []) if d.get("verdict") == VERIFIED
        }
        if not verified_ids:
            continue
        for row in _load_jsonl(claims_path, max_lines_per_file):
            cid = row.get("claim_id")
            if cid in verified_ids:
                row = dict(row)
                row["_validator_source"] = _display_path(validation_path)
                row["_producer_source"] = _display_path(claims_path)
                verified[cid] = row
    return verified


def _claim_evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": row["claim_id"],
        "source_files": row.get("source_files", []),
        "as_of": row.get("computed_at"),
        "validator_verdict": VERIFIED,
        "validator_source": row.get("_validator_source"),
        "producer_source": row.get("_producer_source"),
    }


def _unanswerable(reason: str, question: str) -> dict[str, Any]:
    return {
        "answerable": False,
        "question": question,
        "reason": reason,
        "nearest_supported_families": describe_families(),
    }


# Split modules (see module docstring). Imported here -- after the utilities
# and loaders above are defined -- so ask_families.py/ask_fit.py's own
# top-level `from scripts.platformkit.intel_query.ask import ...` (of
# _ascii_name/_claim_evidence/_unanswerable/load_verified_claims/
# pairs_for_claim_stores) resolves against THIS module's already-populated
# namespace instead of racing a circular import. Re-exported by name (not
# `import *`) so every existing `from ...ask import X` caller/test keeps
# working unchanged.
from scripts.platformkit.intel_query.ask_families import (  # noqa: E402
    FAMILY_BEST,
    FAMILY_SHOOTER_PROFILE,
    _answer_entity_lookup,
    _answer_gate_verdict,
    _answer_provenance,
    _filter_by_hints,
    _format_top_n_answer,
    _try_best_x,
    _try_shooter_profile,
)
from scripts.platformkit.intel_query.ask_fit import (  # noqa: E402
    FAMILY_FIT,
    _FIT_ARCHETYPE_CLAIM_ID,
    _FIT_SCHEME_CLAIM_ID,
    _FIT_VACANCY_CLAIM_ID,
    _FIT_VALIDITY_CLAIM_ID,
    _find_by_key,
    _FORBIDDEN_FIT_WORDS,
    _fit_unanswerable,
    compose_fit,
)


def ask(question: str) -> dict[str, Any]:
    """Answer `question` ONLY from VERIFIED claims. Never guesses, never
    computes from raw data, never uses an UNVERIFIABLE/MISMATCH claim.

    Spec sec 4 SERVING AT SCALE: for FAMILY_TOP_N, try the small per-family
    `.index.jsonl` sidecar FIRST -- a hit skips `load_verified_claims()`'s
    full O(all-claims) parse entirely. A miss (no family has a fresh index,
    or none has a VERIFIED metric/window match) falls through to the
    existing full-load path completely unchanged -- the index is a
    speedup, never a correctness dependency."""
    best_x = _try_best_x(question)
    if best_x is not None:
        return best_x
    profile = _try_shooter_profile(question)
    if profile is not None:
        return profile
    parsed = classify(question)

    if parsed.family is None:
        return _unanswerable(
            "question did not match a supported family (top_n / entity_lookup / "
            "provenance / gate_verdict)",
            question,
        )

    if parsed.family == FAMILY_TOP_N:
        fast_row = ask_index.index_top_n_lookup(parsed, INTEL_CLAIMS_DIR, REPO_ROOT)
        if fast_row is not None:
            return _format_top_n_answer(parsed, question, fast_row)
        # BUG FIX (perf, m38): index miss is authoritative for every INDEXED
        # family (same filters/claim set as index_top_n_lookup); only the
        # handful discover_families can't index (legacy-override pairs, e.g.
        # nba_shooting_claims -- <1MB combined) get loaded here, not the
        # whole multi-GB corpus.
        if not parsed.metric_hints and ask_index.extract_metric_synonym(parsed.raw) is None:
            return _unanswerable(
                "could not map the requested metric to any known claims metric "
                "(no alias or synonym matched) -- refusing to guess", question)
        stale_pairs = tuple((v, p) for v, p in CLAIM_SOURCE_PAIRS if not ask_index.is_index_fresh(p.stem, INTEL_CLAIMS_DIR))
        residual_rows = [r for r in load_verified_claims(stale_pairs).values() if r.get("kind") == "ranking"]
        residual_candidates = _filter_by_hints(residual_rows, parsed)
        if not residual_candidates:
            return _unanswerable("no VERIFIED ranking claim matches the requested metric/window", question)
        return _format_top_n_answer(
            parsed, question, max(residual_candidates, key=lambda r: r.get("computed_at", ""))
        )

    if parsed.family == FAMILY_ENTITY_LOOKUP:
        # Same index-fast-path / stale-residual split as FAMILY_TOP_N above
        # (spec sec 4): a family with a fresh .index.jsonl is answered by
        # seek+read alone (ask_index.index_entity_lookup), never by
        # load_verified_claims -- that whole-store load is exactly what put
        # 2.8GB of nba_player_box_rate in memory for a single-player
        # question (2026-07-16). Only families WITHOUT a fresh index fall
        # back to a full load, and even then it is scoped to just those
        # stale pairs, never the whole corpus.
        if not parsed.entity_name:
            return _unanswerable("could not extract a player/entity name from the question", question)
        # NOT ascii-folded here, matching _answer_entity_lookup's original
        # name_key exactly (only the candidate's player_name gets folded,
        # both here via ask_index._ascii_fold and there via _ascii_name) --
        # this is a behavior-preserving port, not a new normalization rule.
        name_key = parsed.entity_name.strip().lower()
        fast_hits = ask_index.index_entity_lookup(parsed, name_key, INTEL_CLAIMS_DIR, REPO_ROOT)
        stale_pairs = tuple((v, p) for v, p in CLAIM_SOURCE_PAIRS if not ask_index.is_index_fresh(p.stem, INTEL_CLAIMS_DIR))
        residual_rows = [r for r in load_verified_claims(stale_pairs).values() if r.get("kind") == "ranking"]
        residual_candidates = _filter_by_hints(residual_rows, parsed)
        return _answer_entity_lookup(parsed, question, fast_hits + residual_candidates)

    verified = load_verified_claims(max_lines_per_file=_QUERY_SURFACE_MAX_LINES)
    if not verified:
        return _unanswerable("no VERIFIED claims are currently available", question)

    if parsed.family == FAMILY_PROVENANCE:
        return _answer_provenance(parsed, question, verified)
    if parsed.family == FAMILY_GATE_VERDICT:
        return _answer_gate_verdict(parsed, question, verified)
    return _unanswerable("unreachable family branch", question)  # pragma: no cover


_DEMO_QUESTIONS = (
    "Who are the top 5 best shooters (composite) in window=last_20?",
    "Where does Isaiah Joe rank on composite in window=last_20?",
    "How do you know? Show the evidence for nba_shooting_composite_last_20.",
    "What did the tennis surface gate find?",
    "What is the weather in Boston tomorrow?",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ask-anything over VERIFIED intel claims")
    parser.add_argument("question", nargs="?", default=None)
    parser.add_argument("--demo", action="store_true", help="run 3 answerable + 1 unanswerable proof questions")
    args = parser.parse_args(argv)

    if args.demo or not args.question:
        questions = _DEMO_QUESTIONS[:2] + _DEMO_QUESTIONS[-2:]
        for q in questions:
            result = ask(q)
            print(f"Q: {q}")
            print(json.dumps(result, indent=2))
            print()
        return 0

    result = ask(args.question)
    print(json.dumps(result, indent=2))
    return 0 if result.get("answerable") else 1


if __name__ == "__main__":
    sys.exit(main())
