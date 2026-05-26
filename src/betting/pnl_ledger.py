"""pnl_ledger.py — Tier 2-8 (loop 5).

Manual placement -> settlement -> P&L ledger for prop bets.

Single source of truth: data/pnl_ledger.csv. Separate bankroll log:
data/pnl_bankroll.csv (one row per manual deposit/withdraw + per-settle).

Read-only with respect to sportsbooks: operator places the real bet, then
records it here. No sportsbook API is touched.

Schema (data/pnl_ledger.csv):
    bet_id        — UUID4 string
    placed_at     — ISO timestamp (seconds resolution)
    game_id       — NBA game id (e.g. 0022500123) or ""
    player_id     — NBA player id or ""
    player        — player full name
    team          — player team abbrev or ""
    stat          — pts|reb|ast|fg3m|stl|blk|tov
    line          — float O/U line
    side          — OVER|UNDER
    book          — DK|FD|MGM|... freeform
    american_odds — int (-115, +120)
    stake         — $ wagered
    model_pred    — model point prediction
    model_prob    — model P(win this side)  (may be empty)
    model_edge    — model_pred - line       (may be empty)
    kelly_pct     — recommended Kelly % (may be empty)
    status        — open|won|lost|push|voided
    settled_at    — ISO timestamp or ""
    actual_stat   — float realised stat (or "")
    profit_loss   — realised P&L on this bet ($), "" while open
    bankroll_after — bankroll after settle ($), "" while open

Public API:
    place_bet(...)        -> bet_id
    settle_bet(bet_id, actual_stat) -> dict {status, profit_loss, bankroll_after}
    void_bet(bet_id)      -> dict
    pnl_summary(date_range=None, filter_by=None) -> dict
    open_bets()           -> list[dict]
    record_bankroll(amount, note="manual") -> None
    current_bankroll()    -> float

Atomic: every write goes to a tmpfile then os.replace().  A sidecar lockfile
(``.lock``) guards concurrent writers — fcntl on POSIX, msvcrt on Windows.
"""
from __future__ import annotations

import csv
import os
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

from src.prediction.betting_portfolio import clamp_kelly_pct

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

LEDGER_CSV    = os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv")
BANKROLL_CSV  = os.path.join(PROJECT_DIR, "data", "pnl_bankroll.csv")
LOCK_PATH     = LEDGER_CSV + ".lock"

LEDGER_COLS = [
    "bet_id", "placed_at", "game_id", "player_id", "player", "team",
    "stat", "line", "side", "book", "american_odds", "stake",
    "model_pred", "model_prob", "model_edge", "kelly_pct",
    "status", "settled_at", "actual_stat", "profit_loss", "bankroll_after",
    # Additive (tier4-14): strategy tag for A/B attribution. Old rows without
    # this column default to "default" via DictReader fallback.
    "strategy",
]

BANKROLL_COLS = ["timestamp", "amount", "running_balance", "note"]

VALID_SIDES   = {"OVER", "UNDER"}
VALID_STATUS  = {"open", "won", "lost", "push", "voided"}
VALID_STATS   = {"pts", "reb", "ast", "fg3m", "stl", "blk", "tov"}


# --------------------------------------------------------------------------- #
# File locking — keeps concurrent writers from corrupting the ledger.         #
# --------------------------------------------------------------------------- #
@contextmanager
def _file_lock(timeout: float = 10.0):
    """Cross-platform exclusive file lock. Held for the duration of the with block."""
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    deadline = time.time() + timeout
    fh = None
    while True:
        try:
            # 'x' mode: exclusive create — fails if file already exists.
            fh = open(LOCK_PATH, "x")
            break
        except FileExistsError:
            if time.time() >= deadline:
                # Stale lock recovery: remove + retry once.
                try:
                    if time.time() - os.path.getmtime(LOCK_PATH) > 30.0:
                        os.unlink(LOCK_PATH)
                        continue
                except OSError:
                    pass
                raise TimeoutError(f"could not acquire ledger lock at {LOCK_PATH}")
            time.sleep(0.05)
    try:
        fh.write(f"{os.getpid()}\n")
        fh.flush()
        yield
    finally:
        try:
            fh.close()
        except Exception:
            pass
        try:
            os.unlink(LOCK_PATH)
        except OSError:
            pass


