"""line_move_detector.py — steam detector for NBA prop lines.

Diffs consecutive per-book snapshots per (book, player_name, stat) and emits
MOVE events when |line_delta| >= threshold OR |odds_pct_delta| >= threshold_pct.

Cross-book consensus: when >=2 books move in the SAME direction within 5 min
on the same (player, stat), the events get tagged CONSENSUS_STEAM — that's the
high-conviction signal sharps fade.

Inputs
------
data/lines/<YYYY-MM-DD>_<book>.csv  (schema: captured_at,book,game_id,
                                            player_id,player_name,stat,line,
                                            over_price,under_price,start_time)

Outputs
-------
data/cache/line_moves_<isodate>.json   append-only event log
vault/Improvements/line_moves.md       latest 50 events (human readable)

Optional alert hook
-------------------
If env WEBHOOK_URL is set, POST consensus-steam events as JSON. No-op if unset.

CLI
---
    python scripts/line_move_detector.py \
        --interval-sec 30 \
        --threshold-line 0.5 \
        --threshold-odds-pct 10

Design notes
------------
- Implied-prob % change is computed in VIG-INCLUDED implied-prob space
  (not raw American odds) so a -110 -> +110 swing is correctly "huge",
  but -800 -> -750 is correctly "small". Aligns with clv.py convention.
- We dedup by (book, player_name, stat, ts_from, ts_to) so the same
  consecutive-pair never emits twice across daemon restarts. Event log is
  append-only, and a load+filter pass enforces the dedup invariant.
- Consensus window is by ts_to (the more-recent snapshot of the pair).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd

# R19_L3 heartbeat import (sys.path bootstrap so daemons launched via
# 'python -u scripts/<name>.py' can still find src.monitor at the project root).
try:
    import os as _r19_os, sys as _r19_sys
    _r19_root = _r19_os.path.dirname(_r19_os.path.dirname(_r19_os.path.abspath(__file__)))
    if _r19_root not in _r19_sys.path:
        _r19_sys.path.insert(0, _r19_root)
    from src.monitor.daemon_heartbeat import write_heartbeat as _r19_hb
except Exception:
    def _r19_hb(_name):
        return False


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES_DIR    = os.path.join(PROJECT_DIR, "data", "lines")
CACHE_DIR    = os.path.join(PROJECT_DIR, "data", "cache")
VAULT_FEED   = os.path.join(PROJECT_DIR, "vault", "Improvements", "line_moves.md")

CONSENSUS_WINDOW_SEC = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------
def american_to_implied_prob(odds) -> Optional[float]:
    """Vig-included implied probability (0-1). Matches clv._american_to_implied_prob.

    Tolerates 'EVEN'/'EV' (treated as +100) and stripped '+' signs.
    """
    if odds is None:
        return None
    s = str(odds).strip().upper()
    if s in ("EVEN", "EV"):
        return 0.5
    s = s.lstrip("+")
    try:
        o = int(s)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    if o >= 100:
        return 100.0 / (o + 100.0)
    return abs(o) / (abs(o) + 100.0)


def odds_pct_delta(odds_a, odds_b) -> Optional[float]:
    """Percent change in implied prob from odds_a -> odds_b (signed)."""
    pa = american_to_implied_prob(odds_a)
    pb = american_to_implied_prob(odds_b)
    if pa is None or pb is None or pa == 0:
        return None
    return ((pb - pa) / pa) * 100.0


def classify_move(line_delta: Optional[float], odds_delta_pct: Optional[float],
                  threshold_line: float, threshold_odds_pct: float) -> List[str]:
    """Return list of move tags. Empty if no threshold breached.

    A delta of exactly 0 is treated as "no move" even if the threshold is 0,
    so probing with threshold=0 stays sane.
    """
    tags: List[str] = []
    if (line_delta is not None and line_delta != 0
            and abs(line_delta) >= threshold_line):
        tags.append("LINE_UP" if line_delta > 0 else "LINE_DOWN")
    if (odds_delta_pct is not None and odds_delta_pct != 0
            and abs(odds_delta_pct) >= threshold_odds_pct):
        # ODDS_TIGHTEN = implied prob went UP (price moved against the bettor),
        # ODDS_LOOSEN = implied prob went DOWN (price got softer/longer).
        tags.append("ODDS_TIGHTEN" if odds_delta_pct > 0 else "ODDS_LOOSEN")
    return tags


def _to_american_int(odds) -> Optional[int]:
    """Coerce odds value to int. Returns None for blank/NaN/unparseable."""
    if odds is None:
        return None
    try:
        if pd.isna(odds):
            return None
    except (TypeError, ValueError):
        pass
    s = str(odds).strip().upper()
    if s in ("", "EVEN", "EV"):
        return 100 if s in ("EVEN", "EV") else None
    s = s.lstrip("+")
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _name_key(s) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _parse_ts(s) -> Optional[datetime]:
    if pd.isna(s):
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Core diffing
# ---------------------------------------------------------------------------
def diff_group(group: pd.DataFrame, threshold_line: float,
               threshold_odds_pct: float, book: str,
               player: str, stat: str) -> List[Dict]:
    """Diff consecutive snapshots in a (book, player, stat) group."""
    events: List[Dict] = []
    g = group.sort_values("captured_at").reset_index(drop=True)
    for i in range(1, len(g)):
        prev, curr = g.iloc[i - 1], g.iloc[i]
        line_a = prev.get("line")
        line_b = curr.get("line")
        line_delta: Optional[float] = None
        if pd.notna(line_a) and pd.notna(line_b):
            try:
                line_delta = float(line_b) - float(line_a)
            except (TypeError, ValueError):
                line_delta = None
        odds_a = prev.get("over_price")
        odds_b = curr.get("over_price")
        d_pct = odds_pct_delta(odds_a, odds_b)
        tags = classify_move(line_delta, d_pct, threshold_line, threshold_odds_pct)
        if not tags:
            continue
        events.append({
            "book": book,
            "player_name": player,
            "name_key": _name_key(player),
            "stat": stat,
            "ts_from": str(prev["captured_at"]),
            "ts_to": str(curr["captured_at"]),
            "line_from": (float(line_a) if pd.notna(line_a) else None),
            "line_to":   (float(line_b) if pd.notna(line_b) else None),
            "line_delta": line_delta,
            "odds_from": _to_american_int(odds_a),
            "odds_to":   _to_american_int(odds_b),
            "odds_pct_delta": (round(d_pct, 4) if d_pct is not None else None),
            "tags": tags,
            "consensus": False,
        })
    return events


def collapse_to_main_line(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse alt-line ladders to one main line per (book, player, stat, ts).

    The 'main' line is the row whose over_price implied prob is closest to
    0.5 — i.e. the line the book treats as the toss-up. This kills the
    spurious "29.5 -> 9.5" jumps that come from comparing two rungs of the
    alt ladder against each other.
    """
    if df.empty:
        return df
    df = df.copy()
    df["_imp_prob"] = df["over_price"].apply(american_to_implied_prob)
    df["_dist_to_half"] = (df["_imp_prob"] - 0.5).abs().fillna(1.0)
    df = df.sort_values(["book", "player_name", "stat", "captured_at",
                         "_dist_to_half"])
    df = df.drop_duplicates(
        subset=["book", "player_name", "stat", "captured_at"], keep="first")
    return df.drop(columns=["_imp_prob", "_dist_to_half"])


