"""live_rec_tracker.py - R24_Q4 daily tracker for R23_P8's live recommendation engine.

Three modes:

  --snapshot       Run live_recommendation_engine.run_engine(bankroll, top) and
                   persist the rec list to data/cache/rec_tracker/rec_snapshot_<date>.json
                   with timestamp, bankroll context, and a deterministic rec_id
                   per bet (hash of player+stat+line+side+book+date).

  --settle DATE    Read the snapshot for DATE (YYYY-MM-DD); for each rec look
                   up the actual stat value from data/cache/quarter_box (sum of
                   q1..q4) or from a synthetic boxscore dir. Compute WIN/LOSS/PUSH
                   and per-rec profit (assumes -110 if odds missing). Append to
                   data/cache/rec_tracker/rec_settled.parquet. Idempotent: a
                   second --settle of the same date deduplicates by rec_id.

  --report         Aggregate rec_settled.parquet and print:
                       total recs, win-rate, ROI, mean-edge winners vs losers,
                       by-stat breakdown.

CLI:
    python scripts/live_rec_tracker.py --snapshot
    python scripts/live_rec_tracker.py --settle 2026-05-26
    python scripts/live_rec_tracker.py --report [--days 7|30|all]

Public API used by tests:
    rec_id_for(rec, date)                    -> deterministic SHA1 12-hex
    snapshot(payload, snapshot_dir, date)    -> path to written file
    settle(date, snapshot_dir, settled_path, boxscore_loader=None) -> dict
    report(settled_path, days="all")         -> dict
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import unicodedata
from datetime import date as _date_cls
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Standard locations (overridable by tests / probe via kwargs)
DEFAULT_SNAPSHOT_DIR = os.path.join(PROJECT_DIR, "data", "cache", "rec_tracker")
DEFAULT_SETTLED_PATH = os.path.join(DEFAULT_SNAPSHOT_DIR, "rec_settled.parquet")
DEFAULT_QB_DIR = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")

# Map ledger/rec stat names to NBA box-score field names (q*.json uses "to" for tov).
_STAT_TO_BOX_FIELD = {
    "pts":  "pts",
    "reb":  "reb",
    "ast":  "ast",
    "fg3m": "fg3m",
    "stl":  "stl",
    "blk":  "blk",
    "tov":  "to",
}


# ============================================================================ #
# Helpers                                                                       #
# ============================================================================ #
def _player_key(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.lower().strip()


def _american_payout(odds: int, stake: float = 1.0) -> float:
    o = int(odds)
    if o >= 100:
        return stake * o / 100.0
    return stake * 100.0 / abs(o or 1)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rec_id_for(rec: Dict[str, Any], date_str: str) -> str:
    """Deterministic 12-hex id derived from player|stat|line|side|book|date.

    Changes to any of those fields produce a new id (test asserted).
    """
    parts = [
        _player_key(rec.get("player", "")),
        str(rec.get("stat", "")).strip().lower(),
        f"{float(rec.get('line', 0.0)):.2f}",
        str(rec.get("side", "")).strip().upper(),
        str(rec.get("book", "")).strip().lower(),
        str(date_str),
    ]
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return h[:12]


# ============================================================================ #
# --snapshot                                                                    #
# ============================================================================ #
def snapshot(
    payload: Dict[str, Any],
    snapshot_dir: str = DEFAULT_SNAPSHOT_DIR,
    date_str: Optional[str] = None,
) -> str:
    """Persist a recommendation payload as a dated snapshot. Returns the path."""
    os.makedirs(snapshot_dir, exist_ok=True)
    date_str = date_str or payload.get("date") or _date_cls.today().isoformat()
    recs = payload.get("recommendations", []) or []
    enriched: List[Dict[str, Any]] = []
    for r in recs:
        copy = dict(r)
        copy["rec_id"] = rec_id_for(r, date_str)
        copy["snapshot_date"] = date_str
        enriched.append(copy)
    out = {
        "captured_at":    _iso_now(),
        "date":           date_str,
        "bankroll":       payload.get("bankroll"),
        "top":            payload.get("top"),
        "min_edge":       payload.get("min_edge"),
        "engine_version": payload.get("engine_version", "R23_P8"),
        "n_recs":         len(enriched),
        "reason":         payload.get("reason", ""),
        "recommendations": enriched,
    }
    path = os.path.join(snapshot_dir, f"rec_snapshot_{date_str}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)
    return path


def run_snapshot(
    bankroll: float = 1000.0,
    top: int = 10,
    date_str: Optional[str] = None,
    snapshot_dir: str = DEFAULT_SNAPSHOT_DIR,
    min_edge: float = 0.05,
) -> Dict[str, Any]:
    """Call the live recommendation engine and persist the result."""
    from scripts.live_recommendation_engine import run_engine  # local import
    date_str = date_str or _date_cls.today().isoformat()
    payload = run_engine(
        bankroll=bankroll, top=top, date=date_str, min_edge=min_edge,
    )
    path = snapshot(payload, snapshot_dir=snapshot_dir, date_str=date_str)
    return {
        "path": path,
        "date": date_str,
        "n_recs": len(payload.get("recommendations", []) or []),
        "reason": payload.get("reason", ""),
    }


# ============================================================================ #
# Boxscore lookup                                                               #
# ============================================================================ #
def _sum_quarter_box(date_str: str, qb_dir: str) -> Dict[str, Dict[str, float]]:
    """Load all q1..q4 files dated for `date_str` and sum per player.

    Returns: {player_name_key: {stat_field: total}}.

    Quarter-box files have no date in the filename — we use the q4's `min`
    field as an "is final" gate; in practice the only games loaded here are
    those whose q4 file exists. Tests inject their own loader instead so this
    fallback path is only used in production.
    """
    import glob
    out: Dict[str, Dict[str, float]] = {}
    if not os.path.isdir(qb_dir):
        return out
    by_game: Dict[str, Dict[str, Dict[str, float]]] = {}
    for path in glob.glob(os.path.join(qb_dir, "*_q*.json")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        gid = str(data.get("game_id") or "")
        if not gid:
            continue
        slot = by_game.setdefault(gid, {})
        for p in data.get("players") or []:
            name_key = _player_key(p.get("player_name", ""))
            if not name_key:
                continue
            tot = slot.setdefault(name_key, {})
            for fld in ("pts", "reb", "ast", "fg3m", "stl", "blk", "to"):
                try:
                    tot[fld] = tot.get(fld, 0.0) + float(p.get(fld) or 0.0)
                except Exception:
                    pass
    for gid, players in by_game.items():
        for name_key, stats in players.items():
            cur = out.get(name_key)
            if cur is None or sum(stats.values()) > sum(cur.values()):
                out[name_key] = stats
    return out


def _default_box_loader(date_str: str, qb_dir: str) -> Dict[str, Dict[str, float]]:
    return _sum_quarter_box(date_str, qb_dir)


# ============================================================================ #
# --settle                                                                      #
# ============================================================================ #
def _grade_rec(side: str, line: float, actual: float) -> str:
    if actual is None:
        return "UNGRADED"
    if abs(actual - line) < 1e-9:
        return "PUSH"
    if str(side).upper() == "OVER":
        return "WIN" if actual > line else "LOSS"
    return "WIN" if actual < line else "LOSS"


def _profit_for(result: str, odds: int, stake: float = 1.0) -> float:
    if result == "PUSH":
        return 0.0
    if result == "WIN":
        return _american_payout(int(odds), stake)
    if result == "LOSS":
        return -float(stake)
    return 0.0


def settle(
    date_str: str,
    snapshot_dir: str = DEFAULT_SNAPSHOT_DIR,
    settled_path: str = DEFAULT_SETTLED_PATH,
    qb_dir: str = DEFAULT_QB_DIR,
    boxscore_loader: Optional[Callable[[str, str], Dict[str, Dict[str, float]]]] = None,
    stake_unit: float = 1.0,
) -> Dict[str, Any]:
    """Read the snapshot for date_str, grade each rec, append to settled parquet.

    Idempotent: rec_ids already present in the settled parquet are skipped.

    Returns a summary dict.
    """
    import pandas as pd  # local — keep CLI cold-start fast

    snap_path = os.path.join(snapshot_dir, f"rec_snapshot_{date_str}.json")
    if not os.path.exists(snap_path):
        return {
            "ok": False, "date": date_str,
            "reason": f"snapshot not found: {os.path.basename(snap_path)}",
            "n_settled": 0, "n_skipped": 0, "n_missing_player": 0,
        }
    with open(snap_path, "r", encoding="utf-8") as fh:
        snap = json.load(fh)
    recs = snap.get("recommendations") or []
    if not recs:
        return {
            "ok": True, "date": date_str,
            "reason": "snapshot has no recs",
            "n_settled": 0, "n_skipped": 0, "n_missing_player": 0,
        }

    loader = boxscore_loader or _default_box_loader
    box = loader(date_str, qb_dir) or {}

    # Load existing settled rec_ids for idempotency.
    seen_ids: set = set()
    existing_df: Optional["pd.DataFrame"] = None
    if os.path.exists(settled_path):
        try:
            existing_df = pd.read_parquet(settled_path)
            if "rec_id" in existing_df.columns:
                seen_ids = set(existing_df["rec_id"].astype(str).tolist())
        except Exception:
            existing_df = None

    new_rows: List[Dict[str, Any]] = []
    n_missing = 0
    n_skipped = 0
    for r in recs:
        rid = r.get("rec_id") or rec_id_for(r, date_str)
        if rid in seen_ids:
            n_skipped += 1
            continue
        stat = str(r.get("stat", "")).strip().lower()
        side = str(r.get("side", "")).strip().upper()
        try:
            line = float(r.get("line"))
        except (TypeError, ValueError):
            n_skipped += 1
            continue
        try:
            odds = int(float(r.get("odds", -110)))
        except (TypeError, ValueError):
            odds = -110
        edge = float(r.get("edge", 0.0) or 0.0)
        pkey = _player_key(r.get("player", ""))
        bx = box.get(pkey)
        if bx is None:
            n_missing += 1
            result = "UNGRADED"
            actual = None
        else:
            field = _STAT_TO_BOX_FIELD.get(stat, stat)
            actual = bx.get(field)
            if actual is None:
                n_missing += 1
                result = "UNGRADED"
            else:
                try:
                    actual = float(actual)
                except Exception:
                    actual = None
                    result = "UNGRADED"
                    n_missing += 1
                else:
                    result = _grade_rec(side, line, actual)
        profit = _profit_for(result, odds, stake=stake_unit)
        new_rows.append({
            "rec_id":      rid,
            "date":        date_str,
            "settled_at":  _iso_now(),
            "player":      r.get("player", ""),
            "stat":        stat,
            "side":        side,
            "book":        r.get("book", ""),
            "line":        line,
            "odds":        odds,
            "edge":        edge,
            "stake_unit":  float(stake_unit),
            "stake_dollars": float(r.get("stake_dollars", 0.0) or 0.0),
            "actual":      actual if actual is not None else float("nan"),
            "result":      result,
            "profit":      profit,
        })
        seen_ids.add(rid)

    if not new_rows:
        return {
            "ok": True, "date": date_str,
            "reason": "no new recs to settle (all already settled)",
            "n_settled": 0, "n_skipped": n_skipped, "n_missing_player": n_missing,
        }

    new_df = pd.DataFrame(new_rows)
    if existing_df is not None and not existing_df.empty:
        out_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        out_df = new_df
    os.makedirs(os.path.dirname(settled_path) or ".", exist_ok=True)
    out_df.to_parquet(settled_path, index=False)

    wins   = sum(1 for r in new_rows if r["result"] == "WIN")
    losses = sum(1 for r in new_rows if r["result"] == "LOSS")
    pushes = sum(1 for r in new_rows if r["result"] == "PUSH")
    ungrad = sum(1 for r in new_rows if r["result"] == "UNGRADED")
    return {
        "ok": True, "date": date_str,
        "n_settled": len(new_rows),
        "n_skipped": n_skipped,
        "n_missing_player": n_missing,
        "wins": wins, "losses": losses,
        "pushes": pushes, "ungraded": ungrad,
        "settled_path": settled_path,
    }


# ============================================================================ #
# --report                                                                      #
# ============================================================================ #
def report(
    settled_path: str = DEFAULT_SETTLED_PATH,
    days: Any = "all",
) -> Dict[str, Any]:
    """Aggregate the settled parquet over the chosen lookback window."""
    import pandas as pd
    if not os.path.exists(settled_path):
        return {"ok": False, "reason": f"no settled file at {settled_path}"}
    try:
        df = pd.read_parquet(settled_path)
    except Exception as exc:
        return {"ok": False, "reason": f"read failed: {exc}"}
    if df.empty:
        return {"ok": True, "n": 0, "reason": "empty settled file"}

    if isinstance(days, int) or (isinstance(days, str) and days != "all"):
        try:
            n_days = int(days)
        except (TypeError, ValueError):
            n_days = None
        if n_days is not None and n_days > 0:
            cutoff = (_date_cls.today() - timedelta(days=n_days)).isoformat()
            df = df[df["date"].astype(str) >= cutoff]

    if df.empty:
        return {"ok": True, "n": 0, "reason": "no rows in lookback window"}

    graded = df[df["result"].isin(["WIN", "LOSS", "PUSH"])]
    non_push = graded[graded["result"].isin(["WIN", "LOSS"])]
    wins  = int((graded["result"] == "WIN").sum())
    losses = int((graded["result"] == "LOSS").sum())
    pushes = int((graded["result"] == "PUSH").sum())
    total_graded = len(graded)
    win_rate = (wins / len(non_push)) if len(non_push) > 0 else 0.0
    total_stake = float(non_push["stake_unit"].sum()) if not non_push.empty else 0.0
    total_profit = float(graded["profit"].sum()) if not graded.empty else 0.0
    roi = (total_profit / total_stake) if total_stake > 0 else 0.0

    mean_edge_win  = float(graded[graded["result"] == "WIN"]["edge"].mean()) \
        if wins  > 0 else float("nan")
    mean_edge_loss = float(graded[graded["result"] == "LOSS"]["edge"].mean()) \
        if losses > 0 else float("nan")

    by_stat: Dict[str, Dict[str, float]] = {}
    for stat_name, grp in graded.groupby("stat"):
        sub_np = grp[grp["result"].isin(["WIN", "LOSS"])]
        s_wins = int((grp["result"] == "WIN").sum())
        s_losses = int((grp["result"] == "LOSS").sum())
        s_pushes = int((grp["result"] == "PUSH").sum())
        s_total_stake  = float(sub_np["stake_unit"].sum()) if not sub_np.empty else 0.0
        s_total_profit = float(grp["profit"].sum())
        by_stat[str(stat_name)] = {
            "n":        int(len(grp)),
            "wins":     s_wins,
            "losses":   s_losses,
            "pushes":   s_pushes,
            "win_rate": (s_wins / len(sub_np)) if len(sub_np) > 0 else 0.0,
            "roi":      (s_total_profit / s_total_stake) if s_total_stake > 0 else 0.0,
            "profit":   s_total_profit,
        }

    return {
        "ok":              True,
        "lookback":        days,
        "n":               int(len(df)),
        "n_graded":        int(total_graded),
        "n_ungraded":      int((df["result"] == "UNGRADED").sum()),
        "wins":            wins,
        "losses":          losses,
        "pushes":          pushes,
        "win_rate":        round(win_rate, 4),
        "roi":             round(roi, 4),
        "total_stake":     round(total_stake, 4),
        "total_profit":    round(total_profit, 4),
        "mean_edge_win":   round(mean_edge_win,  4) if mean_edge_win  == mean_edge_win  else None,
        "mean_edge_loss":  round(mean_edge_loss, 4) if mean_edge_loss == mean_edge_loss else None,
        "by_stat":         by_stat,
    }


# ============================================================================ #
# CLI                                                                           #
# ============================================================================ #
def _fmt_report_text(rpt: Dict[str, Any]) -> str:
    if not rpt.get("ok"):
        return f"(report unavailable: {rpt.get('reason','')})"
    lines = []
    lines.append("=" * 72)
    lines.append(f"LIVE REC TRACKER REPORT  ({rpt.get('lookback','all')})")
    lines.append("=" * 72)
    lines.append(
        f"Total: {rpt.get('n',0)}  Graded: {rpt.get('n_graded',0)}  "
        f"Ungraded: {rpt.get('n_ungraded',0)}"
    )
    lines.append(
        f"W/L/P: {rpt.get('wins',0)}/{rpt.get('losses',0)}/{rpt.get('pushes',0)}  "
        f"Win-rate: {rpt.get('win_rate',0)*100:.2f}%  "
        f"ROI: {rpt.get('roi',0)*100:+.2f}%"
    )
    lines.append(
        f"Stake (units): {rpt.get('total_stake',0):.2f}  "
        f"Profit: {rpt.get('total_profit',0):+.2f}"
    )
    if rpt.get("mean_edge_win") is not None or rpt.get("mean_edge_loss") is not None:
        lines.append(
            f"Mean edge — winners: {rpt.get('mean_edge_win')}  "
            f"losers: {rpt.get('mean_edge_loss')}"
        )
    by_stat = rpt.get("by_stat") or {}
    if by_stat:
        lines.append("-" * 72)
        lines.append(f"{'Stat':<6} {'N':>4} {'W':>3} {'L':>3} {'P':>3} "
                     f"{'Win%':>7} {'ROI%':>7} {'Profit':>9}")
        for stat, s in sorted(by_stat.items()):
            lines.append(
                f"{stat:<6} {s['n']:>4} {s['wins']:>3} {s['losses']:>3} "
                f"{s['pushes']:>3} {s['win_rate']*100:>6.2f}% "
                f"{s['roi']*100:>+6.2f}% {s['profit']:>+9.2f}"
            )
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--snapshot", action="store_true")
    mode.add_argument("--settle",   type=str, default=None,
                      metavar="DATE", help="settle a snapshot dated YYYY-MM-DD")
    mode.add_argument("--report",   action="store_true")

    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--top",      type=int,   default=10)
    ap.add_argument("--min-edge", type=float, default=0.05)
    ap.add_argument("--date",     type=str,   default=None,
                    help="override date for --snapshot (defaults to today)")
    ap.add_argument("--days",     type=str,   default="all",
                    help="--report lookback window: 'all' or an integer day count")
    ap.add_argument("--snapshot-dir", type=str, default=DEFAULT_SNAPSHOT_DIR,
                    help="override snapshot dir (used by --snapshot dry-run + tests)")
    ap.add_argument("--settled-path", type=str, default=DEFAULT_SETTLED_PATH,
                    help="override settled parquet path (used by tests + probe)")
    ap.add_argument("--qb-dir",   type=str, default=DEFAULT_QB_DIR,
                    help="override quarter-box dir for --settle")
    ap.add_argument("--dry-run", action="store_true",
                    help="--snapshot: write to a temp dir instead of the real one")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON instead of human text")
    return ap.parse_args()


def main() -> int:
    args = _parse_args()

    if args.snapshot:
        snap_dir = args.snapshot_dir
        if args.dry_run:
            import tempfile
            snap_dir = tempfile.mkdtemp(prefix="rec_tracker_dry_")
        out = run_snapshot(
            bankroll=args.bankroll, top=args.top, date_str=args.date,
            snapshot_dir=snap_dir, min_edge=args.min_edge,
        )
        if args.json:
            print(json.dumps(out, indent=2, default=str))
        else:
            print(f"snapshot written: {out['path']}")
            print(f"  date={out['date']}  n_recs={out['n_recs']}")
            print(f"  reason={out['reason']}")
        return 0

    if args.settle:
        out = settle(
            date_str=args.settle,
            snapshot_dir=args.snapshot_dir,
            settled_path=args.settled_path,
            qb_dir=args.qb_dir,
        )
        if args.json:
            print(json.dumps(out, indent=2, default=str))
        else:
            print(f"settle: date={out.get('date')} ok={out.get('ok')} "
                  f"n_settled={out.get('n_settled',0)} "
                  f"skipped={out.get('n_skipped',0)} "
                  f"missing={out.get('n_missing_player',0)} "
                  f"reason={out.get('reason','')}")
        return 0 if out.get("ok") else 1

    if args.report:
        rpt = report(settled_path=args.settled_path, days=args.days)
        if args.json:
            print(json.dumps(rpt, indent=2, default=str))
        else:
            print(_fmt_report_text(rpt))
        return 0 if rpt.get("ok") else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
