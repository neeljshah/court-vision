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

CLI:
    python -m scripts.platformkit.intel_query.ask "Who are the top 5 best shooters (composite) in window=last_20?"
    python -m scripts.platformkit.intel_query.ask --demo
"""
from __future__ import annotations

import argparse
import json
import re
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
    gate_verdict_match_score,
    match_gate_verdict_candidates,
)

# FIT is a compose_fit(player, team)-only family (explicit args, not a
# free-text question routed through families.classify), so it is defined
# here rather than added to families.py's question-classifier enum.
FAMILY_FIT = "fit"

# ONE-CONCLUSION composer family: "who is the best shooter" (singular,
# all-factors-weighed) is a DIFFERENT question from "top 5 best shooters"
# (a ranking list, already routed to FAMILY_TOP_N by families.classify).
# Checked BEFORE the existing family dispatch so it never disturbs top_n's
# "best shooters" plural/top-N phrasing. Only "shooter" is wired v1 --
# _BEST_ASPECT_ALIASES maps a recognized alias phrase to a compose_best()
# aspect key; an unrecognized "best X" phrase falls through to the existing
# families.classify dispatch unchanged.
FAMILY_BEST = "best"
_BEST_ASPECT_ALIASES: dict[str, str] = {"shooter": "shooter", "shooters": "shooter"}
_BEST_SINGLE_RE = re.compile(r"\bbest\s+(shooter|shooters)\b", re.IGNORECASE)
_TOP_N_ANYWHERE_RE = re.compile(r"\btop\s*[- ]?\s*\d+\b", re.IGNORECASE)

# SHOOTER TRAIT PROFILE family: "what kind of shooter is X?" is a VECTOR
# question (multi-axis profile), not a ranking/scalar question -- routed to
# compose_profile(), which assembles per-axis VERIFIED claims and never
# collapses them into one score. Checked before families.classify (same
# pattern as FAMILY_BEST above).
FAMILY_SHOOTER_PROFILE = "shooter_profile"
_PROFILE_RE = re.compile(
    r"\bwhat kind of shooter is\s+(?P<name>[A-Za-z][A-Za-z .'\-]*?)\s*\??\s*$"
    r"|\bshooter profile (?:for|of)\s+(?P<name2>[A-Za-z][A-Za-z .'\-]*?)\s*\??\s*$",
    re.IGNORECASE,
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


# claim_id of each fit-ingredient claim compose_fit() joins -- a static
# registry (not a glob) so compose_fit only ever reads claims this lane
# named, matching the CLAIM_SOURCE_PAIRS pattern above.
_FIT_ARCHETYPE_CLAIM_ID = "nba_fit_archetype_profile_current"
_FIT_SCHEME_CLAIM_ID = "nba_fit_team_scheme_identity_current"
_FIT_VACANCY_CLAIM_ID = "nba_fit_role_vacancy_by_team_posgroup_current"

# compose_fit joins claims from exactly these two stores (3 ingredient claims
# + the validity gate verdict). A bare load_verified_claims() would whole-load
# EVERY store including nba_player_box_rate (2.8GB / 59k VERIFIED rows) -- the
# same footgun as the 6.1GB compose_matchup incident -- so scope like
# compose_best/_profile do (pairs_for_claim_stores).
_FIT_CLAIM_STORES = ("nba_fit_ingredient_claims.jsonl", "gate_verdict_claims.jsonl")

# PROGRAM v3 closure: the pre-registered fit-validity gate's REJECT verdict
# (does scheme fit predict post-move performance? -- see
# data/domains/nba/fit_validity_gate_verdict.json, read-only truth, never
# regenerated here) is cited inline in every compose_fit() answer so the
# SCOUTING composition never implies validity it does not have.
_FIT_VALIDITY_CLAIM_ID = "nba_fit_validity_gate_verdict"

# Words a SCOUTING fit answer must never contain -- compose_fit() is a
# descriptive composition of three VERIFIED ingredient claims, never a
# prediction (no-edge-claims rule).
_FORBIDDEN_FIT_WORDS = ("predict", "will improve", "expected gain", "edge")

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


def _filter_by_hints(rows: list[dict[str, Any]], parsed) -> list[dict[str, Any]]:
    # Per-file schema tolerance: a claims row from a store this lane hasn't
    # seen yet might be missing "criteria" entirely -- treat that as "does
    # not match this hint" rather than KeyError-ing the whole ask() call.
    #
    # BUG FIX: families.classify's metric_hints alias dict has no synonym
    # for phrasings like "free throw percentage", so metric_hints can come
    # back EMPTY for a real, answerable metric -- and an empty metric_hints
    # used to skip metric filtering entirely, letting an unrelated claim
    # (wrong metric, wrong entity type) win by recency. ask_index's
    # extract_metric_synonym covers the phrasings that exist in the actual
    # claim corpus; entity_key_matches rejects a claim whose entity_key
    # (player vs team) contradicts a question that names an entity type
    # unambiguously ("players" must never be answered by a team claim).
    metric_synonym = ask_index.extract_metric_synonym(parsed.raw)
    entity_type = ask_index.question_entity_type(parsed.raw)
    allowed_metrics = set(parsed.metric_hints)
    if metric_synonym is not None:
        allowed_metrics.add(metric_synonym)
    candidates = rows
    if allowed_metrics:
        candidates = [r for r in candidates if r.get("criteria", {}).get("metric") in allowed_metrics]
    if parsed.window_hint:
        candidates = [r for r in candidates if r.get("criteria", {}).get("window") == parsed.window_hint]
    candidates = [
        r for r in candidates if ask_index.entity_key_matches(r.get("criteria", {}).get("entity_key"), entity_type)
    ]
    return candidates


def _format_top_n_answer(parsed, question: str, row: dict[str, Any]) -> dict[str, Any]:
    """Shared formatter: BOTH the index fast path and the full-load slow
    path call this on their winning row, so the two can never drift in
    answer SHAPE -- only in how the winning row was found."""
    ranking = [dict(r) for r in row.get("ranking", [])]
    for r in ranking:
        if "player_name" in r:
            r["player_name"] = _ascii_name(str(r["player_name"]))
    ranking = ranking[:parsed.top_n or 10]
    return {
        "answerable": True, "question": question, "family": FAMILY_TOP_N,
        "answer": {
            "metric": row.get("criteria", {}).get("metric"), "window": row.get("criteria", {}).get("window"),
            "ranking": ranking, "n_considered": row.get("n_considered"),
            "n_excluded_below_floor": row.get("n_excluded_below_floor"),
            "caveats": row.get("caveats", []),
        },
        "evidence": [_claim_evidence(row)],
    }


def _answer_top_n(parsed, question: str, verified: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # UNANSWERABLE-over-wrong-answer: a top-N question whose metric resolved
    # to NOTHING (no families.py alias, no ask_index synonym) must never be
    # answered by whatever unrelated claim is most recent -- that recency
    # guess IS the reported bug. Entity lookups are exempt: metric-less
    # "where does <name> rank" legitimately searches every ranking claim.
    if not parsed.metric_hints and ask_index.extract_metric_synonym(parsed.raw) is None:
        return _unanswerable(
            "could not map the requested metric to any known claims metric "
            "(no alias or synonym matched) -- refusing to guess", question
        )
    ranking_claims = [r for r in verified.values() if r.get("kind") == "ranking"]
    candidates = _filter_by_hints(ranking_claims, parsed)
    if not candidates:
        return _unanswerable(
            "no VERIFIED ranking claim matches the requested metric/window", question
        )
    row = max(candidates, key=lambda r: r.get("computed_at", ""))  # most-recent tie-break
    return _format_top_n_answer(parsed, question, row)


def _answer_entity_lookup(parsed, question: str, verified: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not parsed.entity_name:
        return _unanswerable("could not extract a player/entity name from the question", question)
    name_key = parsed.entity_name.strip().lower()
    ranking_claims = [r for r in verified.values() if r.get("kind") == "ranking"]
    candidates = _filter_by_hints(ranking_claims, parsed)
    hits = []
    for row in candidates:
        for r in row.get("ranking", []):
            if _ascii_name(str(r.get("player_name", ""))).strip().lower() == name_key:
                hits.append((row, r))
    if not hits:
        return _unanswerable(
            f"no VERIFIED ranking claim has an entry for entity_name={parsed.entity_name!r} "
            "(the entity may exist but did not clear the claim's min_sample floor)",
            question,
        )
    answers = [
        {
            "metric": row.get("criteria", {}).get("metric"), "window": row.get("criteria", {}).get("window"),
            "rank": r.get("rank"), "value": r.get("value"), "n": r.get("n"),
        }
        for row, r in hits
    ]
    evidence = [_claim_evidence(row) for row, _r in hits]
    return {
        "answerable": True, "question": question, "family": FAMILY_ENTITY_LOOKUP,
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
        "answerable": True, "question": question, "family": FAMILY_PROVENANCE,
        "answer": {
            "claim_id": row["claim_id"], "question_answered_by_claim": row.get("question"),
            "criteria": row.get("criteria"), "n_considered": row.get("n_considered"),
            "n_excluded_below_floor": row.get("n_excluded_below_floor"),
            "caveats": row.get("caveats", []),
        },
        "evidence": [_claim_evidence(row)],
    }


def _answer_gate_verdict(parsed, question: str, verified: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # Deterministic ranking (score DESC, claim_id ASC). If 2+ candidates tie
    # the top score with DIFFERENT verdicts, report ambiguity honestly.
    candidates = match_gate_verdict_candidates(parsed, verified)
    if not candidates:
        return _unanswerable(
            "no VERIFIED gate-verdict claim matches this question's topic", question
        )
    row = candidates[0]
    if len(candidates) > 1:
        top_score = gate_verdict_match_score(parsed, row)
        tied = [c for c in candidates if gate_verdict_match_score(parsed, c) == top_score]
        distinct_verdicts = {c.get("verdict") for c in tied}
        if len(tied) > 1 and len(distinct_verdicts) > 1:
            return {
                "answerable": True,
                "question": question,
                "family": FAMILY_GATE_VERDICT,
                "note": "multiple matching verdicts with equal match score -- ambiguous topic",
                "candidates": [c.get("claim_id") for c in tied],
            }
    return {
        "answerable": True, "question": question, "family": FAMILY_GATE_VERDICT,
        "answer": {
            "gate_module": row.get("gate_module"), "verdict": row.get("verdict"),
            "primary_number": row.get("primary_number"), "corpus_ids": row.get("corpus_ids", []),
            "planted_null_passed": row.get("planted_null_passed"),
            "edge_claimed": row.get("edge_claimed", False), "verdict_file": row.get("verdict_file"),
            "caveats": row.get("caveats", []),
        },
        "evidence": [_claim_evidence(row)],
    }


def _find_by_key(rows: list[dict[str, Any]], key: str, name_key: str) -> dict[str, Any] | None:
    """First ranking entry whose `key` field ASCII-folds/lowercases to
    name_key. name_key is already normalized by the caller."""
    for r in rows:
        if key in r and _ascii_name(str(r[key])).strip().lower() == name_key:
            return r
    return None


def _fit_unanswerable(player: str, team: str, missing_ingredient: str, reason: str) -> dict[str, Any]:
    return {
        "answerable": False,
        "family": FAMILY_FIT,
        "player": _ascii_name(player),
        "team": team,
        "missing_ingredient": missing_ingredient,
        "reason": _ascii_name(reason),
    }


def compose_fit(player: str, team: str) -> dict[str, Any]:
    """Join the 3 VERIFIED fit-ingredient claims (archetype/attribute
    profile, team scheme identity, role vacancy) into one SCOUTING
    composition -- descriptive only, never predictive. If ANY ingredient is
    below its stated floor or absent for this player/team, returns honest
    UNANSWERABLE naming the exact missing ingredient (never guesses, never
    silently composes from a partial join)."""
    verified = load_verified_claims(pairs_for_claim_stores(_FIT_CLAIM_STORES))
    name_key = _ascii_name(player).strip().lower()
    team_key = team.strip().upper()

    archetype_claim = verified.get(_FIT_ARCHETYPE_CLAIM_ID)
    if not archetype_claim:
        return _fit_unanswerable(
            player, team, "archetype_profile",
            f"claim {_FIT_ARCHETYPE_CLAIM_ID!r} is not currently VERIFIED/available",
        )
    profile = _find_by_key(archetype_claim.get("ranking", []), "player_name", name_key)
    if not profile:
        return _fit_unanswerable(
            player, team, "archetype_profile",
            f"{player!r} has no VERIFIED archetype/attribute row (absent from the claim, "
            f"or below its stated minutes floor -- see {_FIT_ARCHETYPE_CLAIM_ID}'s caveats)",
        )

    scheme_claim = verified.get(_FIT_SCHEME_CLAIM_ID)
    if not scheme_claim:
        return _fit_unanswerable(
            team, team, "team_scheme_identity",
            f"claim {_FIT_SCHEME_CLAIM_ID!r} is not currently VERIFIED/available",
        )
    scheme = _find_by_key(scheme_claim.get("ranking", []), "team", team_key.lower())
    if not scheme:
        return _fit_unanswerable(
            player, team, "team_scheme_identity",
            f"team {team!r} has no VERIFIED scheme-identity row in {_FIT_SCHEME_CLAIM_ID}",
        )

    vacancy_claim = verified.get(_FIT_VACANCY_CLAIM_ID)
    if not vacancy_claim:
        return _fit_unanswerable(
            player, team, "role_vacancy",
            f"claim {_FIT_VACANCY_CLAIM_ID!r} is not currently VERIFIED/available",
        )
    posgroup = profile.get("posgroup")
    vacancy_key = f"{team_key}|{posgroup}"
    vacancy = _find_by_key(vacancy_claim.get("ranking", []), "team_posgroup", vacancy_key.lower())
    if not vacancy:
        return _fit_unanswerable(
            player, team, "role_vacancy",
            f"team_posgroup {vacancy_key!r} has no VERIFIED role-vacancy row (thin sample "
            f"-- see {_FIT_VACANCY_CLAIM_ID}'s min_sample floor)",
        )

    answer = {
        "player": _ascii_name(str(profile.get("player_name"))), "team": team_key,
        "archetype_profile": {
            "posgroup": profile.get("posgroup"), "archetype": profile.get("archetype"),
            "creation": profile.get("creation"), "playmaking": profile.get("playmaking"),
            "spacing": profile.get("spacing"), "rim_pressure": profile.get("rim_pressure"),
            "rebounding": profile.get("rebounding"), "rim_protect": profile.get("rim_protect"),
            "perimeter_d": profile.get("perimeter_d"), "self_create": profile.get("self_create"),
            "usage_pct": profile.get("usage_pct"),
        },
        "team_scheme_identity": {
            "dominant_tag": scheme.get("dominant_tag"), "best_scheme": scheme.get("best_scheme"),
            "confidence": scheme.get("confidence"),
        },
        "role_vacancy": {"team_posgroup": vacancy.get("team_posgroup"), "vacancy_share": vacancy.get("value"),
                          "n": vacancy.get("n")},
        "note": (
            "SCOUTING composition of 3 VERIFIED descriptive ingredients -- purely descriptive, "
            "no market/$ claim. Composition is descriptive; the validity gate returned REJECT "
            "on 2026-07-05."
        ),
    }
    text_blob = json.dumps(answer).lower()
    for word in _FORBIDDEN_FIT_WORDS:
        if word in text_blob:
            return _fit_unanswerable(
                player, team, "forbidden_word_guard",
                f"composed answer would contain forbidden predictive word {word!r} -- refusing",
            )

    evidence = [_claim_evidence(archetype_claim), _claim_evidence(scheme_claim),
                _claim_evidence(vacancy_claim)]
    validity_claim = verified.get(_FIT_VALIDITY_CLAIM_ID)
    if validity_claim:
        evidence.append(_claim_evidence(validity_claim))

    return {
        "answerable": True, "family": FAMILY_FIT, "player": _ascii_name(player), "team": team,
        "answer": answer,
        "evidence": evidence,
    }


def _try_best_x(question: str) -> dict[str, Any] | None:
    """Minimal hook for the ONE-CONCLUSION composer: a singular "best <X>"
    question (not "top N best <X>", which stays FAMILY_TOP_N) with a wired
    aspect alias routes to compose_best(); anything else returns None so
    ask() falls through to its existing family dispatch unchanged."""
    text = question or ""
    if _TOP_N_ANYWHERE_RE.search(text):
        return None
    m = _BEST_SINGLE_RE.search(text)
    if not m:
        return None
    aspect = _BEST_ASPECT_ALIASES.get(m.group(1).lower())
    if aspect is None:
        return None
    from scripts.platformkit.intel_query.compose_best import compose_best  # local import: avoid import cycle

    result = compose_best(aspect)
    result["family"] = FAMILY_BEST
    result["question"] = question
    return result


def _try_shooter_profile(question: str) -> dict[str, Any] | None:
    """"what kind of shooter is <name>" / "shooter profile for <name>" ->
    compose_profile(name); anything else returns None so ask() falls through
    to the existing family dispatch unchanged."""
    m = _PROFILE_RE.search(question or "")
    if not m:
        return None
    name = (m.group("name") or m.group("name2") or "").strip()
    if not name:
        return None
    from scripts.platformkit.intel_query.compose_profile import compose_profile  # local: avoid import cycle

    result = compose_profile(name)
    result["family"] = FAMILY_SHOOTER_PROFILE
    result["question"] = question
    result["answerable"] = result.get("status") == "OK"
    return result


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

    verified = load_verified_claims(max_lines_per_file=_QUERY_SURFACE_MAX_LINES)
    if not verified:
        return _unanswerable("no VERIFIED claims are currently available", question)

    if parsed.family == FAMILY_TOP_N:
        return _answer_top_n(parsed, question, verified)
    if parsed.family == FAMILY_ENTITY_LOOKUP:
        return _answer_entity_lookup(parsed, question, verified)
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
