"""domains.mlb.ingest_player_stats -- per-PLAYER per-GAME MLB batting + pitching
stats from the free official MLB Stats API (statsapi.mlb.com, no key).

KNOWLEDGE/SUBSTRATE ONLY. Realized POST-GAME player stats (one row per player who
batted or pitched in a game) feeding MLB player-prop rate priors + prop-bet
settlement. LEAK-FREE means these rows MUST be joined AS-OF (strictly BEFORE the
game's first pitch) before feeding any model; a player's own post-game row is never
a feature for that same game. Markets are efficient -- this adds per-player data
depth, not edge. Companion to (and does NOT touch) the team-level ingest_current.py;
it reuses that module's statsapi URL pattern, browser UA, and team-name mapping.

Boxscore shape (confirmed 2026-06-18 against gamePk 823451, PHI vs MIA):
  /game/{gamePk}/boxscore -> teams.{home,away}.{team:{id,name,abbreviation},
  players}. players is a dict keyed "ID{personId}". Each player has
  person:{id,fullName}, position:{abbreviation} (pitchers "P"),
  battingOrder (str "100" or None), and stats:{batting:{...}, pitching:{...}}.
  Batting keys: atBats, hits, totalBases, rbi, runs, homeRuns, doubles, triples,
  baseOnBalls, strikeOuts, stolenBases, hitByPitch. Pitching keys: outs,
  inningsPitched (str "7.0"), strikeOuts, earnedRuns, hits, baseOnBalls,
  battersFaced. A pitcher's strikeOuts/hits/baseOnBalls are stored under distinct
  column names (pitch_strikeOuts/hits_allowed/baseOnBalls_allowed) so they never
  clobber the batting columns.

Network isolation: http_get is INJECTABLE; no network at import time. Public funcs
never raise -- they degrade to []/empty.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_TIMEOUT = 15
_SCHED_URL = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}"
_BOX_URL = "https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"

# Game is OVER with a settled result (leak-free).
_FINAL = "Final"

# Batting stat keys (statsapi name == output column name).
_BAT_FIELDS: tuple = (
    "atBats", "hits", "totalBases", "rbi", "runs", "homeRuns", "doubles",
    "triples", "baseOnBalls", "strikeOuts", "stolenBases", "hitByPitch",
)

# Pitching stat keys -> output column name (renamed where they collide with batting).
_PITCH_FIELDS: Dict[str, str] = {
    "outs": "outs",
    "earnedRuns": "earnedRuns",
    "battersFaced": "battersFaced",
    "strikeOuts": "pitch_strikeOuts",
    "hits": "hits_allowed",
    "baseOnBalls": "baseOnBalls_allowed",
}

# Full set of stat columns the parquet always carries (so a position player gets
# None pitching cols and vice-versa rather than a ragged schema).
_ALL_STAT_COLS: tuple = _BAT_FIELDS + tuple(_PITCH_FIELDS.values()) + ("inningsPitched",)


def _default_http_get(url: str) -> dict:
    """Fetch url via urllib with a browser UA; returns {} on any error."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        log.warning("statsapi fetch failed url=%s err=%s", url, exc)
        return {}


# ---------------------------------------------------------------------------
# Pure parsing helpers (no I/O)
# ---------------------------------------------------------------------------

