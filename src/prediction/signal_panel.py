"""signal_panel.py — Live Signal Engine panel data builder.

Surfaces per-player fired signals (TOV spike, cold scoring, foul trouble,
usage shift, etc.) from the in-game snapshot for display on the /tonight page.

This is SCOUTING intelligence (accuracy infrastructure), NOT a projection tilt.
The signals are computed from live snapshot data vs a player's own season
gamelog baseline, identical to the logic in scripts/_scratch_signal_detector.py.

Gate: CV_SIGNAL_PANEL=1 (default OFF).
When OFF: _build_signal_panel() returns None, byte-identical to pre-feature.

Usage from the router:
    from src.prediction.signal_panel import build_signal_panel
    panel = build_signal_panel(snapshot_dict, root_dir=str(ROOT))
    # panel is None when flag is off or snapshot is missing
"""
from __future__ import annotations

import os
import json
import glob as _glob
from statistics import mean, pstdev
from typing import Optional

# ---------------------------------------------------------------------------
# Signal codes and severity labels
# ---------------------------------------------------------------------------
SIGNAL_LABELS: dict[str, str] = {
    "TOV_SPIKE":     "TOV spike",
    "COLD_SCORING":  "cold",
    "THREE_DROUGHT": "3pt drought",
    "FOUL_TROUBLE":  "foul trouble",
    "REB_UP":        "REB surge",
    "REB_DOWN":      "REB drop",
    "AST_UP":        "AST surge",
    "AST_DOWN":      "AST drop",
    "HOT_SCORING":   "hot",
    "STOCKS_UP":     "stocks up",
}

# Stats present in both the live snapshot and gamelogs
_STATS = ["pts", "reb", "ast", "tov", "fg3m", "stl", "blk", "pf"]
_GAMELOG_KEY: dict[str, str] = {
    "pts": "PTS", "reb": "REB", "ast": "AST", "tov": "TOV",
    "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "pf": "PF",
}
_SEASONS = ["2025-26", "2024-25"]

_BASE_CACHE: dict = {}


# ---------------------------------------------------------------------------
# Internal helpers (mirrors _scratch_signal_detector.py logic exactly)
# ---------------------------------------------------------------------------

