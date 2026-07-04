"""ask(question) -> dict, answering ONLY from VERIFIED claims (mission spine 5).

This is a deterministic tool surface: an external LLM calls ask() the way it
would call any other tool. There is NO LLM call inside this module -- question
routing is keyword/regex matching (families.classify), and answers are pulled
straight from claim rows an INDEPENDENT validator already marked VERIFIED.

Sources joined:
    1. The validated-claims artifact(s): data/frontend/ops/intel_claims_validation*.json
       (per-claim_id verdict, written by scripts/platformkit/intel_validation/claims_validator.py)
    2. The producer claims JSONL(s): data/cache/intel_claims/*_claims.jsonl
       (full claim rows: criteria, ranking, source_files, caveats, computed_at)

HONEST UNANSWERABLE: if no VERIFIED claim covers the question, OR the family
cannot be classified, return {"answerable": False, "reason": ..., "nearest_supported_families": [...]}.
This module NEVER falls back to raw computation and NEVER answers from an
UNVERIFIABLE/MISMATCH claim -- those verdicts are treated the same as "absent".

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
from typing import Any

from scripts.platformkit.intel_query.families import (
    FAMILY_ENTITY_LOOKUP,
    FAMILY_PROVENANCE,
    FAMILY_TOP_N,
    classify,
    describe_families,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

# Every known (validation-summary, producer-claims) pair. v1 is a static
# registry rather than a directory glob so the answer surface only ever
# reads artifacts this lane has explicitly verified the shape of.
CLAIM_SOURCE_PAIRS: tuple[tuple[Path, Path], ...] = (
    (
        REPO_ROOT / "data" / "frontend" / "ops" / "intel_claims_validation.json",
        REPO_ROOT / "data" / "cache" / "intel_claims" / "nba_shooting_claims.jsonl",
    ),
    (
        REPO_ROOT / "data" / "cache" / "intel_claims" / "nba_quality_claims_validation.json",
        REPO_ROOT / "data" / "cache" / "intel_claims" / "nba_quality_claims.jsonl",
    ),
)

VERIFIED = "VERIFIED"


def _ascii_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="ascii", errors="strict") as f:
        return json.load(f)


def _display_path(path: Path) -> str:
    """repo-relative string when possible, else the raw path (test fixtures
    live under a tmp_path outside REPO_ROOT)."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="ascii", errors="strict") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_verified_claims() -> dict[str, dict[str, Any]]:
    """Join validation-summary verdicts to full producer claim rows.

    Returns {claim_id: claim_row} for every claim_id whose validator verdict
    is exactly VERIFIED. A claim_id present in the producer JSONL but absent
    from (or non-VERIFIED in) the validation summary is NOT included -- an
    unvalidated or MISMATCH/UNVERIFIABLE claim is invisible to ask()."""
    verified: dict[str, dict[str, Any]] = {}
    for validation_path, claims_path in CLAIM_SOURCE_PAIRS:
        summary = _load_json(validation_path)
        if not summary:
            continue
        verified_ids = {
            d["claim_id"] for d in summary.get("details", []) if d.get("verdict") == VERIFIED
        }
        if not verified_ids:
            continue
        for row in _load_jsonl(claims_path):
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


def _filter_by_hints(rows: list[dict[str, Any]], parsed) -> list[dict[str, Any]]:
    candidates = rows
    if parsed.metric_hints:
        candidates = [r for r in candidates if r["criteria"].get("metric") in parsed.metric_hints]
    if parsed.window_hint:
        candidates = [r for r in candidates if r["criteria"].get("window") == parsed.window_hint]
    return candidates


