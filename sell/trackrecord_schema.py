"""sell.trackrecord_schema -- the TrackRecord dataclass (CLV + calibration only).

The sellable artifact for a sophisticated quant buyer. It presents the HONEST
yardsticks: closing-line value (did we lock a better number than the close?),
out-of-sample calibration (Brier / ECE when available), and the settled-bet
counts that back them -- split by true vs proxy close and by sport.

HONESTY (binding, enforced by shape AND by tests):
  * There is NO dollar / ROI / P&L field anywhere on this record, BY DESIGN. The
    product is a calibrated predictor with a CLV-tracked paper trail, not a profit
    claim (predict_service.contracts carries no $edge field for the same reason).
  * edge_claimed is a hard constant False on every record.
  * Every number is REAL (computed by the vetted CLV ledger / scoreboard) or
    explicitly None / "unavailable" -- never fabricated.

INVARIANTS: build only under sell/; <=300 LOC; ASCII only; no secrets; no
$-edge / ROI / P&L field; dataclasses (stdlib) matching repo convention.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Optional

#: Bumped whenever a field is added/removed/renamed below. Stamped on the record
#: so a reader can detect (and reject) an incompatible shape.
TRACKRECORD_SCHEMA_VERSION = "1.0.0"

#: Repeated everywhere the record is surfaced: this is calibration + CLV, not $.
DEFAULT_METHODOLOGY_NOTE = (
    "Calibrated predictor with a CLV-tracked paper trail. The sellable claim is "
    "out-of-sample calibration (Brier / ECE) and closing-line-value discipline "
    "under a leak-free, walk-forward, reproducible methodology -- NOT a dollar "
    "ROI or edge. A positive mean_clv_pct means bets were recorded at a better "
    "number than the close on average. CLV is computed by the vetted clv_ledger "
    "and never recomputed here. No dollar P&L is asserted anywhere on this record."
)

#: The product makes no dollar-edge claims. Hard constant on every record.
EDGE_CLAIMED: bool = False


def _filter_known(cls: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only keys that are declared fields of *cls* (forward-compat reads)."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in (data or {}).items() if k in names}


@dataclass
class TrackRecord:
    """The signed-able CLV + calibration track record. NO $ / ROI / P&L field.

    Fields
    ------
    generated_at : ISO-8601 UTC timestamp the record was built.
    window : human label for the reporting window (e.g. "all-time" / a date span).
    n_settled : count of settled bets carrying a CLV value (the CLV sample size).
    mean_clv_pct : mean CLV % over settled bets (>0 = beat the close). None if empty.
    pct_beat_close : % of settled bets with clv_pct > 0. None if empty.
    n_true_close : settled bets graded against a TRUE (non-proxy) close.
    n_proxy_close : settled bets graded against a PROXY (last-seen) close.
    by_sport : per-sport breakdown {sport_id: {n, mean_clv_pct, pct_beat_close,
               n_true_close, n_proxy_close}}.
    calibration : {brier, ece} OOS calibration when available; values None /
                  "unavailable" when not measured (never fabricated).
    methodology_note : the binding honesty framing (default DEFAULT_METHODOLOGY_NOTE).
    edge_claimed : hard constant False -- no dollar edge is asserted.
    schema_version : stamped shape version.
    """
    generated_at: str
    window: str = "all-time"
    n_settled: int = 0
    mean_clv_pct: Optional[float] = None
    pct_beat_close: Optional[float] = None
    n_true_close: int = 0
    n_proxy_close: int = 0
    by_sport: Dict[str, Any] = field(default_factory=dict)
    calibration: Dict[str, Any] = field(
        default_factory=lambda: {"brier": None, "ece": None,
                                 "status": "unavailable"})
    methodology_note: str = DEFAULT_METHODOLOGY_NOTE
    edge_claimed: bool = EDGE_CLAIMED
    schema_version: str = TRACKRECORD_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """Plain JSON-round-trippable dict. edge_claimed is forced False."""
        d = asdict(self)
        d["edge_claimed"] = False  # invariant: never True, regardless of input
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrackRecord":
        kw = _filter_known(cls, data or {})
        # edge_claimed is never trusted from input -- it is always False.
        kw["edge_claimed"] = False
        return cls(**kw)


__all__ = [
    "TRACKRECORD_SCHEMA_VERSION",
    "DEFAULT_METHODOLOGY_NOTE",
    "EDGE_CLAIMED",
    "TrackRecord",
]
