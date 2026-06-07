"""Signal contract for ARM-A (predictive features).

A *signal* is a leak-safe predictive feature with a hypothesis, a target stat,
and a scope (pregame / live / both). It is built against an :class:`AsOfContext`
that pins the decision timestamp, so ``build`` may ONLY read information that was
knowable at ``ctx.decision_time`` (the leak-safety contract enforced by the gate).

Signals READ the point-in-time store (``src.loop.store``) so they can consume
intelligence atlas sections as features (atlas x opponent-scheme = interaction
feature). When a signal SHIPs, ``src.loop.wiring`` writes its learned per-entity
values BACK into the store as a new atlas field (the reinforcement loop).

This module defines the shared types ALL ``signals/*.py`` modules and the gate /
orchestrator / ledger import. Concrete signals subclass :class:`Signal`.
"""
from __future__ import annotations

import abc
import datetime as _dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

# A signal's per-decision output: a scalar feature value, or a dict of named
# feature values (e.g. an interval signal emitting {"sigma_mult": ..., ...}).
SignalValue = Union[float, Dict[str, float], None]

# Allowed target families. A signal declares which model surface it feeds.
TARGETS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov",
           "minutes", "total", "winprob", "usage", "sigma")

# Allowed scopes: when the signal can be evaluated.
SCOPES = ("pregame", "live", "both")


class Verdict(str, Enum):
    """Honest-gate verdict for a tested signal (or atlas-derived signal).

    SHIP          -- passed all 5 gate criteria; wire into the model + write
                     learned values back as an atlas field.
    VARIANCE_ONLY -- improves interval/uncertainty (CI width, Kelly) but NOT the
                     point estimate; wire into the sigma/interval path only.
    REJECT        -- failed (null-control, ablation, calibration, or CLV).
    DEFER         -- could not be evaluated yet (missing data / coverage); requeue.
    """

    SHIP = "SHIP"
    VARIANCE_ONLY = "VARIANCE_ONLY"
    REJECT = "REJECT"
    DEFER = "DEFER"