def _answer_top_n(parsed, question: str, verified: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ranking_claims = [r for r in verified.values() if r.get("kind") == "ranking"]
    candidates = _filter_by_hints(ranking_claims, parsed)
    if not candidates:
        return _unanswerable(
            "no VERIFIED ranking claim matches the requested metric/window", question
        )
    # Prefer the most-recently-computed matching claim (deterministic tie-break).
    row = max(candidates, key=lambda r: r.get("computed_at", ""))
    n = parsed.top_n or 10
    ranking = [dict(r) for r in row.get("ranking", [])]
    for r in ranking:
        if "player_name" in r:
            r["player_name"] = _ascii_name(str(r["player_name"]))
    ranking = ranking[:n]
    return {
        "answerable": True,
        "question": question,
        "family": FAMILY_TOP_N,
        "answer": {
            "metric": row["criteria"].get("metric"),
            "window": row["criteria"].get("window"),
            "ranking": ranking,
            "n_considered": row.get("n_considered"),
            "n_excluded_below_floor": row.get("n_excluded_below_floor"),
            "caveats": row.get("caveats", []),
        },
        "evidence": [_claim_evidence(row)],
    }


def _answer_entity_lookup(parsed, question: str, verified: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not parsed.entity_name:
        return _unanswerable("could not extract a player/entity name from the question", question)
    name_key = parsed.entity_name.strip().lower()
    ranking_claims = [r for r in verified.values() if r.get("kind") == "ranking"]
    candidates = _filter_by_hints(ranking_claims, parsed)
    hits = []
    for row in candidates:
        for r in row.get("ranking", []):
            pname = _ascii_name(str(r.get("player_name", "")))
            if pname.strip().lower() == name_key:
                hits.append((row, r))
    if not hits:
        return _unanswerable(
            f"no VERIFIED ranking claim has an entry for entity_name={parsed.entity_name!r} "
            "(the entity may exist but did not clear the claim's min_sample floor)",
            question,
        )
    answers = []
    evidence = []
    for row, r in hits:
        answers.append({
            "metric": row["criteria"].get("metric"),
            "window": row["criteria"].get("window"),
            "rank": r["rank"],
            "value": r["value"],
            "n": r.get("n"),
        })
        evidence.append(_claim_evidence(row))
    return {
        "answerable": True,
        "question": question,
        "family": FAMILY_ENTITY_LOOKUP,
        "answer": {"entity_name": parsed.entity_name, "rankings": answers},
        "evidence": evidence,
    }


def _answer_provenance(parsed, question: str, verified: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not parsed.claim_id or parsed.claim_id not in verified:
        return _unanswerable(
            "no VERIFIED claim_id was named (or recognized) in the question", question
        )
    row = verified[parsed.claim_id]
    return {
        "answerable": True,
        "question": question,
        "family": FAMILY_PROVENANCE,
        "answer": {
            "claim_id": row["claim_id"],
            "question_answered_by_claim": row.get("question"),
            "criteria": row.get("criteria"),
            "n_considered": row.get("n_considered"),
            "n_excluded_below_floor": row.get("n_excluded_below_floor"),
            "caveats": row.get("caveats", []),
        },
        "evidence": [_claim_evidence(row)],
    }


def ask(question: str) -> dict[str, Any]:
    """Answer `question` ONLY from VERIFIED claims. Never guesses, never
    computes from raw data, never uses an UNVERIFIABLE/MISMATCH claim."""
    verified = load_verified_claims()
    parsed = classify(question)

    if parsed.family is None:
        return _unanswerable(
            "question did not match a supported family (top_n / entity_lookup / provenance)",
            question,
        )
    if not verified:
        return _unanswerable("no VERIFIED claims are currently available", question)

    if parsed.family == FAMILY_TOP_N:
        return _answer_top_n(parsed, question, verified)
    if parsed.family == FAMILY_ENTITY_LOOKUP:
        return _answer_entity_lookup(parsed, question, verified)
    if parsed.family == FAMILY_PROVENANCE:
        return _answer_provenance(parsed, question, verified)
    return _unanswerable("unreachable family branch", question)  # pragma: no cover


_DEMO_QUESTIONS = (
    "Who are the top 5 best shooters (composite) in window=last_20?",
    "Where does Isaiah Joe rank on composite in window=last_20?",
    "How do you know? Show the evidence for nba_shooting_composite_last_20.",
    "What is the weather in Boston tomorrow?",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ask-anything over VERIFIED intel claims")
    parser.add_argument("question", nargs="?", default=None)
    parser.add_argument("--demo", action="store_true", help="run 2 answerable + 1 unanswerable proof questions")
    args = parser.parse_args(argv)

    if args.demo or not args.question:
        questions = _DEMO_QUESTIONS[:2] + _DEMO_QUESTIONS[-1:]
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
