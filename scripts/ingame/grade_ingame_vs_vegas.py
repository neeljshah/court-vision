"""grade_ingame_vs_vegas.py — in-game projections vs REAL in-play Vegas lines.

The existing in-game evals grade the model's projection MAE against the final
box. They never compare the model to the MARKET's live in-play line. This does.

For one game it joins three real sources:
  * model projections   — data/cache/ingame/unified_shadow_<gid>.jsonl
                          (prod_proj + unified_proj per player/stat/timestamp)
  * Vegas in-play lines  — data/lines/<date>_{dk,fd}_inplay.csv
                          (line + over/under price per player/stat/timestamp)
  * final actuals        — data/live/<gid>_*.json (highest-score snapshot)

For every in-play line capture it finds the model snapshot nearest in wall-clock
time (within --tol-sec) and asks the only two questions that matter:

  1. ACCURACY  — at that mid-game moment, who is closer to the FINAL value:
     the market's line or the model's projection?  (mean abs error)
  2. EDGE      — bet over/under whenever the model disagrees with the line by
     >= --margin; settle vs the final; ROI at the ACTUAL posted odds.

One game is noisy. This is an honest single-game read-out, not a validated edge.
Output -> stdout + .planning/ingame/vs_vegas_<gid>.json
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
import unicodedata
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
SHADOW_DIR = _ROOT / "data" / "cache" / "ingame"
LINES_DIR = _ROOT / "data" / "lines"
LIVE_DIR = _ROOT / "data" / "live"
PLAN_DIR = _ROOT / ".planning" / "ingame"

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _name_key(s: str) -> str:
    s = s or ""
    # strip "(OKC)" style team suffix some books append
    if "(" in s:
        s = s[:s.index("(")]
    nfkd = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in nfkd if not unicodedata.combining(c))
    return s.lower().strip()


def _parse_epoch_ms(ts: str) -> int | None:
    if not ts:
        return None
    ts = ts.strip().replace("Z", "+00:00")
    # dk uses '...T00:52+00:00' (no seconds) — datetime handles it; fd '...T00:16:58' (no tz)
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                dt = datetime.strptime(ts, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def load_finals(gid: str):
    """actuals[(player_id, stat)] = value, from the highest-score snapshot."""
    paths = sorted(glob.glob(str(LIVE_DIR / f"{gid}_*.json")))
    best = None
    best_total = -1
    for p in paths:
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        tot = (d.get("home_score") or 0) + (d.get("away_score") or 0)
        if tot > best_total and d.get("players"):
            best_total, best = tot, d
    actuals = {}
    pid_name = {}
    if not best:
        return actuals, pid_name
    for pl in best["players"]:
        pid = pl.get("player_id")
        pid_name[pid] = pl.get("name", "")
        for s in STATS:
            if pl.get(s) is not None:
                actuals[(pid, s)] = float(pl[s])
    return actuals, pid_name


def load_model_series(gid: str):
    """series[(pid, stat)] = sorted list of (epoch_ms, period, prod_proj, unified_proj).
    name_to_pid maps normalized player name -> pid (from the model log)."""
    path = SHADOW_DIR / f"unified_shadow_{gid}.jsonl"
    series = defaultdict(list)
    name_to_pid = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ep = rec.get("snapshot_epoch_ms")
            if ep is None:
                continue
            period = int(rec.get("period") or 0)
            for p in rec.get("projections", []):
                pid = p.get("player_id")
                stat = p.get("stat")
                if pid is None or stat not in STATS:
                    continue
                name_to_pid.setdefault(_name_key(p.get("name", "")), pid)
                up = p.get("unified_proj")
                pp = p.get("prod_proj")
                if up is None:
                    continue
                series[(pid, stat)].append((int(ep), period, pp, float(up)))
    for k in series:
        series[k].sort(key=lambda t: t[0])
    return series, name_to_pid


def load_model_series_game_record(gid: str):
    """Adapter for the game_record_<gid>.jsonl log format produced by the live
    golive poller.  Returns the same (series, name_to_pid) shape as
    load_model_series() so the pooled grader can use either loader.

    game_record format: one JSON object per line with keys:
      ts        -- naive ISO timestamp (US/Eastern local time, EDT = UTC-4)
      iter      -- snapshot counter
      players   -- list of {name, team, min, cur_pts/reb/ast,
                              proj_pts, proj_reb, proj_ast, shrink, out, ...}
    There is no player_id in the log; we build name_to_pid from the final
    live box (data/live/<gid>_*.json, highest-score snapshot), which has
    player_id for every player who actually played.

    Period is inferred from the cumulative score total (home_cur + away_cur):
      total < 50  -> Q1   (50-100  -> Q2   (100-150 -> Q3   else -> Q4)
    This is approximate but good enough for the per-band slice.

    Only pts/reb/ast are available (no fg3m/stl/blk/tov in this log).
    """
    import glob as _glob
    import pytz as _pytz

    # Step 1: build name_to_pid from the final box.
    live_files = sorted(_glob.glob(str(LIVE_DIR / f"{gid}_*.json")))
    best_box = None
    best_total = -1
    for p in live_files:
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        tot = (d.get("home_score") or 0) + (d.get("away_score") or 0)
        if tot > best_total and d.get("players"):
            best_total, best_box = tot, d
    name_to_pid: dict[str, int] = {}
    final_score_total: int = best_total  # used to detect post-game snapshots
    if best_box:
        for pl in best_box["players"]:
            pid = pl.get("player_id")
            if pid is not None:
                name_to_pid[_name_key(pl.get("name", ""))] = pid

    # Step 2: parse the game_record log.
    _GAME_RECORD_STATS = ("pts", "reb", "ast")  # only these exist in this log
    path = SHADOW_DIR / f"game_record_{gid}.jsonl"
    series: dict = defaultdict(list)

    try:
        eastern = _pytz.timezone("America/New_York")
    except Exception:
        eastern = None

    def _ts_to_ep(ts: str) -> int | None:
        """Convert naive local (EDT) or UTC ISO timestamp to epoch_ms."""
        ts = ts.strip()
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            try:
                dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M")
            except ValueError:
                return None
        if eastern is not None:
            # treat as US/Eastern (EDT = UTC-4 in June)
            try:
                dt = eastern.localize(dt)
                return int(dt.timestamp() * 1000)
            except Exception:
                pass
        # fallback: assume EDT offset (-4h)
        return int((dt.timestamp() + 4 * 3600) * 1000)

    def _infer_period(home_cur: float, away_cur: float) -> int:
        total = (home_cur or 0) + (away_cur or 0)
        if total < 50:
            return 1
        if total < 100:
            return 2
        if total < 150:
            return 3
        return 4

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ep = _ts_to_ep(rec.get("ts", ""))
            if ep is None:
                continue
            # Skip post-game snapshots: once the running total equals the final
            # score the game is over and all model projections converge to current
            # values.  Keeping them would give the model a spurious advantage
            # (proj ≈ actual by construction) and massively inflate ROI.
            home_cur = rec.get("home_cur") or 0
            away_cur = rec.get("away_cur") or 0
            if final_score_total > 0 and (home_cur + away_cur) >= final_score_total:
                continue
            period = _infer_period(home_cur, away_cur)
            for pl in rec.get("players", []):
                name = _name_key(pl.get("name", ""))
                pid = name_to_pid.get(name)
                if pid is None:
                    continue
                for stat in _GAME_RECORD_STATS:
                    proj = pl.get(f"proj_{stat}")
                    if proj is None:
                        continue
                    try:
                        proj = float(proj)
                    except (TypeError, ValueError):
                        continue
                    if not (proj == proj):  # NaN guard
                        continue
                    # (epoch_ms, period, prod_proj=None, unified_proj)
                    series[(pid, stat)].append((ep, period, None, proj))

    for k in series:
        series[k].sort(key=lambda t: t[0])
    return series, name_to_pid


def load_inplay_lines(date: str, name_to_pid: dict):
    """List of (pid, stat, epoch_ms, line, over_price, under_price, book) for players
    present in the model log (which isolates the one game).

    IMPORTANT — main-line selection. Books emit the WHOLE alt-line ladder per
    tick (e.g. FanDuel posts pts at 9.5/14.5/19.5/24.5 every ~30s), not just the
    'main' line you'd bet at. Keeping all of them and then dedup'ing by (pid,
    stat, period, book) silently chooses the alt-line tier whose ROW happens to
    come first/last in the CSV — a measurement bias that can swing the
    grader's MAE by 2x and inflate ROI by tens of points. We collapse
    same-ep alt-line ticks to ONE record: the most-balanced line (smallest
    |over_price - under_price|) — that is the main line on every book.
    """
    out = []
    # group per (pid, stat, book, ep) so we can pick the main alt-line per moment
    grouped: dict[tuple, list[tuple]] = {}
    for book in ("dk", "fd"):
        path = LINES_DIR / f"{date}_{book}_inplay.csv"
        if not path.exists():
            continue
        for r in csv.DictReader(open(path, encoding="utf-8")):
            stat = (r.get("stat") or "").strip().lower()
            if stat not in STATS:
                continue
            pid = name_to_pid.get(_name_key(r.get("player_name", "")))
            if pid is None:
                continue  # not in this game's model log
            ep = _parse_epoch_ms(r.get("captured_at", ""))
            if ep is None:
                continue
            try:
                line = float(r["line"])
            except (ValueError, KeyError, TypeError):
                continue

            def _f(x):
                try:
                    return float(x)
                except (ValueError, TypeError):
                    return None
            grouped.setdefault((pid, stat, book, ep), []).append(
                (line, _f(r.get("over_price")), _f(r.get("under_price"))))

    for (pid, stat, book, ep), tiers in grouped.items():
        # smallest |op - up| = most balanced book = main line
        def _spread(t):
            line, op, up = t
            if op is None or up is None:
                return float("inf")
            return abs(op - up)
        tiers.sort(key=_spread)
        line, op, up = tiers[0]
        out.append((pid, stat, ep, line, op, up, book))
    return out


def _nearest(series_list, ep, tol_ms, no_lookahead=False):
    """Return (period, prod, unified) at the snapshot nearest ep within tol, else None.

    no_lookahead=True restricts to snapshots at or BEFORE ep, so the model may
    only use information available when the line was captured (kills the up-to-tol
    forward-information advantage of matching a fresher snapshot to a stale line).
    """
    times = [t[0] for t in series_list]
    i = bisect_left(times, ep)
    best = None
    best_d = tol_ms + 1
    cand = (i - 1, i) if no_lookahead else (i - 1, i, i + 1)
    for j in cand:
        if 0 <= j < len(series_list):
            t = series_list[j][0]
            if no_lookahead and t > ep:
                continue
            d = abs(t - ep)
            if d < best_d:
                best_d, best = d, series_list[j]
    if best is None:
        return None
    return best[1], best[2], best[3]  # period, prod, unified


def _payout(odds, win):
    if odds is None:
        odds = -110.0
    if not win:
        return -1.0
    return (100.0 / abs(odds)) if odds < 0 else (odds / 100.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-id", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD of the in-play CSVs")
    ap.add_argument("--tol-sec", type=int, default=180)
    ap.add_argument("--margin", type=float, default=0.5,
                    help="min |proj-line| to place a bet")
    ap.add_argument("--no-lookahead", action="store_true",
                    help="model may only use snapshots at/before each line capture")
    args = ap.parse_args()
    tol_ms = args.tol_sec * 1000
    nla = args.no_lookahead

    actuals, _ = load_finals(args.game_id)
    series, name_to_pid = load_model_series(args.game_id)
    lines = load_inplay_lines(args.date, name_to_pid)
    print(f"game {args.game_id}  finals={len(actuals)}  model_series={len(series)}  "
          f"inplay_captures={len(lines):,}\n")

    # ---- De-dup to ONE observation per (pid, stat, period, book) ----
    # 35k captures are NOT independent: each player-stat is sampled hundreds of
    # times per game. Collapse to the LAST capture in each game period (book kept
    # separate so dk and fd don't double-count the same moment differently). This
    # turns ~27k autocorrelated ticks into ~ (players x stats x periods x books)
    # near-independent observations and lets us split early vs late game.
    keyed = {}  # (pid, stat, period, book) -> (ep, line, op, up_price)
    for pid, stat, ep, line, op, up_price, book in lines:
        sl = series.get((pid, stat))
        if not sl:
            continue
        got = _nearest(sl, ep, tol_ms, no_lookahead=nla)
        if got is None:
            continue
        period = got[0]
        k = (pid, stat, period, book)
        prev = keyed.get(k)
        if prev is None or ep > prev[0]:
            keyed[k] = (ep, line, op, up_price)

    def _period_band(p):
        if p <= 0:
            return "pre"
        if p == 1:
            return "Q1"
        if p == 2:
            return "Q2"
        if p == 3:
            return "Q3"
        if p == 4:
            return "Q4"
        return "OT"

    # per-stat and per-band accumulators
    acc = defaultdict(lambda: {"n": 0, "ae_line": 0.0, "ae_unified": 0.0,
                               "ae_prod": 0.0, "bet_n": 0, "bet_w": 0,
                               "pnl": 0.0, "line_closer": 0, "model_closer": 0})
    band_acc = defaultdict(lambda: {"n": 0, "ae_line": 0.0, "ae_unified": 0.0,
                                    "bet_n": 0, "bet_w": 0, "pnl": 0.0,
                                    "model_closer": 0})
    for (pid, stat, period, book), (ep, line, op, up_price) in keyed.items():
        actual = actuals.get((pid, stat))
        if actual is None:
            continue
        sl = series.get((pid, stat))
        got = _nearest(sl, ep, tol_ms, no_lookahead=nla)
        if got is None:
            continue
        _per, prod, unified = got
        a = acc[stat]
        band = band_acc[_period_band(period)]
        a["n"] += 1
        band["n"] += 1
        ae_line = abs(line - actual)
        ae_uni = abs(unified - actual)
        a["ae_line"] += ae_line
        a["ae_unified"] += ae_uni
        a["ae_prod"] += abs((prod if prod is not None else unified) - actual)
        band["ae_line"] += ae_line
        band["ae_unified"] += ae_uni
        if ae_uni < ae_line:
            a["model_closer"] += 1
            band["model_closer"] += 1
        elif ae_line < ae_uni:
            a["line_closer"] += 1
        # betting: model vs line
        if abs(unified - line) >= args.margin and abs(actual - line) > 1e-9:
            over = unified > line
            won = (actual > line) if over else (actual < line)
            odds = op if over else up_price
            a["bet_n"] += 1
            a["bet_w"] += int(won)
            a["pnl"] += _payout(odds, won)
            band["bet_n"] += 1
            band["bet_w"] += int(won)
            band["pnl"] += _payout(odds, won)

    # report
    tot = {"n": 0, "ae_line": 0.0, "ae_unified": 0.0, "bet_n": 0, "bet_w": 0,
           "pnl": 0.0, "model_closer": 0, "line_closer": 0}
    print(f"{'stat':<5} {'n':>5} {'MAE_line':>9} {'MAE_model':>10} {'model<line%':>11} "
          f"{'bet_n':>6} {'bet_win%':>9} {'ROI%':>8}")
    out_stats = {}
    for stat in STATS:
        a = acc.get(stat)
        if not a or a["n"] == 0:
            continue
        mae_line = a["ae_line"] / a["n"]
        mae_model = a["ae_unified"] / a["n"]
        mc_pct = a["model_closer"] / a["n"] * 100
        roi = a["pnl"] / a["bet_n"] * 100 if a["bet_n"] else 0.0
        bw = a["bet_w"] / a["bet_n"] * 100 if a["bet_n"] else 0.0
        print(f"{stat:<5} {a['n']:>5,d} {mae_line:>9.3f} {mae_model:>10.3f} "
              f"{mc_pct:>10.1f}% {a['bet_n']:>6,d} {bw:>8.1f}% {roi:>+7.2f}%")
        for k in ("n", "bet_n", "bet_w", "model_closer", "line_closer"):
            tot[k] += a[k]
        tot["ae_line"] += a["ae_line"]
        tot["ae_unified"] += a["ae_unified"]
        tot["pnl"] += a["pnl"]
        out_stats[stat] = {"n": a["n"], "mae_line": mae_line, "mae_model": mae_model,
                           "model_closer_pct": mc_pct, "bet_n": a["bet_n"],
                           "bet_win_pct": bw, "roi_pct": roi}
    if tot["n"]:
        print("-" * 72)
        mae_line = tot["ae_line"] / tot["n"]
        mae_model = tot["ae_unified"] / tot["n"]
        mc_pct = tot["model_closer"] / tot["n"] * 100
        roi = tot["pnl"] / tot["bet_n"] * 100 if tot["bet_n"] else 0.0
        bw = tot["bet_w"] / tot["bet_n"] * 100 if tot["bet_n"] else 0.0
        print(f"{'ALL':<5} {tot['n']:>5,d} {mae_line:>9.3f} {mae_model:>10.3f} "
              f"{mc_pct:>10.1f}% {tot['bet_n']:>6,d} {bw:>8.1f}% {roi:>+7.2f}%")

    # ---- per game-period band (early vs late = real uncertainty vs determinism) ----
    print("\nBy game period (de-dup'd; late periods are near-deterministic):")
    print(f"{'band':<5} {'n':>5} {'MAE_line':>9} {'MAE_model':>10} {'model<line%':>11} "
          f"{'bet_n':>6} {'bet_win%':>9} {'ROI%':>8}")
    out_bands = {}
    for band in ("pre", "Q1", "Q2", "Q3", "Q4", "OT"):
        b = band_acc.get(band)
        if not b or b["n"] == 0:
            continue
        mae_line = b["ae_line"] / b["n"]
        mae_model = b["ae_unified"] / b["n"]
        mc_pct = b["model_closer"] / b["n"] * 100
        roi = b["pnl"] / b["bet_n"] * 100 if b["bet_n"] else 0.0
        bw = b["bet_w"] / b["bet_n"] * 100 if b["bet_n"] else 0.0
        print(f"{band:<5} {b['n']:>5,d} {mae_line:>9.3f} {mae_model:>10.3f} "
              f"{mc_pct:>10.1f}% {b['bet_n']:>6,d} {bw:>8.1f}% {roi:>+7.2f}%")
        out_bands[band] = {"n": b["n"], "mae_line": mae_line, "mae_model": mae_model,
                           "model_closer_pct": mc_pct, "bet_n": b["bet_n"],
                           "bet_win_pct": bw, "roi_pct": roi}

    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PLAN_DIR / f"vs_vegas_{args.game_id}.json"
    out_path.write_text(json.dumps({
        "game_id": args.game_id, "date": args.date,
        "tol_sec": args.tol_sec, "margin": args.margin,
        "overall": {"n": tot["n"],
                    "mae_line": tot["ae_line"] / tot["n"] if tot["n"] else None,
                    "mae_model": tot["ae_unified"] / tot["n"] if tot["n"] else None,
                    "model_closer_pct": tot["model_closer"] / tot["n"] * 100 if tot["n"] else None,
                    "bet_n": tot["bet_n"],
                    "bet_win_pct": tot["bet_w"] / tot["bet_n"] * 100 if tot["bet_n"] else None,
                    "roi_pct": tot["pnl"] / tot["bet_n"] * 100 if tot["bet_n"] else None},
        "per_stat": out_stats,
        "per_band": out_bands,
        "note": "Single game; honest read-out, not a validated edge. De-dup'd to one obs per (player,stat,period,book). Model=unified_proj, ROI at actual posted odds.",
    }, indent=2), encoding="utf-8")
    print(f"\nResults: {out_path.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
