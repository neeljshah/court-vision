"""nba_lineup_daemon.py - R17 J1.

Real-time NBA starting-lineup scraper / change-detector / bet-killer alerter.

WHY
====
Starting lineups drop ~1 hr pre-tip on RotoWire / NBA.com / ESPN.  Late
scratches *destroy* prop edges (e.g. if Keldon Johnson is OUT, his
rebounding OVER 3.5 ticket is line_killed and should be voided BEFORE
placement).  This daemon polls every --interval-sec, diffs against the
prior snapshot, persists per-slate JSON, and emits URGENT alerts +
ledger updates when a player on tonight's slate bet list disappears
from the projected starting five.

# R19_L3 heartbeat import (sys.path bootstrap so daemons launched via
# 'python -u scripts/<name>.py' can still find src.monitor at the project root).
try:
    import os as _r19_os, sys as _r19_sys
    _r19_root = _r19_os.path.dirname(_r19_os.path.dirname(_r19_os.path.abspath(__file__)))
    if _r19_root not in _r19_sys.path:
        _r19_sys.path.insert(0, _r19_root)
    from src.monitor.daemon_heartbeat import write_heartbeat as _r19_hb
except Exception:
    def _r19_hb(_name):
        return False


SOURCE
======
We tried (in order):
  1. NBA.com /stats/scoreboardv3       -> requires WAF bypass, no starters
  2. NBA.com /stats/leaguelineupdetails -> historical only, no projections
  3. RotoWire NBA starting lineup page -> WORKS, returns PG/SG/SF/PF/C
     with status (Confirmed/Expected/Projected) + injury tag + play_pct
  4. ESPN NBA lineups page             -> fallback if RotoWire 5xx

RotoWire is the chosen primary - it's the source ESPN/NBA aggregators
use anyway, free, no auth, parses cleanly via the regex parser already
in scripts/fetch_lineups.py.  We reuse that parser; this daemon adds:

  - polling loop with configurable interval
  - canonical schema (one starter per row, with slot + status)
  - persistence: data/lineups/<isodate>.json (one file per slate, updated in place)
  - diff vs prior snapshot -> change-event log
  - alert hook: if a player in data/cache/probe_R15_tonight_slate_bets.json
                is no longer a starter, write URGENT line to
                vault/Improvements/lineup_alerts.md AND mark pending bets
                in data/pnl_ledger.csv as status=line_killed.

CLI
===
    python scripts/nba_lineup_daemon.py --interval-sec 60
    python scripts/nba_lineup_daemon.py --once          # one fetch then exit
    python scripts/nba_lineup_daemon.py --smoke         # one fetch + pretty print starters
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, date as _date, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Reuse the battle-tested rotowire parser from fetch_lineups.py
from scripts.fetch_lineups import (   # noqa: E402  (path insertion above)
    fetch_html as _rw_fetch_html,
    parse_html as _rw_parse_html,
)

# ── paths ─────────────────────────────────────────────────────────────────────
LINEUPS_DIR = os.path.join(PROJECT_DIR, "data", "lineups")
ALERTS_MD = os.path.join(PROJECT_DIR, "vault", "Improvements", "lineup_alerts.md")
SLATE_BETS_JSON = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R15_tonight_slate_bets.json"
)
PNL_LEDGER_CSV = os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv")
DAEMON_LOG = os.path.join(
    PROJECT_DIR, "vault", "Improvements", "nba_lineup_daemon.log"
)

# ── logging ───────────────────────────────────────────────────────────────────
_LOG_FMT = "%(asctime)s %(levelname)s [lineup_daemon] %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FMT)
log = logging.getLogger("nba_lineup_daemon")

# Canonical slot order RotoWire uses
_SLOT_ORDER = ("PG", "SG", "SF", "PF", "C")
_STATUS_MAP = {
    "Confirmed": "CONFIRMED",
    "Expected":  "PROJECTED",
    "Projected": "PROJECTED",
    "Unknown":   "PROJECTED",
}
_QUESTIONABLE_TAGS = {"Ques", "DTD", "GTD", "Prob", "Probable"}
_OUT_TAGS = {"Out", "OUT", "INJ", "SUSP", "DNP"}


# ── normalisation: rotowire payload -> canonical row schema ───────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_games(games: List[Dict[str, Any]],
                    captured_at: Optional[str] = None) -> List[Dict[str, Any]]:
    """Flatten rotowire-style game records into one row per starter.

    Returns rows of:
        {game_id, team, player_id, player_name, position, slot,
         status, captured_at, injury, play_pct, home_away}

    game_id is synthesised as "<away>@<home>_<date>" since rotowire
    doesn't expose nba_api game_ids.  player_id is None (rotowire is
    name-only).  Downstream consumers join on (team, player_name).
    """
    captured_at = captured_at or _now_iso()
    date_str = _date.today().isoformat()
    rows: List[Dict[str, Any]] = []
    for g in games:
        away, home = g["away_team"], g["home_team"]
        gid = f"{away}@{home}_{date_str}"
        for side, key in (("away", "away_lineup"), ("home", "home_lineup")):
            lineup = g[key]
            status_raw = lineup.get("status", "Unknown")
            status = _STATUS_MAP.get(status_raw, "PROJECTED")
            team = away if side == "away" else home
            for s in lineup["starters"]:
                injury = s.get("injury")
                play_pct = int(s.get("play_pct", 100))
                # Per-player status overrides the lineup-level status
                # when an injury tag is present.
                row_status = status
                if injury in _OUT_TAGS or play_pct == 0:
                    row_status = "OUT"
                elif injury in _QUESTIONABLE_TAGS or 0 < play_pct < 75:
                    row_status = "QUESTIONABLE"
                rows.append({
                    "game_id":     gid,
                    "team":        team,
                    "player_id":   None,
                    "player_name": s["name"],
                    "position":    s["pos"],
                    "slot":        s["pos"],   # RW already uses canonical PG/SG/SF/PF/C
                    "status":      row_status,
                    "captured_at": captured_at,
                    "injury":      injury,
                    "play_pct":    play_pct,
                    "home_away":   side,
                })
    return rows


# ── persistence ───────────────────────────────────────────────────────────────
def snapshot_path(date_str: Optional[str] = None) -> str:
    date_str = date_str or _date.today().isoformat()
    return os.path.join(LINEUPS_DIR, f"{date_str}.json")


def load_prior_snapshot(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def write_snapshot(rows: List[Dict[str, Any]], path: str,
                   change_events: Optional[List[Dict[str, Any]]] = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Preserve prior change_events log
    prior = load_prior_snapshot(path) or {}
    events = list(prior.get("change_events", []))
    if change_events:
        events.extend(change_events)
    payload = {
        "date":          _date.today().isoformat(),
        "updated_at":    _now_iso(),
        "n_starters":    len(rows),
        "source":        "rotowire",
        "starters":      rows,
        "change_events": events,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, path)


# ── change detection ──────────────────────────────────────────────────────────
def _key(row: Dict[str, Any]) -> Tuple[str, str]:
    """Identity for diff: (team, slot)."""
    return (row["team"], row["slot"])


def diff_snapshots(prior_rows: List[Dict[str, Any]],
                   new_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compute change-events between two snapshots.

    Event types:
      - STARTER_SWAP:   same (team, slot), different player_name
      - LATE_SCRATCH:   prior player no longer present in new (any slot)
      - NEW_STARTER:    new player not present in prior
      - STATUS_CHANGE:  same player, status flipped
                        (e.g. CONFIRMED -> QUESTIONABLE -> OUT)
    """
    events: List[Dict[str, Any]] = []
    prior_by_slot = {_key(r): r for r in prior_rows}
    new_by_slot = {_key(r): r for r in new_rows}
    prior_players = {(r["team"], r["player_name"]) for r in prior_rows}
    new_players = {(r["team"], r["player_name"]) for r in new_rows}
    captured_at = _now_iso()

    # slot-keyed swaps + status changes
    for slot_key, new_row in new_by_slot.items():
        prior_row = prior_by_slot.get(slot_key)
        if prior_row is None:
            continue
        if prior_row["player_name"] != new_row["player_name"]:
            events.append({
                "event":       "STARTER_SWAP",
                "team":        new_row["team"],
                "slot":        new_row["slot"],
                "out_player":  prior_row["player_name"],
                "in_player":   new_row["player_name"],
                "captured_at": captured_at,
            })
        elif prior_row["status"] != new_row["status"]:
            events.append({
                "event":       "STATUS_CHANGE",
                "team":        new_row["team"],
                "player_name": new_row["player_name"],
                "from_status": prior_row["status"],
                "to_status":   new_row["status"],
                "captured_at": captured_at,
            })

    # late scratches: prior player no longer in any slot for that team
    for (team, name) in prior_players - new_players:
        events.append({
            "event":       "LATE_SCRATCH",
            "team":        team,
            "player_name": name,
            "captured_at": captured_at,
        })
    # new starters
    for (team, name) in new_players - prior_players:
        events.append({
            "event":       "NEW_STARTER",
            "team":        team,
            "player_name": name,
            "captured_at": captured_at,
        })
    return events


