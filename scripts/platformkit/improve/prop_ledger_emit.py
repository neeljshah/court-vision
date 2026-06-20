"""scripts.platformkit.improve.prop_ledger_emit -- SI-04: per-prop recency recal
wired into the graded self-improve ledger.

Builds a recency-weighted Platt recal candidate per (sport, stat) pair, grades
the result with an honest Brier readout, and appends rows to the per-market
segmented ledger with market="prop:<stat>".

CONTRACT:
  - market key is always "prop:<stat>" (lowercase).
  - sentinel absent -> NO_CANDIDATE status; no recal attempted.
  - thin stat (< MIN_PROP_N clean obs) -> INSUFFICIENT_DATA.
  - no $/roi/pnl/profit key in any output row.
  - vs_close = "UNPROVEN" always (prop in-play prices unavailable).
  - status in {"SHIP", "HOLD", "REJECT", "INSUFFICIENT_DATA", "NO_CANDIDATE"}.
  - NEVER raises; any exception -> INSUFFICIENT_DATA row.

Public API:
  emit_prop_stats(sport, stats, ledger_path=None, ts=None) -> List[Dict]
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from scripts.platformkit.improve.prop_recal_recency import (
    build_prop_recency_candidate,
    load_prop_settled,
)
from scripts.platformkit.eval_gate.scoring import brier, ece

logger = logging.getLogger("prop_ledger_emit")

# Minimum clean observations to produce an honest Brier readout.
MIN_PROP_N: int = 12

CALIBRATION_NOTE: str = (
    "calibration != edge: better-calibrated probabilities do NOT imply "
    "beating the market close or a positive expected value"
)

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

_DEFAULT_LEDGER = (
    Path(__file__).resolve().parents[3]
    / "data" / "frontend" / "improve_ledger_segmented.jsonl"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _all_keys(obj: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _assert_no_banned_keys(row: Dict[str, Any]) -> None:
    for k in _all_keys(row):
        if _BANNED_KEY_RE.search(k):
            raise ValueError("Banned key %r violates no-dollar-field contract." % k)


def _base_row(market: str, ts: str) -> Dict[str, Any]:
    return {
        "ts": ts,
        "market": market,
        "vs_close": "UNPROVEN",
        "note": CALIBRATION_NOTE,
    }


def _insufficient_row(
    market: str, ts: str, reason: str, n: int = 0
) -> Dict[str, Any]:
    row = {
        **_base_row(market, ts),
        "status": "INSUFFICIENT_DATA",
        "n": n,
        "min_n": MIN_PROP_N,
        "reason": reason,
    }
    _assert_no_banned_keys(row)
    return row


def _no_candidate_row(market: str, ts: str, reason: str) -> Dict[str, Any]:
    row = {
        **_base_row(market, ts),
        "status": "NO_CANDIDATE",
        "reason": reason,
    }
    _assert_no_banned_keys(row)
    return row


def _brier_readout(
    base_preds: List[float], cand_preds: List[float], y: List[float]
) -> Dict[str, Any]:
    """Honest Brier readout comparing base vs candidate. NEVER raises."""
    try:
        bp = np.clip(np.asarray(base_preds, dtype=float), 1e-6, 1.0 - 1e-6)
        cp = np.clip(np.asarray(cand_preds, dtype=float), 1e-6, 1.0 - 1e-6)
        yy = np.asarray(y, dtype=float)
        base_b = float(brier(bp, yy))
        cand_b = float(brier(cp, yy))
        delta = base_b - cand_b  # positive = candidate better
        return {
            "n": int(len(yy)),
            "base_brier": round(base_b, 6),
            "cand_brier": round(cand_b, 6),
            "brier_delta": round(delta, 6),
            "cand_ece": round(float(ece(cp, yy)), 6),
            "brier_improves": bool(delta > 0.0),
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("_brier_readout failed: %s", exc)
        return {"n": 0, "error": "readout_failed"}


def _grade_prop_stat(
    sport: str, stat: str, ts: str
) -> Dict[str, Any]:
    """Grade one (sport, stat) pair. NEVER raises; returns a complete ledger row."""
    market = "prop:%s" % str(stat).lower()

    # Check settled obs count up-front so we can give an honest thin-stat message.
    try:
        settled = load_prop_settled(sport, stat)
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_ledger_emit(%s/%s): load_prop_settled failed: %s", sport, stat, exc)
        settled = []

    if len(settled) < MIN_PROP_N:
        return _insufficient_row(
            market, ts,
            "only %d settled rows for stat '%s' (need >= %d); thin stat" % (
                len(settled), stat, MIN_PROP_N
            ),
            n=len(settled),
        )

    # Build the recency-weighted candidate (MF1 kill-switch inside).
    try:
        cand_name = "prop_recency_%s_%s" % (str(sport).lower(), str(stat).lower())
        cand = build_prop_recency_candidate(cand_name, sport, stat=stat)
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_ledger_emit(%s/%s): build failed: %s", sport, stat, exc)
        cand = None

    if cand is None:
        return _no_candidate_row(
            market, ts,
            "NO_CANDIDATE for stat '%s' (sentinel absent, under-N, degenerate, or feed degraded)" % stat,
        )

    y = cand.get("y", [])
    if len(y) < MIN_PROP_N:
        return _insufficient_row(
            market, ts,
            "candidate for stat '%s' has only %d clean obs (need >= %d)" % (
                stat, len(y), MIN_PROP_N
            ),
            n=len(y),
        )

    readout = _brier_readout(
        list(cand.get("base_preds", [])),
        list(cand.get("cand_preds", [])),
        list(y),
    )

    # SHIP/HOLD/REJECT: no regression rule.
    improves = readout.get("brier_improves", False)
    brier_delta = readout.get("brier_delta", 0.0)
    if not isinstance(brier_delta, float):
        brier_delta = 0.0
    if improves and brier_delta > 0.0:
        status = "SHIP"
    else:
        status = "HOLD"

    payload = cand.get("payload", {})
    row = {
        **_base_row(market, ts),
        "status": status,
        "sport": str(sport).lower(),
        "stat": str(stat).lower(),
        "n_clean": cand.get("n_clean", len(y)),
        "n_quarantined": cand.get("n_quarantined", 0),
        "readout": readout,
        "platt_a": payload.get("a"),
        "platt_b": payload.get("b"),
        "half_life_days": payload.get("half_life_days"),
        "oos_improves": bool(cand.get("oos_improves", False)),
    }
    _assert_no_banned_keys(row)
    return row


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def emit_prop_stats(
    sport: str,
    stats: Sequence[str],
    ledger_path: Optional[Path] = None,
    ts: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Grade per-prop recency recal for each stat and append rows to the ledger.

    Parameters
    ----------
    sport: Sport key (e.g. "nba").
    stats: Sequence of stat names (e.g. ["pts", "reb", "ast"]).
    ledger_path: Override ledger path (tests supply tmp_path).
    ts: ISO timestamp override (default: now UTC).

    Returns one ledger row per stat with market="prop:<stat>". NEVER raises.
    - Sentinel absent -> NO_CANDIDATE.
    - Thin stat -> INSUFFICIENT_DATA.
    - No $/roi/pnl/profit key.
    - flag stays OFF (no flag flipped here).
    """
    ts = ts or _now_iso()
    lpath = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER
    rows: List[Dict[str, Any]] = []

    for stat in stats:
        try:
            row = _grade_prop_stat(sport, str(stat), ts)
        except Exception as exc:  # noqa: BLE001
            logger.debug("prop_ledger_emit: _grade_prop_stat(%s/%s) raised: %s", sport, stat, exc)
            market = "prop:%s" % str(stat).lower()
            row = _insufficient_row(market, ts, "internal error: %s" % exc)
        rows.append(row)

    if rows:
        try:
            lpath.parent.mkdir(parents=True, exist_ok=True)
            with lpath.open("a", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning("prop_ledger_emit: ledger write failed: %s", exc)

    return rows


__all__ = [
    "emit_prop_stats",
    "MIN_PROP_N",
    "CALIBRATION_NOTE",
]
