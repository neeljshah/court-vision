"""Deterministic keyword-matching question classifier (no LLM call).

Classifies a natural-language question string into ONE of the 3 supported
v1 families, or None if it matches none of them. Pure string/regex logic --
this module never touches disk and never calls a model. The intent is that
an EXTERNAL LLM calls ask() as a tool; ask() (via this module) does the
routing deterministically so the answer surface stays auditable.

Families:
    TOP_N        -- "who are the top N <metric-ish words>" ranking questions
    ENTITY_LOOKUP -- "where does <player> rank on <metric>" / "what is
                     <player>'s <metric>"
    PROVENANCE   -- "how do you know" / "show the evidence" / "prove" for a
                     specific claim_id
    GATE_VERDICT -- "what did the <thing> gate find" / "did <thing> beat
                     <baseline>" -- routes to a VERIFIED claim_kind=verdict
                     row (gate_module + verdict_file + numbers), never to a
                     gate re-run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

FAMILY_TOP_N = "top_n"
FAMILY_ENTITY_LOOKUP = "entity_lookup"
FAMILY_PROVENANCE = "provenance"
FAMILY_GATE_VERDICT = "gate_verdict"

ALL_FAMILIES = (FAMILY_TOP_N, FAMILY_ENTITY_LOOKUP, FAMILY_PROVENANCE, FAMILY_GATE_VERDICT)

_TOP_N_RE = re.compile(
    r"\btop\s*[- ]?\s*(\d+)\b|\bbest\s+(\d+)\b", re.IGNORECASE
)
# numberless ranking phrasings ("top soccer teams by gf diff", "best home
# advantage teams", "leaders in whiff rate") -- classified top_n with
# top_n=None (answer layer applies its default N). Added 2026-07-17 for the
# answer-anything coverage push; a match still needs a metric to resolve
# downstream, so misfires refuse honestly rather than mis-answer.
# "...<metric words> leaders" (bare trailing "leaders", no "in"/"by") added
# 2026-07-19 -- "defense adjusted true shooting leaders" has no "in"/"by"
# after "leaders" and previously fell through to family=None.
_TOP_NONUM_RE = re.compile(
    r"\btop\s+[a-z]|\bbest\s+[a-z]|\bleaders?\s+(?:in|by)\b|\bwho\s+leads\b|\bleaders?\s*[.?!]*\s*$"
    # "most <adj> players" / "which batters/players/teams <metric phrase>"
    # (2026-07-18): ranking-cue shapes with no top/best token fell to
    # family=None even when the metric synonym resolved downstream.
    r"|\bmost\s+[a-z]|\bwhich\s+(?:players?|batters?|pitchers?|hitters?|teams?|officials?|referees?|sports?|markets?|duos?|lineups?)\b"
    r"|\bwidest\s+[a-z]|\bspecialists?\b",
    re.IGNORECASE,
)
_PROVENANCE_WORDS = re.compile(
    r"\b(how do you know|show (?:me )?(?:the )?evidence|prove|provenance|"
    r"source(?:s)? for|where does that come from)\b",
    re.IGNORECASE,
)
_RANK_LOOKUP_RE = re.compile(
    r"\bwhere does\b.+\brank\b|\brank(?:ing)? of\b|\bwhat rank\b|\bwhat is\b.+\brank\b",
    re.IGNORECASE,
)
# claim_id token: producer ids are snake_case, may include digits/hyphens
# once quoted (e.g. season_2024-25 windows embedded in the id).
_CLAIM_ID_RE = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9-]+){2,})\b", re.IGNORECASE)
_WINDOW_RE = re.compile(r"\bwindow\s*[=:]\s*([a-z0-9_-]+)\b", re.IGNORECASE)
_GATE_VERDICT_WORDS = re.compile(
    r"\bwhat did\b.+\b(gate|check)\b.+\bfind\b|\bdid\b.+\b(beat|clear the bar|clear|pass)\b|"
    r"\bgate verdict\b|\bwhat.?s the verdict\b|\bwhat was the verdict\b|"
    r"\bdoes\b.+\bpredict\b",
    re.IGNORECASE,
)


@dataclass
class ParsedQuestion:
    family: str | None
    top_n: int | None = None
    claim_id: str | None = None
    entity_name: str | None = None
    raw: str = ""
    metric_hints: list[str] = field(default_factory=list)
    window_hint: str | None = None
    topic_hints: list[str] = field(default_factory=list)


_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "composite": ("composite", "shooter", "shooting", "best shooters"),
    "fg3_pct": ("3pt", "three point", "3-point", "fg3", "threes"),
    "ts_pct": ("true shooting", "ts%", "ts pct", "ts_pct"),
    "efg_pct": ("effective field goal", "efg%", "efg pct", "efg"),
    "hold_pct_asof": ("hold serve", "holds serve", "hold%", "hold pct", "hold_pct", "service hold"),
    "k_rate": ("strikeout rate", "k-rate", "k rate", "k_rate", "strikeout%"),
    "strength": ("strongest", "team strength", "net expected goals", "strength rating"),
}


def _extract_window_hint(text: str) -> str | None:
    """Explicit 'window=last_20' / 'window: season_2024-25' style hint."""
    m = _WINDOW_RE.search(text)
    return m.group(1) if m else None


def _extract_metric_hints(text: str) -> list[str]:
    lower = text.lower()
    hits = []
    for metric, aliases in _METRIC_ALIASES.items():
        if any(a in lower for a in aliases):
            hits.append(metric)
    return hits


_TOPIC_ALIASES: dict[str, tuple[str, ...]] = {
    "tennis_surface": ("surface", "hold prior", "hold-prior", "atp", "wta", "tennis"),
    "nba_composition": ("composition", "shooter quality", "scorer quality", "quality blend", "nba"),
    "wnba_rest": ("rest covariate", "rest diff", "wnba rest", "+rest", "wnba"),
    "mlb_fatigue": ("fatigue", "velocity decline", "velo decline", "starting pitcher", "sp fatigue", "mlb"),
    "nba_positional": ("positional weight", "per-position", "posgroup", "guard/forward/center"),
    "nba_fit_validity": (
        "scheme fit", "fit validity", "fit predict", "predict performance",
        "after a move", "post-move",
    ),
}


def _extract_topic_hints(text: str) -> list[str]:
    lower = text.lower()
    hits = []
    for topic, aliases in _TOPIC_ALIASES.items():
        if any(a in lower for a in aliases):
            hits.append(topic)
    return hits


def gate_verdict_match_score(parsed: ParsedQuestion, row: dict[str, Any]) -> int:
    """Same scoring rule used by match_gate_verdict_candidates, exposed so
    callers can detect a genuine tie between the top candidates."""
    haystack = " ".join([
        str(row.get("gate_module", "")).lower(),
        str(row.get("claim_id", "")).lower(),
        str(row.get("question", "")).lower(),
    ])
    matched_tokens = 0
    for topic in parsed.topic_hints:
        aliases = _TOPIC_ALIASES.get(topic, ())
        matched_tokens += sum(1 for a in aliases if a in haystack)
    return matched_tokens


def match_gate_verdict_candidates(parsed: ParsedQuestion, verified: dict[str, Any]) -> list[dict[str, Any]]:
    """Match a gate_verdict question to VERIFIED claim_kind=verdict rows by a
    RECOGNIZED topic keyword (checked against gate_module/claim_id/question
    text, lowercase substring match, no fuzzy scoring). A question with no
    recognized topic_hint matches nothing -- honest UNANSWERABLE rather than
    guessing from generic overlap words like "gate" or "find".

    Returned list is DETERMINISTICALLY ordered (best match first): score
    DESC (count of distinct matched alias tokens, i.e. specificity), then
    claim_id ASC (lexicographic) as the final total order -- never
    dict/insertion order, which is not a meaningful ranking."""
    if not parsed.topic_hints:
        return []
    verdict_claims = [r for r in verified.values() if r.get("kind") == "verdict"]
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in verdict_claims:
        haystack = " ".join([
            str(row.get("gate_module", "")).lower(),
            str(row.get("claim_id", "")).lower(),
            str(row.get("question", "")).lower(),
        ])
        matched_tokens = gate_verdict_match_score(parsed, row)
        if matched_tokens > 0:
            scored.append((matched_tokens, row))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("claim_id", ""))))
    return [row for _score, row in scored]


def _extract_claim_id(text: str) -> str | None:
    """Pull the FIRST snake_case-looking token that resembles a claim_id.
    Provenance questions are expected to name the claim_id explicitly
    (e.g. 'show the evidence for nba_shooting_composite_last_20')."""
    for m in _CLAIM_ID_RE.finditer(text):
        token = m.group(1)
        if "_" in token:
            return token
    return None


def _extract_entity_name(text: str) -> str | None:
    """Best-effort entity name extraction for entity-lookup questions:
    text between 'does'/'for' and 'rank'/'on', or a capitalized run of
    words. Deterministic, no NLP model -- good enough for the CLI/tool
    surface where the caller usually names the player directly."""
    m = re.search(
        r"\bdoes\s+(.+?)\s+rank\b", text, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    m = re.search(
        r"\bwhat is\s+(.+?)'s\b", text, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    m = re.search(
        r"\bfor\s+([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+)+)\b", text
    )
    if m:
        return m.group(1).strip()
    return None


def classify(question: str) -> ParsedQuestion:
    """Deterministically classify a question into a supported family.

    Order matters: provenance (explicit claim_id + evidence words) is
    checked first since it can otherwise look like a top-N or lookup
    question if the claim_id itself contains digits/words like 'top'.
    gate_verdict is checked next -- "what did the gate find" / "did X beat
    Y" phrasing is distinctive enough it should not fall through to top_n
    or entity_lookup (which need a metric/player, not a gate topic)."""
    text = question or ""
    window_hint = _extract_window_hint(text)
    topic_hints = _extract_topic_hints(text)

    if _PROVENANCE_WORDS.search(text):
        claim_id = _extract_claim_id(text)
        return ParsedQuestion(
            family=FAMILY_PROVENANCE, claim_id=claim_id, raw=question,
            metric_hints=_extract_metric_hints(text), window_hint=window_hint,
            topic_hints=topic_hints,
        )

    if _GATE_VERDICT_WORDS.search(text):
        return ParsedQuestion(
            family=FAMILY_GATE_VERDICT, raw=question,
            metric_hints=_extract_metric_hints(text), window_hint=window_hint,
            topic_hints=topic_hints,
        )

    top_n_match = _TOP_N_RE.search(text)
    if top_n_match or _TOP_NONUM_RE.search(text):
        n_str = (top_n_match.group(1) or top_n_match.group(2)) if top_n_match else None
        return ParsedQuestion(
            family=FAMILY_TOP_N,
            top_n=int(n_str) if n_str else None,
            raw=question,
            metric_hints=_extract_metric_hints(text),
            window_hint=window_hint,
            topic_hints=topic_hints,
        )

    if _RANK_LOOKUP_RE.search(text):
        return ParsedQuestion(
            family=FAMILY_ENTITY_LOOKUP,
            entity_name=_extract_entity_name(text),
            raw=question,
            metric_hints=_extract_metric_hints(text),
            window_hint=window_hint,
            topic_hints=topic_hints,
        )

    return ParsedQuestion(
        family=None, raw=question, metric_hints=_extract_metric_hints(text), window_hint=window_hint,
        topic_hints=topic_hints,
    )


def describe_families() -> list[dict[str, Any]]:
    """Human-readable family descriptions -- used to populate
    nearest_supported_families in the honest-unanswerable response."""
    return [
        {"family": FAMILY_TOP_N, "example": "Who are the top 10 best shooters (composite) in window=last_20?"},
        {"family": FAMILY_ENTITY_LOOKUP, "example": "Where does Stephen Curry rank on fg3_pct in window=season_2024-25?"},
        {"family": FAMILY_PROVENANCE, "example": "How do you know? Show the evidence for nba_shooting_composite_last_20."},
        {"family": FAMILY_GATE_VERDICT, "example": "What did the tennis surface gate find?"},
    ]
