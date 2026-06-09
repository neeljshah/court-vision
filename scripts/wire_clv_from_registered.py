"""wire_clv_from_registered.py — compute CLV for pre-registered bets vs the
captured Pinnacle closing snapshot, then append to
``data/cache/clv_running_total.json``.

Designed to be run TOMORROW (post-tip), after capture_closing_lines.py has
landed the close-time snapshot. Reads:

  - data/cache/intel_<date>/tonight_bets_registered.json
  - data/lines/snapshots/<game_id>_close_*.csv   (latest by mtime)

For each registered bet, finds the matching row in the closing snapshot
(player_name + stat + line), pulls the closing odds for that side, and
computes CLV % (vig-included implied prob delta). Output is appended to
the running total and a per-bet detail file is dropped under data/clv/.

CLI
---
    python scripts/wire_clv_from_registered.py \
        --registered data/cache/intel_2026-05-26/tonight_bets_registered.json

Defaults: registered path auto-resolved to today's intel folder; closing
snapshot is the most recent matching ``<game_id>_close_*.csv`` in
``data/lines/snapshots/``.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_LINES_SNAP_DIR = _ROOT / "data" / "lines" / "snapshots"
_RUNNING_TOTAL = _ROOT / "data" / "cache" / "clv_running_total.json"
_CLV_OUT_DIR = _ROOT / "data" / "clv"


def _american_to_implied_prob(odds: float) -> float:
    if odds >= 100:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def _name_key(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _find_latest_close(game_id: str) -> Optional[Path]:
    pattern = str(_LINES_SNAP_DIR / f"{game_id}_close_*.csv")
    cands = [Path(p) for p in glob.glob(pattern)
             if "_mainline_" not in os.path.basename(p)]
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def _load_close_snapshot(path: Path) -> Dict[Tuple[str, str, float], Dict[str, Any]]:
    """Return {(name_key, stat, line) -> {over_price, under_price, captured_at}}.
    If multiple rows share the key, prefer the LATEST captured_at (= true close)."""
    out: Dict[Tuple[str, str, float], Dict[str, Any]] = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                key = (_name_key(r["player_name"]),
                       r["stat"].strip().lower(),
                       float(r["line"]))
            except (KeyError, ValueError):
                continue
            existing = out.get(key)
            if existing is None or str(r.get("captured_at", "")) > str(existing.get("captured_at", "")):
                out[key] = {
                    "over_price": int(r["over_price"]) if r.get("over_price") not in ("", None) else None,
                    "under_price": int(r["under_price"]) if r.get("under_price") not in ("", None) else None,
                    "captured_at": r.get("captured_at", ""),
                }
    return out


def compute_clv_for_bets(
    registered: Dict[str, Any],
    close_map: Dict[Tuple[str, str, float], Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Returns (per_bet_clv_rows, summary)."""
    rows: List[Dict[str, Any]] = []
    matched = 0
    pos = 0
    sum_clv = 0.0
    for b in registered["bets"]:
        side = b["side"].upper()
        key = (_name_key(b["player"]), b["stat"].lower(), float(b["line"]))
        close = close_map.get(key)
        if close is None:
            rows.append({**b, "closing_odds": None, "clv_pct": None,
                         "closing_captured_at": None, "matched": False})
            continue
        close_price = close["over_price"] if side == "OVER" else close["under_price"]
        if close_price is None:
            rows.append({**b, "closing_odds": None, "clv_pct": None,
                         "closing_captured_at": close.get("captured_at"),
                         "matched": False})
            continue
        placed = _american_to_implied_prob(b["odds"])
        closed = _american_to_implied_prob(close_price)
        # CLV % = (closing_implied - placed_implied) / placed_implied * 100
        # Positive = bettor's price was better than the close (we beat it).
        clv_pct = round((closed - placed) / placed * 100.0, 3)
        matched += 1
        sum_clv += clv_pct
        if clv_pct > 0:
            pos += 1
        rows.append({**b, "closing_odds": close_price, "clv_pct": clv_pct,
                     "closing_captured_at": close.get("captured_at"),
                     "matched": True})
    summary = {
        "n_bets": len(rows),
        "n_matched": matched,
        "n_unmatched": len(rows) - matched,
        "n_positive_clv": pos,
        "pct_positive_clv": round(100.0 * pos / matched, 2) if matched else 0.0,
        "mean_clv_pct": round(sum_clv / matched, 3) if matched else 0.0,
    }
    return rows, summary


