#!/usr/bin/env python3
"""Re-derive possessions.csv by merging "blip" possessions (< 2.0s) that the OLD
tracker (pre-2026-05-23 debounce fix) emitted as false-positive team switches.

Operates directly on possessions.csv rows (the filtered set). A blip is a row
where (a) duration_sec < 2.0 AND (b) prev_row.team == next_row.team AND
prev_row.team != this_row.team — sandwiched between two same-team neighbors.
Merged by absorbing this row's start/end into the PREV row (and "deleting" it
from possessions.csv).

If multiple consecutive rows form alternating-team blips, we iterate to a fixed
point: first pass merges innermost blips, second pass picks up new neighbors,
etc.

Idempotent. Re-running on already-reconciled data is a no-op.

Side effect: backs up possessions.csv to possessions.csv.bak_blipmerge on first
run only (won't overwrite an existing backup).

Usage:
    python3 scripts/reconcile_possessions.py --all
    python3 scripts/reconcile_possessions.py --game-ids 0022500064 0022500054
    python3 scripts/reconcile_possessions.py --all --dry-run
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

TRACKING_ROOT = Path("/workspace/nba-ai-system/data/tracking")
# 4.0s threshold: catches deflection/swipe blips that pass the in-tracker 2.0s
# debounce but are still false-positive switches. Real steal-and-score in <4s
# is rare (<5% of fast breaks per NBA play-by-play); over-counting is the much
# bigger problem (games at 459-615 vs NBA-typical 180-240).
BLIP_MAX_SEC = 4.0
DEFAULT_FPS = 30.0


def _row_dur_sec(row: dict) -> float:
    try:
        d = float(row.get("duration_sec", 0) or 0)
        if d > 0:
            return d
    except (ValueError, TypeError):
        pass
    try:
        df = int(row.get("duration_frames", 0) or 0)
        if df > 0:
            return df / DEFAULT_FPS
    except (ValueError, TypeError):
        pass
    try:
        sf = int(row.get("start_frame", 0) or 0)
        ef = int(row.get("end_frame", 0) or 0)
        return (ef - sf + 1) / DEFAULT_FPS
    except (ValueError, TypeError):
        return 0.0


def merge_pair(prev: dict, blip: dict) -> dict:
    """Return a NEW row that is prev extended through blip's end."""
    out = dict(prev)
    try:
        out["end_frame"] = max(int(prev.get("end_frame", 0) or 0),
                               int(blip.get("end_frame", 0) or 0))
        out["start_frame"] = min(int(prev.get("start_frame", 0) or 0),
                                 int(blip.get("start_frame", 0) or 0))
        if "duration_frames" in out:
            out["duration_frames"] = int(out["end_frame"]) - int(out["start_frame"]) + 1
        if "duration_sec" in out:
            out["duration_sec"] = round(
                (int(out["end_frame"]) - int(out["start_frame"]) + 1) / DEFAULT_FPS, 2)
    except (ValueError, TypeError):
        pass
    # OR semantics for shot_attempted
    for col in ("shot_attempted", "fast_break", "offensive_rebound_poss", "pbp_matched"):
        if col in out:
            try:
                a = int(prev.get(col, 0) or 0)
                b = int(blip.get(col, 0) or 0)
                out[col] = max(a, b)
            except (ValueError, TypeError):
                pass
    # SUM counts
    for col in ("pass_count", "screen_count", "drive_count", "cut_count",
                "drive_attempts", "max_paint_touches"):
        if col in out:
            try:
                a = int(prev.get(col, 0) or 0)
                b = int(blip.get(col, 0) or 0)
                out[col] = a + b
            except (ValueError, TypeError):
                pass
    return out


