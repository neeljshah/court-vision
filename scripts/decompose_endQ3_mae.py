"""decompose_endQ3_mae.py — cycle 95b (loop 5). End-Q3 MAE failure-mode decomposition.

WHY: cycle 93c/94d showed the cycle-88 in-game projector beats prod pergame
7/7 stats at endQ3 (PTS MAE 2.44, down from 4.23). But 2.44 is not zero — to
drive the residual lower we need to know which Q4 dynamics dominate the
remaining error.

Hypothesized contributors:
  (1) FOUL_CHANGE   — player picks up 2+ fouls between Q3 end and game end
                      (foul trouble materializes in Q4)
  (2) BLOWOUT_FLIP  — |Q3 margin| < 15 but |final margin| > 20 (close game
                      blew open in Q4)
  (3) STAR_PULLED   — player's Q4 min < 50% of their (Q1+Q2+Q3)/3 average
  (4) PACE_SHIFT    — team Q4 pace deviates > 1 std from Q1-Q3 pace mean
                      (proxy: per-quarter team points relative to game mean)
  (5) HEAT_CHECK    — player Q3 per-minute rate > 1.5x their Q1-Q2 mean

For each retro game (50 games via player_quarter_stats.parquet), compute
endQ3 cycle-88 projection vs actual final, stratify by these 5 modes, and
emit per-stratum MAE. The mode with the LARGEST stratum MAE (relative to
the global endQ3 baseline) is the dominant failure mode and the highest-
yield target for cycle 96+.

NO writes to predict_in_game.py / prop_pergame.py / live_factors.py — strictly
a read-only consumer of cycle-88b + cycle-94d infrastructure.

Run:
    python scripts/decompose_endQ3_mae.py
    python scripts/decompose_endQ3_mae.py --max-games 10
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

import retro_inplay_mae as v1  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
STRATA = (
    "foul_change", "blowout_flip", "star_pulled", "pace_shift", "heat_check",
    "none",  # catch-all: no strata triggered (the "clean" subset)
)


# ── per-player Q-by-Q feature extraction ──────────────────────────────────────

def _player_q_rows(game_df, pid: int) -> Dict[int, dict]:
    """Return {period: row_dict} for one player in one game.

    Each row has min/pts/reb/ast/fg3m/stl/blk/tov/pf as floats.
    Periods not played are simply absent from the dict (NOT 0-filled — we
    use absence to distinguish "didn't play" from "played and scored 0").
    """
    out: Dict[int, dict] = {}
    pdf = game_df[game_df["player_id"] == pid]
    for _, r in pdf.iterrows():
        period = int(r["period"])
        out[period] = {
            "min":  float(r["min"]),
            "pts":  float(r["pts"]),
            "reb":  float(r["reb"]),
            "ast":  float(r["ast"]),
            "fg3m": float(r["fg3m"]),
            "stl":  float(r["stl"]),
            "blk":  float(r["blk"]),
            "tov":  float(r["tov"]),
            "pf":   float(r["pf"]),
        }
    return out


def _team_q_points(game_df, team_pids: List[int]) -> Dict[int, float]:
    """{period: team_total_pts} for the given roster pids."""
    out: Dict[int, float] = defaultdict(float)
    for pid in team_pids:
        pdf = game_df[game_df["player_id"] == pid]
        for _, r in pdf.iterrows():
            out[int(r["period"])] += float(r["pts"])
    return dict(out)


# ── classify a single (player, game) into strata triggers ────────────────────

def classify_strata(
    pid: int,
    game_df,
    pid_to_team: Dict[int, str],
) -> Dict[str, bool]:
    """Return {stratum: True/False} for every stratum.

    A (player, game) can be in multiple strata simultaneously — they aren't
    mutually exclusive. We expose all triggers so the report can show both
    overlap and pure-bucket counts.
    """
    triggers = {s: False for s in STRATA}
    q_rows = _player_q_rows(game_df, pid)

    # (1) FOUL_CHANGE — fouls accumulated in Q4 >= 2
    q4_pf = q_rows.get(4, {}).get("pf", 0.0)
    if q4_pf >= 2.0:
        triggers["foul_change"] = True

    # (2) BLOWOUT_FLIP — uses team-level Q1-Q3 margin vs final margin
    team = pid_to_team.get(pid, "")
    if team:
        # Build {period: team_pts} for player's team and for the opposing team.
        team_pids = [p for p, t in pid_to_team.items() if t == team]
        # The opponent set is everyone with a known team that isn't ours.
        opp_teams = [t for t in set(pid_to_team.values()) if t and t != team]
        if opp_teams:
            opp = opp_teams[0]
            opp_pids = [p for p, t in pid_to_team.items() if t == opp]
            team_q = _team_q_points(game_df, team_pids)
            opp_q = _team_q_points(game_df, opp_pids)
            q3_margin = sum(team_q.get(q, 0.0) - opp_q.get(q, 0.0)
                            for q in (1, 2, 3))
            final_margin = q3_margin + (team_q.get(4, 0.0) - opp_q.get(4, 0.0))
            if abs(q3_margin) < 15.0 and abs(final_margin) > 20.0:
                triggers["blowout_flip"] = True

            # (4) PACE_SHIFT — Q4 combined points vs Q1-Q3 mean combined points
            combined_q = {q: team_q.get(q, 0.0) + opp_q.get(q, 0.0)
                          for q in (1, 2, 3, 4)}
            prior = [combined_q[q] for q in (1, 2, 3)]
            if combined_q.get(4) is not None and len(prior) == 3:
                mean = sum(prior) / 3.0
                var = sum((x - mean) ** 2 for x in prior) / 3.0
                std = var ** 0.5
                # 1 std deviation gate. Guard tiny-std games (std<2) with floor.
                std_eff = max(std, 2.0)
                if abs(combined_q[4] - mean) > std_eff:
                    triggers["pace_shift"] = True

    # (3) STAR_PULLED — Q4 min < 0.5 * avg(Q1-Q3 min played)
    prior_mins = [q_rows.get(q, {}).get("min", 0.0) for q in (1, 2, 3)]
    played_priors = [m for m in prior_mins if m > 0.0]
    q4_min = q_rows.get(4, {}).get("min", 0.0)
    if played_priors:
        avg_prior = sum(prior_mins) / 3.0  # avg over 3 quarters incl rest
        # Only meaningful for players with non-trivial Q1-Q3 share (avg >= 4 min).
        if avg_prior >= 4.0 and q4_min < 0.5 * avg_prior:
            triggers["star_pulled"] = True

    # (5) HEAT_CHECK — Q3 stat-per-min > 1.5 * Q1-Q2 mean stat-per-min (PTS)
    q3 = q_rows.get(3, {})
    q1 = q_rows.get(1, {})
    q2 = q_rows.get(2, {})
    q3_min = q3.get("min", 0.0)
    q12_min = q1.get("min", 0.0) + q2.get("min", 0.0)
    if q3_min >= 2.0 and q12_min >= 4.0:
        q3_ppm = q3.get("pts", 0.0) / q3_min
        q12_ppm = (q1.get("pts", 0.0) + q2.get("pts", 0.0)) / q12_min
        # Floor base rate so a 0-pt Q1+Q2 doesn't auto-trigger every Q3 bucket.
        if q12_ppm >= 0.25 and q3_ppm > 1.5 * q12_ppm:
            triggers["heat_check"] = True

    if not any(triggers.values()):
        triggers["none"] = True
    return triggers


# ── decomposition pass ────────────────────────────────────────────────────────

def decompose(qstats_df, max_games: Optional[int] = None) -> Dict:
    """Build the full decomposition table.

    Returns:
        {
            "n_games": int,
            "global": {stat: (n, mae)},
            "per_stratum": {stratum: {stat: (n, mae, mean_signed_err)}},
            "trigger_counts": {stratum: n_triggers},
            "n_player_games": int,
        }
    """
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

    global_buckets: Dict[str, List[float]] = defaultdict(list)
    stratum_buckets: Dict[str, Dict[str, List[Tuple[float, float]]]] = {
        s: defaultdict(list) for s in STRATA
    }
    trigger_counts: Dict[str, int] = defaultdict(int)
    n_player_games = 0

    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        projs = v1.project_snapshot_to_finals(snap)  # {(pid, stat): proj}
        actuals = v1.actuals_for_game(gid, qstats_df)
        game_df = qstats_df[qstats_df["game_id"] == gid]
        pid_to_team, _, _ = v1.load_team_map(gid)

        # Iterate over players that appear in BOTH projections and actuals.
        seen_pids = set(pid for pid, _ in projs.keys())
        for pid in seen_pids:
            triggers = classify_strata(pid, game_df, pid_to_team)
            for s, hit in triggers.items():
                if hit:
                    trigger_counts[s] += 1
            n_player_games += 1
            for stat in STATS:
                pred = projs.get((pid, stat))
                actual = actuals.get((pid, stat))
                if pred is None or actual is None:
                    continue
                abs_err = abs(pred - actual)
                signed = pred - actual
                global_buckets[stat].append(abs_err)
                for s, hit in triggers.items():
                    if hit:
                        stratum_buckets[s][stat].append((abs_err, signed))

    global_out = {
        s: (len(v), sum(v) / len(v)) for s, v in global_buckets.items() if v
    }
    per_stratum: Dict[str, Dict[str, Tuple[int, float, float]]] = {}
    for s, by_stat in stratum_buckets.items():
        per_stratum[s] = {}
        for stat, pairs in by_stat.items():
            if not pairs:
                continue
            n = len(pairs)
            mae = sum(a for a, _ in pairs) / n
            bias = sum(b for _, b in pairs) / n
            per_stratum[s][stat] = (n, mae, bias)

    return {
        "n_games": len(games),
        "global": global_out,
        "per_stratum": per_stratum,
        "trigger_counts": dict(trigger_counts),
        "n_player_games": n_player_games,
    }


# ── report ────────────────────────────────────────────────────────────────────

def _top_worst_stats(global_mae: Dict[str, Tuple[int, float]]) -> List[str]:
    """Top-3 stats by absolute MAE (PTS/REB/AST dominate by construction)."""
    return [s for s, _ in sorted(global_mae.items(),
                                 key=lambda kv: -kv[1][1])[:3]]


def build_report(d: Dict) -> str:
    lines: List[str] = []
    lines.append("# endQ3 MAE decomposition — cycle 95b (loop 5)")
    lines.append("")
    lines.append(f"**Retro games analyzed:** {d['n_games']}")
    lines.append(f"**Total (player, game) rows:** {d['n_player_games']}")
    lines.append("")
    lines.append(
        "Decomposes the residual cycle-88 endQ3 projection error (cycle 94d "
        "baseline: PTS MAE 2.44, REB 0.95, AST 0.65) into 5 Q4-dynamic "
        "failure modes. Each (player, game) row can trigger multiple "
        "strata (overlapping bins, NOT mutually exclusive). The 'none' "
        "bucket isolates the clean subset with no Q4 surprises."
    )
    lines.append("")
    lines.append("## Stratum definitions")
    lines.append("")
    lines.append("- **foul_change**: player Q4 PF >= 2 (post-Q3 foul trouble)")
    lines.append("- **blowout_flip**: |Q3 margin| < 15 AND |final margin| > 20")
    lines.append("- **star_pulled**: avg(Q1-Q3 min) >= 4 AND Q4 min < 0.5 * avg")
    lines.append("- **pace_shift**: Q4 combined pts deviates >1 std from Q1-Q3 mean (std floor=2)")
    lines.append("- **heat_check**: Q3 pts/min > 1.5x Q1-Q2 pts/min (base rate >= 0.25)")
    lines.append("- **none**: catch-all — no stratum triggered")
    lines.append("")
    lines.append("## Trigger counts (per-stratum row counts; overlapping)")
    lines.append("")
    lines.append("| stratum | n_player_games | pct_of_total |")
    lines.append("|---------|---------------:|-------------:|")
    total = max(1, d["n_player_games"])
    for s in STRATA:
        n = d["trigger_counts"].get(s, 0)
        lines.append(f"| {s} | {n} | {100.0 * n / total:.1f}% |")
    lines.append("")

    global_mae = d["global"]
    top_stats = _top_worst_stats(global_mae)

    lines.append("## Global endQ3 MAE (reference)")
    lines.append("")
    lines.append("| stat | n | mae |")
    lines.append("|------|---|-----|")
    for stat in STATS:
        if stat in global_mae:
            n, m = global_mae[stat]
            lines.append(f"| {stat} | {n} | {m:.4f} |")
    lines.append("")

    lines.append(f"## Per-stratum MAE — top 3 worst stats ({', '.join(top_stats).upper()})")
    lines.append("")
    lines.append("Columns: stratum_MAE - global_MAE = delta (positive = stratum is HARDER than baseline)")
    lines.append("Bias = mean(pred - actual); positive = over-projection.")
    lines.append("")
    lines.append("| stratum | " + " | ".join(
        f"{s.upper()} n | {s.upper()} mae | {s.upper()} delta | {s.upper()} bias"
        for s in top_stats) + " |")
    lines.append("|" + "---|" * (1 + 4 * len(top_stats)))
    for s in STRATA:
        cells = [s]
        for stat in top_stats:
            entry = d["per_stratum"].get(s, {}).get(stat)
            g_n, g_mae = global_mae.get(stat, (0, 0.0))
            if entry is None or g_mae == 0.0:
                cells += ["—", "—", "—", "—"]
                continue
            n, mae, bias = entry
            delta = mae - g_mae
            cells += [str(n), f"{mae:.4f}", f"{delta:+.4f}", f"{bias:+.4f}"]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # Ranked failure modes (across all stats; weight = sum_stat (delta * n_stat)).
    lines.append("## Ranked failure modes (across ALL 7 stats)")
    lines.append("")
    lines.append("Rank = sum_over_stats((stratum_MAE - global_MAE) * stratum_n) — captures both "
                 "the absolute MAE gap AND the count of rows affected. Larger = bigger "
                 "total residual error contributed.")
    lines.append("")
    ranking: List[Tuple[str, float, float]] = []
    for s in STRATA:
        if s == "none":
            # 'none' is the clean baseline reference, not a failure mode.
            continue
        total_excess = 0.0
        total_n = 0
        for stat in STATS:
            entry = d["per_stratum"].get(s, {}).get(stat)
            if entry is None:
                continue
            n, mae, _bias = entry
            g_n, g_mae = global_mae.get(stat, (0, 0.0))
            total_excess += (mae - g_mae) * n
            total_n += n
        mean_delta = (total_excess / total_n) if total_n > 0 else 0.0
        ranking.append((s, total_excess, mean_delta))
    ranking.sort(key=lambda x: -x[1])
    lines.append("| rank | stratum | total_excess_MAE_x_n | mean_delta_per_row |")
    lines.append("|-----:|---------|---------------------:|-------------------:|")
    for i, (s, tot, mean_d) in enumerate(ranking, 1):
        lines.append(f"| {i} | {s} | {tot:+.2f} | {mean_d:+.4f} |")
    lines.append("")

    # Cycle 96+ probe hypotheses tied to the top ranked mode.
    lines.append("## Cycle 96+ probe hypotheses")
    lines.append("")
    if ranking:
        top_mode = ranking[0][0]
        runner_up = ranking[1][0] if len(ranking) > 1 else None
        lines.append(f"**Dominant failure mode:** `{top_mode}` "
                     f"(total excess MAE x n = {ranking[0][1]:+.2f}, "
                     f"mean per-row delta = {ranking[0][2]:+.4f}).")
        lines.append("")
        # Mode-specific concrete probes:
        probe_map = {
            "foul_change": [
                "**Q4 foul-rate forecast head**: train a tiny model PF_Q4 = "
                "f(PF_Q3, pos, opp_foul_rate, ref_crew) and bake the expected "
                "Q4 foul count into the cycle-88 foul_trouble_factor BEFORE Q4 "
                "starts (currently the factor only fires on observed pf).",
                "**Player-specific foul-out priors**: backtest per-player Q4 "
                "PF distribution; players in top-decile of foul-rate get a "
                "harsher pre-emptive minute haircut at endQ3 snapshot.",
            ],
            "blowout_flip": [
                "**Margin-velocity forecaster**: project endQ3 margin to "
                "final-margin via Q3 scoring-rate differential (not just "
                "running margin); when forecast indicates blowout flip, "
                "apply blowout_factor PROACTIVELY rather than only at the "
                "post-fact margin gate.",
                "**Backup/depth-chart usage prior**: for high-projected-min "
                "stars on the leading side at endQ3 with margin in 10-15 "
                "window, blend in a 'partial pull' factor (e.g. 0.85) since "
                "blowout flip is materially more likely than current model "
                "credits.",
            ],
            "star_pulled": [
                "**Coach rotation tendency feature**: per-team Q4-min-vs-"
                "starter-min historical distribution. Coaches like Spoelstra "
                "vs Kerr pull stars at different margins; bake this into "
                "blowout_factor.",
                "**Per-player Q4 minute prior**: rolling mean of (Q4_min / "
                "game_min) per player; if recent prior < 0.20 and game is "
                "in 10+ margin at endQ3, scale projection by that ratio.",
            ],
            "pace_shift": [
                "**Q4 pace decay model**: empirical Q4 possessions/12min vs "
                "Q1-Q3 pace, conditioned on margin bucket. Q4 ALWAYS slows "
                "in tight games; predict pace_factor < 1.0 dynamically.",
                "**Late-clock free-throw inflation**: Q4 trailing teams "
                "intentionally foul, inflating PTS for the LEADING team's "
                "ball-handlers. Bake FT-rate uplift into PTS projection "
                "for projected leading team in tight late games.",
            ],
            "heat_check": [
                "**Mean-reversion shrinkage**: Q3 hot-shooting players are "
                "currently linearly extrapolated; apply Bayesian shrinkage "
                "toward season per-min rate when |Q3 rate - season rate| > "
                "1.5 std.",
                "**Defensive adjustment prior**: opposing team applies "
                "stronger defense vs Q3 hot hand in Q4 — quantify the "
                "empirical Q4 stat decline for Q3 heat-check players, "
                "bake as a multiplier.",
            ],
            "none": [],
        }
        for probe in probe_map.get(top_mode, [])[:2]:
            lines.append(f"1. {probe}")
        if runner_up:
            lines.append("")
            lines.append(f"**Runner-up:** `{runner_up}` — secondary candidate:")
            for probe in probe_map.get(runner_up, [])[:1]:
                lines.append(f"1. {probe}")
    lines.append("")
    return "\n".join(lines) + "\n"


# ── runner ───────────────────────────────────────────────────────────────────

def run(max_games: Optional[int] = None,
        output: Optional[str] = None) -> int:
    qstats_df = v1.load_quarter_stats()
    print(f"  decompose_endQ3_mae: loaded {len(qstats_df)} quarter rows")
    d = decompose(qstats_df, max_games=max_games)
    print(f"  games analyzed: {d['n_games']}  player-game rows: {d['n_player_games']}")

    report = build_report(d)
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "endQ3_decomposition_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"  wrote {out_path}")

    # Console summary
    print("\n  trigger counts:")
    for s in STRATA:
        print(f"    {s:14s}: {d['trigger_counts'].get(s, 0)}")
    print("\n  global endQ3 MAE:")
    for stat in STATS:
        if stat in d["global"]:
            n, m = d["global"][stat]
            print(f"    {stat:4s}: n={n}  mae={m:.4f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None,
                    help="Limit to first N games (debug).")
    ap.add_argument("--output", default=None,
                    help="Markdown output path (default: "
                         "scripts/_results/endQ3_decomposition_v1.md)")
    args = ap.parse_args()
    return run(max_games=args.max_games, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
