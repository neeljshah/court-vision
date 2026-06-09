"""One-off: reconstruct SAS@OKC (0042500315) per-quarter snapshots from
cdn.nba.com play-by-play, run the calibrated in-game engine against the
real Pinnacle/Bovada/FanDuel lines, and print what bets would have emitted
at endQ1 / endQ2 / endQ3.
"""
import json
import os
import sys
import urllib.request
from collections import defaultdict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

GAME_ID = "0042500315"
DATE_STR = "2026-05-26"

# Cumulative stat keys to track per player per period.
STAT_KEYS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def fetch_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0",
                      "Referer": "https://www.nba.com/"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def pbp_to_period_states(game_id):
    """Return {period: {player_id: {pts,reb,ast,fg3m,stl,blk,tov,min,name,team}}}
    cumulative through the END of each period (1..4)."""
    pbp = fetch_json(
        f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json")
    actions = pbp.get("game", {}).get("actions", []) or []
    box = fetch_json(
        f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json")
    g = box["game"]
    home_tri = g["homeTeam"]["teamTricode"]
    away_tri = g["awayTeam"]["teamTricode"]
    home_tid = g["homeTeam"]["teamId"]
    away_tid = g["awayTeam"]["teamId"]
    player_meta = {}
    for p in g["homeTeam"]["players"] + g["awayTeam"]["players"]:
        pid = p.get("personId")
        if pid is None:
            continue
        player_meta[int(pid)] = {
            "name": p.get("name"),
            "team": home_tri if p.get("teamId") == home_tid else away_tri,
        }

    # Cumulative stats per (period, player) — we sum through period boundaries.
    cum = defaultdict(lambda: dict(pts=0, reb=0, ast=0, fg3m=0, stl=0, blk=0,
                                    tov=0, min=0.0))
    period_states = {}

    def snapshot_through(period):
        out = {}
        for pid, stats in cum.items():
            if pid not in player_meta:
                continue
            out[pid] = dict(stats)
            out[pid].update(player_meta[pid])
        period_states[period] = out

    last_period = 0
    for a in actions:
        per = int(a.get("period") or 0)
        if per == 0:
            continue
        # When we cross a period boundary, snapshot the prior period.
        while last_period < per - 1 and last_period < 4:
            last_period += 1
            snapshot_through(last_period)
        pid = a.get("personId")
        try:
            pid = int(pid) if pid is not None else None
        except (TypeError, ValueError):
            pid = None
        if pid is None:
            continue
        atype = (a.get("actionType") or "").lower()
        subtype = (a.get("subType") or "").lower()
        # Points scored on this action.
        pts_val = int(a.get("pointsTotal") or 0)
        # Use shotResult + shotValue when available for the increment.
        prev_pts = cum[pid]["pts"]
        if pts_val and pts_val > prev_pts:
            inc = pts_val - prev_pts
            cum[pid]["pts"] = pts_val
            # 3PM increment when increment was 3.
            if inc == 3:
                cum[pid]["fg3m"] += 1
        elif atype == "3pt" and (a.get("shotResult") or "").lower() == "made":
            cum[pid]["pts"] += 3
            cum[pid]["fg3m"] += 1
        elif atype == "2pt" and (a.get("shotResult") or "").lower() == "made":
            cum[pid]["pts"] += 2
        elif atype == "freethrow" and (a.get("shotResult") or "").lower() == "made":
            cum[pid]["pts"] += 1
        if atype == "rebound" and subtype in ("offensive", "defensive"):
            cum[pid]["reb"] += 1
        if atype == "assist":
            cum[pid]["ast"] += 1
        if atype == "steal":
            cum[pid]["stl"] += 1
        if atype == "block":
            cum[pid]["blk"] += 1
        if atype == "turnover":
            cum[pid]["tov"] += 1
    # Snapshot through the last period (usually 4).
    while last_period < 4:
        last_period += 1
        snapshot_through(last_period)
    # Use final box-score values for minutes-played at endQ3 (PBP doesn't track
    # min cleanly). Approximate min_through_q3 = final_min * 0.75 — coarse but
    # adequate for the projection model's pace_factor input.
    for pid in player_meta:
        try:
            final_min_str = next(
                (p.get("statistics", {}).get("minutesCalculated") or "00:00"
                 for p in g["homeTeam"]["players"] + g["awayTeam"]["players"]
                 if p.get("personId") == pid), "00:00")
            mins = final_min_str.replace("PT", "").replace("M", ":").replace("S", "")
            parts = mins.split(":")
            final_min = float(parts[0] or 0) + (float(parts[1] or 0) if len(parts) > 1 else 0) / 60.0
        except Exception:
            final_min = 30.0
        for per in (1, 2, 3, 4):
            if pid in period_states.get(per, {}):
                period_states[per][pid]["min"] = final_min * (per / 4.0)
    return period_states, g


def build_snapshot(period_idx, period_states, game_meta):
    """Build the canonical snap dict for live_engine.project_from_snapshot."""
    ps = period_states.get(period_idx, {})
    players = []
    for pid, st in ps.items():
        players.append({
            "player_id": pid,
            "name": st.get("name"),
            "team": st.get("team"),
            "pts": st["pts"], "reb": st["reb"], "ast": st["ast"],
            "fg3m": st["fg3m"], "stl": st["stl"], "blk": st["blk"],
            "tov": st["tov"], "min": st["min"], "pf": 0,
            "min_q1": st["min"] / period_idx if period_idx else 0,
            "min_q2": st["min"] / period_idx if period_idx >= 2 else 0,
            "min_q3": st["min"] / period_idx if period_idx >= 3 else 0,
            "pts_q1": 0, "pts_q2": 0, "pts_q3": 0,  # coarse
        })
    # period in snap = next period to play (period_idx+1) at endQX boundaries.
    snap_period = period_idx + 1
    return {
        "game_id": GAME_ID,
        "game_date": DATE_STR,
        "period": snap_period,
        "clock": "PT12M00.00S",
        "home_team": game_meta["homeTeam"]["teamTricode"],
        "away_team": game_meta["awayTeam"]["teamTricode"],
        "home_score": sum(p.get("score") for p in
                          game_meta["homeTeam"].get("periods", [])[:period_idx] or [0]),
        "away_score": sum(p.get("score") for p in
                          game_meta["awayTeam"].get("periods", [])[:period_idx] or [0]),
        "players": players,
    }


def load_lines():
    """Load all 2026-05-26 line CSVs, return {(name_lower, stat): [book_offers]}."""
    import csv as _csv
    out = defaultdict(list)
    for fname in os.listdir("data/lines"):
        if not fname.startswith(DATE_STR) or not fname.endswith(".csv"):
            continue
        path = os.path.join("data/lines", fname)
        try:
            with open(path, encoding="utf-8") as fh:
                for row in _csv.DictReader(fh):
                    name = (row.get("player_name") or "").strip().lower()
                    stat = (row.get("stat") or "").strip().lower()
                    if not name or not stat:
                        continue
                    out[(name, stat)].append(row)
        except Exception:
            continue
    return out


def main():
    print(f"reconstructing SAS@OKC ({GAME_ID}) from cdn.nba.com PBP...")
    period_states, game_meta = pbp_to_period_states(GAME_ID)
    print(f"  built {len(period_states)} period states; "
          f"home={game_meta['homeTeam']['teamTricode']} "
          f"away={game_meta['awayTeam']['teamTricode']}")
    lines = load_lines()
    print(f"  loaded {sum(len(v) for v in lines.values())} line offers "
          f"across {len(lines)} (player,stat) keys for {DATE_STR}")

    from src.prediction.live_engine import project_from_snapshot
    from src.prediction.decision_engine import (
        _STAT_SIGMA, _filter_three_book_consensus, _passes_gates,
        hit_probability, ev_per_dollar, kelly_fraction, classify_tier,
        _EMIT_FLOOR_BY_PERIOD, _EV_CEILING_BY_PERIOD,
    )

    for period_idx, point_name in [(1, "endQ1"), (2, "endQ2"), (3, "endQ3")]:
        snap = build_snapshot(period_idx, period_states, game_meta)
        snap_period_str = str(snap["period"])
        emit_floor = _EMIT_FLOOR_BY_PERIOD.get(snap_period_str, 0.04)
        ev_ceiling = _EV_CEILING_BY_PERIOD.get(snap_period_str, 0.50)
        rows = project_from_snapshot(snap)
        emitted = []
        for rec in rows:
            stat = (rec.get("stat") or "").lower()
            if stat not in _STAT_SIGMA:
                continue
            name = (rec.get("name") or "").lower()
            offers = lines.get((name, stat), [])
            if not offers:
                continue
            offers = _filter_three_book_consensus(offers)
            for offer in offers:
                for side in ("over", "under"):
                    odds = offer.get(f"{side}_price")
                    if odds in (None, "",):
                        continue
                    try:
                        odds_int = int(odds)
                        line_val = float(offer["line"])
                        proj = float(rec["projected_final"])
                    except (TypeError, ValueError):
                        continue
                    ok, _ = _passes_gates(rec, offer)
                    if not ok:
                        continue
                    sigma = _STAT_SIGMA[stat]
                    p = hit_probability(proj, line_val, side, sigma)
                    ev = ev_per_dollar(p, odds_int)
                    if ev < emit_floor or ev > ev_ceiling:
                        continue
                    tier = classify_tier(ev, abs(proj - line_val))
                    if tier == "C":
                        continue
                    emitted.append({
                        "name": rec["name"], "stat": stat, "side": side,
                        "line": line_val, "book": offer.get("book"),
                        "odds": odds_int, "proj": proj, "current": rec.get("current"),
                        "ev": ev, "kelly": kelly_fraction(p, odds_int), "tier": tier,
                    })
        emitted.sort(key=lambda b: -b["ev"])
        print()
        print(f"=== {point_name} (period={period_idx} done, snap_period={snap['period']}) "
              f"emit_floor={emit_floor:.2f} ===")
        if not emitted:
            print("  (no bets emitted)")
            continue
        for b in emitted[:10]:
            print(f"  {b['tier']} {b['name'][:24]:24s} {b['stat']:4s} "
                  f"{b['side'].upper():5s} {b['line']:5.1f} @ {b['book']:3s} "
                  f"{b['odds']:+5d}  proj={b['proj']:5.1f} cur={b['current']:4.1f}  "
                  f"EV={b['ev']*100:+5.1f}%  K={b['kelly']*100:.1f}%")


if __name__ == "__main__":
    main()