def reconcile_one(gid: str, dry_run: bool = False) -> dict:
    d = TRACKING_ROOT / gid
    poss_csv = d / "possessions.csv"
    if not poss_csv.exists():
        return {"gid": gid, "skip": "no possessions.csv"}

    with open(poss_csv, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)
    n_orig = len(rows)
    if n_orig < 3:
        return {"gid": gid, "orig": n_orig, "new": n_orig, "merged": 0, "noop": True}

    # Iterate to fixed point
    n_merged_total = 0
    while True:
        new_rows = []
        i = 0
        merged_this_pass = 0
        while i < len(rows):
            if i == 0 or i == len(rows) - 1:
                new_rows.append(rows[i])
                i += 1
                continue
            prev_r, this_r, next_r = rows[i - 1] if not new_rows else new_rows[-1], rows[i], rows[i + 1]
            prev_t = (prev_r.get("team", "") or "").strip()
            this_t = (this_r.get("team", "") or "").strip()
            next_t = (next_r.get("team", "") or "").strip()
            dur = _row_dur_sec(this_r)
            if (dur < BLIP_MAX_SEC and prev_t and next_t
                and prev_t == next_t and this_t != prev_t):
                # Merge this blip into prev. Drop new_rows[-1] (prev), replace
                # with merged. Skip i (this), continue.
                if new_rows:
                    new_rows[-1] = merge_pair(new_rows[-1], this_r)
                else:
                    new_rows.append(merge_pair(prev_r, this_r))
                merged_this_pass += 1
                i += 1
                continue
            # Also: if this row is a blip but neighbors are DIFFERENT teams,
            # absorb into whichever has same team as the next-next; otherwise drop.
            # Skip for now — conservative.
            new_rows.append(this_r)
            i += 1
        if merged_this_pass == 0:
            break
        rows = new_rows
        n_merged_total += merged_this_pass

    n_new = len(rows)
    if n_merged_total == 0:
        return {"gid": gid, "orig": n_orig, "new": n_new, "merged": 0, "noop": True}

    if dry_run:
        return {"gid": gid, "orig": n_orig, "new": n_new, "merged": n_merged_total, "dry": True}

    # Reassign sequential possession_id
    for new_pid, row in enumerate(rows):
        row["possession_id"] = new_pid

    # Backup + write
    bak = poss_csv.with_suffix(".csv.bak_blipmerge")
    if not bak.exists():
        shutil.copy2(poss_csv, bak)
    with open(poss_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # Same for possessions_enriched.csv
    enriched = d / "possessions_enriched.csv"
    if enriched.exists():
        with open(enriched, encoding="utf-8", errors="replace") as f:
            er = csv.DictReader(f)
            efields = er.fieldnames or []
            erows = list(er)
        if erows:
            # Apply same merge logic to enriched
            n_e_orig = len(erows)
            while True:
                ne = []
                i = 0
                m = 0
                while i < len(erows):
                    if i == 0 or i == len(erows) - 1:
                        ne.append(erows[i]); i += 1; continue
                    pr = ne[-1] if ne else erows[i-1]
                    tr = erows[i]; nr = erows[i+1]
                    pt = (pr.get("team","") or "").strip()
                    tt = (tr.get("team","") or "").strip()
                    nt = (nr.get("team","") or "").strip()
                    dur = _row_dur_sec(tr)
                    if (dur < BLIP_MAX_SEC and pt and nt and pt == nt and tt != pt):
                        if ne: ne[-1] = merge_pair(ne[-1], tr)
                        else:  ne.append(merge_pair(pr, tr))
                        m += 1; i += 1; continue
                    ne.append(tr); i += 1
                if m == 0:
                    break
                erows = ne
            for new_pid, row in enumerate(erows):
                row["possession_id"] = new_pid
            ebak = enriched.with_suffix(".csv.bak_blipmerge")
            if not ebak.exists():
                shutil.copy2(enriched, ebak)
            with open(enriched, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=efields)
                w.writeheader()
                w.writerows(erows)

    return {"gid": gid, "orig": n_orig, "new": n_new, "merged": n_merged_total}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-ids", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.all or not args.game_ids:
        gids = sorted(
            p.name for p in TRACKING_ROOT.iterdir()
            if p.is_dir() and p.name.startswith("00")
            and (p / "possessions.csv").exists()
        )
    else:
        gids = args.game_ids

    print(f"Reconciling possessions.csv for {len(gids)} games (blip<{BLIP_MAX_SEC}s)"
          + (" [DRY RUN]" if args.dry_run else ""))

    n_changed = 0
    total_merged = 0
    for gid in gids:
        try:
            r = reconcile_one(gid, dry_run=args.dry_run)
            if r.get("skip"):
                print(f"  {gid}  SKIP: {r['skip']}")
                continue
            if r.get("noop"):
                print(f"  {gid}  noop ({r['orig']} possessions, none merged)")
                continue
            print(f"  {gid}  {r['orig']} -> {r['new']} (-{r['merged']} blips merged)")
            n_changed += 1
            total_merged += r["merged"]
        except Exception as e:
            print(f"  {gid}  ERR {type(e).__name__}: {e}")

    print(f"\nDone: {n_changed} games changed, {total_merged} blips merged total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
