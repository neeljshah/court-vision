"""bet_db.py — SQLite-backed bankroll + bet ledger for CourtVision.

Single file DAL on top of stdlib sqlite3.  WAL mode, connection-per-call,
no SQLAlchemy.  Thread / multi-process safe via WAL + busy-timeout.

DB path default: database/courtvision.db (relative to PROJECT_DIR).
Override via BET_DB_PATH env var or the `path` constructor arg.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_DB  = str(PROJECT_DIR / "database" / "courtvision.db")

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS bets (
    bet_id          TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    date            TEXT NOT NULL,
    game_id         TEXT,
    player_id       TEXT,
    player_name     TEXT NOT NULL,
    stat            TEXT NOT NULL,
    line            REAL NOT NULL,
    side            TEXT NOT NULL,
    book            TEXT NOT NULL,
    odds            INTEGER NOT NULL,
    stake           REAL NOT NULL,
    kelly_size      REAL,
    model_ev_pct    REAL,
    model_p_hit     REAL,
    status          TEXT NOT NULL DEFAULT 'pending',
    settled_at      TEXT,
    closing_line    REAL,
    closing_odds    INTEGER,
    actual_stat     REAL,
    pnl             REAL,
    clv_bps         INTEGER,
    source          TEXT,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_bets_date        ON bets(date);
CREATE INDEX IF NOT EXISTS idx_bets_status      ON bets(status);
CREATE INDEX IF NOT EXISTS idx_bets_player_stat ON bets(player_name, stat);

CREATE TABLE IF NOT EXISTS bankroll_state (
    state_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    bankroll    REAL NOT NULL,
    open_stake  REAL NOT NULL,
    daily_pnl   REAL,
    daily_stake REAL,
    notes       TEXT
);

CREATE INDEX IF NOT EXISTS idx_bankroll_time ON bankroll_state(recorded_at);

CREATE TABLE IF NOT EXISTS clv_summary_daily (
    date        TEXT PRIMARY KEY,
    n_bets      INTEGER NOT NULL,
    avg_clv_bps REAL NOT NULL,
    win_pct     REAL,
    roi_pct     REAL,
    total_stake REAL,
    total_pnl   REAL,
    computed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settled_actuals (
    game_id     TEXT NOT NULL,
    player_id   TEXT NOT NULL,
    stat        TEXT NOT NULL,
    actual_value REAL NOT NULL,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (game_id, player_id, stat)
);
"""

