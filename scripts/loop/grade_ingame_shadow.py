"""grade_ingame_shadow.py -- Post-game grader for the in-game atlas shadow log.

After a game goes final this CLI:
  1. Reads  data/cache/loop/ingame_shadow_<gid>.jsonl  (written by
     scripts/loop/ingame_shadow_logger.py).
  2. Finds the FINAL box from data/live/<gid>_*.json -- selects the snapshot
     with the highest (home_score + away_score) per the project convention of
     using max-total-score as the authoritative final box.
  3. Joins per-(player, stat) actuals from that final snapshot to every logged
     shadow record and buckets records by snapshot_point (endQ1/endQ2/endQ3)
     using the period+clock captured at log time.
  4. Computes per-stat MAE for BASE projection vs ATLAS projection in each
     bucket and prints the delta (negative = atlas better).
  5. Emits an overall verdict: ``LIFT HELD`` when atlas wins more stats than it
     loses; ``NO LIFT`` otherwise (with the count).
  6. Writes a markdown summary to .planning/loop/grade_<gid>_<date>.md.

Snapshot-point assignment (matches eval_atlas_lift_ingame.py convention):
  endQ1  period == 2  AND  clock_remaining_min >= 11.5   (i.e. at/near Q1 end)
  endQ2  period == 3  AND  clock_remaining_min >= 11.5
  endQ3  period == 4  AND  clock_remaining_min >= 11.5
  Mid-quarter records are labelled "midQ<n>" and are NOT graded by this script
  (they are retained in the JSONL for the shadow logger's own use; the retro
  ablation only validates endQ1/2/3).

JSONL record schema (one object per logged snapshot, written by shadow logger):
  {
    "epoch":          <int ms>,          # UTC epoch when snapshot was captured
    "period":         <int 1..4+>,
    "clock":          <str "MM:SS">,
    "game_id":        <str>,
    "rows": [
      {
        "player_id":    <int>,
        "name":         <str>,
        "team":         <str>,
        "stat":         <str>,          # pts/reb/ast/fg3m/stl/blk/tov
        "base_proj":    <float>,        # project_snapshot output
        "atlas_proj":   <float>         # apply_atlas_correction output
      },
      ...
    ]
  }

Run:
    set NBA_OFFLINE=1
    python scripts/loop/grade_ingame_shadow.py --game-id 0042400315
    python scripts/loop/grade_ingame_shadow.py --game-id 0042400315 --shadow-dir data/cache/loop --live-dir data/live
    python scripts/loop/grade_ingame_shadow.py --game-id 0042400315 --quiet
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ── project root on sys.path ───────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("NBA_OFFLINE", "1")

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS = ("endQ1", "endQ2", "endQ3")

# A snapshot at period P with >= this many clock minutes remaining is treated as
# end-of-Q(P-1).  11.5 min gives ~30 s grace from the 12:00 boundary.
_END_OF_Q_CLOCK_MIN = 11.5

_PLANNING_DIR = os.path.join(PROJECT_DIR, ".planning", "loop")


# ── clock helpers ──────────────────────────────────────────────────────────────

def _parse_clock(clock_str: Any) -> float:
    """Parse MM:SS / PT..S / bare float to remaining minutes. Returns 0.0 on failure."""
    if clock_str is None:
        return 0.0
    if isinstance(clock_str, (int, float)):
        return float(clock_str)
    s = str(clock_str).strip()
    if not s:
        return 0.0
    if s.upper().startswith("PT"):
        body = s[2:].upper()
        mins = secs = 0.0
        if "M" in body:
            m_part, _, rest = body.partition("M")
            try:
                mins = float(m_part)
            except ValueError:
                pass
            body = rest
        if "S" in body:
            s_part = body.split("S")[0]
            try:
                secs = float(s_part)
            except ValueError:
                pass
        return mins + secs / 60.0
    sep = ":" if ":" in s else ("." if "." in s else None)
    if sep is None:
        try:
            return float(s)
        except ValueError:
            return 0.0
    head, _, tail = s.partition(sep)
    try:
        return float(head) + (float(tail) if tail else 0.0) / 60.0
    except ValueError:
        return 0.0


def _snapshot_point(period: int, clock_str: Any) -> Optional[str]:
    """Return endQ1/endQ2/endQ3 when a record is at an end-of-quarter boundary.

    Returns None for mid-quarter records (not graded).
    """
    p = int(period or 0)
    rem = _parse_clock(clock_str)
    if p == 2 and rem >= _END_OF_Q_CLOCK_MIN:
        return "endQ1"
    if p == 3 and rem >= _END_OF_Q_CLOCK_MIN:
        return "endQ2"
    if p == 4 and rem >= _END_OF_Q_CLOCK_MIN:
        return "endQ3"
    return None


# ── shadow JSONL reader ────────────────────────────────────────────────────────

def load_shadow_log(shadow_path: str) -> List[Dict[str, Any]]:
    """Read all JSONL records from the shadow log. Tolerates malformed lines."""
    records: List[Dict[str, Any]] = []
    with open(shadow_path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[grade] WARN: line {lineno} malformed ({exc}); skipping")
                continue
            records.append(obj)
    return records


# ── final box loader (max-total-score convention) ──────────────────────────────

def _total_score(snap: Dict[str, Any]) -> int:
    """Sum of home + away score in a snapshot."""
    try:
        return int(snap.get("home_score") or 0) + int(snap.get("away_score") or 0)
    except (TypeError, ValueError):
        return 0


def load_final_box(game_id: str, live_dir: str) -> Optional[Dict[str, Any]]:
    """Find the final box for game_id from data/live/<gid>_*.json.

    Selects the snapshot with the highest (home_score + away_score); breaks
    ties by filename (latest timestamp suffix wins).  Returns None if no
    snapshots are found for this game.
    """
    pattern = os.path.join(live_dir, f"{game_id}_*.json")
    candidates = sorted(glob.glob(pattern))
    if not candidates:
        return None
    best_path: Optional[str] = None
    best_total = -1
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as fh:
                snap = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        t = _total_score(snap)
        if t > best_total:
            best_total = t
            best_path = path
    if best_path is None:
        return None
    with open(best_path, encoding="utf-8") as fh:
        return json.load(fh)


def extract_actuals(final_snap: Dict[str, Any]) -> Dict[Tuple[int, str], float]:
    """Build {(player_id, stat): actual_value} from the final box snapshot."""
    actuals: Dict[Tuple[int, str], float] = {}
    for p in final_snap.get("players") or []:
        try:
            pid = int(p["player_id"])
        except (KeyError, TypeError, ValueError):
            continue
        for stat in STATS:
            v = p.get(stat)
            if v is not None:
                try:
                    actuals[(pid, stat)] = float(v)
                except (TypeError, ValueError):
                    pass
    return actuals


# ── bucket + MAE computation ───────────────────────────────────────────────────

class _Accum:
    """Running accumulator for base/atlas absolute errors per stat."""
    def __init__(self):
        self.base_ae:  Dict[str, List[float]] = defaultdict(list)
        self.atlas_ae: Dict[str, List[float]] = defaultdict(list)
        self.n_matched = 0

    def add(self, stat: str, base_proj: float, atlas_proj: float, actual: float):
        self.base_ae[stat].append(abs(base_proj - actual))
        self.atlas_ae[stat].append(abs(atlas_proj - actual))
        self.n_matched += 1

    def mae_table(self) -> Dict[str, Dict[str, Any]]:
        """Per-stat summary: base_mae, atlas_mae, delta, n."""
        out: Dict[str, Dict[str, Any]] = {}
        for stat in STATS:
            base_list = self.base_ae.get(stat, [])
            atlas_list = self.atlas_ae.get(stat, [])
            n = len(base_list)
            if n == 0:
                out[stat] = {"n": 0, "base_mae": None, "atlas_mae": None, "delta": None}
                continue
            bm = sum(base_list) / n
            am = sum(atlas_list) / n
            out[stat] = {
                "n": n,
                "base_mae": round(bm, 4),
                "atlas_mae": round(am, 4),
                "delta": round(am - bm, 4),  # negative = atlas better
            }
        return out


def grade(
    shadow_records: List[Dict[str, Any]],
    actuals: Dict[Tuple[int, str], float],
    *,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Compute per-snapshot-point MAE comparison and overall verdict.

    Returns a result dict ready for reporting.  Logs to stdout unless quiet.
    """
    # Bucket shadow records by snapshot point (endQ1/Q2/Q3).
    buckets: Dict[str, _Accum] = {pt: _Accum() for pt in SNAPSHOT_POINTS}
    n_records = 0
    n_mid = 0
    n_no_actual = 0

    for rec in shadow_records:
        period = int(rec.get("period") or 0)
        clock  = rec.get("clock", "0:00")
        pt = _snapshot_point(period, clock)

        # The shadow logger writes the per-(player,stat) list under "projections"
        # (key names base_projected_final / atlas_projected_final). Accept the
        # legacy "rows" / base_proj / atlas_proj schema too so the grader works
        # regardless of which logger version produced the JSONL.
        rows = rec.get("rows") or rec.get("projections") or []
        if not rows:
            # Flat record format: one JSONL line per (player, stat) row.
            # Check whether the record itself is a row.
            if "stat" in rec and "player_id" in rec:
                rows = [rec]
            else:
                continue

        for row in rows:
            stat = row.get("stat")
            if stat not in STATS:
                continue
            try:
                pid = int(row["player_id"])
            except (KeyError, TypeError, ValueError):
                continue
            base_raw = row.get("base_proj", row.get("base_projected_final"))
            atlas_raw = row.get("atlas_proj", row.get("atlas_projected_final"))
            try:
                base_proj  = float(base_raw)
                atlas_proj = float(atlas_raw)
            except (TypeError, ValueError):
                continue

            actual = actuals.get((pid, stat))
            n_records += 1
            if pt is None:
                n_mid += 1
                continue
            if actual is None:
                n_no_actual += 1
                continue
            buckets[pt].add(stat, base_proj, atlas_proj, actual)

    # Build result.
    per_snapshot: Dict[str, Any] = {}
    helped_total = evaluated_total = 0
    for pt in SNAPSHOT_POINTS:
        tbl = buckets[pt].mae_table()
        n_helped = sum(1 for v in tbl.values()
                       if v["delta"] is not None and v["delta"] < 0)
        n_eval   = sum(1 for v in tbl.values() if v["delta"] is not None)
        helped_total   += n_helped
        evaluated_total += n_eval
        per_snapshot[pt] = {
            "n_matched": buckets[pt].n_matched,
            "stats_helped": n_helped,
            "stats_evaluated": n_eval,
            "mae_table": tbl,
        }

    verdict = (
        "LIFT HELD"
        if evaluated_total > 0 and helped_total > evaluated_total / 2
        else "NO LIFT"
    )

    return {
        "verdict":         verdict,
        "helped_total":    helped_total,
        "evaluated_total": evaluated_total,
        "n_shadow_records": len(shadow_records),
        "n_graded_rows":   n_records - n_mid,
        "n_mid_quarter":   n_mid,
        "n_no_actual":     n_no_actual,
        "per_snapshot":    per_snapshot,
    }


