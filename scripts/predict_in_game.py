"""predict_in_game.py — cycle 88b (loop 5). Live mid-game stat projector.

Component 4 of the live in-game prediction system. Given the live state of a
game in progress (per-player current pts/reb/ast/etc + game period/clock),
projects each player's FINAL stat line using pace-based extrapolation plus
foul-trouble + blowout penalties.

Why this exists: top sharp prop models update mid-game from observed Q1/Q2/Q3
pace + usage. The cycle-37 pre-game predictor and the cycle-39 slate predictor
never update once tip happens — so we leave a large MAE on the table for
in-play prop markets. This script closes that gap.

Live snapshots are produced by `scripts/live_game_poll.py` (cycle 88a) and
written to `data/live/<game_id>_<timestamp>.json`. Expected schema:

    {
        "game_id":  "0022400123",
        "period":   3,                # 1..4 reg, 5+ OT
        "clock":    "07:24",          # remaining in current period (MM:SS)
        "home":     {"abbrev": "DEN", "score": 78, "fouls_q3": 4, ...},
        "away":     {"abbrev": "LAL", "score": 58, "fouls_q3": 5, ...},
        "players":  [
            {"player_id": 203999, "name": "Nikola Jokic", "team": "DEN",
             "min": 24.5, "pts": 18, "reb": 9, "ast": 7, "fg3m": 1,
             "stl": 1, "blk": 0, "tov": 2, "pf": 2,
             "min_q1": 8.2, "min_q2": 8.4, "min_q3": 8.0, "min_q4": 0.0},
            ...
        ],
    }

Projection logic — pure functions in this module so the unit tests (see
tests/test_predict_in_game.py) can validate the math without nba_api / models:

    clock_played_share   = (12 * (period - 1) + (12 - clock_remaining)) / 48
    remaining_share      = max(0.0, 1.0 - clock_played_share)
    projected_remaining  = current_stat * (remaining_share / clock_played_share)
                                       * pace_factor
                                       * foul_trouble_factor
                                       * blowout_factor
    final_proj           = current_stat + projected_remaining

Bench-player handling: a player whose minutes are all in earlier quarters
(MIN > 0 historically but MIN_q<current>=0 AND on the bench now) projects
from the rate they accumulated WHILE PLAYING — not the elapsed game clock.

CLI:
    python scripts/predict_in_game.py --game-id 0022400123
    python scripts/predict_in_game.py --snapshot data/live/x.json
    python scripts/predict_in_game.py --all-live
    python scripts/predict_in_game.py --snapshot x.json \\
        --save data/predictions/2026-05-24_inplay.csv

Output columns (per player per stat):
    name, team, stat, current, projected_final, pregame_pred (if available)
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from datetime import date as _date
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Reconfigure stdout to UTF-8 on Windows so accented player names don't crash.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")
PRED_DIR = os.path.join(PROJECT_DIR, "data", "predictions")

REG_PERIODS = 4
PERIOD_MIN = 12.0
GAME_MIN = REG_PERIODS * PERIOD_MIN  # 48.0


# ── pure projector functions (testable, no I/O) ──────────────────────────────

def parse_clock(clock_str: str) -> float:
    """Parse 'MM:SS' / 'M:SS' / 'MM.SS' / '0' to remaining float minutes.

    Returns 0.0 if unparseable so end-of-period inputs always degrade
    gracefully into 'no time remaining'.
    """
    if clock_str is None:
        return 0.0
    if isinstance(clock_str, (int, float)):
        return float(clock_str)
    s = str(clock_str).strip()
    if not s:
        return 0.0
    # PBP "PT07M24.00S" ISO 8601 duration support
    if s.upper().startswith("PT"):
        try:
            body = s[2:].upper()
            mins = 0.0
            secs = 0.0
            if "M" in body:
                m_part, _, rest = body.partition("M")
                mins = float(m_part)
                body = rest
            if "S" in body:
                s_part = body.split("S")[0]
                secs = float(s_part)
            return mins + secs / 60.0
        except (TypeError, ValueError):
            return 0.0
    # MM:SS or MM.SS
    sep = ":" if ":" in s else ("." if "." in s else None)
    if sep is None:
        try:
            return float(s)
        except ValueError:
            return 0.0
    head, _, tail = s.partition(sep)
    try:
        mins = float(head)
        secs = float(tail) if tail else 0.0
        return mins + secs / 60.0
    except ValueError:
        return 0.0


def clock_played_share(period: int, clock_remaining_min: float) -> float:
    """Fraction of regulation already elapsed (clamped to (0, 1]).

    OT periods (period > 4) clamp to 1.0 — we still project against a 48-min
    baseline because that's what the pre-game model and prop lines are sized
    against. Late-OT projections become near-equal to current_stat (no
    additional remaining time).
    """
    p = max(1, int(period))
    if p > REG_PERIODS:
        return 1.0
    elapsed = PERIOD_MIN * (p - 1) + (PERIOD_MIN - max(0.0, clock_remaining_min))
    share = elapsed / GAME_MIN
    # Tiny epsilon to avoid div/0 at literal tip (clock=12:00 P1).
    return max(1e-6, min(1.0, share))


def foul_trouble_factor(personal_fouls: float, period: int) -> float:
    """Penalty multiplier applied to remaining-minute projection.

    Bands chosen to roughly match coach behavior: a player with 4 fouls in
    Q3 typically sits 2-4 min; 5 fouls in Q4 sits proactively to protect
    against fouling out. Conservative penalties — easy to refine later
    once we have an empirical signal from in-play vs final actuals.
    """
    try:
        pf = int(personal_fouls or 0)
    except (TypeError, ValueError):
        return 1.0
    p = int(period or 0)
    if p <= 2:
        # Early fouls (Q1/Q2): coach pulls but recovers; mild penalty only at 3+
        if pf >= 3:
            return 0.85
        return 1.0
    if p == 3:
        if pf >= 5:
            return 0.55
        if pf >= 4:
            return 0.70
        return 1.0
    # Q4 / OT
    if pf >= 5:
        return 0.50
    if pf >= 4:
        return 0.80
    return 1.0


def blowout_factor(score_margin: float, period: int, is_star: bool = False) -> float:
    """Reduce projection for star players in a Q4 blowout.

    Stars get pulled when the game is decided (margin > 20 in Q4). Role
    players don't get the same treatment — coaches give them garbage-time
    run. So we only penalize when is_star is true.
    """
    try:
        m = abs(float(score_margin or 0))
    except (TypeError, ValueError):
        return 1.0
    p = int(period or 0)
    if p < 4 or not is_star:
        return 1.0
    if m >= 30:
        return 0.30
    if m >= 25:
        return 0.45
    if m > 20:
        return 0.65
    return 1.0


def project_remaining(
    current_stat: float,
    period: int,
    clock_remaining_min: float,
    *,
    pace_factor: float = 1.0,
    foul_factor: float = 1.0,
    blow_factor: float = 1.0,
    player_clock_played_min: Optional[float] = None,
) -> float:
    """Project remaining stat from current pace.

    Default basis is GAME clock — i.e. assumes the player has been on the
    floor the whole game so far. If `player_clock_played_min` is provided
    AND > 0, we use that as the basis instead (bench player who only
    played in earlier quarters projects from their personal rate).

    For a player who hasn't played at all (player_clock_played_min == 0
    and current_stat == 0), returns 0.0 — we have no signal.
    """
    if player_clock_played_min is not None and player_clock_played_min > 0:
        # Player-clock basis: project the per-minute rate over remaining game min.
        share_played = min(1.0, player_clock_played_min / GAME_MIN)
        share_remaining = max(0.0, 1.0 - share_played)
        if share_played <= 1e-6 or share_remaining <= 1e-6:
            return 0.0
        per_min_rate = current_stat / player_clock_played_min
        # Use a default "expected remaining player minutes" = remaining_share * 36
        # (typical star ceiling), but cap at remaining game minutes.
        # Simpler: project at the rate over the proportional remaining time.
        remaining_proj = (
            current_stat * (share_remaining / share_played)
            * pace_factor * foul_factor * blow_factor
        )
        return max(0.0, remaining_proj)

    share_played = clock_played_share(period, clock_remaining_min)
    share_remaining = max(0.0, 1.0 - share_played)
    if share_played <= 1e-6 or share_remaining <= 1e-6:
        return 0.0
    remaining_proj = (
        current_stat * (share_remaining / share_played)
        * pace_factor * foul_factor * blow_factor
    )
    return max(0.0, remaining_proj)


def project_final(
    current_stat: float,
    period: int,
    clock_remaining_min: float,
    *,
    pace_factor: float = 1.0,
    foul_factor: float = 1.0,
    blow_factor: float = 1.0,
    player_clock_played_min: Optional[float] = None,
) -> float:
    """final_proj = current_stat + project_remaining(...)."""
    rem = project_remaining(
        current_stat, period, clock_remaining_min,
        pace_factor=pace_factor, foul_factor=foul_factor,
        blow_factor=blow_factor,
        player_clock_played_min=player_clock_played_min,
    )
    return float(current_stat) + rem


def is_bench_in_current_period(
    player: dict, period: int, period_elapsed_min: float = 12.0,
) -> bool:
    """True if the player has 0 minutes in the current period AND the
    period has actually been in progress for >= 2 minutes.

    Uses optional `min_q1`/`min_q2`/`min_q3`/`min_q4` fields. If those are
    missing, returns False (we can't tell — assume on-floor and use game
    clock basis).

    The period_elapsed_min guard prevents the false-positive at the start
    of a quarter — at halftime (period=3, clock=12:00) every player has
    min_q3=0 because Q3 hasn't started yet. We only treat them as 'bench'
    once the quarter is actually 2+ minutes deep AND they haven't checked in.
    """
    p = int(period or 0)
    key = f"min_q{p}" if 1 <= p <= 4 else None
    if key is None or key not in player:
        return False
    if period_elapsed_min < 2.0:
        return False
    try:
        return float(player.get(key, 0) or 0) <= 0.0
    except (TypeError, ValueError):
        return False


# ── snapshot loading + project-a-snapshot orchestration ──────────────────────

def _num(v, default: float = 0.0) -> float:
    """Best-effort float cast — None / non-numeric → default."""
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load_snapshot(path: str) -> dict:
    """Parse snapshot JSON. Missing fields tolerated — projector handles defaults."""
    with open(path, "r", encoding="utf-8") as fh:
        snap = json.load(fh)
    if not isinstance(snap, dict):
        raise ValueError(f"snapshot {path}: top-level must be an object")
    snap.setdefault("players", [])
    snap.setdefault("period", 1)
    snap.setdefault("clock", "12:00")
    snap.setdefault("home", {})
    snap.setdefault("away", {})
    return snap


def latest_snapshot_for_game(game_id: str, live_dir: str = LIVE_DIR) -> Optional[str]:
    """Return path to most recent snapshot for `game_id`, or None if absent."""
    pat = os.path.join(live_dir, f"{game_id}_*.json")
    matches = sorted(glob.glob(pat))
    return matches[-1] if matches else None


def project_snapshot(
    snap: dict,
    *,
    pace_factor: float = 1.0,
    star_threshold_min: float = 30.0,
) -> List[Dict]:
    """Project final-stat lines for every player in a snapshot.

    Returns a list of dicts:
        {name, team, player_id, stat, current, projected_final,
         period, foul_factor, blow_factor}

    Stars (for blowout detection) defined as players with cumulative
    MIN > star_threshold_min projected across the game (rough proxy =
    current MIN scaled to 48 min). Avoids a separate roster lookup.
    """
    period = int(snap.get("period") or 1)
    clock_rem = parse_clock(snap.get("clock"))
    home = snap.get("home") or {}
    away = snap.get("away") or {}
    home_score = _num(home.get("score"))
    away_score = _num(away.get("score"))
    margin = home_score - away_score  # signed

    out: List[Dict] = []
    for p in snap.get("players") or []:
        name = p.get("name") or f"pid_{p.get('player_id')}"
        team = p.get("team") or ""
        pid = p.get("player_id")
        cur_min = _num(p.get("min"))
        pf = _num(p.get("pf"))
        ff = foul_trouble_factor(pf, period)
        # Star proxy: project min to 48; >= star_threshold_min counts.
        share_played_game = clock_played_share(period, clock_rem)
        proj_min = (cur_min / share_played_game) if share_played_game > 0 else cur_min
        is_star = proj_min >= star_threshold_min
        # Blowout factor uses absolute margin AND we apply only to the
        # leading-side stars (winning teams sit stars more aggressively).
        team_is_leading = (
            (team == home.get("abbrev") and margin > 0) or
            (team == away.get("abbrev") and margin < 0)
        )
        bf = blowout_factor(abs(margin), period, is_star=(is_star and team_is_leading))

        period_elapsed_min = max(0.0, PERIOD_MIN - clock_rem)
        bench_now = is_bench_in_current_period(
            p, period, period_elapsed_min=period_elapsed_min,
        )
        player_basis = cur_min if bench_now else None

        for stat in STATS:
            cur = _num(p.get(stat))
            final = project_final(
                cur, period, clock_rem,
                pace_factor=pace_factor,
                foul_factor=ff, blow_factor=bf,
                player_clock_played_min=player_basis,
            )
            out.append({
                "name": name, "team": team, "player_id": pid,
                "stat": stat, "current": cur, "projected_final": final,
                "period": period, "foul_factor": ff, "blow_factor": bf,
                "bench_in_current_period": bench_now,
            })
    return out


# ── pre-game prediction join (optional reference) ────────────────────────────

def load_pregame_predictions(date_iso: str) -> Dict[Tuple[int, str], float]:
    """Load data/predictions/<date>.csv as {(player_id, stat): pred}.

    Returns empty dict on missing file / unreadable rows. Used purely as a
    REFERENCE column on the in-play output — we never blend pre-game into
    the in-play projection here.
    """
    path = os.path.join(PRED_DIR, f"{date_iso}.csv")
    out: Dict[Tuple[int, str], float] = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, "r", encoding="utf-8") as fh:
            r = csv.DictReader(fh)
            for row in r:
                try:
                    pid = int(row["player_id"])
                    stat = str(row["stat"]).lower()
                    pred = float(row["pred"])
                except (KeyError, TypeError, ValueError):
                    continue
                out[(pid, stat)] = pred
    except Exception:
        pass
    return out


# ── output formatting + ledger save ──────────────────────────────────────────

def format_stdout(rows: List[Dict],
                  pregame: Optional[Dict[Tuple[int, str], float]] = None) -> str:
    """Render projection rows as a multi-line stdout report grouped by player."""
    if not rows:
        return "(no projections — empty snapshot)\n"
    pregame = pregame or {}
    # Group by (player_id or name)
    by_player: Dict[str, List[Dict]] = {}
    order: List[str] = []
    for r in rows:
        key = f"{r['name']} ({r['team']})"
        if key not in by_player:
            by_player[key] = []
            order.append(key)
        by_player[key].append(r)

    lines: List[str] = []
    period = rows[0].get("period", 0)
    lines.append(f"\n  IN-GAME PROJECTIONS  —  period {period}")
    lines.append(f"  {'player':30s} {'stat':5s} {'cur':>6s} {'proj':>7s} {'pre':>7s}")
    lines.append("  " + "-" * 60)
    for key in order:
        for r in by_player[key]:
            pid = r.get("player_id")
            pre = pregame.get((int(pid), r["stat"])) if pid is not None else None
            pre_s = f"{pre:.2f}" if pre is not None else "  —  "
            lines.append(
                f"  {key[:30]:30s} {r['stat'].upper():5s} "
                f"{r['current']:>6.1f} {r['projected_final']:>7.2f} {pre_s:>7s}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def save_inplay_csv(
    out_path: str, snap: dict, rows: List[Dict],
    pregame: Optional[Dict[Tuple[int, str], float]] = None,
) -> int:
    """Write one row per (player, stat) to a cycle-80-style ledger variant.

    Schema:
        date, game_id, player_id, player, team, stat,
        current, projected_final, pregame_pred,
        period, foul_factor, blow_factor
    """
    pregame = pregame or {}
    game_id = snap.get("game_id", "")
    date_str = _date.today().isoformat()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    file_exists = os.path.exists(out_path) and os.path.getsize(out_path) > 0
    n = 0
    with open(out_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if not file_exists:
            w.writerow([
                "date", "game_id", "player_id", "player", "team",
                "stat", "current", "projected_final", "pregame_pred",
                "period", "foul_factor", "blow_factor",
            ])
        for r in rows:
            pid = r.get("player_id")
            pre = pregame.get((int(pid), r["stat"])) if pid is not None else None
            pre_s = f"{pre:.4f}" if pre is not None else ""
            w.writerow([
                date_str, game_id, pid, r["name"], r["team"],
                r["stat"], f"{r['current']:.2f}", f"{r['projected_final']:.4f}",
                pre_s, r.get("period", ""),
                f"{r.get('foul_factor', 1.0):.3f}",
                f"{r.get('blow_factor', 1.0):.3f}",
            ])
            n += 1
    return n


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--game-id", help="NBA game_id; loads latest snapshot")
    grp.add_argument("--snapshot", help="Explicit path to snapshot JSON")
    grp.add_argument("--all-live", action="store_true",
                     help="Project every distinct game_id in data/live/")
    ap.add_argument("--pace", type=float, default=1.0,
                    help="Pace factor multiplier (default 1.0)")
    ap.add_argument("--save", nargs="?", const="__default__", default=None,
                    help="Append projections to a ledger CSV. Bare flag → "
                         "data/predictions/<today>_inplay.csv. With arg → that path.")
    args = ap.parse_args()

    paths: List[str] = []
    if args.snapshot:
        paths = [args.snapshot]
    elif args.game_id:
        p = latest_snapshot_for_game(args.game_id)
        if p is None:
            print(f"  [fail] no snapshot for game_id={args.game_id} in {LIVE_DIR}")
            return 2
        paths = [p]
    else:  # --all-live: one path per distinct game_id (latest snapshot each)
        seen = set()
        for fp in sorted(glob.glob(os.path.join(LIVE_DIR, "*.json"))):
            base = os.path.basename(fp)
            gid = base.split("_")[0]
            if gid in seen:
                continue
            seen.add(gid)
            latest = latest_snapshot_for_game(gid)
            if latest:
                paths.append(latest)
        if not paths:
            print(f"  [fail] no snapshots found in {LIVE_DIR}")
            return 2

    pregame = load_pregame_predictions(_date.today().isoformat())

    save_path: Optional[str] = None
    if args.save is not None:
        save_path = (os.path.join(PRED_DIR,
                                   f"{_date.today().isoformat()}_inplay.csv")
                     if args.save == "__default__" else args.save)

    total_written = 0
    for p in paths:
        try:
            snap = load_snapshot(p)
        except Exception as e:
            print(f"  [warn] could not load {p}: {e}")
            continue
        rows = project_snapshot(snap, pace_factor=args.pace)
        gid = snap.get("game_id", "?")
        away = (snap.get("away") or {}).get("abbrev", "")
        home = (snap.get("home") or {}).get("abbrev", "")
        print(f"\n  === {away} @ {home}  game_id={gid}  "
              f"period={snap.get('period')}  clock={snap.get('clock')} ===")
        print(format_stdout(rows, pregame))
        if save_path is not None:
            total_written += save_inplay_csv(save_path, snap, rows, pregame)

    if save_path is not None:
        print(f"  Wrote {total_written} in-play projection rows → {save_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
