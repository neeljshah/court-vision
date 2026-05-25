"""snap_action_network_bets.py - daily Action Network pct_bets / pct_money +
opening vs current line snapshotter (tier3-12, loop 5).

Why
---
T2-C in `scripts/_results/in_game_gaps_v1.md` (cycle 89f) calls out reverse
line movement (RLM) as the strongest pre-game sharp-money signal we can
exploit. The mechanism: when the LINE moves AGAINST the public bet majority,
sharp dollars are on the other side. To probe whether that translates to
prop-level residual ROI we need a time-series of (line, pct_bets, pct_money)
captured at multiple times per game-day, then evaluated against the final
stat outcome.

Distinct from existing infra:
  * `scripts/poll_line_movement.py` (cycle 88g) - DK/FD line-only diff log,
    keyed off transient snapshots. No public_bets / public_money columns.
  * `src/data/action_network.py` - 15-min-TTL CACHE of the AN endpoint,
    optimised for one-shot per-player lookup. Caches per-day, NOT a
    time-series ledger.
  * `scripts/fetch_live_prop_lines.py` (tier1-1) - permanent DK/FD line
    ledger, no public-bet% data at all.

This script is the AN-specific RLM accumulator: per-poll append of every
prop's (pct_bets_over, pct_money_over, line_opening, line_current,
rlm_flag) to a date+HHMM CSV so we can compute residual ROI after 30+
game-days of paired snapshot vs final-stat data.

Endpoint
--------
    GET https://api.actionnetwork.com/web/v2/scoreboard/nba
        ?period=game
        &bookIds=15           (DraftKings; AN's most-populated prop book)

The endpoint is unauthenticated (no login). Each game in the response carries
a markets[15] object with game-level moneyline/spread/total; per-prop
percentages live on the per-game `/web/v2/games/{id}/props` endpoint (already
verified live in `src.data.action_network.refresh_action_network`).

RLM rule (per prop)
-------------------
    line_move_dir = sign(line_current - line_opening)   # +1 / 0 / -1
    side_with_more_money = "over" if pct_money_over > pct_bets_over else "under"
    rlm = True iff:
        abs(pct_money_over - pct_bets_over) >= 5   (5pp threshold per
                                                    sportscapping research)
        AND line_move_dir != 0
        AND line moved AWAY from the side_with_more_money

Concretely: if money is on the OVER (pct_money_over > pct_bets_over) and the
LINE moved DOWN (line_current < line_opening, making the OVER easier to hit
is the WRONG direction here - sharps would want the line UP if they liked
the over, BUT if the book is shifting it DOWN despite sharp money on the
over, that's evidence the book respects the sharp move and is BAITING under
bettors). Standard sportsbook convention: when sharps hammer the over, the
book RAISES the line. So RLM occurs when the line moves AGAINST that:
sharps on over but line down, or sharps on under but line up.

CLI
---
    python scripts/snap_action_network_bets.py --once
    python scripts/snap_action_network_bets.py --interval-min 15
    python scripts/snap_action_network_bets.py --date 2026-05-24 --once
"""
from __future__ import annotations

import argparse
import csv
import glob
import logging
import os
import sys
import time
from datetime import date as _date
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger("snap_action_network_bets")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] %(message)s",
                                       datefmt="%Y-%m-%dT%H:%M:%S"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

# Endpoint - see module docstring for rationale.
_AN_SCOREBOARD = ("https://api.actionnetwork.com/web/v2/scoreboard/nba")
_AN_GAME_PROPS = "https://api.actionnetwork.com/web/v2/games/{game_id}/props"
_BOOK_ID = "15"   # DraftKings on Action Network

# RLM threshold: money% must exceed bets% by at least this many pp on one side
# AND the line must have moved AGAINST that side.
_RLM_MONEY_VS_BETS_MIN_PP = 5.0

# Polite throttle between per-game prop fetches.
_INTER_GAME_PAUSE_SEC = 1.0

_OUT_DIR = os.path.join(PROJECT_DIR, "data", "action_bets")

# Canonical schema. Order matters for human-eye scans but downstream parsers
# read by name.
_FIELDS = [
    "captured_at", "game_id", "player_id", "player", "stat",
    "line_opening", "line_current", "pct_bets_over", "pct_money_over",
    "line_move_dir", "rlm_flag",
]

# Stat -> Action Network player_props key (mirrors src/data/action_network.py).
_STAT_TO_AN_PROP: Dict[str, str] = {
    "pts":  "core_bet_type_27_points",
    "reb":  "core_bet_type_23_rebounds",
    "ast":  "core_bet_type_26_assists",
    "fg3m": "core_bet_type_21_3fgm",
    "stl":  "core_bet_type_24_steals",
    "blk":  "core_bet_type_25_blocks",
    "tov":  "core_bet_type_580_turnovers",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.actionnetwork.com/",
}


