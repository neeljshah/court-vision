"""
coverage_matrix_g7.py — full who-guards-whom coverage intelligence for WCF G7.
From real NBA-API matchup tracking (wcf_defensive_matchups.csv), for every key scorer:
their primary defenders, efficiency allowed (pts per matchup-min + FG% allowed), and the G7
lean — accounting for OKC's OUT defenders (Jalen Williams, Ajay Mitchell) reallocating coverage.
Output: data/cache/intel_game7/coverage_matrix_g7.json + printed table.
"""
import csv, json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "intel_game7"
MATCH = ROOT / "data" / "cache" / "intel_2026-05-26" / "wcf_defensive_matchups.csv"

OUT_DEFENDERS = {"1631114", "1642349"}  # Jalen Williams, Ajay Mitchell (OKC) — OUT for G7
KEY_SCORERS = {  # off_player_id -> (name, team)
    "1641705": ("Wembanyama", "SAS"), "1628983": ("SGA", "OKC"),
    "1628368": ("Fox", "SAS"), "1642844": ("Harper", "SAS"),
    "1642264": ("Castle", "SAS"), "1631096": ("Holmgren", "OKC"),
    "1642272": ("McCain", "OKC"), "1627936": ("Caruso", "OKC"),
}

rows = list(csv.DictReader(open(MATCH, newline="")))
by_off = defaultdict(list)
for r in rows:
    by_off[r["off_player_id"]].append(r)

def f(x):
    try: return float(x)
    except: return 0.0

matrix = {}
for oid, (name, team) in KEY_SCORERS.items():
    defs = sorted(by_off.get(oid, []), key=lambda r: f(r["matchup_min"]), reverse=True)
    total_min = sum(f(r["matchup_min"]) for r in defs)
    rec = []
    lost_min = 0.0
    for r in defs[:6]:
        mm = f(r["matchup_min"])
        if mm < 0.8:  # ignore trivial samples
            continue
        out = r["def_player_id"] in OUT_DEFENDERS
        if out: lost_min += mm
        ppm = f(r["pts_allowed"]) / mm if mm else 0
        rec.append({"defender": r["def_player_name"], "matchup_min": round(mm, 1),
                    "pts_allowed": f(r["pts_allowed"]), "pts_per_min": round(ppm, 2),
                    "fg_pct_allowed": round(f(r["fg_pct_allowed"]), 3),
                    "OUT_g7": out})
    # lean: weighted pts/min of remaining (in) defenders vs his overall; flag reallocation
    in_def = [d for d in rec if not d["OUT_g7"]]
    if in_def:
        w_ppm = sum(d["pts_per_min"] * d["matchup_min"] for d in in_def) / sum(d["matchup_min"] for d in in_def)
    else:
        w_ppm = 0
    matrix[name] = {
        "team": team, "primary_defenders": rec,
        "coverage_min_lost_to_injury": round(lost_min, 1),
        "remaining_pts_per_min_allowed": round(w_ppm, 2),
        "note": ("OKC loses %.1f matchup-min of coverage (JWill/Mitchell OUT) → reallocates" % lost_min) if lost_min else "coverage intact",
    }

out = {"game": "WCF G7", "out_defenders": ["Jalen Williams", "Ajay Mitchell"], "matrix": matrix,
       "reads": {
           "Wembanyama": "Bigs (Hartenstein 58%/Holmgren 47%) = favorable; Dort/Caruso/Wallace HOLD him; JWill+Mitchell out thins pesky-wing pool → median 27.6.",
           "SGA": "Castle (46.7%) + Vassell (29.4% LOCKDOWN) = the wall → suppressed to 23.9; UNDER lean.",
           "Fox": "primary OKC defender + how he's held — see table; he's ice-cold/facilitating.",
       }}
(CACHE / "coverage_matrix_g7.json").write_text(json.dumps(out, indent=2))

print("=== WCF G7 COVERAGE MATRIX (real matchup tracking) ===")
for name, d in matrix.items():
    print(f"\n{name} ({d['team']}) — lost {d['coverage_min_lost_to_injury']} min to injury; remaining {d['remaining_pts_per_min_allowed']} pts/matchup-min")
    for dd in d["primary_defenders"]:
        tag = "  ❌OUT" if dd["OUT_g7"] else ""
        print(f"   vs {dd['defender']:22s} {dd['matchup_min']:>5}min  {dd['pts_allowed']:>4}pts  {dd['pts_per_min']:>4}/min  FG%{dd['fg_pct_allowed']:.0%}{tag}")
print("\nWROTE", CACHE / "coverage_matrix_g7.json")