def detect_moves(df: pd.DataFrame, threshold_line: float,
                 threshold_odds_pct: float) -> List[Dict]:
    """Collapse alt-line ladders then group by (book, player_name, stat)
    and diff each group's consecutive snapshots."""
    out: List[Dict] = []
    if df.empty:
        return out
    needed = {"book", "player_name", "stat", "captured_at"}
    if not needed.issubset(df.columns):
        return out
    df = collapse_to_main_line(df)
    for (book, player, stat), g in df.groupby(["book", "player_name", "stat"],
                                              dropna=False):
        if len(g) < 2:
            continue
        out.extend(diff_group(g, threshold_line, threshold_odds_pct,
                              book, player, stat))
    return out


def tag_consensus(events: List[Dict],
                  window_sec: int = CONSENSUS_WINDOW_SEC) -> List[Dict]:
    """Mark events as CONSENSUS_STEAM when >=2 books move same direction
    within window_sec on the same (name_key, stat)."""
    # Group by (name_key, stat). For each event, look for another event with
    # a *different* book whose ts_to is within window AND whose dominant
    # direction agrees.
    def direction_of(ev: Dict) -> Optional[str]:
        for t in ev["tags"]:
            if t in ("LINE_UP", "LINE_DOWN"):
                return t
        for t in ev["tags"]:
            if t in ("ODDS_TIGHTEN", "ODDS_LOOSEN"):
                return t
        return None

    by_key: Dict[Tuple[str, str], List[Dict]] = {}
    for ev in events:
        by_key.setdefault((ev["name_key"], ev["stat"]), []).append(ev)
    for ks, evs in by_key.items():
        # Parse ts_to once
        for ev in evs:
            ev["_ts_to_dt"] = _parse_ts(ev["ts_to"])
        for i, ev_i in enumerate(evs):
            t_i = ev_i["_ts_to_dt"]
            dir_i = direction_of(ev_i)
            if t_i is None or dir_i is None:
                continue
            for j, ev_j in enumerate(evs):
                if i == j:
                    continue
                if ev_j["book"] == ev_i["book"]:
                    continue
                t_j = ev_j["_ts_to_dt"]
                if t_j is None:
                    continue
                if abs((t_j - t_i).total_seconds()) > window_sec:
                    continue
                if direction_of(ev_j) != dir_i:
                    continue
                ev_i["consensus"] = True
                if "CONSENSUS_STEAM" not in ev_i["tags"]:
                    ev_i["tags"].append("CONSENSUS_STEAM")
                break
    # Strip helper key
    for ev in events:
        ev.pop("_ts_to_dt", None)
    return events


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
REQUIRED_COLS = {"captured_at", "book", "player_name", "stat", "line", "over_price"}