# ── time helpers ──────────────────────────────────────────────────────────────

def _today_iso() -> str:
    return _date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _stamp_hhmm() -> str:
    return datetime.now().strftime("%H%M")


# ── opening-line ledger (intra-day persistence) ──────────────────────────────

def _opening_line_path(date_str: str, out_dir: str = _OUT_DIR) -> str:
    """Per-date opening-line ledger - the FIRST line seen for a (game,player,
    stat) tuple on that day. Used to compute line_move_dir across polls."""
    return os.path.join(out_dir, f"{date_str}_openings.csv")


def load_openings(date_str: str, out_dir: str = _OUT_DIR
                  ) -> Dict[Tuple[str, str, str], float]:
    """Return {(game_id, player_id_or_name, stat): opening_line} for date."""
    path = _opening_line_path(date_str, out_dir)
    out: Dict[Tuple[str, str, str], float] = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    key = (str(r.get("game_id", "") or ""),
                           str(r.get("player_id_or_name", "") or ""),
                           str(r.get("stat", "") or ""))
                    out[key] = float(r.get("line_opening", "nan"))
                except (TypeError, ValueError):
                    continue
    except Exception as e:    # noqa: BLE001
        log.warning("could not load openings ledger %s: %s", path, e)
    return out


def save_openings(openings: Dict[Tuple[str, str, str], float],
                  date_str: str, out_dir: str = _OUT_DIR) -> str:
    """Persist the opening-line ledger (overwrites). Returns path."""
    os.makedirs(out_dir, exist_ok=True)
    path = _opening_line_path(date_str, out_dir)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["game_id", "player_id_or_name", "stat", "line_opening"])
        for (gid, pid, stat), line in sorted(openings.items()):
            w.writerow([gid, pid, stat, f"{line:g}"])
    return path


# ── fetch ─────────────────────────────────────────────────────────────────────

class EndpointUnavailable(Exception):
    """Raised when AN scoreboard returns 403 / 404 / 5xx so the caller can
    log a clean message and exit gracefully (offseason or schema drift)."""


def fetch_scoreboard(date_str: str, fetch_fn=None) -> List[dict]:
    """Hit AN's v2 scoreboard for date_str. Returns list of game dicts.

    `fetch_fn(url, params, headers) -> dict` is injectable for tests; in
    production it imports `requests` lazily so the module imports cleanly
    in environments where requests is absent.

    Raises `EndpointUnavailable` on 403/404 (schema drift) so the daemon
    can log a one-shot warning and back off. Returns [] for empty days
    (offseason) without raising.
    """
    # AN expects YYYYMMDD with no dashes for the date query.
    date_compact = date_str.replace("-", "")
    params = {"period": "game", "bookIds": _BOOK_ID, "date": date_compact}

    if fetch_fn is None:
        try:
            import requests
        except ImportError:
            log.error("requests not installed - cannot hit AN")
            raise EndpointUnavailable("requests not installed")

        def _real_fetch(url, params, headers):
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code in (403, 404):
                raise EndpointUnavailable(
                    f"AN scoreboard returned {r.status_code} - endpoint may "
                    f"have changed. Try WebSearch 'action network v2 "
                    f"scoreboard nba endpoint' to refresh URL."
                )
            r.raise_for_status()
            return r.json()
        fetch_fn = _real_fetch

    try:
        payload = fetch_fn(_AN_SCOREBOARD, params, _HEADERS)
    except EndpointUnavailable:
        raise
    except Exception as e:    # noqa: BLE001
        # Treat network/transient errors as empty - don't crash daemons.
        log.warning("scoreboard fetch failed: %s", e)
        return []

    if not isinstance(payload, dict):
        return []
    return payload.get("games", []) or []


def fetch_game_props(game_id: int, fetch_fn=None) -> dict:
    """Hit AN's per-game props endpoint. Returns the full JSON payload,
    or {} on transient failure (caller handles empty)."""
    url = _AN_GAME_PROPS.format(game_id=game_id)
    if fetch_fn is None:
        try:
            import requests
        except ImportError:
            return {}

        def _real_fetch(url, params, headers):
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code in (403, 404):
                raise EndpointUnavailable(
                    f"AN props returned {r.status_code} for game {game_id}"
                )
            r.raise_for_status()
            return r.json()
        fetch_fn = _real_fetch

    try:
        return fetch_fn(url, None, _HEADERS) or {}
    except EndpointUnavailable:
        raise
    except Exception as e:    # noqa: BLE001
        log.warning("props fetch failed for game %s: %s", game_id, e)
        return {}


