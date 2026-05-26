"""auto_settle_daemon.py — R18_K8 post-game auto-settle daemon.

Watches data/cache/quarter_box/ for new <game_id>_q4.json files (which appear
only when a game has gone final and all four quarters have been ingested).
For each newly-final game, settles every still-open bet in data/pnl_ledger.csv
whose game_id matches, using actual q1..qN summed stats.

Edge cases handled:
  * DNP — if the bet's player does not appear in any quarter box for the game,
    the bet is VOIDED via src.betting.pnl_ledger.void_bet (stake refunded).
  * OT — sum_quarter_box_full() walks ALL period files (q1, q2, …, q4, q5, …),
    so overtime stats are folded into the FINAL totals automatically.
  * Idempotency — already-settled bets (status != "open") are skipped, and the
    daemon tracks "seen" q4 files via data/cache/auto_settle_seen.json.
  * Bankroll refresh — after each batch of settles, calls
    scripts/bankroll_monitor_daemon.tick() to refresh bankroll_state.json.

CLI:
    python scripts/auto_settle_daemon.py \\
        --interval-sec 300 \\
        --qb-dir data/cache/quarter_box \\
        [--once]               # run one scan then exit (for tests / cron)
        [--start-bankroll N]   # passed to bankroll tick() (default 1000.0)

Output:
  * vault/Improvements/auto_settle.md   — append-only audit log
  * data/cache/bankroll_state.json      — refreshed by tick()
  * data/cache/auto_settle_seen.json    — list of q4 game_ids processed

Public API (importable):
    scan_new_q4_files(qb_dir, seen_set) -> list[str]    # new game_ids
    settle_game(game_id, qb_dir, dry_run=False) -> dict # per-game result
    void_dnp_bets(game_id, qb_dir, dry_run=False) -> list[dict]
    tick(state) -> dict                                  # one full cycle
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import logging
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# ----- Lazy imports (project local modules) ----- #
# Done at module level so they're easy to monkey-patch from tests.
from src.betting import pnl_ledger as _ledger          # noqa: E402

# Reuse helpers + the existing per-game summer from settle_bets.
import scripts.settle_bets as _sb                       # noqa: E402

DEFAULT_QB_DIR = Path(PROJECT_DIR) / "data" / "cache" / "quarter_box"
SEEN_PATH      = Path(PROJECT_DIR) / "data" / "cache" / "auto_settle_seen.json"
LOG_MD         = Path(PROJECT_DIR) / "vault" / "Improvements" / "auto_settle.md"
PROBE_PATH     = Path(PROJECT_DIR) / "data" / "cache" / "probe_R18_K8_auto_settle_results.json"

# R25_R2: full-game boxscore_<gid>.json fallback dir. Lives at data/nba/.
# Per-period quarter_box JSONs occasionally omit garbage-time low-minute
# players whose minutes never round to a per-period bucket -> daemon used to
# void those bets as DNP even when the player did play. Fall back to the
# full-game traditional boxscore (which reflects official-corrected totals)
# before declaring DNP.
DEFAULT_FULL_BOX_DIR = Path(PROJECT_DIR) / "data" / "nba"

# ---- Logger ---- #
logger = logging.getLogger("auto_settle")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[auto-settle] %(asctime)s %(message)s",
                                       "%Y-%m-%dT%H:%M:%S"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)


# --------------------------------------------------------------------------- #
# Player-name normalization (mirrors scripts/settle_bets.py).                 #
# --------------------------------------------------------------------------- #
def _player_key(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.lower().strip()


# --------------------------------------------------------------------------- #
# OT-aware: walk ALL period files for a game (q1, q2, q3, q4, q5, q6, ...).   #
# --------------------------------------------------------------------------- #
_Q_RE = re.compile(r"^(\d{10})_q(\d+)\.json$")


def list_period_files(game_id: str, qb_dir: Path) -> List[Path]:
    qb_dir = Path(qb_dir)
    out: List[Tuple[int, Path]] = []
    if not qb_dir.exists():
        return []
    for entry in qb_dir.iterdir():
        m = _Q_RE.match(entry.name)
        if m and m.group(1) == game_id:
            out.append((int(m.group(2)), entry))
    out.sort()
    return [p for _, p in out]


def sum_quarter_box_full(game_id: str, qb_dir: Optional[Path] = None,
                          ) -> Dict[str, Dict[str, Any]]:
    """OT-aware total: sum across ALL period files present for game_id."""
    qb_dir = Path(qb_dir or DEFAULT_QB_DIR)
    files = list_period_files(game_id, qb_dir)
    if not files:
        return {}
    totals: Dict[str, Dict[str, Any]] = {}
    for p in files:
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for pl in d.get("players", []) or []:
            name = pl.get("player_name", "")
            if not name:
                continue
            row = totals.setdefault(name, {
                "pts": 0.0, "reb": 0.0, "ast": 0.0, "fg3m": 0.0,
                "stl": 0.0, "blk": 0.0, "tov": 0.0,
                "player_id": pl.get("player_id"),
                "team": pl.get("team_abbreviation"),
            })
            for ledger_stat, box_field in _sb._STAT_TO_BOX_FIELD.items():
                v = pl.get(box_field, 0) or 0
                try:
                    row[ledger_stat] += float(v)
                except (TypeError, ValueError):
                    continue
    return totals


# --------------------------------------------------------------------------- #
# Seen-set persistence (tracks which q4 files we've processed).               #
# --------------------------------------------------------------------------- #
def load_seen(path: Path = SEEN_PATH) -> Set[str]:
    if not path.exists():
        return set()
    try:
        return set(json.load(open(path, encoding="utf-8")) or [])
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen(seen: Set[str], path: Path = SEEN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    json.dump(sorted(seen), open(tmp, "w", encoding="utf-8"))
    os.replace(tmp, path)


def scan_new_q4_files(qb_dir: Path, seen: Set[str]) -> List[str]:
    """Return list of game_ids whose _q4.json file appeared since last scan."""
    qb_dir = Path(qb_dir)
    if not qb_dir.exists():
        return []
    out: List[str] = []
    for entry in sorted(qb_dir.glob("*_q4.json")):
        gid = entry.name[:-len("_q4.json")]
        if len(gid) == 10 and gid.isdigit() and gid not in seen:
            out.append(gid)
    return out


# --------------------------------------------------------------------------- #
# Per-bet match against the box.                                              #
# --------------------------------------------------------------------------- #
def _match_player(bet: Dict[str, Any], totals: Dict[str, Dict[str, Any]],
                   ) -> Optional[Dict[str, Any]]:
    pname = bet.get("player", "")
    pkey = _player_key(pname)
    for nm, row in totals.items():
        if _player_key(nm) == pkey:
            return row
    pid = str(bet.get("player_id") or "").strip()
    if pid:
        for row in totals.values():
            if str(row.get("player_id") or "") == pid:
                return row
    return None


# --------------------------------------------------------------------------- #
# R25_R2: Full-game boxscore fallback. The per-period quarter_box files       #
# occasionally drop low-minute garbage-time players (e.g. < 1 min in any      #
# single quarter). Before voiding a bet as DNP, consult the                   #
# traditional boxscore_<gid>.json which carries the official-final totals.   #
# --------------------------------------------------------------------------- #
_FULL_BOX_STAT_MAP = {
    "pts": "pts", "reb": "reb", "ast": "ast",
    "fg3m": "fg3m", "stl": "stl", "blk": "blk", "tov": "to",
}


def _load_full_box_player(game_id: str,
                            bet: Dict[str, Any],
                            full_box_dir: Optional[Path] = None,
                            ) -> Optional[Dict[str, Any]]:
    """Return a totals-shaped dict for `bet`'s player from the full-game box.

    Returns None when (a) no full-box file exists, (b) it's unreadable, or
    (c) the player is absent from the full box too (= true DNP).
    """
    full_box_dir = Path(full_box_dir or DEFAULT_FULL_BOX_DIR)
    fp = full_box_dir / f"boxscore_{game_id}.json"
    if not fp.exists():
        return None
    try:
        data = json.load(open(fp, encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    pname = bet.get("player", "")
    pkey  = _player_key(pname)
    pid   = str(bet.get("player_id") or "").strip()
    for pl in data.get("players", []) or []:
        nm = pl.get("player_name", "") or ""
        if _player_key(nm) == pkey or (pid and str(pl.get("player_id") or "") == pid):
            row: Dict[str, Any] = {
                "player_id": pl.get("player_id"),
                "team":      pl.get("team_abbreviation"),
            }
            for ledger_stat, box_field in _FULL_BOX_STAT_MAP.items():
                v = pl.get(box_field, 0) or 0
                try:
                    row[ledger_stat] = float(v)
                except (TypeError, ValueError):
                    row[ledger_stat] = 0.0
            return row
    return None


# --------------------------------------------------------------------------- #
# Game settlement (settle won/lost/push + void DNPs).                         #
# --------------------------------------------------------------------------- #
def settle_game(game_id: str, qb_dir: Optional[Path] = None,
                 dry_run: bool = False,
                 open_bets_by_game: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                 ) -> Dict[str, Any]:
    """Settle all open bets for game_id from quarter-box totals (OT-aware).

    Returns:
        {
          'game_id': str,
          'settled': [{bet_id, status, profit_loss, actual_stat}, ...],
          'voided':  [{bet_id, reason: "dnp"}, ...],
          'skipped': [{bet_id, reason}, ...],
          'errored': [{bet_id, error}, ...],
        }

    If open_bets_by_game is supplied, the ledger is NOT re-read — used by
    tick() to amortise one load across many game_ids.
    """
    qb_dir = Path(qb_dir or DEFAULT_QB_DIR)
    result: Dict[str, Any] = {
        "game_id": game_id, "settled": [], "voided": [], "skipped": [],
        "errored": [], "n_periods": len(list_period_files(game_id, qb_dir)),
    }

    # Cheap pre-check: do we even have open bets on this game?
    if open_bets_by_game is None:
        all_open = _ledger.open_bets()
        bets = [b for b in all_open if (b.get("game_id") or "").strip() == game_id]
    else:
        bets = open_bets_by_game.get(game_id, [])
    if not bets:
        return result   # no work, no need to load the 200-player box

    totals = sum_quarter_box_full(game_id, qb_dir)
    if not totals:
        result["skipped"].append({"bet_id": "*", "reason": "no_box_data"})
        return result

    for bet in bets:
        bid = bet["bet_id"]
        match = _match_player(bet, totals)
        if match is None:
            # R25_R2 fix: before voiding, try the full-game traditional
            # boxscore. Per-period files occasionally omit low-minute
            # garbage-time players whose minutes were never recorded in any
            # single quarter (R25_R2 audit found this on game 0022500005
            # for Johnny Furphy — full box has him at 0/0/0, quarter_box
            # has him in zero periods).
            match = _load_full_box_player(game_id, bet, DEFAULT_FULL_BOX_DIR)
        if match is None:
            # DNP — player didn't appear in quarter box OR full box -> void + refund stake.
            if dry_run:
                result["voided"].append({"bet_id": bid, "reason": "dnp_dryrun"})
                continue
            try:
                v = _ledger.void_bet(bid)
                result["voided"].append({
                    "bet_id": bid, "reason": "dnp",
                    "bankroll_after": v.get("bankroll_after"),
                })
            except (KeyError, ValueError) as exc:
                result["errored"].append({"bet_id": bid, "error": str(exc)})
            continue

        stat = str(bet.get("stat", "")).lower()
        actual = match.get(stat)
        if actual is None:
            result["skipped"].append({"bet_id": bid,
                                       "reason": f"stat_{stat}_missing"})
            continue

        if dry_run:
            result["settled"].append({"bet_id": bid,
                                       "would_settle": True,
                                       "actual_stat": float(actual)})
            continue
        try:
            r = _ledger.settle_bet(bid, float(actual))
            result["settled"].append({
                "bet_id": bid,
                "status": r["status"],
                "profit_loss": r["profit_loss"],
                "bankroll_after": r["bankroll_after"],
                "actual_stat": float(actual),
            })
        except (KeyError, ValueError) as exc:
            result["errored"].append({"bet_id": bid, "error": str(exc)})

    return result


def void_dnp_bets(game_id: str, qb_dir: Optional[Path] = None,
                    dry_run: bool = False) -> List[Dict[str, Any]]:
    """Standalone helper: void any open bets for game_id whose player is DNP.

    Returns list of {bet_id, reason, bankroll_after?} dicts.
    """
    return settle_game(game_id, qb_dir, dry_run=dry_run)["voided"]


# --------------------------------------------------------------------------- #
# Append-only audit log.                                                      #
# --------------------------------------------------------------------------- #
def append_audit_log(result: Dict[str, Any],
                      path: Optional[Path] = None) -> None:
    path = Path(path) if path is not None else LOG_MD
    path.parent.mkdir(parents=True, exist_ok=True)
    now = _dt.datetime.now().isoformat(timespec="seconds")
    gid = result["game_id"]
    s = result["settled"]; v = result["voided"]
    sk = result["skipped"]; er = result["errored"]
    lines = [
        "",
        f"## {now}  game `{gid}`  ({result.get('n_periods', 4)} periods)",
        f"- settled: **{len(s)}**, voided: **{len(v)}**, skipped: {len(sk)}, errored: {len(er)}",
    ]
    for x in s[:25]:
        if x.get("would_settle"):
            lines.append(f"  - {x['bet_id'][:8]} would-settle actual={x['actual_stat']:.2f}")
        else:
            lines.append(f"  - {x['bet_id'][:8]} **{x['status']}**  "
                          f"actual={x['actual_stat']:.2f}  "
                          f"pnl={x['profit_loss']:+.2f}  "
                          f"bal={x['bankroll_after']:.2f}")
    for x in v[:25]:
        lines.append(f"  - {x['bet_id'][:8]} *voided* ({x['reason']})")
    for x in sk[:10]:
        lines.append(f"  - {x['bet_id'][:8]} skip ({x['reason']})")
    for x in er[:10]:
        lines.append(f"  - {x['bet_id'][:8]} ERROR ({x['error']})")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# Bankroll-state refresh (calls into R17_J4's compute_metrics).               #
# --------------------------------------------------------------------------- #
def refresh_bankroll(start_bankroll: float = 1000.0) -> Dict[str, Any]:
    """Recompute data/cache/bankroll_state.json via R17_J4 tick()."""
    try:
        import scripts.bankroll_monitor_daemon as _bm
        return _bm.tick(start_bankroll)
    except Exception as exc:                # pragma: no cover - hard to mock
        logger.warning("bankroll refresh failed: %s", exc)
        return {"error": str(exc)}


# --------------------------------------------------------------------------- #
# One scan cycle.                                                             #
# --------------------------------------------------------------------------- #
def tick(qb_dir: Optional[Path] = None,
          seen_path: Optional[Path] = None,
          dry_run: bool = False, start_bankroll: float = 1000.0,
          ) -> Dict[str, Any]:
    qb_dir = Path(qb_dir or DEFAULT_QB_DIR)
    seen_path = Path(seen_path) if seen_path is not None else SEEN_PATH
    first_run = not seen_path.exists()
    seen = load_seen(seen_path)

    # First-run safety: don't replay all historical q4 files — seed the seen
    # set with every q4 currently on disk and persist. Subsequent ticks will
    # only act on NEW q4 files that appear after this moment.
    if first_run:
        for entry in Path(qb_dir).glob("*_q4.json") if Path(qb_dir).exists() else []:
            gid = entry.name[:-len("_q4.json")]
            if len(gid) == 10 and gid.isdigit():
                seen.add(gid)
        if not dry_run:
            save_seen(seen, seen_path)
        logger.info("first-run: seeded seen-set with %d existing q4 files",
                     len(seen))

    new = scan_new_q4_files(qb_dir, seen)
    cycle: Dict[str, Any] = {
        "as_of": _dt.datetime.now().isoformat(timespec="seconds"),
        "new_q4_files": new, "games": [], "first_run": first_run,
    }

    # Load open bets ONCE for the whole tick and group by game_id.
    open_by_game: Dict[str, List[Dict[str, Any]]] = {}
    if new:
        for b in _ledger.open_bets():
            gid = (b.get("game_id") or "").strip()
            if gid:
                open_by_game.setdefault(gid, []).append(b)

    for gid in new:
        res = settle_game(gid, qb_dir, dry_run=dry_run,
                            open_bets_by_game=open_by_game)
        cycle["games"].append(res)
        if not dry_run:
            # Only audit-log games where something happened.
            if res["settled"] or res["voided"] or res["errored"]:
                append_audit_log(res)
            seen.add(gid)
    if not dry_run and new:
        save_seen(seen, seen_path)
        # Only refresh bankroll if we actually settled or voided something.
        if any(g["settled"] or g["voided"] for g in cycle["games"]):
            cycle["bankroll"] = refresh_bankroll(start_bankroll)
    cycle["totals"] = {
        "games":   len(cycle["games"]),
        "settled": sum(len(g["settled"]) for g in cycle["games"]),
        "voided":  sum(len(g["voided"])  for g in cycle["games"]),
        "skipped": sum(len(g["skipped"]) for g in cycle["games"]),
        "errored": sum(len(g["errored"]) for g in cycle["games"]),
    }
    return cycle


# --------------------------------------------------------------------------- #
# Probe (atomic JSON dump of last cycle for downstream consumers).            #
# --------------------------------------------------------------------------- #
def write_probe(cycle: Dict[str, Any], path: Path = PROBE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    json.dump(cycle, open(tmp, "w", encoding="utf-8"), indent=2, default=str)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Post-game auto-settle daemon (R18_K8)")
    ap.add_argument("--interval-sec", type=int, default=300,
                     help="Seconds between scans (default 300)")
    ap.add_argument("--qb-dir", type=str, default=str(DEFAULT_QB_DIR),
                     help="quarter_box dir (default data/cache/quarter_box)")
    ap.add_argument("--seen-path", type=str, default=str(SEEN_PATH),
                     help="seen-set JSON path (default data/cache/auto_settle_seen.json)")
    ap.add_argument("--start-bankroll", type=float, default=1000.0)
    ap.add_argument("--dry-run", action="store_true",
                     help="Don't mutate ledger; only report what would happen")
    ap.add_argument("--once", action="store_true",
                     help="Run one scan + exit (good for cron / smoke tests)")
    args = ap.parse_args(argv)

    qb_dir = Path(args.qb_dir)
    seen_path = Path(args.seen_path)
    logger.info("start  interval=%ds  qb_dir=%s  dry_run=%s",
                 args.interval_sec, qb_dir, args.dry_run)
    while True:
        # R19_L3 heartbeat
        _r19_hb('auto_settle_daemon')
        try:
            cycle = tick(qb_dir, seen_path, dry_run=args.dry_run,
                          start_bankroll=args.start_bankroll)
            write_probe(cycle)
            t = cycle["totals"]
            logger.info("tick  new_games=%d  settled=%d  voided=%d  "
                         "skipped=%d  errored=%d",
                         t["games"], t["settled"], t["voided"],
                         t["skipped"], t["errored"])
        except Exception as exc:                # pragma: no cover
            logger.exception("tick failed: %s", exc)
        if args.once:
            return 0
        time.sleep(args.interval_sec)


if __name__ == "__main__":
    sys.exit(main())
