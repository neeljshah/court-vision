"""scripts.platformkit.quant.clv_core -- the ONE sign-audited CLV yardstick.

INFRASTRUCTURE ONLY. This module makes NO predictive claim and computes NO new
CLV math: it re-exports the TWO already-verified CLV compute paths and wraps them
in a sign-agreement + vintage audit so every consumer (the self-improving loop
AND the Execution API) reads the SAME yardstick through ONE door.

Why a single door:
  CLV is the honest "did I lock a better number than the close?" yardstick -- and a
  do-no-harm / second-corpus guard. It is NEVER a SHIP objective (the ship objective
  stays held-out OUTCOME Brier/BSS; CLV vs_close defaults UNPROVEN). This file does
  not upgrade anything to vs_close and does not self-stamp any flag.

The two VERIFIED paths (imported VERBATIM, never reimplemented):
  1. pct path  -- scripts.platformkit.clv_ledger.compute_clv
                  -> clv_pct in PERCENT space; positive = better-than-close.
  2. prob path -- scripts.platformkit.forward_capture.clv.compute_clv
                  -> CLVResult.clv = calibrated_prob - devig_close_prob in
                     PROBABILITY space; positive = better-than-close.

Both paths share the SAME sign convention (positive = you got a better number than
the close). This module's audit ENFORCES that they agree in sign on a bet, raising
on any silent divergence rather than averaging a contradiction.

Honesty invariants enforced here:
  * positive = better-than-close (reuses the verified compute_clv functions VERBATIM;
    never re-endorses the documented-backwards record_clv).
  * assert_vintage(pred_ts < close_captured_at): a hindsight bet (stamped at/after
    the close it is graded against) RAISES -- never silently graded.
  * true-close and proxy-close are NEVER merged into one headline. is_true_close is
    carried separately; a proxy result is flagged proxy=True.
  * NO $/roi/pnl/bankroll/stake field anywhere -- units/probability only.

Build invariants: additive; <=300 LOC; ASCII only; reuse, never reimplement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

# --- the two VERIFIED CLV compute paths, imported VERBATIM (no reimplementation) ----------
from scripts.platformkit.clv_ledger import compute_clv as compute_clv_pct
from scripts.platformkit.forward_capture.clv import (  # noqa: E402
    compute_clv as compute_clv_prob,
)

# --- the verified vintage leak guard, imported VERBATIM ------------------------------------
from scripts.platformkit.freshness.as_of_reader import (  # noqa: E402
    assert_vintage as _assert_vintage_raw,
)

__all__ = [
    "compute_clv_pct",
    "compute_clv_prob",
    "assert_vintage",
    "clv_sign",
    "ClvAudit",
    "audit_clv",
]


def clv_sign(value: Optional[float]) -> int:
    """Sign of a CLV value under the ONE convention: positive = better-than-close.

    Returns +1 (beat the close), -1 (worse than the close), or 0 (exactly flat /
    None). Both verified paths emit the SAME convention, so this single helper is
    valid for either clv_pct (percent) or clv (probability) space.
    """
    if value is None:
        return 0
    v = float(value)
    if v > 0.0:
        return 1
    if v < 0.0:
        return -1
    return 0


def assert_vintage(pred_ts: str, close_captured_at: str,
                   *, pred_id: Optional[str] = None) -> None:
    """Hindsight guard: RAISE unless pred_ts is STRICTLY before close_captured_at.

    Excludes hindsight from the yardstick: a prediction stamped at/after the close it
    is being graded against must never count. Reuses the verified
    freshness.as_of_reader.assert_vintage VERBATIM by framing the prediction as the
    "evidence" {extracted_at: pred_ts} that must predate asof=close_captured_at; that
    primitive raises AssertionError('LEAK...') exactly when pred_ts >= close_captured_at.

    Raises AssertionError on a hindsight (or equal-timestamp) bet; returns None when
    the vintage is clean (pred_ts < close_captured_at).
    """
    _assert_vintage_raw(
        {"extracted_at": str(pred_ts), "player_id": pred_id},
        str(close_captured_at),
    )


@dataclass(frozen=True)
class ClvAudit:
    """One sign-audited CLV reading. NO $/roi/stake field -- units/probability only.

    clv_pct  -- percent-space CLV from the verified clv_ledger path (or None).
    clv_prob -- probability-space CLV from the verified forward_capture path (or None).
    sign     -- the agreed sign (+1/-1/0); both paths' signs match by construction.
    is_true_close -- whether the close was a REAL captured close (True) vs a proxy
                     (False). Carried SEPARATELY; true and proxy are never merged.
    proxy    -- convenience inverse of is_true_close; a proxy reading is flagged.
    """
    clv_pct: Optional[float]
    clv_prob: Optional[float]
    sign: int
    is_true_close: bool
    proxy: bool

    def as_record(self) -> Dict[str, Any]:
        return {
            "clv_pct": self.clv_pct,
            "clv_prob": self.clv_prob,
            "sign": self.sign,
            "is_true_close": self.is_true_close,
            "proxy": self.proxy,
            "units": "probability",  # explicit: never dollars
        }


def _sign_agrees(a: int, b: int) -> bool:
    """Two signs agree unless they are strictly opposite (+1 vs -1)."""
    return not ((a > 0 and b < 0) or (a < 0 and b > 0))


def audit_clv(
    *,
    side: str,
    taken_decimal: float,
    closing_decimal_home: float,
    closing_decimal_away: float,
    pred_ts: str,
    close_captured_at: str,
    calibrated_prob: float,
    is_true_close: bool,
    pred_id: Optional[str] = None,
) -> ClvAudit:
    """Compute CLV through BOTH verified paths for one bet and AUDIT their sign.

    Steps (all read-only, no I/O):
      1. assert_vintage(pred_ts < close_captured_at) -- RAISE on a hindsight bet.
      2. pct path: clv_ledger.compute_clv -> clv_pct (percent space).
      3. prob path: forward_capture.clv.compute_clv -> clv (probability space),
         using the SAME devigged close (home leg) so the two are comparable. The
         prob path's own vintage guard would EXCLUDE (return None) on hindsight, but
         step 1 already raised, so a clean call yields a result.
      4. ASSERT the two signs agree; RAISE on any strictly-opposite divergence.
      5. Return a ClvAudit carrying both values, the agreed sign, and is_true_close
         kept SEPARATE (proxy flagged) -- true and proxy are never merged.

    Raises AssertionError on a hindsight bet (step 1) or a sign mismatch (step 4).
    NO $/roi field is produced or accepted.
    """
    # 1) hindsight guard -- raises on pred_ts >= close_captured_at
    assert_vintage(pred_ts, close_captured_at, pred_id=pred_id)

    # 2) percent-space CLV via the verified clv_ledger path
    pct = compute_clv_pct(
        side, taken_decimal, closing_decimal_home, closing_decimal_away,
    )
    clv_pct = float(pct["clv_pct"])

    # 3) probability-space CLV via the verified forward_capture path. We hand it the
    #    SAME captured close (devigged home leg) and the calibrated prob; the home
    #    side is the reference leg both paths price against.
    move = {
        "close_captured_at": str(close_captured_at),
        "close_home_price": float(closing_decimal_home),
        "close_away_price": float(closing_decimal_away),
    }
    pred_row = {
        "pred_ts": str(pred_ts),
        "calibrated_prob": float(calibrated_prob),
        "pred_id": pred_id,
    }
    prob_res = compute_clv_prob(pred_row, move)
    clv_prob = None if prob_res is None else float(prob_res.clv)

    # 4) sign agreement audit -- the two paths must not silently contradict
    s_pct = clv_sign(clv_pct)
    s_prob = clv_sign(clv_prob)
    if not _sign_agrees(s_pct, s_prob):
        raise AssertionError(
            "CLV SIGN MISMATCH: pct path sign %+d (clv_pct=%r) disagrees with "
            "prob path sign %+d (clv_prob=%r); refusing to merge a contradiction"
            % (s_pct, clv_pct, s_prob, clv_prob)
        )

    # agreed sign: prefer the non-zero, non-None signal; both agree by the check above
    agreed = s_pct if s_pct != 0 else s_prob
    return ClvAudit(
        clv_pct=clv_pct,
        clv_prob=clv_prob,
        sign=agreed,
        is_true_close=bool(is_true_close),
        proxy=not bool(is_true_close),
    )
