"""
compare_reprocess_pre_post.py
Compact A/B report for a reprocessed game tracking directory.

Usage:
    python scripts/compare_reprocess_pre_post.py \
        --before /tmp/0022401190_BEFORE \
        --after  /workspace/nba-ai-system/data/tracking/0022401190

Handles partial/missing files gracefully — prints N/A for unavailable data.
Exit code: always 0 (informational only).
"""

import argparse
import csv
import re
import sys
from pathlib import Path

# ── helpers ────────────────────────────────────────────────────────────────────

def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []

def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

def _pct(a: int, b: int) -> str:
    if b == 0:
        return "N/A"
    return f"{(a - b) / b * 100:+.1f}%"

def _fmt(val, fallback="N/A"):
    return str(val) if val is not None else fallback

# ── per-metric extractors ───────────────────────────────────────────────────────

def shot_log_stats(rows: list[dict]) -> dict:
    total = len(rows)
    slot_counts: dict[str, int] = {}
    cs_count = 0
    for r in rows:
        slot = r.get("player_id", "?")
        slot_counts[slot] = slot_counts.get(slot, 0) + 1
        pt = r.get("play_type", r.get("shot_type", "")).lower()
        if "catch" in pt or "c&s" in pt:
            cs_count += 1
    cs_rate = cs_count / total if total else None
    return {"total": total, "slot_counts": slot_counts, "cs_count": cs_count, "cs_rate": cs_rate}

def tracking_shot_count(rows: list[dict]) -> int:
    return sum(1 for r in rows if r.get("event", "").lower() == "shot")

def pbp_recall(log_text: str) -> str | None:
    """Extract the LAST 'PBP recall (relevant): N/M = X.XX%' line."""
    matches = re.findall(
        r"PBP recall \(relevant\):\s*\d+/\d+\s*=\s*([\d.]+%)", log_text
    )
    return matches[-1] if matches else None

def defender_distance_stats(rows: list[dict]) -> dict:
    missing = 0
    values = []
    for r in rows:
        v = r.get("defender_distance", "")
        if v in ("", "nan", "NaN", "NULL", "None") or v is None:
            missing += 1
        else:
            try:
                values.append(float(v))
            except ValueError:
                missing += 1
    mean_val = sum(values) / len(values) if values else None
    return {"missing": missing, "valid_count": len(values), "mean": mean_val}

def dribble_stats(rows: list[dict]) -> dict:
    on_ball = 0
    off_ball = 0
    for r in rows:
        dc_raw = r.get("dribble_count", "0")
        bp_raw = r.get("ball_possession", "0")
        try:
            dc = float(dc_raw) if dc_raw not in ("", None) else 0.0
            bp = float(bp_raw) if bp_raw not in ("", None) else 0.0
        except ValueError:
            dc, bp = 0.0, 0.0
        if dc > 0:
            if bp == 1:
                on_ball += 1
            else:
                off_ball += 1
    return {"on_ball": on_ball, "off_ball": off_ball}

def has_is_stub(rows: list[dict]) -> bool:
    if not rows:
        return False
    return "is_stub" in rows[0]

# ── per-game report ─────────────────────────────────────────────────────────────

STAR_SLOTS = ["2", "3", "9"]  # Curry / Jokic slots from prior session


