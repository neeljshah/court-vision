"""CLV CAPTURE -- the append-only odds log that turns snapshots into OPEN/CLOSE pairs (the freshness prerequisite).

iter-17 graded the freshness/CLV edge on GAME LINES (ESPN already ships open+close). But PLAYER PROPS only exist
as single near-close snapshots (`data/cache/odds_api/historical_event_odds/`), so prop-level CLV is un-gradable
until open/close is captured over time. This builds that capture: each run appends a TIMESTAMPED snapshot of the
available odds to an append-only log; over a slate the FIRST snapshot per (game/player, market, line) is the
OPEN and the LAST before tip is the CLOSE. Then `open_close()` collapses the log into the open/close corpus the
EDGE_GATE lacked, and `freshness_clv_analysis` / `crossbook_edge_regrade` can grade prop CLV exactly like game lines.

Sources: game-line = ESPN scoreboard (`data/cache/spreads/`); prop = the odds_api event-odds snapshots. LIVE
capture (the daemon use) re-fetches these on a cadence; OFFLINE, `--ingest-cached` backfills the log from what's
already cached (so the structure is testable now). DISCIPLINE: capture only -- it never bets, sizes, or recommends.

  python scripts/team_system/clv_capture.py --ingest-cached         # backfill the log from cached snapshots
  python scripts/team_system/clv_capture.py --open-close --market player_assists
"""
from __future__ import annotations
# Eager pyarrow.dataset import (P1-9): preload before other heavy natives to
# avoid a Windows DLL import-order access violation when pd.read_parquet()
# triggers the lazy pyarrow.dataset import mid-session.
try:
    import pyarrow.dataset  # noqa: F401
except ImportError:
    pass
import argparse, glob, json, os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "data", "cache")
CLV_DIR = os.path.join(CACHE, "clv")
LOG = os.path.join(CLV_DIR, "clv_log.parquet")

COLS = ["snap_ts", "commence_ts", "date", "game", "market", "selection", "line", "book", "over_price",
        "under_price", "grain"]


def _am(s):
    try:
        return float(str(s).replace("+", ""))
    except Exception:
        return None


def _append(rows):
    os.makedirs(CLV_DIR, exist_ok=True)
    new = pd.DataFrame(rows, columns=COLS)
    if os.path.exists(LOG):
        old = pd.read_parquet(LOG)
        # dedup: one row per (snap_ts, game, market, selection, line, book) -- a re-ingest is idempotent
        cat = pd.concat([old, new], ignore_index=True)
        cat = cat.drop_duplicates(subset=["snap_ts", "game", "market", "selection", "line", "book"], keep="last")
    else:
        cat = new
    tmp = LOG + ".staging"
    cat.to_parquet(tmp, index=False)
    os.replace(tmp, LOG)
    return len(new), len(cat)


def ingest_cached():
    """Backfill the append-only log from cached snapshots (game lines + props) -- offline-testable structure."""
    rows = []
    # game lines (ESPN scoreboard) -- carry their own open+close, ingested as two snapshots (open ts < close ts)
    for f in sorted(glob.glob(os.path.join(CACHE, "spreads", "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        date = os.path.basename(f)[:8]
        for e in d.get("events", []):
            comp = e.get("competitions", [{}])[0]
            cs = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            if "home" not in cs:
                continue
            game = f"{cs.get('away', {}).get('team', {}).get('abbreviation')}@{cs['home'].get('team', {}).get('abbreviation')}"
            for o in comp.get("odds", [])[:1]:
                hto = o.get("homeTeamOdds", {})
                for phase, ts in (("open", 0), ("close", 1)):
                    ps = hto.get(phase, {}).get("pointSpread", {})
                    line_val = _am(ps.get("american"))
                    if line_val is not None:
                        # COLS order: snap_ts, commence_ts, date, game, market, selection, line, book, over_price, under_price, grain
                        rows.append([f"{date}_{ts}", comp.get("date"), date, game, "spread", "home",
                                     line_val, "espn", -110.0, -110.0, "game"])
    # props (odds_api) -- single snapshot each; ingested with their own timestamp (becomes open until more captured)
    for f in sorted(glob.glob(os.path.join(CACHE, "odds_api", "historical_event_odds", "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        dat = d.get("data", {})
        ts = d.get("timestamp"); date = os.path.basename(f)[:10]
        game = f"{dat.get('away_team')}@{dat.get('home_team')}"
        for b in dat.get("bookmakers", []):
            for m in b.get("markets", []):
                tmp = {}
                for oc in m.get("outcomes", []):
                    pt = oc.get("point")
                    if pt is None or oc.get("price") in (None, 0):
                        continue
                    tmp.setdefault((oc.get("description"), pt), {})[oc["name"]] = oc["price"]
                for (pl, pt), sd in tmp.items():
                    if "Over" in sd and "Under" in sd:
                        # COLS order: snap_ts, commence_ts, date, game, market, selection, line, book, over_price, under_price, grain
                        rows.append([ts, dat.get("commence_time"), date, game, m["key"], pl, float(pt),
                                     b["key"], float(sd["Over"]), float(sd["Under"]), "prop"])
    n_new, n_tot = _append(rows)
    print(f"ingested {n_new} snapshot-rows -> log now {n_tot} rows ({LOG})")
    df = pd.read_parquet(LOG)
    print(f"  grains: {df.grain.value_counts().to_dict()}")
    print(f"  distinct games: {df.game.nunique()} | markets: {sorted(df.market.unique())}")


def open_close(market=None):
    """Collapse the log into OPEN (first snap) + CLOSE (last snap) per (game, market, selection, line)."""
    if not os.path.exists(LOG):
        print("no log yet -- run --ingest-cached"); return
    df = pd.read_parquet(LOG)
    if market:
        df = df[df.market == market]
    df = df.sort_values("snap_ts")
    key = ["game", "market", "selection", "line", "book"]
    op = df.groupby(key).first().reset_index()
    cl = df.groupby(key).last().reset_index()
    merged = op.merge(cl, on=key, suffixes=("_open", "_close"))
    n_pairs = (merged.snap_ts_open != merged.snap_ts_close).sum()
    print(f"open/close pairs: {len(merged)} ({n_pairs} with a real open!=close move captured)")
    print("NOTE: game lines already carry open!=close; props need MULTIPLE live captures (currently 1 snapshot "
          "each -> open==close until the live daemon accumulates). This is the structure; the daemon fills it.")
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest-cached", action="store_true")
    ap.add_argument("--open-close", action="store_true")
    ap.add_argument("--market", default=None)
    a = ap.parse_args()
    if a.ingest_cached:
        ingest_cached()
    if a.open_close:
        open_close(a.market)
    if not (a.ingest_cached or a.open_close):
        ap.print_help()


if __name__ == "__main__":
    main()