def update_running_total(
    new_rows: List[Dict[str, Any]],
    summary: Dict[str, Any],
    game_id: str,
) -> Dict[str, Any]:
    """Merge today's results into data/cache/clv_running_total.json (cumulative)."""
    if _RUNNING_TOTAL.exists():
        try:
            with open(_RUNNING_TOTAL, encoding="utf-8") as fh:
                running = json.load(fh)
        except Exception:
            running = {}
    else:
        running = {}

    history = running.get("history") or []
    history.append({
        "game_id": game_id,
        "settled_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
    })

    # Recompute running aggregate over BOTH the prior aggregate fields and today's matched bets.
    prior_n = int(running.get("n_bets_tracked", 0) or 0)
    prior_pos_pct = float(running.get("pct_positive_clv", 0.0) or 0.0)
    prior_mean = float(running.get("mean_clv_pct", 0.0) or 0.0)
    prior_pos = round(prior_n * prior_pos_pct / 100.0)

    today_n = summary["n_matched"]
    today_pos = summary["n_positive_clv"]
    today_mean = summary["mean_clv_pct"]

    new_n = prior_n + today_n
    new_pos = prior_pos + today_pos
    if new_n > 0:
        new_mean = round(
            (prior_mean * prior_n + today_mean * today_n) / new_n, 4
        )
        new_pos_pct = round(100.0 * new_pos / new_n, 4)
    else:
        new_mean = 0.0
        new_pos_pct = 0.0

    by_book = running.get("by_book") or {}
    for r in new_rows:
        if not r.get("matched"):
            continue
        bk = r["book"]
        bb = by_book.setdefault(bk, {"n": 0, "pos": 0, "mean_clv_pct": 0.0, "pct_positive": 0.0})
        old_n = bb["n"]; old_pos = bb["pos"]; old_mean = bb["mean_clv_pct"]
        bb["n"] = old_n + 1
        if r["clv_pct"] > 0:
            bb["pos"] = old_pos + 1
        bb["mean_clv_pct"] = round((old_mean * old_n + r["clv_pct"]) / bb["n"], 4)
        bb["pct_positive"] = round(100.0 * bb["pos"] / bb["n"], 4)

    out = {
        "n_bets_tracked": new_n,
        "mean_clv_pct": new_mean,
        "pct_positive_clv": new_pos_pct,
        "by_book": by_book,
        "history": history,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _RUNNING_TOTAL.parent.mkdir(parents=True, exist_ok=True)
    with open(_RUNNING_TOTAL, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--registered", default=None,
                    help="path to tonight_bets_registered.json "
                         "(default: today's intel dir)")
    ap.add_argument("--close-csv", default=None,
                    help="explicit closing-snapshot CSV "
                         "(default: latest <game_id>_close_*.csv in data/lines/snapshots/)")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute + print; do NOT write to clv_running_total.json")
    args = ap.parse_args(argv)

    if args.registered is None:
        today = datetime.now().strftime("%Y-%m-%d")
        args.registered = str(_ROOT / "data" / "cache" / f"intel_{today}"
                              / "tonight_bets_registered.json")

    if not os.path.exists(args.registered):
        print(f"[fail] registered bets file not found: {args.registered}")
        return 1
    with open(args.registered, encoding="utf-8") as fh:
        registered = json.load(fh)
    game_id = registered["game_id"]
    print(f"[wire_clv] registered: {args.registered}")
    print(f"[wire_clv] game_id={game_id}  n_bets={len(registered['bets'])}")

    close_path = Path(args.close_csv) if args.close_csv else _find_latest_close(game_id)
    if close_path is None or not close_path.exists():
        print(f"[fail] no closing snapshot found for game_id={game_id} "
              f"in {_LINES_SNAP_DIR}")
        print(f"       run capture_closing_lines.py first, or pass --close-csv")
        return 2
    print(f"[wire_clv] closing snapshot: {close_path}")

    close_map = _load_close_snapshot(close_path)
    print(f"[wire_clv] closing rows loaded: {len(close_map)}")

    rows, summary = compute_clv_for_bets(registered, close_map)
    print(f"[wire_clv] matched: {summary['n_matched']}/{summary['n_bets']}  "
          f"positive: {summary['n_positive_clv']} ({summary['pct_positive_clv']}%)  "
          f"mean CLV: {summary['mean_clv_pct']:+.3f}%")

    # Write per-bet detail
    _CLV_OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    detail_path = _CLV_OUT_DIR / f"{today}_{game_id}_clv.json"
    with open(detail_path, "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "bets": rows}, fh, indent=2, default=str)
    print(f"[wire_clv] per-bet detail -> {detail_path}")

    if args.dry_run:
        print("[wire_clv] --dry-run: clv_running_total.json NOT updated")
        return 0

    updated = update_running_total(rows, summary, game_id)
    print(f"[wire_clv] running total -> {_RUNNING_TOTAL}")
    print(f"           n_bets_tracked={updated['n_bets_tracked']}  "
          f"mean_clv_pct={updated['mean_clv_pct']:+.4f}%  "
          f"pct_positive={updated['pct_positive_clv']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
