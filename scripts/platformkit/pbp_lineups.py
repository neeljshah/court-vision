"""Reconstruct 5-man on-court lineups from the free public play-by-play.

The broadcast pixels resolve player identity only ~15% of the time. The
substitution log resolves it 100% of the time, for free. This module turns
the PBP action stream into (period, seconds_remaining) -> {team: frozenset of
5 personIds}, which is the identity layer the tracking cannot supply.

Usage:
    python -m scripts.platformkit.pbp_lineups --games 10
"""
import argparse
import glob
import json
import os
import re
import sys

PBP_DIRS = (
    "data/cache/team_system/pbp_2025_26",
    "data/cache/team_system/pbp_2024_25",
    "data/cache/team_system/pbp_2023_24",
    "data/cache/team_system/pbp",
)
SUB_RE = re.compile(r"^(.*?)\s+enters the game for\s+(.*?)\s*$", re.I)


def clock_to_sec(c):
    """'PT7M1.00S' -> 421.0 seconds remaining in the period."""
    m = re.match(r"PT(?:(\d+)M)?(?:([\d.]+)S)?", c or "")
    if not m:
        return None
    mins = float(m.group(1) or 0)
    secs = float(m.group(2) or 0)
    return mins * 60.0 + secs


def find_pbp(game_id):
    for d in PBP_DIRS:
        p = os.path.join(d, game_id + ".json")
        if os.path.exists(p):
            return p
    return None


def _name_index(actions):
    """Map the display names used in sub descriptions to personIds."""
    idx = {}
    for a in actions:
        pid = a.get("personId")
        desc = a.get("description") or ""
        if not pid or a.get("actionType") == "substitution":
            continue
        # leading token run before a verb is usually the player's name
        m = re.match(r"^([A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,3})", desc)
        if m:
            idx.setdefault(m.group(1).strip(), pid)
    return idx


def build_lineups(pbp_path):
    """Return list of (period, sec_remaining, team_tricode, frozenset(personIds))."""
    with open(pbp_path, encoding="utf-8", errors="ignore") as fh:
        game = json.load(fh)["game"]
    actions = game.get("actions") or []
    names = _name_index(actions)

    # starters per period: first appearance in the period, not as a sub-in
    by_period = {}
    subbed_in = {}
    for a in actions:
        per = a.get("period")
        team = a.get("teamTricode")
        pid = a.get("personId")
        if per is None or not team:
            continue
        if a.get("actionType") == "substitution":
            m = SUB_RE.match(a.get("description") or "")
            if m:
                in_id = names.get(m.group(1).strip())
                if in_id:
                    subbed_in.setdefault((per, team), set()).add(in_id)
            continue
        if pid:
            by_period.setdefault((per, team), [])
            if pid not in by_period[(per, team)]:
                by_period[(per, team)].append(pid)

    on = {}
    for key, seen in by_period.items():
        ins = subbed_in.get(key, set())
        starters = [p for p in seen if p not in ins][:5]
        on[key] = set(starters)

    out = []
    cur_period = None
    for a in actions:
        per = a.get("period")
        team = a.get("teamTricode")
        if per is None:
            continue
        if per != cur_period:
            cur_period = per
        if a.get("actionType") == "substitution" and team:
            m = SUB_RE.match(a.get("description") or "")
            if m:
                in_id = names.get(m.group(1).strip())
                out_id = names.get(m.group(2).strip())
                s = on.setdefault((per, team), set())
                if out_id in s:
                    s.discard(out_id)
                if in_id:
                    s.add(in_id)
        sec = clock_to_sec(a.get("clock"))
        if sec is None or not team:
            continue
        s = on.get((per, team))
        if s and len(s) == 5:
            out.append((per, sec, team, frozenset(s)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=10)
    args = ap.parse_args()

    gids = sorted(
        os.path.basename(os.path.dirname(f))
        for f in glob.glob("data/tracking/*/tracking_data.csv")
    )
    ok = 0
    total_states = 0
    valid5 = 0
    checked = 0
    for gid in gids:
        p = find_pbp(gid)
        if not p:
            continue
        checked += 1
        if checked > args.games:
            break
        try:
            rows = build_lineups(p)
        except Exception as exc:
            print("SKIP %s: %s" % (gid, exc))
            continue
        if rows:
            ok += 1
            total_states += len(rows)
            valid5 += sum(1 for r in rows if len(r[3]) == 5)
            uniq = len({(r[2], r[3]) for r in rows})
            print("%s  states=%5d  distinct lineups=%3d" % (gid, len(rows), uniq))
    print("\ngames with lineups: %d" % ok)
    print("lineup states     : %d" % total_states)
    print("exactly 5 players : %d (%.1f%%)" % (
        valid5, 100.0 * valid5 / max(total_states, 1)))


if __name__ == "__main__":
    main()
