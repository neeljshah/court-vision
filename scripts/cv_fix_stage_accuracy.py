"""
cv_fix_stage_accuracy.py — REALLY find out when the prop model is most accurate.

For each game with PBP/box snapshots, project every player's FINAL stat at each
quarter break (pregame proxy = end-Q1 baseline excluded), compare to the true
final, and report MAE by stage. Answers: does the in-play projection get sharper
as the game progresses (so betting later is "smarter"), per stat?

This is the empirical "when to bet" signal — projection accuracy by stage. (Betting
EDGE also depends on how efficient the LINES are at each stage; this isolates the
model's own accuracy.)
"""
from __future__ import annotations
import sys, os, glob, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.courtvision_router import (  # noqa: E402
    _end_of_quarter_snapshots, _project_at_snapshot_map, _et_date_from_iso)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def final_actuals(gid: str) -> dict:
    """Max-total FINAL snapshot's player stats (true final, robust to non-monotonic snaps)."""
    best_total, amap = -1, {}
    for p in glob.glob(f"data/live/{gid}_*.json"):
        try:
            s = json.load(open(p))
        except Exception:
            continue
        if "FINAL" not in str(s.get("game_status") or "").upper():
            continue
        try:
            tot = int(s.get("away_score") or 0) + int(s.get("home_score") or 0)
        except (TypeError, ValueError):
            tot = 0
        if tot <= best_total:
            continue
        m = {}
        for pl in (s.get("players") or []):
            nm = (pl.get("name") or "").lower()
            if not nm:
                continue
            for st in STATS:
                v = pl.get(st)
                if v is not None:
                    try:
                        m[(nm, st)] = float(v)
                    except (TypeError, ValueError):
                        pass
        if m:
            best_total, amap = tot, m
    return amap


def main():
    gids = sys.argv[1:] or ["0042500315", "0042500316"]
    from collections import defaultdict
    agg = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))  # period -> stat -> [abs_err_sum, n]
    for gid in gids:
        actuals = final_actuals(gid)
        if not actuals:
            print(f"{gid}: no final actuals; skip")
            continue
        eoq = _end_of_quarter_snapshots(gid)
        print(f"\n{gid}: final actuals for {len(set(k[0] for k in actuals))} players")
        for period in (1, 2, 3):
            snap = eoq.get(period)
            if not snap:
                print(f"  Q{period}: no snapshot")
                continue
            proj = _project_at_snapshot_map(snap)
            errs = defaultdict(lambda: [0.0, 0])
            for (nm, st), pv in proj.items():
                av = actuals.get((nm, st))
                if av is None:
                    continue
                errs[st][0] += abs(pv - av)
                errs[st][1] += 1
                agg[period][st][0] += abs(pv - av)
                agg[period][st][1] += 1
            line = "  ".join(f"{st}={errs[st][0]/errs[st][1]:.2f}(n{errs[st][1]})"
                             for st in STATS if errs[st][1])
            print(f"  Q{period}: {line}")

    print("\n=== AGGREGATE projection MAE by stage (lower = sharper) ===")
    for period in (1, 2, 3):
        parts = []
        for st in STATS:
            s, n = agg[period][st]
            if n:
                parts.append(f"{st} {s/n:.2f}")
        print(f"End Q{period}:  " + "  ".join(parts))
    # overall (pts+reb+ast) per stage
    print("\n=== headline: PTS MAE by stage ===")
    for period in (1, 2, 3):
        s, n = agg[period]["pts"]
        if n:
            print(f"  End Q{period}: pts MAE {s/n:.2f}  (n={n})")


if __name__ == "__main__":
    main()
