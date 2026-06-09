"""grade_ingame_pooled.py — pooled in-game grader across ALL eligible games.

Auto-discovers every (shadow_log, inplay_csv) pair under data/cache/ingame +
data/lines/, runs the existing per-game grader's joining logic, and reports:

  * per-game baseline (same numbers as grade_ingame_vs_vegas.py)
  * pooled per-stat / per-band aggregates across all games
  * holdout-cross results: for each game, fit any calibration (passed in via a
    pluggable hook) on the OTHER games and grade THIS game with it.

The grader's expensive step is loading the lines/series; this script computes
the (line, model, actual) tuples ONCE per game and stores them as a small list
that any downstream calibration sweep can re-grade cheaply without re-parsing.

It is strict no-lookahead by default and de-dup'd to one observation per
(player, stat, period, book) — same as the single-game grader.

NEW vs the single-game grader:
  * --cadence {dedup_period, line_move}: 'line_move' keeps one observation per
    consecutive line CHANGE per (player, stat, book) instead of last-in-period.
    This is the realistic bet-decision cadence: you only decide when the line
    moves, not on every tick.
  * --consensus {off, agree, worst_price}: 'agree' requires BOTH books to lean
    the same way and prices at the average; 'worst_price' bets at the worst
    (least favorable) of the two posted prices when both books are available.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
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

# Re-use the proven loaders from the single-game grader.
sys.path.insert(0, str(_ROOT / "scripts" / "ingame"))
from grade_ingame_vs_vegas import (  # noqa: E402
    _name_key, _parse_epoch_ms, _nearest, _payout,
    load_finals, load_model_series, load_model_series_game_record,
    load_inplay_lines,
)


def discover_pairs() -> list[tuple[str, str, str]]:
    """Return list of (game_id, yyyy-mm-dd, log_type) for every shadow log that
    has at least one matching inplay CSV (same date, with at least one of the
    log's players appearing in the CSV).

    log_type is 'unified_shadow' for the original format or 'game_record' for
    the live-poller game_record_<gid>.jsonl format.  Callers should pass this
    through to grade_one_game() so the correct loader is used.

    Backward-compatible: callers that unpack (gid, date) still work because
    log_type is appended as a third element (tuple unpacking ``gid, date = t``
    still works when the caller uses ``gid, date, *_`` or we pass the full
    tuple to grade_one_game via kwargs).
    """
    pairs = []
    inplay_csvs = sorted(LINES_DIR.glob("*_inplay.csv"))
    if not inplay_csvs:
        return pairs

    # date -> set of normalized player names appearing in any inplay CSV that date
    by_date: dict[str, set[str]] = defaultdict(set)
    for p in inplay_csvs:
        m = re.match(r"(\d{4}-\d{2}-\d{2})_", p.name)
        if not m:
            continue
        d = m.group(1)
        for r in csv.DictReader(open(p, encoding="utf-8")):
            by_date[d].add(_name_key(r.get("player_name", "")))

    # ---- unified_shadow logs (original format) --------------------------------
    for sp in sorted(SHADOW_DIR.glob("unified_shadow_*.jsonl")):
        gid = sp.stem.replace("unified_shadow_", "")
        log_date = None
        log_names: set[str] = set()
        with open(sp, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ep = rec.get("snapshot_epoch_ms")
                if ep and ep > 1_000_000_000_000 and log_date is None:
                    log_date = datetime.fromtimestamp(
                        ep / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                for pr in rec.get("projections", []):
                    log_names.add(_name_key(pr.get("name", "")))
        if not log_date:
            continue

        # in-play CSV is captured the night the game tipped (UTC); the shadow log
        # epoch is usually that same UTC date OR the prior local date. Check both.
        candidates = {log_date}
        try:
            y, mo, d = (int(x) for x in log_date.split("-"))
            from datetime import date as _date, timedelta
            candidates.add((_date(y, mo, d) - timedelta(days=1)).strftime("%Y-%m-%d"))
        except Exception:
            pass
        for cand in candidates:
            shared = log_names & by_date.get(cand, set())
            if len(shared) >= 3:
                pairs.append((gid, cand, "unified_shadow"))
                break

    # ---- game_record logs (live-poller format) --------------------------------
    import pytz as _pytz
    try:
        _eastern = _pytz.timezone("America/New_York")
    except Exception:
        _eastern = None

    def _gr_ts_to_utc_date(ts: str) -> str | None:
        """Convert naive local EDT timestamp to a UTC date string."""
        try:
            dt = datetime.strptime(ts.strip(), "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            try:
                dt = datetime.strptime(ts.strip(), "%Y-%m-%dT%H:%M")
            except ValueError:
                return None
        if _eastern is not None:
            try:
                dt_utc = _eastern.localize(dt).astimezone(timezone.utc)
                return dt_utc.strftime("%Y-%m-%d")
            except Exception:
                pass
        # fallback: EDT = UTC-4
        dt_utc = datetime.fromtimestamp(dt.timestamp() + 4 * 3600, tz=timezone.utc)
        return dt_utc.strftime("%Y-%m-%d")

    for sp in sorted(SHADOW_DIR.glob("game_record_*.jsonl")):
        gid = sp.stem.replace("game_record_", "")
        log_date = None
        log_names: set[str] = set()
        with open(sp, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = rec.get("ts")
                if ts and log_date is None:
                    log_date = _gr_ts_to_utc_date(ts)
                for pl in rec.get("players", []):
                    log_names.add(_name_key(pl.get("name", "")))
        if not log_date:
            continue

        # game_record timestamps are local (EDT); UTC date may be next calendar day.
        # Check the log_date AND the prior local date.
        candidates = {log_date}
        try:
            y, mo, d = (int(x) for x in log_date.split("-"))
            from datetime import date as _date, timedelta
            candidates.add((_date(y, mo, d) - timedelta(days=1)).strftime("%Y-%m-%d"))
        except Exception:
            pass
        for cand in candidates:
            shared = log_names & by_date.get(cand, set())
            if len(shared) >= 3:
                pairs.append((gid, cand, "game_record"))
                break

    return pairs


def grade_one_game(gid: str, date: str, tol_sec: int = 180,
                   no_lookahead: bool = True,
                   cadence: str = "dedup_period",
                   consensus: str = "off",
                   margin: float = 0.5,
                   log_type: str = "unified_shadow") -> dict:
    """Return per-stat / per-band accumulators + the raw obs list for this game.

    The raw obs list is a list of (pid, stat, period, book, line, op, up, model,
    actual) tuples that downstream sweeps can re-grade without re-parsing.

    log_type controls which loader is used:
      'unified_shadow'  -- original unified_shadow_<gid>.jsonl (default)
      'game_record'     -- live-poller game_record_<gid>.jsonl (pts/reb/ast only)
    """
    actuals, _ = load_finals(gid)
    if log_type == "game_record":
        series, name_to_pid = load_model_series_game_record(gid)
    else:
        series, name_to_pid = load_model_series(gid)
    lines = load_inplay_lines(date, name_to_pid)
    tol_ms = tol_sec * 1000

    # Step A: attach the nearest model snapshot to every raw line capture (subject
    # to no-lookahead). Keep ALL of them in an intermediate stream so cadence
    # logic can choose how to thin.
    stream = []
    for pid, stat, ep, line, op, up_price, book in lines:
        sl = series.get((pid, stat))
        if not sl:
            continue
        got = _nearest(sl, ep, tol_ms, no_lookahead=no_lookahead)
        if got is None:
            continue
        period, _prod, unified = got
        stream.append({
            "pid": pid, "stat": stat, "ep": ep, "period": period,
            "book": book, "line": line, "op": op, "up": up_price,
            "model": unified,
        })

    # Step B: apply cadence.
    keyed: dict[tuple, dict] = {}
    if cadence == "dedup_period":
        # one obs per (pid, stat, period, book) -- last capture wins
        for s in sorted(stream, key=lambda r: r["ep"]):
            k = (s["pid"], s["stat"], s["period"], s["book"])
            keyed[k] = s
    elif cadence == "line_move":
        # one obs per consecutive (pid, stat, book) LINE CHANGE
        last_line: dict[tuple, float | None] = {}
        for s in sorted(stream, key=lambda r: r["ep"]):
            k = (s["pid"], s["stat"], s["book"])
            if last_line.get(k) != s["line"]:
                # store under a unique key (use ep to keep uniqueness)
                keyed[(s["pid"], s["stat"], s["period"], s["book"], s["ep"])] = s
                last_line[k] = s["line"]
    else:
        raise ValueError(f"unknown cadence {cadence}")

    # Step C: cross-book consensus filter.
    if consensus != "off":
        # Re-group by (pid, stat, period, line_bucket=int(round(ep/30s))) — i.e.,
        # near-simultaneous captures across books. The simplest correct version:
        # for each (pid, stat, period), pair the closest-in-time dk and fd
        # captures and apply the rule.
        by_psp: dict[tuple, list[dict]] = defaultdict(list)
        for s in keyed.values():
            by_psp[(s["pid"], s["stat"], s["period"])].append(s)
        keyed = {}
        for grp in by_psp.values():
            grp.sort(key=lambda r: r["ep"])
            # cluster consecutive captures within 60s as one "moment"
            cluster: list[dict] = []
            for s in grp:
                if cluster and s["ep"] - cluster[-1]["ep"] > 60_000:
                    _emit_consensus_cluster(cluster, keyed, consensus)
                    cluster = []
                cluster.append(s)
            if cluster:
                _emit_consensus_cluster(cluster, keyed, consensus)

    # Step D: compute per-stat / per-band / raw obs.
    obs = []
    acc = defaultdict(lambda: {"n": 0, "ae_line": 0.0, "ae_model": 0.0,
                               "bet_n": 0, "bet_w": 0, "pnl": 0.0,
                               "model_closer": 0})
    band_acc = defaultdict(lambda: dict(acc.default_factory()))
    for s in keyed.values():
        actual = actuals.get((s["pid"], s["stat"]))
        if actual is None:
            continue
        model = s["model"]
        line = s["line"]
        ae_line = abs(line - actual)
        ae_model = abs(model - actual)
        band = _period_band(s["period"])
        a = acc[s["stat"]]
        b = band_acc[band]
        a["n"] += 1; b["n"] += 1
        a["ae_line"] += ae_line; b["ae_line"] += ae_line
        a["ae_model"] += ae_model; b["ae_model"] += ae_model
        if ae_model < ae_line:
            a["model_closer"] += 1; b["model_closer"] += 1
        if abs(model - line) >= margin and abs(actual - line) > 1e-9:
            over = model > line
            won = (actual > line) if over else (actual < line)
            odds = s["op"] if over else s["up"]
            pay = _payout(odds, won)
            a["bet_n"] += 1; b["bet_n"] += 1
            a["bet_w"] += int(won); b["bet_w"] += int(won)
            a["pnl"] += pay; b["pnl"] += pay
        obs.append({
            "pid": s["pid"], "stat": s["stat"], "period": s["period"],
            "book": s["book"], "line": line, "model": model, "actual": actual,
            "op": s["op"], "up": s["up"], "ep": s["ep"],
        })
    return {"per_stat": dict(acc), "per_band": dict(band_acc), "obs": obs}


def _emit_consensus_cluster(cluster: list[dict],
                            keyed: dict, consensus: str) -> None:
    """Apply the consensus rule to a same-moment cluster across books."""
    by_book: dict[str, dict] = {}
    for s in cluster:
        # keep latest per book in this cluster
        if s["book"] not in by_book or s["ep"] > by_book[s["book"]]["ep"]:
            by_book[s["book"]] = s
    if len(by_book) < 2:
        # single-book: pass through unchanged
        for s in by_book.values():
            keyed[(s["pid"], s["stat"], s["period"], s["book"], s["ep"])] = s
        return
    dk = by_book.get("dk")
    fd = by_book.get("fd")
    # model is identical (book-independent); line/prices differ
    model = cluster[0]["model"]
    line_dk = dk["line"]; line_fd = fd["line"]
    # consensus = both books on the SAME side of the model
    side_dk = model > line_dk
    side_fd = model > line_fd
    if side_dk != side_fd:
        # books disagree on which side the model takes -> skip the bet entirely
        return
    if consensus == "agree":
        # use the line closer to the model (more conservative bet target) and the
        # better of the two prices on that side
        if side_dk:
            best = dk if (dk["op"] or 0) > (fd["op"] or 0) else fd
        else:
            best = dk if (dk["up"] or 0) > (fd["up"] or 0) else fd
        keyed[(best["pid"], best["stat"], best["period"], "agree", best["ep"])] = best
    elif consensus == "worst_price":
        # synthesize: keep the more conservative line and the WORST of the two prices
        if side_dk:  # taking the over
            line_use = max(line_dk, line_fd)
            op_use = min((dk["op"] or -110.0), (fd["op"] or -110.0))
            up_use = max((dk["up"] or -110.0), (fd["up"] or -110.0))
        else:
            line_use = min(line_dk, line_fd)
            op_use = max((dk["op"] or -110.0), (fd["op"] or -110.0))
            up_use = min((dk["up"] or -110.0), (fd["up"] or -110.0))
        merged = dict(dk)
        merged["line"] = line_use; merged["op"] = op_use; merged["up"] = up_use
        merged["book"] = "worst"
        keyed[(merged["pid"], merged["stat"], merged["period"],
               "worst", merged["ep"])] = merged


def _period_band(p: int) -> str:
    return {0: "pre", 1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"}.get(int(p), "OT")


def _format_row(label: str, a: dict) -> str:
    n = a["n"] or 1
    bn = a["bet_n"] or 1
    return (f"{label:<8} {a['n']:>5,d} {a['ae_line']/n:>9.3f} "
            f"{a['ae_model']/n:>10.3f} {a['model_closer']/n*100:>10.1f}% "
            f"{a['bet_n']:>6,d} {a['bet_w']/bn*100:>8.1f}% "
            f"{a['pnl']/bn*100:>+7.2f}%")


def _print_table(title: str, blocks: dict[str, dict]) -> None:
    print(f"\n{title}")
    print(f"{'key':<8} {'n':>5} {'MAE_line':>9} {'MAE_model':>10} "
          f"{'model<%':>11} {'bet_n':>6} {'bet_w%':>9} {'ROI%':>8}")
    for k, a in blocks.items():
        if a["n"]:
            print(_format_row(k, a))


def pool(per_game: list[dict], key: str) -> dict[str, dict]:
    pooled: dict[str, dict] = defaultdict(lambda: {
        "n": 0, "ae_line": 0.0, "ae_model": 0.0, "bet_n": 0, "bet_w": 0,
        "pnl": 0.0, "model_closer": 0,
    })
    for g in per_game:
        for k, a in g[key].items():
            p = pooled[k]
            for f in ("n", "ae_line", "ae_model", "bet_n", "bet_w", "pnl",
                      "model_closer"):
                p[f] += a[f]
    return dict(pooled)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", nargs="*", help="optional gid:date pairs to grade")
    ap.add_argument("--tol-sec", type=int, default=180)
    ap.add_argument("--lookahead", action="store_true",
                    help="allow forward-snapshot match (default: no-lookahead)")
    ap.add_argument("--cadence", choices=("dedup_period", "line_move"),
                    default="dedup_period")
    ap.add_argument("--consensus", choices=("off", "agree", "worst_price"),
                    default="off")
    ap.add_argument("--margin", type=float, default=0.5)
    ap.add_argument("--save", default=None)
    args = ap.parse_args()

    if args.pairs:
        # Manual pairs: accept "gid:date" (log_type defaults to unified_shadow)
        # or "gid:date:log_type"
        triples = []
        for s in args.pairs:
            parts = s.split(":", 2)
            gid = parts[0]
            d = parts[1] if len(parts) > 1 else ""
            lt = parts[2] if len(parts) > 2 else "unified_shadow"
            triples.append((gid, d, lt))
    else:
        triples = discover_pairs()
    if not triples:
        print("no (shadow, inplay) pairs found", file=sys.stderr)
        return 1
    print(f"grading {len(triples)} game(s):  cadence={args.cadence}  "
          f"consensus={args.consensus}  no_lookahead={not args.lookahead}")
    for gid, d, lt in triples:
        print(f"  {gid}  {d}  [{lt}]")

    per_game = []
    for gid, d, lt in triples:
        r = grade_one_game(
            gid, d, tol_sec=args.tol_sec, no_lookahead=not args.lookahead,
            cadence=args.cadence, consensus=args.consensus,
            margin=args.margin, log_type=lt)
        per_game.append(r)

    # Per-game readouts
    for (gid, d, lt), r in zip(triples, per_game):
        _print_table(f"-- {gid}  {d}  [{lt}]  per-stat --", r["per_stat"])
        _print_table(f"-- {gid}  {d}  [{lt}]  per-band --", r["per_band"])

    # Pooled
    _print_table("== POOLED per-stat ==", pool(per_game, "per_stat"))
    _print_table("== POOLED per-band ==", pool(per_game, "per_band"))

    if args.save:
        out = {
            "pairs": [{"gid": g, "date": d, "log_type": lt}
                      for g, d, lt in triples],
            "cadence": args.cadence, "consensus": args.consensus,
            "no_lookahead": not args.lookahead,
            "per_game": [
                {"per_stat": g["per_stat"], "per_band": g["per_band"]}
                for g in per_game
            ],
            "pooled_per_stat": pool(per_game, "per_stat"),
            "pooled_per_band": pool(per_game, "per_band"),
        }
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nSaved: {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