def load_book_csvs(lines_dir: str, isodate: str) -> pd.DataFrame:
    """Load every player-props book CSV for the given date.

    Skips files that don't match the player-prop schema (e.g. *_mainline.csv
    game-total files which lack player_name) and drops rows with blank
    player_name.
    """
    pattern = os.path.join(lines_dir, f"{isodate}_*.csv")
    files = sorted(glob.glob(pattern))
    frames = []
    for fp in files:
        try:
            # on_bad_lines='skip' guards against schema-drift mid-file (some
            # scrapers append extra columns after a redeploy).
            df = pd.read_csv(fp, on_bad_lines="skip")
        except Exception as e:
            print(f"[warn] could not read {fp}: {e}", file=sys.stderr)
            continue
        if not REQUIRED_COLS.issubset(df.columns):
            # Not a player-props file — likely *_mainline.csv. Silently skip.
            continue
        df = df[df["player_name"].notna() & (df["player_name"].astype(str).str.strip() != "")]
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def event_dedup_key(ev: Dict) -> str:
    return f"{ev['book']}|{ev['name_key']}|{ev['stat']}|{ev['ts_from']}|{ev['ts_to']}"


def load_existing_event_keys(cache_path: str) -> set:
    keys: set = set()
    if not os.path.exists(cache_path):
        return keys
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    keys.add(event_dedup_key(ev))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return keys


def append_events(cache_path: str, events: List[Dict]) -> int:
    """JSONL append. Returns count actually written."""
    if not events:
        return 0
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "a", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, default=str) + "\n")
    return len(events)