# ── slate-bet alert hook ──────────────────────────────────────────────────────
def load_slate_bet_players(path: str = SLATE_BETS_JSON) -> Set[str]:
    """Return the set of player names with at least one pending bet on tonight's slate."""
    if not os.path.exists(path):
        return set()
    try:
        with open(path, encoding="utf-8") as fh:
            slate = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return set()
    return {b["player"] for b in slate.get("ranked_bets", []) if b.get("player")}


def find_killed_bets(rows: List[Dict[str, Any]],
                     slate_players: Set[str]) -> List[Dict[str, Any]]:
    """A bet is line-killed when a player in the slate is OUT or absent from starters.

    Returns one row per killed player with reason:
      - 'not_starting' (absent from rows entirely)
      - 'status_out'   (present but status == OUT)
    """
    starter_names = {r["player_name"] for r in rows}
    status_by_name = {r["player_name"]: r["status"] for r in rows}
    killed: List[Dict[str, Any]] = []
    for p in slate_players:
        if p not in starter_names:
            killed.append({"player": p, "reason": "not_starting"})
        elif status_by_name.get(p) == "OUT":
            killed.append({"player": p, "reason": "status_out"})
    return killed


def append_alert_md(killed: List[Dict[str, Any]],
                    path: str = ALERTS_MD) -> int:
    """Append URGENT lines to vault/Improvements/lineup_alerts.md.  Returns lines written."""
    if not killed:
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ts = _now_iso()
    new_file = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as fh:
        if new_file:
            fh.write("# Lineup Alerts (R17 J1 — nba_lineup_daemon)\n\n")
            fh.write("URGENT line-killers detected by the lineup daemon.\n\n")
        for k in killed:
            fh.write(
                f"- **URGENT** [{ts}] `{k['player']}` line-killed "
                f"(reason: {k['reason']}) — kill all pending bets.\n"
            )
    # R21_N3 — layered alert (vault + critical-stack always; Discord if URL set).
    try:
        from src.alerts.discord_webhook import alert
        for k in killed:
            alert(
                f"Line-killer: {k['player']}",
                level="critical",
                tag="nba_lineup_daemon",
                source="nba_lineup_daemon",
                body=f"Reason: {k['reason']} — kill all pending bets.",
                fields=[{"name": "player", "value": str(k.get('player', '?'))},
                        {"name": "reason", "value": str(k.get('reason', '?'))}],
            )
    except Exception as exc:  # never block alert ledger on push-notify failure
        log.warning("discord push failed: %s", exc)
    return len(killed)


