"""backtest_closing_lines_2024_playoffs.py — honest backtest vs REAL closing lines.

Replaces the cycle-30 L5-proxy backtest with a real closing-line test against
the 2024 NBA playoffs (n=5108 player-stat rows, April-May 2024).

Pipeline per CSV row:
    (player_name, date, stat) -> resolve player_id (nba_api static, accent-aware)
                              -> filter gamelog to games strictly < date
                              -> build leak-free prediction row (as-of)
                              -> call prop_pergame.predict_pergame(stat, row)
                              -> compare to closing_line + actual_value
                              -> derive bet_recommendation @ |edge| > 0.5 unit
                              -> tally hit rate, MAE, ROI @ -110

Outputs per-stat hit rate / MAE / ROI table and an overall pool result.
Saves report to vault/Reports/closing_line_backtest_2024_playoffs.md if dir exists.

Leak caveat: prop_pergame q50 + blend models on disk were trained on data that
INCLUDES the 2024 playoff window — see vault Improvements log. This is a soft
backtest (in-sample), not a true OOS validation. The MAE here is therefore an
optimistic upper bound; closing-line hit rate is closer to the OOS truth (the
sportsbook line is independent of our model).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Cycle 92d note: cap retro fetches by disabling injury wire — playoff CSV
# already encodes availability via actual_value (DNPs are simply absent rows).
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from src.prediction.prop_pergame import (  # noqa: E402
    STATS,
    _MIN_PLAYED,
    _REST_TRAVEL_DEFAULTS,
    _PLAYTYPE_DEFAULTS,
    _BBREF_DEFAULTS,
    _CONTRACT_DEFAULTS,
    _REB_CONTEXT_DEFAULTS,
    _SYN_PPP_DEFAULTS,
    _ITER23_DEFAULTS,
    _row_features,
    _num,
    _parse_date,
    _prior_season,
    _get_opponent_defense,
    _get_playtypes,
    _get_bbref,
    _get_contracts,
    _get_team_reb_context,
    _get_pregame_spreads,
    _get_syn_ppp,
    _inject_iter23_features,
    _PLAYTYPE_PRIOR_SEASON_JOIN,
    predict_pergame,
)


# ───────────────────────────────────────────────────────────── helpers ──────

def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


_PLAYERS_INDEX: Optional[List[dict]] = None


def _players_index() -> List[dict]:
    """Cached nba_api static players list — loaded once."""
    global _PLAYERS_INDEX
    if _PLAYERS_INDEX is None:
        try:
            from nba_api.stats.static import players  # noqa: PLC0415
            _PLAYERS_INDEX = players.get_players()
        except Exception as e:
            print(f"  [warn] nba_api unavailable: {e}")
            _PLAYERS_INDEX = []
    return _PLAYERS_INDEX


def _resolve_player_id(name: str) -> Optional[int]:
    """Diacritic-insensitive nba_api name -> id resolver. Fuzzy substring fallback."""
    cands = _players_index()
    if not cands:
        return None
    needle = _strip_accents(name).lower().strip()
    for p in cands:
        if _strip_accents(p["full_name"]).lower() == needle:
            return int(p["id"])
    # Substring fallback (covers 'Jr.', 'Sr.', middle-name variants).
    for p in cands:
        if needle in _strip_accents(p["full_name"]).lower():
            return int(p["id"])
    # Last-name only fallback for 1-token CSV names.
    if " " not in needle:
        for p in cands:
            ln = _strip_accents(p["full_name"]).lower().split()[-1]
            if ln == needle:
                return int(p["id"])
    return None


def _season_for_date(d: datetime) -> str:
    """Map an ISO date to NBA season string. Apr-May => the season that started prior fall."""
    if d.month >= 10:
        start = d.year
    else:
        start = d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _load_filtered_gamelog(player_id: int, season: str, asof_date: datetime,
                           gamelog_dir: str) -> Optional[List[dict]]:
    """Return prior_played games strictly before asof_date.

    Falls back across two seasons (current + prior) when asof is early in the
    season. Returns None if no gamelog file exists at all for the player."""
    rows: List[dict] = []
    found_any = False
    for try_season in (season, _prior_season(season)):
        p = os.path.join(gamelog_dir, f"gamelog_{player_id}_{try_season}.json")
        if not os.path.exists(p):
            continue
        found_any = True
        try:
            games = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list):
            continue
        rows.extend(games)
    if not found_any:
        return None
    # Filter strictly before asof
    out: List[Tuple[datetime, dict]] = []
    for g in rows:
        gd = _parse_date(g.get("GAME_DATE"))
        if gd is None or gd >= asof_date:
            continue
        out.append((gd, g))
    out.sort(key=lambda x: x[0])
    return [g for _d, g in out if _num(g.get("MIN")) >= _MIN_PLAYED]


def _build_asof_row(player_id: int, opp_team: str, asof_date: datetime,
                    season: str, *, is_home: bool, rest_days: float,
                    gamelog_dir: str) -> Optional[Dict[str, float]]:
    """Build a leak-free feature row strictly using prior games < asof_date.

    Mirrors prop_pergame.build_prediction_row but takes an explicit asof_date
    so the join/factor lookups all use the historical game date (not the
    player's last-cached game date).
    """
    prior_played = _load_filtered_gamelog(player_id, season, asof_date, gamelog_dir)
    if prior_played is None or not prior_played:
        return None

    feats = _row_features(prior_played, float(rest_days), int(is_home),
                          len(prior_played))
    # Opponent defence — strictly-to-asof_date via the process-cached defense.
    feats.update(_get_opponent_defense(gamelog_dir).factors(opp_team, asof_date))
    feats.update(_REST_TRAVEL_DEFAULTS)
    # Play-type frequencies (prior-season join per R10_M14).
    try:
        pt_season = _prior_season(season) if _PLAYTYPE_PRIOR_SEASON_JOIN else season
        feats.update(_get_playtypes().features(int(player_id), pt_season))
    except Exception:
        feats.update(_PLAYTYPE_DEFAULTS)
    try:
        feats.update(_get_bbref().features(int(player_id), season))
    except Exception:
        feats.update(_BBREF_DEFAULTS)
    try:
        feats.update(_get_contracts().features(int(player_id), season))
    except Exception:
        feats.update(_CONTRACT_DEFAULTS)
    # REB OREB-context: derive team_abbrev from most-recent prior game.
    try:
        last_matchup = str(prior_played[-1].get("MATCHUP", "")) if prior_played else ""
        team_abbrev = last_matchup.split()[0] if last_matchup.split() else ""
        feats.update(_get_team_reb_context().features(
            team_abbrev, opp_team, asof_date))
    except Exception:
        feats.update(_REB_CONTEXT_DEFAULTS)
    # Iter-44: synergy PPP per-play-type (current-season join, 5 keys).
    try:
        feats.update(_get_syn_ppp().features(int(player_id), season))
    except Exception:
        feats.update(_SYN_PPP_DEFAULTS)
    # Pre-game spread (defaults to None when absent => garbage-time haircut no-op).
    try:
        last_matchup = str(prior_played[-1].get("MATCHUP", "")) if prior_played else ""
        team_abbrev = last_matchup.split()[0] if last_matchup.split() else ""
        if is_home:
            sp_home, sp_away, sign = team_abbrev, opp_team, 1.0
        else:
            sp_home, sp_away, sign = opp_team, team_abbrev, -1.0
        sp_feats = _get_pregame_spreads().features(sp_home, sp_away, asof_date)
        hs = sp_feats.get("home_spread")
        feats["home_spread"] = (sign * float(hs)) if hs is not None else None
        feats["total"] = sp_feats.get("total")
    except Exception:
        feats["home_spread"] = None
        feats["total"] = None
    # Iter-7: inject the 39 Iter-2/3 features that were constant-zero at
    # inference (present in training via build_pergame_dataset, missing here).
    # team_abbrev derived from most-recent prior game's MATCHUP string.
    try:
        last_matchup = str(prior_played[-1].get("MATCHUP", "")) if prior_played else ""
        _team_abbrev_inj = last_matchup.split()[0] if last_matchup.split() else ""
        _inject_iter23_features(feats, int(player_id), asof_date, _team_abbrev_inj)
    except Exception:
        feats.update(_ITER23_DEFAULTS)
    return feats


# ───────────────────────────────────────────────────── backtest engine ──────

def _classify_result(actual: float, line: float) -> str:
    if abs(actual - line) < 1e-9:
        return "PUSH"
    return "OVER" if actual > line else "UNDER"


def _recommend(edge: float, threshold: float) -> str:
    if edge > threshold:
        return "OVER"
    if edge < -threshold:
        return "UNDER"
    return "NO_BET"


def _odds_to_decimal_profit(odds: int) -> float:
    """American odds -> profit per $1 risked on a win. -110 => 0.909."""
    if odds < 0:
        return 100.0 / abs(odds)
    return odds / 100.0


def run_backtest(csv_path: str, gamelog_dir: str, threshold: float = 0.5,
                 max_rows: Optional[int] = None,
                 verbose_preview: int = 10) -> dict:
    rows = []
    with open(csv_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)
    if max_rows:
        rows = rows[:max_rows]
    print(f"  Loaded {len(rows)} rows from {os.path.basename(csv_path)}")

    # Resolve player ids ONCE per unique name.
    unique_names = sorted({r["player"] for r in rows})
    name2pid: Dict[str, Optional[int]] = {}
    unresolved: List[str] = []
    for nm in unique_names:
        pid = _resolve_player_id(nm)
        name2pid[nm] = pid
        if pid is None:
            unresolved.append(nm)
    print(f"  Player name -> id resolution: {len(unique_names) - len(unresolved)}/{len(unique_names)} resolved ({len(unresolved)} unresolved)")
    if unresolved[:5]:
        print(f"    unresolved sample: {unresolved[:5]}")

    # Cache as-of feature rows per (player_id, date, venue, opp) to avoid 6x recompute per stat.
    row_cache: Dict[Tuple[int, str, str, str], Optional[Dict[str, float]]] = {}

    per_stat = defaultdict(lambda: {
        "n_pred": 0, "n_skip": 0,
        "abs_err_actual": [], "abs_err_line": [],
        "n_bets": 0, "wins": 0, "losses": 0, "pushes": 0,
    })
    overall_skip_reasons = defaultdict(int)
    preview_rows: List[Tuple[str, str, str, float, float, float]] = []

    t0 = time.time()
    for idx, r in enumerate(rows):
        player = r["player"]
        opp = r["opp"]
        venue = r["venue"]  # "home" / "away"
        stat = r["stat"].lower()
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            over_odds = int(r.get("over_odds", -110))
            under_odds = int(r.get("under_odds", -110))
        except (TypeError, ValueError):
            per_stat[stat]["n_skip"] += 1
            overall_skip_reasons["bad_numeric"] += 1
            continue
        try:
            d = datetime.fromisoformat(r["date"])
        except Exception:
            per_stat[stat]["n_skip"] += 1
            overall_skip_reasons["bad_date"] += 1
            continue
        pid = name2pid.get(player)
        if pid is None:
            per_stat[stat]["n_skip"] += 1
            overall_skip_reasons["no_pid"] += 1
            continue

        season = _season_for_date(d)
        is_home = (venue == "home")
        key = (pid, r["date"], venue, opp)
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, opp, d, season, is_home=is_home, rest_days=2.0,
                gamelog_dir=gamelog_dir,
            )
        feat_row = row_cache[key]
        if feat_row is None:
            per_stat[stat]["n_skip"] += 1
            overall_skip_reasons["no_history"] += 1
            continue

        try:
            pred = predict_pergame(stat, feat_row)
        except Exception as e:
            per_stat[stat]["n_skip"] += 1
            overall_skip_reasons[f"predict_err:{type(e).__name__}"] += 1
            continue
        if pred is None:
            per_stat[stat]["n_skip"] += 1
            overall_skip_reasons["model_missing"] += 1
            continue
        pred = float(pred)

        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, threshold)

        s = per_stat[stat]
        s["n_pred"] += 1
        s["abs_err_actual"].append(abs(pred - actual))
        s["abs_err_line"].append(abs(pred - line))

        if rec != "NO_BET":
            if actual_result == "PUSH":
                s["pushes"] += 1
            else:
                s["n_bets"] += 1
                if rec == actual_result:
                    s["wins"] += 1
                else:
                    s["losses"] += 1

        if len(preview_rows) < verbose_preview:
            preview_rows.append((player, r["date"], stat, pred, line, actual))

        if (idx + 1) % 1000 == 0:
            elapsed = time.time() - t0
            print(f"  ...{idx+1}/{len(rows)} processed ({elapsed:.1f}s)")

    elapsed = time.time() - t0
    print(f"  Backtest finished in {elapsed:.1f}s")
    print(f"  Skip reasons: {dict(overall_skip_reasons)}")

    # Report
    print("\n  First 10 predictions (manual sanity check):")
    print(f"  {'player':22s} {'date':10s} {'stat':5s} {'pred':>6s} {'line':>6s} {'actual':>7s}")
    for (p, d, st, pr, ln, ac) in preview_rows:
        print(f"  {p[:22]:22s} {d:10s} {st:5s} {pr:6.2f} {ln:6.2f} {ac:7.2f}")

    # Per-stat metrics
    print("\n  Per-stat results:")
    header = f"  {'stat':4s} | {'n_pred':>6s} | {'n_skip':>6s} | {'MAE_act':>7s} | {'MAE_line':>8s} | {'n_bets':>6s} | {'hit%':>6s} | {'ROI':>7s}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    pooled_bets = pooled_wins = 0
    pooled_roi_units = 0.0
    out_rows = []
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]:
        s = per_stat.get(stat)
        if not s or s["n_pred"] == 0:
            continue
        mae_a = sum(s["abs_err_actual"]) / len(s["abs_err_actual"])
        mae_l = sum(s["abs_err_line"]) / len(s["abs_err_line"]) if s["abs_err_line"] else 0.0
        nb = s["n_bets"]
        w = s["wins"]
        hit = (w / nb) if nb else 0.0
        # ROI at -110: each win pays 0.909, each loss costs 1.0. Pushes drop out.
        profit_per_win = _odds_to_decimal_profit(-110)
        roi_units = w * profit_per_win - (nb - w) * 1.0
        roi_pct = (roi_units / nb * 100.0) if nb else 0.0
        pooled_bets += nb
        pooled_wins += w
        pooled_roi_units += roi_units
        print(f"  {stat.upper():4s} | {s['n_pred']:6d} | {s['n_skip']:6d} | {mae_a:7.3f} | {mae_l:8.3f} | {nb:6d} | {hit*100:5.1f}% | {roi_pct:6.2f}%")
        out_rows.append({
            "stat": stat, "n_pred": s["n_pred"], "n_skip": s["n_skip"],
            "mae_actual": mae_a, "mae_line": mae_l,
            "n_bets": nb, "wins": w, "hit_rate": hit,
            "roi_pct": roi_pct, "roi_units": roi_units,
        })

    pooled_hit = (pooled_wins / pooled_bets) if pooled_bets else 0.0
    pooled_roi_pct = (pooled_roi_units / pooled_bets * 100.0) if pooled_bets else 0.0
    print(f"\n  Overall: bets={pooled_bets}  hit_rate={pooled_hit*100:.2f}%  "
          f"ROI={pooled_roi_pct:+.2f}%  flat_$100_PnL=${pooled_roi_units*100:+.0f}")

    return {
        "n_rows": len(rows),
        "skip_reasons": dict(overall_skip_reasons),
        "per_stat": out_rows,
        "pooled": {
            "n_bets": pooled_bets,
            "wins": pooled_wins,
            "hit_rate": pooled_hit,
            "roi_pct": pooled_roi_pct,
            "roi_units": pooled_roi_units,
        },
        "preview": preview_rows,
    }


def save_report(result: dict, out_path: str, csv_path: str, threshold: float) -> None:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    p = result["pooled"]
    lines = []
    lines.append("# Closing-Line Backtest — 2024 NBA Playoffs (soft, in-sample)\n")
    lines.append(f"- Source: `{csv_path}`")
    lines.append(f"- Rows: {result['n_rows']}")
    lines.append(f"- Bet threshold: |edge| > {threshold} stat-unit")
    lines.append(f"- Bet pricing assumed: -110/-110 (CSV defaults)")
    lines.append("")
    lines.append("## Leak caveat")
    lines.append("Prop q50 + blend models on disk were trained on data that **includes**")
    lines.append("the April-May 2024 window. MAE-vs-actual here is therefore optimistic")
    lines.append("(in-sample). Closing-line hit rate is the honest signal — the line")
    lines.append("itself is independent of the model.")
    lines.append("")
    lines.append("## Per-stat results")
    lines.append("| stat | n_pred | n_skip | MAE_actual | MAE_line | n_bets | hit% | ROI |")
    lines.append("|------|-------:|-------:|----------:|---------:|------:|-----:|----:|")
    for r in result["per_stat"]:
        lines.append(
            f"| {r['stat'].upper()} | {r['n_pred']} | {r['n_skip']} | "
            f"{r['mae_actual']:.3f} | {r['mae_line']:.3f} | {r['n_bets']} | "
            f"{r['hit_rate']*100:.2f}% | {r['roi_pct']:+.2f}% |"
        )
    lines.append("")
    lines.append("## Overall")
    lines.append(f"- bets: {p['n_bets']}")
    lines.append(f"- wins: {p['wins']}")
    lines.append(f"- hit rate: {p['hit_rate']*100:.2f}%")
    lines.append(f"- ROI: {p['roi_pct']:+.2f}%")
    lines.append(f"- flat $100/bet PnL: ${p['roi_units']*100:+.0f}")
    lines.append("")
    lines.append("## Skip reasons")
    for k, v in sorted(result["skip_reasons"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{k}`: {v}")
    lines.append("")
    lines.append("## Preview (first 10)")
    lines.append("| player | date | stat | pred | line | actual |")
    lines.append("|--------|------|------|-----:|-----:|------:|")
    for (p_, d_, st_, pr_, ln_, ac_) in result["preview"]:
        lines.append(f"| {p_} | {d_} | {st_} | {pr_:.2f} | {ln_:.2f} | {ac_:.2f} |")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\n  Report saved -> {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(
        PROJECT_DIR, "data", "external", "historical_lines",
        "playoffs_2024_canonical.csv"))
    ap.add_argument("--gamelog-dir", default=os.path.join(PROJECT_DIR, "data", "nba"))
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="|edge| threshold for bet recommendation (in stat units).")
    ap.add_argument("--max-rows", type=int, default=None,
                    help="Cap rows for a quick test (default: all 5108)")
    ap.add_argument("--report", default=os.path.join(
        PROJECT_DIR, "vault", "Reports",
        "closing_line_backtest_2024_playoffs.md"))
    args = ap.parse_args()

    print(f"\n  csv          : {args.csv}")
    print(f"  gamelog dir  : {args.gamelog_dir}")
    print(f"  threshold    : {args.threshold}")
    print(f"  max_rows     : {args.max_rows or 'ALL'}\n")

    result = run_backtest(args.csv, args.gamelog_dir, args.threshold,
                          max_rows=args.max_rows)

    if os.path.isdir(os.path.dirname(args.report)):
        save_report(result, args.report, args.csv, args.threshold)
    else:
        print(f"\n  [skip-report] {os.path.dirname(args.report)} does not exist; printing only.")


if __name__ == "__main__":
    main()
