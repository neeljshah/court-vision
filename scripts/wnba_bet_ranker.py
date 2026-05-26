"""wnba_bet_ranker.py - WNBA prop bet ranker (R17_J6).

Mirrors the NBA live_bet_ranker but uses the lean wnba_proxy_predictor
(L5 + league shrinkage) as its model layer. Reads the same Bovada line
CSV (data/lines/<date>_bov.csv), filters to WNBA players (anyone whose
name resolves to a WNBA PERSON_ID), predicts q10/q50/q90 per stat, prices
each (player,stat,book,side) tuple with a normal-CDF hit-probability, and
ranks by EV with fractional-Kelly stake sizing.

Outputs (atomic temp+rename):
    data/cache/live_bets/wnba_<date>.json
    vault/Predictions/wnba_<date>_live.md

Run:
    python scripts/wnba_bet_ranker.py --date 2026-05-26 --bankroll 1000
"""
from __future__ import annotations

import argparse
import csv as _csv
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from math import erf, sqrt
from typing import Any, Dict, List, Optional

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts import wnba_proxy_predictor as wpp  # noqa: E402

log = logging.getLogger("wnba_bet_ranker")

# Config (mirrors live_bet_ranker thresholds)
KELLY_FRACTION = 0.25
PER_BET_CAP = 0.05
SLATE_CAP = 0.25
MIN_EDGE_PCT = 0.5
MAX_ODDS_ABS = 400
MIN_PRICE_PROB = 0.20
DEFAULT_BANKROLL = 1000.0


# ----- odds math (lifted from live_bet_ranker) -----
def american_to_decimal(odds):
    if odds is None or pd.isna(odds):
        return None
    o = int(float(odds))
    return 1 + (o / 100.0) if o > 0 else 1 + (100.0 / -o)


def american_payout(odds, stake=1.0):
    o = int(float(odds))
    return stake * (o / 100.0) if o > 0 else stake * (100.0 / -o)


def implied_prob(odds):
    o = int(float(odds))
    return 100.0 / (o + 100) if o > 0 else (-o) / ((-o) + 100)


def kelly_fraction(prob, odds):
    if prob is None or odds is None or pd.isna(odds):
        return 0.0
    b = american_payout(odds, 1.0)
    p = prob
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, f)


def model_hit_prob(q10, q50, q90, line, side):
    """Normal-CDF hit probability from quantile band. Mirrors live_bet_ranker."""
    if q10 is None or q90 is None or q50 is None:
        return None
    sigma = max((q90 - q10) / (2 * 1.2816), 1e-6)
    z = (line - q50) / sigma
    cdf_at_line = 0.5 * (1 + erf(z / sqrt(2)))
    p_over = 1 - cdf_at_line
    return p_over if side == "OVER" else 1 - p_over


# ----- atomic write -----
def atomic_write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json",
                                dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def atomic_write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".md",
                                dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


# ----- line CSV reader (canonical 10/11-col Bovada schema) -----
def read_lines_csv(path: str) -> pd.DataFrame:
    canon = ["captured_at", "book", "game_id", "player_id",
             "player_name", "stat", "line", "over_price",
             "under_price", "start_time"]
    rows = []
    if not os.path.exists(path):
        return pd.DataFrame(columns=canon)
    with open(path, encoding="utf-8") as f:
        reader = _csv.reader(f)
        try:
            next(reader)
        except StopIteration:
            return pd.DataFrame(columns=canon)
        for row in reader:
            if len(row) == 10:
                d = dict(zip(canon, row))
            elif len(row) == 11:
                d = {
                    "captured_at": row[0], "book": row[1],
                    "game_id": row[2], "player_id": row[3],
                    "player_name": row[4],
                    "stat": row[6], "line": row[7],
                    "over_price": row[8], "under_price": row[9],
                    "start_time": row[10],
                }
            else:
                continue
            rows.append(d)
    df = pd.DataFrame(rows, columns=canon)
    if df.empty:
        return df
    df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce", utc=True)
    df["line"] = pd.to_numeric(df["line"], errors="coerce")
    df["over_price"] = pd.to_numeric(df["over_price"], errors="coerce")
    df["under_price"] = pd.to_numeric(df["under_price"], errors="coerce")
    return df