def report_game(before_dir: Path, after_dir: Path, game_id: str) -> dict:
    """Return a dict of metrics for summary aggregation; also prints inline."""

    lines = [f"\n=== Game {game_id} ==="]

    # ── shot_log.csv ──────────────────────────────────────────────────────────
    sl_b = shot_log_stats(_read_csv(before_dir / "shot_log.csv"))
    sl_a = shot_log_stats(_read_csv(after_dir  / "shot_log.csv"))

    tb, ta = sl_b["total"], sl_a["total"]
    lines.append(f"Shots  before: {tb} | after: {ta} | delta: {_pct(ta, tb)}")

    # Star slot breakdown
    all_slots = sorted(
        set(list(sl_b["slot_counts"]) + list(sl_a["slot_counts"])),
        key=lambda x: (len(x), x)
    )
    star_slots_shown = [s for s in all_slots if s in STAR_SLOTS]
    for s in star_slots_shown:
        nb = sl_b["slot_counts"].get(s, 0)
        na = sl_a["slot_counts"].get(s, 0)
        lines.append(f"  Slot {s}: before={nb} after={na} ({_pct(na, nb)})")

    # ── tracking_data.csv shots ───────────────────────────────────────────────
    td_b = _read_csv(before_dir / "tracking_data.csv")
    td_a = _read_csv(after_dir  / "tracking_data.csv")
    tsc_b = tracking_shot_count(td_b)
    tsc_a = tracking_shot_count(td_a)
    lines.append(
        f"tracking event='shot':  before={tsc_b} after={tsc_a} delta={_pct(tsc_a, tsc_b)}"
    )

    # ── PBP recall ────────────────────────────────────────────────────────────
    log_b = _read_text(before_dir / "run.log")
    log_a = _read_text(after_dir  / "run.log")
    pbp_b = pbp_recall(log_b) or "N/A"
    pbp_a = pbp_recall(log_a) or "N/A"
    lines.append(f"PBP recall  before: {pbp_b} | after: {pbp_a}")

    # ── Catch-and-shoot rate (Bug 30 gate) ───────────────────────────────────
    def _cs_fmt(stats: dict) -> str:
        if stats["cs_rate"] is None:
            return "N/A"
        pct = stats["cs_rate"] * 100
        flag = " [OK]" if pct <= 60 else " [WARN OVER-DETECTION]"
        return f"{pct:.0f}%{flag}"

    lines.append(
        f"Catch-and-shoot:  before={_cs_fmt(sl_b)} after={_cs_fmt(sl_a)}"
        f"  (gate <=60%)"
    )

    # ── defender_distance (Bug 1) ─────────────────────────────────────────────
    # Use shot_log rows (has defender_distance column)
    sl_rows_b = _read_csv(before_dir / "shot_log.csv")
    sl_rows_a = _read_csv(after_dir  / "shot_log.csv")
    dd_b = defender_distance_stats(sl_rows_b)
    dd_a = defender_distance_stats(sl_rows_a)
    mean_b = f"{dd_b['mean']:.1f}" if dd_b["mean"] is not None else "N/A"
    mean_a = f"{dd_a['mean']:.1f}" if dd_a["mean"] is not None else "N/A"
    lines.append(
        f"defender_distance: missing before={dd_b['missing']} after={dd_a['missing']}"
        f"  mean before={mean_b} after={mean_a}  (Bug 1 fix)"
    )

    # ── dribble_count off-ball (Bug 25) ──────────────────────────────────────
    dr_b = dribble_stats(td_b)
    dr_a = dribble_stats(td_a)
    lines.append(
        f"dribble off-ball:  before={dr_b['off_ball']} after={dr_a['off_ball']}"
        f"  on-ball: before={dr_b['on_ball']} after={dr_a['on_ball']}  (Bug 25 fix)"
    )

    # ── possessions.csv is_stub (Bug 26) ─────────────────────────────────────
    poss_b = _read_csv(before_dir / "possessions.csv")
    poss_a = _read_csv(after_dir  / "possessions.csv")
    stub_b = "YES" if has_is_stub(poss_b) else ("NO" if poss_b else "FILE MISSING")
    stub_a = "YES" if has_is_stub(poss_a) else ("NO" if poss_a else "FILE MISSING")
    lines.append(f"possessions has is_stub: before={stub_b} after={stub_a}  (Bug 26 fix)")

    lines.append("=" * 57)
    print("\n".join(lines))

    return {
        "game_id": game_id,
        "shots_before": tb,
        "shots_after": ta,
        "cs_rate_before": sl_b["cs_rate"],
        "cs_rate_after":  sl_a["cs_rate"],
        "dd_missing_before": dd_b["missing"],
        "dd_missing_after":  dd_a["missing"],
        "dd_total_before": len(sl_rows_b),
        "dd_total_after":  len(sl_rows_a),
        "off_ball_before": dr_b["off_ball"],
        "off_ball_after":  dr_a["off_ball"],
        "stub_after": stub_a,
    }