def _atomic_write_rows(path: str, cols: List[str], rows: Iterable[Dict]) -> None:
    """Write rows to path atomically via tmpfile + os.replace."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}.{int(time.time()*1e6)}"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, path)


def _load_ledger() -> List[Dict]:
    if not os.path.exists(LEDGER_CSV):
        return []
    rows: List[Dict] = []
    with open(LEDGER_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(r)
    return rows


def _load_bankroll() -> List[Dict]:
    if not os.path.exists(BANKROLL_CSV):
        return []
    with open(BANKROLL_CSV, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------- #
# Odds math.                                                                  #
# --------------------------------------------------------------------------- #
def american_to_payout(odds: int) -> float:
    """Net profit per $1 staked on a winning bet (excludes stake return)."""
    odds = int(odds)
    if odds == 0:
        return 0.0
    if odds > 0:
        return odds / 100.0
    return 100.0 / abs(odds)


# --------------------------------------------------------------------------- #
# Bankroll.                                                                   #
# --------------------------------------------------------------------------- #
def _append_bankroll(amount: float, note: str, running: float) -> None:
    os.makedirs(os.path.dirname(BANKROLL_CSV), exist_ok=True)
    new_file = not os.path.exists(BANKROLL_CSV) or os.path.getsize(BANKROLL_CSV) == 0
    with open(BANKROLL_CSV, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(BANKROLL_COLS)
        w.writerow([
            datetime.now().isoformat(timespec="seconds"),
            f"{float(amount):.2f}",
            f"{float(running):.2f}",
            note,
        ])


def current_bankroll() -> float:
    """Return latest running_balance recorded in pnl_bankroll.csv (or 0)."""
    rows = _load_bankroll()
    if not rows:
        return 0.0
    try:
        return float(rows[-1]["running_balance"])
    except (KeyError, ValueError):
        return 0.0


def record_bankroll(amount: float, note: str = "manual") -> float:
    """Apply a manual deposit (positive) or withdraw (negative). Returns new balance."""
    with _file_lock():
        new_bal = current_bankroll() + float(amount)
        _append_bankroll(float(amount), note, new_bal)
    return new_bal


# --------------------------------------------------------------------------- #
# Placement.                                                                  #
# --------------------------------------------------------------------------- #
def place_bet(
    game_id: str,
    player: str,
    stat: str,
    line: float,
    side: str,
    book: str,
    odds: int,
    stake: float,
    model_pred: Optional[float] = None,
    model_prob: Optional[float] = None,
    kelly_pct: Optional[float] = None,
    player_id: Optional[str] = None,
    team: Optional[str] = None,
    bankroll_before: Optional[float] = None,
    strategy: str = "default",
) -> str:
    """Record a placed bet. Returns the new bet_id (UUID4)."""
    side = str(side).upper()
    stat = str(stat).lower()
    if side not in VALID_SIDES:
        raise ValueError(f"side must be OVER|UNDER, got {side!r}")
    if stat not in VALID_STATS:
        raise ValueError(f"stat must be one of {VALID_STATS}, got {stat!r}")
    if float(stake) <= 0:
        raise ValueError(f"stake must be > 0, got {stake!r}")

    bet_id = str(uuid.uuid4())
    edge = (float(model_pred) - float(line)) if model_pred is not None else None

    with _file_lock():
        rows = _load_ledger()
        rows.append({
            "bet_id":         bet_id,
            "placed_at":      datetime.now().isoformat(timespec="seconds"),
            "game_id":        game_id or "",
            "player_id":      str(player_id) if player_id is not None else "",
            "player":         player,
            "team":           team or "",
            "stat":           stat,
            "line":           f"{float(line):.2f}",
            "side":           side,
            "book":           book,
            "american_odds":  str(int(odds)),
            "stake":          f"{float(stake):.2f}",
            "model_pred":     "" if model_pred is None else f"{float(model_pred):.4f}",
            "model_prob":     "" if model_prob is None else f"{float(model_prob):.4f}",
            "model_edge":     "" if edge is None else f"{edge:+.4f}",
            "kelly_pct":      "" if kelly_pct is None else f"{clamp_kelly_pct(kelly_pct):.4f}",
            "status":         "open",
            "settled_at":     "",
            "actual_stat":    "",
            "profit_loss":    "",
            "bankroll_after": "",
            "strategy":       strategy or "default",
        })
        _atomic_write_rows(LEDGER_CSV, LEDGER_COLS, rows)

        # Deduct stake from bankroll immediately (stake at risk).
        if bankroll_before is not None and current_bankroll() == 0.0:
            _append_bankroll(float(bankroll_before), "initial", float(bankroll_before))
        new_bal = current_bankroll() - float(stake)
        _append_bankroll(-float(stake), f"stake:{bet_id[:8]}", new_bal)

    return bet_id


# --------------------------------------------------------------------------- #
# Settlement.                                                                 #
# --------------------------------------------------------------------------- #
def _resolve_status(line: float, side: str, actual: float) -> str:
    if abs(actual - line) < 1e-9:
        return "push"
    over_wins = actual > line
    if (side == "OVER" and over_wins) or (side == "UNDER" and not over_wins):
        return "won"
    return "lost"


def _compute_profit(status: str, stake: float, odds: int) -> float:
    if status == "won":
        return round(stake * american_to_payout(odds), 2)
    if status == "lost":
        return round(-stake, 2)
    return 0.0  # push or voided


def settle_bet(bet_id: str, actual_stat: float) -> Dict:
    """Settle an open bet. Auto-computes won/lost/push from line vs actual."""
    with _file_lock():
        rows = _load_ledger()
        target = next((r for r in rows if r["bet_id"] == bet_id), None)
        if target is None:
            raise KeyError(f"bet_id {bet_id} not found")
        if target["status"] != "open":
            raise ValueError(f"bet_id {bet_id} already {target['status']}")

        line   = float(target["line"])
        side   = target["side"]
        stake  = float(target["stake"])
        odds   = int(target["american_odds"])
        actual = float(actual_stat)

        status = _resolve_status(line, side, actual)
        pnl    = _compute_profit(status, stake, odds)

        # Bankroll move: return stake + add net profit (won),
        # nothing (lost — stake already deducted),
        # return stake (push).
        if status == "won":
            credit = stake + pnl   # stake back + winnings
        elif status == "push":
            credit = stake         # stake back
        else:
            credit = 0.0
        new_bal = current_bankroll() + credit

        target["status"]         = status
        target["settled_at"]     = datetime.now().isoformat(timespec="seconds")
        target["actual_stat"]    = f"{actual:.4f}"
        target["profit_loss"]    = f"{pnl:+.2f}"
        target["bankroll_after"] = f"{new_bal:.2f}"
        _atomic_write_rows(LEDGER_CSV, LEDGER_COLS, rows)

        if credit != 0.0:
            _append_bankroll(credit, f"settle:{bet_id[:8]}:{status}", new_bal)

    return {"status": status, "profit_loss": pnl, "bankroll_after": new_bal}


def void_bet(bet_id: str) -> Dict:
    """Void an open bet (returns stake, status=voided, no P&L)."""
    with _file_lock():
        rows = _load_ledger()
        target = next((r for r in rows if r["bet_id"] == bet_id), None)
        if target is None:
            raise KeyError(f"bet_id {bet_id} not found")
        if target["status"] != "open":
            raise ValueError(f"bet_id {bet_id} already {target['status']}")
        stake = float(target["stake"])
        new_bal = current_bankroll() + stake
        target["status"]         = "voided"
        target["settled_at"]     = datetime.now().isoformat(timespec="seconds")
        target["profit_loss"]    = "0.00"
        target["bankroll_after"] = f"{new_bal:.2f}"
        _atomic_write_rows(LEDGER_CSV, LEDGER_COLS, rows)
        _append_bankroll(stake, f"void:{bet_id[:8]}", new_bal)
    return {"status": "voided", "profit_loss": 0.0, "bankroll_after": new_bal}


# --------------------------------------------------------------------------- #
# Query.                                                                      #
# --------------------------------------------------------------------------- #
def open_bets() -> List[Dict]:
    return [r for r in _load_ledger() if r.get("status") == "open"]


def all_bets() -> List[Dict]:
    return _load_ledger()


def _parse_date_range(date_range: Optional[str]) -> Optional[tuple]:
    """Parse '7d', '30d', '90d', 'YYYY-MM-DD:YYYY-MM-DD', or None."""
    if not date_range:
        return None
    today = datetime.now()
    if date_range.endswith("d") and date_range[:-1].isdigit():
        days = int(date_range[:-1])
        return (today - timedelta(days=days), today + timedelta(days=1))
    if ":" in date_range:
        a, b = date_range.split(":", 1)
        return (datetime.fromisoformat(a), datetime.fromisoformat(b))
    raise ValueError(f"unknown date_range format {date_range!r}")


def _apply_filters(
    rows: List[Dict],
    date_range: Optional[str],
    filter_by: Optional[Dict[str, str]],
) -> List[Dict]:
    dr = _parse_date_range(date_range)
    out = []
    for r in rows:
        if dr is not None:
            ts = r.get("placed_at", "")
            if not ts:
                continue
            try:
                t = datetime.fromisoformat(ts)
            except ValueError:
                continue
            if not (dr[0] <= t <= dr[1]):
                continue
        if filter_by:
            ok = True
            for k, v in filter_by.items():
                if str(r.get(k, "")).lower() != str(v).lower():
                    ok = False
                    break
            if not ok:
                continue
        out.append(r)
    return out


def pnl_summary(
    date_range: Optional[str] = None,
    filter_by: Optional[Dict[str, str]] = None,
) -> Dict:
    """Aggregate stats across (optionally filtered) settled bets.

    Returns:
        n_bets, n_settled, n_open, win_rate, push_rate, roi,
        total_profit, total_staked, avg_stake, sharpe, current_bankroll.
    """
    rows = _apply_filters(_load_ledger(), date_range, filter_by)
    settled = [r for r in rows if r["status"] in ("won", "lost", "push")]
    won     = sum(1 for r in settled if r["status"] == "won")
    lost    = sum(1 for r in settled if r["status"] == "lost")
    push    = sum(1 for r in settled if r["status"] == "push")
    open_n  = sum(1 for r in rows if r["status"] == "open")

    def _f(s: str) -> float:
        try:
            return float(s)
        except (TypeError, ValueError):
            return 0.0

    profits  = [_f(r.get("profit_loss")) for r in settled]
    stakes   = [_f(r.get("stake")) for r in settled]
    total_p  = round(sum(profits), 2)
    total_s  = round(sum(stakes), 2)
    n_decisive = won + lost
    win_rate = round(won / n_decisive, 4) if n_decisive else 0.0
    push_rate = round(push / len(settled), 4) if settled else 0.0
    roi      = round(total_p / total_s, 4) if total_s > 0 else 0.0

    # Sharpe of per-bet ROI (no risk-free subtraction — relative comparison only).
    if len(profits) > 1 and total_s > 0:
        per_bet_roi = [p / s if s > 0 else 0.0 for p, s in zip(profits, stakes)]
        mean_r = sum(per_bet_roi) / len(per_bet_roi)
        var_r  = sum((r - mean_r) ** 2 for r in per_bet_roi) / (len(per_bet_roi) - 1)
        sigma  = var_r ** 0.5
        sharpe = round(mean_r / sigma, 4) if sigma > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "n_bets":           len(rows),
        "n_settled":        len(settled),
        "n_open":           open_n,
        "won":              won,
        "lost":             lost,
        "push":             push,
        "win_rate":         win_rate,
        "push_rate":        push_rate,
        "roi":              roi,
        "total_profit":     total_p,
        "total_staked":     total_s,
        "avg_stake":        round(total_s / len(settled), 2) if settled else 0.0,
        "sharpe":           sharpe,
        "current_bankroll": round(current_bankroll(), 2),
    }


def pnl_group_by(field: str, date_range: Optional[str] = None) -> List[Dict]:
    """Group settled bets by field (stat|book|side|player) and report sub-summary."""
    rows = _apply_filters(_load_ledger(), date_range, None)
    settled = [r for r in rows if r["status"] in ("won", "lost", "push")]
    groups: Dict[str, List[Dict]] = {}
    for r in settled:
        k = str(r.get(field, "")).lower() or "(none)"
        groups.setdefault(k, []).append(r)

    out = []
    for k, grp in sorted(groups.items()):
        won   = sum(1 for r in grp if r["status"] == "won")
        lost  = sum(1 for r in grp if r["status"] == "lost")
        push  = sum(1 for r in grp if r["status"] == "push")
        prof  = sum(float(r.get("profit_loss") or 0) for r in grp)
        stake = sum(float(r.get("stake") or 0) for r in grp)
        ndec  = won + lost
        out.append({
            field:        k,
            "n":          len(grp),
            "won":        won,
            "lost":       lost,
            "push":       push,
            "win_rate":   round(won / ndec, 4) if ndec else 0.0,
            "profit":     round(prof, 2),
            "staked":     round(stake, 2),
            "roi":        round(prof / stake, 4) if stake > 0 else 0.0,
        })
    out.sort(key=lambda x: x["profit"], reverse=True)
    return out


# --------------------------------------------------------------------------- #
# Auto-settle helper — looks up realised stat from cached gamelog JSON.       #
# --------------------------------------------------------------------------- #
def _load_actual_from_gamelog(
    player_id: str, stat: str, on_date: str,
    gamelog_dir: Optional[str] = None,
) -> Optional[float]:
    """Look up the player's realised stat for ``on_date`` (ISO yyyy-mm-dd).

    Scans all data/nba/gamelog_<pid>_*.json files for the player and matches
    on the GAME_DATE field (formatted like ``Apr 13, 2025``).
    """
    if not player_id:
        return None
    import glob
    import json
    gamelog_dir = gamelog_dir or os.path.join(PROJECT_DIR, "data", "nba")
    pattern = os.path.join(gamelog_dir, f"gamelog_{player_id}_*.json")
    target = datetime.fromisoformat(on_date).date()
    stat_key = stat.upper()
    for path in glob.glob(pattern):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for g in games:
            d = g.get("GAME_DATE", "")
            try:
                gd = datetime.strptime(d, "%b %d, %Y").date()
            except ValueError:
                continue
            if gd == target and stat_key in g:
                return float(g[stat_key])
    return None


def auto_settle_date(
    on_date: str, gamelog_dir: Optional[str] = None,
) -> List[Dict]:
    """Settle every open bet whose placed_at date == on_date using gamelog actuals."""
    results = []
    target = datetime.fromisoformat(on_date).date()
    for bet in open_bets():
        try:
            placed = datetime.fromisoformat(bet["placed_at"]).date()
        except (ValueError, KeyError):
            continue
        if placed != target:
            continue
        actual = _load_actual_from_gamelog(
            bet.get("player_id", ""), bet["stat"], on_date, gamelog_dir,
        )
        if actual is None:
            results.append({"bet_id": bet["bet_id"], "skipped": "no_actual"})
            continue
        out = settle_bet(bet["bet_id"], actual)
        out["bet_id"] = bet["bet_id"]
        out["actual"] = actual
        results.append(out)
    return results
