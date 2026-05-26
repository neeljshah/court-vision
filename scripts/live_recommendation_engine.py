"""live_recommendation_engine.py — R23_P8 end-to-end "what to bet right now".

Orchestrates the full live-stack to answer the operator's morning question
in one shot:

  Stage 1: Load slate predictions (predictions_cache_<date>.parquet, R16_E3
           served, R20_M7 m2_family + N5 cache.)
  Stage 2: Load latest snapshot per (book, player, stat, line) from
           data/lines/<today>_*.csv (FD / Bov / Pin).
  Stage 3: Load injury parquet (R22_O8 nba_injuries_<today>.parquet) and
           filter OUT players (availability_factor == 0.0).
  Stage 4: Compute edge per (player, stat, side, book) = model_prob - implied.
  Stage 5: Rank by edge; apply per-bet Kelly cap (R19_L2 KELLY_PCT_MAX=0.25)
           AND slate-level Kelly cap via R18_K7 multi_game_kelly (25%).
  Stage 6: Return ranked, sized, injury-filtered bet objects.

This module is a RECOMMENDATION engine — it does NOT place real bets. It
mirrors the math of `live_bet_ranker.run_tick` but operates on a single
"right now" snapshot rather than running as a polling daemon.

Public API
----------
    run_engine(
        bankroll: float = 1000.0,
        top: int = 10,
        date: str | None = None,
        exclude_books: list[str] | None = None,
        min_edge: float = 0.05,
        predictions_path: str | None = None,
        lines_dir: str | None = None,
        injury_parquet_path: str | None = None,
    ) -> dict

CLI
---
    python scripts/live_recommendation_engine.py \
        --bankroll 1000 --top 10 [--exclude-books PP,Bov] [--min-edge 0.05]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as _date_cls
from datetime import datetime, timezone
from math import erf, sqrt
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


# ----- constants (mirror R19_L2 / R18_K7 / live_bet_ranker) ----------------- #
KELLY_FRACTION  = 0.25     # fractional Kelly multiplier
PER_BET_CAP     = 0.05     # max stake per bet as fraction of bankroll
SLATE_CAP       = 0.25     # max total exposure across all bets
MAX_ODDS_ABS    = 400
MIN_PRICE_PROB  = 0.20
DEFAULT_MIN_EDGE = 0.05    # 5pp minimum edge


# ============================================================================ #
# Odds math (mirror scripts/live_bet_ranker.py)                                #
# ============================================================================ #
def american_to_decimal(odds: float) -> float:
    o = int(float(odds))
    return 1 + (o / 100.0) if o > 0 else 1 + (100.0 / -o)


def american_payout(odds: float, stake: float = 1.0) -> float:
    o = int(float(odds))
    return stake * (o / 100.0) if o > 0 else stake * (100.0 / -o)


def implied_prob(odds: float) -> float:
    o = int(float(odds))
    return 100.0 / (o + 100) if o > 0 else (-o) / ((-o) + 100)


def kelly_fraction(prob: float, odds: float) -> float:
    if prob is None or odds is None:
        return 0.0
    b = american_payout(odds, 1.0)
    p = prob
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, f)


def model_hit_prob_normal(
    point: float, q10: float, q90: float, line: float, side: str
) -> Optional[float]:
    """Probability the realised value lands on the chosen side of `line`,
    assuming a Normal(point, sigma) where sigma=(q90-q10)/(2*1.2816)."""
    if point is None or q10 is None or q90 is None:
        return None
    sigma = max((float(q90) - float(q10)) / (2 * 1.2816), 1e-6)
    z = (float(line) - float(point)) / sigma
    cdf_at_line = 0.5 * (1 + erf(z / sqrt(2)))
    p_over = 1.0 - cdf_at_line
    return p_over if str(side).upper() == "OVER" else (1.0 - p_over)


# ============================================================================ #
# Stage 1: predictions                                                         #
# ============================================================================ #
def load_predictions(
    date_str: str, predictions_path: Optional[str] = None
) -> Tuple[Optional["pd.DataFrame"], str]:
    """Load predictions_cache_<date>.parquet. Returns (df, reason).

    Returns (None, reason_string) when the file is missing/empty/unreadable.
    """
    import pandas as pd
    path = predictions_path or os.path.join(
        PROJECT_DIR, "data", "cache", f"predictions_cache_{date_str}.parquet"
    )
    if not os.path.exists(path):
        return None, f"predictions cache missing: {os.path.basename(path)}"
    try:
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        return None, f"predictions read error: {exc}"
    if df is None or df.empty:
        return None, "predictions cache is empty"
    needed = {"player_name", "stat", "q10", "q50", "q90"}
    if not needed.issubset(df.columns):
        return None, f"predictions missing cols: {needed - set(df.columns)}"
    return df, f"loaded {len(df)} prediction rows"


# ============================================================================ #
# Stage 2: book snapshots                                                      #
# ============================================================================ #
def load_book_snapshots(
    date_str: str,
    lines_dir: Optional[str] = None,
    exclude_books: Optional[List[str]] = None,
) -> Tuple[Dict[str, "pd.DataFrame"], int]:
    """Return (book -> latest snapshot per (player,stat,line), total_rows)."""
    from scripts.live_bet_ranker import _read_lines_csv  # reuses schema-aware reader
    import pandas as pd  # noqa: F401

    base_dir = lines_dir or os.path.join(PROJECT_DIR, "data", "lines")
    excluded = {b.strip().lower() for b in (exclude_books or [])}
    out: Dict[str, "pd.DataFrame"] = {}
    total = 0
    if not os.path.isdir(base_dir):
        return out, 0
    for book in ("fd", "bov", "pin", "pp"):
        if book in excluded:
            continue
        path = os.path.join(base_dir, f"{date_str}_{book}.csv")
        df = _read_lines_csv(path)
        if df.empty:
            continue
        df = df.dropna(subset=["captured_at"])
        if df.empty:
            continue
        df = df.sort_values("captured_at").drop_duplicates(
            subset=["player_name", "stat", "line"], keep="last"
        )
        out[book] = df
        total += len(df)
    return out, total


# ============================================================================ #
# Stage 3: injury filter (R22_O8)                                              #
# ============================================================================ #
def load_out_players(
    date_str: str, injury_parquet_path: Optional[str] = None
) -> Tuple[set, int]:
    """Return (set_of_lowercased_out_player_names, count)."""
    import pandas as pd
    path = injury_parquet_path or os.path.join(
        PROJECT_DIR, "data", "cache", f"nba_injuries_{date_str}.parquet"
    )
    if not os.path.exists(path):
        return set(), 0
    try:
        df = pd.read_parquet(path)
    except Exception:
        return set(), 0
    if df is None or df.empty or "status" not in df.columns:
        return set(), 0
    out_df = df[df["status"].astype(str).str.upper() == "OUT"]
    names = {
        str(n).strip().lower() for n in out_df["player_name"].dropna().tolist()
    }
    return names, len(names)


# ============================================================================ #
# Stages 4 + 5: rank, edge, Kelly cap                                          #
# ============================================================================ #
def _build_predictions_index(
    df_preds: "pd.DataFrame",
) -> Dict[Tuple[str, str], Dict[str, float]]:
    """Map (player_name_lower, stat_lower) -> {q10, q50, q90, team}."""
    idx: Dict[Tuple[str, str], Dict[str, float]] = {}
    for _, r in df_preds.iterrows():
        pname = str(r.get("player_name") or "").strip()
        stat  = str(r.get("stat") or "").strip().lower()
        if not pname or not stat:
            continue
        key = (pname.lower(), stat)
        idx[key] = {
            "q10":  float(r.get("q10")) if r.get("q10") is not None else None,
            "q50":  float(r.get("q50")) if r.get("q50") is not None else None,
            "q90":  float(r.get("q90")) if r.get("q90") is not None else None,
            "team": str(r.get("team") or ""),
        }
    return idx


def compute_recommendations(
    df_preds: "pd.DataFrame",
    books: Dict[str, "pd.DataFrame"],
    out_players: set,
    bankroll: float,
    min_edge: float,
    top: int,
) -> Dict[str, Any]:
    """Stages 4 + 5: compute edges, apply per-bet + slate Kelly caps."""
    import pandas as pd  # noqa: F401

    pred_idx = _build_predictions_index(df_preds)

    candidates: List[Dict[str, Any]] = []
    n_evaluated = 0
    n_filtered_out = 0
    n_filtered_no_pred = 0
    n_filtered_min_edge = 0

    for book, df in books.items():
        for _, r in df.iterrows():
            pname = str(r.get("player_name") or "").strip()
            stat  = str(r.get("stat") or "").strip().lower()
            if not pname or not stat:
                continue
            if pname.lower() in out_players:
                n_filtered_out += 1
                continue
            mdl = pred_idx.get((pname.lower(), stat))
            if mdl is None or mdl["q50"] is None:
                n_filtered_no_pred += 1
                continue
            try:
                line = float(r.get("line"))
            except (TypeError, ValueError):
                continue
            for side, price_col in (("OVER", "over_price"),
                                     ("UNDER", "under_price")):
                price = r.get(price_col)
                if price is None or (hasattr(price, "__float__") is False and pd.isna(price)):
                    continue
                try:
                    if pd.isna(price):
                        continue
                except Exception:
                    pass
                try:
                    odds = int(float(price))
                except (TypeError, ValueError):
                    continue
                if abs(odds) > MAX_ODDS_ABS:
                    continue
                impl = implied_prob(odds)
                if impl < MIN_PRICE_PROB:
                    continue
                prob = model_hit_prob_normal(
                    mdl["q50"], mdl["q10"], mdl["q90"], line, side
                )
                if prob is None:
                    continue
                n_evaluated += 1
                edge = prob - impl
                if edge < min_edge:
                    n_filtered_min_edge += 1
                    continue
                # Per-bet Kelly cap (R19_L2): full kelly * fraction, capped.
                kf_full   = kelly_fraction(prob, odds)
                kf_used   = min(kf_full * KELLY_FRACTION, PER_BET_CAP)
                stake     = round(kf_used * bankroll, 2)
                payout    = american_payout(odds, 1.0)
                ev        = prob * payout - (1.0 - prob)
                candidates.append({
                    "player":           pname,
                    "stat":             stat,
                    "side":             side,
                    "book":             book,
                    "line":             round(line, 2),
                    "odds":             odds,
                    "team":             mdl.get("team", ""),
                    "model_q10":        round(mdl["q10"], 3) if mdl["q10"] is not None else None,
                    "model_q50":        round(mdl["q50"], 3),
                    "model_q90":        round(mdl["q90"], 3) if mdl["q90"] is not None else None,
                    "model_prob":       round(prob, 4),
                    "implied_prob":     round(impl, 4),
                    "edge":             round(edge, 4),
                    "edge_pct":         round(edge * 100, 2),
                    "ev_per_dollar":    round(ev, 4),
                    "kelly_full":       round(kf_full, 4),
                    "kelly_pct":        round(kf_used, 4),
                    "stake_dollars":    stake,
                    "reason":           "positive edge, per-bet kelly applied",
                })

    # Stage 5 — rank by edge then EV, take top-N, then apply slate cap (R18_K7).
    candidates.sort(key=lambda b: (b["edge"], b["ev_per_dollar"]), reverse=True)
    top_n = candidates[: max(int(top), 0)]

    n_filtered_kelly_cap = 0
    cap_dollars = SLATE_CAP * float(bankroll)
    total_stake_pre = float(sum(b["stake_dollars"] for b in top_n))
    if total_stake_pre > cap_dollars and total_stake_pre > 0.0:
        multiplier = cap_dollars / total_stake_pre
        for b in top_n:
            b["stake_dollars_original"] = b["stake_dollars"]
            b["stake_dollars"] = round(b["stake_dollars"] * multiplier, 2)
            b["kelly_pct_original"] = b["kelly_pct"]
            b["kelly_pct"] = round(b["kelly_pct"] * multiplier, 4)
            b["reason"] = "slate cap scaled (R18_K7 multi_game_kelly)"
            n_filtered_kelly_cap += 1
    total_stake_post = float(sum(b["stake_dollars"] for b in top_n))

    return {
        "n_evaluated":             n_evaluated,
        "n_filtered_out":          n_filtered_out,
        "n_filtered_no_pred":      n_filtered_no_pred,
        "n_filtered_min_edge":     n_filtered_min_edge,
        "n_candidates_pos_edge":   len(candidates),
        "n_recs":                  len(top_n),
        "n_filtered_kelly_cap":    n_filtered_kelly_cap,
        "slate_cap_dollars":       round(cap_dollars, 2),
        "total_stake_pre_cap":     round(total_stake_pre, 2),
        "total_stake_post_cap":    round(total_stake_post, 2),
        "recommendations":         top_n,
    }


# ============================================================================ #
# Orchestrator                                                                  #
# ============================================================================ #
def run_engine(
    bankroll: float = 1000.0,
    top: int = 10,
    date: Optional[str] = None,
    exclude_books: Optional[List[str]] = None,
    min_edge: float = DEFAULT_MIN_EDGE,
    predictions_path: Optional[str] = None,
    lines_dir: Optional[str] = None,
    injury_parquet_path: Optional[str] = None,
) -> Dict[str, Any]:
    """End-to-end recommendation engine. Returns a single payload dict.

    On any missing input the payload contains an empty recommendations list
    and a populated `reason` field — never raises.
    """
    if bankroll <= 0:
        return _empty_payload(date, reason=f"bankroll must be > 0 (got {bankroll})")
    date_str = date or _date_cls.today().isoformat()
    payload: Dict[str, Any] = {
        "generated_at":       datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date":               date_str,
        "bankroll":           float(bankroll),
        "top":                int(top),
        "min_edge":           float(min_edge),
        "exclude_books":      list(exclude_books or []),
        "engine_version":     "R23_P8",
    }

    # Stage 1
    df_preds, pred_reason = load_predictions(date_str, predictions_path)
    payload["n_predictions_available"] = 0 if df_preds is None else int(len(df_preds))
    payload["predictions_reason"] = pred_reason
    if df_preds is None:
        payload["recommendations"] = []
        payload["reason"] = pred_reason
        payload["n_evaluated"] = 0
        payload["n_filtered_out"] = 0
        payload["n_filtered_kelly_cap"] = 0
        return payload

    # Stage 2
    books, total_rows = load_book_snapshots(date_str, lines_dir, exclude_books)
    payload["n_snapshots_loaded"] = int(total_rows)
    payload["books_loaded"] = sorted(books.keys())
    if not books:
        payload["recommendations"] = []
        payload["reason"] = "no book snapshots available"
        payload["n_evaluated"] = 0
        payload["n_filtered_out"] = 0
        payload["n_filtered_kelly_cap"] = 0
        return payload

    # Stage 3
    out_players, n_out = load_out_players(date_str, injury_parquet_path)
    payload["n_out_players_in_feed"] = int(n_out)

    # Stages 4 + 5
    rec_payload = compute_recommendations(
        df_preds=df_preds,
        books=books,
        out_players=out_players,
        bankroll=float(bankroll),
        min_edge=float(min_edge),
        top=int(top),
    )
    payload.update({
        "n_evaluated":          rec_payload["n_evaluated"],
        "n_filtered_out":       rec_payload["n_filtered_out"],
        "n_filtered_no_pred":   rec_payload["n_filtered_no_pred"],
        "n_filtered_min_edge":  rec_payload["n_filtered_min_edge"],
        "n_candidates_pos_edge": rec_payload["n_candidates_pos_edge"],
        "n_recs":               rec_payload["n_recs"],
        "n_filtered_kelly_cap": rec_payload["n_filtered_kelly_cap"],
        "slate_cap_dollars":    rec_payload["slate_cap_dollars"],
        "total_stake_pre_cap":  rec_payload["total_stake_pre_cap"],
        "total_stake_post_cap": rec_payload["total_stake_post_cap"],
        "recommendations":      rec_payload["recommendations"],
    })
    if rec_payload["recommendations"]:
        payload["reason"] = (
            f"{rec_payload['n_recs']} recs ranked; "
            f"slate exposure ${rec_payload['total_stake_post_cap']:.2f} of "
            f"${rec_payload['slate_cap_dollars']:.2f} cap"
        )
    else:
        payload["reason"] = (
            "no positive-edge recs above min_edge "
            f"(evaluated {rec_payload['n_evaluated']}, "
            f"filtered OUT={rec_payload['n_filtered_out']}, "
            f"no_pred={rec_payload['n_filtered_no_pred']}, "
            f"below_min_edge={rec_payload['n_filtered_min_edge']})"
        )
    return payload


def _empty_payload(date: Optional[str], reason: str) -> Dict[str, Any]:
    date_str = date or _date_cls.today().isoformat()
    return {
        "generated_at":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date":                 date_str,
        "recommendations":      [],
        "reason":                reason,
        "n_predictions_available": 0,
        "n_snapshots_loaded":   0,
        "n_evaluated":          0,
        "n_filtered_out":       0,
        "n_filtered_kelly_cap": 0,
        "engine_version":       "R23_P8",
    }


# ============================================================================ #
# CLI table formatter                                                          #
# ============================================================================ #
def format_table(payload: Dict[str, Any]) -> str:
    recs = payload.get("recommendations", [])
    lines = []
    lines.append("=" * 100)
    lines.append(
        f"LIVE RECOMMENDATION ENGINE — {payload.get('engine_version','')}  "
        f"({payload.get('date','')})"
    )
    lines.append("=" * 100)
    lines.append(
        f"Bankroll: ${payload.get('bankroll',0):.2f}  |  "
        f"Top: {payload.get('top',0)}  |  "
        f"Min edge: {payload.get('min_edge',0):.3f}"
    )
    if payload.get("exclude_books"):
        lines.append(f"Excluded books: {', '.join(payload['exclude_books'])}")
    lines.append(
        f"Predictions: {payload.get('n_predictions_available',0)}  |  "
        f"Snapshots: {payload.get('n_snapshots_loaded',0)}  |  "
        f"Books: {payload.get('books_loaded', [])}"
    )
    lines.append(
        f"Filtered OUT: {payload.get('n_filtered_out',0)}  |  "
        f"No pred: {payload.get('n_filtered_no_pred',0)}  |  "
        f"Below min-edge: {payload.get('n_filtered_min_edge',0)}  |  "
        f"Kelly cap scaled: {payload.get('n_filtered_kelly_cap',0)}"
    )
    lines.append(
        f"Slate cap: ${payload.get('slate_cap_dollars',0):.2f}  |  "
        f"Total stake: ${payload.get('total_stake_post_cap',0):.2f}"
    )
    lines.append(f"Reason: {payload.get('reason','—')}")
    lines.append("-" * 100)
    if not recs:
        lines.append("(no recommendations)")
        return "\n".join(lines)
    header = (
        f"{'#':>2}  {'Player':<24} {'Stat':<5} {'Side':<5} "
        f"{'Book':<5} {'Line':>6} {'Odds':>6} {'Edge%':>7} "
        f"{'Kelly%':>7} {'Stake$':>8}"
    )
    lines.append(header)
    lines.append("-" * 100)
    for i, b in enumerate(recs, 1):
        lines.append(
            f"{i:>2}  {b['player'][:24]:<24} {b['stat'].upper():<5} "
            f"{b['side']:<5} {b['book']:<5} "
            f"{b['line']:>6.1f} {b['odds']:>+6d} "
            f"{b['edge_pct']:>+6.2f}% "
            f"{b['kelly_pct']*100:>6.2f}% "
            f"${b['stake_dollars']:>7.2f}"
        )
    return "\n".join(lines)


# ============================================================================ #
# CLI                                                                          #
# ============================================================================ #
def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--date", type=str, default=None,
                    help="ISO date (defaults to today)")
    ap.add_argument("--exclude-books", type=str, default="",
                    help="comma-separated book ids to exclude (e.g. 'PP,Bov')")
    ap.add_argument("--min-edge", type=float, default=DEFAULT_MIN_EDGE,
                    help="minimum edge as a fraction (0.05 == 5pp)")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON instead of a table")
    ap.add_argument("--out", type=str, default=None,
                    help="optional path to also write payload JSON to")
    return ap.parse_args()


def main() -> int:
    args = _parse_args()
    excludes = [b.strip().lower() for b in args.exclude_books.split(",") if b.strip()]
    payload = run_engine(
        bankroll=args.bankroll,
        top=args.top,
        date=args.date,
        exclude_books=excludes,
        min_edge=args.min_edge,
    )
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(format_table(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
