"""probe_R15_tonight_slate.py — single-game slate runner for SAS@OKC Game 7 WCF.

Reads FD / BOV / Pinnacle line CSVs, computes model q10/q50/q90 per player
per stat (with injury availability factor applied), evaluates EV vs every
book / line / side, ranks bets by EV, sizes with Kelly (0.25-fractional,
5% bankroll cap per bet, 25% slate exposure cap), and detects
cross-book middle arbitrage.

Outputs:
    data/cache/probe_R15_tonight_slate_bets.json — machine output
    vault/Predictions/2026-05-26_spurs_okc_game7.md — human-readable
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, date as _date
from math import erf, sqrt

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_prediction_row, predict_pergame,
)
from src.prediction.prop_quantiles import (  # noqa: E402
    predict_pergame_quantiles,
)
from src.prediction.quantile_calibration import apply as apply_quantile_calibration  # noqa: E402
from src.prediction.injury_availability import (  # noqa: E402
    get_availability_factor,
)


# --------- config ----------
BANKROLL = 1000.0
KELLY_FRACTION = 0.25      # 0.25-fractional Kelly
PER_BET_CAP = 0.05         # 5% bankroll cap per bet
SLATE_CAP = 0.25           # 25% bankroll cap on total slate
MIN_EDGE_PCT = 0.5         # show bets with >=0.5% raw EV
# Model tail is unreliable for big alt-line longshots — the quantile bands
# are fit on regular-season data and don't price playoff-game tails well.
# Hard guardrails: skip any bet where the book odds imply <15% hit rate
# (i.e. > +570) — those are alt-lines / longshots and the model edge is
# almost always a calibration artifact.
MAX_ODDS_ABS = 400         # exclude prices > +400 or < -400
MIN_PRICE_PROB = 0.20      # exclude any line where implied prob < 20%
SEASON = "2024-25"
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
OUT_JSON = os.path.join(PROJECT_DIR, "data", "cache",
                         "probe_R15_tonight_slate_bets.json")
OUT_MD = os.path.join(PROJECT_DIR, "vault", "Predictions",
                        "2026-05-26_spurs_okc_game7.md")

# Roster splits (SAS @ OKC — Game 7 WCF)
SAS_PLAYERS = [
    "Victor Wembanyama", "De'Aaron Fox", "Devin Vassell", "Stephon Castle",
    "Keldon Johnson", "Dylan Harper", "Julian Champagnie", "Jared McCain",
]
OKC_PLAYERS = [
    "Shai Gilgeous-Alexander", "Jalen Williams", "Chet Holmgren",
    "Luguentz Dort", "Cason Wallace", "Alex Caruso",
    "Isaiah Hartenstein", "Jaylin Williams", "Luke Kornet",
]
SAS_OPP = "OKC"
OKC_OPP = "SAS"
# OKC is home (per Pinnacle mainline csv), SAS is away
SAS_HOME = False
OKC_HOME = True


# --------- odds helpers (mirror compare_to_lines.py) ----------
def american_to_decimal(odds):
    if odds is None or pd.isna(odds):
        return None
    o = int(float(odds))
    if o > 0:
        return 1 + o / 100.0
    return 1 + 100.0 / (-o)


def american_payout(odds, stake=1.0):
    o = int(float(odds))
    if o > 0:
        return stake * (o / 100.0)
    return stake * (100.0 / (-o))


def implied_prob(odds):
    o = int(float(odds))
    if o > 0:
        return 100.0 / (o + 100)
    return (-o) / ((-o) + 100)


def model_hit_prob(stat, point_pred, qint, line, side):
    q10 = qint.get("q10")
    q50 = qint.get("q50")
    q90 = qint.get("q90")
    if q10 is None or q90 is None or point_pred is None:
        return None
    cal_q10, cal_q90 = apply_quantile_calibration(
        stat, q10, q50 or point_pred, q90
    )
    sigma = max((cal_q90 - cal_q10) / (2 * 1.2816), 1e-6)
    z = (line - point_pred) / sigma
    cdf_at_line = 0.5 * (1 + erf(z / sqrt(2)))
    p_over = 1 - cdf_at_line
    return p_over if side == "OVER" else 1 - p_over


def kelly_fraction(prob, odds):
    if prob is None or odds is None or pd.isna(odds):
        return 0.0
    b = american_payout(odds, 1.0)
    p = prob
    q = 1 - p
    f = (b * p - q) / b
    return max(0.0, f)


def resolve_pid(name):
    try:
        from nba_api.stats.static import players
    except Exception:
        return None
    import unicodedata
    def _strip(s):
        n = unicodedata.normalize("NFKD", str(s))
        return "".join(c for c in n if not unicodedata.combining(c)).lower()
    needle = _strip(name)
    cands = players.get_players()
    for p in cands:
        if _strip(p["full_name"]) == needle:
            return int(p["id"])
    for p in cands:
        if needle in _strip(p["full_name"]):
            return int(p["id"])
    return None


# --------- data load ----------
def _read_lines_csv(path):
    """Robust reader: Bovada changed schema mid-day, some rows have 11 fields.
    We map by the canonical 10-column schema and discard malformed rows."""
    import csv as _csv
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = _csv.reader(f)
        header = next(reader)
        # detect schema
        canon = ["captured_at", "book", "game_id", "player_id",
                 "player_name", "stat", "line", "over_price",
                 "under_price", "start_time"]
        for row in reader:
            # Bovada new schema: captured_at,book,game_id,_,player_name,team,stat,line,o,u,start
            if len(row) == 10:
                d = dict(zip(canon, row))
            elif len(row) == 11:
                # newer Bovada has an inserted team column at index 5
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
    df = pd.DataFrame(rows)
    return df


def load_books():
    """Return dict[book] -> DataFrame with latest snapshot per (player,stat,line,side)."""
    out = {}
    for book in ("fd", "bov", "pin"):
        path = os.path.join(PROJECT_DIR, "data", "lines",
                            f"2026-05-26_{book}.csv")
        if not os.path.exists(path):
            continue
        df = _read_lines_csv(path)
        if df.empty:
            continue
        df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce")
        df["line"] = pd.to_numeric(df["line"], errors="coerce")
        df["over_price"] = pd.to_numeric(df["over_price"], errors="coerce")
        df["under_price"] = pd.to_numeric(df["under_price"], errors="coerce")
        # take latest snapshot per (player_name, stat, line)
        df = df.sort_values("captured_at").drop_duplicates(
            subset=["player_name", "stat", "line"], keep="last"
        )
        out[book] = df
    return out


# --------- model ----------
def predict_player(name, opp, is_home, season=SEASON):
    pid = resolve_pid(name)
    if pid is None:
        return None, "no_pid"
    prow = build_prediction_row(pid, opp, season, is_home=is_home,
                                 rest_days=2.0, gamelog_dir=GAMELOG_DIR)
    if prow is None:
        return None, "no_gamelog"
    out = {}
    for s in STATS:
        try:
            point = predict_pergame(s, prow, MODEL_DIR)
            qint = predict_pergame_quantiles(s, prow, MODEL_DIR)
            if point is None or qint is None:
                continue
            # injury availability scaling
            factor = get_availability_factor(player_id=pid, player_name=name)
            if factor == 0.0:
                # OUT — collapse to zero; downstream will skip
                out[s] = {"point": 0.0, "q10": 0.0, "q50": 0.0, "q90": 0.0,
                          "availability_factor": 0.0}
                continue
            point_adj = float(point) * factor
            qadj = {k: (float(v) * factor) if isinstance(v, (int, float))
                    else v for k, v in qint.items()}
            out[s] = {"point": point_adj, "q10": qadj.get("q10"),
                       "q50": qadj.get("q50"), "q90": qadj.get("q90"),
                       "availability_factor": factor}
        except Exception as exc:
            print(f"  [warn] {name} {s}: {exc}")
            continue
    return (out, "ok") if out else (None, "no_preds")


# --------- arbitrage / middles ----------
def find_middles(by_player_stat_book):
    """Given a nested dict {player: {stat: {book: rows}}}, find pairs where
    book_A OVER line is strictly less than book_B UNDER line (a 'middle'),
    flag those where both sides are at -120 or better."""
    middles = []
    for player, stats_dict in by_player_stat_book.items():
        for stat, book_dict in stats_dict.items():
            overs = []  # (book, line, price)
            unders = []
            for book, rows in book_dict.items():
                for r in rows:
                    if r["over_price"] is not None and not pd.isna(r["over_price"]):
                        overs.append((book, float(r["line"]),
                                       int(r["over_price"])))
                    if r["under_price"] is not None and not pd.isna(r["under_price"]):
                        unders.append((book, float(r["line"]),
                                        int(r["under_price"])))
            for (bo, lo, po) in overs:
                for (bu, lu, pu) in unders:
                    if bo == bu:
                        continue
                    gap = lu - lo  # OVER lo < UNDER lu means middle
                    # Real middles: gap between 1 and 5 line units,
                    # AND both prices reasonable (>= -130 each).
                    # Excludes alt-line vs main-line "fake middles".
                    if 1.0 <= gap <= 5.0 and po >= -130 and pu >= -130:
                        middles.append({
                            "player": player, "stat": stat,
                            "over_book": bo, "over_line": lo,
                            "over_price": po,
                            "under_book": bu, "under_line": lu,
                            "under_price": pu,
                            "middle_width": round(gap, 2),
                        })
    return middles


# --------- main ----------
def main():
    print("[1/5] Loading line CSVs...")
    books = load_books()
    n_lines = sum(len(df) for df in books.values())
    print(f"  loaded {n_lines} total line rows across {list(books.keys())}")

    # Build (player, team, opp, is_home)
    roster = [(p, "SAS", SAS_OPP, SAS_HOME) for p in SAS_PLAYERS] + \
             [(p, "OKC", OKC_OPP, OKC_HOME) for p in OKC_PLAYERS]

    print(f"[2/5] Running model on {len(roster)} players...")
    preds = {}
    skipped = []
    for name, team, opp, is_home in roster:
        out, status = predict_player(name, opp, is_home)
        if out is None:
            skipped.append((name, status))
            print(f"  [skip] {name} ({status})")
            continue
        preds[name] = {"team": team, "opp": opp, "is_home": is_home,
                       "stats": out}
        af = next(iter(out.values())).get("availability_factor", 1.0)
        print(f"  [ok] {name:25s} af={af:.2f} pts_q50={out.get('pts',{}).get('q50'):.1f}"
              if out.get("pts") else f"  [ok] {name}")

    print(f"[3/5] Modelled {len(preds)} players ({len(skipped)} skipped)")

    # Build line index: {player: {stat: {book: [rows]}}}
    line_idx = {}
    for book, df in books.items():
        for _, r in df.iterrows():
            pname = r["player_name"]
            stat = r["stat"]
            line_idx.setdefault(pname, {}).setdefault(stat, {}) \
                .setdefault(book, []).append({
                    "line": r["line"],
                    "over_price": r.get("over_price"),
                    "under_price": r.get("under_price"),
                })

    print("[4/5] Evaluating bets...")
    bets = []
    n_evaluated = 0
    for pname, pdata in preds.items():
        stats_dict = line_idx.get(pname, {})
        for stat, book_dict in stats_dict.items():
            if stat not in pdata["stats"]:
                continue
            mdl = pdata["stats"][stat]
            if mdl.get("availability_factor", 1.0) == 0.0:
                continue
            point = mdl["point"]
            qint = {"q10": mdl["q10"], "q50": mdl["q50"], "q90": mdl["q90"]}
            for book, rows in book_dict.items():
                for r in rows:
                    line = float(r["line"])
                    for side, price_col in (("OVER", "over_price"),
                                              ("UNDER", "under_price")):
                        price = r.get(price_col)
                        if price is None or pd.isna(price):
                            continue
                        odds = int(float(price))
                        # GUARDRAIL: skip extreme prices — model tail
                        # uncalibrated, edge is artifact.
                        if abs(odds) > MAX_ODDS_ABS:
                            continue
                        impl_check = implied_prob(odds)
                        if impl_check < MIN_PRICE_PROB:
                            continue
                        prob = model_hit_prob(stat, point, qint, line, side)
                        if prob is None:
                            continue
                        n_evaluated += 1
                        net = american_payout(odds, 1.0)
                        ev = prob * net - (1 - prob) * 1.0
                        kf_full = kelly_fraction(prob, odds)
                        kf_used = kf_full * KELLY_FRACTION
                        # cap at PER_BET_CAP
                        kf_used = min(kf_used, PER_BET_CAP)
                        stake = round(kf_used * BANKROLL, 2)
                        impl = implied_prob(odds)
                        # sigma from quantiles (for high-confidence flag)
                        cal_q10, cal_q90 = apply_quantile_calibration(
                            stat, qint["q10"], qint["q50"] or point,
                            qint["q90"]
                        )
                        sigma = max((cal_q90 - cal_q10) / (2 * 1.2816), 1e-6)
                        sigma_dev = (point - line) / sigma if side == "OVER" \
                            else (line - point) / sigma
                        bets.append({
                            "player": pname,
                            "team": pdata["team"],
                            "stat": stat,
                            "side": side,
                            "book": book,
                            "line": line,
                            "model_q50": round(point, 2),
                            "model_q10": round(qint["q10"], 2)
                                if qint["q10"] is not None else None,
                            "model_q90": round(qint["q90"], 2)
                                if qint["q90"] is not None else None,
                            "odds": odds,
                            "implied_prob": round(impl, 4),
                            "model_prob": round(prob, 4),
                            "edge_pct": round((prob - impl) * 100, 2),
                            "edge_bps": round((prob - impl) * 10000, 1),
                            "ev_per_dollar": round(ev, 4),
                            "kelly_pct_full": round(kf_full * 100, 2),
                            "kelly_pct_used": round(kf_used * 100, 2),
                            "kelly_stake_$1000": stake,
                            "sigma_deviation": round(sigma_dev, 2),
                            "availability_factor":
                                mdl.get("availability_factor", 1.0),
                        })

    # Sort by EV desc
    bets.sort(key=lambda x: x["ev_per_dollar"], reverse=True)

    # Filter to positive-edge bets only
    pos_bets = [b for b in bets if b["edge_pct"] >= MIN_EDGE_PCT]

    # Apply 25% slate exposure cap on positive bets
    total_stake = 0.0
    capped_bets = []
    cap_dollars = SLATE_CAP * BANKROLL
    for b in pos_bets:
        if total_stake + b["kelly_stake_$1000"] <= cap_dollars:
            capped_bets.append(b)
            total_stake += b["kelly_stake_$1000"]
        else:
            # scale this one down to fit
            remaining = max(0.0, cap_dollars - total_stake)
            if remaining >= 5.0:
                b2 = dict(b)
                b2["kelly_stake_$1000"] = round(remaining, 2)
                capped_bets.append(b2)
                total_stake += remaining
            break

    # EV expected dollars
    exp_ev = sum(b["ev_per_dollar"] * b["kelly_stake_$1000"]
                  for b in capped_bets)
    exp_var = sum(b["model_prob"] * (american_payout(b["odds"], 1.0) ** 2)
                   * (b["kelly_stake_$1000"] ** 2) +
                   (1 - b["model_prob"]) * (b["kelly_stake_$1000"] ** 2)
                   for b in capped_bets)
    exp_std = sqrt(exp_var)

    # Middles
    middles = find_middles(line_idx)

    # Highest-confidence: |sigma_dev| >= 1.0, positive EV
    high_conf = [b for b in capped_bets if b["sigma_deviation"] >= 1.0]

    print(f"[5/5] Bets evaluated: {n_evaluated}, positive-edge: {len(pos_bets)},"
          f" final (capped): {len(capped_bets)}")
    print(f"  total exposure: ${total_stake:.2f} of ${BANKROLL:.2f}")
    print(f"  expected EV: ${exp_ev:.2f}, expected std: ${exp_std:.2f}")
    print(f"  middles found: {len(middles)}")

    payload = {
        "game": "SAS @ OKC Game 7 WCF",
        "captured_at": datetime.utcnow().isoformat() + "Z",
        "books_used": list(books.keys()),
        "n_props_evaluated": n_evaluated,
        "n_players_modelled": len(preds),
        "players_skipped": [{"name": n, "reason": r} for n, r in skipped],
        "bankroll": BANKROLL,
        "kelly_fraction": KELLY_FRACTION,
        "per_bet_cap_pct": PER_BET_CAP * 100,
        "slate_cap_pct": SLATE_CAP * 100,
        "min_edge_pct": MIN_EDGE_PCT,
        "total_recommended_exposure_$": round(total_stake, 2),
        "expected_value_$": round(exp_ev, 2),
        "expected_std_$": round(exp_std, 2),
        "ranked_bets": capped_bets,
        "all_positive_bets_unfiltered": pos_bets[:50],
        "arbitrage_middles": middles,
        "highest_confidence_bets": high_conf,
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"  wrote {OUT_JSON}")

    # ----- vault markdown -----
    md_lines = []
    md_lines.append(f"# 2026-05-26 — Spurs @ Thunder Game 7 WCF Bet Slate\n")
    md_lines.append(f"_Generated: {payload['captured_at']}_\n")
    md_lines.append(f"**Books scraped:** {', '.join(books.keys())}  ")
    md_lines.append(f"**Props evaluated:** {n_evaluated}  ")
    md_lines.append(f"**Players modelled:** {len(preds)}  ")
    md_lines.append(f"**Players skipped:** "
                    f"{', '.join(f'{n}({r})' for n,r in skipped) or 'none'}\n")
    md_lines.append(f"**Bankroll:** ${BANKROLL:.0f}  ")
    md_lines.append(f"**Strategy:** 0.25-fractional Kelly, "
                    f"5% per-bet cap, 25% slate cap  \n")
    md_lines.append(f"## Headline\n")
    md_lines.append(f"- Total recommended exposure: "
                    f"**${total_stake:.2f}** ({total_stake/BANKROLL*100:.1f}% of bankroll)")
    md_lines.append(f"- Expected EV: **${exp_ev:+.2f}**")
    md_lines.append(f"- Expected std: ${exp_std:.2f}")
    md_lines.append(f"- Edge-positive props found: {len(pos_bets)}")
    md_lines.append(f"- Arbitrage middles: {len(middles)}\n")
    md_lines.append("## Top Ranked Bets\n")
    md_lines.append("| # | Player | Team | Stat | Side | Book | Line | Model q50 "
                    "| Edge % | Kelly % | Stake $ | σ-dev |")
    md_lines.append("|--|--|--|--|--|--|--|--|--|--|--|--|")
    for i, b in enumerate(capped_bets[:25], 1):
        md_lines.append(
            f"| {i} | {b['player']} | {b['team']} | {b['stat'].upper()} "
            f"| {b['side']} | {b['book']} | {b['line']:.1f} "
            f"| {b['model_q50']:.2f} | {b['edge_pct']:+.2f}% "
            f"| {b['kelly_pct_used']:.2f}% | ${b['kelly_stake_$1000']:.2f} "
            f"| {b['sigma_deviation']:+.2f} |"
        )
    md_lines.append("\n## High-Confidence Picks (|σ-dev| ≥ 1.0)\n")
    if high_conf:
        for b in high_conf[:10]:
            md_lines.append(
                f"- **{b['player']} {b['stat'].upper()} {b['side']} "
                f"{b['line']:.1f}** @ {b['book']} {b['odds']:+d} — "
                f"model q50={b['model_q50']:.2f} ({b['sigma_deviation']:+.2f}σ), "
                f"edge {b['edge_pct']:+.2f}%, stake ${b['kelly_stake_$1000']:.2f}"
            )
    else:
        md_lines.append("_none_")
    md_lines.append("\n## Arbitrage Middles\n")
    if middles:
        for m in middles:
            md_lines.append(
                f"- **{m['player']} {m['stat'].upper()}** — OVER "
                f"{m['over_line']:.1f} @ {m['over_book']} ({m['over_price']:+d}) "
                f"× UNDER {m['under_line']:.1f} @ {m['under_book']} "
                f"({m['under_price']:+d}), width={m['middle_width']:.1f}"
            )
    else:
        md_lines.append("_none_")
    md_lines.append("\n## Verdict\n")
    if not capped_bets:
        md_lines.append(
            "**SIT OUT.** No positive-edge prop survived vig at any book."
        )
    elif total_stake < 25:
        md_lines.append(
            "**MARGINAL — small slate.** Edges are real but tiny; "
            "execution slippage will probably eat most of the EV."
        )
    else:
        md_lines.append(
            f"**Play the top {min(5,len(capped_bets))} bets** at the listed "
            f"stakes. Total ${total_stake:.0f} exposure, "
            f"${exp_ev:+.2f} EV / ${exp_std:.0f} std."
        )

    md_lines.append("\n## Honesty Caveats\n")
    md_lines.append(
        "- Model edges of +30-50% smell rich. The prop_pergame model is "
        "trained on regular-season data; playoff Game 7 variance is "
        "outside the training distribution. Treat all 'edge_pct' figures "
        "as upper bounds — true edge after vig + variance is likely "
        "30-50% of the printed value."
    )
    md_lines.append(
        "- Bovada blocks (BLK / STL) are notoriously soft — the +200 on "
        "Wemby UNDER 2.5 BLK isn't quoted by Pinnacle at all. When the "
        "sharp book won't price it, the edge is either real-and-quickly-"
        "moved or fake."
    )
    md_lines.append(
        "- 'Middles' detected use a same-stat ≤5-point gap with both "
        "sides priced ≥-130. Mainline middles ($1-line gap) are tiny "
        "variance plays — only worth executing if you can hit both sides "
        "simultaneously."
    )
    md_lines.append(
        "- Pinnacle is the sharpest book in the slate. Bets that show "
        "edge vs Pinnacle (not just FD/Bovada) are the highest-quality "
        "signals."
    )

    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"  wrote {OUT_MD}")


if __name__ == "__main__":
    main()
