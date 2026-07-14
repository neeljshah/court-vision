"""scripts.platformkit.live_edge.news.parser -- rule-first free-text injury-status parser.

THE GAP: ESPN's OWN injury/news feeds are already structured (injury_facts.py /
news_facts.py extract status/entities from JSON fields, zero NLP needed). But
RSS/tweet/nitter items are NOT structured -- a beat-writer sentence like
"Tatum (knee) has been ruled out for Saturday's game" needs regex extraction of
{status, player_name_raw} before it can join the vintage-guarded pipeline. This
module is that extractor: pure regex, no LLM, no network.

LLM discipline (S9.6): parse_via_llm() is a STUB seam only -- returns None,
never calls an API. If ever wired, it stays PARSING only (never guesses an
effect/number); the golden-set test in test_news_parse.py gates any promotion.

Status vocabulary + priority (more specific phrases checked before the
generic OUT catch-all so "questionable"/"doubtful"/"probable"/"day-to-day"/
"GTD" don't get swallowed by a coincidental "out" substring elsewhere in the
sentence): OUT, DOUBTFUL, QUESTIONABLE, PROBABLE, DAY_TO_DAY, GTD.

minutes_implication ordinal mirrors omni/news_knowability.py's scale (higher
= more likely to play) so a future feature_store wire-in is a drop-in, but
this module does NOT import or write to feature_store (out of scope for the
A2 Day-1 DONE bar; avoids touching the concurrently-owned omni/ tree).

<=300 LOC. ASCII stdout. Per-file test: tests/platformkit/live_edge/test_news_parse.py.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

# Ordinal = likelihood of playing (higher = more likely). Mirrors
# omni/news_knowability.py's _STATUS_ORDINAL scale for future interop.
MINUTES_IMPLICATION: Dict[str, int] = {
    "OUT": 0,
    "DOUBTFUL": 1,
    "QUESTIONABLE": 2,
    "DAY_TO_DAY": 2,
    "GTD": 2,
    "PROBABLE": 3,
}

# Ordered (specific -> generic): first match wins. Word-boundary regex so
# "without"/"outing" etc never false-match the OUT catch-all.
_STATUS_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("DOUBTFUL", re.compile(r"\bdoubtful\b", re.IGNORECASE)),
    ("QUESTIONABLE", re.compile(r"\bquestionable\b", re.IGNORECASE)),
    ("PROBABLE", re.compile(r"\bprobable\b", re.IGNORECASE)),
    ("GTD", re.compile(r"\bgtd\b|\bgame-time decision\b|\bgame time decision\b", re.IGNORECASE)),
    ("DAY_TO_DAY", re.compile(r"\bday-to-day\b|\bday to day\b", re.IGNORECASE)),
    ("OUT", re.compile(
        r"\bruled out\b|\bis out\b|\bwon'?t play\b|\bwill not play\b|"
        r"\blisted (?:as )?out\b|\bunavailable\b|\bhas been ruled out\b|"
        r"\bsitting out\b",
        re.IGNORECASE,
    )),
]

# Player name (raw, un-joined -- caller/resolver maps to player_id): the leading
# capitalized token(s) before the first "(" (injury parenthetical) or the first
# status verb. Real captured items are consistently "Lastname (injury) ..." or
# "Lastname is/won't/has been ...".
_NAME_RE = re.compile(
    r"^([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+)?)\s*(?:\(|is\b|won'?t\b|will\b|has\b)"
)


def extract_status(text: str) -> Optional[str]:
    """First matching status token in *text*, or None if no known status word appears."""
    for label, pat in _STATUS_PATTERNS:
        if pat.search(text):
            return label
    return None


def extract_player_name_raw(text: str) -> Optional[str]:
    """Leading name-shaped token(s) from *text*; None if the text doesn't start with one."""
    m = _NAME_RE.match(text.strip())
    return m.group(1) if m else None


def parse_via_llm(text: str) -> Optional[Dict[str, Any]]:  # pragma: no cover - stub, unused
    """LLM parsing hook -- STUB ONLY, never calls an API today (S9.6 discipline).

    Returns None always. A future wire-in would delegate to the same
    extract.extract_llm seam used by edge_engine/news_facts.py, gated behind
    an env flag, and would still be adjudicated by this module's golden-set
    test before any promotion.
    """
    return None


def parse_item(text: str, *, report_ts: str, source: str = "unknown") -> Dict[str, Any]:
    """Rule-first parse of one raw text item -> the A2 row shape.

    {player_id_raw, status, minutes_implication, confidence, report_ts}.
    confidence is a plain heuristic (not a model output): 0.9 when both a
    status word AND a name-shaped lead were found, 0.6 when only the status
    matched (name extraction failed -- still useful, just unattributed),
    0.0 when no status word was found at all (raw retained, parse deferred
    per the A2 DONE bar -- caller decides whether to keep the raw item).
    """
    status = extract_status(text)
    name = extract_player_name_raw(text)
    if status is None:
        confidence = 0.0
    elif name is not None:
        confidence = 0.9
    else:
        confidence = 0.6
    return {
        "player_id_raw": name,
        "status": status,
        "minutes_implication": MINUTES_IMPLICATION.get(status) if status else None,
        "confidence": confidence,
        "report_ts": report_ts,
        "source": source,
    }


if __name__ == "__main__":  # pragma: no cover - manual smoke check
    import json as _json
    sample = "Tatum (knee) has been ruled out for Saturday's Game 7 against the 76ers."
    print(_json.dumps(parse_item(sample, report_ts="2026-07-14T00:00:00+00:00", source="demo")))
