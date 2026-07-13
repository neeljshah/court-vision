"""scripts.platformkit.knowledge.query -- deterministic answer engine over
the knowledge store (domains/<sport>/knowledge/knowledge.jsonl, built by
backfill_knowledge.py). No LLM calls, no embeddings: keyword-routed
filtering + ranking over ~530 rows. Labels are VERBATIM from the source --
every claim line ends `[LABEL, n=X]`, never paraphrased or upgraded.
HARD BOUNDARY (.claude/rules/no-edge-claims.md): calibration/mechanism
language only; "validated_edges" = validated MECHANISM relationships, never
a dollar edge/ROI; NULL/REJECTED rows surface only under what_failed.
Stat/rating/prediction/calibration questions route through
scripts/platformkit/answers/resolver_registry.py (docs/AI_CONSUMER_CONTRACT.md)
-- this module only answers questions about the knowledge store itself.
CLI: python -m scripts.platformkit.knowledge.query
"""
from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[3]
SPORTS = ["basketball_nba", "mlb", "soccer", "tennis"]
_SPORT_ALIASES = {"nba": "basketball_nba", "basketball_nba": "basketball_nba",
                   "basketball": "basketball_nba", "mlb": "mlb", "baseball": "mlb",
                   "soccer": "soccer", "tennis": "tennis"}

def _sport_from_question(question: str) -> Optional[str]:
    """First sport word named in the question text, or None ('all sports')."""
    for w in re.findall(r"[a-z_]+", question.lower()):
        if w in _SPORT_ALIASES:
            return _SPORT_ALIASES[w]
    return None

# Labels whose LEADING token starts with one of these are failed/null findings.
# Leading-token only: "CONFIRMED (REPLICATED, ... BLOCKED/NULL ...)" is NOT
# failed -- a parenthetical/trailing note never reclassifies the verdict.
_FAIL_TOKENS = ("REJECTED", "NULL", "KILLED", "NOT_TESTABLE", "FAILED_REPLICATION",
                "REPLICATION_BLOCKED")
# Strength order (highest first), matched within the leading token.
_STRENGTH = ["REPLICATED", "CONFIRMED_LOCAL", "CONFIRMED", "PARTIAL", "PROVISIONAL"]

Row = Dict[str, Any]


def _normalize_sport(sport: Optional[str]) -> Optional[str]:
    if sport is None:
        return None
    return _SPORT_ALIASES.get(sport.lower(), sport.lower())

@lru_cache(maxsize=1)
def _load_all() -> Tuple[Row, ...]:
    rows: List[Row] = []
    for sport in SPORTS:
        path = REPO / "domains" / sport / "knowledge" / "knowledge.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return tuple(rows)

def load_knowledge(sports: Optional[List[str]] = None) -> List[Row]:
    """All knowledge rows, cached read of the 4 jsonl files, optionally
    filtered to `sports` (aliases ok, e.g. 'nba' -> 'basketball_nba')."""
    rows = _load_all()
    if not sports:
        return list(rows)
    wanted = {_normalize_sport(s) for s in sports}
    return [r for r in rows if r.get("sport") in wanted]

def _lead_token(row: Row) -> str:
    """First WORD_CHARS run of the label, e.g. 'CONFIRMED (REPLICATED...)' ->
    'CONFIRMED', 'SURVIVES_PREREG_PROVISIONAL' -> itself, '' if no label."""
    m = re.match(r"[A-Za-z_]+", (row.get("label") or "").strip())
    return m.group(0) if m else ""

def is_failed(row: Row) -> bool:
    tok = _lead_token(row)
    return bool(tok) and any(tok.startswith(f) for f in _FAIL_TOKENS)

def is_provisional(row: Row) -> bool:
    tok = _lead_token(row)
    return "PROVISIONAL" in tok or "UNDERPOWERED" in tok

def _strength_rank(row: Row) -> int:
    lead = _lead_token(row)
    for i, tok in enumerate(_STRENGTH):
        if tok in lead:
            return i
    return len(_STRENGTH)  # unranked labels sort last

def rank(rows: List[Row]) -> List[Row]:
    """Label strength desc, then n desc (missing n treated as 0)."""
    return sorted(rows, key=lambda r: (_strength_rank(r), -(r.get("n") or 0)))

def _label_line(row: Row) -> str:
    label = row.get("label") or "UNLABELED"
    n = row.get("n")
    n_str = str(n) if n is not None else "?"
    claim = row.get("claim") or row.get("mechanism") or "?"
    return "%s [%s, n=%s]" % (claim, label, n_str)

def _scope_rows(sport: Optional[str]) -> Tuple[List[Row], Optional[str]]:
    """(rows, error). error is set iff a sport was given but not recognized."""
    if sport is None:
        return load_knowledge(), None
    norm = _normalize_sport(sport)
    if norm not in SPORTS:
        return [], "sport '%s' not recognized (know: %s)" % (sport, ", ".join(SPORTS))
    return load_knowledge([norm]), None