def mark_killed_in_ledger(killed: List[Dict[str, Any]],
                          path: str = PNL_LEDGER_CSV) -> int:
    """Mark pending bets in pnl_ledger.csv as status=line_killed.

    A 'pending' bet has status in {'pending', 'open', ''}.  Returns the
    number of bet rows updated.
    """
    if not killed or not os.path.exists(path):
        return 0
    killed_names = {k["player"] for k in killed}
    PENDING = {"pending", "open", ""}
    updated = 0
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fieldnames = reader.fieldnames
    if not fieldnames:
        return 0
    for r in rows:
        if (r.get("player") in killed_names
                and (r.get("status") or "").strip().lower() in PENDING):
            r["status"] = "line_killed"
            updated += 1
    if updated:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, path)
    return updated


# ── one-shot loop body ────────────────────────────────────────────────────────
def run_once(fetcher: Optional[Callable[[], str]] = None,
             slate_path: str = SLATE_BETS_JSON,
             ledger_path: str = PNL_LEDGER_CSV,
             alerts_path: str = ALERTS_MD,
             snapshot_dir: str = LINEUPS_DIR) -> Dict[str, Any]:
    """Single fetch + diff + alert.

    fetcher: callable returning raw HTML; defaults to rotowire fetch_html().
             Tests can inject a static HTML string here.
    Returns a small summary dict for logging / probes.
    """
    body = (fetcher() if fetcher is not None else _rw_fetch_html(force=True))
    games = _rw_parse_html(body)
    rows = normalize_games(games)
    if not rows:
        log.warning("0 starters parsed; rotowire layout may have changed")
        return {"n_starters": 0, "killed": [], "events": []}

    snap_path = os.path.join(snapshot_dir, f"{_date.today().isoformat()}.json")
    prior = load_prior_snapshot(snap_path)
    prior_rows = (prior or {}).get("starters", [])
    events = diff_snapshots(prior_rows, rows)

    slate_players = load_slate_bet_players(slate_path)
    killed = find_killed_bets(rows, slate_players)
    alert_lines = append_alert_md(killed, alerts_path) if killed else 0
    ledger_updates = mark_killed_in_ledger(killed, ledger_path) if killed else 0

    write_snapshot(rows, snap_path, change_events=events)

    if events:
        for ev in events:
            log.info("change_event %s", json.dumps(ev, ensure_ascii=False))
    if killed:
        log.warning(
            "URGENT line-killers: %s  (alerts=%d ledger_updates=%d)",
            [k["player"] for k in killed], alert_lines, ledger_updates,
        )
    else:
        log.info("no killed bets; n_starters=%d events=%d",
                 len(rows), len(events))

    return {
        "n_starters":      len(rows),
        "events":          events,
        "killed":          killed,
        "alerts_written":  alert_lines,
        "ledger_updates":  ledger_updates,
        "snapshot_path":   snap_path,
        "rows":            rows,
    }


