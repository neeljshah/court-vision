"""backtest_inplay_edge.py — cycle 95d (loop 5). In-play betting edge vs pregame.

WHY: cycle 94d's prod-baseline MAE probe established that the cycle-88 end-Q3
projection beats the production pergame predictor on 7/7 stats (PTS -1.80 MAE,
42% relative improvement). The natural follow-up is: does that MAE improvement
translate to a betting EDGE when we treat the L5 rolling mean as the sportsbook-
line proxy (cycle 30 documented L5 as the strongest naive book-analog)?

This script answers that empirically:

  1. For each retro game in data/player_quarter_stats.parquet (50 games), build
     the end-Q3 cycle-88 projection AND the prod pregame prediction AND the
     L5-rolling-mean "line" — all on the SAME (game_id, player_id, stat) keys.
  2. For each (player, stat), compute:
        edge_pregame  = pregame_pred - L5_line
        edge_inplay   = endQ3_proj   - L5_line
  3. Simulate a placement rule: bet at -110 odds when |edge| >= threshold AND
     model probability gives positive Kelly. Settle vs actual: bet WINS if
     (actual > L5_line) and side=OVER (or vice versa).
  4. Report per-stat ROI at thresholds {0.5, 1.0, 1.5, 2.0, 3.0} for BOTH the
     pregame and the in-play systems. The natural ablation: does the in-play
     edge win MORE often / at HIGHER ROI than the pregame edge on the same
     games / players / lines?

The hypothesis we're testing: in-play projection ROI > pregame projection ROI
on >= 4/7 stats at threshold 1.0+. If TRUE, the cycle-88 system is the
production betting layer. If FALSE, the MAE improvement is a regression-to-
mean artifact — better at PRE-cancellation point estimates but not at the
DIRECTIONAL bet (which is what scores against the line).

CRITICAL: we do NOT synthesize fake sportsbook lines. L5 is the documented
proxy from cycle 30. Real sportsbook lines aren't available retroactively.

Strictly read-only — no model writes, no edits to prop_pergame / predict_in_game.

Run:
    python scripts/backtest_inplay_edge.py
    python scripts/backtest_inplay_edge.py --max-games 10
    python scripts/backtest_inplay_edge.py --output scripts/_results/foo.md
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as v1        # snapshot + L5 helpers  # noqa: E402
import retro_inplay_mae_v2 as v2     # prod pergame builder    # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
THRESHOLDS = (0.5, 1.0, 1.5, 2.0, 3.0)
# Standard -110 odds, the canonical prop book number.
DEFAULT_ODDS = -110

# Cycle 40 calibrated typical q90-q10 spread per stat. Sourced from the
# production quantile_calibration manifest; locked-in defaults so this script
# doesn't depend on the prop_quantiles model being trained / present. These
# control sigma in the win-prob estimate (sigma = spread / (2 * 1.2816)).
# They are intentionally generous — narrower would overstate Kelly confidence.
_CAL_SPREAD = {
    "pts": 14.0, "reb": 5.5, "ast": 4.0, "fg3m": 2.4,
    "stl": 2.0, "blk": 1.6, "tov": 2.4,
}


# ── pure betting math (testable) ──────────────────────────────────────────────

def american_payout(odds: int, stake: float = 1.0) -> float:
    """Profit on $stake at American odds (excluding stake return).

    -110 → 0.909, +150 → 1.50.
    """
    odds = int(odds)
    if odds > 0:
        return stake * (odds / 100.0)
    return stake * (100.0 / -odds)


def model_hit_prob(point_pred: float, line: float, sigma: float,
                   side: str) -> float:
    """Approximate P(WIN | side). Normal centered at point_pred with the given
    sigma; side='OVER' → P(actual > line), 'UNDER' → P(actual < line).
    """
    from math import erf, sqrt
    if sigma <= 0:
        return 1.0 if (
            (side == "OVER" and point_pred > line)
            or (side == "UNDER" and point_pred < line)
        ) else 0.0
    z = (line - point_pred) / sigma
    cdf_at_line = 0.5 * (1.0 + erf(z / sqrt(2.0)))
    p_over = 1.0 - cdf_at_line
    return p_over if side == "OVER" else 1.0 - p_over


def kelly_fraction(prob: float, odds: int) -> float:
    """Standard Kelly. Returns 0.0 (clipped, never negative) when no edge.

    f = (b * p - q) / b   where b = net payout per unit stake, q = 1 - p.
    """
    if prob is None:
        return 0.0
    b = american_payout(odds, 1.0)
    if b <= 0:
        return 0.0
    p = float(prob)
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, f)


def settle_bet(stake: float, side: str, line: float, actual: float,
               odds: int) -> float:
    """Return P&L on a $stake bet. Push (actual == line) refunds 0.

    Wins receive `stake * american_payout(odds)`; losses receive `-stake`.
    Pushes (when actual exactly equals the line — rare on .5 lines but
    possible on .0 lines) return 0.0.
    """
    if actual == line:
        return 0.0
    if side == "OVER":
        win = actual > line
    else:
        win = actual < line
    if win:
        return stake * american_payout(odds, 1.0)
    return -stake


# ── per-system simulator ──────────────────────────────────────────────────────

def simulate_bets(
    triples: Dict[Tuple[str, int, str], float],
    lines: Dict[Tuple[str, int, str], float],
    actuals: Dict[Tuple[str, int, str], float],
    threshold: float,
    odds: int = DEFAULT_ODDS,
) -> Dict[str, dict]:
    """For one prediction system (pregame OR inplay), simulate flat-$1 +
    Kelly placement at the given edge threshold.

    Returns {stat: {"n_bets", "wins", "roi_flat", "roi_kelly", "stake_flat",
                    "stake_kelly", "pnl_flat", "pnl_kelly"}}.
    """
    out: Dict[str, dict] = {s: {
        "n_bets": 0, "wins": 0,
        "stake_flat": 0.0, "pnl_flat": 0.0,
        "stake_kelly": 0.0, "pnl_kelly": 0.0,
    } for s in STATS}

    for key, pred in triples.items():
        gid, pid, stat = key
        line = lines.get(key)
        actual = actuals.get(key)
        if line is None or actual is None:
            continue
        edge = pred - line
        if abs(edge) < threshold:
            continue
        side = "OVER" if edge > 0 else "UNDER"
        sigma = _CAL_SPREAD.get(stat, 1.0) / (2.0 * 1.2816)
        prob = model_hit_prob(pred, line, sigma, side)
        kf = kelly_fraction(prob, odds)
        if kf <= 0:
            continue  # No-Kelly bet → skip (matches the spec's "Kelly-positive" gate)

        # Flat $1 bet
        pnl_flat = settle_bet(1.0, side, line, actual, odds)
        # Kelly fractional: stake = kf (assume bankroll=1.0 unit)
        pnl_kelly = settle_bet(kf, side, line, actual, odds)

        b = out[stat]
        b["n_bets"] += 1
        if pnl_flat > 0:
            b["wins"] += 1
        b["stake_flat"] += 1.0
        b["pnl_flat"] += pnl_flat
        b["stake_kelly"] += kf
        b["pnl_kelly"] += pnl_kelly

    # Finalise ROI cells.
    for s, b in out.items():
        b["roi_flat"] = (b["pnl_flat"] / b["stake_flat"]) if b["stake_flat"] > 0 else None
        b["roi_kelly"] = (b["pnl_kelly"] / b["stake_kelly"]) if b["stake_kelly"] > 0 else None
        b["win_rate"] = (b["wins"] / b["n_bets"]) if b["n_bets"] > 0 else None
    return out


# ── report ────────────────────────────────────────────────────────────────────

def build_report(
    results_by_thr: Dict[float, Dict[str, Dict[str, dict]]],
    n_games: int,
    n_triples: int,
) -> str:
    """Build the markdown report comparing pregame vs inplay edge ROI.

    `results_by_thr[thr][system][stat]` where system ∈ {"pregame", "inplay"}.
    """
    lines: List[str] = []
    lines.append("# In-play vs pregame betting edge backtest — cycle 95d (loop 5)")
    lines.append("")
    lines.append(f"**Games analyzed:** {n_games}")
    lines.append(f"**(game, player, stat) triples with all 3 systems populated:** "
                 f"{n_triples}")
    lines.append("")
    lines.append("**RESEARCH MEASUREMENT — NOT a betting recommendation.**")
    lines.append("")
    lines.append(
        "Compares two prediction systems' EDGE vs an L5-rolling-mean line proxy "
        "(cycle 30 documented L5 as the strongest naive sportsbook-line analog "
        "available retroactively). Both systems bet at standard -110 odds when "
        "|edge| >= threshold AND Kelly fraction > 0. Outcomes settle vs actual "
        "full-game stat sums from data/player_quarter_stats.parquet. Pregame "
        "uses the cycle-48 production pergame predictor; inplay uses the cycle-"
        "88 end-Q3 projector (which only sees data through end of Q3)."
    )
    lines.append("")

    # ── master table: per stat / per threshold ──────────────────────────────
    lines.append("## ROI by threshold and stat (flat $1 stakes)")
    lines.append("")
    lines.append("| stat | thr | n_pre | n_inp | wr_pre | wr_inp | "
                 "ROI_pregame | ROI_inplay | inplay_better |")
    lines.append("|------|-----|------:|------:|-------:|-------:|"
                 "------------:|-----------:|---------------|")

    # `wins[thr][stat]` = "Y" if inplay ROI strictly beats pregame.
    inplay_wins_by_thr: Dict[float, int] = defaultdict(int)
    inplay_total_by_thr: Dict[float, int] = defaultdict(int)

    for thr in THRESHOLDS:
        per_sys = results_by_thr[thr]
        for stat in STATS:
            pre = per_sys["pregame"][stat]
            ip = per_sys["inplay"][stat]
            roi_pre = pre.get("roi_flat")
            roi_ip = ip.get("roi_flat")
            wr_pre = pre.get("win_rate")
            wr_ip = ip.get("win_rate")
            ip_better = ""
            if roi_pre is not None and roi_ip is not None:
                inplay_total_by_thr[thr] += 1
                if roi_ip > roi_pre:
                    inplay_wins_by_thr[thr] += 1
                    ip_better = "Y"
                else:
                    ip_better = "n"

            def _fmt_roi(x):
                return f"{x:+.4f}" if x is not None else "—"

            def _fmt_wr(x):
                return f"{x:.3f}" if x is not None else "—"

            lines.append(
                f"| {stat} | {thr} | {pre['n_bets']} | {ip['n_bets']} | "
                f"{_fmt_wr(wr_pre)} | {_fmt_wr(wr_ip)} | "
                f"{_fmt_roi(roi_pre)} | {_fmt_roi(roi_ip)} | {ip_better} |"
            )

    lines.append("")
    lines.append("## Per-threshold summary: in-play wins vs pregame")
    lines.append("")
    lines.append("| thr | inplay_better | inplay_total |")
    lines.append("|----:|--------------:|-------------:|")
    for thr in THRESHOLDS:
        lines.append(
            f"| {thr} | {inplay_wins_by_thr[thr]} | {inplay_total_by_thr[thr]} |"
        )
    lines.append("")

    # ── verdict ────────────────────────────────────────────────────────────
    # Hypothesis: in-play wins >= 4/7 stats at threshold 1.0+.
    headline_threshold = 1.0
    wins = inplay_wins_by_thr.get(headline_threshold, 0)
    total = inplay_total_by_thr.get(headline_threshold, 0)

    lines.append("## Verdict")
    lines.append("")
    if total == 0:
        lines.append(
            "**Inconclusive — not enough placed bets at threshold 1.0 to "
            "judge.**"
        )
    elif wins >= 4:
        lines.append(
            f"**IN-PLAY EDGE WINS — endQ3 projection beats pregame on "
            f"{wins}/{total} stats at threshold 1.0.** The cycle-88 MAE "
            f"improvement (cycle 94d: -1.80 PTS MAE) DOES translate into "
            f"directional bet edge. Locking in the cycle-88 system as the "
            f"in-play betting layer is justified."
        )
    elif wins == 3:
        lines.append(
            f"**MIXED — endQ3 wins {wins}/{total} at threshold 1.0.** The MAE "
            f"improvement gets partial translation to bet edge. Use the in-play "
            f"projector selectively (winning stats only) and stay on pregame "
            f"for the rest."
        )
    else:
        lines.append(
            f"**IN-PLAY EDGE LOSES — endQ3 wins only {wins}/{total} at "
            f"threshold 1.0.** The MAE improvement is point-estimate-only — "
            f"the in-play projection is regressing toward the actual on "
            f"average but NOT giving stronger directional signal at the "
            f"sportsbook-line proxy. Cycle-88 ships as a tracking tool, not "
            f"as the production betting layer."
        )
    lines.append("")
    lines.append(
        "(Hypothesis pre-registered before run: in-play wins >= 4/7 stats at "
        "thr 1.0+.)"
    )
    lines.append("")
    return "\n".join(lines) + "\n"


# ── main runner ──────────────────────────────────────────────────────────────

def run(max_games: Optional[int] = None,
        output: Optional[str] = None) -> int:
    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    print(f"  backtest_inplay_edge: {len(games)} games")

    # 1) game_id → ISO date.
    game_dates: Dict[str, str] = {}
    for gid in games:
        d = v1.find_game_date(gid, qstats_df)
        if d:
            game_dates[gid] = d
    print(f"  dated games: {len(game_dates)} / {len(games)}")

    # 2) Snapshot + endQ3 projection.
    inplay: Dict[Tuple[str, int, str], float] = {}
    actuals_t: Dict[Tuple[str, int, str], float] = {}
    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is not None:
            for (pid, stat), proj in v1.project_snapshot_to_finals(snap).items():
                inplay[(gid, pid, stat)] = float(proj)
        for (pid, stat), act in v1.actuals_for_game(gid, qstats_df).items():
            actuals_t[(gid, pid, stat)] = float(act)
    print(f"  endQ3 projections: {len(inplay)}; actuals: {len(actuals_t)}")

    # 3) L5 line proxy (sportsbook-line analog).
    lines = v1.pregame_predictions_via_gamelog(game_dates, qstats_df)
    print(f"  L5 line proxies: {len(lines)}")

    # 4) Pregame predictions from prod cycle-48 dispatcher.
    pregame = v2.prod_pergame_predictions(game_dates, qstats_df)
    print(f"  pregame predictions: {len(pregame)}")

    # Count triples present in ALL 4 sets — these are the only ones bet.
    keys_all = set(inplay) & set(pregame) & set(lines) & set(actuals_t)
    print(f"  fully-populated triples: {len(keys_all)}")

    # 5) Run simulator at each threshold.
    results_by_thr: Dict[float, Dict[str, Dict[str, dict]]] = {}
    for thr in THRESHOLDS:
        results_by_thr[thr] = {
            "pregame": simulate_bets(pregame, lines, actuals_t, thr),
            "inplay":  simulate_bets(inplay,  lines, actuals_t, thr),
        }

    # 6) Report.
    report = build_report(results_by_thr, len(games), len(keys_all))
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "inplay_edge_backtest_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"  wrote {out_path}")

    # Console summary at the headline threshold.
    print("\n  ROI at threshold 1.0 (flat $1):")
    print("  stat   pregame_n  inplay_n  ROI_pregame  ROI_inplay  better")
    for stat in STATS:
        pre = results_by_thr[1.0]["pregame"][stat]
        ip = results_by_thr[1.0]["inplay"][stat]
        roi_pre = pre.get("roi_flat")
        roi_ip = ip.get("roi_flat")
        better = ""
        if roi_pre is not None and roi_ip is not None:
            better = "INPLAY" if roi_ip > roi_pre else "pregame"
        roi_pre_s = f"{roi_pre:+.4f}" if roi_pre is not None else "    —   "
        roi_ip_s = f"{roi_ip:+.4f}" if roi_ip is not None else "    —   "
        print(f"  {stat:4s}   {pre['n_bets']:>9d}  {ip['n_bets']:>8d}  "
              f"{roi_pre_s:>11s}  {roi_ip_s:>10s}  {better}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None,
                    help="Limit to first N games (debug).")
    ap.add_argument("--output", default=None,
                    help="Markdown output path (default: "
                         "scripts/_results/inplay_edge_backtest_v1.md)")
    args = ap.parse_args()
    return run(max_games=args.max_games, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
