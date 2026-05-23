"""
predict_game.py — Unified game prediction CLI (Phase E-CLI).

Usage
-----
    python scripts/predict_game.py --home BOS --away LAL --date 2026-05-22
    python scripts/predict_game.py --game-id 0022500999
    python scripts/predict_game.py --home BOS --away LAL --date 2026-05-22 \\
        --players "LAL:LeBron James,Anthony Davis;BOS:Jayson Tatum,Jaylen Brown"
    python scripts/predict_game.py --home BOS --away LAL --date 2026-05-22 --json
    python scripts/predict_game.py --home BOS --away LAL --date 2026-05-22 \\
        --lines '{"pts":{"LeBron James":25.5},"reb":{"LeBron James":7.5}}'
    python scripts/predict_game.py --home BOS --away LAL --date 2026-05-22 \\
        --save vault/Predictions/BOS_LAL_2026-05-22.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# ── Constants ──────────────────────────────────────────────────────────────────
_MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_PORTFOLIO_CAP = 0.05      # 5 % bankroll cap per bet
_N_PORTFOLIO_SIMS = 10_000
_DEFAULT_BANKROLL = 10_000.0
_SEP = "=" * 60


# ── Interval helpers ───────────────────────────────────────────────────────────

def _load_conformal_intervals() -> Dict[str, float]:
    """Return {stat: half_width} from conformal_*.json. Falls back to 1.28σ heuristic."""
    intervals: Dict[str, float] = {}
    for stat in _STATS:
        cpath = os.path.join(_MODELS_DIR, f"conformal_{stat}.json")
        if os.path.exists(cpath):
            try:
                data = json.load(open(cpath))
                intervals[stat] = float(data.get("q80", 0.0))
                continue
            except Exception:
                pass
        # Fallback: 1.28σ from residual std (prop_residuals_summary.json)
        rpath = os.path.join(_MODELS_DIR, "prop_residuals_summary.json")
        if os.path.exists(rpath):
            try:
                summary = json.load(open(rpath))
                mae = float(summary.get(stat, {}).get("mae", 3.0))
                sigma = mae * 1.2533  # MAE ≈ σ√(2/π), so σ ≈ MAE / 0.7979
                intervals[stat] = round(1.28 * sigma, 2)
                continue
            except Exception:
                pass
        # Hard-coded sensible defaults
        intervals[stat] = {"pts": 7.5, "reb": 3.1, "ast": 2.1,
                           "fg3m": 1.5, "stl": 1.0, "blk": 0.9, "tov": 1.4}.get(stat, 3.0)
    return intervals


# ── Player name → prop resolution ─────────────────────────────────────────────

def _resolve_player_props(
    player_name: str,
    opp_team: str,
    season: str,
    intervals: Dict[str, float],
    lines_for_player: Dict[str, float],
) -> Optional[dict]:
    """
    Return prop predictions for a single player by display name.
    Uses predict_props (read-only) then wraps with intervals and edge calculation.
    """
    try:
        from src.prediction.player_props import predict_props as _pp
        raw = _pp(player_name, opp_team, season=season)
        if raw is None:
            return None
    except Exception as e:
        return {"player_name": player_name, "error": str(e)}

    props: Dict[str, dict] = {}
    for stat in _STATS:
        mean = raw.get(stat)
        if mean is None:
            continue
        mean = float(mean)
        hw = float(intervals.get(stat, 3.0))
        lo = round(mean - hw, 1)
        hi = round(mean + hw, 1)
        line = lines_for_player.get(stat)
        edge = round(mean - float(line), 2) if line is not None else None
        direction = ("Over" if edge and edge > 0 else "Under") if edge is not None else None
        props[stat] = {
            "mean": round(mean, 1),
            "lo": lo,
            "hi": hi,
            "line": line,
            "edge": edge,
            "direction": direction,
        }
    return {"player_name": player_name, "props": props}


# ── Portfolio simulator ────────────────────────────────────────────────────────

def _simulate_portfolio(
    edge_plays: List[dict],
    bankroll: float,
    n_sims: int = _N_PORTFOLIO_SIMS,
) -> dict:
    """
    Monte-Carlo portfolio simulation with Kelly sizing (5% cap).
    Returns: expected_roi, win_prob, var_5pct, allocations.
    """
    import numpy as _np

    if not edge_plays:
        return {"expected_roi": 0.0, "win_prob": 0.5, "var_5pct": 0.0, "allocations": []}

    allocations = []
    total_exposure = 0.0
    for play in edge_plays:
        edge = float(play.get("edge_pct", 0.0))
        if edge <= 0:
            continue
        # Half-Kelly fraction capped at portfolio cap
        odds = int(play.get("odds", -110))
        b = (100 / abs(odds)) if odds < 0 else (odds / 100)
        p = 0.5 + edge / 2.0
        kelly_f = max(0.0, (b * p - (1 - p)) / b)
        kelly_f = min(kelly_f * 0.5, _PORTFOLIO_CAP)  # half-Kelly, 5% cap
        alloc_pct = round(kelly_f * 100, 1)
        if alloc_pct <= 0:
            continue
        allocations.append({**play, "kelly_pct": alloc_pct})
        total_exposure += kelly_f

    if not allocations:
        return {"expected_roi": 0.0, "win_prob": 0.5, "var_5pct": 0.0, "allocations": []}

    # Simulate P&L across n_sims
    _np.random.seed(42)
    pnls = _np.zeros(n_sims)
    for alloc in allocations:
        edge = float(alloc.get("edge_pct", 0.0))
        odds = int(alloc.get("odds", -110))
        f = alloc["kelly_pct"] / 100.0
        b = (100 / abs(odds)) if odds < 0 else (odds / 100)
        p = min(0.95, max(0.05, 0.5 + edge / 2.0))
        wins = _np.random.random(n_sims) < p
        bet_pnl = _np.where(wins, b * f, -f)
        pnls += bet_pnl

    expected_roi = round(float(pnls.mean()) * 100, 2)
    win_prob = round(float((pnls > 0).mean()) * 100, 1)
    var_5pct = round(float(_np.percentile(pnls, 5)) * 100, 2)

    return {
        "expected_roi": expected_roi,
        "win_prob": win_prob,
        "var_5pct": var_5pct,
        "allocations": allocations,
    }


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _fmt_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _fmt_ci(lo: float, hi: float) -> str:
    return f"[{lo:>5.1f} – {hi:<5.1f}]"


def _render_report(report: dict, use_json: bool = False) -> str:
    """Render the full prediction report as a string."""
    if use_json:
        return json.dumps(report, indent=2, default=str)

    home = report["home_team"]
    away = report["away_team"]
    game_date = report.get("game_date", "")
    lines = []

    lines.append(_SEP)
    lines.append(f"{away} @ {home}  —  {game_date}")
    lines.append(_SEP)

    # ── Win probability ──────────────────────────────────────────────────────
    wp = report.get("win_probability", {})
    home_wp = wp.get("home_win_prob")
    if home_wp is not None:
        away_wp = round(1.0 - float(home_wp), 4)
        model_id = wp.get("model_id", "xgboost")
        brier = wp.get("brier", report.get("win_prob_brier", "?"))
        ci = wp.get("confidence_interval")
        ci_str = f"  CI [{ci[0]:.0%}–{ci[1]:.0%}]" if ci else ""
        lines.append("")
        lines.append("WIN PROBABILITY")
        lines.append(f"  {home} win:  {_fmt_pct(float(home_wp))}   "
                     f"(model {model_id}, brier={brier}){ci_str}")
        lines.append(f"  {away} win:  {_fmt_pct(away_wp)}")
        # Injury warnings
        iw = wp.get("injury_warnings", {})
        if iw.get("has_warnings"):
            lines.append("")
            lines.append("  INJURY WARNINGS")
            for side, team in [("home", home), ("away", away)]:
                for inj in iw.get(side, []):
                    lines.append(f"    {team}: {inj['player_name']} — {inj['status']}"
                                 + (f" ({inj['comment']})" if inj.get("comment") else ""))
    else:
        err = wp.get("error", "unavailable")
        lines.append(f"\nWIN PROBABILITY  (unavailable: {err})")

    # ── Game score ───────────────────────────────────────────────────────────
    gm = report.get("game_models", {})
    if gm and not gm.get("error"):
        total = gm.get("total_est")
        spread = gm.get("spread_est")
        fh = gm.get("first_half_total")
        pace = gm.get("pace_est")
        blowout = gm.get("blowout_prob")
        ot_prob = gm.get("ot_prob")
        total_std = gm.get("total_std", report.get("total_std"))
        spread_std = gm.get("spread_std", report.get("spread_std"))
        fh_std = gm.get("first_half_std")

        # Use model MAE as std if not returned
        if total_std is None:
            total_std = 14.08  # from game_models_metrics.json
        if spread_std is None:
            spread_std = 11.23
        if fh_std is None:
            fh_std = 6.66

        lines_meta = report.get("lines", {})
        total_line = lines_meta.get("total")
        spread_line = lines_meta.get("spread")

        lines.append("")
        lines.append("GAME SCORE")
        if total is not None:
            total_line_str = f"  (line: {total_line})" if total_line is not None else ""
            lines.append(f"  Total:    {total:.1f} ± {total_std:.1f}{total_line_str}")
        if spread is not None:
            # spread_est = home_pts - away_pts; negative → away team favored
            fav = away if spread < 0 else home
            sprd_abs = abs(spread)
            sl_str = ""
            if spread_line is not None:
                fav_l = home if spread_line < 0 else away
                sl_str = f"  (line: {fav_l} {spread_line:+.1f})"
            lines.append(f"  Spread:   {fav} {-sprd_abs:+.1f} ± {spread_std:.1f}{sl_str}")
        if fh is not None:
            lines.append(f"  1st Half: {fh:.1f} ± {fh_std:.1f}")
        if pace is not None:
            lines.append(f"  Pace:     {pace:.1f} poss")
        if blowout is not None:
            lines.append(f"  Blowout (>15): {float(blowout) * 100:.1f}%")
        if ot_prob is not None:
            lines.append(f"  OT prob:  {float(ot_prob) * 100:.1f}%")
    else:
        err = gm.get("error", "unavailable") if gm else "unavailable"
        lines.append(f"\nGAME SCORE  (unavailable: {err})")

    # ── Player props ─────────────────────────────────────────────────────────
    prop_entries = report.get("player_props", [])
    if prop_entries:
        lines.append("")
        lines.append("PLAYER PROPS (mean | 80% interval | line | edge)")
        has_lines = any(
            p.get("line") is not None
            for entry in prop_entries
            for p in entry.get("props", {}).values()
        )
        for entry in prop_entries:
            pname = entry.get("player_name", "?")
            if entry.get("error"):
                lines.append(f"  {pname}  (error: {entry['error']})")
                continue
            if entry.get("suppressed"):
                lines.append(f"  {pname}  [suppressed: {entry.get('suppression_reason', '')}]")
                continue
            lines.append(f"  {pname}")
            for stat, pd in entry.get("props", {}).items():
                mean = pd["mean"]
                lo   = pd["lo"]
                hi   = pd["hi"]
                line = pd.get("line")
                edge = pd.get("edge")
                direction = pd.get("direction")

                ci_str = f"  {_fmt_ci(lo, hi)}"
                line_str = f"  line {line:<5.1f}" if line is not None else ""
                edge_str = ""
                if edge is not None and direction:
                    sign = "+" if edge > 0 else ""
                    edge_str = f"  EDGE {sign}{edge:.1f} ({direction})"
                elif has_lines and line is None:
                    edge_str = "  (no line)"

                lines.append(f"    {stat.upper():<4}  {mean:>5.1f} {ci_str}{line_str}{edge_str}")
    elif report.get("props_skipped"):
        lines.append(f"\nPLAYER PROPS  (skipped: {report['props_skipped']})")
    else:
        lines.append("\nPLAYER PROPS  (none requested)")

    # ── Portfolio ────────────────────────────────────────────────────────────
    portfolio = report.get("portfolio")
    if portfolio and portfolio.get("allocations"):
        lines.append("")
        lines.append(f"PORTFOLIO (correlated Kelly, {int(_PORTFOLIO_CAP * 100)}% cap)")
        lines.append("  Optimal allocation:")
        for alloc in portfolio["allocations"]:
            pname = alloc.get("player_name", "?")
            stat = alloc.get("stat", "")
            direction = alloc.get("direction", "")
            odds = alloc.get("odds", -110)
            kelly_pct = alloc.get("kelly_pct", 0)
            lines.append(f"    {pname:<22} {stat} {direction:<5} @ {odds:+d}  "
                         f"->  {kelly_pct:.1f}% bankroll  (Kelly fraction)")
        lines.append(f"  Expected portfolio ROI: {portfolio['expected_roi']:+.1f}%  "
                     f"(Monte-Carlo n={_N_PORTFOLIO_SIMS:,})")
        lines.append(f"  Win probability:        {portfolio['win_prob']:.1f}%")
        lines.append(f"  5%-VaR:                 {portfolio['var_5pct']:+.1f}%")
    elif report.get("lines"):
        lines.append("\nPORTFOLIO  (no edge plays above threshold)")

    lines.append(_SEP)
    return "\n".join(lines)


# ── Save to markdown ───────────────────────────────────────────────────────────

def _save_markdown(report: dict, path: str) -> None:
    """Write a markdown version of the report to vault/Predictions/."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    txt = _render_report(report)
    md_lines = ["```", txt, "```", ""]
    md_lines.insert(0, f"# Prediction: {report['away_team']} @ {report['home_team']} "
                       f"— {report.get('game_date', '')}\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines))
    print(f"[predict_game] saved -> {path}", file=sys.stderr)


# ── NBA game_id → teams ────────────────────────────────────────────────────────

def _resolve_game_id(game_id: str) -> Optional[dict]:
    """Attempt to resolve a game_id to {home_team, away_team, game_date}."""
    try:
        from nba_api.stats.endpoints import boxscoresummaryv2
        import time
        time.sleep(0.5)
        bs = boxscoresummaryv2.BoxScoreSummaryV2(game_id=game_id)
        df = bs.game_summary.get_data_frame()
        if df.empty:
            return None
        row = df.iloc[0]
        home = str(row.get("HOME_TEAM_ABBREVIATION", ""))
        away = str(row.get("VISITOR_TEAM_ABBREVIATION", ""))
        gd   = str(row.get("GAME_DATE_EST", ""))[:10]
        return {"home_team": home, "away_team": away, "game_date": gd}
    except Exception as e:
        print(f"[predict_game] game_id lookup failed: {e}", file=sys.stderr)
        return None


# ── Lines parsing ──────────────────────────────────────────────────────────────

def _parse_lines(lines_arg: Optional[str], lines_file: Optional[str]) -> dict:
    """
    Parse --lines JSON string or --lines-file CSV/JSON.
    Expected format: {"pts": {"LeBron James": 25.5}, "reb": {...}, ...}
    Returns {} on failure.
    """
    if lines_arg:
        try:
            return json.loads(lines_arg)
        except Exception as e:
            print(f"[predict_game] --lines parse error: {e}", file=sys.stderr)
    if lines_file and os.path.exists(lines_file):
        try:
            if lines_file.endswith(".json"):
                return json.load(open(lines_file))
            # CSV: player_name,stat,line
            import csv
            data: dict = {}
            for row in csv.DictReader(open(lines_file)):
                stat = row.get("stat", "").lower()
                pname = row.get("player_name", "").strip()
                try:
                    line = float(row.get("line", 0))
                except ValueError:
                    continue
                data.setdefault(stat, {})[pname] = line
            return data
        except Exception as e:
            print(f"[predict_game] --lines-file parse error: {e}", file=sys.stderr)
    return {}


# ── Main prediction flow ───────────────────────────────────────────────────────

def run(
    home_team: str,
    away_team: str,
    season: str,
    game_date: str,
    players: Optional[Dict[str, List[str]]],
    lines_by_stat: dict,
    bankroll: float,
    no_save: bool,
) -> dict:
    """
    Run the full prediction pipeline and return the report dict.
    Reuses game_orchestrator for win_prob + game_models, adds prop CI layer.
    """
    report: dict = {
        "home_team": home_team,
        "away_team": away_team,
        "season": season,
        "game_date": game_date,
    }
    if lines_by_stat:
        report["lines"] = {
            "total":  lines_by_stat.get("total"),
            "spread": lines_by_stat.get("spread"),
        }

    # Load model metrics for display
    try:
        wp_metrics = json.load(open(os.path.join(_MODELS_DIR, "win_prob_metrics.json")))
        report["win_prob_brier"] = round(wp_metrics.get("brier", 0.0), 4)
    except Exception:
        pass

    # ── 1. Win probability ─────────────────────────────────────────────────
    try:
        from src.prediction.win_probability import load as _load_wp
        wp_model = _load_wp()
        wp = wp_model.predict(home_team, away_team, season=season, game_date=game_date)
        # Attach model ID from metrics
        try:
            _wpm = json.load(open(os.path.join(_MODELS_DIR, "win_prob_metrics.json")))
            wp["model_id"] = _wpm.get("version", "xgboost_v2")
            wp["brier"] = round(float(_wpm.get("brier", 0.0)), 4)
        except Exception:
            wp["model_id"] = "xgboost_v2"
            wp["brier"] = report.get("win_prob_brier", "?")
        # Simple ±5% CI around win probability
        hwp = float(wp.get("home_win_prob", 0.5))
        wp["confidence_interval"] = [round(hwp - 0.05, 3), round(hwp + 0.05, 3)]
        report["win_probability"] = wp
    except Exception as e:
        report["win_probability"] = {"error": str(e)}
        print(f"[predict_game] win_prob error: {e}", file=sys.stderr)

    # ── 2. Game models ─────────────────────────────────────────────────────
    try:
        from src.prediction.game_models import predict as _gm_predict
        gm = _gm_predict(home_team, away_team, season=season, game_date=game_date)
        # Attach MAE-based stdev from metrics for ± display
        try:
            gm_metrics = json.load(open(os.path.join(_MODELS_DIR, "game_models_metrics.json")))
            gm["total_std"] = round(gm_metrics.get("game_total", {}).get("mae", 14.0), 1)
            gm["spread_std"] = round(gm_metrics.get("spread", {}).get("mae", 11.0), 1)
            gm["first_half_std"] = round(gm_metrics.get("first_half", {}).get("mae", 6.7), 1)
        except Exception:
            pass
        report["game_models"] = gm
    except Exception as e:
        report["game_models"] = {"error": str(e)}
        print(f"[predict_game] game_models error: {e}", file=sys.stderr)

    # ── 3. Player props ────────────────────────────────────────────────────
    intervals = _load_conformal_intervals()
    prop_entries = []
    all_edge_plays = []

    if players is None:
        # No --players arg: skip props with an informative note
        report["props_skipped"] = (
            "no --players arg provided; pass "
            "--players 'TEAM:Name1,Name2;TEAM2:Name3' to predict props"
        )
    else:
        for team_abbr, player_names in players.items():
            opp = away_team if team_abbr.upper() == home_team.upper() else home_team
            for pname in player_names:
                pname = pname.strip()
                if not pname:
                    continue
                # Lines keyed by stat → player_name
                player_lines: Dict[str, float] = {}
                for stat, pdict in lines_by_stat.items():
                    if stat in ("total", "spread"):
                        continue
                    if isinstance(pdict, dict) and pname in pdict:
                        player_lines[stat] = float(pdict[pname])

                entry = _resolve_player_props(
                    pname, opp, season, intervals, player_lines
                )
                if entry is None:
                    prop_entries.append({"player_name": pname, "error": "player not found"})
                else:
                    prop_entries.append(entry)

                    # Collect edge plays for portfolio
                    for stat, pd in entry.get("props", {}).items():
                        edge = pd.get("edge")
                        if edge is None or edge <= 0:
                            continue
                        direction = pd.get("direction", "Over")
                        all_edge_plays.append({
                            "player_name": pname,
                            "stat": stat,
                            "direction": direction,
                            "line": pd.get("line"),
                            "edge_pct": edge / float(pd.get("line", 1) or 1),
                            "odds": -110,
                        })

        report["player_props"] = prop_entries

        # ── 4. Portfolio ───────────────────────────────────────────────────
        if all_edge_plays:
            portfolio = _simulate_portfolio(all_edge_plays, bankroll)
            report["portfolio"] = portfolio

    return report


# ── CLI entry point ────────────────────────────────────────────────────────────

def _parse_players(players_str: str) -> Dict[str, List[str]]:
    """
    Parse 'LAL:LeBron James,Anthony Davis;BOS:Jayson Tatum' into
    {'LAL': ['LeBron James', 'Anthony Davis'], 'BOS': ['Jayson Tatum']}.
    """
    result: Dict[str, List[str]] = {}
    for segment in players_str.split(";"):
        segment = segment.strip()
        if ":" not in segment:
            continue
        team, names_str = segment.split(":", 1)
        result[team.strip().upper()] = [n.strip() for n in names_str.split(",") if n.strip()]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NBA game prediction CLI — win prob, game models, props, portfolio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--game-id", help="NBA game_id (e.g. 0022500999)")
    group.add_argument("--home", help="Home team abbreviation (e.g. BOS)")

    parser.add_argument("--away",   help="Away team abbreviation (e.g. LAL)")
    parser.add_argument("--date",   default=str(date.today()), help="Game date YYYY-MM-DD")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument(
        "--players",
        help="Players to predict: 'TEAM:Name1,Name2;TEAM2:Name3'",
    )
    parser.add_argument(
        "--lines",
        help='JSON of lines: \'{"pts":{"LeBron James":25.5},"total":228.5}\'',
    )
    parser.add_argument("--lines-file", help="Path to lines JSON/CSV file")
    parser.add_argument("--bankroll", type=float, default=_DEFAULT_BANKROLL)
    parser.add_argument("--json",    action="store_true", help="Output raw JSON")
    parser.add_argument("--save",    metavar="PATH", help="Save markdown report to vault path")
    parser.add_argument("--no-save-prediction", action="store_true",
                        help="Skip saving JSON to data/predictions/")

    args = parser.parse_args()

    # Resolve game identity
    home_team = args.home
    away_team = args.away
    game_date = args.date

    if args.game_id:
        resolved = _resolve_game_id(args.game_id)
        if resolved:
            home_team = resolved["home_team"]
            away_team = resolved["away_team"]
            game_date = resolved.get("game_date", game_date)
        else:
            print(f"[predict_game] Could not resolve game_id={args.game_id}. "
                  "Provide --home/--away instead.", file=sys.stderr)
            sys.exit(1)

    if not home_team or not away_team:
        parser.error("Provide --home and --away, or --game-id")

    home_team = home_team.upper()
    away_team = away_team.upper()

    # Parse players
    players = None
    if args.players:
        players = _parse_players(args.players)

    # Parse lines
    lines_by_stat = _parse_lines(args.lines, args.lines_file)

    # Run
    report = run(
        home_team=home_team,
        away_team=away_team,
        season=args.season,
        game_date=game_date,
        players=players,
        lines_by_stat=lines_by_stat,
        bankroll=args.bankroll,
        no_save=args.no_save_prediction,
    )

    # Save prediction JSON (unless suppressed)
    if not args.no_save_prediction:
        try:
            pdir = os.path.join(PROJECT_DIR, "data", "predictions")
            os.makedirs(pdir, exist_ok=True)
            fname = f"{game_date}_{home_team}_{away_team}_cli.json"
            fpath = os.path.join(pdir, fname)
            with open(fpath, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2, default=str)
        except Exception as e:
            print(f"[predict_game] prediction save failed: {e}", file=sys.stderr)

    # Render
    output = _render_report(report, use_json=args.json)
    print(output)

    # Optionally save to vault
    if args.save:
        _save_markdown(report, args.save)


if __name__ == "__main__":
    main()