# ── console printer ────────────────────────────────────────────────────────────

def print_results(game_id: str, result: Dict[str, Any]) -> None:
    verdict = result["verdict"]
    verdict_tag = "OK" if verdict == "LIFT HELD" else "!!"
    print(f"\n[grade] game_id={game_id}  verdict={verdict} [{verdict_tag}]")
    print(f"        atlas helps {result['helped_total']}/{result['evaluated_total']} "
          f"stat-snapshot pairs  (>50% = LIFT HELD)")
    print(f"        shadow records read: {result['n_shadow_records']}  "
          f"graded rows: {result['n_graded_rows']}  "
          f"mid-quarter (skipped): {result['n_mid_quarter']}  "
          f"no-actual (skipped): {result['n_no_actual']}")
    print()
    for pt in SNAPSHOT_POINTS:
        blk = result["per_snapshot"][pt]
        print(f"  {pt}  ({blk['n_matched']} player-stat pairs, "
              f"atlas beats base on {blk['stats_helped']}/{blk['stats_evaluated']} stats)")
        print(f"  {'stat':<6}  {'n':>5}  {'base_mae':>9}  {'atlas_mae':>9}  "
              f"{'delta':>8}  {'winner':>7}")
        print(f"  {'-'*6}  {'-'*5}  {'-'*9}  {'-'*9}  {'-'*8}  {'-'*7}")
        tbl = blk["mae_table"]
        for stat in STATS:
            v = tbl.get(stat, {})
            if v.get("delta") is None:
                print(f"  {stat:<6}  {'--':>5}  {'--':>9}  {'--':>9}  {'--':>8}  {'--':>7}")
                continue
            d = v["delta"]
            winner = "ATLAS" if d < 0 else ("BASE " if d > 0 else "TIE  ")
            print(f"  {stat:<6}  {v['n']:>5}  {v['base_mae']:>9.4f}  "
                  f"{v['atlas_mae']:>9.4f}  {d:>+8.4f}  {winner:>7}")
        print()


