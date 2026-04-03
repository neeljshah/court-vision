"""Quick check of enrichment status for all processed games."""
import csv
import os

TRACKING = os.path.join(os.path.dirname(__file__), "..", "data", "tracking")

for gid in sorted(os.listdir(TRACKING)):
    gdir = os.path.join(TRACKING, gid)
    if not os.path.isdir(gdir) or not gid.isdigit() or len(gid) != 10:
        continue
    shot_csv = os.path.join(gdir, "shot_log.csv")
    enriched_csv = os.path.join(gdir, "shot_log_enriched.csv")
    if not os.path.exists(shot_csv):
        print(f"{gid}: no shot_log.csv")
        continue
    
    with open(shot_csv, newline="") as f:
        rows = list(csv.DictReader(f))
    total = len(rows)
    if total == 0:
        print(f"{gid}: 0 shots")
        continue
    
    made_filled = sum(1 for r in rows if r.get("made", "").strip() not in ("", "nan", "None"))
    
    # Get timestamp range
    timestamps = []
    for r in rows:
        try:
            timestamps.append(float(r.get("timestamp", 0)))
        except (ValueError, TypeError):
            pass
    
    ts_range = f"ts: {min(timestamps):.0f}-{max(timestamps):.0f}s" if timestamps else "ts: ?"
    
    # Check sentinels
    sentinel = sum(1 for r in rows if r.get("defender_distance", "").strip() == "200.0")
    
    pct = made_filled / total
    status = "OK" if pct >= 0.80 else "LOW"
    sent_flag = f" SENTINEL={sentinel}" if sentinel > 0 else ""
    print(f"{gid}: {made_filled}/{total} enriched ({pct:.0%}) {ts_range} [{status}]{sent_flag}")
