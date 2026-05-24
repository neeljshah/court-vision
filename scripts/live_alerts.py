"""live_alerts.py — terminal-bell alerts when live projections diverge from
pre-game predictions or placed bets. Cycle 88k (loop 5).

During games the user has 5-15 bets active. Watching every one is overwhelming.
This script polls `data/live/` for new snapshots, joins them against the day's
pre-game predictions (`data/predictions/<date>.csv`) and active bets
(`data/bets/<date>.csv`), and emits ALERTS only when a meaningful divergence is
detected.

Alert types
-----------
1. EDGE_FLIP        — pre-game +EV bet has gone to -EV (or vice versa)
2. PROJECTION_SHIFT — in-game projection moved >= threshold stat units from
                       pre-game prediction for a player on the bet log
3. BLOWOUT_RISK     — |margin| crossed 20+ in Q4 → star bets at risk
4. FOUL_TROUBLE     — a player with active bets has 4+ fouls
5. INACTIVE_LATE    — player listed inactive AFTER bet was placed
                       (live snapshot has min==0 in the live game)

Each fired alert writes a structured JSON line to `data/alerts/<date>.log` and
prints a coloured stdout line preceded by '\\a' (BEL). A state file
`data/alerts/<date>_state.json` tracks which alert keys have already fired so a
running daemon doesn't re-alert every poll.

CLI
---
    python scripts/live_alerts.py                       # daemon, 30s interval
    python scripts/live_alerts.py --once                # one check + exit
    python scripts/live_alerts.py --threshold 5.0       # custom shift threshold
    python scripts/live_alerts.py --types EDGE_FLIP,FOUL_TROUBLE
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import date as _date, datetime
from typing import Callable, Dict, List, Optional, Set, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from src.data.live import (  # noqa: E402
    absolute_margin, find_player, is_live, list_today_snapshots,
    load_live_state, _name_key,
)

# Optional import — predict_in_game lives in scripts/. We import lazily inside
# the projection routine so tests don't pay the cost.
ALERT_TYPES = (
    "EDGE_FLIP",
    "PROJECTION_SHIFT",
    "BLOWOUT_RISK",
    "FOUL_TROUBLE",
    "INACTIVE_LATE",
)

_DEFAULT_THRESHOLD = 3.0
_DEFAULT_INTERVAL = 30.0
_BLOWOUT_MARGIN = 20
_FOUL_TROUBLE_PF = 4
_ANSI = {
    "red":    "\033[31m",
    "yellow": "\033[33m",
    "cyan":   "\033[36m",
    "magenta": "\033[35m",
    "green":  "\033[32m",
    "reset":  "\033[0m",
}
_TYPE_COLOR = {
    "EDGE_FLIP":         "red",
    "PROJECTION_SHIFT":  "yellow",
    "BLOWOUT_RISK":      "magenta",
    "FOUL_TROUBLE":      "cyan",
    "INACTIVE_LATE":     "red",
}


# ── path helpers ─────────────────────────────────────────────────────────────

def alerts_dir(project_dir: Optional[str] = None) -> str:
    project_dir = project_dir or PROJECT_DIR
    return os.path.join(project_dir, "data", "alerts")


def predictions_path(date_str: str, project_dir: Optional[str] = None) -> str:
    project_dir = project_dir or PROJECT_DIR
    return os.path.join(project_dir, "data", "predictions", f"{date_str}.csv")


def bets_path(date_str: str, project_dir: Optional[str] = None) -> str:
    project_dir = project_dir or PROJECT_DIR
    return os.path.join(project_dir, "data", "bets", f"{date_str}.csv")


# ── state + ledger I/O ───────────────────────────────────────────────────────

def load_state(date_str: str, project_dir: Optional[str] = None) -> Set[str]:
    """Return the set of alert KEYS already fired today."""
    path = os.path.join(alerts_dir(project_dir), f"{date_str}_state.json")
    if not os.path.exists(path):
        return set()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh) or {}
        return set(data.get("fired", []))
    except Exception:
        return set()


def save_state(date_str: str, fired: Set[str],
               project_dir: Optional[str] = None) -> str:
    d = alerts_dir(project_dir)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{date_str}_state.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"fired": sorted(fired)}, fh, indent=2)
    return path


def append_log(date_str: str, alert: dict,
               project_dir: Optional[str] = None) -> str:
    """Append a single structured alert JSON to data/alerts/<date>.log."""
    d = alerts_dir(project_dir)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{date_str}.log")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(alert, ensure_ascii=False) + "\n")
    return path


# ── pre-game + bets loaders ──────────────────────────────────────────────────

def load_pregame_predictions(date_str: str,
                              project_dir: Optional[str] = None) -> Dict[Tuple[str, str], float]:
    """{(player_name_key, stat_lower): pred} — empty if file absent."""
    path = predictions_path(date_str, project_dir)
    out: Dict[Tuple[str, str], float] = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8") as fh:
            r = csv.DictReader(fh)
            for row in r:
                name = row.get("player") or ""
                stat = (row.get("stat") or "").lower()
                try:
                    pred = float(row.get("pred"))
                except (TypeError, ValueError):
                    continue
                if name and stat:
                    out[(_name_key(name), stat)] = pred
    except Exception:
        pass
    return out


def load_active_bets(date_str: str,
                      project_dir: Optional[str] = None) -> List[dict]:
    """Return a list of normalized active-bet dicts from data/bets/<date>.csv.

    Each row carries the FIELDS the alert logic needs:
        player, stat (lower), line (float), side ('OVER'/'UNDER'),
        odds (int), ev_per_dollar (float)
    """
    path = bets_path(date_str, project_dir)
    out: List[dict] = []
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8") as fh:
            r = csv.DictReader(fh)
            for row in r:
                try:
                    line = float(row.get("line"))
                except (TypeError, ValueError):
                    continue
                try:
                    odds = int(float(row.get("odds") or -110))
                except (TypeError, ValueError):
                    odds = -110
                try:
                    ev = float(row.get("ev_per_dollar") or 0.0)
                except (TypeError, ValueError):
                    ev = 0.0
                out.append({
                    "player": row.get("player") or "",
                    "stat":   (row.get("stat") or "").lower(),
                    "line":   line,
                    "side":   (row.get("side") or "OVER").upper(),
                    "odds":   odds,
                    "ev_per_dollar": ev,
                    "placed_ts": row.get("timestamp") or "",
                })
    except Exception:
        pass
    return out


# ── projection (delegates to predict_in_game) ────────────────────────────────

def _project_snapshot_rows(snapshot: dict) -> List[dict]:
    """Lazy wrapper around predict_in_game.project_snapshot.

    Imported inline so unit tests that monkeypatch this can run without
    materialising the heavy module graph.
    """
    from scripts.predict_in_game import project_snapshot
    return project_snapshot(snapshot)


def _projection_index(rows: List[dict]) -> Dict[Tuple[str, str], dict]:
    """Index project_snapshot rows by (name_key, stat_lower)."""
    idx: Dict[Tuple[str, str], dict] = {}
    for r in rows:
        key = (_name_key(r.get("name", "")), str(r.get("stat", "")).lower())
        idx[key] = r
    return idx


# ── alert detectors (pure functions, all return list[dict]) ──────────────────

def _bet_won_at_pred(bet: dict, pred: float) -> Optional[bool]:
    """For a bet of side OVER/UNDER, would `pred` clear the line in our favor?

    Returns True if the model agrees with the bet, False if disagrees, None
    if pred isn't usable. Equal-to-line is treated as 'no edge' (False).
    """
    if pred is None:
        return None
    if bet["side"] == "OVER":
        return pred > bet["line"]
    return pred < bet["line"]


def detect_edge_flip(bets: List[dict],
                      pregame: Dict[Tuple[str, str], float],
                      proj_idx: Dict[Tuple[str, str], dict]) -> List[dict]:
    """A bet was +EV pre-game but the live projection has flipped it -EV."""
    alerts = []
    for bet in bets:
        key = (_name_key(bet["player"]), bet["stat"])
        pre = pregame.get(key)
        proj_row = proj_idx.get(key)
        if proj_row is None:
            continue
        proj = proj_row.get("projected_final")
        # Source of "pre-game edge": prefer the pregame prediction if present,
        # otherwise fall back to the model EV column from the bet log.
        if pre is not None:
            pre_agree = _bet_won_at_pred(bet, pre)
        else:
            pre_agree = bet["ev_per_dollar"] > 0
        live_agree = _bet_won_at_pred(bet, proj)
        if pre_agree is None or live_agree is None:
            continue
        if pre_agree and not live_agree:
            alerts.append({
                "type":       "EDGE_FLIP",
                "player":     bet["player"],
                "stat":       bet["stat"].upper(),
                "line":       bet["line"],
                "side":       bet["side"],
                "pregame":    pre,
                "projected":  proj,
                "key":        f"EDGE_FLIP|{key[0]}|{key[1]}|{bet['side']}|{bet['line']}",
                "message":    (
                    f"{bet['player']} {bet['stat'].upper()} {bet['side']} "
                    f"{bet['line']}: pregame {pre if pre is not None else '?'} "
                    f"→ live proj {proj:.2f} (edge flipped against bet)"
                ),
            })
    return alerts


def detect_projection_shift(bets: List[dict],
                             pregame: Dict[Tuple[str, str], float],
                             proj_idx: Dict[Tuple[str, str], dict],
                             threshold: float) -> List[dict]:
    """Live projection moved >= threshold stat-units away from pre-game."""
    alerts = []
    bet_keys = {(_name_key(b["player"]), b["stat"]) for b in bets}
    for key in bet_keys:
        pre = pregame.get(key)
        row = proj_idx.get(key)
        if pre is None or row is None:
            continue
        proj = row.get("projected_final")
        if proj is None:
            continue
        delta = float(proj) - float(pre)
        if abs(delta) < threshold:
            continue
        # Bucket the delta sign + integer magnitude into the key so a shift
        # that grows from 3.0 to 5.0 fires only once per integer step (we
        # don't want to spam the user as the projection drifts).
        bucket = int(abs(delta))
        sign = "+" if delta > 0 else "-"
        alerts.append({
            "type":      "PROJECTION_SHIFT",
            "player":    row.get("name", ""),
            "stat":      key[1].upper(),
            "pregame":   pre,
            "projected": float(proj),
            "delta":     round(delta, 3),
            "threshold": threshold,
            "key":       f"PROJECTION_SHIFT|{key[0]}|{key[1]}|{sign}{bucket}",
            "message":   (
                f"{row.get('name', '')} {key[1].upper()}: pregame "
                f"{pre:.2f} → live proj {float(proj):.2f} "
                f"({delta:+.2f} units; threshold {threshold:+.1f})"
            ),
        })
    return alerts


def detect_blowout_risk(snapshot: dict, bets: List[dict]) -> List[dict]:
    """Q4+ and |margin| >= 20 — star bets at risk of garbage time."""
    period = int(snapshot.get("period") or 0)
    if period < 4:
        return []
    margin = absolute_margin(snapshot)
    if margin < _BLOWOUT_MARGIN:
        return []
    game_id = snapshot.get("game_id", "")
    home = snapshot.get("home_team", "")
    away = snapshot.get("away_team", "")
    # Surface ONE alert per game (single key) listing every at-risk bet.
    at_risk = []
    for bet in bets:
        p = find_player(snapshot, bet["player"])
        if p is None:
            continue
        if p.get("team", "").upper() not in {home.upper(), away.upper()}:
            continue
        at_risk.append(f"{bet['player']} {bet['stat'].upper()} {bet['side']} {bet['line']}")
    if not at_risk:
        return []
    return [{
        "type":     "BLOWOUT_RISK",
        "game_id":  game_id,
        "period":   period,
        "margin":   margin,
        "matchup":  f"{away} @ {home}",
        "at_risk":  at_risk,
        "key":      f"BLOWOUT_RISK|{game_id}",
        "message": (
            f"BLOWOUT in {away}@{home} Q{period} (margin {margin}); "
            f"{len(at_risk)} bet(s) at risk: " + "; ".join(at_risk)
        ),
    }]


def detect_foul_trouble(snapshot: dict, bets: List[dict]) -> List[dict]:
    """A bet-on player has >= 4 personal fouls. One alert per (player, pf-bucket)."""
    alerts = []
    bet_players = {_name_key(b["player"]) for b in bets}
    for p in snapshot.get("players") or []:
        if _name_key(p.get("name", "")) not in bet_players:
            continue
        try:
            pf = int(p.get("pf") or 0)
        except (TypeError, ValueError):
            continue
        if pf < _FOUL_TROUBLE_PF:
            continue
        period = int(snapshot.get("period") or 0)
        alerts.append({
            "type":     "FOUL_TROUBLE",
            "player":   p.get("name", ""),
            "team":     p.get("team", ""),
            "pf":       pf,
            "period":   period,
            "key":      f"FOUL_TROUBLE|{_name_key(p.get('name', ''))}|{pf}",
            "message":  (
                f"{p.get('name', '')} ({p.get('team', '')}) has {pf} fouls "
                f"in Q{period} — active bet at risk"
            ),
        })
    return alerts


def detect_inactive_late(snapshot: dict, bets: List[dict]) -> List[dict]:
    """Player on the bet log has min==0 in a LIVE game (post-tip scratch)."""
    if not is_live(snapshot):
        return []
    period = int(snapshot.get("period") or 0)
    # Don't fire pre-tip — only once at least one quarter has elapsed so we
    # don't mistake "hasn't checked in yet" for "scratched".
    if period < 1:
        return []
    alerts = []
    for bet in bets:
        p = find_player(snapshot, bet["player"])
        if p is None:
            # Not in the box score at all → scratched.
            scratched = True
            cur_min = 0.0
        else:
            try:
                cur_min = float(p.get("min") or 0.0)
            except (TypeError, ValueError):
                cur_min = 0.0
            scratched = cur_min <= 0.0
        if not scratched:
            continue
        # Require >= one full quarter elapsed before we trust the "min==0"
        # signal as 'inactive', otherwise garbage-time bench guys trigger
        # at tipoff.
        if period < 2:
            continue
        key_name = _name_key(bet["player"])
        alerts.append({
            "type":    "INACTIVE_LATE",
            "player":  bet["player"],
            "stat":    bet["stat"].upper(),
            "line":    bet["line"],
            "side":    bet["side"],
            "game_id": snapshot.get("game_id", ""),
            "period":  period,
            "key":     f"INACTIVE_LATE|{key_name}|{snapshot.get('game_id', '')}",
            "message": (
                f"{bet['player']} appears INACTIVE after tip "
                f"(min=0, Q{period}); bet was {bet['stat'].upper()} "
                f"{bet['side']} {bet['line']}"
            ),
        })
    return alerts


# ── orchestrator ─────────────────────────────────────────────────────────────

def _color_for(alert_type: str) -> str:
    return _TYPE_COLOR.get(alert_type, "yellow")


def _emit_stdout(alert: dict, *, use_color: bool, ring_bell: bool,
                 stream=None) -> str:
    """Print the alert line; return the rendered string for testability."""
    stream = stream or sys.stdout
    color = _color_for(alert["type"])
    line = f"[{alert['type']}] {alert['message']}"
    if use_color:
        line = f"{_ANSI[color]}{line}{_ANSI['reset']}"
    if ring_bell:
        line = "\a" + line
    try:
        stream.write(line + "\n")
        stream.flush()
    except Exception:
        pass
    return line


def _use_color() -> bool:
    return os.environ.get("NO_COLOR", "") == ""


def _stamp(alert: dict) -> dict:
    out = dict(alert)
    out["timestamp"] = datetime.now().isoformat(timespec="seconds")
    return out


def check_snapshot(snapshot: dict, bets: List[dict],
                    pregame: Dict[Tuple[str, str], float], *,
                    threshold: float,
                    types: Set[str]) -> List[dict]:
    """Run every active detector against ONE snapshot. Returns raw alert dicts.

    No I/O, no state — orchestrator filters by already-fired keys and emits.
    """
    proj_idx: Dict[Tuple[str, str], dict] = {}
    needs_proj = bool({"EDGE_FLIP", "PROJECTION_SHIFT"} & types)
    if needs_proj and snapshot.get("players"):
        try:
            proj_idx = _projection_index(_project_snapshot_rows(snapshot))
        except Exception:
            proj_idx = {}
    out: List[dict] = []
    if "EDGE_FLIP" in types:
        out.extend(detect_edge_flip(bets, pregame, proj_idx))
    if "PROJECTION_SHIFT" in types:
        out.extend(detect_projection_shift(bets, pregame, proj_idx, threshold))
    if "BLOWOUT_RISK" in types:
        out.extend(detect_blowout_risk(snapshot, bets))
    if "FOUL_TROUBLE" in types:
        out.extend(detect_foul_trouble(snapshot, bets))
    if "INACTIVE_LATE" in types:
        out.extend(detect_inactive_late(snapshot, bets))
    return out


def process_once(*, date_str: Optional[str] = None,
                  threshold: float = _DEFAULT_THRESHOLD,
                  types: Optional[Set[str]] = None,
                  project_dir: Optional[str] = None,
                  ring_bell: bool = True,
                  stream=None,
                  snapshot_paths: Optional[List[str]] = None) -> List[dict]:
    """One pass: load snapshots + bets + pregame, run detectors, emit + log."""
    date_str = date_str or _date.today().isoformat()
    types = set(types) if types else set(ALERT_TYPES)
    bets = load_active_bets(date_str, project_dir)
    pregame = load_pregame_predictions(date_str, project_dir)
    if snapshot_paths is None:
        snapshot_paths = list_today_snapshots(date_str=date_str,
                                              project_dir=project_dir)
    fired = load_state(date_str, project_dir)
    use_color = _use_color()
    new_alerts: List[dict] = []
    for path in snapshot_paths:
        snap = load_live_state(path)
        if not snap:
            continue
        for alert in check_snapshot(snap, bets, pregame,
                                     threshold=threshold, types=types):
            key = alert.get("key")
            if not key or key in fired:
                continue
            stamped = _stamp(alert)
            _emit_stdout(stamped, use_color=use_color,
                         ring_bell=ring_bell, stream=stream)
            append_log(date_str, stamped, project_dir)
            fired.add(key)
            new_alerts.append(stamped)
    save_state(date_str, fired, project_dir)
    return new_alerts


def run_daemon(*, interval: float = _DEFAULT_INTERVAL,
                threshold: float = _DEFAULT_THRESHOLD,
                types: Optional[Set[str]] = None,
                project_dir: Optional[str] = None,
                sleep_fn: Callable[[float], None] = time.sleep,
                max_ticks: Optional[int] = None,
                ring_bell: bool = True,
                stream=None) -> int:
    """Poll process_once every `interval` seconds. Tests pass max_ticks."""
    ticks = 0
    while True:
        if max_ticks is not None and ticks >= max_ticks:
            break
        ticks += 1
        try:
            process_once(threshold=threshold, types=types,
                          project_dir=project_dir, ring_bell=ring_bell,
                          stream=stream)
        except Exception as e:  # pragma: no cover (defensive)
            sys.stderr.write(f"[live_alerts] iter {ticks} error: {e}\n")
        if max_ticks is not None and ticks >= max_ticks:
            break
        sleep_fn(interval)
    return ticks


# ── CLI ──────────────────────────────────────────────────────────────────────

def _parse_types(arg: str) -> Set[str]:
    parts = [p.strip().upper() for p in arg.split(",") if p.strip()]
    bad = [p for p in parts if p not in ALERT_TYPES]
    if bad:
        raise argparse.ArgumentTypeError(
            f"unknown alert types: {bad}. valid: {ALERT_TYPES}")
    return set(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true",
                    help="Single check pass then exit (default: daemon mode).")
    ap.add_argument("--interval", type=float, default=_DEFAULT_INTERVAL,
                    help="Daemon poll interval seconds (default 30).")
    ap.add_argument("--threshold", type=float, default=_DEFAULT_THRESHOLD,
                    help="Divergence threshold for PROJECTION_SHIFT (default 3.0).")
    ap.add_argument("--types", type=_parse_types, default=None,
                    help="Comma-separated alert types to enable. "
                         f"Default: all of {ALERT_TYPES}.")
    ap.add_argument("--date", default=None,
                    help="Override date YYYY-MM-DD (default: today).")
    ap.add_argument("--no-bell", action="store_true",
                    help="Suppress the terminal bell character.")
    args = ap.parse_args()

    types = args.types if args.types else set(ALERT_TYPES)
    ring_bell = not args.no_bell
    date_str = args.date or _date.today().isoformat()

    if args.once:
        alerts = process_once(date_str=date_str, threshold=args.threshold,
                               types=types, ring_bell=ring_bell)
        print(f"[live_alerts] one-shot: {len(alerts)} new alert(s).")
        return 0

    print(f"[live_alerts] daemon: interval={args.interval}s "
          f"threshold={args.threshold} types={sorted(types)} date={date_str}",
          flush=True)
    run_daemon(interval=args.interval, threshold=args.threshold,
                types=types, ring_bell=ring_bell)
    return 0


if __name__ == "__main__":
    sys.exit(main())
