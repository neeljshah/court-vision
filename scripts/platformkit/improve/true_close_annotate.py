"""scripts.platformkit.improve.true_close_annotate -- additive true-close annotator.

The settled-CLV second corpus (clv_corpus.build_close_corpus) is PERMANENTLY
REPLICATION_PENDING because settled rows never carry is_true_close / p_close:
settled_ingest stamps 'vs_close UNPROVEN' but does not resolve the closing odds
snapshot. This module fills that gap with a PURE, READ-ONLY annotator.

WHAT IT DOES
  annotate_row(row, snapshot_fn) -> dict
    Tags ONE settled game-row with two new fields:
      is_true_close : True ONLY when a genuine closing snapshot exists for the
                      game (captured within the lock window near tipoff, kind="close").
                      Never True for an L5/pregame proxy or a "last-seen" fallback.
      p_close       : float | None  -- Shin-devigged home probability from the
                      closing snapshot.  None when is_true_close is False (honest
                      default; no fabrication).

  annotate_batch(rows, snapshot_fn) -> list[dict]
    Applies annotate_row to a list of rows; only rows with a genuine close flip
    is_true_close=True.  Rows that already carry is_true_close=True are skipped
    (idempotent -- a row previously annotated is unchanged).

WHAT IT DOES NOT DO
  * Never edits settled_ingest.py or clv_corpus.py.
  * Never makes a network call (snapshot_fn is injected; tests use stubs).
  * Never fabricates a p_close from an L5/pregame proxy or a "last-seen" fallback.
  * Never claims an edge; calibration only.
  * No $/roi/pnl/profit/edge key anywhere.

HONESTY INVARIANTS
  is_true_close=False is the safe default: if snapshot_fn returns None, or the
  snapshot is a proxy (is_true_close=False from line_store.get_close), or devigging
  fails for any reason, is_true_close stays False and p_close stays None.
  Any exception inside annotate_row is caught; the row is returned unchanged.

SETTLED ROW SCHEMA (read-only, from clv_corpus._extract semantics):
  game_id       : str  -- game identifier (used to key the snapshot lookup)
  p_raw         : float -- model pre-existing probability (base, not modified here)
  y / outcome   : float -- observed result (not modified here)
  p_close       : float | None -- FILLED by this module when is_true_close=True
  is_true_close : bool -- FILLED by this module

KEYLESS ODDS SNAPSHOT SHAPE (from line_store.get_close):
  Returns (quotes_by_market_side, is_true_close) or None.
  quotes_by_market_side: {(market_type, side): {odds: float, ...}}
  is_true_close: True iff every returned quote was captured in the lock window.

Build invariants: additive (does NOT edit settled_ingest / clv_corpus); stdlib +
repo-internal only; no network; ASCII; <=300 LOC; never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/improve/test_true_close_annotate.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("true_close_annotate")

# ---------------------------------------------------------------------------
# Snapshot-function type alias (injectable; no network in tests)
# ---------------------------------------------------------------------------
# Callable(game_id: str) -> Optional[Tuple[Dict[Tuple[str,str], Dict], bool]]
# Matches the signature of line_store.get_close(game_key) (minus optional kwargs).
SnapshotFn = Callable[[str], Optional[Tuple[Dict, bool]]]

# Market type + side keys used to locate the closing home probability from quotes.
# line_store.get_close returns keys as (market_type, side) tuples.
_ML = "moneyline"
_HOME = "home"
_AWAY = "away"

# Minimum acceptable decimal odds (must be > 1.0 to devig meaningfully).
_MIN_DECIMAL_ODDS = 1.001

# Sentinel: the annotator never modifies these -- they are read-only schema fields.
_READ_ONLY_FIELDS = frozenset({"p_raw", "y", "outcome", "game_id", "sport"})


def _devig_home(quotes: Dict[Tuple[str, str], Dict[str, Any]]) -> Optional[float]:
    """Extract Shin-devigged home probability from a moneyline snapshot. Never raises.

    Looks for (moneyline, home) and (moneyline, away) decimal odds. Returns the
    Shin-devigged home probability, or None when either side is missing / invalid.
    Uses the vetted devig_twoway (Shin solver) VERBATIM; never reimplements devigging.
    """
    home_row = quotes.get((_ML, _HOME))
    away_row = quotes.get((_ML, _AWAY))
    if home_row is None or away_row is None:
        return None
    try:
        h_odds = float(home_row.get("odds", 0.0) or 0.0)
        a_odds = float(away_row.get("odds", 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    if h_odds <= _MIN_DECIMAL_ODDS or a_odds <= _MIN_DECIMAL_ODDS:
        return None
    try:
        from scripts.platformkit.odds_shop import devig_twoway
        home_p, _away_p = devig_twoway(h_odds, a_odds)
        if not (0.0 < home_p < 1.0):
            return None
        return float(home_p)
    except Exception as exc:  # noqa: BLE001 -- purity: devig failure -> None
        logger.debug("_devig_home: devig_twoway raised -> None: %s", exc)
        return None


def _game_id_for_row(row: Dict[str, Any]) -> Optional[str]:
    """Extract the game_id string used to key the snapshot lookup. Never raises."""
    gid = row.get("game_id") or row.get("id") or row.get("event_id")
    if not gid:
        return None
    return str(gid).strip() or None


def annotate_row(
    row: Dict[str, Any],
    snapshot_fn: Optional[SnapshotFn] = None,
) -> Dict[str, Any]:
    """Tag ONE settled row with is_true_close and p_close. NEVER raises.

    Parameters
    ----------
    row:
        A settled game dict (from settled_ingest clean_games). Read-only fields
        (p_raw, y, outcome, game_id, sport) are never modified.
    snapshot_fn:
        Callable(game_id: str) -> Optional[Tuple[quotes, is_true_close]].
        Matches the line_store.get_close interface. Injected so tests never hit
        the network. When None, falls back to the real line_store.get_close.

    Returns
    -------
    dict
        A SHALLOW COPY of row with is_true_close and p_close added.
        is_true_close defaults to False (REPLICATION_PENDING stays) for any:
          - missing game_id
          - None from snapshot_fn (no history / no odds)
          - proxy-only snapshot (is_true_close=False from line_store)
          - devigging failure
        p_close is None whenever is_true_close is False (never fabricated).

    Idempotent: if the row already carries is_true_close=True, it is returned
    unchanged to avoid re-annotating a row that was already resolved.
    """
    out = dict(row)  # shallow copy -- never mutate the caller's dict
    try:
        # Idempotency: skip if already genuinely annotated.
        if row.get("is_true_close") is True:
            return out

        # Default: honest REPLICATION_PENDING posture.
        out["is_true_close"] = False
        out["p_close"] = None

        gid = _game_id_for_row(row)
        if not gid:
            return out  # no key -> cannot resolve -> False stays

        # Resolve snapshot_fn: inject the real line_store getter when absent.
        fn = snapshot_fn
        if fn is None:
            try:
                from scripts.platformkit.odds_provider.line_store import get_close as _gc
                fn = _gc
            except Exception as exc:  # noqa: BLE001
                logger.debug("annotate_row: line_store unavailable -> False: %s", exc)
                return out

        # Fetch the closing snapshot (no network; fn is injected in tests).
        try:
            result = fn(gid)
        except Exception as exc:  # noqa: BLE001 -- snapshot fetch failure -> False
            logger.debug("annotate_row: snapshot_fn(%r) raised -> False: %s", gid, exc)
            return out

        if result is None:
            return out  # no history -> False stays

        quotes, snapshot_is_true = result

        # P3 guard: a proxy snapshot (is_true_close=False from line_store) must
        # NEVER be treated as a genuine close -- is_true_close stays False.
        if not snapshot_is_true:
            logger.debug(
                "annotate_row(%s): snapshot is a proxy -> is_true_close=False "
                "(REPLICATION_PENDING stays)", gid)
            return out

        # Genuine close confirmed: devig the home moneyline probability.
        if not isinstance(quotes, dict):
            return out

        p_close = _devig_home(quotes)
        if p_close is None:
            # Devigging failed (missing moneyline, bad odds, etc.) -- the close
            # snapshot exists but we cannot extract p_close. Keep is_true_close=False
            # to avoid a half-annotated row that looks genuine but has no probability.
            logger.debug(
                "annotate_row(%s): genuine snapshot but devig failed -> "
                "is_true_close=False (no half-annotated rows)", gid)
            return out

        # Full genuine annotation: snapshot is a true close AND devig succeeded.
        out["is_true_close"] = True
        out["p_close"] = p_close
        out["vs_close"] = "UNPROVEN"   # calibration gate decides; annotator never claims a win
        out["note"] = "calibration, not edge; true close annotated; no $ / roi / pnl"

    except Exception as exc:  # noqa: BLE001 -- purity: any failure -> unchanged row
        logger.debug("annotate_row: unexpected error -> returning row unchanged: %s", exc)
        out = dict(row)
        out.setdefault("is_true_close", False)
        out.setdefault("p_close", None)

    return out


def annotate_batch(
    rows: List[Dict[str, Any]],
    snapshot_fn: Optional[SnapshotFn] = None,
) -> List[Dict[str, Any]]:
    """Annotate a list of settled rows with is_true_close / p_close. NEVER raises.

    Only rows where a genuine closing snapshot exists AND devigging succeeds flip
    is_true_close=True.  Rows already carrying is_true_close=True are returned
    unchanged (idempotent).  Rows with no close or a proxy keep is_true_close=False
    (REPLICATION_PENDING stays; never fabricated).

    Parameters
    ----------
    rows:
        Batch of settled game dicts (clean_games from settled_ingest).
    snapshot_fn:
        Same injectable as annotate_row. Shared across the batch so a test stub
        can return different values per game_id.

    Returns
    -------
    list[dict]
        One annotated copy per input row.  Order preserved.  Never raises.
    """
    if not rows:
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            out.append(annotate_row(row, snapshot_fn))
        except Exception as exc:  # noqa: BLE001 -- paranoid purity
            logger.debug("annotate_batch: annotate_row raised -> row unchanged: %s", exc)
            r = dict(row)
            r.setdefault("is_true_close", False)
            r.setdefault("p_close", None)
            out.append(r)
    return out


__all__ = ["annotate_row", "annotate_batch", "SnapshotFn"]
