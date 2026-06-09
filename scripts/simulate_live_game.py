"""Replay a past game's snapshots into the live folder under tonight's game_id
so the UI goes through the full live experience without an actual game.

Usage
-----
    # Default: replay SAS@OKC playoff game at 30x speed (Q4 in ~3 minutes)
    python scripts/simulate_live_game.py

    # Real-time (1 snapshot per ~30s; full game takes ~2 hours)
    python scripts/simulate_live_game.py --speed 1

    # Faster: 60x compression
    python scripts/simulate_live_game.py --speed 60

    # Different source game / target game_id
    python scripts/simulate_live_game.py --source 0042500315 --target 1027678168

Stop with Ctrl+C — the simulator cleans up its TEST files on exit.

While running, open in another tab:
    http://127.0.0.1:3000/tonight?date=<DATE>&game_id=<TARGET>
    http://127.0.0.1:3000/parlays?date=<DATE>
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
LIVE_DIR = PROJECT / "data" / "live"


def _cleanup(target_gid: str) -> int:
    """Remove all SIM-tagged snapshot files for `target_gid`."""
    n = 0
    for p in LIVE_DIR.glob(f"{target_gid}_SIM_*.json"):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    return n


def _summarize(snap: dict) -> str:
    period = snap.get("period")
    clock = snap.get("clock")
    ht_abbr = snap.get("home_team") or snap.get("home_team_id") or "?"
    at_abbr = snap.get("away_team") or snap.get("away_team_id") or "?"
    hs = snap.get("home_score") or 0
    as_ = snap.get("away_score") or 0
    return f"Q{period} {clock} · {at_abbr} {as_} — {hs} {ht_abbr}"


def run(source_gid: str, target_gid: str, speed: float) -> None:
    """Replay source_gid snapshots as target_gid_SIM_*.json files.

    `speed=1` plays back in real time (each snapshot is written N seconds after
    the previous, where N matches the original snapshot interval). `speed=30`
    means 30× faster (a 2hr game replays in ~4 minutes)."""

    files = sorted(LIVE_DIR.glob(f"{source_gid}_*.json"))
    if not files:
        print(f"ERR: no source snapshots found for game_id={source_gid}")
        sys.exit(1)

    # Read timestamps from the filename suffix (epoch-ms). If missing/garbled,
    # we'll fall back to a fixed sleep between snapshots.
    parsed: list[tuple[int, Path]] = []
    for p in files:
        try:
            ts = int(p.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        parsed.append((ts, p))
    parsed.sort()
    if not parsed:
        print(f"ERR: source snapshots have no parseable timestamps")
        sys.exit(1)

    # Dedupe identical consecutive snapshots + drop pregame (Q0) — these have
    # no live_engine projection. Cache to disk so re-runs are instant; first
    # scan reads 2k+ files and takes ~20s. Cache key includes the filter
    # version so old caches without the Q0 drop get rebuilt.
    cache_path = PROJECT / "data" / "cache" / f"sim_replay_{source_gid}_v2.json"
    newest_src_mtime = max(p.stat().st_mtime for _, p in parsed)
    deduped: list[tuple[int, Path]] = []
    if cache_path.exists() and cache_path.stat().st_mtime > newest_src_mtime:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            for entry in cached:
                deduped.append((int(entry["ts"]), Path(entry["path"])))
            print(f"  dedup: cached ({len(deduped)} snapshots from Q1 onward)")
        except Exception:
            deduped = []
    if not deduped:
        print(f"  dedup: scanning {len(parsed)} snapshots (~20s, cached afterward)…")
        last_sig = None
        n_pregame = 0
        for ts, p in parsed:
            try:
                sn = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            period = sn.get("period") or 0
            if period < 1:
                n_pregame += 1
                continue
            sig = (period, sn.get("clock"),
                   sn.get("home_score"), sn.get("away_score"))
            if sig != last_sig:
                deduped.append((ts, p))
                last_sig = sig
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps([{"ts": t, "path": str(p)} for t, p in deduped]),
                encoding="utf-8",
            )
        except Exception:
            pass
        print(f"  dedup: {len(parsed)} → {len(deduped)} unique Q1+ snapshots ({n_pregame} pregame dropped)")
    if not deduped:
        print(f"ERR: dedup left zero snapshots")
        sys.exit(1)
    parsed = deduped

    print(f"▶ Simulator booting")
    print(f"  source game: {source_gid}  →  target game_id: {target_gid}")
    print(f"  {len(parsed)} snapshots  ·  speed: {speed}×")
    print(f"  live_dir: {LIVE_DIR}")

    cleaned = _cleanup(target_gid)
    if cleaned:
        print(f"  cleaned {cleaned} stale SIM files")

    def _exit_handler(sig, frame):
        n = _cleanup(target_gid)
        print(f"\n■ Simulator stopped — cleaned up {n} SIM files")
        sys.exit(0)

    signal.signal(signal.SIGINT, _exit_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _exit_handler)

    start_real_ts = time.time()
    start_snap_ts = parsed[0][0] / 1000.0  # convert epoch-ms → s

    try:
        for i, (orig_ts_ms, snap_path) in enumerate(parsed):
            # Pace replay: target wall-clock time for this snapshot
            target_offset = (orig_ts_ms / 1000.0 - start_snap_ts) / max(speed, 0.0001)
            elapsed = time.time() - start_real_ts
            to_sleep = max(0.0, target_offset - elapsed)
            if to_sleep > 0:
                time.sleep(to_sleep)

            try:
                snap = json.loads(snap_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  [skip] failed to load {snap_path.name}: {e}")
                continue

            # Rewrite game_id so consumers think this snapshot is for tonight's
            # game. Keep all player stats, period, clock, scores intact.
            snap["game_id"] = target_gid

            # Use a current-time epoch-ms suffix on the output filename so the
            # live_dir scanner's mtime + filename-sort logic both see "newest".
            out_ts_ms = int(time.time() * 1000)
            out_path = LIVE_DIR / f"{target_gid}_SIM_{out_ts_ms}.json"
            out_path.write_text(json.dumps(snap), encoding="utf-8")

            # Touch mtime explicitly (some filesystems lag)
            try:
                os.utime(out_path, None)
            except OSError:
                pass

            print(f"  [{i + 1:4d}/{len(parsed)}] {_summarize(snap)}  → wrote {out_path.name}")

        # Hold the final snapshot for 60s so the user can inspect end-state
        print("\n✓ Replay finished — holding final snapshot for 60s")
        print("  (or hit Ctrl+C now to clean up immediately)")
        time.sleep(60)
    finally:
        n = _cleanup(target_gid)
        print(f"■ Cleanup: removed {n} SIM files")


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay a past game's snapshots into tonight's game_id slot")
    ap.add_argument("--source", default="0042500315",
                    help="Source game_id (a real past game with snapshots in data/live/). Default: SAS@OKC playoff game")
    ap.add_argument("--target", default="1027678168",
                    help="Target game_id (tonight's KAMBI/sportsbook id). Default: 1027678168")
    ap.add_argument("--speed", type=float, default=30.0,
                    help="Replay speed multiplier. 1.0 = real time, 30.0 = 30× faster. Default: 30.")
    args = ap.parse_args()

    run(args.source, args.target, args.speed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