def render_vault_feed(cache_path: str, vault_path: str, limit: int = 50) -> None:
    """Read the latest N events from cache_path and rewrite the vault feed."""
    if not os.path.exists(cache_path):
        return
    rows: List[Dict] = []
    with open(cache_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows = rows[-limit:][::-1]
    os.makedirs(os.path.dirname(vault_path), exist_ok=True)
    md = ["# Line Moves Feed",
          "",
          f"_Last {len(rows)} events. Updated {datetime.utcnow().isoformat()}Z._",
          "",
          "| ts_to | book | player | stat | line | odds | tags |",
          "|---|---|---|---|---|---|---|"]
    for ev in rows:
        line_str = f"{ev.get('line_from')} -> {ev.get('line_to')} (d={ev.get('line_delta')})"
        odds_str = f"{ev.get('odds_from')} -> {ev.get('odds_to')} ({ev.get('odds_pct_delta')}%)"
        tags = ",".join(ev.get("tags", []))
        md.append(f"| {ev.get('ts_to')} | {ev.get('book')} | {ev.get('player_name')} "
                  f"| {ev.get('stat')} | {line_str} | {odds_str} | {tags} |")
    with open(vault_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")


def fire_webhook(events: List[Dict]) -> int:
    """POST consensus-steam events to WEBHOOK_URL. No-op if unset."""
    url = os.environ.get("WEBHOOK_URL", "").strip()
    if not url:
        return 0
    sent = 0
    try:
        import urllib.request
        for ev in events:
            if not ev.get("consensus"):
                continue
            data = json.dumps(ev, default=str).encode("utf-8")
            req = urllib.request.Request(url, data=data,
                                         headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=3)
                sent += 1
            except Exception as e:
                print(f"[webhook warn] {e}", file=sys.stderr)
    except ImportError:
        pass
    return sent


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run_once(isodate: str, threshold_line: float, threshold_odds_pct: float,
             lines_dir: str = LINES_DIR, cache_dir: str = CACHE_DIR,
             vault_path: str = VAULT_FEED) -> Dict:
    """Single detector pass. Returns summary dict."""
    df = load_book_csvs(lines_dir, isodate)
    if df.empty:
        return {"events_new": 0, "events_total_today": 0,
                "consensus_new": 0, "rows_seen": 0}
    events = detect_moves(df, threshold_line, threshold_odds_pct)
    events = tag_consensus(events)

    cache_path = os.path.join(cache_dir, f"line_moves_{isodate}.json")
    existing = load_existing_event_keys(cache_path)
    new_events = [ev for ev in events if event_dedup_key(ev) not in existing]
    append_events(cache_path, new_events)
    render_vault_feed(cache_path, vault_path, limit=50)
    consensus_new = [ev for ev in new_events if ev.get("consensus")]
    fired = fire_webhook(consensus_new)
    # R21_N3 — layered alert (vault + critical-stack always; Discord if URL set).
    try:
        from src.alerts.discord_webhook import alert
        for ev in consensus_new:
            alert(
                f"STEAM: {ev.get('player_name', '?')} {ev.get('stat', '?')}",
                level="warn",
                tag="line_move_detector",
                source="line_move_detector",
                severity="STEAM",  # preserve R18_K3 blue embed color for consensus moves
                body=(f"book={ev.get('book', '?')}  "
                      f"line {ev.get('line_from', '?')}→{ev.get('line_to', '?')}  "
                      f"odds {ev.get('over_from', '?')}→{ev.get('over_to', '?')}"),
                fields=[{"name": "book", "value": str(ev.get('book', '?'))},
                        {"name": "tags", "value": ",".join(ev.get('tags', []))[:1024] or "-"}],
            )
    except Exception:
        pass
    return {
        "events_new": len(new_events),
        "events_total_today": len(existing) + len(new_events),
        "consensus_new": len(consensus_new),
        "rows_seen": len(df),
        "webhook_fired": fired,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval-sec", type=int, default=30)
    ap.add_argument("--threshold-line", type=float, default=0.5)
    ap.add_argument("--threshold-odds-pct", type=float, default=10.0)
    ap.add_argument("--once", action="store_true", help="single pass + exit")
    ap.add_argument("--date", type=str, default=None,
                    help="ISO date (YYYY-MM-DD). Defaults to today UTC.")
    ap.add_argument("--lines-dir", type=str, default=LINES_DIR)
    ap.add_argument("--cache-dir", type=str, default=CACHE_DIR)
    args = ap.parse_args()

    while True:
        # R19_L3 heartbeat
        _r19_hb('line_move_detector')
        isodate = args.date or datetime.utcnow().strftime("%Y-%m-%d")
        try:
            summary = run_once(isodate, args.threshold_line,
                               args.threshold_odds_pct,
                               lines_dir=args.lines_dir,
                               cache_dir=args.cache_dir)
            print(f"[{datetime.utcnow().isoformat()}Z] "
                  f"date={isodate} rows={summary['rows_seen']} "
                  f"new={summary['events_new']} "
                  f"consensus_new={summary['consensus_new']} "
                  f"total_today={summary['events_total_today']}",
                  flush=True)
        except Exception as e:
            print(f"[err] {e}", file=sys.stderr, flush=True)
        if args.once:
            break
        time.sleep(args.interval_sec)


if __name__ == "__main__":
    main()
