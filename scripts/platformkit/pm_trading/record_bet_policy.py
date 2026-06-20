"""record_bet_policy.py -- stamp tier/flat_unit/quarter_kelly onto open ledger rows.

PT-1 workstream: policy fields (tier, flat_unit, quarter_kelly) are computed at
placement time in run_paper_today but historically were NOT written into the
append-only CLV ledger row itself -- they existed only in the in-memory bets[]
list.  This module adds a thin stamp layer that:

  1. Accepts an *already-open* CLV ledger row (as a dict, just returned by
     clv_ledger.record_bet).
  2. Computes tier + stake_units from pm_trading.policy (pure, no IO).
  3. Appends a ``policy_stamp`` row to the ledger (a NEW line, not a mutation)
     carrying bet_id + tier + flat_unit + quarter_kelly.
  4. Returns the stamp row for the caller to inspect / assert.

DESIGN RAILS (binding):
  * UNITS ONLY -- there is no $/dollar field on the stamp.  No ROI / PnL / edge
    claim.  CLV is computed downstream; this module only writes sizing policy.
  * Append-only: the original open row is NEVER mutated.  The stamp row is a
    second JSONL line with status="policy_stamp" so it is distinguishable from
    open/settled rows.
  * The stamp is idempotent by design: stamping the same bet_id twice produces
    two stamp rows (append-only invariant), but callers that read policy prefer
    the FIRST stamp row (chronological order).
  * Pure policy: ev / model_prob / taken_decimal must be provided by the caller;
    this module does NOT re-fetch prices or touch the network.
  * <=300 LOC; ASCII only; no secrets.

Build only under scripts/platformkit/.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# ---- imports with flat-sibling fallback for hermetic per-file tests ------------
try:
    from scripts.platformkit import clv_ledger as _clv
    from scripts.platformkit.pm_trading import policy as _policy
except ImportError:  # pragma: no cover -- hermetic test path
    import clv_ledger as _clv          # type: ignore[no-redef]
    import policy as _policy           # type: ignore[no-redef]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# stamp_policy -- the main public function
# --------------------------------------------------------------------------

def stamp_policy(
    open_row: Dict[str, Any],
    *,
    ev: float,
    model_prob: Optional[float] = None,
    taken_decimal: Optional[float] = None,
    market_prob: Optional[float] = None,
    clv_is_proxy: bool = False,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Append a policy_stamp row to the CLV ledger for *open_row*.

    Given the *open_row* (the dict returned by clv_ledger.record_bet), compute
    the policy tier and dual unit stakes, then append a new ``policy_stamp``
    line to the ledger.  The original open row is never mutated.

    Parameters
    ----------
    open_row:
        The row returned by ``clv_ledger.record_bet`` (must carry ``bet_id``
        and ``status == "open"``).
    ev:
        EV per 1-unit staked = p*decimal - 1, same definition as
        ``odds_shop.ev_vs_price``. Used to derive the tier.
    model_prob:
        Calibrated model probability for the side backed (used for quarter-
        Kelly sizing).  May be omitted if quarter_kelly is not needed.
    taken_decimal:
        Decimal price actually taken (used for quarter-Kelly sizing).  May be
        omitted; quarter_kelly will be 0.0 when missing.
    market_prob:
        Optional market implied prob (after devig); used only for sanity gate
        in policy.tier().
    clv_is_proxy:
        When the closing line that will be settled against is a proxy (not a
        true settled close) each tier floor is raised by EV_PROXY_PENALTY.
    path:
        Ledger path override (for tests; defaults to clv_ledger.DEFAULT_LEDGER).

    Returns
    -------
    dict:
        The policy_stamp row that was appended.  Fields:
          status         "policy_stamp"
          stamped_at     UTC ISO timestamp
          bet_id         matches the open_row's bet_id
          tier           "A" | "B" | "C" | None
          flat_unit      1.0 when tiered, else 0.0  (UNITS, never $)
          quarter_kelly  fractional Kelly (UNITS, never $)
          ev             the EV passed in (for auditability)
          clv_is_proxy   bool

    Raises
    ------
    ValueError:
        If *open_row* lacks a ``bet_id`` key (caller forgot record_bet) or
        its ``status`` is not ``"open"`` (guard against double-stamping settled
        rows by accident).
    """
    if "bet_id" not in open_row:
        raise ValueError(
            "open_row must carry 'bet_id' (was it created by clv_ledger.record_bet?)"
        )
    if open_row.get("status") != "open":
        raise ValueError(
            "stamp_policy expects an open row (status='open'), got %r"
            % open_row.get("status")
        )

    # Compute tier (pure, no IO).
    tier_label: Optional[str] = _policy.tier(
        ev=ev,
        model_prob=model_prob,
        market_prob=market_prob,
        clv_is_proxy=clv_is_proxy,
    )

    # Compute dual unit stakes (pure, no IO).
    stakes = _policy.stake_units(
        ev=ev,
        model_prob=model_prob,
        taken_decimal=taken_decimal,
        tier=tier_label,
        clv_is_proxy=clv_is_proxy,
    )

    stamp: Dict[str, Any] = {
        "status": "policy_stamp",
        "stamped_at": _now_iso(),
        "bet_id": open_row["bet_id"],
        "tier": tier_label,
        "flat_unit": stakes["flat_unit"],
        "quarter_kelly": stakes["quarter_kelly"],
        "ev": float(ev),
        "clv_is_proxy": bool(clv_is_proxy),
    }

    # Propagate sport/matchup/side for human readability (not relied on for key).
    for field in ("sport", "matchup", "side"):
        if field in open_row:
            stamp[field] = open_row[field]

    # Append to ledger (never mutates the open row).
    target = Path(path) if path is not None else _clv.DEFAULT_LEDGER
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        from scripts.platformkit.clv_ledger_io import append_row as _append_row
    except Exception:  # noqa: BLE001 -- lock layer is optional
        _append_row = None  # type: ignore[assignment]
    if _append_row is not None:
        try:
            _append_row(stamp, path=target)
            return stamp
        except Exception:  # noqa: BLE001 -- fall back to direct write
            pass
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(stamp, default=str) + "\n")
    return stamp


# --------------------------------------------------------------------------
# load_policy_stamps -- utility to read stamps back by bet_id
# --------------------------------------------------------------------------

def load_policy_stamps(
    bet_id_filter: Optional[str] = None,
    *,
    path: Optional[Path] = None,
) -> list:
    """Return policy_stamp rows from the ledger, newest-first.

    Parameters
    ----------
    bet_id_filter:
        When provided, return only rows whose ``bet_id`` matches exactly.
        When None, return all policy_stamp rows.
    path:
        Ledger path override.

    Returns
    -------
    list[dict]:
        All policy_stamp rows in the ledger, most-recently-written last
        (JSONL order = append order).  Returns [] when the file is absent.
    """
    rows = _clv.load_ledger(path)
    stamps = [r for r in rows if r.get("status") == "policy_stamp"]
    if bet_id_filter is not None:
        stamps = [r for r in stamps if r.get("bet_id") == bet_id_filter]
    return stamps


__all__ = [
    "stamp_policy",
    "load_policy_stamps",
]
