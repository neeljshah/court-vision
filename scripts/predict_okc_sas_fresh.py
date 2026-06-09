"""predict_okc_sas_fresh.py — final consolidation for SAS @ OKC WCF G5.

Re-runs prop predictions on the 21 OKC + SAS rotation players using the
gamelogs refreshed through 2026-05-24 (WCF G1-G4 included). Then builds
the EV table vs the fresh Pinnacle / FanDuel / Bovada sharp lines.

Outputs:
  data/cache/intel_2026-05-26/slate_fresh_2026-05-26.parquet
  data/cache/intel_2026-05-26/ev_final_top25.csv
  data/cache/intel_2026-05-26/ev_final_high_conviction.csv
  data/cache/intel_2026-05-26/slate_fresh_vs_old.csv  (sanity check)
"""
from __future__ import annotations
import json, os, sys, math, csv
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = r"C:\Users\neelj\nba-ai-system"
sys.path.insert(0, PROJECT_DIR)

import warnings
warnings.filterwarnings("ignore", message="X does not have valid feature names")

import pandas as pd
import numpy as np

# Disable injury-wire dampener for the raw cache — we apply the filter manually
os.environ["NBA_INJURY_WIRE_DISABLE"] = "1"

from src.prediction.prop_pergame import (
    STATS, build_prediction_row, predict_pergame,
)
from src.prediction.prop_quantiles import predict_pergame_quantiles

NBA_DIR   = os.path.join(PROJECT_DIR, "data", "nba")
MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
INTEL_DIR = os.path.join(PROJECT_DIR, "data", "cache", "intel_2026-05-26")
LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")

DATE = "2026-05-26"
SEASON = "2025-26"
GAME_ID = "0042500315"

# (player_id, name, team, is_home_for_okc?)  OKC = home, SAS = away
ROSTER: List[Tuple[int, str, str, bool]] = [
    # OKC (home)
    (1628983, "Shai Gilgeous-Alexander", "OKC", True),
    (1631114, "Jalen Williams",           "OKC", True),
    (1631096, "Chet Holmgren",            "OKC", True),
    (1628392, "Isaiah Hartenstein",       "OKC", True),
    (1627936, "Alex Caruso",              "OKC", True),
    (1629652, "Luguentz Dort",            "OKC", True),
    (1641717, "Cason Wallace",            "OKC", True),
    (1642272, "Jared McCain",             "OKC", True),
    (1631119, "Jaylin Williams",          "OKC", True),
    (1630198, "Isaiah Joe",               "OKC", True),
    (1642349, "Ajay Mitchell",            "OKC", True),
    (1629026, "Kenrich Williams",         "OKC", True),
    # SAS (away)
    (1641705, "Victor Wembanyama",        "SAS", False),
    (1642264, "Stephon Castle",           "SAS", False),
    (1630170, "Devin Vassell",            "SAS", False),
    (1628368, "De'Aaron Fox",             "SAS", False),
    (1642844, "Dylan Harper",             "SAS", False),
    (1629640, "Keldon Johnson",           "SAS", False),
    (1630577, "Julian Champagnie",        "SAS", False),
    (1628436, "Luke Kornet",              "SAS", False),
    (203084,  "Harrison Barnes",          "SAS", False),
    (1642868, "Carter Bryant",            "SAS", False),
]

# Players ruled OUT by injury filter — zero out their predictions
OUT_PLAYERS = {"Jalen Williams", "Ajay Mitchell", "Thomas Sorber"}

# Playoff Kelly multiplier and bankroll
KELLY_MULT = 0.65
BANKROLL = 10_000.0
KELLY_CAP = 0.04


def american_to_decimal(odds: float) -> float:
    """American odds -> decimal payout (e.g., +150 -> 2.5, -120 -> 1.833)."""
    if odds > 0:
        return 1.0 + odds / 100.0
    else:
        return 1.0 + 100.0 / abs(odds)


def american_to_prob(odds: float) -> float:
    """American odds -> implied probability."""
    if odds > 0:
        return 100.0 / (odds + 100.0)
    else:
        return abs(odds) / (abs(odds) + 100.0)