# ── parse ─────────────────────────────────────────────────────────────────────

def _extract_over_pct(outcomes: List[dict]) -> Tuple[Optional[float],
                                                       Optional[float],
                                                       Optional[float]]:
    """From a list of outcome dicts (one over / one under), pull the OVER's
    tickets% + money% + line value. Returns (line, pct_bets_over,
    pct_money_over) - any element may be None when missing.
    """
    line_val: Optional[float] = None
    pct_bets: Optional[float] = None
    pct_money: Optional[float] = None
    for o in outcomes:
        val = o.get("value")
        if val is not None and line_val is None:
            try:
                line_val = float(val)
            except (TypeError, ValueError):
                pass
        side = (o.get("side") or "").lower()
        if side == "over":
            bi = o.get("bet_info", {}) or {}
            tp = (bi.get("tickets") or {}).get("percent")
            mp = (bi.get("money") or {}).get("percent")
            try:
                pct_bets = float(tp) if tp is not None else None
            except (TypeError, ValueError):
                pct_bets = None
            try:
                pct_money = float(mp) if mp is not None else None
            except (TypeError, ValueError):
                pct_money = None
    return line_val, pct_bets, pct_money


def compute_rlm(line_opening: Optional[float], line_current: Optional[float],
                pct_bets_over: Optional[float],
                pct_money_over: Optional[float]) -> Tuple[int, bool]:
    """Compute (line_move_dir, rlm_flag) for one prop.

    line_move_dir: +1 if line moved up, -1 if down, 0 if unchanged/missing.
    rlm_flag: True iff money/bets asymmetry >= _RLM_MONEY_VS_BETS_MIN_PP
        AND the line moved AGAINST the side with more money. The "convention"
        is sportsbooks RAISE the line when sharp money is on the OVER, so
        an opposing move is the RLM signal:
            * money on OVER  + line moved DOWN  -> RLM
            * money on UNDER + line moved UP    -> RLM
    """
    if (line_opening is None or line_current is None
            or pct_bets_over is None or pct_money_over is None):
        return 0, False
    delta = line_current - line_opening
    if abs(delta) < 1e-9:
        return 0, False
    line_move_dir = 1 if delta > 0 else -1
    money_minus_bets = pct_money_over - pct_bets_over
    if abs(money_minus_bets) < _RLM_MONEY_VS_BETS_MIN_PP:
        return line_move_dir, False
    money_on_over = money_minus_bets > 0
    # RLM when line moved AGAINST side with money.
    if money_on_over and line_move_dir < 0:
        return line_move_dir, True
    if (not money_on_over) and line_move_dir > 0:
        return line_move_dir, True
    return line_move_dir, False


def parse_props_payload(game_id: int, props_payload: dict,
                        openings: Dict[Tuple[str, str, str], float],
                        captured_at: str) -> List[dict]:
    """Convert one game's `/props` payload into canonical schema rows.

    `openings` is mutated in place: every (game_id, player_id_or_name, stat)
    not yet seen on this date is recorded as its opening line. This means
    the FIRST poll of the day establishes openings and subsequent polls
    diff against them.
    """
    rows: List[dict] = []
    if not isinstance(props_payload, dict):
        return rows
    player_props = props_payload.get("player_props", {}) or {}
    players_idx  = props_payload.get("players", {}) or {}

    def _player_name(pid) -> str:
        rec = players_idx.get(str(pid)) or players_idx.get(pid) or {}
        return (rec.get("full_name") or rec.get("player_full_name")
                or rec.get("name") or "")

    for stat, an_key in _STAT_TO_AN_PROP.items():
        entries = player_props.get(an_key, []) or []
        for entry in entries:
            pid = entry.get("player_id")
            player = _player_name(pid)
            if not player:
                continue
            lines_by_book = entry.get("lines", {}) or {}
            # Prefer the DraftKings (15) book; fall back to first available.
            book = _BOOK_ID if _BOOK_ID in lines_by_book else next(
                iter(lines_by_book), None)
            if not book:
                continue
            outcomes = lines_by_book[book] or []
            line_current, pct_bets, pct_money = _extract_over_pct(outcomes)
            if line_current is None:
                continue
            pid_key = str(pid or player).lower().strip()
            key = (str(game_id), pid_key, stat)
            opening = openings.get(key)
            if opening is None:
                openings[key] = line_current
                opening = line_current
            line_move_dir, rlm = compute_rlm(opening, line_current,
                                              pct_bets, pct_money)
            rows.append({
                "captured_at":     captured_at,
                "game_id":         str(game_id),
                "player_id":       str(pid or ""),
                "player":          player,
                "stat":            stat,
                "line_opening":    f"{opening:g}",
                "line_current":    f"{line_current:g}",
                "pct_bets_over":   ("" if pct_bets  is None
                                       else f"{pct_bets:g}"),
                "pct_money_over":  ("" if pct_money is None
                                       else f"{pct_money:g}"),
                "line_move_dir":   str(line_move_dir),
                "rlm_flag":        "Y" if rlm else "N",
            })
    return rows