def latest_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """Keep latest captured_at per (player_name, stat, line)."""
    if df.empty:
        return df
    df = df.dropna(subset=["captured_at", "player_name", "stat", "line"])
    return df.sort_values("captured_at").drop_duplicates(
        subset=["player_name", "stat", "line"], keep="last"
    )


# ----- bet ranking -----
def rank_bets(
    lines_df: pd.DataFrame,
    season: str = "2025",
    lookback: int = wpp.DEFAULT_LOOKBACK,
    shrink: float = wpp.DEFAULT_SHRINK,
    min_edge_pct: float = MIN_EDGE_PCT,
    max_odds_abs: int = MAX_ODDS_ABS,
    min_price_prob: float = MIN_PRICE_PROB,
    bankroll: float = DEFAULT_BANKROLL,
) -> Dict[str, Any]:
    """Run the full prediction + ranking pipeline.

    Returns a dict payload with shape:
        {
          'meta': {...},
          'n_lines': int, 'n_evaluated': int, 'n_predictions': int,
          'bets': [...]   # sorted by EV descending
        }
    """
    # Resolve unique player_name -> wnba player_id, drop NBA-only names.
    name_to_pid: Dict[str, int] = {}
    unresolved: List[str] = []
    for name in sorted(set(lines_df["player_name"].dropna())):
        pid = wpp.resolve_wnba_player(name, season=season)
        if pid is not None:
            name_to_pid[name] = pid
        else:
            unresolved.append(name)

    # Predict in batch
    preds: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for name, pid in name_to_pid.items():
        try:
            p = wpp.predict_player(pid, season=season,
                                    lookback=lookback, shrink=shrink)
            if p is not None:
                preds[name] = p
        except Exception as e:  # noqa: BLE001
            log.warning("predict failed for %s/%s: %s", name, pid, e)

    bets: List[Dict[str, Any]] = []
    n_evaluated = 0
    for _, r in lines_df.iterrows():
        pname = r["player_name"]
        stat = (r["stat"] or "").lower()
        mdl_all = preds.get(pname)
        if mdl_all is None:
            continue
        mdl = mdl_all.get(stat)
        if mdl is None:
            continue
        try:
            line = float(r["line"])
        except (TypeError, ValueError):
            continue
        if pd.isna(line):
            continue
        for side, price_col in (("OVER", "over_price"),
                                 ("UNDER", "under_price")):
            price = r.get(price_col)
            if price is None or pd.isna(price):
                continue
            try:
                odds = int(float(price))
            except (TypeError, ValueError):
                continue
            if abs(odds) > max_odds_abs:
                continue
            impl = implied_prob(odds)
            if impl < min_price_prob:
                continue
            prob = model_hit_prob(mdl["q10"], mdl["q50"], mdl["q90"], line, side)
            if prob is None:
                continue
            n_evaluated += 1
            net = american_payout(odds, 1.0)
            ev = prob * net - (1 - prob) * 1.0
            kf_full = kelly_fraction(prob, odds)
            kf_used = min(kf_full * KELLY_FRACTION, PER_BET_CAP)
            edge_pp = (prob - impl) * 100.0  # percentage points
            if edge_pp < min_edge_pct:
                continue
            bets.append({
                "player": pname,
                "stat": stat,
                "side": side,
                "line": line,
                "odds": odds,
                "book": r.get("book") or "",
                "model_q50": float(mdl["q50"]),
                "model_q10": float(mdl["q10"]),
                "model_q90": float(mdl["q90"]),
                "model_n_games": int(mdl.get("n_games", 0)),
                "prob_model": round(float(prob), 4),
                "prob_implied": round(float(impl), 4),
                "edge_pp": round(edge_pp, 3),
                "ev_per_unit": round(float(ev), 4),
                "kelly_full": round(float(kf_full), 4),
                "kelly_used": round(float(kf_used), 4),
                "stake_usd": round(float(kf_used) * bankroll, 2),
            })

    bets.sort(key=lambda b: b["ev_per_unit"], reverse=True)
    # Apply slate cap (total stake percentage)
    total_stake = 0.0
    cap = SLATE_CAP * bankroll
    capped = []
    for b in bets:
        if total_stake + b["stake_usd"] > cap:
            b["stake_usd"] = max(0.0, round(cap - total_stake, 2))
            b["slate_capped"] = True
        else:
            b["slate_capped"] = False
        total_stake += b["stake_usd"]
        capped.append(b)
    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "season": season,
            "lookback": lookback,
            "shrink": shrink,
            "bankroll": bankroll,
            "min_edge_pct": min_edge_pct,
            "n_lines_input": int(len(lines_df)),
            "n_unique_players": int(lines_df["player_name"].nunique()),
            "n_wnba_resolved": len(name_to_pid),
            "n_unresolved": len(unresolved),
            "n_predictions": len(preds),
        },
        "n_evaluated": n_evaluated,
        "n_bets": len(capped),
        "bets": capped,
    }