def normal_p_over(mean: float, sigma: float, line: float) -> float:
    """P(X > line) under N(mean, sigma^2). Half-point continuity: line is .5."""
    if sigma <= 0:
        return 1.0 if mean > line else 0.0
    z = (line - mean) / sigma
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def predict_one(pid: int, opp: str, is_home: bool) -> Optional[Dict[str, Dict[str, float]]]:
    """Return {stat: {q10, q50, q90, sigma}} or None."""
    row = build_prediction_row(
        pid, opp, SEASON,
        is_home=is_home, rest_days=2.0, gamelog_dir=NBA_DIR,
    )
    if row is None:
        return None
    out: Dict[str, Dict[str, float]] = {}
    for stat in STATS:
        q50_point = predict_pergame(stat, row, MODEL_DIR)
        qint = predict_pergame_quantiles(stat, row, MODEL_DIR) or {}
        q10 = float(qint.get("q10", float("nan")))
        q50_q = float(qint.get("q50", float("nan")))
        q90 = float(qint.get("q90", float("nan")))
        q50 = float(q50_point) if q50_point is not None else q50_q
        # sigma proxy from quantile band: (q90 - q10) / 2.5631 ~= 1.0 (Normal 80% IQR)
        if math.isnan(q10) or math.isnan(q90):
            sigma = float("nan")
        else:
            sigma = max((q90 - q10) / 2.5631, 0.1)
        out[stat] = {"q10": q10, "q50": q50, "q90": q90, "sigma": sigma}
    return out


