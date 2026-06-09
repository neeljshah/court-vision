import json, urllib.request, sys
date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-30"
d = json.loads(urllib.request.urlopen(f"http://127.0.0.1:8077/api/slate?date={date}", timeout=60).read())
print("stale_data", d.get("stale_data"), "| synthesized", d.get("slate_synthesized"),
      "| has_lines", d.get("has_lines"), "| latest", d.get("latest_available"))
print("summary", d.get("summary"))
cal = d.get("calibration")
if cal:
    print("calibration: shown", cal.get("n_shown"), "of", cal.get("n_bets_pre_gate"),
          "|", cal.get("message", ""))
print("--- shown bets ---")
for b in d.get("bets", []):
    print(f"{b['player_name'][:22]:22s} {b['prop_stat']:4s} {b['side']:5s} line={b['line']:<5} "
          f"q50={b.get('q50')} EV%={b.get('ev_pct')} mp={b.get('model_prob')} "
          f"{b.get('best_book')} {b.get('best_price')}")
