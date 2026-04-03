"""Test different matching windows for enrichment recall."""
import csv, json, os, sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

def check_window(game_id, windows=[2, 4, 6, 8, 10]):
    game_dir = os.path.join(PROJECT_DIR, "data", "tracking", game_id)
    shot_csv = os.path.join(game_dir, "shot_log.csv")
    if not os.path.exists(shot_csv): return

    with open(shot_csv, newline="") as f:
        shots = list(csv.DictReader(f))
    ts_vals = [float(r["timestamp"]) for r in shots if r.get("timestamp")]

    pbp_fg = []
    for p in range(1, 4):
        cache = os.path.join(NBA_CACHE, f"pbp_{game_id}_p{p}.json")
        if not os.path.exists(cache): continue
        with open(cache) as f:
            rows = json.load(f)
        offset = (p-1)*720
        pbp_fg.extend([offset + r["game_clock_sec"] for r in rows if r["event_type"] in (1,2)])
    
    if not pbp_fg: return
    
    pbp_fg = [t for t in pbp_fg if t <= max(ts_vals) + 10]
    
    print(f"\nGame {game_id}: {len(pbp_fg)} PBP FG events in range")
    for w in windows:
        matched = sum(1 for pbp_t in pbp_fg if any(abs(ts - pbp_t) <= w for ts in ts_vals))
        print(f"  Window {w}s: {matched}/{len(pbp_fg)} ({matched/len(pbp_fg):.1%})")

for gid in ["0022401123", "0022400430"]:
    check_window(gid)
