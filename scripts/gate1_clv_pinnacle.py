"""gate1_clv_pinnacle.py — R29_V8: Gate-1 CLV validation against real Pinnacle.

What it does
------------
For every historical Pinnacle snapshot (``data/lines/<date>_pin.csv``) with at
least two captured_at timestamps (opening + closing), and a matching
``predictions_cache_<date>.parquet``, this script:

1. Pairs each (game_id, player_name, stat, line) with its opening and
   closing rows. (Opening = min captured_at, closing = max captured_at.)
2. Computes the model's recommended side: bet OVER if q50 > line else UNDER.
3. Computes CLV % for that side: (closing_prob − opening_prob) / opening_prob.
   Positive CLV means the opening price was *better* than the close — the
   market moved toward the model's pick.
4. Filters OUT players (R22_O8 — never bet a guy who is OUT).
5. Aggregates by stat: n_bets, mean_clv_pct, edge_pct, fair_value_ROI.

Output: ``data/cache/gate1_clv_pinnacle_results.json``.

CLI
---
    python scripts/gate1_clv_pinnacle.py [--days 7] [--min-stat-coverage 10]

Hard rules
----------
* Read-only on Pin snapshots and predictions caches.
* Local only — no network, no DB writes.
* Honest CLV = market-line-vs-market-line (does NOT need bet outcomes).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.validation.clv_tracker import (  # noqa: E402
    american_to_prob,
    compute_clv,
)
from src.prediction.betting_portfolio import (  # noqa: E402
    KELLY_PCT_MAX,
    clamp_kelly_pct,
)

_DATA_DIR = _ROOT / "data"
_LINES_DIR = _DATA_DIR / "lines"
_CACHE_DIR = _DATA_DIR / "cache"
_RESULTS_PATH = _CACHE_DIR / "gate1_clv_pinnacle_results.json"

_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_pin\.csv$")


# ── helpers ──────────────────────────────────────────────────────────────────


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _list_pin_files(days: int) -> List[Tuple[str, Path]]:
    """Return list of (date_iso, path) for the most recent N days of Pin files."""
    if not _LINES_DIR.exists():
        return []
    today = date.today()
    cutoff = today - timedelta(days=days)
    out: List[Tuple[str, Path]] = []
    for p in sorted(_LINES_DIR.glob("*_pin.csv")):
        m = _DATE_RE.match(p.name)
        if not m:
            continue
        d_iso = m.group(1)
        try:
            d_obj = datetime.strptime(d_iso, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d_obj < cutoff or d_obj > today:
            continue
        out.append((d_iso, p))
    return out


def _load_predictions(date_iso: str) -> Optional[Dict[Tuple[str, str], float]]:
    """Load model q50 predictions for a given date.

    Returns: lookup dict {(player_name_lower, stat_lower) -> q50_float} or None.
    """
    try:
        import pandas as pd
    except ImportError:
        return None
    p = _CACHE_DIR / f"predictions_cache_{date_iso}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:
        return None
    out: Dict[Tuple[str, str], float] = {}
    for _, row in df.iterrows():
        name = str(row.get("player_name", "")).strip().lower()
        stat = str(row.get("stat", "")).strip().lower()
        q50 = row.get("q50")
        if not name or not stat or q50 is None:
            continue
        try:
            out[(name, stat)] = float(q50)
        except (TypeError, ValueError):
            continue
    return out


def _load_out_player_names(date_iso: str) -> set:
    """Load names of players marked OUT for the date (R22_O8 filter)."""
    try:
        import pandas as pd
    except ImportError:
        return set()
    p = _CACHE_DIR / f"nba_injuries_{date_iso}.parquet"
    if not p.exists():
        return set()
    try:
        df = pd.read_parquet(p)
    except Exception:
        return set()
    out_names = set()
    for _, row in df.iterrows():
        status = str(row.get("status", "")).strip().upper()
        if status != "OUT":
            continue
        nm = str(row.get("player_name", "")).strip().lower()
        if nm:
            out_names.add(nm)
    return out_names


def _pair_open_close_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """For each (game_id, player_name, stat, line) group, return (opening, closing).

    Opening = row with min captured_at; closing = row with max captured_at.
    Returns merged dicts with open_/close_ prefixed price fields.
    """
    groups: Dict[Tuple[str, str, str, float], List[Dict[str, Any]]] = {}
    for r in rows:
        try:
            line = float(r["line"])
        except (KeyError, TypeError, ValueError):
            continue
        key = (
            str(r.get("game_id", "")).strip(),
            str(r.get("player_name", "")).strip(),
            str(r.get("stat", "")).strip().lower(),
            line,
        )
        groups.setdefault(key, []).append(r)

    out: List[Dict[str, Any]] = []
    for key, lst in groups.items():
        if len(lst) < 2:
            continue
        lst_sorted = sorted(lst, key=lambda r: str(r.get("captured_at", "")))
        opening = lst_sorted[0]
        closing = lst_sorted[-1]
        if str(opening.get("captured_at")) == str(closing.get("captured_at")):
            continue
        out.append({
            "game_id": key[0],
            "player_name": key[1],
            "stat": key[2],
            "line": key[3],
            "open_captured_at": opening.get("captured_at"),
            "close_captured_at": closing.get("captured_at"),
            "open_over_price": opening.get("over_price"),
            "open_under_price": opening.get("under_price"),
            "close_over_price": closing.get("over_price"),
            "close_under_price": closing.get("under_price"),
        })
    return out


def _compute_clv_for_pair(
    pair: Dict[str, Any],
    side: str,
) -> Optional[float]:
    """Compute CLV % for a single (opening, closing) pair on a given side.

    Returns None on bad data.
    """
    if side not in ("over", "under"):
        return None
    open_price_key = "open_over_price" if side == "over" else "open_under_price"
    close_price_key = "close_over_price" if side == "over" else "close_under_price"
    try:
        open_price = float(pair[open_price_key])
        close_price = float(pair[close_price_key])
    except (KeyError, TypeError, ValueError):
        return None
    try:
        r = compute_clv(
            taken_odds=open_price,
            closing_odds=close_price,
            stake=100.0,
            fmt="american",
        )
    except (ValueError, ZeroDivisionError):
        return None
    return r.clv_pct


def _kelly_fraction(model_prob: float, american_odds: float) -> float:
    """Quarter-Kelly fraction, clamped to [0, KELLY_PCT_MAX]. Pure-function."""
    if model_prob <= 0 or model_prob >= 1:
        return 0.0
    implied = american_to_prob(american_odds)
    if implied >= 1.0:
        return 0.0
    # Decimal odds
    if american_odds >= 0:
        b = american_odds / 100.0
    else:
        b = 100.0 / abs(american_odds)
    edge = model_prob * (b + 1.0) - 1.0
    if edge <= 0 or b <= 0:
        return 0.0
    full_kelly = edge / b
    quarter = full_kelly * 0.25
    clamped = clamp_kelly_pct(quarter)
    return clamped if clamped is not None else 0.0


# ── core ─────────────────────────────────────────────────────────────────────


def evaluate_date(
    date_iso: str,
    pin_path: Path,
    skip_out_players: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Evaluate a single date's Pin file vs predictions cache.

    Returns (per_bet_records, diagnostics).
    """
    import csv as _csv

    diag: Dict[str, Any] = {
        "date": date_iso,
        "n_raw_rows": 0,
        "n_paired": 0,
        "n_with_prediction": 0,
        "n_not_out": 0,
        "n_eligible": 0,
        "reason_skipped": {},
    }

    if not pin_path.exists():
        diag["reason_skipped"]["file_missing"] = 1
        return [], diag

    # Load raw rows from CSV
    rows: List[Dict[str, Any]] = []
    with open(pin_path, encoding="utf-8") as fh:
        reader = _csv.DictReader(fh)
        for r in reader:
            rows.append(r)
    diag["n_raw_rows"] = len(rows)
    if not rows:
        return [], diag

    pairs = _pair_open_close_rows(rows)
    diag["n_paired"] = len(pairs)
    if not pairs:
        return [], diag

    preds = _load_predictions(date_iso)
    if preds is None:
        diag["reason_skipped"]["no_predictions"] = 1
        return [], diag

    out_names = _load_out_player_names(date_iso) if skip_out_players else set()

    bets: List[Dict[str, Any]] = []
    for pair in pairs:
        nm_l = pair["player_name"].lower()
        stat = pair["stat"]
        q50 = preds.get((nm_l, stat))
        if q50 is None:
            diag["reason_skipped"].setdefault("no_pred_match", 0)
            diag["reason_skipped"]["no_pred_match"] += 1
            continue
        diag["n_with_prediction"] += 1

        if skip_out_players and nm_l in out_names:
            diag["reason_skipped"].setdefault("player_out", 0)
            diag["reason_skipped"]["player_out"] += 1
            continue
        diag["n_not_out"] += 1

        line_val = pair["line"]
        side = "over" if q50 > line_val else "under"
        clv_pct = _compute_clv_for_pair(pair, side)
        if clv_pct is None:
            diag["reason_skipped"].setdefault("bad_odds", 0)
            diag["reason_skipped"]["bad_odds"] += 1
            continue

        # implied edge: model q50 distance from line, %
        edge_units = q50 - line_val
        if side == "under":
            edge_units = -edge_units

        # Kelly sanity (R19_L2): use a dummy model_prob from q50 distance.
        # Without sigma we can't get true prob, so we use a conservative
        # 0.55 if edge > 0 else 0.50 — purely to verify the invariant.
        model_prob = 0.55 if edge_units > 0 else 0.50
        open_price = pair["open_over_price" if side == "over" else "open_under_price"]
        try:
            kelly = _kelly_fraction(model_prob, float(open_price))
        except (TypeError, ValueError):
            kelly = 0.0

        bets.append({
            "date": date_iso,
            "game_id": pair["game_id"],
            "player_name": pair["player_name"],
            "stat": stat,
            "line": line_val,
            "side": side,
            "q50": q50,
            "edge_units": round(edge_units, 4),
            "open_price": pair["open_over_price" if side == "over" else "open_under_price"],
            "close_price": pair["close_over_price" if side == "over" else "close_under_price"],
            "open_captured_at": pair["open_captured_at"],
            "close_captured_at": pair["close_captured_at"],
            "clv_pct": clv_pct,
            "kelly_pct": kelly,
        })
        diag["n_eligible"] += 1

    return bets, diag