# ── markdown summary ───────────────────────────────────────────────────────────

def _markdown(game_id: str, result: Dict[str, Any], run_ts: str) -> str:
    L: List[str] = []
    verdict = result["verdict"]
    L.append(f"# In-game atlas shadow grade: {game_id}")
    L.append("")
    L.append(f"- run: {run_ts}")
    L.append(f"- verdict: **{verdict}**  "
              f"(atlas wins {result['helped_total']}/{result['evaluated_total']} "
              f"stat-snapshot pairs; >50% = LIFT HELD)")
    L.append(f"- shadow records: {result['n_shadow_records']}  "
              f"graded rows: {result['n_graded_rows']}  "
              f"mid-quarter (skipped): {result['n_mid_quarter']}")
    L.append("")
    L.append("Delta = MAE(atlas) - MAE(base); **negative = atlas better**.")
    L.append("")
    for pt in SNAPSHOT_POINTS:
        blk = result["per_snapshot"][pt]
        L.append(f"## {pt}  (n_pairs={blk['n_matched']}, "
                 f"atlas wins {blk['stats_helped']}/{blk['stats_evaluated']})")
        L.append("")
        L.append("| stat | n | base_mae | atlas_mae | delta | winner |")
        L.append("|------|---|----------|-----------|-------|--------|")
        tbl = blk["mae_table"]
        for stat in STATS:
            v = tbl.get(stat, {})
            if v.get("delta") is None:
                L.append(f"| {stat} | -- | -- | -- | -- | -- |")
                continue
            d = v["delta"]
            winner = "ATLAS" if d < 0 else ("BASE" if d > 0 else "TIE")
            L.append(f"| {stat} | {v['n']} | {v['base_mae']:.4f} | "
                     f"{v['atlas_mae']:.4f} | {d:+.4f} | {winner} |")
        L.append("")
    L.append("## Context")
    L.append("")
    L.append(
        "The retro ablation (`scripts/loop/eval_atlas_lift_ingame.py`) showed the atlas "
        "corrector reduces endQ1 PTS MAE by ~0.627 (3/3 folds) and helps REB/AST/BLK "
        "also 3/3.  This per-game grade validates whether that retro lift holds on a "
        "real live game."
    )
    L.append("")
    L.append("Shadow mode is gated behind `CV_INGAME_ATLAS` (default OFF). "
             "To enable on the next game night: `set CV_INGAME_ATLAS=1` before starting "
             "the live poller. To flip to production (atlas replaces base): TBD pending "
             "additional shadow validation.")
    L.append("")
    return "\n".join(L)