# ── CSV write ─────────────────────────────────────────────────────────────────

def write_snapshot_csv(rows: List[dict], date_str: str, hhmm: str,
                        out_dir: str = _OUT_DIR) -> str:
    """Append rows to `data/action_bets/<date>_<HHMM>.csv`. Always writes
    the file (even if rows is empty) so daemon runs are auditable."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{date_str}_{hhmm}.csv")
    new_file = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in _FIELDS})
    return path


# ── orchestration ─────────────────────────────────────────────────────────────

def snap_once(date_str: Optional[str] = None,
              hhmm: Optional[str] = None,
              out_dir: str = _OUT_DIR,
              scoreboard_fn=None,
              props_fn=None,
              sleep_fn=time.sleep,
              ) -> Tuple[str, List[dict]]:
    """One poll. Returns (out_csv_path, rows). Injectable fetchers for tests.

    On empty schedule (offseason / no games today) writes a header-only CSV
    and returns ([], path).
    On endpoint-unavailable: logs a clear WebSearch hint, writes an empty
    CSV, returns ([], path) - does NOT crash.
    """
    date_str = date_str or _today_iso()
    hhmm     = hhmm or _stamp_hhmm()
    captured_at = _now_iso()

    try:
        games = fetch_scoreboard(date_str, fetch_fn=scoreboard_fn)
    except EndpointUnavailable as e:
        log.error("ENDPOINT UNAVAILABLE: %s", e)
        log.error("  Suggest: WebSearch 'action network v2 scoreboard nba "
                  "endpoint' to refresh URL.")
        path = write_snapshot_csv([], date_str, hhmm, out_dir)
        return path, []

    if not games:
        log.info("no games on %s (offseason or empty schedule)", date_str)
        path = write_snapshot_csv([], date_str, hhmm, out_dir)
        return path, []

    openings = load_openings(date_str, out_dir)
    all_rows: List[dict] = []
    for i, game in enumerate(games):
        gid = game.get("id")
        if not gid:
            continue
        if i > 0:
            sleep_fn(_INTER_GAME_PAUSE_SEC)
        try:
            props_payload = fetch_game_props(int(gid), fetch_fn=props_fn)
        except EndpointUnavailable as e:
            log.warning("props endpoint unavailable for game %s: %s",
                        gid, e)
            continue
        rows = parse_props_payload(int(gid), props_payload, openings,
                                    captured_at)
        all_rows.extend(rows)

    save_openings(openings, date_str, out_dir)
    path = write_snapshot_csv(all_rows, date_str, hhmm, out_dir)
    n_rlm = sum(1 for r in all_rows if r.get("rlm_flag") == "Y")
    log.info("snap done: %d props, %d RLM-flagged -> %s",
             len(all_rows), n_rlm, path)
    return path, all_rows


def run_daemon(interval_min: int,
               out_dir: str = _OUT_DIR,
               sleep_fn=time.sleep,
               max_iters: Optional[int] = None,
               clock_fn=_today_iso,
               ) -> int:
    """Loop forever (or max_iters times for tests). Returns iters run.
    Never lets a single failure kill the loop."""
    interval_sec = max(1, int(interval_min * 60))
    i = 0
    while True:
        try:
            date_str = clock_fn()
            snap_once(date_str=date_str, out_dir=out_dir)
        except Exception as e:    # noqa: BLE001
            log.error("snap_once failed: %s", e)
        i += 1
        if max_iters is not None and i >= max_iters:
            return i
        sleep_fn(interval_sec)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Action Network DraftKings prop bet% + line snapshotter "
                    "(RLM signal accumulation)."
    )
    ap.add_argument("--date", default=None,
                    help="Schedule date YYYY-MM-DD (default: today).")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true",
                       help="Single snapshot + exit (default mode).")
    mode.add_argument("--interval-min", type=int, default=None,
                       help="Daemon mode: snap every N minutes.")
    args = ap.parse_args(argv)

    if args.interval_min:
        log.info("daemon mode: snap every %d min  (Ctrl-C to stop)",
                 args.interval_min)
        run_daemon(args.interval_min)
        return 0
    snap_once(date_str=args.date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
