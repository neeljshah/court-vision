"""grade_unified_shadow.py -- Post-game grader for the UNIFIED in-game shadow log.

After a game goes final this CLI grades the THREE unified components logged by
``unified_shadow_logger.py`` (PRODUCTION vs UNIFIED, both vs the real actuals):

  1. PLAYER LINES -- per (stat, game-time bucket): MAE of PRODUCTION
     ``project_snapshot`` projection vs MAE of the UNIFIED SBS-v2 projection, vs
     the actual per-(player, stat) finals. Verdict per (stat, bucket) and overall.
  2. FINAL SCORE  -- per game-time bucket: MAE of UNIFIED possession-sim
     ``home/away_final_mean`` vs the actual final home/away scores, AND the same
     for PRODUCTION *iff* the production payload carried a team-score head (the
     default production in-game projector does NOT, so that column is marked
     "n/a"). Verdict on the unified score head's absolute MAE + (when available)
     vs production.
  3. WIN PROB     -- per game-time bucket: Brier + LogLoss of the UNIFIED
     ``home_win_prob`` against the realized home-win outcome (1/0), AND the same
     for PRODUCTION iff carried. Verdict on the unified win-prob calibration +
     (when available) vs production.

It reads:
  * data/cache/ingame/unified_shadow_<gid>.jsonl  (from unified_shadow_logger.py).
  * the FINAL box from data/live/<gid>_*.json -- the snapshot with the highest
    (home_score + away_score) (project convention for the authoritative final
    box) -- for per-player actuals AND the actual final team score / home-win.

De-dup: one row per (bucket, pid, stat) and one team row per bucket -- the LAST
logged snapshot in each bucket (closest to the boundary) -- so a 200-snapshot
game does not weight one bucket 100x. This mirrors grade_sbs_shadow.py.

A single game is noisy. Verdicts are an honest single-game read-out at the SAME
held-out bar as the retro (unified heads trained on games strictly before this
game's date); promote a component only after it holds across several shadow
nights. Per-EVENT accuracy (the display ticks per-second; accuracy is graded per
event/snapshot).

Writes a markdown summary to .planning/ingame/unified_grade_<gid>_<date>.md.

Run:
    set NBA_OFFLINE=1
    python scripts/ingame/grade_unified_shadow.py --game-id 0042500317
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_OFFLINE", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from src.ingame.sbs_shadow import PLAYER_STATS as STATS, GRID_LABELS  # noqa: E402

# Bucket order for printing (game-time ascending).
BUCKET_ORDER: Tuple[str, ...] = tuple(GRID_LABELS[s] for s in sorted(GRID_LABELS))

SHADOW_DIR = os.path.join(PROJECT_DIR, "data", "cache", "ingame")
LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")
PLAN_DIR = os.path.join(PROJECT_DIR, ".planning", "ingame")

_EPS = 1e-12


# -- shadow JSONL reader ------------------------------------------------------ #
def load_shadow_log(shadow_path: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with open(shadow_path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"[grade] WARN line {lineno} malformed ({exc}); skip")
    return records


# -- final box (max-total-score convention) ----------------------------------- #
def _total_score(snap: Dict[str, Any]) -> int:
    try:
        return int(snap.get("home_score") or 0) + int(snap.get("away_score") or 0)
    except (TypeError, ValueError):
        return 0


def load_final_box(game_id: str, live_dir: str) -> Optional[Dict[str, Any]]:
    candidates = sorted(glob.glob(os.path.join(live_dir, f"{game_id}_*.json")))
    if not candidates:
        return None
    best_path, best_total = None, -1
    for path in candidates:
        try:
            snap = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        t = _total_score(snap)
        if t > best_total:
            best_total, best_path = t, path
    if best_path is None:
        return None
    return json.load(open(best_path, encoding="utf-8"))


def extract_player_actuals(final_snap: Dict[str, Any]) -> Dict[Tuple[int, str], float]:
    actuals: Dict[Tuple[int, str], float] = {}
    for p in final_snap.get("players") or []:
        try:
            pid = int(p["player_id"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            if float(p.get("min", 0) or 0) <= 0:
                continue
        except (TypeError, ValueError):
            pass
        for stat in STATS:
            v = p.get(stat)
            if v is not None:
                try:
                    actuals[(pid, stat)] = float(v)
                except (TypeError, ValueError):
                    pass
    return actuals


def extract_team_actuals(final_snap: Dict[str, Any]
                         ) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    """(actual_home_final, actual_away_final, home_win_flag 1/0/None)."""
    try:
        h = float(final_snap.get("home_score"))
        a = float(final_snap.get("away_score"))
    except (TypeError, ValueError):
        return None, None, None
    home_win = 1 if h > a else (0 if h < a else None)
    return h, a, home_win


# -- player-line component ---------------------------------------------------- #
class _PlayerAccum:
    def __init__(self):
        self.prod: Dict[str, List[float]] = defaultdict(list)
        self.uni: Dict[str, List[float]] = defaultdict(list)
        self.n = 0

    def add(self, stat, prod, uni, actual):
        if prod is not None:
            self.prod[stat].append(abs(prod - actual))
        self.uni[stat].append(abs(uni - actual))
        self.n += 1

    def table(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for stat in STATS:
            nu = len(self.uni.get(stat, []))
            if nu == 0:
                out[stat] = {"n": 0, "prod_mae": None, "uni_mae": None, "delta": None}
                continue
            np_ = len(self.prod.get(stat, []))
            pm = (sum(self.prod[stat]) / np_) if np_ else None
            um = sum(self.uni[stat]) / nu
            out[stat] = {
                "n": nu,
                "prod_mae": (round(pm, 4) if pm is not None else None),
                "uni_mae": round(um, 4),
                # negative = unified better than production
                "delta": (round(um - pm, 4) if pm is not None else None),
            }
        return out


def grade_player_lines(records, actuals) -> Dict[str, Any]:
    buckets: Dict[str, _PlayerAccum] = defaultdict(_PlayerAccum)
    latest: Dict[Tuple[str, int, str], Tuple[Optional[float], float]] = {}
    n_rows = n_no_actual = n_no_bucket = 0
    for rec in records:
        bucket = rec.get("grid_bucket")
        for row in rec.get("projections") or []:
            stat = row.get("stat")
            if stat not in STATS:
                continue
            try:
                pid = int(row["player_id"])
            except (KeyError, TypeError, ValueError):
                continue
            n_rows += 1
            if not bucket:
                n_no_bucket += 1
                continue
            if (pid, stat) not in actuals:
                n_no_actual += 1
                continue
            uni_raw = row.get("unified_proj")
            if uni_raw is None:
                continue
            try:
                uni = float(uni_raw)
            except (TypeError, ValueError):
                continue
            prod_raw = row.get("prod_proj")
            prod: Optional[float]
            try:
                prod = float(prod_raw) if prod_raw is not None else None
            except (TypeError, ValueError):
                prod = None
            latest[(bucket, pid, stat)] = (prod, uni)

    for (bucket, pid, stat), (prod, uni) in latest.items():
        buckets[bucket].add(stat, prod, uni, actuals[(pid, stat)])

    per_bucket: Dict[str, Any] = {}
    uni_wins = uni_eval = 0
    for bucket in BUCKET_ORDER:
        if bucket not in buckets:
            continue
        tbl = buckets[bucket].table()
        nh = sum(1 for v in tbl.values() if v["delta"] is not None and v["delta"] < 0)
        ne = sum(1 for v in tbl.values() if v["delta"] is not None)
        uni_wins += nh
        uni_eval += ne
        per_bucket[bucket] = {"n_pairs": buckets[bucket].n,
                              "uni_wins": nh, "uni_evaluated": ne, "table": tbl}

    if uni_eval == 0:
        verdict = "PLAYER: NO PROD BASELINE (cannot compare)"
    elif uni_wins > uni_eval / 2:
        verdict = "PLAYER: UNIFIED LIFT"
    else:
        verdict = "PLAYER: NO UNIFIED LIFT"
    return {
        "verdict": verdict,
        "uni_wins": uni_wins,
        "uni_evaluated": uni_eval,
        "n_rows_seen": n_rows,
        "n_no_actual": n_no_actual,
        "n_no_bucket": n_no_bucket,
        "per_bucket": per_bucket,
    }


# -- team-score + win-prob components ----------------------------------------- #
def _brier(p: float, y: int) -> float:
    return (p - y) ** 2


def _logloss(p: float, y: int) -> float:
    p = min(1.0 - _EPS, max(_EPS, p))
    return -(y * math.log(p) + (1 - y) * math.log(1.0 - p))


def grade_team(records, actual_home, actual_away, home_win) -> Dict[str, Any]:
    """Per-bucket final-score MAE + win-prob Brier/LogLoss, unified vs production.

    Uses the LAST logged snapshot per bucket (closest to the boundary).
    """
    latest: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        bucket = rec.get("grid_bucket")
        if not bucket:
            continue
        team = rec.get("team")
        if isinstance(team, dict):
            latest[bucket] = team  # later record in same bucket overwrites

    have_score = actual_home is not None and actual_away is not None
    have_win = home_win is not None

    per_bucket: Dict[str, Any] = {}
    # accumulate overall (mean across evaluated buckets)
    uni_score_maes: List[float] = []
    prod_score_maes: List[float] = []
    uni_briers: List[float] = []
    prod_briers: List[float] = []
    uni_loglosses: List[float] = []
    prod_loglosses: List[float] = []
    prod_has_score = prod_has_wp = False

    for bucket in BUCKET_ORDER:
        team = latest.get(bucket)
        if not team:
            continue
        cell: Dict[str, Any] = {}
        # --- final score ---
        if have_score:
            uh = team.get("unified_home_final")
            ua = team.get("unified_away_final")
            if uh is not None and ua is not None:
                mae = (abs(float(uh) - actual_home)
                       + abs(float(ua) - actual_away)) / 2.0
                cell["uni_score_mae"] = round(mae, 4)
                uni_score_maes.append(mae)
            ph = team.get("prod_home_final")
            pa = team.get("prod_away_final")
            if ph is not None and pa is not None:
                prod_has_score = True
                pmae = (abs(float(ph) - actual_home)
                        + abs(float(pa) - actual_away)) / 2.0
                cell["prod_score_mae"] = round(pmae, 4)
                prod_score_maes.append(pmae)
            else:
                cell["prod_score_mae"] = None
        # --- win prob ---
        if have_win:
            uwp = team.get("unified_home_win_prob")
            if uwp is not None:
                b = _brier(float(uwp), home_win)
                ll = _logloss(float(uwp), home_win)
                cell["uni_home_win_prob"] = round(float(uwp), 4)
                cell["uni_brier"] = round(b, 4)
                cell["uni_logloss"] = round(ll, 4)
                uni_briers.append(b)
                uni_loglosses.append(ll)
            pwp = team.get("prod_home_win_prob")
            if pwp is not None:
                prod_has_wp = True
                pb = _brier(float(pwp), home_win)
                pll = _logloss(float(pwp), home_win)
                cell["prod_home_win_prob"] = round(float(pwp), 4)
                cell["prod_brier"] = round(pb, 4)
                cell["prod_logloss"] = round(pll, 4)
                prod_briers.append(pb)
                prod_loglosses.append(pll)
            else:
                cell["prod_home_win_prob"] = None
        if cell:
            per_bucket[bucket] = cell

    def _mean(xs):
        return round(sum(xs) / len(xs), 4) if xs else None

    score_verdict = "SCORE: NO DATA"
    if uni_score_maes:
        if prod_score_maes:
            d = _mean(uni_score_maes) - _mean(prod_score_maes)
            score_verdict = ("SCORE: UNIFIED BEATS PROD" if d < 0
                             else "SCORE: PROD BEATS UNIFIED")
        else:
            score_verdict = ("SCORE: UNIFIED ONLY (prod has no team-score head; "
                             "absolute MAE reported)")

    wp_verdict = "WINPROB: NO DATA"
    if uni_briers:
        if prod_briers:
            d = _mean(uni_briers) - _mean(prod_briers)
            wp_verdict = ("WINPROB: UNIFIED BEATS PROD" if d < 0
                          else "WINPROB: PROD BEATS UNIFIED")
        else:
            wp_verdict = ("WINPROB: UNIFIED ONLY (prod has no win-prob head; "
                          "absolute Brier/LogLoss reported)")

    return {
        "have_score": have_score,
        "have_win": have_win,
        "actual_home": actual_home,
        "actual_away": actual_away,
        "home_win": home_win,
        "prod_has_score": prod_has_score,
        "prod_has_wp": prod_has_wp,
        "score_verdict": score_verdict,
        "wp_verdict": wp_verdict,
        "uni_score_mae_mean": _mean(uni_score_maes),
        "prod_score_mae_mean": _mean(prod_score_maes),
        "uni_brier_mean": _mean(uni_briers),
        "prod_brier_mean": _mean(prod_briers),
        "uni_logloss_mean": _mean(uni_loglosses),
        "prod_logloss_mean": _mean(prod_loglosses),
        "per_bucket": per_bucket,
    }


# -- printer ------------------------------------------------------------------ #
def print_results(game_id: str, player: Dict[str, Any], team: Dict[str, Any]) -> None:
    print(f"\n[grade] game_id={game_id}  UNIFIED shadow grade")
    print(f"  {player['verdict']}")
    print(f"  {team['score_verdict']}")
    print(f"  {team['wp_verdict']}")
    print()

    # player lines
    print("== PLAYER LINES (prod vs unified-v2, vs actual finals) ==")
    print(f"   unified beats prod on {player['uni_wins']}/{player['uni_evaluated']} "
          f"(stat,bucket) cells; rows seen {player['n_rows_seen']}, "
          f"no-actual {player['n_no_actual']}, no-bucket {player['n_no_bucket']}")
    for bucket in BUCKET_ORDER:
        blk = player["per_bucket"].get(bucket)
        if not blk:
            continue
        print(f"  {bucket}  ({blk['n_pairs']} pairs, "
              f"unified beats prod {blk['uni_wins']}/{blk['uni_evaluated']})")
        print(f"  {'stat':<6}{'n':>5}{'prod':>9}{'unified':>9}{'delta':>9}{'win':>7}")
        for stat in STATS:
            d = blk["table"].get(stat, {})
            if d.get("uni_mae") is None:
                continue
            pm = d["prod_mae"]
            dl = d["delta"]
            pm_s = f"{pm:>9.4f}" if pm is not None else f"{'n/a':>9}"
            dl_s = f"{dl:>+9.4f}" if dl is not None else f"{'n/a':>9}"
            win = ("unified" if (dl is not None and dl < 0)
                   else ("prod" if (dl is not None and dl > 0) else "--"))
            print(f"  {stat:<6}{d['n']:>5}{pm_s}{d['uni_mae']:>9.4f}{dl_s}{win:>7}")
        print()

    # team score + win prob
    print("== FINAL SCORE + WIN PROB (unified possession-sim, vs actual) ==")
    if team["have_score"]:
        print(f"   actual final: home {team['actual_home']} - away {team['actual_away']}"
              f"  (home_win={team['home_win']})")
    else:
        print("   actual final score unavailable -> score/winprob NOT graded")
    print(f"   {'bucket':<20}{'uScoreMAE':>11}{'pScoreMAE':>11}"
          f"{'uBrier':>9}{'pBrier':>9}{'uLogL':>9}{'pLogL':>9}")
    for bucket in BUCKET_ORDER:
        c = team["per_bucket"].get(bucket)
        if not c:
            continue

        def g(k):
            v = c.get(k)
            return f"{v:>9.4f}" if isinstance(v, (int, float)) else f"{'--':>9}"

        def g11(k):
            v = c.get(k)
            return f"{v:>11.4f}" if isinstance(v, (int, float)) else f"{'--':>11}"

        print(f"   {bucket:<20}{g11('uni_score_mae')}{g11('prod_score_mae')}"
              f"{g('uni_brier')}{g('prod_brier')}{g('uni_logloss')}{g('prod_logloss')}")
    print()
    print(f"   means: uni_score_mae={team['uni_score_mae_mean']} "
          f"prod_score_mae={team['prod_score_mae_mean']} | "
          f"uni_brier={team['uni_brier_mean']} prod_brier={team['prod_brier_mean']} | "
          f"uni_logloss={team['uni_logloss_mean']} prod_logloss={team['prod_logloss_mean']}")
    if not team["prod_has_score"]:
        print("   note: production in-game default carries NO team-score head "
              "(prod columns n/a; unified absolute MAE is the read-out).")
    if not team["prod_has_wp"]:
        print("   note: production in-game default carries NO win-prob head "
              "(prod columns n/a; unified absolute Brier/LogLoss is the read-out).")


# -- markdown ----------------------------------------------------------------- #
def _markdown(game_id: str, player: Dict[str, Any], team: Dict[str, Any],
              run_ts: str) -> str:
    L: List[str] = [f"# Unified in-game shadow grade: {game_id}", ""]
    L.append(f"- run: {run_ts}")
    L.append(f"- **{player['verdict']}**")
    L.append(f"- **{team['score_verdict']}**")
    L.append(f"- **{team['wp_verdict']}**")
    L.append("")
    L.append("Verdicts are a single-game held-out read-out (unified heads trained "
             "on games strictly before this game's date). A single game is noisy -- "
             "promote a component only after it holds across several shadow nights. "
             "Accuracy is per-EVENT (the display ticks per-second).")
    L.append("")

    # player lines
    L.append("## Player lines (production vs unified SBS-v2)")
    L.append("")
    L.append(f"unified beats production on {player['uni_wins']}/"
             f"{player['uni_evaluated']} (stat,bucket) cells. "
             f"Delta = MAE(unified) - MAE(prod); **negative = unified better**.")
    L.append("")
    for bucket in BUCKET_ORDER:
        blk = player["per_bucket"].get(bucket)
        if not blk:
            continue
        L.append(f"### {bucket}  (n_pairs={blk['n_pairs']}, "
                 f"unified wins {blk['uni_wins']}/{blk['uni_evaluated']})")
        L.append("")
        L.append("| stat | n | prod | unified | delta | winner |")
        L.append("|------|---|------|---------|-------|--------|")
        for stat in STATS:
            d = blk["table"].get(stat, {})
            if d.get("uni_mae") is None:
                continue
            pm = d["prod_mae"]
            dl = d["delta"]
            pm_s = f"{pm:.4f}" if pm is not None else "n/a"
            dl_s = f"{dl:+.4f}" if dl is not None else "n/a"
            win = ("unified" if (dl is not None and dl < 0)
                   else ("prod" if (dl is not None and dl > 0) else "--"))
            L.append(f"| {stat} | {d['n']} | {pm_s} | {d['uni_mae']:.4f} | "
                     f"{dl_s} | {win} |")
        L.append("")

    # team
    L.append("## Final score + win prob (unified possession-sim)")
    L.append("")
    if team["have_score"]:
        L.append(f"Actual final: home **{team['actual_home']}** - away "
                 f"**{team['actual_away']}** (home_win={team['home_win']}).")
    else:
        L.append("Actual final score unavailable -> score/win-prob NOT graded.")
    L.append("")
    L.append("| bucket | uni score MAE | prod score MAE | uni Brier | prod Brier "
             "| uni LogLoss | prod LogLoss |")
    L.append("|--------|---------------|----------------|-----------|------------"
             "|-------------|--------------|")
    for bucket in BUCKET_ORDER:
        c = team["per_bucket"].get(bucket)
        if not c:
            continue

        def cell(k):
            v = c.get(k)
            return f"{v:.4f}" if isinstance(v, (int, float)) else "--"

        L.append(f"| {bucket} | {cell('uni_score_mae')} | {cell('prod_score_mae')} "
                 f"| {cell('uni_brier')} | {cell('prod_brier')} "
                 f"| {cell('uni_logloss')} | {cell('prod_logloss')} |")
    L.append("")
    L.append(f"- means: uni_score_mae={team['uni_score_mae_mean']}, "
             f"prod_score_mae={team['prod_score_mae_mean']}")
    L.append(f"- means: uni_brier={team['uni_brier_mean']}, "
             f"prod_brier={team['prod_brier_mean']}; "
             f"uni_logloss={team['uni_logloss_mean']}, "
             f"prod_logloss={team['prod_logloss_mean']}")
    if not team["prod_has_score"]:
        L.append("- note: production in-game default carries **no team-score head** "
                 "(prod column n/a; unified absolute MAE is the read-out).")
    if not team["prod_has_wp"]:
        L.append("- note: production in-game default carries **no win-prob head** "
                 "(prod column n/a; unified absolute Brier/LogLoss is the read-out).")
    L.append("")
    L.append("## Context")
    L.append("")
    L.append("Retro: the SBS-v2 player head beats the production snapshot projector "
             "midQ1->midQ3 (half PTS MAE 4.11 -> 3.43); the possession sim beats "
             "snapshot_pace on final score at all game-times and beats the sigmoid "
             "on Brier/LogLoss from mid-game on (decisive late). This per-game grade "
             "checks whether that lift shows on ONE real game.")
    L.append("")
    L.append("Shadow mode is gated behind `CV_INGAME_SBS` (default OFF; "
             "`project_unified` is a byte-identical pass-through when off). To shadow "
             "on the next game night: `python scripts/ingame/unified_shadow_logger.py "
             "--game-id <gid> --watch`, then grade after FINAL.")
    L.append("")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-id", required=True, help="NBA game_id, e.g. 0042500317")
    ap.add_argument("--shadow-dir", default=SHADOW_DIR)
    ap.add_argument("--live-dir", default=LIVE_DIR)
    ap.add_argument("--out-dir", default=PLAN_DIR)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    game_id = args.game_id.strip()
    shadow_path = os.path.join(args.shadow_dir, f"unified_shadow_{game_id}.jsonl")
    if not os.path.exists(shadow_path):
        print(f"[grade] ERROR: shadow log not found: {shadow_path}")
        print(f"        Run unified_shadow_logger.py --game-id {game_id} first.")
        return 1
    print(f"[grade] reading shadow log: {shadow_path}")
    records = load_shadow_log(shadow_path)
    if not records:
        print("[grade] ERROR: shadow log is empty.")
        return 1
    print(f"[grade] loaded {len(records)} JSONL records")

    final_snap = load_final_box(game_id, args.live_dir)
    if final_snap is None:
        print(f"[grade] ERROR: no live snapshots for {game_id} in {args.live_dir}")
        return 1
    print(f"[grade] final box: {final_snap.get('home_team')} "
          f"{final_snap.get('home_score')} - {final_snap.get('away_team')} "
          f"{final_snap.get('away_score')}  (period={final_snap.get('period')}, "
          f"clock={final_snap.get('clock')})")

    player_actuals = extract_player_actuals(final_snap)
    actual_home, actual_away, home_win = extract_team_actuals(final_snap)
    print(f"[grade] actuals: {len(player_actuals)} (player,stat) pairs; "
          f"team final={actual_home}-{actual_away} home_win={home_win}")

    player = grade_player_lines(records, player_actuals)
    team = grade_team(records, actual_home, actual_away, home_win)

    if not args.quiet:
        print_results(game_id, player, team)

    os.makedirs(args.out_dir, exist_ok=True)
    run_ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_tag = run_ts[:10].replace("-", "")
    md_path = os.path.join(args.out_dir, f"unified_grade_{game_id}_{date_tag}.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(_markdown(game_id, player, team, run_ts))
    print(f"[grade] summary -> {md_path}")
    print(f"[grade] RESULT: {player['verdict']} | {team['score_verdict']} | "
          f"{team['wp_verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
