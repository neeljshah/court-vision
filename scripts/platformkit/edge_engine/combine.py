"""edge_engine.combine -- the BOUNDED COMBINER (the scheme-prior pattern, fused).

THESIS (binding): the edge is NOT better prediction (price is efficient). It is a
PROPRIETARY + PREDICTIVE + TIMELY input fused FASTER than the market into ONE bounded
net adjustment on an EXISTING model knob -- and that adjustment FIRES ONLY when the
combined signal clears a gate threshold AND the line has not yet moved.

This module fuses N already-SHIPPED weak signals (each carries an extracted FACT, an
EXTRACTION confidence, a per-signal gate weight, and a vintage availability_ts) into a
SINGLE leak-flagged multiplier on one named knob -- exactly the scheme-prior law:

  * The LLM NEVER authors the number. It extracts FACTS + confidence only. combine.py
    computes the multiplier deterministically from GATE-assigned signal weights.
  * Confidence-shrink then hard-clamp: eff = 1 + sum(weight_i * conf_i * (lean_i)),
    then clamp to a deliberately TIGHT band so a confidently-wrong fusion can nudge but
    never dominate. (Mirrors src/sim/scheme_prior.py eff/clamp law.)
  * FIRES only when |combined lean| >= gate_threshold (weak/conflicting signals -> 1.0,
    a no-op -- the honest default is "do nothing").
  * LEAK-FREE per game: EVERY contributing signal's availability_ts must be strictly
    before the line-move timestamp, else the whole fusion is REFUSED (no partial leak).

HONESTY RAILS: no probability/outcome number rides on a signal row; no $/ROI/+EV; the
combiner emits a clamped MULTIPLIER on an existing knob, never a prediction. A fusion
that does not clear the threshold is a NO-OP, which is an honest, recorded default.

Reuses freshness.as_of_reader.assert_vintage READ-ONLY for the leak guard. Stdlib only,
no numpy needed. <=300 LOC. Per-file test: test_combine.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# Reuse the existing vintage guard -- do NOT reimplement leak checking.
try:  # package import
    from scripts.platformkit.freshness.as_of_reader import assert_vintage  # type: ignore
except ImportError:  # direct-script / per-file-test fallback
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "freshness"))
    from as_of_reader import assert_vintage  # type: ignore

# Numeric/outcome fields that must NEVER ride on a signal row (honesty rail).
_BANNED_FIELDS: Tuple[str, ...] = (
    "win_prob", "probability", "prob", "edge", "ev", "roi", "spread",
    "total", "price", "odds", "line", "payout",
)

# Knob bands: each named EXISTING knob the combiner may nudge, with a TIGHT clamp.
# A fused multiplier is hard-clamped into [lo, hi]; outside the band it saturates.
# Bands mirror the scheme-prior PARAM_SPEC philosophy: shape, never dominate.
KNOB_BANDS: Dict[str, Tuple[float, float]] = {
    "pace":         (0.94, 1.06),   # possessions / tempo knob
    "off_eff":      (0.95, 1.05),   # team offensive efficiency knob
    "def_eff":      (0.95, 1.05),   # team defensive efficiency knob
    "minutes_load": (0.90, 1.10),   # redistributed-minutes (fatigue/rotation) knob
    "total_pts":    (0.96, 1.04),   # game-total knob (tightest -- totals are sharp)
}

# The combiner default-fires nothing below this combined-lean magnitude.
DEFAULT_GATE_THRESHOLD = 0.02


@dataclass(frozen=True)
class GatedSignal:
    """One already-SHIPPED weak signal that passed the gate, ready to be fused.

    The LLM filled `confidence` (EXTRACTION confidence) and `fact_text` (verbatim FACT)
    ONLY. `weight` is assigned by the GATE (its measured per-corpus reliability), never by
    the LLM. `lean` is the FACT's signed direction on the knob in {-1, 0, +1} -- a
    deterministic mapping from the extracted FACT (e.g. 'minutes restriction' -> -1 on
    minutes_load), NOT a magnitude the LLM authored.
    """
    signal: str
    knob: str
    lean: int               # signed direction in {-1, 0, +1}, from the FACT (not a number)
    weight: float           # GATE-assigned reliability weight in [0, 1]
    confidence: float       # [0, 1] EXTRACTION confidence ONLY (never an outcome prob)
    availability_ts: str    # ISO datetime the FACT became public -- the vintage key
    subject_id: str         # team_id / player_id the knob attaches to
    fact_text: str = ""     # verbatim extracted FACT (evidence span)
    source: str = ""        # provenance

    def as_dict(self) -> dict:
        return {
            "signal": self.signal, "knob": self.knob, "lean": self.lean,
            "weight": self.weight, "confidence": self.confidence,
            "availability_ts": self.availability_ts, "subject_id": self.subject_id,
            "fact_text": self.fact_text, "source": self.source,
        }


@dataclass(frozen=True)
class Combined:
    """The single bounded net adjustment the combiner emits for one (knob, subject).

    `multiplier` is the clamped number that may enter an EXISTING knob. `fired` is False
    when the combined lean did not clear the threshold -> multiplier is exactly 1.0 (no-op,
    the honest default). `contributors` lists which signals moved it. NO probability rides
    here -- the combiner outputs a knob multiplier, never a prediction.
    """
    knob: str
    subject_id: str
    multiplier: float
    fired: bool
    combined_lean: float
    n_signals: int
    contributors: Tuple[str, ...]
    clamped: bool


def validate_signal(d: dict) -> None:
    """Raise AssertionError on a malformed signal row. Runs DOWNSTREAM of LLM extraction.

    Enforces required fields, enum/band membership, and crucially that NO probability /
    outcome number sneaked onto the row (the LLM never authors a number that predicts).
    """
    req = ("signal", "knob", "lean", "weight", "confidence",
           "availability_ts", "subject_id")
    for k in req:
        assert k in d and d[k] not in (None, ""), f"missing/empty field {k}"
    assert d["knob"] in KNOB_BANDS, f"unknown knob {d['knob']}"
    assert d["lean"] in (-1, 0, 1), f"lean must be in {{-1,0,+1}}, got {d['lean']}"
    for fld in ("weight", "confidence"):
        try:
            v = float(d[fld])
        except (TypeError, ValueError):
            raise AssertionError(f"{fld} not numeric")
        assert 0.0 <= v <= 1.0, f"{fld} out of [0,1]"
    # honesty rail: no outcome/$ number may ride on a signal row.
    for k in d:
        assert k not in _BANNED_FIELDS, f"FORBIDDEN outcome/$ field on a signal row: {k}"


def assert_all_leak_free(signals: Sequence[GatedSignal], line_move_ts: str) -> None:
    """Refuse the WHOLE fusion unless EVERY signal was known strictly before the line move.

    No partial leak: one hindsight signal poisons the combination, so we fail the entire
    fusion (AssertionError with 'LEAK') rather than silently drop the offender. Reuses the
    freshness vintage guard keyed on extracted_at.
    """
    for s in signals:
        validate_signal(s.as_dict())
        assert_vintage({"extracted_at": s.availability_ts,
                        "player_id": s.subject_id}, line_move_ts)


def _clamp(x: float, lo: float, hi: float) -> Tuple[float, bool]:
    if x < lo:
        return lo, True
    if x > hi:
        return hi, True
    return x, False


def combine(
    signals: Sequence[GatedSignal],
    knob: str,
    subject_id: str,
    line_move_ts: str,
    gate_threshold: float = DEFAULT_GATE_THRESHOLD,
) -> Combined:
    """Fuse the signals for ONE (knob, subject) into ONE bounded, leak-free multiplier.

    Steps (deterministic; the LLM authored none of these numbers):
      1. Select signals matching `knob` AND `subject_id` (a fusion is per knob/subject).
      2. LEAK GUARD: assert EVERY selected signal is known < line_move_ts, else refuse.
      3. Combined lean = sum_i weight_i * confidence_i * lean_i  (confidence-shrunk,
         gate-weighted). Opposing FACTS net out -- conflicting evidence -> ~0 -> no-op.
      4. FIRE only if |combined lean| >= gate_threshold; else multiplier = 1.0 (no-op).
      5. multiplier = 1 + combined_lean, then HARD-CLAMP to the knob's tight band.

    Raises AssertionError (with 'LEAK') if any contributing signal is hindsight, or
    KeyError/AssertionError on an unknown knob. Returns a Combined; fired=False is the
    honest default when evidence is weak/conflicting.
    """
    assert knob in KNOB_BANDS, f"unknown knob {knob}"
    sel = [s for s in signals if s.knob == knob and s.subject_id == subject_id]

    if not sel:
        return Combined(knob=knob, subject_id=subject_id, multiplier=1.0, fired=False,
                        combined_lean=0.0, n_signals=0, contributors=tuple(), clamped=False)

    # LEAK GUARD across ALL contributors -- one hindsight row refuses the whole fusion.
    assert_all_leak_free(sel, line_move_ts)

    combined_lean = 0.0
    for s in sel:
        combined_lean += float(s.weight) * float(s.confidence) * float(s.lean)

    fired = abs(combined_lean) >= float(gate_threshold)
    if not fired:
        return Combined(knob=knob, subject_id=subject_id, multiplier=1.0, fired=False,
                        combined_lean=combined_lean, n_signals=len(sel),
                        contributors=tuple(s.signal for s in sel), clamped=False)

    lo, hi = KNOB_BANDS[knob]
    raw = 1.0 + combined_lean
    mult, clamped = _clamp(raw, lo, hi)
    return Combined(knob=knob, subject_id=subject_id, multiplier=mult, fired=True,
                    combined_lean=combined_lean, n_signals=len(sel),
                    contributors=tuple(s.signal for s in sel), clamped=clamped)


def combine_all(
    signals: Sequence[GatedSignal],
    line_move_ts: str,
    gate_threshold: float = DEFAULT_GATE_THRESHOLD,
) -> List[Combined]:
    """Fuse EVERY distinct (knob, subject) group present in `signals`.

    Convenience over `combine`: groups the shipped signals and emits one bounded
    multiplier per (knob, subject). A group whose fusion does not clear the threshold
    still returns a fired=False / 1.0 no-op row (recorded, honest default). Order is
    deterministic (sorted by knob then subject) for reproducible scoreboards.
    """
    groups: Dict[Tuple[str, str], List[GatedSignal]] = {}
    for s in signals:
        groups.setdefault((s.knob, s.subject_id), []).append(s)
    out: List[Combined] = []
    for knob, subject in sorted(groups):
        out.append(combine(signals, knob, subject, line_move_ts, gate_threshold))
    return out