_BET_COLS = (
    "bet_id", "created_at", "date", "game_id", "player_id", "player_name",
    "stat", "line", "side", "book", "odds", "stake", "kelly_size",
    "model_ev_pct", "model_p_hit", "status", "settled_at", "closing_line",
    "closing_odds", "actual_stat", "pnl", "clv_bps", "source", "notes",
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect(path: str) -> sqlite3.Connection:
    """Return a connection with WAL mode + 5-second busy timeout."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


class BetDB:
    """Thin DAL over the CourtVision SQLite ledger."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or os.environ.get("BET_DB_PATH", _DEFAULT_DB)
        self._ensure_schema()

    # ── schema ────────────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        """Idempotently create all tables + indexes.

        Also seeds a default $100 paper-trade bankroll on first run so the
        /api/bankroll endpoint never returns $0 on a fresh install.
        """
        with _connect(self.path) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()
            # Seed only when the table is completely empty (first-ever run).
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM bankroll_state"
            ).fetchone()
            if row and row["n"] == 0:
                conn.execute(
                    "INSERT INTO bankroll_state "
                    "  (recorded_at, bankroll, open_stake, notes) "
                    "VALUES (?, ?, ?, ?)",
                    (_now_utc(), 100.0, 0.0, "default paper-trade bankroll"),
                )
                conn.commit()

    # ── bet writes ────────────────────────────────────────────────────────────

    def insert_bet(self, bet: Dict[str, Any]) -> str:
        """Insert a new bet row; return the bet_id.

        Auto-generates bet_id (UUID4) and created_at if not supplied.
        Required keys: player_name, stat, line, side, book, odds, stake.
        Optional: date (defaults to today UTC), status (defaults to 'pending').
        """
        now    = _now_utc()
        bet_id = bet.get("bet_id") or str(uuid.uuid4())
        date   = bet.get("date") or now[:10]
        status = bet.get("status") or "pending"

        row = {
            "bet_id":       bet_id,
            "created_at":   bet.get("created_at") or now,
            "date":         date,
            "game_id":      bet.get("game_id"),
            "player_id":    bet.get("player_id"),
            "player_name":  str(bet.get("player_name") or bet.get("player") or ""),
            "stat":         str(bet.get("stat") or ""),
            "line":         float(bet.get("line", 0.0)),
            "side":         str(bet.get("side") or "").lower(),
            "book":         str(bet.get("book") or ""),
            "odds":         int(bet.get("odds") or bet.get("american_odds") or 0),
            "stake":        float(bet.get("stake", 0.0)),
            "kelly_size":   _maybe_float(bet.get("kelly_size") or bet.get("kelly_pct")),
            "model_ev_pct": _maybe_float(bet.get("model_ev_pct") or bet.get("model_edge")),
            "model_p_hit":  _maybe_float(bet.get("model_p_hit") or bet.get("model_prob")),
            "status":       status,
            "settled_at":   bet.get("settled_at"),
            "closing_line": _maybe_float(bet.get("closing_line")),
            "closing_odds": _maybe_int(bet.get("closing_odds")),
            "actual_stat":  _maybe_float(bet.get("actual_stat")),
            "pnl":          _maybe_float(bet.get("pnl") or bet.get("profit_loss")),
            "clv_bps":      _maybe_int(bet.get("clv_bps")),
            "source":       bet.get("source"),
            "notes":        bet.get("notes"),
        }

        cols   = ", ".join(row.keys())
        places = ", ".join("?" for _ in row)
        sql    = f"INSERT OR IGNORE INTO bets ({cols}) VALUES ({places})"
        with _connect(self.path) as conn:
            conn.execute(sql, list(row.values()))
            conn.commit()
        return bet_id

    def settle_bet(
        self,
        bet_id: str,
        *,
        status: str,
        actual_stat: Optional[float],
        pnl: float,
        clv_bps: Optional[int] = None,
        closing_line: Optional[float] = None,
        closing_odds: Optional[int] = None,
    ) -> None:
        """Update a bet's settled fields."""
        sql = """
            UPDATE bets
               SET status       = ?,
                   settled_at   = ?,
                   actual_stat  = ?,
                   pnl          = ?,
                   clv_bps      = ?,
                   closing_line = ?,
                   closing_odds = ?
             WHERE bet_id = ?
        """
        with _connect(self.path) as conn:
            conn.execute(sql, (
                status, _now_utc(), actual_stat,
                pnl, clv_bps, closing_line, closing_odds,
                bet_id,
            ))
            conn.commit()

    # ── queries ───────────────────────────────────────────────────────────────

    def get_bet(self, bet_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single bet by ID; None if not found."""
        with _connect(self.path) as conn:
            row = conn.execute(
                "SELECT * FROM bets WHERE bet_id = ?", (bet_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_bets(
        self,
        *,
        date: Optional[str]   = None,
        status: Optional[str] = None,
        player: Optional[str] = None,
        limit: int            = 100,
    ) -> List[Dict[str, Any]]:
        """Filtered list of bets ordered by created_at DESC."""
        clauses: List[str] = []
        params:  List[Any] = []
        if date:
            clauses.append("date = ?")
            params.append(date)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if player:
            clauses.append("player_name LIKE ?")
            params.append(f"%{player}%")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql   = f"SELECT * FROM bets {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with _connect(self.path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def recent_bets(self, n: int = 20) -> List[Dict[str, Any]]:
        """Last N bets across all dates (for the bet-history widget)."""
        with _connect(self.path) as conn:
            rows = conn.execute(
                "SELECT * FROM bets ORDER BY created_at DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── bankroll ──────────────────────────────────────────────────────────────

    def current_bankroll(self) -> float:
        """Return the latest bankroll from bankroll_state, or 0.0."""
        with _connect(self.path) as conn:
            row = conn.execute(
                "SELECT bankroll FROM bankroll_state ORDER BY state_id DESC LIMIT 1"
            ).fetchone()
        return float(row["bankroll"]) if row else 0.0

    def update_bankroll(self, new_value: float, *, notes: str = "") -> None:
        """Insert a new bankroll_state snapshot."""
        open_stake  = self.open_bet_value()
        today       = _now_utc()[:10]
        daily_pnl   = self._daily_pnl(today)
        daily_stake = self._daily_stake(today)
        sql = """
            INSERT INTO bankroll_state
                (recorded_at, bankroll, open_stake, daily_pnl, daily_stake, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        with _connect(self.path) as conn:
            conn.execute(sql, (_now_utc(), new_value, open_stake,
                               daily_pnl, daily_stake, notes))
            conn.commit()

    def open_bet_value(self) -> float:
        """Sum stake of all 'pending' bets — capital currently at risk."""
        with _connect(self.path) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(stake), 0.0) AS s FROM bets WHERE status = 'pending'"
            ).fetchone()
        return float(row["s"]) if row else 0.0

    # ── analytics ────────────────────────────────────────────────────────────

    def daily_summary(self, date: str) -> Dict[str, Any]:
        """Return per-day aggregate: n_bets, stakes, pnl, roi, avg_clv."""
        sql = """
            SELECT
                COUNT(*)                                              AS n_bets,
                COALESCE(SUM(stake), 0.0)                            AS total_stake,
                COALESCE(SUM(CASE WHEN pnl IS NOT NULL THEN pnl END), 0.0) AS total_pnl,
                COALESCE(AVG(CASE WHEN clv_bps IS NOT NULL THEN clv_bps END), 0.0) AS avg_clv_bps,
                COALESCE(SUM(CASE WHEN status='won' THEN 1 ELSE 0 END), 0) AS n_won
            FROM bets
            WHERE date = ?
        """
        with _connect(self.path) as conn:
            row = conn.execute(sql, (date,)).fetchone()
        if not row or row["n_bets"] == 0:
            return {"date": date, "n_bets": 0, "total_stake": 0.0,
                    "total_pnl": 0.0, "roi_pct": 0.0, "avg_clv_bps": 0.0, "win_pct": 0.0}
        n          = row["n_bets"]
        ts, tp     = row["total_stake"], row["total_pnl"]
        roi_pct    = round(100.0 * tp / ts, 2) if ts else 0.0
        win_pct    = round(100.0 * row["n_won"] / n, 2) if n else 0.0
        return {
            "date":         date,
            "n_bets":       n,
            "total_stake":  round(ts, 2),
            "total_pnl":    round(tp, 2),
            "roi_pct":      roi_pct,
            "avg_clv_bps":  round(row["avg_clv_bps"], 1),
            "win_pct":      win_pct,
        }

    def daily_pnl_series(self, days: int = 30) -> List[Dict[str, Any]]:
        """One aggregate row per date for the last `days` days (charting)."""
        sql = """
            SELECT date,
                   COUNT(*)                          AS n_bets,
                   COALESCE(SUM(stake), 0.0)         AS total_stake,
                   COALESCE(SUM(pnl),  0.0)          AS total_pnl
            FROM bets
            WHERE date >= date('now', ?)
            GROUP BY date
            ORDER BY date ASC
        """
        offset = f"-{days} days"
        with _connect(self.path) as conn:
            rows = conn.execute(sql, (offset,)).fetchall()
        out = []
        for r in rows:
            ts, tp = r["total_stake"], r["total_pnl"]
            roi = round(100.0 * tp / ts, 2) if ts else 0.0
            out.append({"date": r["date"], "n_bets": r["n_bets"],
                        "total_stake": ts, "total_pnl": tp, "roi_pct": roi})
        return out

    def high_water_mark(self, days: int = 90) -> float:
        """Peak bankroll over the last `days` days."""
        sql = """
            SELECT COALESCE(MAX(bankroll), 0.0) AS hwm
            FROM bankroll_state
            WHERE recorded_at >= datetime('now', ?)
        """
        with _connect(self.path) as conn:
            row = conn.execute(sql, (f"-{days} days",)).fetchone()
        return float(row["hwm"]) if row else 0.0

    def drawdown_pct(self, days: int = 30) -> float:
        """(HWM − current) / HWM × 100 over the last `days` days."""
        hwm     = self.high_water_mark(days)
        current = self.current_bankroll()
        if hwm <= 0:
            return 0.0
        return round(max(0.0, (hwm - current) / hwm * 100.0), 2)

    # ── CLV daily cache ───────────────────────────────────────────────────────

    def upsert_clv_daily(self, date: str, row: Dict[str, Any]) -> None:
        """Insert or replace a row in clv_summary_daily."""
        sql = """
            INSERT OR REPLACE INTO clv_summary_daily
                (date, n_bets, avg_clv_bps, win_pct, roi_pct,
                 total_stake, total_pnl, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        with _connect(self.path) as conn:
            conn.execute(sql, (
                date,
                int(row.get("n_bets", 0)),
                float(row.get("avg_clv_bps", 0.0)),
                _maybe_float(row.get("win_pct")),
                _maybe_float(row.get("roi_pct")),
                _maybe_float(row.get("total_stake")),
                _maybe_float(row.get("total_pnl")),
                _now_utc(),
            ))
            conn.commit()

    # ── actuals cache ─────────────────────────────────────────────────────────

    def upsert_actual(self, game_id: str, player_id: str,
                      stat: str, value: float) -> None:
        """Cache a player's actual stat outcome for a game."""
        sql = """
            INSERT OR REPLACE INTO settled_actuals
                (game_id, player_id, stat, actual_value, fetched_at)
            VALUES (?, ?, ?, ?, ?)
        """
        with _connect(self.path) as conn:
            conn.execute(sql, (game_id, player_id, stat, value, _now_utc()))
            conn.commit()

    def get_actual(self, game_id: str, player_id: str,
                   stat: str) -> Optional[float]:
        with _connect(self.path) as conn:
            row = conn.execute(
                "SELECT actual_value FROM settled_actuals "
                "WHERE game_id=? AND player_id=? AND stat=?",
                (game_id, player_id, stat),
            ).fetchone()
        return float(row["actual_value"]) if row else None

    # ── private helpers ───────────────────────────────────────────────────────

    def _daily_pnl(self, date: str) -> float:
        with _connect(self.path) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(pnl),0.0) AS s FROM bets WHERE date=?",
                (date,),
            ).fetchone()
        return float(row["s"]) if row else 0.0

    def _daily_stake(self, date: str) -> float:
        with _connect(self.path) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(stake),0.0) AS s FROM bets WHERE date=?",
                (date,),
            ).fetchone()
        return float(row["s"]) if row else 0.0


# ── helpers ────────────────────────────────────────────────────────────────────

def _maybe_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _maybe_int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
