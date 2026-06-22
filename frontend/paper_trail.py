"""frontend.paper_trail -- read the CLV ledger and produce collapsed paper-trail rows.

Append-only ledger: open row written first, settled twin appended. This module
COLLAPSES open->settled pairs into one current representation and surfaces CLV.

HONESTY: executed always False; no $ / roi / profit field; CLV=better-than-close.
NEVER raises on missing / torn ledger. Synthetic rows (test_* sport/bet_id) and
malformed rows (game_id < _MIN_GAME_ID_LEN) dropped at read time.
INVARIANTS: build only under frontend/; <=300 LOC; ASCII-only; no secrets.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default ledger path mirrors clv_ledger.DEFAULT_LEDGER so both modules see the
# same file. Override with an explicit `ledger_path=` arg (used in tests).
_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_PATH: Path = (
    _REPO_ROOT / "data" / "frontend" / "clv_ledger.jsonl"
)

# Mirrors clv_ledger._MIN_GAME_ID_LEN -- rows with a game_id shorter than this
# are malformed (e.g. "gg" has len=2) and must not reach the trail/consumers.
_MIN_GAME_ID_LEN: int = 3


def _is_synthetic_row(row: Dict[str, Any]) -> bool:
    """True for test_* sport/bet_id or short game_id rows -- mirrors clv_ledger."""
    sport = str(row.get("sport") or "")
    bid = str(row.get("bet_id") or "")
    if sport.startswith("test_") or bid.startswith("test_"):
        return True
    game_id = row.get("game_id")
    if game_id is not None and len(str(game_id)) < _MIN_GAME_ID_LEN:
        return True
    return False


# -- ledger loading -----------------------------------------------------------


def _load_raw(ledger_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read every JSONL line from *ledger_path*. Missing/corrupt -> empty list.

    Drops synthetic/malformed rows via _is_synthetic_row at read time.
    On-disk file is never mutated.
    """
    target = ledger_path if ledger_path is not None else DEFAULT_LEDGER_PATH
    if not target.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    import json as _json
                    row = _json.loads(line)
                except Exception:  # noqa: BLE001 -- tolerate a partial last line
                    continue
                if _is_synthetic_row(row):
                    continue  # read-time filter: synthetic/malformed rows never reach consumers
                rows.append(row)
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper_trail: failed to read ledger: %s", exc)
    return rows


# -- collapse open->settled ---------------------------------------------------

def _settle_key(row: Dict[str, Any]) -> str:
    """Build the natural match key for a ledger row (collapses open->settled twin).

    Prefers the durable ``bet_id`` (independent of the write ts) so a same logical
    bet -- open row, settled twin, and any re-record across a tick / UTC-midnight
    boundary -- collapses to ONE trail row. Falls back to the stored ``settle_key``,
    then to the legacy ts-bearing tuple for rows minted before bet_id existed.
    """
    bid = row.get("bet_id")
    if bid:
        return str(bid)
    existing = row.get("settle_key")
    if existing:
        return str(existing)
    return "|".join([
        str(row.get("sport", "")),
        str(row.get("matchup", "")),
        str(row.get("side", "")),
        str(row.get("taken_book", "")),
        str(row.get("taken_decimal", "")),
        str(row.get("ts", "")),
    ])


