"""L07_pnl_ledger.py — Settlement + P&L Ledger (execute_loop layer 7).

Storage: data/ledger/bets.parquet  (CSV fallback if pyarrow missing)
         data/ledger/contests.parquet

CLI:
    python L07_pnl_ledger.py settle [--date YYYY-MM-DD]
    python L07_pnl_ledger.py summary [--start YYYY-MM-DD] [--end YYYY-MM-DD]
                                     [--by stat|book|day]
    python L07_pnl_ledger.py open

Event Publication
-----------------
L07 publishes the following events via L46 EventBus (additive — does not replace
existing direct calls to L22 alerting):

``bet.settled``
    Emitted for each bet that transitions from OPEN → WON / LOST / PUSH.
    Source: ``"L7"``
    Payload schema::

        {
            "bet_id":     str,   # unique bet identifier
            "status":     str,   # "WON" | "LOST" | "PUSH"
            "stake":      float, # stake in units
            "pnl":        float, # realised P&L in units
            "player":     str,   # player name
            "stat":       str,   # stat key, e.g. "pts"
            "settled_at": str,   # ISO 8601 UTC timestamp of settlement
        }

    NOTE: VOID (DNP) outcomes do NOT emit ``bet.settled``.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_DIR))

import src.data.nba_api_headers_patch  # noqa: F401, E402

import pandas as pd

# Soft-import L46 EventBus — non-fatal if unavailable (e.g. in isolated tests)
try:
    from scripts.execute_loop import L46_event_bus as _L46
except Exception:
    _L46 = None

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_LEDGER_DIR = PROJECT_DIR / "data" / "ledger"
_BETS_FILE = _LEDGER_DIR / "bets.parquet"
_BETS_CSV = _LEDGER_DIR / "bets.csv"
_CONTESTS_FILE = _LEDGER_DIR / "contests.parquet"
_CONTESTS_CSV = _LEDGER_DIR / "contests.csv"

# ---------------------------------------------------------------------------
# Parquet / CSV helpers
# ---------------------------------------------------------------------------
try:
    import pyarrow  # noqa: F401
    _HAS_PARQUET = True
except ImportError:
    _HAS_PARQUET = False


def _bets_path() -> Path:
    return _BETS_FILE if _HAS_PARQUET else _BETS_CSV


def _contests_path() -> Path:
    return _CONTESTS_FILE if _HAS_PARQUET else _CONTESTS_CSV


def _read_df(path_parquet: Path, path_csv: Path) -> pd.DataFrame:
    """Read parquet or csv; return empty DataFrame if neither exists."""
    if _HAS_PARQUET and path_parquet.exists():
        return pd.read_parquet(path_parquet)
    if path_csv.exists():
        return pd.read_csv(path_csv, dtype=str)
    return pd.DataFrame()


def _write_df(df: pd.DataFrame, path_parquet: Path, path_csv: Path) -> None:
    """Atomic write: write to .tmp then rename."""
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    if _HAS_PARQUET:
        tmp = path_parquet.with_suffix(".tmp.parquet")
        df.to_parquet(tmp, index=False)
        tmp.replace(path_parquet)
    else:
        tmp = path_csv.with_suffix(".tmp.csv")
        df.to_csv(tmp, index=False)
        tmp.replace(path_csv)


def _load_bets() -> pd.DataFrame:
    return _read_df(_BETS_FILE, _BETS_CSV)


def _save_bets(df: pd.DataFrame) -> None:
    _write_df(df, _BETS_FILE, _BETS_CSV)


def _load_contests() -> pd.DataFrame:
    return _read_df(_CONTESTS_FILE, _CONTESTS_CSV)


def _save_contests(df: pd.DataFrame) -> None:
    _write_df(df, _CONTESTS_FILE, _CONTESTS_CSV)


# ---------------------------------------------------------------------------
# BetRow dataclass
# ---------------------------------------------------------------------------
@dataclass
class BetRow:
    bet_id: str = ""
    placed_at_iso: str = ""
    book: str = ""
    market: str = ""       # e.g. "player_prop_pts"
    player: str = ""
    stat: str = ""
    line: float = 0.0
    side: str = ""
    stake: float = 0.0
    odds: int = -110
    model_q50: float = 0.0
    model_p_side: float = 0.0
    model_edge_pp: float = 0.0
    test_mode: bool = True
    status: str = "OPEN"
    settled_at_iso: str = ""
    actual_value: Optional[float] = None
    pnl: Optional[float] = None
    game_id: str = ""
    notes: str = ""
    # v2 fields — all Optional so existing CSVs load with None defaults
    ip: Optional[str] = None                  # L26 IP cross-checks
    model_p_var: Optional[float] = None       # L33 uncertainty
    clv_units: Optional[float] = None
    clv_prob_pts: Optional[float] = None
    line_at_close: Optional[float] = None


_BET_COLS = list(BetRow.__dataclass_fields__.keys())

# ---------------------------------------------------------------------------
# bet_id generation
# ---------------------------------------------------------------------------
def _make_bet_id(row: BetRow) -> str:
    """Use composite key if fields are meaningful, else uuid4 hex."""
    if row.bet_id:
        return row.bet_id
    if row.book and row.player and row.stat and row.line and row.placed_at_iso:
        return f"{row.book}:{row.player}:{row.stat}:{row.line}:{row.placed_at_iso}"
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def place_bet(row: BetRow) -> str:
    """Append a BetRow to the ledger. Returns the bet_id.

    Idempotent: if bet_id already exists, the existing row is kept silently.
    Fills bet_id and placed_at_iso if not set.
    """
    if not row.placed_at_iso:
        row.placed_at_iso = datetime.now(timezone.utc).isoformat()
    if not row.bet_id:
        row.bet_id = _make_bet_id(row)

    existing = _load_bets()

    if not existing.empty and row.bet_id in existing["bet_id"].values:
        log.debug("place_bet: duplicate bet_id=%s — skipped", row.bet_id)
        return row.bet_id

    new_row = pd.DataFrame([_row_to_dict(row)])
    combined = pd.concat([existing, new_row], ignore_index=True) if not existing.empty else new_row
    _save_bets(combined)
    log.info("place_bet: recorded bet_id=%s player=%s stat=%s line=%s side=%s",
             row.bet_id, row.player, row.stat, row.line, row.side)
    return row.bet_id


def _row_to_dict(row: BetRow) -> dict:
    d = asdict(row)
    # Serialise None → "" for storage compatibility
    for k, v in d.items():
        if v is None:
            d[k] = ""
    return d


def _dict_to_betrow(d: dict) -> BetRow:
    """Rehydrate a dict (from parquet/csv) back to a BetRow."""
    def _flt(v):
        try:
            return float(v) if v not in (None, "", "nan") else None
        except (TypeError, ValueError):
            return None

    def _int(v, default):
        try:
            return int(float(v)) if v not in (None, "", "nan") else default
        except (TypeError, ValueError):
            return default

    def _bool(v):
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("true", "1", "yes")

    return BetRow(
        bet_id=str(d.get("bet_id", "")),
        placed_at_iso=str(d.get("placed_at_iso", "")),
        book=str(d.get("book", "")),
        market=str(d.get("market", "")),
        player=str(d.get("player", "")),
        stat=str(d.get("stat", "")),
        line=float(d.get("line", 0.0) or 0.0),
        side=str(d.get("side", "")),
        stake=float(d.get("stake", 0.0) or 0.0),
        odds=_int(d.get("odds"), -110),
        model_q50=float(d.get("model_q50", 0.0) or 0.0),
        model_p_side=float(d.get("model_p_side", 0.0) or 0.0),
        model_edge_pp=float(d.get("model_edge_pp", 0.0) or 0.0),
        test_mode=_bool(d.get("test_mode", True)),
        status=str(d.get("status", "OPEN")),
        settled_at_iso=str(d.get("settled_at_iso", "")),
        actual_value=_flt(d.get("actual_value")),
        pnl=_flt(d.get("pnl")),
        game_id=str(d.get("game_id", "")),
        notes=str(d.get("notes", "")),
        # v2 fields — safe defaults for legacy CSVs that lack these columns
        ip=(str(d["ip"]) if d.get("ip") not in (None, "", "nan") else None),
        model_p_var=_flt(d.get("model_p_var")),
        clv_units=_flt(d.get("clv_units")),
        clv_prob_pts=_flt(d.get("clv_prob_pts")),
        line_at_close=_flt(d.get("line_at_close")),
    )


def _compute_clv_for_bet(
    bet: "BetRow",
) -> "tuple[Optional[float], Optional[float], Optional[float]]":
    """Try to compute CLV for a single bet via L19.

    Returns (line_at_close, clv_units, clv_prob_pts) or (None, None, None) on
    any error (missing snapshots, import failure, etc.).  Always safe to call.
    """
    try:
        import importlib
        L19 = importlib.import_module("scripts.execute_loop.L19_clv_calculator")

        date = str(bet.placed_at_iso)[:10]
        if not date:
            return None, None, None

        snaps = L19.load_snapshots(date, date)
        if snaps.empty:
            log.debug("_compute_clv_for_bet: no snapshots for %s", date)
            return None, None, None

        import unicodedata

        def _nk(s: str) -> str:
            nfkd = unicodedata.normalize("NFKD", str(s))
            return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()

        player_norm = _nk(bet.player)
        stat_key = str(bet.stat).lower()

        mask = (
            (snaps["player_norm"] == player_norm)
            & (snaps["stat"].str.lower() == stat_key)
        )
        player_snaps = snaps[mask]
        if player_snaps.empty:
            log.debug("_compute_clv_for_bet: no snapshot row for player=%s stat=%s", bet.player, bet.stat)
            return None, None, None

        # pick latest snapshot as closing line proxy
        close_row = player_snaps.loc[player_snaps["snapshot_ts"].idxmax()]
        lclose = float(close_row["line"])

        clv_pt = L19.compute_clv(bet, line_at_bet=float(bet.line), line_at_close=lclose)
        return lclose, clv_pt.clv_units, clv_pt.clv_prob_pts
    except Exception as exc:
        log.debug("_compute_clv_for_bet: failed for bet_id=%s: %s", getattr(bet, "bet_id", "?"), exc)
        return None, None, None


def get_open_bets() -> list[BetRow]:
    """Return all OPEN bets as BetRow objects."""
    df = _load_bets()
    if df.empty:
        return []
    open_df = df[df["status"].str.upper() == "OPEN"]
    return [_dict_to_betrow(r) for _, r in open_df.iterrows()]


def _compute_pnl(stake: float, odds: int, status: str) -> float:
    """American-odds P&L math."""
    if status == "WON":
        if odds < 0:
            return round(stake * (100.0 / abs(odds)), 4)
        return round(stake * (odds / 100.0), 4)
    if status == "LOST":
        return -stake
    return 0.0  # PUSH or VOID


def settle_unsettled(date: str = None) -> int:
    """Settle all OPEN bets that have a game_id.

    Fetches boxscores via settle_tonight.fetch_boxscore_player_stats.
    Returns count of bets settled.
    """
    from scripts.validation.real_lines_check.settle_tonight import (
        fetch_boxscore_player_stats,
    )

    df = _load_bets()
    if df.empty:
        return 0

    open_mask = df["status"].str.upper() == "OPEN"
    has_game = df["game_id"].astype(str).str.strip() != ""
    candidates = df[open_mask & has_game].copy()
    if candidates.empty:
        return 0

    # Cache boxscores per game_id
    box_cache: dict[str, dict] = {}
    for gid in candidates["game_id"].unique():
        try:
            box_cache[str(gid)] = fetch_boxscore_player_stats(str(gid))
            log.info("settle_unsettled: fetched boxscore game_id=%s (%d players)",
                     gid, len(box_cache[str(gid)]))
        except Exception as exc:
            log.warning("settle_unsettled: boxscore fetch failed game_id=%s: %s", gid, exc)
            box_cache[str(gid)] = None  # type: ignore[assignment]

    settled_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx, row_s in candidates.iterrows():
        bet = _dict_to_betrow(row_s.to_dict())
        gid = str(row_s["game_id"]).strip()
        box = box_cache.get(gid)

        if box is None:
            # Boxscore fetch failed — leave OPEN
            continue

        # Name-key lookup (mirrors settle_tonight logic)
        import unicodedata

        def _nk(s: str) -> str:
            nfkd = unicodedata.normalize("NFKD", str(s))
            return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()

        player_key = _nk(bet.player)
        player_box = box.get(player_key)
        if player_box is None:
            # Last-name fallback
            last = player_key.split()[-1] if " " in player_key else player_key
            cands = [k for k in box if k.endswith(" " + last) or k == last]
            player_box = box.get(cands[0]) if cands else None

        if player_box is None:
            log.debug("settle_unsettled: player %r not in boxscore game_id=%s", bet.player, gid)
            continue

        # DNP check
        mn = str(player_box.get("min", "")).strip()
        if mn in ("", "0:00", "0", "0.0"):
            df.at[idx, "status"] = "VOID"
            df.at[idx, "pnl"] = 0.0
            df.at[idx, "notes"] = "DNP"
            df.at[idx, "settled_at_iso"] = now_iso
            df.at[idx, "actual_value"] = 0.0
            settled_count += 1
            log.info("settle_unsettled: VOID (DNP) bet_id=%s player=%s", bet.bet_id, bet.player)
            continue

        # Stat lookup — normalise key
        stat_key = bet.stat.lower()
        actual = player_box.get(stat_key)
        if actual is None:
            log.debug("settle_unsettled: stat %r not in boxscore for %r", stat_key, bet.player)
            continue

        actual = float(actual)
        line = float(bet.line)
        side = str(bet.side).upper()

        # PUSH
        if abs(actual - line) < 1e-9:
            status = "PUSH"
        elif side == "OVER":
            status = "WON" if actual > line else "LOST"
        elif side == "UNDER":
            status = "WON" if actual < line else "LOST"
        else:
            log.warning("settle_unsettled: unknown side=%r for bet_id=%s", side, bet.bet_id)
            continue

        pnl = _compute_pnl(float(bet.stake), int(bet.odds), status)
        df.at[idx, "status"] = status
        df.at[idx, "actual_value"] = actual
        df.at[idx, "pnl"] = pnl
        df.at[idx, "settled_at_iso"] = now_iso

        # Publish bet.settled event via L46 EventBus (additive — non-fatal)
        if _L46 is not None:
            try:
                _L46.publish("bet.settled", source="L7", payload={
                    "bet_id": bet.bet_id,
                    "status": status,
                    "stake": float(bet.stake),
                    "pnl": pnl,
                    "player": bet.player,
                    "stat": bet.stat,
                    "settled_at": now_iso,
                })
            except Exception:
                log.debug("L46 publish failed (non-fatal)", exc_info=True)

        # CLV enrichment (soft — never blocks settlement)
        lclose, clv_u, clv_pp = _compute_clv_for_bet(bet)
        if lclose is not None:
            df.at[idx, "line_at_close"] = lclose
        if clv_u is not None:
            df.at[idx, "clv_units"] = clv_u
        if clv_pp is not None:
            df.at[idx, "clv_prob_pts"] = clv_pp

        settled_count += 1
        log.info("settle_unsettled: %s bet_id=%s player=%s %s %s %.1f actual=%.1f pnl=%.4f",
                 status, bet.bet_id, bet.player, stat_key, side, line, actual, pnl)

    if settled_count > 0:
        _save_bets(df)

    return settled_count


def get_pnl_summary(
    start: str = None,
    end: str = None,
    by: str = "stat",
) -> dict:
    """Aggregate P&L for settled bets, grouped by `by` (stat|book|day).

    Returns a dict keyed by the group value, each with:
        n, won, lost, push, void, total_pnl, total_staked, roi_pct, hit_rate_pct
    """
    df = _load_bets()
    if df.empty:
        return {}

    settled_statuses = {"WON", "LOST", "PUSH", "VOID"}
    mask = df["status"].str.upper().isin(settled_statuses)

    if start:
        mask &= df["settled_at_iso"].str[:10] >= start
    if end:
        mask &= df["settled_at_iso"].str[:10] <= end

    settled = df[mask].copy()
    if settled.empty:
        return {}

    def _group_key(row: pd.Series) -> str:
        s = str(row.get(by, ""))
        if by == "day":
            return str(row.get("settled_at_iso", ""))[:10]
        return s.lower() or "(none)"

    groups: dict[str, list] = {}
    for _, row in settled.iterrows():
        k = _group_key(row)
        groups.setdefault(k, []).append(row)

    out: dict[str, dict] = {}
    for k, rows_list in sorted(groups.items()):
        n = len(rows_list)
        won = sum(1 for r in rows_list if str(r.get("status", "")).upper() == "WON")
        lost = sum(1 for r in rows_list if str(r.get("status", "")).upper() == "LOST")
        push = sum(1 for r in rows_list if str(r.get("status", "")).upper() == "PUSH")
        void = sum(1 for r in rows_list if str(r.get("status", "")).upper() == "VOID")

        def _f(v):
            try:
                return float(v) if v not in (None, "", "nan") else 0.0
            except (TypeError, ValueError):
                return 0.0

        total_pnl = round(sum(_f(r.get("pnl")) for r in rows_list), 4)
        total_staked = round(sum(_f(r.get("stake")) for r in rows_list), 4)
        decisive = won + lost
        hit_rate = round(100.0 * won / decisive, 2) if decisive else 0.0
        roi = round(100.0 * total_pnl / total_staked, 2) if total_staked > 0 else 0.0

        out[k] = {
            "n": n,
            "won": won,
            "lost": lost,
            "push": push,
            "void": void,
            "total_pnl": total_pnl,
            "total_staked": total_staked,
            "roi_pct": roi,
            "hit_rate_pct": hit_rate,
        }

    return out


def close_contest(contest_id: str, entry_position: int, total_payout: float) -> None:
    """Record final result for a DFS contest entry.

    Appends (or updates) the contest row and stamps a P&L = total_payout - entry_fee.
    """
    df = _load_contests()

    if not df.empty and contest_id in df["contest_id"].values:
        idx = df.index[df["contest_id"] == contest_id][0]
        entry_fee = float(df.at[idx, "entry_fee"] if "entry_fee" in df.columns else 0)
        pnl = round(total_payout - entry_fee, 4)
        df.at[idx, "entry_position"] = entry_position
        df.at[idx, "total_payout"] = total_payout
        df.at[idx, "pnl"] = pnl
        df.at[idx, "settled_at_iso"] = datetime.now(timezone.utc).isoformat()
        df.at[idx, "status"] = "SETTLED"
    else:
        new_row = pd.DataFrame([{
            "contest_id": contest_id,
            "entry_position": entry_position,
            "total_payout": total_payout,
            "entry_fee": 0.0,
            "pnl": round(total_payout, 4),
            "settled_at_iso": datetime.now(timezone.utc).isoformat(),
            "status": "SETTLED",
        }])
        df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row

    _save_contests(df)
    log.info("close_contest: contest_id=%s position=%d payout=%.2f",
             contest_id, entry_position, total_payout)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli_settle(args) -> None:
    count = settle_unsettled(date=args.date)
    print(f"[L07] settled {count} bet(s)")


def _cli_summary(args) -> None:
    summary = get_pnl_summary(start=args.start, end=args.end, by=args.by)
    if not summary:
        print("[L07] no settled bets in range")
        return
    print(f"[L07] P&L summary by {args.by}")
    hdr = f"  {'key':<20}  {'n':>4}  {'won':>4}  {'lost':>4}  "
    hdr += f"{'pnl':>8}  {'staked':>8}  {'roi%':>7}  {'hit%':>7}"
    print(hdr)
    for k, d in sorted(summary.items()):
        print(
            f"  {k:<20}  {d['n']:>4}  {d['won']:>4}  {d['lost']:>4}  "
            f"{d['total_pnl']:>8.2f}  {d['total_staked']:>8.2f}  "
            f"{d['roi_pct']:>6.1f}%  {d['hit_rate_pct']:>6.1f}%"
        )


def _cli_open(args) -> None:  # noqa: ARG001
    bets = get_open_bets()
    if not bets:
        print("[L07] no open bets")
        return
    print(f"[L07] {len(bets)} open bet(s):")
    for b in bets:
        print(f"  {b.bet_id[:16]}  {b.player:<22} {b.stat:>5} {b.side:>5} "
              f"{b.line:>6.1f}  stake={b.stake:.2f}  book={b.book}")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="L07_pnl_ledger")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_settle = sub.add_parser("settle", help="Settle open bets from boxscores")
    p_settle.add_argument("--date", default=None, help="YYYY-MM-DD (future use)")
    p_settle.set_defaults(func=_cli_settle)

    p_summary = sub.add_parser("summary", help="Print P&L summary")
    p_summary.add_argument("--start", default=None, help="YYYY-MM-DD")
    p_summary.add_argument("--end", default=None, help="YYYY-MM-DD")
    p_summary.add_argument("--by", default="stat", choices=["stat", "book", "day"])
    p_summary.set_defaults(func=_cli_summary)

    p_open = sub.add_parser("open", help="List open bets")
    p_open.set_defaults(func=_cli_open)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