# Intent handlers -- each returns (answer_text, claims, caveats)
def _factors_for_matchup(question: str, sport: Optional[str]) -> Tuple[str, List[Row], List[str]]:
    rows, err = _scope_rows(sport)
    if err:
        return "cannot answer: %s" % err, [], [err]
    ranked = rank([r for r in rows if not is_failed(r)])[:8]
    if not ranked:
        return "no validated factors on record for %s yet." % (sport or "any sport"), [], \
            ["knowledge store has no non-failed rows for this scope"]
    lines = ["in-game factors on record for %s (not exhaustive):" % (sport or "cross-sport")]
    lines += [_label_line(r) for r in ranked]
    return "\n".join(lines), ranked, \
        ["local/single-corpus findings unless the label says REPLICATED -- calibration signal, not a dollar edge"]

def _validated_edges(question: str, sport: Optional[str]) -> Tuple[str, List[Row], List[str]]:
    rows, err = _scope_rows(sport)
    if err:
        return "cannot answer: %s" % err, [], [err]
    replicated = [r for r in rows if not is_failed(r) and "REPLICATED" in (r.get("label") or "")]
    ranked = rank(replicated)[:10]
    if not ranked:
        return "no mechanisms are labeled REPLICATED yet for %s." % (sport or "any sport"), [], \
            ["replication is the highest bar -- most rows are single-corpus"]
    lines = ["mechanisms validated across corpora (REPLICATED label -- calibration signal, never a dollar edge):"]
    lines += [_label_line(r) for r in ranked]
    return "\n".join(lines), ranked, ["LOCAL statistical findings, not a market-beating or causal claim"]

# ponytail: filler set mirrors resolver_registry._MECH_FILLER (same shape of
# problem -- strip question words so token-subset matching survives phrasing).
_MECH_FILLER = {"what", "does", "the", "evidence", "say", "about", "is", "there", "for", "on",
                "mechanism", "hypothesis", "folklore", "of", "a", "an", "in", "explain", "lookup",
                "we"} | set(_SPORT_ALIASES)  # sport words scope the answer, never match mechanisms

def _mech_tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in _MECH_FILLER}

def _mechanism_lookup(question: str, sport: Optional[str]) -> Tuple[str, List[Row], List[str]]:
    rows, err = _scope_rows(sport)
    if err:
        return "cannot answer: %s" % err, [], [err]
    q_tokens = _mech_tokens(question)
    if not q_tokens:
        return "cannot answer: no mechanism term found in the question.", [], ["empty search term"]
    matches = [r for r in rows if q_tokens <= _mech_tokens("%s %s" % (r.get("mechanism") or "", r.get("claim") or ""))]
    ranked = rank(matches)[:10]
    if not ranked:
        return "cannot answer: no mechanism matching %s in the knowledge store." % sorted(q_tokens), [], \
            ["no token-subset match"]
    lines = ["knowledge-store rows matching %s:" % sorted(q_tokens)]
    lines += [_label_line(r) for r in ranked]
    return "\n".join(lines), ranked, ["verbatim labels -- NULL/REJECTED rows shown as-is, not softened"]

def _what_failed(question: str, sport: Optional[str]) -> Tuple[str, List[Row], List[str]]:
    rows, err = _scope_rows(sport)
    if err:
        return "cannot answer: %s" % err, [], [err]
    ranked = rank([r for r in rows if is_failed(r)])[:10]
    if not ranked:
        return "no failed/rejected rows on record for %s." % (sport or "any sport"), [], []
    lines = ["tested-and-failed for %s (do not claim these):" % (sport or "all sports")]
    lines += [_label_line(r) for r in ranked]
    return "\n".join(lines), ranked, \
        ["an honest REJECT/NULL is a success, not a gap -- see .claude/rules/no-edge-claims.md"]

def _what_is_provisional(question: str, sport: Optional[str]) -> Tuple[str, List[Row], List[str]]:
    rows, err = _scope_rows(sport)
    if err:
        return "cannot answer: %s" % err, [], [err]
    ranked = rank([r for r in rows if is_provisional(r)])[:10]
    if not ranked:
        return "no PROVISIONAL/UNDERPOWERED rows on record for %s." % (sport or "any sport"), [], []
    lines = ["PROVISIONAL/UNDERPOWERED for %s (not yet confirmed):" % (sport or "all sports")]
    lines += [_label_line(r) for r in ranked]
    return "\n".join(lines), ranked, \
        ["PROVISIONAL means underpowered or single-half replication -- never quote as CONFIRMED"]

