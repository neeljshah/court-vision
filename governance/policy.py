"""governance.policy -- the SINGLE SOURCE of governance constants every gate reads.

Every governance gate imports its banned numbers, banned tokens, thresholds, and
provenance vocabulary FROM HERE, so all gates measure against the same constants
and cannot silently drift apart. This module owns no I/O and makes no decision; it
is pure policy data plus tolerant matchers.

The canonical truth source is ``.claude/rules/no-edge-claims.md`` (and
``docs/JOB_EVIDENCE_PACKET.md`` it points to). The product is a CALIBRATED
predictor, NOT a $ROI / edge product: there is no $edge field anywhere, and the
retracted measurement-artifact figures must NEVER appear as a live result -- they
are permitted ONLY inside an explicit retraction / citation context.

The real-money thresholds are RE-EXPORTED from the vetted, decision-only
``scripts.platformkit.pm_trading.realmoney_gate`` (M4) so there is exactly one
definition of the conservative real-money bar; this module never redefines them.

INVARIANTS: build only under governance/; <=300 LOC; ASCII only; no secrets; no
$-edge claim; no I/O; never authorizes a bet; never flips a flag.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Dict, List, NamedTuple, Optional

from scripts.platformkit.pm_trading import realmoney_gate as _rmg

POLICY_VERSION = "governance.policy.v1"

# ---------------------------------------------------------------------------
# BANNED NUMBERS -- the RETRACTED measurement-artifact figures.
# These are documented artifacts (see no-edge-claims.md). They may appear ONLY
# inside an explicit retraction / citation context; never as a live result.
# Matching is TOLERANT: the canonical decimal token is detected with optional
# leading +/- and optional surrounding '%', regardless of nearby formatting.
# ---------------------------------------------------------------------------


class BannedNumber(NamedTuple):
    """One retracted figure: its canonical token, why it is banned, and a regex.

    *token* is the canonical decimal string (e.g. "18.38"). *value* is the same as
    a float for numeric comparison. *pattern* matches the token as a standalone
    number (optional sign, optional trailing '%') with word-ish boundaries so it
    does not fire on an unrelated longer number that merely contains the digits.
    """
    token: str
    value: float
    reason: str
    pattern: "re.Pattern[str]"

    def matches(self, text: str) -> bool:
        return bool(self.pattern.search(text or ""))


def _num_pattern(token: str, *, require_context: bool = False) -> "re.Pattern[str]":
    """Tolerant standalone-number regex for *token* (e.g. "18.38" or "0.119").

    Allows an optional sign and optional trailing percent sign, and requires the
    matched number not to be embedded in a longer number (no adjacent digit / dot
    on either side). Case-insensitive is irrelevant for digits but harmless.

    When *require_context* is True the bare digits alone do NOT match -- the token
    must carry an explicit percent/sign context (a leading '+'/'-' OR a trailing
    '%'). This is needed for a short, otherwise-common integer token (e.g. "54"),
    which as a bare number collides with innocuous text (an ISO ':54' second, a
    page count) and would otherwise fire a false honesty violation. The retracted
    figure is "+54%" / "54%", never a standalone 54, so we only ban it in context.
    """
    esc = re.escape(token)
    if require_context:
        # Require EITHER a leading sign OR a trailing percent (not a bare number).
        signed = r"(?<![\d.])[+-]" + esc + r"\s*%?(?![\d.])"
        pct = r"(?<![\d.])[+-]?" + esc + r"\s*%(?![\d.])"
        return re.compile(r"(?:" + signed + r"|" + pct + r")")
    return re.compile(r"(?<![\d.])[+-]?" + esc + r"\s*%?(?![\d.])")


# Each entry is (token, value, reason, require_context). *require_context* True
# means the bare digits do NOT match -- the token must carry +/- or % context (see
# _num_pattern). "54" is context-gated so a standalone 54 (ISO :54 second, a count)
# does not raise a false honesty 500; the retracted figure is "+54%" / "54%".
_RAW_BANNED = (
    ("18.38", 18.38, "pregame ROI -- a market-follow artifact, not the model", False),
    ("0.119", 0.119, "endQ3 win-prob -- a Q4 leak", False),
    ("54", 54.0, "in-play -- an L5-proxy ceiling, not realized edge", True),
    ("78.11", 78.11, "in-play 78% accuracy -- same L5-proxy ceiling", False),
    ("8.94", 8.94, "retracted inflated figure", False),
    ("54.57", 54.57, "retracted inflated figure", False),
)

BANNED_NUMBERS: List[BannedNumber] = [
    BannedNumber(token=t, value=v, reason=r,
                 pattern=_num_pattern(t, require_context=ctx))
    for (t, v, r, ctx) in _RAW_BANNED
]

#: Quick lookup of the canonical banned tokens.
BANNED_NUMBER_TOKENS: List[str] = [b.token for b in BANNED_NUMBERS]

# ---------------------------------------------------------------------------
# BANNED TOKENS -- forbidden field / claim strings that must NEVER appear as a
# live claim. The product carries probability/EV only; there is no dollar edge,
# no guaranteed profit, no fabricated-ROI marker. Matched case-insensitively.
# ---------------------------------------------------------------------------
BANNED_TOKENS: List[str] = [
    "$edge",
    "dollar_edge",
    "dollar-edge",
    "dollaredge",
    "roi_edge",
    "roi edge",
    "guaranteed",
    "guaranteed profit",
    "guaranteed_profit",
    "sure thing",
    "risk-free profit",
    "risk_free_profit",
    "lock of the day",
    "fabricated_profit",
    "profit_guarantee",
]

#: Lower-cased forms for fast membership / substring scans.
BANNED_TOKENS_LOWER: List[str] = [t.lower() for t in BANNED_TOKENS]

# ---------------------------------------------------------------------------
# RETRACTION-CONTEXT WHITELIST -- a banned NUMBER inside explicit retraction /
# citation framing is ALLOWED (the honesty docs MUST be able to name the artifact
# in order to retract it). These markers signal that context. A line / block that
# contains one of these markers is exempt from the banned-number check.
# ---------------------------------------------------------------------------
RETRACTION_MARKERS: List[str] = [
    "retract",          # retracted / retraction
    "artifact",         # measurement artifact
    "do-not-claim",
    "do not claim",
    "never claim",
    "never print",
    "no-edge-claims",
    "JOB_EVIDENCE_PACKET",
    "KNOWN_LIMITATIONS",
    "not the model",
    "not realized",
    "leak)",            # "(a Q4 leak)" style retraction note
]

_RETRACTION_MARKERS_LOWER: List[str] = [m.lower() for m in RETRACTION_MARKERS]


def is_retraction_context(text: str) -> bool:
    """True if *text* carries explicit retraction / citation framing.

    When True, a banned NUMBER appearing in the same text is permitted: the
    honesty docs are allowed (indeed required) to name the artifact to retract it.
    Banned TOKENS are never whitelisted by this -- a $edge field is wrong even in
    a retraction.
    """
    low = (text or "").lower()
    return any(m in low for m in _RETRACTION_MARKERS_LOWER)


# ---------------------------------------------------------------------------
# THRESHOLDS -- the conservative real-money criteria, RE-EXPORTED from the vetted
# pm_trading.realmoney_gate (M4) so there is exactly one definition. Plus the
# governance-layer threshold(s). Named constants; gates read these, never literals.
# ---------------------------------------------------------------------------
MIN_SETTLED_N: int = _rmg.MIN_SETTLED_N
CLV_BOOTSTRAP_LB_MIN: float = _rmg.CLV_BOOTSTRAP_LB_MIN
MIN_PCT_BEAT_CLOSE: float = _rmg.MIN_PCT_BEAT_CLOSE
MIN_TRUE_CLOSE_FRAC: float = _rmg.MIN_TRUE_CLOSE_FRAC
REALMONEY_GATE_VERSION: str = _rmg.GATE_VERSION

#: Governance default: the stack is INELIGIBLE for real money unless a gate
#: explicitly clears it AND a human flip + valid signed token are present.
DEFAULT_REALMONEY_ELIGIBLE: bool = False

#: Aggregated, frozen view of the real-money bar (echoed by gates / logs).
REALMONEY_THRESHOLDS: Dict[str, float] = {
    "min_settled_n": MIN_SETTLED_N,
    "clv_bootstrap_lb_min": CLV_BOOTSTRAP_LB_MIN,
    "min_pct_beat_close": MIN_PCT_BEAT_CLOSE,
    "min_true_close_frac": MIN_TRUE_CLOSE_FRAC,
}


# ---------------------------------------------------------------------------
# PROVENANCE -- the allowed provenance of any number surfaced to a user. Anything
# FILLED or UNKNOWN must be FLAGGED and never presented as a REAL_MODEL output.
# ---------------------------------------------------------------------------
class Provenance(str, Enum):
    """Provenance of a number surfaced to a user.

    REAL_MODEL      -- produced by the validated forecaster / sim. Presentable.
    CAPTURED_MARKET -- a real captured market quote (true close / live book).
    DERIVED         -- deterministically computed from REAL/CAPTURED inputs.
    FILLED          -- imputed / placeholder / percentile-filled. MUST be flagged;
                       never presented as a real result.
    UNAVAILABLE     -- explicitly missing (sentinel); presented as "unavailable".
    UNKNOWN         -- provenance not established. MUST be flagged; treat as unsafe.
    """
    REAL_MODEL = "REAL_MODEL"
    CAPTURED_MARKET = "CAPTURED_MARKET"
    DERIVED = "DERIVED"
    FILLED = "FILLED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


#: Provenances that may be presented to a user as a genuine number.
PRESENTABLE_PROVENANCE = frozenset(
    {Provenance.REAL_MODEL, Provenance.CAPTURED_MARKET, Provenance.DERIVED})

#: Provenances that must be FLAGGED and never presented as REAL.
FLAGGED_PROVENANCE = frozenset(
    {Provenance.FILLED, Provenance.UNKNOWN})


def provenance_must_be_flagged(p: Provenance) -> bool:
    """True iff *p* may NOT be presented as a real number (FILLED / UNKNOWN)."""
    return Provenance(p) in FLAGGED_PROVENANCE


def find_banned_numbers(text: str, *, respect_retraction: bool = True) -> List[str]:
    """Return the canonical tokens of banned NUMBERS present in *text*.

    When *respect_retraction* is True (default) and *text* carries explicit
    retraction framing, the result is empty (the artifact may be named to retract
    it). Banned tokens are detected by :data:`BANNED_NUMBERS`.
    """
    if respect_retraction and is_retraction_context(text):
        return []
    return [b.token for b in BANNED_NUMBERS if b.matches(text)]


def find_banned_tokens(text: str) -> List[str]:
    """Return the banned CLAIM tokens present in *text* (case-insensitive).

    Banned tokens are NEVER whitelisted by retraction context: a $edge field or a
    "guaranteed" claim is wrong even inside a retraction note.
    """
    low = (text or "").lower()
    return [orig for orig, low_tok in zip(BANNED_TOKENS, BANNED_TOKENS_LOWER)
            if low_tok in low]


__all__ = [
    "POLICY_VERSION",
    "BannedNumber",
    "BANNED_NUMBERS",
    "BANNED_NUMBER_TOKENS",
    "BANNED_TOKENS",
    "BANNED_TOKENS_LOWER",
    "RETRACTION_MARKERS",
    "is_retraction_context",
    "MIN_SETTLED_N",
    "CLV_BOOTSTRAP_LB_MIN",
    "MIN_PCT_BEAT_CLOSE",
    "MIN_TRUE_CLOSE_FRAC",
    "REALMONEY_GATE_VERSION",
    "DEFAULT_REALMONEY_ELIGIBLE",
    "REALMONEY_THRESHOLDS",
    "Provenance",
    "PRESENTABLE_PROVENANCE",
    "FLAGGED_PROVENANCE",
    "provenance_must_be_flagged",
    "find_banned_numbers",
    "find_banned_tokens",
]