@dataclass
class AsOfContext:
    """Pins the decision timestamp + entity identifiers for a leak-safe build.

    Everything a signal reads MUST be filtered to ``<= decision_time``. The store
    enforces this on reads; signals must not call ``datetime.utcnow()`` or read
    any live/today-only artifact at train time.

    Attributes:
        decision_time: the as-of timestamp; no info after this may be used.
        player_id:     subject player (None for team/total/winprob targets).
        team:          subject team tricode (e.g. "DAL").
        opp:           opponent team tricode.
        game_id:       NBA game id, when known.
        game_date:     ISO date of the game (the temporal-split key).
        season:        season string (e.g. "2025-26").
        is_home:       whether the subject team is home.
        scope:         "pregame" | "live" | "both".
        snapshot:      live snapshot label ("endQ1".."endQ3") for live scope.
        live:          the live box snapshot dict (src.data.live schema) if live.
        extra:         free-form additional context (lines, lineup, etc.).
    """

    decision_time: _dt.datetime
    player_id: Optional[int] = None
    team: Optional[str] = None
    opp: Optional[str] = None
    game_id: Optional[str] = None
    game_date: Optional[str] = None
    season: Optional[str] = None
    is_home: Optional[bool] = None
    scope: str = "pregame"
    snapshot: Optional[str] = None
    live: Optional[Dict[str, Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_of_iso(self) -> str:
        """Return the decision date as an ISO ``YYYY-MM-DD`` string."""
        return self.decision_time.date().isoformat()


@dataclass
class Hypothesis:
    """A testable basketball hypothesis emitted by the error-miner or a signal.

    Attributes:
        name:        unique signal slug (matches ``signals/<name>.py``).
        target:      one of :data:`TARGETS`.
        scope:       one of :data:`SCOPES`.
        statement:   human-readable basketball claim.
        rationale:   why we expect an edge (which residual bucket / atlas field).
        source:      "seed" | "error_miner" | "intel_scanner".
        atlas_fields: atlas sections this signal reads (for the reinforcement map).
        expected_verdict: optional prior expectation for triage.
        priority:    P0..P3 (lower = sooner).
    """

    name: str
    target: str
    scope: str
    statement: str
    rationale: str = ""
    source: str = "seed"
    atlas_fields: List[str] = field(default_factory=list)
    expected_verdict: Optional[str] = None
    priority: str = "P2"


@dataclass
class GateResult:
    """Outcome of running a signal through the 5-criterion honest gate.

    Attributes:
        signal_name:    slug of the tested signal.
        verdict:        the :class:`Verdict`.
        reason:         short human-readable justification.
        wf_folds:       per-fold delta_mae (ALL must be < 0 to SHIP a point signal).
        wf_all_improve: True iff every walk-forward fold improved.
        null_delta:     mean delta vs null-shuffle control (must clear the real signal).
        null_pass:      True iff the real delta beats the null distribution.
        ablation_delta: delta when added to the FULL model (never tested in isolation).
        ablation_pass:  True iff the ablation delta is meaningful.
        calibration_ok: reliability/calibration check passed.
        clv:            closing-line value vs the sharpest line (Pinnacle), pp.
        clv_pass:       True iff CLV is positive / acceptable.
        p_value:        raw p-value for the FDR / Benjamini-Hochberg bookkeeping.
        fdr_pass:       True iff it survives the multiple-comparisons correction.
        metrics:        any extra numeric diagnostics.
    """

    signal_name: str
    verdict: Verdict
    reason: str = ""
    wf_folds: List[float] = field(default_factory=list)
    wf_all_improve: bool = False
    null_delta: Optional[float] = None
    null_pass: bool = False
    ablation_delta: Optional[float] = None
    ablation_pass: bool = False
    calibration_ok: bool = False
    clv: Optional[float] = None
    clv_pass: bool = False
    p_value: Optional[float] = None
    fdr_pass: bool = False
    metrics: Dict[str, Any] = field(default_factory=dict)


class Signal(abc.ABC):
    """Base class for a predictive signal (ARM-A).

    Subclasses (``signals/<name>.py``) set the class attributes ``name``,
    ``target``, ``scope`` and implement :meth:`build` (leak-safe) and
    :meth:`hypothesis`. The orchestrator builds a feature column over the
    training matrix by calling :meth:`build` once per row's :class:`AsOfContext`.

    Class attributes:
        name:   unique slug (== module filename, == feature column name).
        target: one of :data:`TARGETS`.
        scope:  one of :data:`SCOPES`.
        reads_atlas: atlas section keys this signal consumes from the store.
        emits:  for dict-valued signals, the names of the emitted sub-features.
    """

    name: str = "base_signal"
    target: str = "pts"
    scope: str = "pregame"
    reads_atlas: List[str] = []
    emits: List[str] = []

    def __init__(self, store: Optional[Any] = None) -> None:
        """Bind an optional :class:`~src.loop.store.PointInTimeStore` for reads."""
        self.store = store

    @abc.abstractmethod
    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute the leak-safe feature value(s) for one decision.

        MUST only read information available at ``ctx.decision_time`` (read the
        store with ``as_of=ctx.decision_time`` and parquets filtered to the same
        bound). Return a float, a dict of named sub-features, or ``None`` if the
        signal cannot be computed for this row (neutral / missing).
        """
        raise NotImplementedError

    @abc.abstractmethod
    def hypothesis(self) -> Hypothesis:
        """Return the :class:`Hypothesis` this signal tests."""
        raise NotImplementedError

    # ----- shared convenience helpers (concrete; subclasses may use) ----------
    def feature_names(self) -> List[str]:
        """Feature column name(s) this signal contributes to the model matrix.

        Scalar signals contribute ``[self.name]``; dict signals contribute
        ``[f"{self.name}__{k}" for k in self.emits]``.
        """
        if self.emits:
            return [f"{self.name}__{k}" for k in self.emits]
        return [self.name]

    def read_atlas(self, entity: str, section: str, as_of: _dt.datetime,
                   default: Optional[dict] = None) -> Optional[dict]:
        """Leak-safe convenience read of an atlas section from the bound store."""
        if self.store is None:
            return default
        val = self.store.read(entity, section, as_of)
        return val if val is not None else default

    def validate_output(self, value: SignalValue) -> bool:
        """Cheap sanity check used by tests + the gate's value-sanity assertion."""
        if value is None:
            return True
        if isinstance(value, dict):
            return all(isinstance(v, (int, float)) for v in value.values())
        return isinstance(value, (int, float))