def aggregate_bets(bets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate per-stat and overall metrics from a flat bet list."""
    overall: Dict[str, Any] = {
        "n_bets": len(bets),
        "n_distinct_dates": len({b["date"] for b in bets}),
        "mean_clv_pct": 0.0,
        "n_positive_clv": 0,
        "positive_clv_rate": 0.0,
    }

    by_stat: Dict[str, Dict[str, Any]] = {}
    if not bets:
        return {"overall": overall, "per_stat": by_stat}

    total_clv = 0.0
    pos = 0
    for b in bets:
        total_clv += b["clv_pct"]
        if b["clv_pct"] > 0:
            pos += 1
        s = b["stat"]
        agg = by_stat.setdefault(s, {
            "n_bets": 0,
            "sum_clv_pct": 0.0,
            "n_positive_clv": 0,
            "mean_edge_units": 0.0,
            "_sum_edge": 0.0,
        })
        agg["n_bets"] += 1
        agg["sum_clv_pct"] += b["clv_pct"]
        agg["_sum_edge"] += b["edge_units"]
        if b["clv_pct"] > 0:
            agg["n_positive_clv"] += 1

    overall["mean_clv_pct"] = round(total_clv / len(bets), 4)
    overall["n_positive_clv"] = pos
    overall["positive_clv_rate"] = round(pos / len(bets), 4)

    for s, agg in by_stat.items():
        n = agg["n_bets"]
        agg["mean_clv_pct"] = round(agg["sum_clv_pct"] / n, 4)
        agg["mean_edge_units"] = round(agg["_sum_edge"] / n, 4)
        agg["positive_clv_rate"] = round(agg["n_positive_clv"] / n, 4)
        del agg["sum_clv_pct"], agg["_sum_edge"]

    return {"overall": overall, "per_stat": by_stat}


def run(
    days: int = 7,
    min_stat_coverage: int = 10,
    write_results: bool = True,
) -> Dict[str, Any]:
    """Run the full gate-1 evaluation. Returns serialisable result dict."""
    pin_files = _list_pin_files(days=days)
    all_bets: List[Dict[str, Any]] = []
    per_date_diag: List[Dict[str, Any]] = []
    for d_iso, p in pin_files:
        bets, diag = evaluate_date(d_iso, p)
        all_bets.extend(bets)
        per_date_diag.append(diag)

    agg = aggregate_bets(all_bets)
    stats_with_coverage = [
        s for s, v in agg["per_stat"].items()
        if v["n_bets"] >= min_stat_coverage
    ]

    result = {
        "probe": "R29_V8",
        "ts": _iso_now(),
        "days_window": days,
        "min_stat_coverage": min_stat_coverage,
        "n_pin_files_scanned": len(pin_files),
        "n_eligible_bets": agg["overall"]["n_bets"],
        "n_distinct_dates": agg["overall"]["n_distinct_dates"],
        "n_stats_with_coverage": len(stats_with_coverage),
        "stats_with_coverage": stats_with_coverage,
        "overall": agg["overall"],
        "per_stat": agg["per_stat"],
        "per_date_diagnostic": per_date_diag,
    }

    if write_results:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_RESULTS_PATH, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=str)

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Gate-1 CLV validation against real Pinnacle openings vs closes."
    )
    p.add_argument("--days", type=int, default=7,
                   help="Look-back window in days (default 7)")
    p.add_argument("--min-stat-coverage", type=int, default=10,
                   help="Min bets per stat to count as 'covered' (default 10)")
    p.add_argument("--no-write", action="store_true",
                   help="Skip writing data/cache/gate1_clv_pinnacle_results.json")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    result = run(
        days=args.days,
        min_stat_coverage=args.min_stat_coverage,
        write_results=not args.no_write,
    )
    print("=== R29_V8 Gate-1 CLV vs Pinnacle ===")
    print(f"days_window:           {result['days_window']}")
    print(f"pin files scanned:     {result['n_pin_files_scanned']}")
    print(f"n_eligible_bets:       {result['n_eligible_bets']}")
    print(f"n_distinct_dates:      {result['n_distinct_dates']}")
    print(f"stats_with_coverage:   {result['n_stats_with_coverage']}  ({result['stats_with_coverage']})")
    print(f"overall mean_clv_pct:  {result['overall']['mean_clv_pct']:+.4f}%")
    print(f"overall positive rate: {result['overall']['positive_clv_rate']:.2%}")
    print()
    if result["per_stat"]:
        print("per-stat:")
        print(f"  {'stat':<6} {'n':>6} {'mean_clv_pct':>14} {'pos_rate':>10} {'edge_units':>12}")
        for s in sorted(result["per_stat"]):
            v = result["per_stat"][s]
            print(f"  {s:<6} {v['n_bets']:>6d} {v['mean_clv_pct']:>13.4f}% {v['positive_clv_rate']:>10.2%} {v['mean_edge_units']:>12.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