def _collapse(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse open->settled pairs into one current row per bet.

    Algorithm:
      1. Partition rows into open and settled buckets keyed by settle_key.
      2. For each unique key: a settled twin wins if present; otherwise open stands.
      3. Result carries the current status, CLV if graded, and enforces:
         executed=False always; no dollar/roi field.
    """
    open_by_key: Dict[str, Dict[str, Any]] = {}
    settled_by_key: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        status = str(row.get("status", "open")).lower()
        key = _settle_key(row)
        if status == "settled":
            # Keep the FIRST settled twin per key (P2-3): a later re-settle from a
            # flipped/glitched feed must NOT silently overwrite the first result.
            if key not in settled_by_key:
                settled_by_key[key] = row
        else:
            open_by_key[key] = row

    # Build the collapsed list: order = settled first (closed bets) then open, and
    # NEWEST-FIRST within each bucket. The newest-first open sort matters under the read
    # cap (limit=200): with hundreds of open paper bets, a freshly-placed bet (e.g. a live
    # in-game WC position) must surface at the TOP of the open section, not be buried at the
    # tail of ledger-append order and clipped away. Settled stays before open (UI contract).
    def _recency(row: Dict[str, Any]) -> str:
        return str(row.get("settled_at") or row.get("ts") or "")

    settled_sorted = sorted(settled_by_key.values(), key=_recency, reverse=True)
    # a settled twin wins its key -> exclude that key from the open bucket (collapse).
    open_only = [r for k, r in open_by_key.items() if k not in settled_by_key]
    open_sorted = sorted(open_only, key=_recency, reverse=True)
    return [_build_trail_row(base) for base in (settled_sorted + open_sorted)]


def _build_trail_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Shape one raw ledger row into a clean TrailRow dict.

    Key output fields: game_id (<sport>|<matchup>|<ts>), matchup, sport, side,
    taken_book/decimal, model_prob, model_ev (EV per unit staked), tier, status,
    graded, outcome, clv_pct/beat_close/clv_is_proxy/clv_note, executed=False,
    ts, settled_at. See module docstring for honesty contract.
    """
    sport = str(raw.get("sport", ""))
    matchup = str(raw.get("matchup", ""))
    ts = str(raw.get("ts", ""))
    side = str(raw.get("side", ""))
    taken_decimal = raw.get("taken_decimal")
    model_prob = raw.get("model_prob")
    tier = raw.get("tier")  # may be absent from raw ledger rows
    status = str(raw.get("status", "open")).lower()
    graded = bool(raw.get("graded", False))
    outcome = raw.get("outcome")  # "win" | "loss" | "push" | "void" | None
    clv_pct = raw.get("clv_pct")
    beat_close = raw.get("beat_close")
    clv_note = raw.get("clv_note")
    settled_at = raw.get("settled_at")
    # market / line / units the history view needs (PT-P0-03/04/05).
    market_type = raw.get("market_type") or raw.get("market")
    line = raw.get("line")
    stake_units = raw.get("stake_units")

    # PE-P0-03: read clv_is_proxy as a FIRST-CLASS field the grader wrote -- do NOT
    # infer proxy from clv_pct=None (that mislabels a NO-close bet as proxy). The
    # producer sets clv_is_proxy=False on a no-close settle; we trust it. Legacy
    # rows (no explicit field) default to False, never an inferred True.
    clv_is_proxy = bool(raw.get("clv_is_proxy", False))
    # clv_status: explicit lifecycle of the CLV grade ("true_close" | "proxy" |
    # "no_close" | None-when-open). A settled row with no clv_pct and no explicit
    # status is treated as "no_close" (CLV unavailable -> VOID/pending), NOT proxy.
    clv_status = raw.get("clv_status")
    if clv_status is None and status == "settled":
        clv_status = "proxy" if clv_is_proxy else (
            "no_close" if clv_pct is None else "true_close")
    # clv_unavailable: a settled bet with NO real CLV (no_close) -> render VOID/
    # pending, NEVER a fabricated proxy-confidence label.
    clv_unavailable = (status == "settled" and clv_pct is None
                       and not clv_is_proxy)

    game_id = "|".join([sport, matchup, ts])

    # model_ev: (model_prob * taken_decimal) - 1 -- never a dollar amount.
    model_ev: Optional[float] = None
    if model_prob is not None and taken_decimal is not None:
        try:
            model_ev = round(float(model_prob) * float(taken_decimal) - 1.0, 6)
        except (TypeError, ValueError):
            model_ev = None

    return {
        "game_id": game_id,
        "matchup": matchup,
        "sport": sport,
        "side": side,
        "market_type": (str(market_type) if market_type is not None else None),
        "line": (float(line) if isinstance(line, (int, float)) else line),
        "taken_book": str(raw.get("taken_book", "")),
        "taken_decimal": (float(taken_decimal) if taken_decimal is not None else None),
        "model_prob": (float(model_prob) if model_prob is not None else None),
        "model_ev": model_ev,
        "tier": (str(tier) if tier is not None else None),
        "stake_units": (float(stake_units) if stake_units is not None else None),
        "status": status,
        "graded": graded,
        "outcome": (str(outcome) if outcome is not None else None),
        "clv_pct": (float(clv_pct) if clv_pct is not None else None),
        "beat_close": (bool(beat_close) if beat_close is not None else None),
        "clv_is_proxy": clv_is_proxy,
        "clv_status": (str(clv_status) if clv_status is not None else None),
        "clv_unavailable": clv_unavailable,
        "clv_note": (str(clv_note) if clv_note is not None else None),
        "executed": False,  # INVARIANT: paper-only, never a real bet
        # preserve the source channel ("paper_ingame" for live in-game positions, else the
        # default paper channel) so the UI can isolate in-game bets from props/pregame.
        "channel": (str(raw.get("channel")) if raw.get("channel") is not None else None),
        "ts": ts,
        "settled_at": (str(settled_at) if settled_at is not None else None),
    }


# -- public API ---------------------------------------------------------------

def read_trail(ledger_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load the CLV ledger and collapse open->settled pairs into trail rows.

    Returns a list of TrailRow dicts (see _build_trail_row). Settled bets come
    first, open bets last. NEVER raises; missing / corrupt ledger -> empty list.
    executed is ALWAYS False on every row.
    """
    try:
        rows = _load_raw(ledger_path)
        return _collapse(rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper_trail.read_trail error: %s", exc)
        return []


def clv_summary(ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Aggregate CLV stats. Returns n_total_rows, n_open, n_bets (gradeable),
    pct_beat_close, mean_clv_pct (null when 0 bets), clv_is_proxy, n_no_close,
    by_sport, note. NEVER raises; missing ledger -> sentinel with zeros/nulls.
    """
    raw_rows: List[Dict[str, Any]] = []
    try:
        raw_rows = _load_raw(ledger_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper_trail.clv_summary: _load_raw error: %s", exc)

    try:
        from scripts.platformkit import clv_ledger as _clv_mod  # noqa: PLC0415
        summary = _clv_mod.clv_summary(raw_rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper_trail.clv_summary error: %s", exc)
        summary = {
            "n_bets": 0,
            "pct_beat_close": None,
            "mean_clv_pct": None,
            "by_sport": {},
        }

    # Tally open, settled, no-close from the raw ledger (before collapse).
    # PE-P0-03: clv_is_proxy uses the EXPLICIT field the grader wrote -- not inferred
    # from clv_pct=None (which would mislabel a no-close bet as a proxy).
    try:
        settled = [r for r in raw_rows if r.get("status") == "settled"]
        open_rows = [r for r in raw_rows if r.get("status") != "settled"]
        has_proxy = any(bool(r.get("clv_is_proxy", False)) for r in settled)
        n_no_close = sum(
            1 for r in settled
            if r.get("clv_pct") is None and not bool(r.get("clv_is_proxy", False))
        )
        n_total_rows = len(raw_rows)
        n_open = len(open_rows)
    except Exception:  # noqa: BLE001
        has_proxy = False
        n_no_close = 0
        n_total_rows = 0
        n_open = 0

    summary["clv_is_proxy"] = has_proxy
    summary["n_no_close"] = n_no_close
    summary["n_total_rows"] = n_total_rows
    summary["n_open"] = n_open
    summary["note"] = (
        "CLV is the honest yardstick (better-number-than-close). "
        "Positive CLV = you locked a better price than the market settled at. "
        "No $ edge is claimed; this is calibrated decision-support only."
    )
    return summary


__all__ = [
    "DEFAULT_LEDGER_PATH",
    "read_trail",
    "clv_summary",
]