# ── summary ─────────────────────────────────────────────────────────────────────

def print_summary(results: list[dict]) -> None:
    if not results:
        print("\nNo results to summarize.")
        return

    # Shot recall delta
    shot_deltas = []
    for r in results:
        if r["shots_before"] > 0:
            shot_deltas.append((r["shots_after"] - r["shots_before"]) / r["shots_before"] * 100)
    avg_shot = f"{sum(shot_deltas)/len(shot_deltas):+.1f}%" if shot_deltas else "N/A"

    # Bug 1: % rows now NaN
    dd_pct_parts = []
    for r in results:
        t = r["dd_total_after"]
        if t > 0:
            dd_pct_parts.append(r["dd_missing_after"] / t * 100)
    avg_dd_pct = f"{sum(dd_pct_parts)/len(dd_pct_parts):.1f}%" if dd_pct_parts else "N/A"

    # Bug 25: off-ball dribble drop
    ob_before = sum(r["off_ball_before"] for r in results)
    ob_after  = sum(r["off_ball_after"]  for r in results)
    ob_drop = _pct(ob_after, ob_before) if ob_before else "N/A"

    # Bug 26: is_stub present in all after?
    stub_all = all(r["stub_after"] == "YES" for r in results)

    # Bug 30: catch-and-shoot gate
    cs_ok = all(
        r["cs_rate_after"] is None or r["cs_rate_after"] <= 0.60
        for r in results
    )

    print(
        f"\nSUMMARY:"
        f"\n  Bug 30 fix (shot recall):    {avg_shot} avg shot count change across {len(results)} game(s)"
        f"\n  Bug 1  fix (defender_dist):  {avg_dd_pct} of shot rows have NaN defender_distance post-reprocess"
        f"\n  Bug 25 fix (off-ball drib):  off-ball dribble noise {ob_drop} ({ob_before} -> {ob_after})"
        f"\n  Bug 26 fix (is_stub flag):   {'PRESENT in all after dirs [OK]' if stub_all else 'MISSING in one or more after dirs [FAIL]'}"
        f"\n  Catch-and-shoot <=60% gate: {'PASS [OK]' if cs_ok else 'FAIL [WARN] -- over-detection risk'}"
    )


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="A/B report: before/after reprocess of a tracking directory."
    )
    parser.add_argument("--before", required=True,
                        help="Path to the BEFORE tracking directory (or parent of multiple game dirs)")
    parser.add_argument("--after", required=True,
                        help="Path to the AFTER tracking directory (or parent of multiple game dirs)")
    parser.add_argument("--game-id", default=None,
                        help="Explicit game ID label (inferred from path if omitted)")
    args = parser.parse_args()

    before_root = Path(args.before)
    after_root  = Path(args.after)

    results = []

    # Support two calling modes:
    # 1. Both paths point directly to a game dir: compare them as a pair.
    # 2. Both paths are parent dirs containing same-named game subdirs.

    def _looks_like_game_dir(p: Path) -> bool:
        return (p / "shot_log.csv").exists() or (p / "tracking_data.csv").exists()

    if _looks_like_game_dir(before_root) or _looks_like_game_dir(after_root):
        # Single-game mode
        gid = args.game_id or after_root.name
        r = report_game(before_root, after_root, gid)
        results.append(r)
    else:
        # Multi-game mode: walk subdirs present in after_root
        after_subdirs = sorted(after_root.iterdir()) if after_root.exists() else []
        paired = [(before_root / d.name, d) for d in after_subdirs if d.is_dir()]
        if not paired:
            print(f"No game subdirectories found under {after_root}", file=sys.stderr)
        for b_dir, a_dir in paired:
            gid = a_dir.name
            r = report_game(b_dir, a_dir, gid)
            results.append(r)

    print_summary(results)
    sys.exit(0)


if __name__ == "__main__":
    main()