# ── main ───────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--game-id", required=True,
                    help="NBA game_id, e.g. 0042400315")
    ap.add_argument("--shadow-dir", default=os.path.join(PROJECT_DIR, "data", "cache", "loop"),
                    help="Directory containing ingame_shadow_<gid>.jsonl "
                         "(default: data/cache/loop)")
    ap.add_argument("--live-dir", default=os.path.join(PROJECT_DIR, "data", "live"),
                    help="Directory containing <gid>_*.json live snapshots "
                         "(default: data/live)")
    ap.add_argument("--out-dir", default=_PLANNING_DIR,
                    help="Directory for the markdown summary "
                         "(default: .planning/loop)")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress per-stat console table (still writes markdown)")
    args = ap.parse_args(argv)

    game_id = args.game_id.strip()
    shadow_path = os.path.join(args.shadow_dir, f"ingame_shadow_{game_id}.jsonl")

    # -- load shadow log -------------------------------------------------------
    if not os.path.exists(shadow_path):
        print(f"[grade] ERROR: shadow log not found: {shadow_path}")
        print(f"        Run ingame_shadow_logger.py --game-id {game_id} first.")
        return 1
    print(f"[grade] reading shadow log: {shadow_path}")
    shadow_records = load_shadow_log(shadow_path)
    if not shadow_records:
        print("[grade] ERROR: shadow log is empty -- nothing to grade.")
        return 1
    print(f"[grade] loaded {len(shadow_records)} JSONL records")

    # -- load final box --------------------------------------------------------
    final_snap = load_final_box(game_id, args.live_dir)
    if final_snap is None:
        print(f"[grade] ERROR: no live snapshots found for {game_id} in {args.live_dir}")
        return 1
    total = _total_score(final_snap)
    print(f"[grade] final box: {final_snap.get('home_team')} "
          f"{final_snap.get('home_score')} - {final_snap.get('away_team')} "
          f"{final_snap.get('away_score')}  (total={total}, "
          f"period={final_snap.get('period')}, clock={final_snap.get('clock')})")

    actuals = extract_actuals(final_snap)
    print(f"[grade] actuals extracted: {len(actuals)} (player,stat) pairs")

    # -- grade -----------------------------------------------------------------
    result = grade(shadow_records, actuals, quiet=args.quiet)

    if not args.quiet:
        print_results(game_id, result)

    # -- write markdown --------------------------------------------------------
    os.makedirs(args.out_dir, exist_ok=True)
    run_ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_tag = run_ts[:10].replace("-", "")
    md_path = os.path.join(args.out_dir, f"grade_{game_id}_{date_tag}.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(_markdown(game_id, result, run_ts))
    print(f"[grade] summary -> {md_path}")

    # Final verdict line -- easy to grep.
    v = result["verdict"]
    helped = result["helped_total"]
    total_eval = result["evaluated_total"]
    print(f"[grade] RESULT: {v}  ({helped}/{total_eval} stat-snapshot pairs atlas wins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
