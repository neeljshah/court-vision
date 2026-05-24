"""retro_inplay_mae_v2.py — cycle 94d (loop 5).

v2 of cycle 93c's retro in-play MAE probe. Cycle 93c established that the
cycle-88 in-play projector beats a L5-rolling-mean baseline 7/7 stats at
end-Q3 (PTS -2.21 MAE!). But L5-mean is the sportsbook-line proxy — it is
NOT the production pergame predictor (cycle 48 R²=0.5105, MAE=4.62 for PTS).
The 7/7 win may collapse against the real prod pergame predict.

This script answers the harder question: does the in-play projector beat the
FULL prod pergame predictor (cycle 48 dispatch — q50 for fg3m/stl/blk/tov/reb,
sqrt+Huber blend for PTS, multitask MLP for AST)?

Approach:
  1. Same data sources as v1: data/player_quarter_stats.parquet for snapshot
     reconstruction; full-game actuals are Q1+Q2+Q3+Q4 sums from the parquet.
  2. For each (game_id, player_id) we build the SAME feature row that
     build_pergame_dataset would build (form features, opp_def, rest_travel,
     playtypes, bbref, contracts, reb_ctx) STRICTLY from prior games — same
     leakage discipline as the trainer. We then call predict_pergame per
     stat, which dispatches to q50 / sqrt+Huber / multitask exactly as
     production does.
  3. Project end-Q1/Q2/Q3 snapshots through predict_in_game.project_snapshot
     (cycle 88b) — identical to v1.
  4. Compare per-stat MAE: prod_pergame vs endQ1/Q2/Q3 in-play projection
     on the SAME set of (game_id, player_id, stat) triples.

NO writes to predict_in_game.py or prop_pergame.py — read-only consumer.

Run:
    python scripts/retro_inplay_mae_v2.py
    python scripts/retro_inplay_mae_v2.py --max-games 10
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_in_game as pig  # noqa: E402

# Reuse v1's snapshot / dating / actuals helpers (read-only).
import retro_inplay_mae as v1  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS = ("endQ1", "endQ2", "endQ3")


# ── prod pergame prediction for a single historical (player, game) ────────────

def _build_pid_gamelog_index() -> Dict[int, List[Tuple[datetime, dict, str]]]:
    """Return {player_id: [(date, gamelog_row, season), ...]} sorted by date.

    Loads every data/nba/gamelog_<pid>_<season>.json once and pre-sorts so the
    per-(player, target_date) prior list lookup is O(log n).
    """
    import glob
    import json

    from src.prediction.prop_pergame import _parse_date  # type: ignore

    out: Dict[int, List[Tuple[datetime, dict, str]]] = defaultdict(list)
    for fp in glob.glob(os.path.join(PROJECT_DIR, "data", "nba", "gamelog_*.json")):
        basename = os.path.basename(fp)
        try:
            parts = basename.split("_")
            pid = int(parts[1])
            season = parts[-1].replace(".json", "")
        except Exception:
            continue
        try:
            with open(fp, encoding="utf-8") as fh:
                games = json.load(fh) or []
        except Exception:
            continue
        if not isinstance(games, list):
            continue
        for g in games:
            d = _parse_date(g.get("GAME_DATE"))
            if d is None:
                continue
            out[pid].append((d, g, season))
    for pid in out:
        out[pid].sort(key=lambda x: x[0])
    return out


def _prepare_joins():
    """Build the same join wrappers build_pergame_dataset uses.

    Importing the wrappers is cheap; loading the underlying parquets is the
    heavy part (each is in-memory once, then per-row lookups are fast).
    """
    from src.prediction import prop_pergame as pp  # noqa: PLC0415
    joins = {
        "oppdef":     pp.build_opponent_defense(pp._NBA_CACHE),
        "resttravel": pp.build_rest_travel(),
        "playtypes":  pp.build_playtypes(),
        "bbref":      pp.build_bbref_advanced(),
        "contracts":  pp.build_contracts(),
        "reb_ctx":    pp.build_team_reb_context(),
    }
    return joins, pp


def _build_feature_row_for(
    pid: int,
    target_date: datetime,
    gamelog_index: Dict[int, List[Tuple[datetime, dict, str]]],
    joins: dict,
    pp,
) -> Optional[Dict[str, float]]:
    """Build the pre-game feature row for one (player_id, target_date).

    Mirrors build_pergame_dataset's per-row construction. Returns None when
    the player has no gamelog or no game on target_date.
    """
    history = gamelog_index.get(pid)
    if not history:
        return None

    # Find the target game in the player's gamelog AND collect strictly-prior
    # played games. We use _MIN_PLAYED == 1.0 (matches prop_pergame default).
    from src.prediction.prop_pergame import (  # type: ignore
        _MIN_PLAYED, _num, _opponent_from_matchup, _REB_CONTEXT_KEYS,
        _row_features, feature_columns,
    )

    target_game = None
    target_season = ""
    prior_played: List[dict] = []
    last_played_date: Optional[datetime] = None
    target_idx = -1
    for idx, (d, g, season) in enumerate(history):
        # Match on calendar date (gamelog uses 'Apr 13, 2025' -> datetime
        # midnight; quarter-stats target_date is same).
        if d.date() == target_date.date() and target_game is None:
            target_game = g
            target_season = season
            target_idx = idx
            break
        if _num(g.get("MIN")) >= _MIN_PLAYED:
            prior_played.append(g)
            last_played_date = d

    if target_game is None:
        return None

    matchup = str(target_game.get("MATCHUP", ""))
    is_home = 1 if " vs. " in matchup else 0
    team_abbrev = matchup.split()[0] if matchup.split() else ""
    opp_abbrev = _opponent_from_matchup(matchup)

    # Rest days — clamped 0-10, mirrors build_pergame_dataset.
    rest = 3.0
    if target_idx > 0:
        delta = (history[target_idx][0] - history[target_idx - 1][0]).days
        rest = float(min(max(delta, 0), 10))

    raw_gap_days = 3.0
    if last_played_date is not None:
        raw_gap_days = float(max((target_date - last_played_date).days, 0))

    feats = _row_features(prior_played, rest, is_home, len(prior_played),
                          days_since_last_game=raw_gap_days)
    feats.update(joins["oppdef"].factors(opp_abbrev, target_date))
    feats.update(joins["resttravel"].features(team_abbrev, target_date))
    feats.update(joins["playtypes"].features(pid, target_season))
    feats.update(joins["bbref"].features(pid, target_season))
    feats.update(joins["contracts"].features(pid, target_season))
    feats.update(joins["reb_ctx"].features(team_abbrev, opp_abbrev, target_date))

    # predict_pergame reads via feature_columns() — every key it requests must
    # exist (0.0 is the trainer's default for missing). Slice to the canonical
    # column list, plus carry REB-context cols even though q50 uses 85 cols.
    cols = feature_columns()
    row: Dict[str, float] = {c: float(feats.get(c, 0.0) or 0.0) for c in cols}
    for k in _REB_CONTEXT_KEYS:
        row[k] = float(feats.get(k, 0.0) or 0.0)
    return row


def prod_pergame_predictions(
    game_dates: Dict[str, str],
    qstats_df,
) -> Dict[Tuple[str, int, str], float]:
    """Compute prod pergame predictions for every (game_id, player_id, stat).

    Returns {(game_id, player_id, stat): predicted}. Players we can't tie back
    to a gamelog row on the target_date are skipped silently.
    """
    from src.prediction.prop_pergame import predict_pergame  # type: ignore

    joins, pp = _prepare_joins()
    gamelog_index = _build_pid_gamelog_index()

    out: Dict[Tuple[str, int, str], float] = {}
    n_built = n_pred = 0
    for game_id, date_iso in game_dates.items():
        if not date_iso:
            continue
        try:
            target_date = datetime.fromisoformat(date_iso)
        except ValueError:
            continue
        # Players we need for this game (those who appear in player_quarter_stats).
        gpids = qstats_df[qstats_df["game_id"] == game_id]["player_id"].unique()
        for raw_pid in gpids:
            try:
                pid = int(raw_pid)
            except (TypeError, ValueError):
                continue
            row = _build_feature_row_for(
                pid, target_date, gamelog_index, joins, pp)
            if row is None:
                continue
            n_built += 1
            for stat in STATS:
                val = predict_pergame(stat, row)
                if val is None:
                    continue
                out[(game_id, pid, stat)] = float(val)
                n_pred += 1
    print(f"  prod pergame: built {n_built} feature rows, "
          f"emitted {n_pred} predictions across {len(STATS)} stats")
    return out


# ── MAE aggregation (3 systems on the SAME (game,pid,stat) triples) ───────────

def aggregate_mae_v2(
    snaps_per_game: Dict[str, Dict[str, Dict[Tuple[int, str], float]]],
    actuals: Dict[str, Dict[Tuple[int, str], float]],
    prod_pergame: Dict[Tuple[str, int, str], float],
) -> Dict[str, Dict[str, Tuple[int, float]]]:
    """Build {stat: {kind: (n, mae)}} restricted to (game,pid,stat) triples
    that have BOTH a prod pergame prediction AND an actual.

    `kind` ∈ {"prod_pergame", "endQ1", "endQ2", "endQ3"}.
    """
    buckets: Dict[str, Dict[str, List[float]]] = {
        s: defaultdict(list) for s in STATS
    }

    for (game_id, pid, stat), pred in prod_pergame.items():
        actual = actuals.get(game_id, {}).get((pid, stat))
        if actual is None:
            continue
        buckets[stat]["prod_pergame"].append(abs(pred - actual))
        # Pair each prod pred with its in-play counterpart on the same triple.
        for point in SNAPSHOT_POINTS:
            projs = snaps_per_game.get(game_id, {}).get(point)
            if not projs:
                continue
            ip = projs.get((pid, stat))
            if ip is None:
                continue
            buckets[stat][point].append(abs(ip - actual))

    out: Dict[str, Dict[str, Tuple[int, float]]] = {}
    for s, by_kind in buckets.items():
        out[s] = {k: (len(v), sum(v) / len(v)) for k, v in by_kind.items() if v}
    return out


def build_report_v2(
    mae_table: Dict[str, Dict[str, Tuple[int, float]]],
    n_games: int,
) -> str:
    lines: List[str] = []
    lines.append("# Retro in-play vs PROD pergame MAE — cycle 94d (loop 5)")
    lines.append("")
    lines.append(f"**Games analyzed:** {n_games}")
    lines.append("")
    lines.append(
        "v2 of cycle 93c. v1 compared end-Q3 in-play projection to an L5-mean "
        "baseline (sportsbook-line proxy); v2 compares against the FULL prod "
        "pergame predictor (cycle 48 dispatch — q50 for fg3m/stl/blk/tov/reb, "
        "sqrt+Huber blend for PTS, multitask MLP-blend for AST). All 3 systems "
        "are MAE'd on the SAME (game_id, player_id, stat) triples — players "
        "whose pregame feature row couldn't be built (no gamelog match) drop "
        "from all systems."
    )
    lines.append("")
    lines.append("| stat | n | prod_pergame_mae | endQ1_mae | endQ2_mae | endQ3_mae | winner_q3 | delta_q3_vs_prod |")
    lines.append("|------|---|------------------|-----------|-----------|-----------|-----------|------------------|")

    q3_wins = 0
    q3_total = 0
    per_stat_winners: Dict[str, int] = defaultdict(int)
    for stat in STATS:
        by_kind = mae_table.get(stat, {})
        pp_pair = by_kind.get("prod_pergame")
        if pp_pair is None:
            continue
        n_pp, mae_pp = pp_pair
        q1 = by_kind.get("endQ1")
        q2 = by_kind.get("endQ2")
        q3 = by_kind.get("endQ3")

        def _cell(entry):
            if entry is None:
                return "—"
            n, m = entry
            return f"{m:.4f} (n={n})"

        # Winner across all 4 systems for this stat.
        candidates = [("prod_pergame", mae_pp)]
        for k, e in (("endQ1", q1), ("endQ2", q2), ("endQ3", q3)):
            if e is not None:
                candidates.append((k, e[1]))
        winner_overall, _ = min(candidates, key=lambda x: x[1])
        per_stat_winners[winner_overall] += 1

        delta = "—"
        winner_q3 = "—"
        if q3 is not None:
            d = q3[1] - mae_pp
            delta = f"{d:+.4f}"
            q3_total += 1
            if q3[1] < mae_pp:
                q3_wins += 1
                winner_q3 = "endQ3"
            else:
                winner_q3 = "prod_pergame"

        lines.append(
            f"| {stat} | {n_pp} | {mae_pp:.4f} | "
            f"{_cell(q1)} | {_cell(q2)} | {_cell(q3)} | "
            f"{winner_q3} | {delta} |"
        )

    lines.append("")
    lines.append("## Per-stat winner counts (best MAE across all 4 systems)")
    lines.append("")
    for kind in ("prod_pergame", "endQ1", "endQ2", "endQ3"):
        lines.append(f"- {kind}: {per_stat_winners.get(kind, 0)}")
    lines.append("")

    lines.append("## Verdict")
    lines.append("")
    if q3_total == 0:
        lines.append("**Inconclusive — no (game,pid,stat) triples shared between "
                     "prod_pergame and endQ3 systems.**")
    else:
        if q3_wins == q3_total:
            lines.append(
                f"**ENTIRE IN-GAME SYSTEM VALIDATED — endQ3 beats prod pergame "
                f"on {q3_wins}/{q3_total} stats.** v1's 7/7 sweep against the "
                f"L5 baseline holds against the real production predictor too. "
                f"The cycle-88 pace + foul + blowout heuristics carry signal "
                f"beyond what either the line-proxy OR the trained model can "
                f"produce at the late-game horizon."
            )
        elif q3_wins >= 4:
            lines.append(
                f"**In-play projection PARTIALLY validated — endQ3 beats prod "
                f"pergame on {q3_wins}/{q3_total} stats.** Stat-specific use: "
                f"prefer endQ3 for the winning stats; stay on prod_pergame for "
                f"the rest. v1's 7/7 sweep was inflated by the L5-baseline "
                f"weakness on the losing stats."
            )
        else:
            lines.append(
                f"**In-play projection NOT competitive with prod pergame — "
                f"endQ3 beats prod on only {q3_wins}/{q3_total} stats.** "
                f"v1's 7/7 win was a baseline artifact: the cycle-88 system "
                f"beats L5-mean but does not clear the trained model bar. "
                f"Cycle-88 needs stat-specific refinement OR should be used "
                f"only for stats not in production prop_pergame."
            )
    lines.append("")
    return "\n".join(lines) + "\n"


# ── main runner ───────────────────────────────────────────────────────────────

def run(max_games: Optional[int] = None,
        output: Optional[str] = None) -> int:
    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    print(f"  retro_inplay_mae_v2: {len(games)} games")

    # 1) Dating — same lookup v1 uses.
    game_dates: Dict[str, str] = {}
    for gid in games:
        d = v1.find_game_date(gid, qstats_df)
        if d:
            game_dates[gid] = d
    print(f"  dated games: {len(game_dates)} / {len(games)}")

    # 2) Snapshot reconstruction + projection (cycle 88b).
    snaps_per_game: Dict[str, Dict[str, Dict[Tuple[int, str], float]]] = {}
    actuals: Dict[str, Dict[Tuple[int, str], float]] = {}
    for gid in games:
        snaps_per_game[gid] = {}
        for point in SNAPSHOT_POINTS:
            snap = v1.build_snapshot(gid, point, qstats_df)
            if snap is None:
                continue
            snaps_per_game[gid][point] = v1.project_snapshot_to_finals(snap)
        actuals[gid] = v1.actuals_for_game(gid, qstats_df)

    # 3) PROD pergame predictions (v2's novelty).
    prod_pergame = prod_pergame_predictions(game_dates, qstats_df)
    print(f"  prod pergame preds: {len(prod_pergame)} (game,player,stat) keys")

    # 4) Aggregate MAE table (paired triples only).
    mae_table = aggregate_mae_v2(snaps_per_game, actuals, prod_pergame)

    # 5) Report.
    report = build_report_v2(mae_table, len(games))
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "retro_inplay_mae_v2_prod_baseline.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"  wrote {out_path}")

    # Console summary.
    for stat in STATS:
        by_kind = mae_table.get(stat, {})
        if "prod_pergame" not in by_kind or "endQ3" not in by_kind:
            continue
        n_pp, mae_pp = by_kind["prod_pergame"]
        n_q3, mae_q3 = by_kind["endQ3"]
        delta = mae_q3 - mae_pp
        sign = "WIN " if delta < 0 else "loss"
        print(f"  {stat:4s}: prod_pergame={mae_pp:.4f}  endQ3={mae_q3:.4f}  "
              f"delta={delta:+.4f}  {sign}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None,
                    help="Limit to first N games (debug).")
    ap.add_argument("--output", default=None,
                    help="Markdown output path (default: "
                         "scripts/_results/retro_inplay_mae_v2_prod_baseline.md)")
    args = ap.parse_args()
    return run(max_games=args.max_games, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
