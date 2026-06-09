"""
cv_fix_resolve_offline.py — Iterate slot->player resolution logic offline.

Consumes ocr_raw_reads.json (dumped by cv_fix_ocr_replay.py) and resolves
slots to players WITHOUT re-running OCR. Lets us test gate/team-restriction/
assignment strategies in milliseconds.

Core idea: each team has 5 on-court slots that must map to 5 DISTINCT players.
Build a [slots x roster] confidence-weighted vote matrix restricted to the
slot's team roster, then Hungarian-assign for distinctness. This structurally
rejects the "#6 resolved to 5 slots" OCR-noise failure mode.

Usage: python scripts/cv_fix_resolve_offline.py <game_id> [--minconf 0.55] [--sizew]
"""
from __future__ import annotations
import argparse, json, os
from collections import Counter, defaultdict
import numpy as np
from scipy.optimize import linear_sum_assignment


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game_id")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--minconf", type=float, default=0.55, help="drop reads below this conf")
    ap.add_argument("--sizew", action="store_true", help="weight reads by crop area")
    ap.add_argument("--minmargin", type=float, default=1.3,
                    help="top score must beat 2nd by this ratio to accept")
    args = ap.parse_args()

    data_dir = args.data_dir or f"data/tracking/{args.game_id}"
    dump = json.load(open(os.path.join(data_dir, "ocr_raw_reads.json")))
    reads = dump["reads"]
    slot_team = {int(k): v for k, v in dump["slot_team"].items()}
    # Roster from jersey_name_map.json (by_team) + name->pid from NBA box if available.
    jmap = json.load(open(os.path.join(data_dir, "jersey_name_map.json")))
    name_to_pid = {}
    try:
        from nba_api.stats.endpoints import boxscoretraditionalv2
        bx = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=args.game_id).player_stats.get_data_frame()
        name_to_pid = {str(r["PLAYER_NAME"]): int(r["PLAYER_ID"]) for _, r in bx.iterrows()}
    except Exception as e:
        print(f"[resolve] box pid fetch failed ({e}); pids=0")
    team_roster = defaultdict(dict)
    for abbr, jdict in jmap.get("by_team", {}).items():
        for jstr, name in jdict.items():
            try:
                team_roster[abbr][int(jstr)] = (name, name_to_pid.get(name, 0))
            except ValueError:
                continue
    teams = sorted(team_roster.keys())
    print(f"[resolve] reads={len(reads)} slots={sorted(slot_team)} teams={teams}")
    print(f"[resolve] minconf={args.minconf} sizew={args.sizew} minmargin={args.minmargin}")

    # 1) map color label -> team abbrev: for each color, which team's jerseys do
    #    the (in-either-roster) reads mostly match?
    color_team_votes = defaultdict(Counter)
    valid_jerseys = {abbr: set(r) for abbr, r in team_roster.items()}
    for slot, color, jn, conf, ch, cw in reads:
        if conf < args.minconf:
            continue
        for abbr in teams:
            if jn in valid_jerseys[abbr]:
                color_team_votes[color][abbr] += conf
    color_to_team = {}
    used = set()
    # greedy: strongest (color,team) pair first so the two colors get distinct teams
    pairs = []
    for color, ctr in color_team_votes.items():
        for abbr, w in ctr.items():
            pairs.append((w, color, abbr))
    for w, color, abbr in sorted(pairs, reverse=True):
        if color in color_to_team or abbr in used:
            continue
        color_to_team[color] = abbr
        used.add(abbr)
    print(f"[resolve] color->team: {color_to_team}")

    # 2) per-team: build slot x jersey weighted-vote matrix, restrict to team roster
    results = {}
    for color, abbr in color_to_team.items():
        slots = sorted([s for s in slot_team if slot_team[s] == color])
        roster = team_roster[abbr]
        jerseys = sorted(roster.keys())
        # weighted votes
        W = defaultdict(lambda: defaultdict(float))  # slot -> jersey -> weight
        raw = defaultdict(Counter)                    # slot -> jersey -> count (in-roster only)
        for slot, c, jn, conf, ch, cw in reads:
            if c != color or conf < args.minconf:
                continue
            if jn not in roster:
                continue  # team-restricted: drop reads not in this team's roster
            w = conf * (ch * cw if args.sizew else 1.0)
            W[slot][jn] += w
            raw[slot][jn] += 1
        # cost matrix: slots x jerseys (maximize weight -> minimize -weight)
        M = np.zeros((len(slots), len(jerseys)))
        for i, s in enumerate(slots):
            for j, jn in enumerate(jerseys):
                M[i, j] = W[s].get(jn, 0.0)
        # Hungarian on -M for distinct assignment
        ri, ci = linear_sum_assignment(-M)
        for i, j in zip(ri, ci):
            s = slots[i]; jn = jerseys[j]; score = M[i, j]
            # margin: best score for this slot vs 2nd best
            srow = sorted(W[s].values(), reverse=True)
            margin = (srow[0] / srow[1]) if len(srow) > 1 and srow[1] > 0 else 999.0
            name, pid = roster[jn]
            total = sum(W[s].values())
            domfrac = (score / total) if total else 0.0
            accept = score > 0 and (margin >= args.minmargin or domfrac >= 0.45)
            results[s] = dict(team=abbr, jersey=jn, name=name, pid=pid, score=round(score, 1),
                              domfrac=round(domfrac, 2), margin=round(margin, 2),
                              accept=accept, top5=raw[s].most_common(5))

    print("\n===== ASSIGNED RESOLUTION (Hungarian, team-restricted, distinct) =====")
    n_accept = 0
    for s in sorted(results):
        r = results[s]
        flag = "OK " if r["accept"] else "weak"
        if r["accept"]:
            n_accept += 1
        print(f"slot {s:2d} {r['team']} -> #{r['jersey']:<2d} {r['name']:26s} "
              f"pid={r['pid']} score={r['score']:7.1f} domfrac={r['domfrac']:.2f} "
              f"margin={r['margin']:.2f} [{flag}] in-roster-votes(top5)={r['top5']}")
    print(f"\n[resolve] ACCEPTED (high-confidence): {n_accept}/{len(results)}")

    # Star check
    stars = {"Victor Wembanyama", "Shai Gilgeous-Alexander", "Chet Holmgren",
             "Jalen Williams", "De'Aaron Fox", "Luguentz Dort", "Devin Vassell",
             "Isaiah Hartenstein", "Aaron Wiggins", "Cason Wallace"}
    got = {r["name"] for r in results.values() if r["accept"]}
    print("\n===== STARS (accepted only) =====")
    for st in sorted(stars):
        print(f"  {'YES' if st in got else ' . '}  {st}")


if __name__ == "__main__":
    main()