def _coverage(question: str, sport: Optional[str]) -> Tuple[str, List[Row], List[str]]:
    rows, err = _scope_rows(sport)
    if err:
        return "cannot answer: %s" % err, [], [err]
    if not rows:
        return "knowledge store is empty for this scope.", [], []
    by_sport: Dict[str, Dict[str, int]] = {}
    for r in rows:
        b = by_sport.setdefault(r.get("sport") or "?", {"total": 0, "FAILED": 0, "PROVISIONAL": 0, "VALIDATED": 0, "OTHER": 0})
        b["total"] += 1
        if is_failed(r):
            b["FAILED"] += 1
        elif is_provisional(r):
            b["PROVISIONAL"] += 1
        elif _strength_rank(r) < len(_STRENGTH):
            b["VALIDATED"] += 1
        else:
            b["OTHER"] += 1
    lines = ["knowledge-store coverage:"]
    for s in sorted(by_sport):
        b = by_sport[s]
        lines.append("%s: %d rows [FAILED=%d, VALIDATED=%d, PROVISIONAL=%d, OTHER=%d]"
                      % (s, b["total"], b["FAILED"], b["VALIDATED"], b["PROVISIONAL"], b["OTHER"]))
    return "\n".join(lines), [], \
        ["VALIDATED = non-failed rows with a recognized strength label; OTHER = free-text label outside that set"]

_HANDLERS = {
    "factors_for_matchup": _factors_for_matchup,
    "validated_edges": _validated_edges,
    "mechanism_lookup": _mechanism_lookup,
    "what_failed": _what_failed,
    "what_is_provisional": _what_is_provisional,
    "coverage": _coverage,
}

# ponytail: fixed keyword table, no NLP -- priority order matters, first hit
# wins (provisional/failed/replicate checked before the broad "factors" catch-all).
_INTENT_RULES: List[Tuple[str, Tuple[str, ...]]] = [
    ("what_is_provisional", ("provisional", "underpowered")),
    ("what_failed", ("failed", "reject", " null", "not claim", "do not claim", "should not claim")),
    ("validated_edges", ("replicate", "replicated", "which mechanisms", "validated mechanism")),
    ("coverage", ("coverage", "how many rows", "label histogram")),
    ("mechanism_lookup", ("evidence say about", "hypothesis", "mechanism lookup", "explain ")),
    ("factors_for_matchup", ("factors", "what matters", "matter for", "powers", "what powers")),
]
_KEYWORD_TO_INTENT = {kw: intent for intent, kws in _INTENT_RULES for kw in kws}

def classify_intent(question: str) -> Optional[str]:
    low = question.lower()
    for intent, keywords in _INTENT_RULES:
        if any(k in low for k in keywords):
            return intent
    return None

def _closest_intents(question: str) -> List[str]:
    words = re.findall(r"[a-z]+", question.lower())
    out: List[str] = []
    for w in words:
        for kw in difflib.get_close_matches(w, _KEYWORD_TO_INTENT.keys(), n=2, cutoff=0.6):
            intent = _KEYWORD_TO_INTENT[kw]
            if intent not in out:
                out.append(intent)
    return out or sorted(_HANDLERS)

def answer(question: str, sport: str = None) -> dict:
    """Route `question` (+ optional `sport`) through the fixed intent table
    and return {answer_text, claims, labels_present, caveats}. Explicit
    `sport` arg wins; otherwise the sport named in the question text scopes
    the answer; only a question naming no sport spans all sports.
    Unregistered question shape -> honest refusal + closest supported
    intents, never an improvised answer."""
    sport = sport or _sport_from_question(question)
    intent = classify_intent(question)
    if intent is None:
        closest = _closest_intents(question)
        return {"answer_text": "cannot answer from knowledge store -- unrecognized question shape. "
                                "closest supported intents: %s" % ", ".join(closest),
                "claims": [], "labels_present": False,
                "caveats": ["unrecognized intent -- for stat/rating/prediction/calibration questions use "
                            "resolver_registry.resolve() per docs/AI_CONSUMER_CONTRACT.md instead"]}
    text, claims, caveats = _HANDLERS[intent](question, sport)
    labels_present = bool(claims) and all(c.get("label") for c in claims)
    return {"answer_text": text, "claims": claims, "labels_present": labels_present, "caveats": caveats}

# Phase 4 acceptance: the 10 canonical questions
CANONICAL_QUESTIONS: List[Tuple[str, Optional[str]]] = [
    ("what in-game factors matter for MLB totals", "mlb"),
    ("what has been tested and failed for NBA", "nba"),
    ("what is provisional for tennis", "tennis"),
    ("which mechanisms replicate across corpora", None),
    ("what powers soccer predictions", "soccer"),
    ("what in-game factors matter for NBA", "nba"),
    ("what in-game factors matter for tennis", "tennis"),
    ("give a coverage summary of the knowledge store", None),
    ("what should we not claim", None),
    ("what does the evidence say about back to back rest", "nba"),
]

def main() -> int:
    for q, sport in CANONICAL_QUESTIONS:
        result = answer(q, sport)
        print("Q: %s" % q)
        print("A: %s" % result["answer_text"])
        if result["caveats"]:
            print("caveats: %s" % "; ".join(result["caveats"]))
        print()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