# ── CLI / daemon loop ─────────────────────────────────────────────────────────
def _pretty_print_starters(rows: List[Dict[str, Any]]) -> None:
    by_team: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_team.setdefault(r["team"], []).append(r)
    for team in sorted(by_team):
        print(f"\n=== {team} starters ===")
        # sort by canonical slot order
        ranked = sorted(by_team[team],
                        key=lambda r: _SLOT_ORDER.index(r["slot"])
                                       if r["slot"] in _SLOT_ORDER else 99)
        for r in ranked:
            inj = f" [{r['injury']}]" if r["injury"] else ""
            print(f"  {r['slot']:>2}  {r['player_name']:<28} "
                  f"{r['status']:<13} play_pct={r['play_pct']}%{inj}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="NBA starting-lineup daemon (R17 J1)")
    ap.add_argument("--interval-sec", type=int, default=60,
                    help="Poll interval in seconds (default 60)")
    ap.add_argument("--once", action="store_true",
                    help="Run a single fetch then exit")
    ap.add_argument("--smoke", action="store_true",
                    help="Run once and pretty-print all starters")
    args = ap.parse_args(argv)

    if args.smoke or args.once:
        result = run_once()
        if args.smoke:
            _pretty_print_starters(result.get("rows", []))
            if result.get("killed"):
                print("\nURGENT line-killers:")
                for k in result["killed"]:
                    print(f"  - {k['player']}  reason={k['reason']}")
        return 0

    # long-running daemon
    log.info("daemon starting; interval=%ds  snapshot_dir=%s",
             args.interval_sec, LINEUPS_DIR)
    while True:
        # R19_L3 heartbeat
        _r19_hb('nba_lineup_daemon')
        try:
            run_once()
        except urllib.error.URLError as e:
            log.warning("transient network error: %s", e)
        except Exception:  # noqa: BLE001 — daemon must not die
            log.exception("unexpected error in poll cycle")
        time.sleep(args.interval_sec)


if __name__ == "__main__":
    sys.exit(main())
