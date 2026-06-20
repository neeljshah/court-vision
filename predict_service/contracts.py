"""predict_service.contracts -- frozen, JSON-round-trippable schemas for the
canonical predict-service snapshot.

This module is the SINGLE SOURCE OF TRUTH for the shapes that both CourtVision
(the frontend / FastAPI surface) and the paper-trading engine read out of the
canonical store. Define the schema here ONCE; every producer and consumer
conforms to it via to_dict / from_dict so a snapshot written today still parses
tomorrow (schema_version is stamped on every envelope).

HONESTY (binding, enforced by shape): an EdgeRow carries probability/EV and a
CLV-proxy flag -- it has NO dollar / $edge field, by construction. We never
fabricate an ROI. CLV ("better number than the close") is computed downstream by
the vetted scripts.platformkit.clv_ledger.compute_clv -- never reimplemented and
never stored as a money edge here. Markets are efficient; this is calibrated
decision-support, not a profit claim.

Stake sizing (flat_unit + quarter_kelly) is RECORDED BY THE PAPER ENGINE later,
not here. What we DO carry is everything that engine needs to size a stake: the
model probability, the market probability, the EV, and the evidence tier.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; dataclasses
(stdlib) matching repo convention; no secrets; no $-edge field anywhere.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional

# The 1.1.0 ADDITIVE shapes live in contracts_v11 (LOC budget) but are part of
# the SAME frozen contract: import + re-export so consumers keep importing them
# from predict_service.contracts. A merged number is phase-LABELLED, never an
# average; no $ field on any of these.
from predict_service.contracts_v11 import (  # noqa: F401  (re-exported)
    PHASE_INGAME,
    PHASE_MERGED,
    PHASE_PREGAME,
    VALID_PHASES,
    Interval,
    ProbEstimate,
    Provenance,
)

# Bumped whenever a field is added/removed/renamed below. Stamped on every
# SnapshotEnvelope so a reader can detect (and reject) an incompatible shape.
#
# 1.1.0 (2026-06-19, WAVE 3): ADDITIVE, non-breaking. Adds ProbEstimate +
# Provenance (a contracted, provenance-stamped probability with an optional
# held-out interval) and gives EdgeRow a vs_close field defaulting UNPROVEN.
# Every 1.0.0 field is intact and round-trips unchanged; a 1.0.0 reader ignoring
# the new keys still parses a 1.1.0 envelope (forward-compat via _filter_known).
#
# 1.2.0 (2026-06-20, BE-R3-1): ADDITIVE, non-breaking. Adds game_state field
# to PredictionRecord ('pre'|'live'|'post'). A 1.1.0 reader ignoring the new
# key still parses a 1.2.0 envelope (forward-compat via _filter_known).
SCHEMA_VERSION = "1.2.0"

# Valid game_state values. Derived authoritatively at the producer so every
# downstream consumer (edges, bestbets, slate, FE LiveDot) reads it from the
# envelope rather than re-deriving LIVE from tipoff-in-past.
GAME_STATE_PRE = "pre"
GAME_STATE_LIVE = "live"
GAME_STATE_POST = "post"
VALID_GAME_STATES = (GAME_STATE_PRE, GAME_STATE_LIVE, GAME_STATE_POST)

# Typical NBA game duration used when no explicit live.state is available.
# 2.5 h covers 4 quarters + stoppages + OT margin; after this window a game
# without explicit live data is assumed finished (state='post').
_TYPICAL_GAME_DURATION_SECONDS = int(2.5 * 3600)

# (Phase constants PHASE_PREGAME/PHASE_INGAME/PHASE_MERGED + VALID_PHASES are
# imported from contracts_v11 above and re-exported here -- a merged number is
# LABELLED by phase, NEVER silently averaged into an unlabelled scalar.)

# vs_close default. The honest rail: a model number is presumed NOT proven to beat
# the close until a gate (>=2 corpora + DM + a true close) upgrades it. We default
# to UNPROVEN everywhere and only a downstream gate may set PROVEN/MATCH.
VS_CLOSE_UNPROVEN = "UNPROVEN"
VS_CLOSE_MATCH = "MATCH"          # calibrated, matches the devigged close (success)
VS_CLOSE_PROVEN = "PROVEN"        # gate-proven beat (>=2 corpora + DM + true close)
VALID_VS_CLOSE = (VS_CLOSE_UNPROVEN, VS_CLOSE_MATCH, VS_CLOSE_PROVEN)

# Honest, repeated everywhere a snapshot is surfaced: no money edge is claimed.
HONEST_NOTE = (
    "Calibrated decision-support only. Markets are efficient; no $ edge is "
    "claimed. Edges are probability/EV; CLV (better-number-than-close) is the "
    "only honest yardstick and is computed by the vetted clv_ledger."
)


def _filter_known(cls: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only keys that are declared fields of *cls* (forward-compat reads)."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in (data or {}).items() if k in names}


@dataclass
class MarketRow:
    """One market quote line (a single book's price for one side of one market).

    market_type is one of 'moneyline' / 'spread' / 'total'. devigged_prob is the
    no-vig fair probability for *side* (None until devigged). is_close marks the
    closing line (used for CLV). clv_is_proxy is True when the "close" we settle
    against is a proxy (e.g. last-seen pre-tip price), not a true settled close --
    surfaced, never hidden.
    """
    sport: str
    game_id: str
    market_type: str
    side: str
    line: Optional[float] = None
    odds: Optional[float] = None          # decimal price as quoted
    book: str = ""                         # book / source name
    devigged_prob: Optional[float] = None
    captured_at: Optional[str] = None      # ISO-8601 UTC
    is_close: bool = False
    clv_is_proxy: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketRow":
        return cls(**_filter_known(cls, data))


@dataclass
class EdgeRow:
    """Model-vs-market edge for one market. NO dollar / $edge field -- by design.

    ev is the expected value per 1 unit staked at *market_prob* given *model_prob*
    (a pure probability ratio, NOT a dollar amount). tier is an evidence label
    'A' / 'B' / 'C' (or None when unmeasured). market_ref points back at the
    MarketRow this edge was computed against (book + market_type + side).

    vs_close (1.1.0, ADDITIVE) defaults VS_CLOSE_UNPROVEN: a model number is
    presumed NOT proven to beat the close until a gate (>=2 corpora + DM + true
    close) upgrades it. It is an EVIDENCE LABEL, never a $ claim.
    """
    game_id: str
    market_type: str
    side: str
    model_prob: float
    market_prob: float
    ev: float
    tier: Optional[str] = None
    book: str = ""
    line: Optional[float] = None
    clv_is_proxy: bool = False
    vs_close: str = VS_CLOSE_UNPROVEN

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EdgeRow":
        kw = _filter_known(cls, data)
        vc = kw.get("vs_close")
        # Guard: an unknown / missing vs_close degrades to UNPROVEN (never PROVEN).
        if vc not in VALID_VS_CLOSE:
            kw["vs_close"] = VS_CLOSE_UNPROVEN
        return cls(**kw)


@dataclass
class PredictionRecord:
    """One game's model output: teams, tipoff, pregame probabilities + markets.

    pregame_probs holds the model's calibrated probabilities (e.g.
    {'home_ml': 0.58, 'draw': 0.27, ...}). markets holds the MarketRows seen for
    this game. leak_guard records the in_sample flag (an honest in-sample
    prediction is flagged so it is never mistaken for OOS).

    game_state (1.2.0, ADDITIVE) is one of VALID_GAME_STATES ('pre'|'live'|'post').
    Derived authoritatively by the producer at emit time so every downstream
    consumer reads the authoritative answer from the envelope rather than
    re-deriving LIVE from tipoff-in-past (the stale-game-as-LIVE leak, BE-R3-1).
    """
    sport: str
    game_id: str
    home: str
    away: str
    tipoff: Optional[str] = None           # ISO-8601 UTC
    pregame_probs: Dict[str, float] = field(default_factory=dict)
    markets: List[MarketRow] = field(default_factory=list)
    leak_guard: Dict[str, bool] = field(default_factory=lambda: {"in_sample": False})
    produced_at: Optional[str] = None      # ISO-8601 UTC
    game_state: str = GAME_STATE_PRE       # 'pre'|'live'|'post'
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["markets"] = [m.to_dict() for m in self.markets]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PredictionRecord":
        kw = _filter_known(cls, data)
        kw["markets"] = [MarketRow.from_dict(m) for m in (data or {}).get("markets", [])]
        lg = dict((data or {}).get("leak_guard", {}) or {})
        lg.setdefault("in_sample", False)
        kw["leak_guard"] = {"in_sample": bool(lg.get("in_sample", False))}
        # game_state: guard against unknown / missing values (safe degradation to 'pre').
        gs = kw.get("game_state")
        if gs not in VALID_GAME_STATES:
            kw["game_state"] = GAME_STATE_PRE
        return cls(**kw)


@dataclass
class SnapshotEnvelope:
    """Top-level stored object both CourtVision and the paper engine read.

    A single canonical snapshot for one sport at one point in time. status is
    'ok' when the snapshot is complete and usable, 'unavailable' for the sentinel
    a reader returns when the file is missing / partial (NEVER a torn read).
    schema_version is always stamped so an incompatible shape is detectable.
    """
    sport: str
    generated_at: str                      # ISO-8601 UTC
    schema_version: str = SCHEMA_VERSION
    status: str = "ok"
    predictions: List[PredictionRecord] = field(default_factory=list)
    markets: List[MarketRow] = field(default_factory=list)
    edges: List[EdgeRow] = field(default_factory=list)
    honest_note: str = HONEST_NOTE
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sport": self.sport,
            "generated_at": self.generated_at,
            "status": self.status,
            "predictions": [p.to_dict() for p in self.predictions],
            "markets": [m.to_dict() for m in self.markets],
            "edges": [e.to_dict() for e in self.edges],
            "honest_note": self.honest_note,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SnapshotEnvelope":
        data = data or {}
        return cls(
            sport=str(data.get("sport", "")),
            generated_at=str(data.get("generated_at", "")),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
            status=str(data.get("status", "ok")),
            predictions=[PredictionRecord.from_dict(p)
                         for p in data.get("predictions", []) or []],
            markets=[MarketRow.from_dict(m) for m in data.get("markets", []) or []],
            edges=[EdgeRow.from_dict(e) for e in data.get("edges", []) or []],
            honest_note=str(data.get("honest_note", HONEST_NOTE)),
            note=str(data.get("note", "")),
        )

    @classmethod
    def unavailable(cls, sport: str, generated_at: str = "",
                    reason: str = "") -> "SnapshotEnvelope":
        """The status='unavailable' sentinel a reader returns instead of raising."""
        return cls(sport=str(sport), generated_at=str(generated_at),
                   status="unavailable", note=str(reason))


__all__ = [
    "SCHEMA_VERSION",
    "HONEST_NOTE",
    "PHASE_PREGAME",
    "PHASE_INGAME",
    "PHASE_MERGED",
    "VALID_PHASES",
    "VS_CLOSE_UNPROVEN",
    "VS_CLOSE_MATCH",
    "VS_CLOSE_PROVEN",
    "VALID_VS_CLOSE",
    "GAME_STATE_PRE",
    "GAME_STATE_LIVE",
    "GAME_STATE_POST",
    "VALID_GAME_STATES",
    "MarketRow",
    "Provenance",
    "Interval",
    "ProbEstimate",
    "EdgeRow",
    "PredictionRecord",
    "SnapshotEnvelope",
]
