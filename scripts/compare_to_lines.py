"""compare_to_lines.py — compare model predictions vs YOUR pasted sportsbook lines.

Lets you ingest actual prop O/U lines from a CSV/TSV file and see where the
model has claimed edge. Output is a sortable ranking of bets by EV.

The CSV must have these columns (case-insensitive):
    player        — full player name (NBA stats.com canonical)
    opp           — opponent team abbrev (LAL, DEN, etc.)
    venue         — 'home' or 'away' (player's team's side)
    stat          — one of: pts reb ast fg3m stl blk tov
    line          — the over/under number from the book (e.g. 22.5)
  optional:
    over_odds     — American odds for OVER (e.g. -110). Default -110.
    under_odds    — American odds for UNDER. Default -110.
    rest_days     — defaults to 2.0 if missing
    season        — defaults to current

Usage:
    python scripts/compare_to_lines.py tonight.csv
    python scripts/compare_to_lines.py tonight.csv --min-edge 1.0
    python scripts/compare_to_lines.py tonight.csv --kelly --bankroll 1000

Output (sorted by EV):
    player           stat  line   model  edge   bet   prob   odds   EV/$   Kelly%
    Nikola Jokic     REB   11.5   13.07  +1.57  OVER  0.671  -110  +27.96  5.42%
    ...
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, date as _date

import numpy as np

# Cycle 51: injury statuses that mean "don't bet this player". QUESTIONABLE
# is intentionally NOT in this set — the player is more likely than not to
# play, and the model's L5/L10 features already partially account for limited
# minutes. PROBABLE / AVAILABLE / NOT-LISTED never skip.
_UNAVAILABLE_STATUSES = {"OUT", "DOUBTFUL", "NOT WITH TEAM"}

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_prediction_row, predict_pergame,
)
from src.prediction.prop_quantiles import (  # noqa: E402
    predict_pergame_quantiles,
)
from src.prediction.quantile_calibration import apply as apply_quantile_calibration  # noqa: E402
from src.data.injuries import load_unavailable_players  # noqa: E402
from src.data.lineups import (  # noqa: E402
    build_starter_index, classify_starter, STATUS_SCALE,
)


def _strip_accents(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _resolve_player_id(name: str):
    try:
        from nba_api.stats.static import players  # noqa: PLC0415
    except Exception:
        return None
    needle = _strip_accents(name).lower()
    cands = players.get_players()
    for p in cands:
        if _strip_accents(p["full_name"]).lower() == needle:
            return int(p["id"])
    for p in cands:
        if needle in _strip_accents(p["full_name"]).lower():
            return int(p["id"])
    return None


def _current_season() -> str:
    now = datetime.now()
    start = now.year if now.month >= 10 else now.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _american_to_implied_prob(odds: int) -> float:
    """-110 → 0.5238; +150 → 0.4 ; -150 → 0.6."""
    odds = int(odds)
    if odds > 0:
        return 100 / (odds + 100)
    return -odds / (-odds + 100)


def _american_payout(odds: int, stake: float = 1.0) -> float:
    """Profit on $stake bet given odds (NOT including stake return). -110 = 0.909."""
    odds = int(odds)
    if odds > 0:
        return stake * (odds / 100)
    return stake * (100 / -odds)


def _model_hit_prob(stat: str, point_pred: float, qint: dict, line: float, side: str) -> float:
    """Approximate the model's predicted probability of WINNING the side at the given line.

    Centers a normal distribution at the BLEND's point prediction and uses the
    CYCLE-40 CALIBRATED q90 - q10 spread to estimate sigma. Calibration brings
    each stat's interval to actually-80% coverage (raw was 71-91%) — without
    it the Kelly probability estimates are systematically off (PTS/AST under-
    cover means too-confident bets; STL/BLK over-cover means too-cautious).
    """
    q10 = qint.get("q10"); q50 = qint.get("q50"); q90 = qint.get("q90")
    if q10 is None or q90 is None or point_pred is None:
        return None
    cal_q10, cal_q90 = apply_quantile_calibration(stat, q10, q50 or point_pred, q90)
    sigma = max((cal_q90 - cal_q10) / (2 * 1.2816), 1e-6)
    from math import erf, sqrt
    z = (line - point_pred) / sigma
    cdf_at_line = 0.5 * (1 + erf(z / sqrt(2)))
    p_over = 1 - cdf_at_line
    return p_over if side == "OVER" else 1 - p_over


def _kelly_fraction(prob: float, odds: int) -> float:
    """Kelly fraction for a single bet. Returns 0 if no edge."""
    b = _american_payout(odds, 1.0)  # net odds per unit
    p = prob; q = 1 - p
    f = (b * p - q) / b
    return max(0.0, f)


def load_injury_unavailable(path: str) -> dict:
    """Cycle-51 wrapper kept for the existing test suite. Cycle 53 moved the
    implementation to src/data/injuries.load_unavailable_players() for reuse
    across compare_to_lines, predict_player, and predict_slate.
    """
    return load_unavailable_players(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="CSV file with prop lines")
    ap.add_argument("--min-edge", type=float, default=0.0,
                    help="Minimum |model - line| in stat units to show. Default 0.")
    ap.add_argument("--kelly", action="store_true", help="Also show Kelly fraction")
    ap.add_argument("--bankroll", type=float, default=1000.0,
                    help="Bankroll for Kelly stake sizing (default $1000)")
    ap.add_argument("--season", default=None)
    ap.add_argument("--injuries", nargs="?", const="__default__", default=None,
                    help="Skip players listed OUT/DOUBTFUL in the injury JSON. "
                         "Bare flag → data/injuries_<today>.json; with arg → that path.")
    ap.add_argument("--include-injured", action="store_true",
                    help="Override --injuries: include all players regardless of status.")
    ap.add_argument("--lineups", nargs="?", const="__default__", default=None,
                    help="Cycle 64. Skip players not classified starter/questionable in the "
                         "cycle-61 rotowire lineup JSON. Bare flag → data/lineups_<today>.json.")
    ap.add_argument("--scale-by-status", action="store_true",
                    help="Cycle 67. Scale model_pred + q10/q90 by the lineup classification "
                         "(questionable*0.75) before computing edge / EV. Requires --lineups.")
    args = ap.parse_args()

    inj_unavail: dict = {}
    if args.injuries is not None and not args.include_injured:
        inj_path = (os.path.join(PROJECT_DIR, "data",
                                  f"injuries_{_date.today().isoformat()}.json")
                    if args.injuries == "__default__" else args.injuries)
        inj_unavail = load_injury_unavailable(inj_path)
        print(f"  [injuries] loaded {len(inj_unavail)} unavailable player(s) from "
              f"{os.path.basename(inj_path)}")

    starter_idx: dict = {}
    if args.lineups is not None:
        lu_path = (os.path.join(PROJECT_DIR, "data",
                                  f"lineups_{_date.today().isoformat()}.json")
                    if args.lineups == "__default__" else args.lineups)
        starter_idx = build_starter_index(lu_path)
        print(f"  [lineups] loaded {len(starter_idx)} starter(s) from "
              f"{os.path.basename(lu_path)}")

    season_default = args.season or _current_season()
    gamelog_dir = os.path.join(PROJECT_DIR, "data", "nba")
    model_dir   = os.path.join(PROJECT_DIR, "data", "models")

    rows_in = []
    with open(args.csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows_in.append({k.strip().lower(): v.strip() for k, v in r.items()})
    if not rows_in:
        print("[fail] empty CSV"); sys.exit(1)

    results = []
    skipped_inj = []
    skipped_lu = []
    for r in rows_in:
        name = r.get("player", ""); opp = r.get("opp", "").upper()
        venue = r.get("venue", "home").lower(); stat = r.get("stat", "").lower()
        try:
            line = float(r.get("line", "nan"))
        except ValueError:
            line = float("nan")
        if not (name and opp and stat in STATS and not np.isnan(line)):
            print(f"  [skip] bad row: {r}"); continue
        if inj_unavail:
            key = _strip_accents(name).lower()
            if key in inj_unavail:
                skipped_inj.append((name, inj_unavail[key]))
                continue
        if starter_idx:
            cls = classify_starter(name, starter_idx)
            if cls in ("bench", "no-game"):
                skipped_lu.append((name, cls))
                continue
        rest_days = float(r.get("rest_days") or 2.0)
        season = r.get("season") or season_default
        is_home = (venue.startswith("h"))
        over_odds = int(r.get("over_odds") or -110)
        under_odds = int(r.get("under_odds") or -110)

        pid = _resolve_player_id(name)
        if pid is None:
            print(f"  [skip] cannot resolve player '{name}'"); continue
        prow = build_prediction_row(pid, opp, season, is_home=is_home,
                                    rest_days=rest_days, gamelog_dir=gamelog_dir)
        if prow is None:
            print(f"  [skip] no gamelog for {name} season={season}"); continue
        model_pred = predict_pergame(stat, prow, model_dir)
        qint = predict_pergame_quantiles(stat, prow, model_dir)
        if model_pred is None or qint is None:
            print(f"  [skip] {name} {stat}: no model output"); continue
        # Cycle 67: scale by lineup classification before EV math.
        if args.scale_by_status and starter_idx:
            cls = classify_starter(name, starter_idx)
            factor = STATUS_SCALE.get(cls, 1.0)
            if factor != 1.0:
                model_pred = round(float(model_pred) * factor, 2)
                qint = {k: (round(float(v) * factor, 2)
                            if isinstance(v, (int, float)) else v)
                        for k, v in qint.items()}
        edge = model_pred - line
        if abs(edge) < args.min_edge:
            continue
        side = "OVER" if edge > 0 else "UNDER"
        odds = over_odds if side == "OVER" else under_odds
        prob = _model_hit_prob(stat, model_pred, qint, line, side)
        net_payout = _american_payout(odds, 1.0)
        ev_per_dollar = prob * net_payout - (1 - prob) * 1.0 if prob is not None else 0.0
        kf = _kelly_fraction(prob, odds) if prob is not None else 0.0

        results.append({
            "player": name, "stat": stat.upper(), "line": line,
            "model": round(model_pred, 2), "edge": round(edge, 2),
            "side": side, "prob": round(prob, 3) if prob else None,
            "odds": odds, "ev": round(ev_per_dollar, 4),
            "kelly_pct": round(kf * 100, 2),
            "kelly_stake": round(kf * args.bankroll, 2),
        })

    if skipped_inj:
        print(f"\n  [injuries] skipped {len(skipped_inj)} line(s) for OUT/DOUBTFUL players:")
        # De-duplicate (a player has multiple lines) before printing.
        seen = set()
        for n, s in skipped_inj:
            if n in seen:
                continue
            seen.add(n)
            print(f"    - {n} ({s})")
    if skipped_lu:
        print(f"\n  [lineups] skipped {len(skipped_lu)} line(s) for non-starters:")
        seen = set()
        for n, c in skipped_lu:
            if n in seen:
                continue
            seen.add(n)
            print(f"    - {n} ({c})")

    if not results:
        print("[done] no bets passed --min-edge filter"); return

    # Sort by EV descending
    results.sort(key=lambda x: x["ev"], reverse=True)
    print(f"\n  {'player':<22s} {'stat':4s} {'line':>5s}  {'model':>5s} {'edge':>6s}  {'side':5s}  {'prob':>5s}  {'odds':>5s}  {'EV/$':>7s}  {'Kelly%':>7s}")
    print(f"  {'-'*22} {'-'*4} {'-'*5}  {'-'*5} {'-'*6}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*7}  {'-'*7}")
    for r in results:
        pr = f"{r['prob']:.3f}" if r['prob'] is not None else "  —  "
        print(f"  {r['player']:<22s} {r['stat']:4s} {r['line']:>5.1f}  {r['model']:>5.2f} {r['edge']:>+6.2f}  {r['side']:5s}  {pr:>5s}  {r['odds']:>+5d}  {r['ev']:>+7.4f}  {r['kelly_pct']:>6.2f}%")
    if args.kelly:
        total_stake = sum(r["kelly_stake"] for r in results)
        print(f"\n  Total Kelly stake on positive-EV bets: ${total_stake:.2f} of ${args.bankroll:.2f} bankroll")


if __name__ == "__main__":
    main()
