"""
diag_pbp_coverage.py  — check real PBP FG coverage per game.

The tracker over-detects shots (false positives from rebounds, dribbles, etc.)
so enriched_pct = matched_shots/total_tracker_shots is inherently low.

REAL metric: how many official PBP FG events were captured by the tracker
(recall), AND does the tracker match most real shots (precision anchored on PBP).
"""
import csv, json, os, sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

def pbp_recall(game_id, window=4.0):
    game_dir = os.path.join(PROJECT_DIR, "data", "tracking", game_id)
    shot_csv  = os.path.join(game_dir, "shot_log.csv")

    if not os.path.exists(shot_csv):
        return None, "no shot_log.csv"

    with open(shot_csv, newline="") as f:
        shots = list(csv.DictReader(f))
    ts_vals = []
    for r in shots:
        try:
            ts_vals.append(float(r.get("timestamp", 0)))
        except: pass

    # Load all PBP FG events (with absolute timestamps)
    pbp_fg = []
    for p in range(1, 5):
        cache = os.path.join(NBA_CACHE, f"pbp_{game_id}_p{p}.json")
        if not os.path.exists(cache):
            continue
        with open(cache) as f:
            rows = json.load(f)
        period_offset = (p - 1) * 12 * 60  # 720s per period
        for r in rows:
            if r["event_type"] in (1, 2):  # made or missed
                pbp_fg.append(period_offset + r["game_clock_sec"])

    if not pbp_fg:
        return None, "no PBP cache"

    # PBP recall: fraction of real PBP FG events that were captured by tracker
    pbp_matched = 0
    for pbp_t in pbp_fg:
        if any(abs(ts - pbp_t) <= window for ts in ts_vals):
            pbp_matched += 1

    recall = pbp_matched / len(pbp_fg)
    return recall, f"PBP_recall={pbp_matched}/{len(pbp_fg)}={recall:.0%}  tracker_shots={len(ts_vals)}"

print("PBP Recall per game (what % of real PBP FG events did tracker capture?):")
print("A recall >= 0.80 means 80% of real shots were detected by the tracker.\n")

for gid in ["0022400430","0022400537","0022400625","0022400909","0022400921","0022401123","0022401156"]:
    recall, detail = pbp_recall(gid)
    status = "PASS" if recall and recall >= 0.80 else "FAIL"
    print(f"  {gid}: [{status}] {detail}")
