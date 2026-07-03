"""sell.track_record -- build + sign the CLV / calibration track record.

build_track_record() assembles a :class:`TrackRecord` from the vetted paper
trail: it REUSES scripts.platformkit.pm_trading.scoreboard.build_scoreboard
(which already aggregates the CLV ledger -- n_settled, mean_clv_pct,
pct_beat_close, true vs proxy, by_sport) and NEVER recomputes CLV here. An
optional pre-built scoreboard dict and/or ledger rows may be injected for
deterministic / test use.

sign_track_record() canonicalises the record and attaches an HMAC-SHA256
signature (sell.signing). Before returning, the signed dict is run through
governance.honesty_linter.lint_obj and a violation raises -- the artifact can
only ship if it is honest (no $-edge key, no retracted live number).

HONESTY: no dollar / ROI / P&L field is ever added. Calibration (Brier / ECE)
is surfaced ONLY when a real measurement is supplied; otherwise it is marked
"unavailable" -- never fabricated. edge_claimed is always False.

INVARIANTS: build only under sell/; <=300 LOC; ASCII only; no secrets; no
$-edge field; reuse the scoreboard / clv_ledger, do not recompute CLV.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from governance import honesty_linter as _linter
from scripts.platformkit.pm_trading import scoreboard as _scoreboard

from sell.signing import sign as _sign
from sell.trackrecord_schema import TrackRecord


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sport_view(bucket: Dict[str, Any]) -> Dict[str, Any]:
    """Project a scoreboard by_sport bucket to the track-record sport shape.

    CLV + counts only -- the flat-unit win/loss fields are intentionally dropped
    so the record carries no win/loss-as-money framing.
    """
    return {
        "n": int(bucket.get("n", 0) or 0),
        "mean_clv_pct": bucket.get("mean_clv_pct"),
        "pct_beat_close": bucket.get("pct_beat_close"),
        "n_true_close": int(bucket.get("n_true_close", 0) or 0),
        "n_proxy_close": int(bucket.get("n_proxy_close", 0) or 0),
    }


def _calibration_view(calibration: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalise an optional calibration measurement into the record shape.

    A real measurement carries numeric brier and/or ece. When nothing real is
    supplied, calibration is marked "unavailable" -- never fabricated.
    """
    if not isinstance(calibration, dict):
        return {"brier": None, "ece": None, "status": "unavailable"}
    brier = calibration.get("brier")
    ece = calibration.get("ece")
    has_real = isinstance(brier, (int, float)) or isinstance(ece, (int, float))
    out: Dict[str, Any] = {
        "brier": brier if isinstance(brier, (int, float)) else None,
        "ece": ece if isinstance(ece, (int, float)) else None,
        "status": "measured" if has_real else "unavailable",
    }
    return out


def build_track_record(
    *,
    scoreboard: Optional[Dict[str, Any]] = None,
    ledger: Optional[List[Dict[str, Any]]] = None,
    calibration: Optional[Dict[str, Any]] = None,
    window: str = "all-time",
) -> TrackRecord:
    """Build a TrackRecord from the CLV scoreboard / ledger. CLV is NOT recomputed.

    Parameters
    ----------
    scoreboard : pre-built grade_summary dict, optional. When None, it is built
        via scoreboard.build_scoreboard (which loads the canonical CLV ledger)
        -- optionally over injected *ledger* rows.
    ledger : injected CLV ledger rows, optional. Only used when *scoreboard* is
        None; passed straight to build_scoreboard(rows=...).
    calibration : optional real OOS calibration measurement {brier, ece}. When
        absent, calibration is surfaced as "unavailable" (never fabricated).
    window : human label for the reporting window.

    Returns
    -------
    TrackRecord
        CLV + calibration + counts. No dollar / ROI / P&L field.
    """
    board = scoreboard
    if board is None:
        board = _scoreboard.build_scoreboard(rows=ledger)

    by_sport_raw = board.get("by_sport", {}) or {}
    by_sport = {
        str(sp): _sport_view(bucket if isinstance(bucket, dict) else {})
        for sp, bucket in by_sport_raw.items()
    }

    return TrackRecord(
        generated_at=_now_iso(),
        window=str(window),
        n_settled=int(board.get("n_settled", 0) or 0),
        mean_clv_pct=board.get("mean_clv_pct"),
        pct_beat_close=board.get("pct_beat_close"),
        n_true_close=int(board.get("n_true_close", 0) or 0),
        n_proxy_close=int(board.get("n_proxy_close", 0) or 0),
        by_sport=by_sport,
        calibration=_calibration_view(calibration),
    )


def _lint_view(signed: Dict[str, Any]) -> Dict[str, Any]:
    """A view of the signed envelope with the opaque MAC value redacted.

    The signature ``value`` is a cryptographic hex digest -- random bytes, not a
    presented result. Its hex can incidentally contain a banned-number substring
    (e.g. "54" flanked by hex letters), which would false-positive the honesty
    linter and make signing non-deterministically fail. We lint the full record
    BODY (every claim / key, including the signature block's structural keys) but
    replace the opaque ``value`` with a constant placeholder so an opaque MAC can
    never trip the banned-number scan. Honesty is still fully enforced on content.
    """
    if not isinstance(signed, dict):
        return signed
    view = dict(signed)
    sig = view.get("signature")
    if isinstance(sig, dict):
        sig = dict(sig)
        sig["value"] = "REDACTED_OPAQUE_MAC" if sig.get("value") else None
        view["signature"] = sig
    return view


def sign_track_record(
    tr: TrackRecord, *, secret: Optional[str] = None
) -> Dict[str, Any]:
    """Sign a TrackRecord and return the honesty-linted signed envelope.

    The record is serialised (to_dict), signed via HMAC-SHA256 (sell.signing),
    then linted by governance.honesty_linter. A lint violation RAISES
    AssertionError -- a dishonest artifact must never ship. With no signing
    secret available the record is returned UNSIGNED but still linted.

    The opaque MAC hex is excluded from the lint (it is a cryptographic digest,
    not a presented result number); every other field -- and every key, including
    the signature block's structural keys -- is fully linted.

    Returns
    -------
    dict
        The signed (or explicitly unsigned) envelope, guaranteed lint-clean.
    """
    payload = tr.to_dict()
    signed = _sign(payload, secret)
    # Honesty gate: the artifact can only ship if it is clean. Raises on a
    # violation (no $-edge key, no retracted live number). The opaque MAC value
    # is redacted so a random hex digest cannot false-positive the number scan.
    _linter.assert_clean(_lint_view(signed))
    return signed


__all__ = [
    "build_track_record",
    "sign_track_record",
]
