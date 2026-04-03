"""Diagnose timestamp mismatch between tracker shot_log and NBA PBP."""
import csv, json, os, sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

def check_game(game_id):
    game_dir = os.path.join(PROJECT_DIR, "data", "tracking", game_id)
    shot_csv = os.path.join(game_dir, "shot_log.csv")
    if not os.path.exists(shot_csv):
        print(f"{game_id}: no shot_log.csv")
        return

    with open(shot_csv, newline="") as f:
        shots = list(csv.DictReader(f))

    ts_vals = []
    for r in shots:
        try:
            ts_vals.append(float(r.get("timestamp", 0)))
        except (ValueError, TypeError):
            pass

    if not ts_vals:
        print(f"{game_id}: no timestamps")
        return

    print(f"\n{'='*60}")
    print(f"Game: {game_id}")
    print(f"  Shot timestamps: {min(ts_vals):.1f}s - {max(ts_vals):.1f}s  ({len(ts_vals)} shots)")

    # Load PBP cache files
    pbp_all = []
    for p in range(1, 5):
        cache = os.path.join(NBA_CACHE, f"pbp_{game_id}_p{p}.json")
        if os.path.exists(cache):
            with open(cache) as f:
                rows = json.load(f)
            # In multi-period mode, game_clock_sec was already offset by the enricher
            # But in the cache, it's still period-relative. offset manually.
            period_offset = sum(12*60 if q <= 4 else 5*60 for q in range(1, p))
            fg = [(period_offset + r["game_clock_sec"], r["event_type"], r["event_desc"][:40])
                  for r in rows if r["event_type"] in (1, 2)]
            pbp_all.extend(fg)
            print(f"  PBP period {p}: {len(fg)} FG events, clocks {min((x[0] for x in fg), default=0):.0f}s - {max((x[0] for x in fg), default=0):.0f}s")

    if not pbp_all:
        print("  No PBP cache found")
        return

    pbp_all.sort()
    pbp_ts = [x[0] for x in pbp_all]

    # How many shots fall within 4s of ANY PBP FG event?
    window = 4.0
    matched = 0
    for ts in ts_vals:
        for ptx in pbp_ts:
            if abs(ts - ptx) <= window:
                matched += 1
                break

    print(f"  Shots matched within {window}s window: {matched}/{len(ts_vals)} ({matched/len(ts_vals):.0%})")
    print(f"  PBP FG range: {min(pbp_ts):.0f}s - {max(pbp_ts):.0f}s")

    # Show first 5 unmatched shots
    unmatched = []
    for ts in ts_vals:
        if not any(abs(ts - ptx) <= window for ptx in pbp_ts):
            unmatched.append(ts)
    if unmatched:
        nearest = []
        for ts in unmatched[:5]:
            closest = min(pbp_ts, key=lambda p: abs(p - ts))
            nearest.append(f"{ts:.0f}s (nearest PBP: {closest:.0f}s, diff={abs(ts-closest):.0f}s)")
        print(f"  First 5 unmatched shots: {nearest}")

for gid in ["0022400430", "0022400537", "0022400909", "0022401123", "0022401156"]:
    check_game(gid)
