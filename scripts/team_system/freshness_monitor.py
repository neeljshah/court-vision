"""FRESHNESS MONITOR -- operationalize the #1 graded edge (iter-17): the open->close line move is real
information (~58% ATS ceiling) but is NEWS-DRIVEN and has NO static-model substitute (R^2 0). So the realizable
edge is to DETECT the same-day availability news and surface it BEFORE the line fully adjusts.

This is the capability that turns the finding into action. Given a date it reads the injury feed
(`data/cache/injury_status_*.json`) + (when available) the day's OPENER game lines, identifies
ROTATION-SIGNIFICANT availability changes, and emits FRESHNESS INTELLIGENCE: which game has a meaningful
availability shift, the expected direction of the line move, and the HISTORICAL base rate for capturing it
(from `freshness_clv.json`).

DISCIPLINE: this emits INTELLIGENCE + a historical base rate as a PROJECTION -- it never sizes, stakes, or says
"bet this" (SS0.1.2). It is the war-room's freshness read, not a wager. Edge realization still requires live
opener odds + execution speed (it can't be validated offline -- single snapshots); this is the ready capability.

  python scripts/team_system/freshness_monitor.py --date 2026-06-08 --home NYK --away SAS
"""
from __future__ import annotations
import argparse, glob, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "data", "cache")
TS = os.path.join(CACHE, "team_system")

# rotation-significance: a player matters to the line only if he plays real minutes. Pulled from ratings/mpg.
MIN_MPG_SIGNIFICANT = 18.0


def _latest_feed(asof):
    feeds = sorted(glob.glob(os.path.join(CACHE, "injury_status_*.json")))
    if asof:
        feeds = [f for f in feeds if os.path.basename(f)[14:24] <= asof] or feeds
    return feeds[-1] if feeds else None


def _mpg_map():
    import pandas as pd
    try:
        r = pd.read_parquet(os.path.join(TS, "player_ratings.parquet"))
        col = "mpg" if "mpg" in r.columns else ("min" if "min" in r.columns else None)
        if col:
            return {int(p): float(m) for p, m in zip(r["pid"], r[col]) if m == m}
    except Exception:
        pass
    return {}


def _base_rates():
    p = os.path.join(TS, "freshness_clv.json")
    if os.path.exists(p):
        d = json.load(open(p))
        return d.get("freshness_ceiling_ats", 0.579)
    return 0.579


def assess(date, teams):
    """Return the freshness intelligence for the given teams on `date` (no live odds needed for the read)."""
    feed = _latest_feed(date)
    if not feed:
        return {"status": "no-feed", "note": "no cached injury feed; schedule the scraper ~2h pre-tip"}
    fd = json.load(open(feed, encoding="utf-8"))
    mpg = _mpg_map()
    players = fd.get("players", [])
    out = {"feed_date": os.path.basename(feed)[14:24], "teams": teams, "situations": [],
           "playoff_ceiling": 0.548, "regseason_ceiling": _base_rates()}
    for p in players:
        tm = str(p.get("team", "")).upper()
        if tm not in teams:
            continue
        st = str(p.get("status", "")).upper()
        if st not in ("OUT", "QUESTIONABLE", "DOUBTFUL"):
            continue
        pid = p.get("player_id")
        try:
            m = mpg.get(int(pid), None) if pid is not None and pid == pid else None
        except (ValueError, TypeError):
            m = None
        # conservative: only a KNOWN rotation player (in ratings, mpg >= threshold) moves a line. A player
        # absent from player_ratings is almost certainly deep-bench/non-rotation -> NOT significant.
        significant = (m is not None) and (m >= MIN_MPG_SIGNIFICANT)
        out["situations"].append({
            "player": p.get("player_name"), "team": tm, "status": st,
            "mpg": round(m, 1) if m else None, "rotation_significant": bool(significant),
            "reason": (p.get("reason") or "")[:90]})
    # the only situations that move a line are rotation-significant OUT (or downgraded QUESTIONABLE on a starter)
    triggers = [s for s in out["situations"] if s["status"] == "OUT" and s["rotation_significant"]]
    out["freshness_trigger"] = bool(triggers)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--home", default="NYK")
    ap.add_argument("--away", default="SAS")
    a = ap.parse_args()
    r = assess(a.date, {a.home.upper(), a.away.upper()})
    print(f"=== FRESHNESS MONITOR -- {a.away} @ {a.home} (feed {r.get('feed_date', 'n/a')}) ===")
    if r.get("status") == "no-feed":
        print(r["note"]); return
    if not r["situations"]:
        print("no OUT/QUESTIONABLE rotation players -> NO freshness situation (both teams full strength).")
    for s in r["situations"]:
        flag = "  >> ROTATION-SIGNIFICANT" if s["rotation_significant"] and s["status"] == "OUT" else ""
        print(f"  {s['team']} {s['player']}: {s['status']} (mpg {s['mpg']}){flag}")
        if s["reason"]:
            print(f"      {s['reason']}")
    print(f"\nFRESHNESS TRIGGER: {'YES -> ' if r['freshness_trigger'] else 'NO'}", end="")
    if r["freshness_trigger"]:
        print("a rotation-significant player is OUT. PROJECTION (not a bet): the opener line should move toward "
              f"the opponent; historically capturing that move at the opener has been ~{r['regseason_ceiling']*100:.0f}% "
              f"ATS reg-season / ~{r['playoff_ceiling']*100:.0f}% playoffs. Watch the opener; the edge is SPEED, not the model.")
    else:
        print("-> the model's projection stands without an availability re-route; no opener edge to chase.")


if __name__ == "__main__":
    main()
