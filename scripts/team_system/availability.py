"""SAME-DAY AVAILABILITY -> OUT player ids per team (the freshness lever for the live slate).

The signal lab found vacated-load is immaterial for MARGINAL accuracy (recency absorbs it), but the real
value of availability is FRESHNESS: removing a player who is OUT before tip so his minutes/usage re-route
in the sim (and, for betting, beating the line before it moves on the news). This reads the scraped injury
feed (`data/cache/injury_status_*.json`, status OUT/QUESTIONABLE + player_id) as-of a date and returns the
OUT ids for a team -- feed into TeamModel.from_cache(out_ids=...).

  from availability import out_ids_for
  out = out_ids_for("SAS", asof="2026-06-08")          # set of player ids OUT for SAS as-of that date
"""
from __future__ import annotations
import glob, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "data", "cache")


def _latest_feed(asof: str = None):
    feeds = sorted(glob.glob(os.path.join(CACHE, "injury_status_*.json")))
    if not feeds:
        return None
    if asof:
        ok = [f for f in feeds if os.path.basename(f)[14:24] <= asof]   # injury_status_YYYY-MM-DD.json
        feeds = ok or feeds
    return feeds[-1]


def out_ids_for(tri: str, asof: str = None, include_questionable: bool = False):
    """Return the set of int player ids that are OUT (and optionally QUESTIONABLE) for team `tri`."""
    f = _latest_feed(asof)
    if not f:
        return set()
    bad = {"OUT"} | ({"QUESTIONABLE", "DOUBTFUL"} if include_questionable else set())
    out = set()
    for p in json.load(open(f)).get("players", []):
        if p.get("team") == tri and p.get("status") in bad:
            pid = p.get("player_id")
            if pid is not None and pid == pid:        # skip None + NaN (NaN != NaN)
                out.add(int(pid))
    return out


def report(tri: str, asof: str = None):
    f = _latest_feed(asof)
    if not f:
        print(f"  {tri}: no injury feed found"); return set()
    names = [(p.get("player_name"), p.get("status"), p.get("reason", "")[:50])
             for p in json.load(open(f)).get("players", []) if p.get("team") == tri and p.get("status") == "OUT"]
    print(f"  {tri} OUT (feed {os.path.basename(f)}): {len(names)}")
    for n, s, r in names:
        print(f"    - {n}: {r}")
    return out_ids_for(tri, asof)


if __name__ == "__main__":
    import sys
    asof = sys.argv[1] if len(sys.argv) > 1 else None
    for t in ("NYK", "SAS"):
        report(t, asof)