def main() -> int:
    os.makedirs(INTEL_DIR, exist_ok=True)
    print(f"\n  Slate {DATE} ({GAME_ID}) -- SAS @ OKC WCF Game 5")
    print(f"  Rosters: {len(ROSTER)} players")
    print(f"  OUT: {sorted(OUT_PLAYERS)}\n")

    # Step 1: fresh predictions
    rows = []
    for pid, name, team, is_home in ROSTER:
        opp = "SAS" if team == "OKC" else "OKC"
        is_out = name in OUT_PLAYERS
        if is_out:
            print(f"  [OUT]    {name:<28} ({team}) -- zeroed")
            for stat in STATS:
                rows.append({
                    "player_id": pid, "player": name, "team": team,
                    "opp": opp, "is_home": is_home, "stat": stat,
                    "q10": 0.0, "q50": 0.0, "q90": 0.0, "sigma": 0.1,
                    "status": "OUT",
                })
            continue
        preds = predict_one(pid, opp, is_home)
        if preds is None:
            print(f"  [SKIP]   {name:<28} ({team}) -- no row")
            continue
        q50_pts = preds["pts"]["q50"]
        q50_reb = preds["reb"]["q50"]
        q50_ast = preds["ast"]["q50"]
        print(f"  [pred]   {name:<28} ({team}) PTS {q50_pts:>5.2f}  "
              f"REB {q50_reb:>4.2f}  AST {q50_ast:>4.2f}")
        for stat, qd in preds.items():
            rows.append({
                "player_id": pid, "player": name, "team": team,
                "opp": opp, "is_home": is_home, "stat": stat,
                "q10": qd["q10"], "q50": qd["q50"],
                "q90": qd["q90"], "sigma": qd["sigma"],
                "status": "OK",
            })

    df = pd.DataFrame(rows)
    pq_path = os.path.join(INTEL_DIR, "slate_fresh_2026-05-26.parquet")
    df.to_parquet(pq_path, index=False)
    print(f"\n  -> wrote {len(df)} rows to {pq_path}")

    # Step 2: sanity-check table vs old slate + WCF series avg + Pin line
    old_path = os.path.join(PROJECT_DIR, "data", "predictions",
                             "slate_2026-05-26_post_inj_refresh.csv")
    old = pd.read_csv(old_path)
    old["stat"] = old["stat"].str.lower()
    old_lookup = {}
    for _, r in old.iterrows():
        old_lookup[(int(r["player_id"]), r["stat"])] = float(r["pred"])

    wcf = pd.read_csv(os.path.join(INTEL_DIR, "wcf_player_series_avg.csv"))
    wcf_lookup: Dict[Tuple[int, str], float] = {}
    for _, r in wcf.iterrows():
        pid = int(r["player_id"])
        for col, stat in [("pts_pg","pts"),("reb_pg","reb"),("ast_pg","ast"),
                          ("stl_pg","stl"),("blk_pg","blk"),("tov_pg","tov"),
                          ("fg3m_pg","fg3m")]:
            try:
                wcf_lookup[(pid, stat)] = float(r[col])
            except Exception:
                pass

    # Latest Pin snapshot per (player, stat) — last captured_at row
    pin = pd.read_csv(os.path.join(LINES_DIR, f"{DATE}_pin.csv"))
    pin["stat"] = pin["stat"].str.lower()
    pin = pin.sort_values("captured_at").drop_duplicates(["player_name","stat"], keep="last")
    pin_lookup: Dict[Tuple[str, str], dict] = {}
    for _, r in pin.iterrows():
        pin_lookup[(r["player_name"], r["stat"])] = {
            "line": float(r["line"]),
            "over_price": float(r["over_price"]),
            "under_price": float(r["under_price"]),
        }

    sanity_rows = []
    for _, r in df.iterrows():
        old_q50 = old_lookup.get((r["player_id"], r["stat"]))
        wcf_avg = wcf_lookup.get((r["player_id"], r["stat"]))
        pin_rec = pin_lookup.get((r["player"], r["stat"]))
        sanity_rows.append({
            "player": r["player"], "team": r["team"], "stat": r["stat"],
            "old_q50": old_q50, "new_q50": round(r["q50"], 3),
            "wcf_series_avg": wcf_avg,
            "pin_line": pin_rec["line"] if pin_rec else None,
            "gap_new_vs_pin": (round(r["q50"] - pin_rec["line"], 3)
                                if pin_rec else None),
            "gap_old_vs_pin": (round(old_q50 - pin_rec["line"], 3)
                                if pin_rec and old_q50 is not None else None),
        })
    san_df = pd.DataFrame(sanity_rows)
    san_path = os.path.join(INTEL_DIR, "slate_fresh_vs_old.csv")
    san_df.to_csv(san_path, index=False)
    print(f"  -> wrote sanity check to {san_path}")

    # Step 3: EV table — load all books
    books = {}
    for book_tag in ("pin", "fd", "bov"):
        fp = os.path.join(LINES_DIR, f"{DATE}_{book_tag}.csv")
        if not os.path.exists(fp):
            continue
        b = pd.read_csv(fp)
        b["stat"] = b["stat"].str.lower()
        b = b.sort_values("captured_at").drop_duplicates(
            ["player_name", "stat"], keep="last"
        )
        books[book_tag] = b

    pred_lookup: Dict[Tuple[str, str], dict] = {}
    for _, r in df.iterrows():
        pred_lookup[(r["player"], r["stat"])] = r.to_dict()

    ev_rows = []
    for book_tag, b in books.items():
        for _, lr in b.iterrows():
            key = (lr["player_name"], lr["stat"])
            pred = pred_lookup.get(key)
            if pred is None:
                continue
            if pred["status"] == "OUT":
                continue
            q50 = float(pred["q50"])
            sigma = float(pred["sigma"])
            if math.isnan(sigma) or sigma <= 0:
                continue
            line = float(lr["line"])
            for side, price_col in (("OVER", "over_price"), ("UNDER", "under_price")):
                try:
                    odds = float(lr[price_col])
                except Exception:
                    continue
                if math.isnan(odds):
                    continue
                p_over = normal_p_over(q50, sigma, line)
                p_win = p_over if side == "OVER" else 1.0 - p_over
                dec = american_to_decimal(odds)
                payout = dec - 1.0   # net win per $1
                ev_per_d = p_win * payout - (1.0 - p_win)
                ev_pct = ev_per_d * 100.0
                implied = american_to_prob(odds)
                edge_prob = p_win - implied
                edge_units = (q50 - line) if side == "OVER" else (line - q50)
                # Kelly: f* = (b*p - q) / b  where b=payout, p=p_win, q=1-p_win
                b_kelly = payout
                if b_kelly <= 0:
                    kelly_raw = 0.0
                else:
                    kelly_raw = (b_kelly * p_win - (1.0 - p_win)) / b_kelly
                kelly_raw = max(0.0, min(kelly_raw, KELLY_CAP))
                kelly_adj = kelly_raw * KELLY_MULT
                stake = round(kelly_adj * BANKROLL, 2)

                wcf_avg = wcf_lookup.get((pred["player_id"], pred["stat"]))
                # Series direction: positive if avg > line (model says OVER aligns)
                if wcf_avg is None:
                    series_dir = None; series_aligned = False
                else:
                    series_dir = "OVER" if wcf_avg > line else "UNDER"
                    series_aligned = (series_dir == side)
                model_dir = "OVER" if q50 > line else "UNDER"
                model_aligned = (model_dir == side)

                ev_rows.append({
                    "player": pred["player"],
                    "team": pred["team"],
                    "stat": pred["stat"],
                    "book": book_tag,
                    "side": side,
                    "line": line,
                    "model_q50": round(q50, 3),
                    "sigma": round(sigma, 3),
                    "wcf_series_avg": wcf_avg,
                    "edge_units": round(edge_units, 3),
                    "odds": int(odds),
                    "implied_p": round(implied, 4),
                    "model_p": round(p_win, 4),
                    "edge_prob": round(edge_prob, 4),
                    "ev_pct": round(ev_pct, 2),
                    "kelly_raw_pct": round(kelly_raw * 100, 3),
                    "kelly_adj_pct": round(kelly_adj * 100, 3),
                    "stake_$": stake,
                    "series_dir": series_dir,
                    "model_aligned_w_side": model_aligned,
                    "series_aligned_w_side": series_aligned,
                })

    ev_df = pd.DataFrame(ev_rows)

    # Top 25 by Kelly
    top25 = ev_df.sort_values("kelly_adj_pct", ascending=False).head(25)
    top25_path = os.path.join(INTEL_DIR, "ev_final_top25.csv")
    top25.to_csv(top25_path, index=False)
    print(f"  -> wrote top25 ({len(top25)}) to {top25_path}")

    # High-conviction filter:
    #   - model AND series both align with the bet side
    #   - edge_units > 0.5 AND ev_pct > 5
    #   - either Pin is the book OR a soft book offers >5% better odds than Pin
    pin_pivot: Dict[Tuple[str, str, str], float] = {}
    if "pin" in books:
        for _, lr in books["pin"].iterrows():
            line = float(lr["line"])
            for side, c in (("OVER","over_price"),("UNDER","under_price")):
                try:
                    pin_pivot[(lr["player_name"], lr["stat"], side)] = (
                        line, american_to_decimal(float(lr[c]))
                    )
                except Exception:
                    pass

    def pin_edge_check(row) -> bool:
        if row["book"] == "pin":
            return True
        key = (row["player"], row["stat"], row["side"])
        pin_rec = pin_pivot.get(key)
        if not pin_rec:
            return False
        pin_line, pin_dec = pin_rec
        # If lines differ, skip the "better odds" check (different prop)
        if abs(pin_line - row["line"]) > 1e-6:
            return False
        my_dec = american_to_decimal(row["odds"])
        return my_dec >= pin_dec * 1.05  # 5%+ better than Pin

    hc = ev_df[
        ev_df["model_aligned_w_side"] &
        ev_df["series_aligned_w_side"] &
        (ev_df["edge_units"] > 0.5) &
        (ev_df["ev_pct"] > 5.0)
    ].copy()
    hc["pin_edge_ok"] = hc.apply(pin_edge_check, axis=1)
    hc = hc[hc["pin_edge_ok"]].copy()
    hc = hc.sort_values("kelly_adj_pct", ascending=False).reset_index(drop=True)
    hc_path = os.path.join(INTEL_DIR, "ev_final_high_conviction.csv")
    hc.to_csv(hc_path, index=False)
    print(f"  -> wrote high-conviction ({len(hc)}) to {hc_path}")

    # Print top-10 high conviction summary
    print("\n  ===== TOP 10 HIGH CONVICTION =====")
    for i, r in hc.head(10).iterrows():
        print(f"   {i+1:>2}. {r['player']:<28} {r['stat'].upper():<5} "
              f"{r['side']} {r['line']:>5}  @{r['book']:>3} {int(r['odds']):+d}  "
              f"q50={r['model_q50']:>5.2f}  wcf={r['wcf_series_avg']:>5.2f}  "
              f"edge={r['edge_units']:+.2f}  EV={r['ev_pct']:+.1f}%  "
              f"K={r['kelly_adj_pct']:.2f}%  ${r['stake_$']:.0f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