def _num(raw: object) -> Optional[float]:
    """Numeric value from a stat field; None if missing/unparseable."""
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _innings_to_float(raw: object) -> Optional[float]:
    """inningsPitched string -> outs-correct float. '7.0'->7.0, '6.2'->6.667."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if "." in s:
            whole, frac = s.split(".", 1)
            outs = {"0": 0.0, "1": 1.0 / 3.0, "2": 2.0 / 3.0}.get(frac[:1])
            if outs is None:
                return float(s)
            return float(int(whole)) + outs
        return float(s)
    except (TypeError, ValueError):
        return None


def _batting_order(raw: object) -> Optional[int]:
    """battingOrder '100' -> 1 (the lineup slot); None when absent."""
    if raw in (None, ""):
        return None
    try:
        return int(int(str(raw)) / 100)
    except (TypeError, ValueError):
        return None


def _empty_stats() -> Dict[str, Optional[float]]:
    return {c: None for c in _ALL_STAT_COLS}


def _player_row(pid_key: str, pl: dict, team: str, game_pk: object, date: str) -> Optional[dict]:
    """Build one row from a boxscore player block; None if no batting/pitching."""
    if not isinstance(pl, dict):
        return None
    stats = pl.get("stats") or {}
    batting = stats.get("batting") or {}
    pitching = stats.get("pitching") or {}
    has_bat = bool(batting)
    has_pitch = bool(pitching)
    if not has_bat and not has_pitch:
        return None

    person = pl.get("person") or {}
    position = (pl.get("position") or {}).get("abbreviation", "")
    is_pitcher = has_pitch or position == "P"

    row: dict = {
        "game_pk": game_pk,
        "date": date,
        "team": team,
        "player_id": person.get("id"),
        "player": person.get("fullName", ""),
        "position": position,
        "is_pitcher": is_pitcher,
        "batting_order": _batting_order(pl.get("battingOrder")),
    }
    row.update(_empty_stats())

    if has_bat:
        for f in _BAT_FIELDS:
            row[f] = _num(batting.get(f))
    if has_pitch:
        for src, dst in _PITCH_FIELDS.items():
            row[dst] = _num(pitching.get(src))
        row["inningsPitched"] = _innings_to_float(pitching.get("inningsPitched"))
    return row


def _parse_boxscore(payload: dict, game_pk: object, date: str) -> List[dict]:
    """Per-player rows from a boxscore payload. PURE -- no I/O. One row per player
    with batting OR pitching stats. Returns [] on empty/missing payload.
    """
    if not payload:
        return []
    teams = payload.get("teams")
    if not isinstance(teams, dict):
        return []
    rows: List[dict] = []
    for side in ("home", "away"):
        block = teams.get(side) or {}
        team_info = block.get("team") or {}
        team = team_info.get("abbreviation") or team_info.get("name", "")
        players = block.get("players") or {}
        if not isinstance(players, dict):
            continue
        for pid_key, pl in players.items():
            row = _player_row(pid_key, pl, team, game_pk, date)
            if row is not None:
                rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Fetch layer
# ---------------------------------------------------------------------------

def fetch_game(game_pk: object, http_get: Optional[Callable] = None) -> List[dict]:
    """Fetch + parse per-player stats for one gamePk; [] on error. date left ''."""
    getter = http_get or _default_http_get
    payload = getter(_BOX_URL.format(game_pk=game_pk))
    return _parse_boxscore(payload, game_pk, "")


def fetch_finals_for_date(date: str, http_get: Optional[Callable] = None) -> List[object]:
    """Return gamePk list for FINAL games on a YYYY-MM-DD date; [] on error."""
    getter = http_get or _default_http_get
    payload = getter(_SCHED_URL.format(date=date))
    pks: List[object] = []
    for day in (payload.get("dates") or []):
        for g in (day.get("games") or []):
            state = (g.get("status") or {}).get("abstractGameState", "")
            if state == _FINAL and g.get("gamePk") is not None:
                pks.append(g["gamePk"])
    return pks


# ---------------------------------------------------------------------------
# Ingest range -- writes gitignored parquet
# ---------------------------------------------------------------------------

def ingest_range(
    dates: Sequence[str],
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """Fetch per-player stats for *dates* (YYYY-MM-DD); write/merge parquet.

    One row per player per game; dedup on (game_pk, player_id) keeping last.
    Off-days return 0 finals and are skipped gracefully.
    Realized/post-game only -- NOT a model input without an as-of (pre-first-pitch) join.
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    rows: List[dict] = []

    for date in dates:
        pks = fetch_finals_for_date(date, http_get=getter)
        log.info("date=%s finals=%d", date, len(pks))
        for pk in pks:
            payload = getter(_BOX_URL.format(game_pk=pk))
            game_rows = _parse_boxscore(payload, pk, date)
            rows.extend(game_rows)
            if not game_rows:
                log.debug("game_pk=%s: no player rows", pk)

    new_df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not new_df.empty and "date" in new_df.columns:
        new_df["date"] = pd.to_datetime(new_df["date"], format="mixed", errors="coerce")
    if out.exists() and not new_df.empty:
        try:
            existing = pd.read_parquet(out)
            if "date" in existing.columns:
                existing["date"] = pd.to_datetime(existing["date"], format="mixed", errors="coerce")
            new_df = (
                pd.concat([existing, new_df], ignore_index=True)
                .drop_duplicates(subset=["game_pk", "player_id"], keep="last")
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("S95: unreadable existing parquet %s" % out) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    if not new_df.empty:
        write_parquet_atomic(new_df, out)
    log.info("Wrote %d player rows to %s", len(new_df), out)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ingest MLB per-player game stats.")
    parser.add_argument("--dates", nargs="+", default=[dt.date.today().strftime("%Y-%m-%d")])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(f"Done: {ingest_range(args.dates, out_path=args.out)}")


if __name__ == "__main__":
    _main()
