#!/usr/bin/env python3
"""
audit_completed.py — Real quality audit for completed games.

Goes beyond self-reported metrics to surface ground-truth signal:
 - Ball coordinate sanity (catches homography corruption)
 - Player count per frame (broadcast detection coverage)
 - x_norm spread (homography mapping the full court vs. half)
 - Possession count (NBA games are 180–240 possessions; way over = false-positive detection)
 - Shot detection recall vs NBA Stats PBP (the real accuracy signal)
 - Possession enrichment % (how many tracker possessions match PBP)

Usage:
    python scripts/audit_completed.py                        # all completed games
    python scripts/audit_completed.py --game 0022500054      # specific game
    python scripts/audit_completed.py --tracking-dir DIR     # alt root
    python scripts/audit_completed.py --json                 # machine-readable

Exit code: 0 if all games pass thresholds; 1 if any are flagged BAD.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
TRACKING_ROOT = ROOT / "data" / "tracking"

# Real-data thresholds — tighter than the gate, surfaces accuracy issues.
T_BALL_OOB_MAX        = 0   # any OOB coord = data corruption (post-fix should be 0)
T_PLAYERS_PER_FRAME   = 4.0 # broadcast usually has 5–7; below 4 = detector dropout
T_XNORM_SPREAD_MIN    = 0.5 # healthy game spans most of court width
T_POSSESSIONS_MIN     = 150 # NBA games average ~200 possessions; <150 = undercounted
T_POSSESSIONS_MAX     = 280 # >280 = false-positive possession changes
T_PBP_SHOT_RECALL_MIN = 25.0  # below this = shot detection failing too often
T_POSS_ENRICH_PCT_MIN = 70.0  # PBP coverage of tracker possessions


def _ball_audit(d: Path) -> Dict:
    bt = d / "ball_tracking.csv"
    if not bt.exists():
        return {"ball_rows": 0, "detected_pct": 0.0, "oob": 0,
                "x_max": 0.0, "y_max": 0.0}
    rows = list(csv.DictReader(bt.open(encoding="utf-8", errors="replace")))
    xs, ys = [], []
    det = 0
    oob = 0
    for r in rows:
        if str(r.get("detected", "")).strip() == "1":
            det += 1
        try:
            x = float(r.get("ball_x2d") or 0)
            y = float(r.get("ball_y2d") or 0)
            xs.append(x); ys.append(y)
            if x >= 6000 or x < -100 or y >= 6000 or y < -100:
                oob += 1
        except (ValueError, TypeError):
            pass
    return {
        "ball_rows": len(rows),
        "detected_pct": round(100.0 * det / max(len(rows), 1), 1),
        "oob": oob,
        "x_max": max(xs) if xs else 0.0,
        "y_max": max(ys) if ys else 0.0,
    }


def _player_audit(d: Path) -> Dict:
    td = d / "tracking_data.csv"
    if not td.exists():
        return {"frames": 0, "players_per_frame": 0.0,
                "x_norm_spread": 0.0, "y_norm_spread": 0.0}
    from collections import Counter
    rows = list(csv.DictReader(td.open(encoding="utf-8", errors="replace")))
    per = Counter(r.get("frame", "") for r in rows)
    cnts = list(per.values())
    xn = [float(r["x_norm"]) for r in rows
          if r.get("x_norm") not in (None, "", "nan")]
    yn = [float(r["y_norm"]) for r in rows
          if r.get("y_norm") not in (None, "", "nan")]
    return {
        "frames": len(per),
        "players_per_frame": round(statistics.mean(cnts), 2) if cnts else 0.0,
        "x_norm_spread": round(max(xn) - min(xn), 3) if xn else 0.0,
        "y_norm_spread": round(max(yn) - min(yn), 3) if yn else 0.0,
    }


def _possession_audit(d: Path) -> Dict:
    p = d / "possessions.csv"
    if not p.exists():
        return {"possession_count": 0}
    rows = list(csv.DictReader(p.open(encoding="utf-8", errors="replace")))
    return {"possession_count": len(rows)}


_PBP_RECALL_RE  = re.compile(r"PBP recall.*?(\d+)/(\d+) = ([\d.]+)%.*tracker shots:\s*(\d+)")
_ENRICH_RE      = re.compile(r"enriched_pct: (\d+)/(\d+) = ([\d.]+)%")


def _runlog_audit(d: Path) -> Dict:
    log = d / "run.log"
    if not log.exists():
        return {"pbp_shot_recall_pct": None, "tracker_shots": None,
                "pbp_total_fg": None, "poss_enrich_pct": None}
    txt = log.read_text(encoding="utf-8", errors="replace")
    m = _PBP_RECALL_RE.search(txt)
    e = _ENRICH_RE.search(txt)
    out = {"pbp_shot_recall_pct": None, "tracker_shots": None,
           "pbp_total_fg": None, "poss_enrich_pct": None}
    if m:
        out["pbp_total_fg"]       = int(m.group(2))
        out["pbp_shot_recall_pct"] = float(m.group(3))
        out["tracker_shots"]      = int(m.group(4))
    if e:
        out["poss_enrich_pct"] = float(e.group(3))
    return out


def audit_game(game_id: str, root: Path) -> Dict:
    d = root / game_id
    if not d.is_dir():
        return {"game_id": game_id, "error": "missing tracking dir"}
    result = {"game_id": game_id}
    result.update(_ball_audit(d))
    result.update(_player_audit(d))
    result.update(_possession_audit(d))
    result.update(_runlog_audit(d))
    # Score against thresholds.
    flags = []
    if result["oob"] > T_BALL_OOB_MAX:
        flags.append(f"ball_oob={result['oob']}")
    if result["players_per_frame"] < T_PLAYERS_PER_FRAME:
        flags.append(f"low_player_count={result['players_per_frame']}")
    if result["x_norm_spread"] < T_XNORM_SPREAD_MIN:
        flags.append(f"narrow_court_mapping (x_norm spread {result['x_norm_spread']})")
    pc = result["possession_count"]
    if pc and (pc < T_POSSESSIONS_MIN or pc > T_POSSESSIONS_MAX):
        flags.append(f"possession_count_outside_normal={pc}")
    if result["pbp_shot_recall_pct"] is not None and result["pbp_shot_recall_pct"] < T_PBP_SHOT_RECALL_MIN:
        flags.append(f"low_shot_recall={result['pbp_shot_recall_pct']}%")
    if result["poss_enrich_pct"] is not None and result["poss_enrich_pct"] < T_POSS_ENRICH_PCT_MIN:
        flags.append(f"low_poss_enrich={result['poss_enrich_pct']}%")
    result["flags"] = flags
    # 3 tiers: CLEAN (no flags), USABLE (flags but not corrupt), BAD (ball OOB or no data)
    if "ball_oob" in " ".join(flags) or "missing" in result.get("error", ""):
        result["tier"] = "BAD"
    elif flags:
        result["tier"] = "USABLE"
    else:
        result["tier"] = "CLEAN"
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", help="single game id; otherwise audits all in tracking dir")
    ap.add_argument("--tracking-dir", default=str(TRACKING_ROOT))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(args.tracking_dir)
    games: List[str]
    if args.game:
        games = [args.game]
    else:
        games = sorted(p.name for p in root.iterdir()
                       if p.is_dir() and (p / "tracking_data.csv").exists())
    results = [audit_game(g, root) for g in games]
    bad = sum(1 for r in results if r["tier"] == "BAD")

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'game':12} {'tier':6} {'ball%':>6} {'OOB':>4} {'plyr/fr':>8} {'xspread':>8} {'poss':>5} {'shot_recall':>12} {'enrich':>7}  flags")
        for r in results:
            print(f"{r['game_id']:12} "
                  f"{r.get('tier','?'):6} "
                  f"{r.get('detected_pct',0):>6.1f} "
                  f"{r.get('oob',0):>4} "
                  f"{r.get('players_per_frame',0):>8.2f} "
                  f"{r.get('x_norm_spread',0):>8.3f} "
                  f"{r.get('possession_count',0):>5} "
                  f"{(str(r.get('pbp_shot_recall_pct',''))+ '%' if r.get('pbp_shot_recall_pct') is not None else '-'):>12} "
                  f"{(str(r.get('poss_enrich_pct',''))+ '%' if r.get('poss_enrich_pct') is not None else '-'):>7}  "
                  f"{', '.join(r.get('flags', []))}")
        total = len(results)
        clean = sum(1 for r in results if r["tier"] == "CLEAN")
        usable = sum(1 for r in results if r["tier"] == "USABLE")
        print(f"\n  {clean} CLEAN  +  {usable} USABLE  +  {bad} BAD  =  {total} total")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
