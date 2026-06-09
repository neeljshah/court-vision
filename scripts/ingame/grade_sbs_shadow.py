"""grade_sbs_shadow.py -- Post-game grader for the v2 SBS player-line shadow log.

After a game goes final this CLI:
  1. Reads  data/cache/ingame/sbs_shadow_<gid>.jsonl  (from sbs_shadow_logger.py).
  2. Finds the FINAL box from data/live/<gid>_*.json -- the snapshot with the
     highest (home_score + away_score) (project convention for the authoritative
     final box), and extracts per-(player, stat) actual finals from its players.
  3. Buckets every logged shadow row by its captured game-time grid bucket
     (midQ1/endQ1/.../midQ4) and computes, per (stat, bucket), MAE for:
        * BASE   (production box-snapshot projector)
        * V2     (raw v2 player-line head)
        * GATED  (server-equivalent under the validated game-time gate)
     all vs the actual finals.
  4. PROMOTES a (stat, bucket) cell ONLY on a real held-out win: V2 strictly
     beats BASE on this game in that cell (delta < 0). This is a single-game
     read-out -- it is the SAME held-out bar as the retro (v2 trained on games
     strictly before this game's date), but a single game is noisy; the promotion
     list is advisory until it holds across several shadow nights.
  5. Writes a markdown summary to .planning/ingame/sbs_grade_<gid>_<date>.md.

This mirrors scripts/loop/grade_ingame_shadow.py (the atlas-shadow grader) but
grades the v2 player-line head (base vs v2 vs gated) instead of the atlas
corrector, and reads/writes the SBS paths.

Run:
    set NBA_OFFLINE=1
    python scripts/ingame/grade_sbs_shadow.py --game-id 0042500317
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


# ── shadow JSONL reader ──────────────────────────────────────────────────────
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


# ── final box (max-total-score convention) ───────────────────────────────────
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


def extract_actuals(final_snap: Dict[str, Any]) -> Dict[Tuple[int, str], float]:
    actuals: Dict[Tuple[int, str], float] = {}
    for p in final_snap.get("players") or []:
        try:
            pid = int(p["player_id"])
        except (KeyError, TypeError, ValueError):
            continue
        # only grade players who actually played (final min > 0)
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


# ── bucket accumulator ────────────────────────────────────────────────────────
class _Accum:
    def __init__(self):
        self.base: Dict[str, List[float]] = defaultdict(list)
        self.v2: Dict[str, List[float]] = defaultdict(list)
        self.gated: Dict[str, List[float]] = defaultdict(list)
        self.n = 0

    def add(self, stat, base, v2, gated, actual):
        self.base[stat].append(abs(base - actual))
        self.v2[stat].append(abs(v2 - actual))
        self.gated[stat].append(abs(gated - actual))
        self.n += 1

    def table(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for stat in STATS:
            n = len(self.base.get(stat, []))
            if n == 0:
                out[stat] = {"n": 0, "base_mae": None, "v2_mae": None,
                             "gated_mae": None, "delta_v2": None, "delta_gated": None}
                continue
            bm = sum(self.base[stat]) / n
            vm = sum(self.v2[stat]) / n
            gm = sum(self.gated[stat]) / n
            out[stat] = {
                "n": n,
                "base_mae": round(bm, 4),
                "v2_mae": round(vm, 4),
                "gated_mae": round(gm, 4),
                "delta_v2": round(vm - bm, 4),     # negative = v2 better
                "delta_gated": round(gm - bm, 4),  # negative = gated better
            }
        return out


def grade(records: List[Dict[str, Any]],
          actuals: Dict[Tuple[int, str], float]) -> Dict[str, Any]:
    buckets: Dict[str, _Accum] = defaultdict(_Accum)
    # de-dup: one (bucket, pid, stat) per game -> use the LAST logged snapshot in
    # that bucket (closest to the boundary), so a 200-snapshot game does not weight
    # one bucket 100x. Keyed (bucket, pid, stat) -> (base, v2, gated).
    latest: Dict[Tuple[str, int, str], Tuple[float, float, float]] = {}
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
            try:
                base = float(row["base_proj"])
                v2 = float(row["v2_proj"])
                gated = float(row.get("gated_proj", base))
            except (KeyError, TypeError, ValueError):
                continue
            latest[(bucket, pid, stat)] = (base, v2, gated)

    for (bucket, pid, stat), (base, v2, gated) in latest.items():
        buckets[bucket].add(stat, base, v2, gated, actuals[(pid, stat)])

    per_bucket: Dict[str, Any] = {}
    promote: List[Dict[str, Any]] = []
    v2_wins = v2_eval = 0
    for bucket in BUCKET_ORDER:
        if bucket not in buckets:
            continue
        tbl = buckets[bucket].table()
        nh = sum(1 for v in tbl.values()
                 if v["delta_v2"] is not None and v["delta_v2"] < 0)
        ne = sum(1 for v in tbl.values() if v["delta_v2"] is not None)
        v2_wins += nh
        v2_eval += ne
        for stat, v in tbl.items():
            if v["delta_v2"] is not None and v["delta_v2"] < 0:
                promote.append({"bucket": bucket, "stat": stat,
                                "delta_v2": v["delta_v2"], "n": v["n"]})
        per_bucket[bucket] = {"n_pairs": buckets[bucket].n,
                              "v2_wins": nh, "v2_evaluated": ne, "table": tbl}

    verdict = ("V2 LIFT" if v2_eval > 0 and v2_wins > v2_eval / 2 else "NO V2 LIFT")
    return {
        "verdict": verdict,
        "v2_wins": v2_wins,
        "v2_evaluated": v2_eval,
        "n_shadow_records": len(records),
        "n_rows_seen": n_rows,
        "n_no_actual": n_no_actual,
        "n_no_bucket": n_no_bucket,
        "promote": sorted(promote, key=lambda x: x["delta_v2"]),
        "per_bucket": per_bucket,
    }


# ── printer ────────────────────────────────────────────────────────────────────
def print_results(game_id: str, result: Dict[str, Any]) -> None:
    v = result["verdict"]
    tag = "OK" if v == "V2 LIFT" else "!!"
    print(f"\n[grade] game_id={game_id}  verdict={v} [{tag}]")
    print(f"        v2 beats base on {result['v2_wins']}/{result['v2_evaluated']} "
          f"(stat,bucket) cells held-out  (>50% = V2 LIFT)")
    print(f"        shadow records: {result['n_shadow_records']}  "
          f"rows seen: {result['n_rows_seen']}  "
          f"no-actual: {result['n_no_actual']}  no-bucket: {result['n_no_bucket']}")
    print()
    for bucket in BUCKET_ORDER:
        blk = result["per_bucket"].get(bucket)
        if not blk:
            continue
        print(f"  {bucket}  ({blk['n_pairs']} player-stat pairs, "
              f"v2 beats base on {blk['v2_wins']}/{blk['v2_evaluated']})")
        print(f"  {'stat':<6}{'n':>5}{'base':>9}{'v2':>9}{'gated':>9}"
              f"{'dV2':>9}{'win':>6}")
        for stat in STATS:
            d = blk["table"].get(stat, {})
            if d.get("delta_v2") is None:
                print(f"  {stat:<6}{'--':>5}{'--':>9}{'--':>9}{'--':>9}{'--':>9}{'--':>6}")
                continue
            win = "V2" if d["delta_v2"] < 0 else ("base" if d["delta_v2"] > 0 else "tie")
            print(f"  {stat:<6}{d['n']:>5}{d['base_mae']:>9.4f}{d['v2_mae']:>9.4f}"
                  f"{d['gated_mae']:>9.4f}{d['delta_v2']:>+9.4f}{win:>6}")
        print()
    if result["promote"]:
        print("  PROMOTE candidates (v2 < base this game):")
        for p in result["promote"]:
            print(f"    {p['bucket']:<18} {p['stat']:<5} dV2={p['delta_v2']:+.4f} n={p['n']}")
    else:
        print("  PROMOTE candidates: none (v2 did not beat base in any cell)")


def _markdown(game_id: str, result: Dict[str, Any], run_ts: str) -> str:
    L: List[str] = [f"# SBS v2 player-line shadow grade: {game_id}", ""]
    L.append(f"- run: {run_ts}")
    L.append(f"- verdict: **{result['verdict']}** "
             f"(v2 beats base on {result['v2_wins']}/{result['v2_evaluated']} "
             f"(stat,bucket) cells held-out; >50% = V2 LIFT)")
    L.append(f"- shadow records: {result['n_shadow_records']}; rows seen: "
             f"{result['n_rows_seen']}; no-actual: {result['n_no_actual']}")
    L.append("")
    L.append("Delta = MAE(v2) - MAE(base); **negative = v2 better**. "
             "`gated` = server-equivalent under the game-time gate.")
    L.append("")
    for bucket in BUCKET_ORDER:
        blk = result["per_bucket"].get(bucket)
        if not blk:
            continue
        L.append(f"## {bucket}  (n_pairs={blk['n_pairs']}, "
                 f"v2 wins {blk['v2_wins']}/{blk['v2_evaluated']})")
        L.append("")
        L.append("| stat | n | base | v2 | gated | dV2 | winner |")
        L.append("|------|---|------|----|-------|-----|--------|")
        for stat in STATS:
            d = blk["table"].get(stat, {})
            if d.get("delta_v2") is None:
                L.append(f"| {stat} | -- | -- | -- | -- | -- | -- |")
                continue
            win = "V2" if d["delta_v2"] < 0 else ("base" if d["delta_v2"] > 0 else "tie")
            L.append(f"| {stat} | {d['n']} | {d['base_mae']:.4f} | {d['v2_mae']:.4f} | "
                     f"{d['gated_mae']:.4f} | {d['delta_v2']:+.4f} | {win} |")
        L.append("")
    L.append("## Promote candidates (v2 < base this game)")
    L.append("")
    if result["promote"]:
        for p in result["promote"]:
            L.append(f"- `{p['bucket']}` / **{p['stat']}**: dV2={p['delta_v2']:+.4f} (n={p['n']})")
    else:
        L.append("- none")
    L.append("")
    L.append("## Context")
    L.append("")
    L.append("Retro walk-forward (`.planning/ingame/eval_curve_v2.json`): v2_core beats "
             "the production snapshot projector on essentially all stats at "
             "endQ1->midQ3, ties/loses at midQ1 (defer to L5) and endQ3->Q4 (defer to "
             "snapshot). This per-game grade checks whether that lift shows on ONE real "
             "game. A single game is noisy -- promote a cell only after it holds across "
             "several shadow nights.")
    L.append("")
    L.append(f"Shadow mode is gated behind `CV_INGAME_SBS` (default OFF). "
             f"To enable on the next game night: `set CV_INGAME_SBS=1` before "
             f"starting the live poller.")
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
    shadow_path = os.path.join(args.shadow_dir, f"sbs_shadow_{game_id}.jsonl")
    if not os.path.exists(shadow_path):
        print(f"[grade] ERROR: shadow log not found: {shadow_path}")
        print(f"        Run sbs_shadow_logger.py --game-id {game_id} first.")
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
    actuals = extract_actuals(final_snap)
    print(f"[grade] actuals: {len(actuals)} (player,stat) pairs")

    result = grade(records, actuals)
    if not args.quiet:
        print_results(game_id, result)

    os.makedirs(args.out_dir, exist_ok=True)
    run_ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_tag = run_ts[:10].replace("-", "")
    md_path = os.path.join(args.out_dir, f"sbs_grade_{game_id}_{date_tag}.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(_markdown(game_id, result, run_ts))
    print(f"[grade] summary -> {md_path}")
    print(f"[grade] RESULT: {result['verdict']}  "
          f"({result['v2_wins']}/{result['v2_evaluated']} cells v2 beats base)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