# ----- markdown report -----
def render_markdown(payload: Dict[str, Any], date_str: str, top_n: int = 25) -> str:
    meta = payload["meta"]
    bets = payload["bets"][:top_n]
    lines = [
        f"# WNBA Live Bets — {date_str}",
        "",
        f"_generated {meta['generated_at']}_",
        "",
        f"- Lines input: **{meta['n_lines_input']}**  "
        f"unique players: {meta['n_unique_players']}  "
        f"WNBA resolved: {meta['n_wnba_resolved']}  "
        f"predictions: {meta['n_predictions']}",
        f"- Bets evaluated: **{payload['n_evaluated']}**  "
        f"positive-edge: **{payload['n_bets']}**",
        f"- Bankroll: ${meta['bankroll']:.0f}  "
        f"min edge: {meta['min_edge_pct']}pp  "
        f"L{meta['lookback']} mean + {meta['shrink']}-game shrink",
        "",
        "## Top bets (ranked by EV/unit)",
        "",
        "| # | Player | Stat | Side | Line | Odds | Model q50 | Edge | EV | Stake |",
        "|---|--------|------|------|-----:|-----:|----------:|-----:|---:|------:|",
    ]
    for i, b in enumerate(bets, 1):
        lines.append(
            f"| {i} | {b['player']} | {b['stat'].upper()} | {b['side']} | "
            f"{b['line']} | {b['odds']:+d} | {b['model_q50']:.1f} | "
            f"{b['edge_pp']:.1f}pp | {b['ev_per_unit']:+.3f} | ${b['stake_usd']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="WNBA prop bet ranker (R17_J6).")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                     help="Slate date (YYYY-MM-DD)")
    ap.add_argument("--season", default="2025")
    ap.add_argument("--bankroll", type=float, default=DEFAULT_BANKROLL)
    ap.add_argument("--lookback", type=int, default=wpp.DEFAULT_LOOKBACK)
    ap.add_argument("--shrink", type=float, default=wpp.DEFAULT_SHRINK)
    ap.add_argument("--min-edge", type=float, default=MIN_EDGE_PCT)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--lines-csv", default=None,
                     help="Override Bovada CSV path")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                         format="[%(asctime)s] %(message)s",
                         datefmt="%H:%M:%S")

    lines_csv = args.lines_csv or os.path.join(
        PROJECT_DIR, "data", "lines", f"{args.date}_bov.csv")
    df = read_lines_csv(lines_csv)
    df = latest_snapshot(df)

    payload = rank_bets(
        df, season=args.season, lookback=args.lookback, shrink=args.shrink,
        min_edge_pct=args.min_edge, bankroll=args.bankroll,
    )

    out_json = args.out_json or os.path.join(
        PROJECT_DIR, "data", "cache", "live_bets", f"wnba_{args.date}.json")
    out_md = args.out_md or os.path.join(
        PROJECT_DIR, "vault", "Predictions", f"wnba_{args.date}_live.md")
    atomic_write_json(out_json, payload)
    atomic_write_text(out_md, render_markdown(payload, args.date, top_n=args.top))

    if not args.quiet:
        print(f"[wnba_bet_ranker] lines={payload['meta']['n_lines_input']} "
              f"wnba_resolved={payload['meta']['n_wnba_resolved']} "
              f"predictions={payload['meta']['n_predictions']} "
              f"evaluated={payload['n_evaluated']} bets={payload['n_bets']}")
        for b in payload["bets"][:5]:
            print(f"  {b['ev_per_unit']:+.3f} EV | {b['player']:25s} "
                  f"{b['stat'].upper():4s} {b['side']:5s} {b['line']} @ {b['odds']:+d}  "
                  f"edge={b['edge_pp']:.1f}pp stake=${b['stake_usd']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
