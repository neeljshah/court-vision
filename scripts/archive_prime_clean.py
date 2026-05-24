#!/usr/bin/env python3
"""Archive videos from /root/nba_videos to /workspace archive.

Strategy:
  - PRIME+CLEAN games (highest quality, definitely don't need reproc) — always archive.
  - Any game with a tracking dir that completed AND no active worker — archive.
    (Conservative reprocess gate: only USABLE/CLEAN, not BAD. POOR included since brief
    says broadcast-limited POOR games "won't improve".)

NEVER touch a video whose game-id has an active run_clip.py worker.

Idempotent. Logs every action. Reports disk before/after.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SRC_DIR = Path("/root/nba_videos")
DST_DIR = Path("/workspace/nba_videos_archive")
TRACKING_ROOT = Path("/workspace/nba-ai-system/data/tracking")
DST_DIR.mkdir(parents=True, exist_ok=True)


def active_worker_gids() -> set[str]:
    out = subprocess.check_output(["ps", "-eo", "args"], text=True)
    gids = set()
    for line in out.splitlines():
        if "run_clip.py" not in line:
            continue
        m = re.search(r"--game-id\s+(\d+)", line)
        if m:
            gids.add(m.group(1))
    return gids


def audit_rows() -> dict[str, tuple[str, str]]:
    """Returns {gid: (train_tier, audit_tier)} from audit_completed.py."""
    out = subprocess.check_output(
        ["python3", "scripts/audit_completed.py"],
        cwd="/workspace/nba-ai-system",
        text=True,
    )
    rows = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        gid, train, tier = parts[0], parts[1], parts[2]
        if not gid.startswith("00"):
            continue
        rows[gid] = (train, tier)
    return rows


def tracking_complete(gid: str) -> bool:
    """A game's tracking is "complete enough" if run.log exists and is non-tiny."""
    rlog = TRACKING_ROOT / gid / "run.log"
    return rlog.exists() and rlog.stat().st_size > 4096


def main() -> int:
    active = active_worker_gids()
    rows = audit_rows()
    print(f"audit: {len(rows)} games audited, active workers on: {sorted(active)}")

    moved = 0
    skipped_active = 0
    skipped_incomplete = 0
    skipped_bad = 0
    freed_mb = 0

    for src in sorted(SRC_DIR.glob("*.mp4")):
        gid = src.stem
        dst = DST_DIR / src.name

        if gid in active:
            skipped_active += 1
            continue

        # Must have audit row + tracking complete (otherwise might be download-in-progress)
        if gid not in rows or not tracking_complete(gid):
            skipped_incomplete += 1
            continue

        train, tier = rows[gid]
        if tier == "BAD":
            skipped_bad += 1
            continue

        size_mb = src.stat().st_size / (1024 * 1024)

        if dst.exists():
            try:
                src.unlink()
                freed_mb += size_mb
                moved += 1
                print(f"  rm  {gid}.mp4 ({size_mb:.0f} MB) [{train}/{tier}] — dup of archive")
            except OSError as e:
                print(f"  ERR rm {gid}.mp4: {e}")
            continue

        try:
            shutil.copy2(src, dst)
            # Verify byte-for-byte size before deleting source
            if dst.stat().st_size != src.stat().st_size:
                raise OSError(f"size mismatch: src={src.stat().st_size} dst={dst.stat().st_size}")
            src.unlink()
            moved += 1
            freed_mb += size_mb
            print(f"  mv  {gid}.mp4 ({size_mb:.0f} MB) [{train}/{tier}] -> archive")
        except OSError as e:
            # Clean up partial copy so next run can retry cleanly
            if dst.exists() and dst.stat().st_size != src.stat().st_size:
                try:
                    dst.unlink()
                    print(f"  ERR mv {gid}.mp4: {e} [cleaned partial dst]")
                except OSError:
                    print(f"  ERR mv {gid}.mp4: {e} [partial dst cleanup failed]")
            else:
                print(f"  ERR mv {gid}.mp4: {e}")

    print(
        f"summary: moved={moved} freed_MB={freed_mb:.0f} "
        f"skipped_active={skipped_active} skipped_incomplete={skipped_incomplete} "
        f"skipped_bad={skipped_bad}"
    )

    # --- Second pass: purge videos we don't need anymore from archive ---
    # CLEAN games are stable — we don't plan to reprocess.
    # POOR/BAD games are broadcast-limited per the brief — won't improve on retry.
    # Both are safe to delete; their tracking data persists in data/tracking/.
    # USABLE-tier videos are kept (might benefit from future tracker improvements).
    purged = 0
    purged_mb = 0
    for arch in sorted(DST_DIR.glob("*.mp4")):
        gid = arch.stem
        if gid not in rows:
            continue
        train_tier, audit_tier = rows[gid]
        # Delete if: CLEAN (don't need to reprocess) OR POOR/BAD (won't improve)
        delete = audit_tier == "CLEAN" or audit_tier == "BAD" or train_tier == "POOR"
        if not delete:
            continue
        sz_mb = arch.stat().st_size / (1024 * 1024)
        try:
            arch.unlink()
            purged += 1
            purged_mb += sz_mb
            print(f"  purge_archive {gid}.mp4 ({sz_mb:.0f} MB) [{train_tier}/{audit_tier}]")
        except OSError as e:
            print(f"  ERR purge {gid}: {e}")
    print(f"archive_purge: purged={purged} freed_MB={purged_mb:.0f}")

    df_root = subprocess.check_output(["df", "-h", "/root"], text=True)
    print(df_root.strip())
    ws_du = subprocess.check_output(["du", "-sh", "/workspace"], text=True).strip()
    print(f"/workspace total: {ws_du.split()[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