def _load_baseline(pid: str | int, gamelog_dir: str) -> Optional[dict]:
    """Per-player baseline from gamelog. Returns dict or None if unavailable."""
    key = str(pid)
    if key in _BASE_CACHE:
        return _BASE_CACHE[key]
    rows = None
    used_season = None
    for season in _SEASONS:
        fp = os.path.join(gamelog_dir, f"gamelog_{pid}_{season}.json")
        if os.path.exists(fp):
            try:
                data = json.load(open(fp, encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, list) and data:
                rows = data
                used_season = season
                break
    if not rows:
        _BASE_CACHE[key] = None
        return None

    games = []
    for r in rows:
        try:
            mn = float(r.get("MIN") or 0)
        except Exception:
            mn = 0.0
        if mn >= 4.0:
            games.append((r, mn))
    if len(games) < 2:
        _BASE_CACHE[key] = None
        return None

    base: dict = {
        "n_games": len(games),
        "season": used_season,
        "mpg": mean([m for _, m in games]),
    }
    for st in _STATS:
        gk = _GAMELOG_KEY[st]
        pg_vals: list[float] = []
        p36_vals: list[float] = []
        for r, mn in games:
            try:
                v = float(r.get(gk) or 0)
            except Exception:
                v = 0.0
            pg_vals.append(v)
            if mn > 0:
                p36_vals.append(v * 36.0 / mn)
        base[st] = {
            "pg_mean": mean(pg_vals),
            "pg_std": pstdev(pg_vals) if len(pg_vals) > 1 else 0.0,
            "p36_mean": mean(p36_vals),
            "p36_std": pstdev(p36_vals) if len(p36_vals) > 1 else 0.0,
        }
    _BASE_CACHE[key] = base
    return base


def _z(obs: float, mu: float, sd: float, floor: float) -> float:
    sd_eff = max(sd, floor)
    return (obs - mu) / sd_eff if sd_eff > 0 else 0.0


def _conf(n_games: int, game_min: float) -> str:
    if n_games >= 15 and game_min >= 18:
        return "high"
    if n_games >= 8 and game_min >= 12:
        return "med"
    return "low"


def _detect_signals(
    player: dict,
    base: Optional[dict],
    period: int | str,
    min_game_min: float = 8.0,
    min_base_games: int = 5,
) -> list[dict]:
    """Detect fired signals for one player. Returns list of signal dicts."""
    gm = float(player.get("min") or 0.0)
    if gm < min_game_min:
        return []
    if base is None or base["n_games"] < min_base_games:
        return []

    conf = _conf(base["n_games"], gm)
    out: list[dict] = []

    def obs36(st: str) -> float:
        v = float(player.get(st) or 0.0)
        return v * 36.0 / gm if gm > 0 else 0.0

    # 1. TURNOVER SPIKE
    tov36 = obs36("tov")
    bt = base["tov"]
    z = _z(tov36, bt["p36_mean"], bt["p36_std"], floor=1.0)
    if z >= 1.5 and float(player.get("tov") or 0) >= 3:
        out.append(dict(
            code="TOV_SPIKE", stat="tov", severity=z,
            obs=round(tov36, 1), base=round(bt["p36_mean"], 1), z=round(z, 2),
            raw=int(player.get("tov") or 0),
            note="TOV/36 well above own norm — trapped/doubled, forcing, fatigue",
            conf=conf,
        ))

    # 2. COLD SCORING
    pts36 = obs36("pts")
    bp = base["pts"]
    z_pts = _z(pts36, bp["p36_mean"], bp["p36_std"], floor=4.0)
    if z_pts <= -1.3 and bp["p36_mean"] >= 12.0:
        out.append(dict(
            code="COLD_SCORING", stat="pts", severity=abs(z_pts),
            obs=round(pts36, 1), base=round(bp["p36_mean"], 1), z=round(z_pts, 2),
            raw=int(player.get("pts") or 0),
            note="Scoring rate well below own norm — rhythm/flow read",
            conf=conf,
        ))

    # 2b. THREE-POINT DROUGHT (for shooters)
    fg3_36 = obs36("fg3m")
    b3 = base["fg3m"]
    if b3["p36_mean"] >= 1.8 and gm >= 18 and int(player.get("fg3m") or 0) == 0:
        exp_makes = b3["p36_mean"] * gm / 36.0
        if exp_makes >= 1.3:
            out.append(dict(
                code="THREE_DROUGHT", stat="fg3m", severity=exp_makes,
                obs=0.0, base=round(b3["p36_mean"], 1), z=round(-exp_makes, 2),
                raw=0,
                note=f"0 made 3s with ~{exp_makes:.1f} expected — cold from deep",
                conf=conf,
            ))

    # 3. FOUL TROUBLE
    pf = int(player.get("pf") or 0)
    elapsed = max(gm, 1.0)
    foul_pace_48 = pf * 48.0 / elapsed
    period_i = int(period or 0)
    if pf >= 4 and period_i <= 4:
        risk = pf / 6.0
        out.append(dict(
            code="FOUL_TROUBLE", stat="pf", severity=risk * 3,
            obs=pf, base=round(base["pf"]["pg_mean"], 1), z=round(foul_pace_48, 1),
            raw=pf,
            note=f"{pf} PF in P{period_i} — foul-out/minutes-loss risk (pace {foul_pace_48:.1f} PF/48)",
            conf=conf,
        ))

    # 4. REBOUND DEVIATION
    reb36 = obs36("reb")
    br = base["reb"]
    z_reb = _z(reb36, br["p36_mean"], br["p36_std"], floor=2.0)
    if abs(z_reb) >= 1.7 and br["p36_mean"] >= 5.0:
        code = "REB_UP" if z_reb > 0 else "REB_DOWN"
        direction = "surge" if z_reb > 0 else "collapse"
        out.append(dict(
            code=code, stat="reb", severity=abs(z_reb),
            obs=round(reb36, 1), base=round(br["p36_mean"], 1), z=round(z_reb, 2),
            raw=int(player.get("reb") or 0),
            note=f"Rebound rate {direction} vs own norm (matchup/scheme/box-out read)",
            conf=conf,
        ))

    # 5. ASSIST DEVIATION
    ast36 = obs36("ast")
    ba = base["ast"]
    z_ast = _z(ast36, ba["p36_mean"], ba["p36_std"], floor=1.5)
    if abs(z_ast) >= 1.7 and ba["p36_mean"] >= 4.0:
        code = "AST_UP" if z_ast > 0 else "AST_DOWN"
        direction = "surge" if z_ast > 0 else "collapse"
        out.append(dict(
            code=code, stat="ast", severity=abs(z_ast),
            obs=round(ast36, 1), base=round(ba["p36_mean"], 1), z=round(z_ast, 2),
            raw=int(player.get("ast") or 0),
            note=f"Playmaking {direction} vs own norm (live role/coverage read)",
            conf=conf,
        ))

    # 6. HOT SCORING
    z_hot = _z(pts36, bp["p36_mean"], bp["p36_std"], floor=4.0)
    if z_hot >= 1.8 and bp["p36_mean"] >= 10.0:
        out.append(dict(
            code="HOT_SCORING", stat="pts", severity=z_hot,
            obs=round(pts36, 1), base=round(bp["p36_mean"], 1), z=round(z_hot, 2),
            raw=int(player.get("pts") or 0),
            note="Scoring rate well above own norm — hot hand/favorable matchup",
            conf=conf,
        ))

    # 7. STOCKS SURGE
    stk36 = obs36("stl") + obs36("blk")
    base_stk = base["stl"]["p36_mean"] + base["blk"]["p36_mean"]
    if base_stk > 0:
        ratio = stk36 / base_stk
        raw_stk = int(player.get("stl") or 0) + int(player.get("blk") or 0)
        if ratio >= 2.0 and raw_stk >= 3:
            out.append(dict(
                code="STOCKS_UP", stat="stl+blk", severity=ratio,
                obs=round(stk36, 1), base=round(base_stk, 1), z=round(ratio, 2),
                raw=raw_stk,
                note="Steals+blocks elevated — active defensively/disruptive",
                conf=conf,
            ))

    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_signal_panel(
    snapshot: dict,
    root_dir: str,
    min_game_min: float = 8.0,
    min_base_games: int = 5,
) -> Optional[dict]:
    """Build a per-player signal panel from a live snapshot dict.

    Returns a dict with keys:
        game_status: str
        period: int
        clock: str
        players: list of {
            player_id, name, team, min, pts, reb, ast, tov, pf,
            signals: list of signal dicts,
        }
        n_players_flagged: int
        n_signals_total: int

    Returns None if CV_SIGNAL_PANEL is not "1" or if snapshot is invalid.
    """
    if os.environ.get("CV_SIGNAL_PANEL", "0") != "1":
        return None
    if not isinstance(snapshot, dict):
        return None
    players_raw = snapshot.get("players")
    if not isinstance(players_raw, list) or not players_raw:
        return None

    gamelog_dir = os.path.join(root_dir, "data", "nba")
    period = snapshot.get("period", 0)

    # Sort by minutes desc (rotation players first)
    players_sorted = sorted(
        players_raw,
        key=lambda p: -float(p.get("min") or 0.0),
    )

    out_players: list[dict] = []
    for p in players_sorted:
        gm = float(p.get("min") or 0.0)
        if gm < min_game_min:
            continue
        pid = p.get("player_id")
        base = _load_baseline(pid, gamelog_dir) if pid is not None else None
        sigs = _detect_signals(p, base, period, min_game_min, min_base_games)
        # Include player only if signals fired
        if sigs:
            out_players.append({
                "player_id": pid,
                "name": p.get("name") or p.get("player_name") or "?",
                "team": (p.get("team") or "").upper(),
                "min": round(gm, 1),
                "pts": int(p.get("pts") or 0),
                "reb": int(p.get("reb") or 0),
                "ast": int(p.get("ast") or 0),
                "tov": int(p.get("tov") or 0),
                "pf": int(p.get("pf") or 0),
                "signals": sorted(sigs, key=lambda s: -s["severity"]),
            })

    n_total = sum(len(pl["signals"]) for pl in out_players)
    return {
        "game_status": snapshot.get("game_status", ""),
        "period": period,
        "clock": snapshot.get("clock", ""),
        "away_team": snapshot.get("away_team", ""),
        "home_team": snapshot.get("home_team", ""),
        "players": out_players,
        "n_players_flagged": len(out_players),
        "n_signals_total": n_total,
    }


def build_signal_panel_from_live_dir(
    gid: str,
    root_dir: str,
    min_game_min: float = 8.0,
    min_base_games: int = 5,
) -> Optional[dict]:
    """Load the latest snapshot for a game id and return the signal panel.

    Convenience wrapper used by the /tonight router.
    Returns None if no snapshot found or flag is off.
    """
    if os.environ.get("CV_SIGNAL_PANEL", "0") != "1":
        return None
    live_dir = os.path.join(root_dir, "data", "live")
    if not os.path.isdir(live_dir):
        return None
    pattern = os.path.join(live_dir, f"{gid}_*.json")
    paths = sorted(_glob.glob(pattern))
    if not paths:
        return None
    try:
        snap = json.load(open(paths[-1], encoding="utf-8"))
    except Exception:
        return None
    # Basic validity check: must have players list with player_id
    if not isinstance(snap.get("players"), list):
        return None
    if not snap.get("players") or "player_id" not in snap["players"][0]:
        return None
    return build_signal_panel(snap, root_dir, min_game_min, min_base_games)
