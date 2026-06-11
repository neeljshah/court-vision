"""cv_demo_replay.py — LIVE in-game demo for the /cv page.

Streams the real Game-3 play-by-play snapshots into data/live as FRESH snapshots
for the default /cv game (0042500404, NYK vs SAS — same matchup), at a watchable
cadence. With the server up (scripts/courtvision/cv_serve.ps1), open /cv and watch
the page go LIVE → progress quarter-by-quarter → FINAL, with the win-prob bar,
box score, intelligence narrative, and bet cards ALL updating buzzer-to-buzzer —
and the live win-prob correctly collapsing to 0/100 at the final gun (terminal
gate). The bets re-price from live odds + live predictions.

Because the snapshots are written with a FRESH mtime, the live overlay treats
them as live (the stale gate only fires on >4h-old snapshots). G4 has not tipped,
so no real 0042500404 snapshots are disturbed.

Usage:
    python scripts/courtvision/cv_demo_replay.py            # ~50 frames @ 3s each
    python scripts/courtvision/cv_demo_replay.py --frames 60 --interval 2.5
    python scripts/courtvision/cv_demo_replay.py --clean    # remove demo snapshots
    python scripts/courtvision/cv_demo_replay.py --hold 0   # don't hold the FINAL

Stop any time with Ctrl-C; run --clean afterward to revert /cv to pregame.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LIVE_DIR = ROOT / "data" / "live"
SRC_GAME = "0042500403"   # Game 3 (played) — source PBP
DST_GAME = "0042500404"   # Game 4 — what /cv shows by default (same NYK vs SAS)


def _epoch_ms_of(path: Path) -> int:
    """The snapshot's own epoch-ms (filename <gid>_<epoch_ms>.json) for ordering."""
    try:
        return int(path.stem.split("_")[-1])
    except (ValueError, IndexError):
        return 0


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _sample(paths: list[Path], n: int) -> list[Path]:
    """~n evenly-spaced snapshots that have real game action (period>0), in order,
    always including the very last (final) snapshot."""
    live = []
    for p in paths:
        snap = _load(p)
        if snap and int(snap.get("period", 0) or 0) > 0:
            live.append(p)
    if not live:
        return paths[:n]
    if len(live) <= n:
        return live
    step = max(1, len(live) // n)
    out = live[::step]
    if out[-1] is not live[-1]:
        out.append(live[-1])
    return out


def clean(quiet: bool = False) -> int:
    """Remove every demo snapshot for the destination game. Returns the count."""
    removed = 0
    for p in LIVE_DIR.glob(f"{DST_GAME}_*.json"):
        try:
            p.unlink()
            removed += 1
        except OSError:
            pass
    if not quiet:
        print(f"Removed {removed} demo snapshot(s) for {DST_GAME}. /cv reverts to pregame.")
    return removed


def _prune(keep: int = 4) -> None:
    """Keep only the newest `keep` demo snapshots so the loop never accumulates
    thousands of files — but NEVER drops to zero (the page stays live)."""
    files = sorted(LIVE_DIR.glob(f"{DST_GAME}_*.json"), key=_epoch_ms_of)
    for p in files[:-keep]:
        try:
            p.unlink()
        except OSError:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Live /cv in-game demo (replays G3).")
    ap.add_argument("--frames", type=int, default=50, help="snapshots to stream (default 50)")
    ap.add_argument("--interval", type=float, default=3.0, help="seconds between frames (default 3)")
    ap.add_argument("--hold", type=float, default=30.0, help="seconds to hold the FINAL frame (default 30)")
    ap.add_argument("--loop", action="store_true", help="replay forever (pregame->live->final->repeat)")
    ap.add_argument("--clean", action="store_true", help="remove demo snapshots and exit")
    args = ap.parse_args()

    if args.clean:
        clean()
        return

    paths = sorted(LIVE_DIR.glob(f"{SRC_GAME}_*.json"), key=_epoch_ms_of)
    if not paths:
        print(f"No source snapshots for {SRC_GAME} in {LIVE_DIR}", file=sys.stderr)
        sys.exit(1)
    frames = _sample(paths, args.frames)

    def _write(src: Path) -> str | None:
        snap = _load(src)
        if snap is None:
            return None
        snap["game_id"] = DST_GAME   # re-key; everything else is the real G3 state
        now_ms = int(time.time() * 1000)
        (LIVE_DIR / f"{DST_GAME}_{now_ms}.json").write_text(json.dumps(snap), encoding="utf-8")
        per, clk = snap.get("period"), snap.get("clock")
        hs, as_ = snap.get("home_score"), snap.get("away_score")
        tag = "FINAL" if "FINAL" in str(snap.get("game_status", "")).upper() else f"Q{per} {clk}"
        return f"{tag:>10}  NYK {hs:>3} - SAS {as_:>3}"

    if args.loop:
        # CONTINUOUS live demo: cycle Q1->Q4->FINAL->Q1 forever, pruning old
        # snapshots so the page is ALWAYS live (no pregame gap). Open /cv and it
        # is always mid-game. Ctrl-C + --clean to revert to pregame.
        print(f"LOOP demo: streaming G3 as live {DST_GAME} every {args.interval}s "
              f"(prune-not-clean → always live). Ctrl-C to stop.\n")
        n = 0
        try:
            while True:
                for src in frames:
                    line = _write(src)
                    _prune(keep=4)
                    n += 1
                    if line:
                        print(f"  [{n:>4}] {line}", flush=True)
                    time.sleep(args.interval)
                # brief hold on FINAL, then loop straight back to Q1 (still live)
                time.sleep(max(0.0, args.hold))
        except KeyboardInterrupt:
            print("\nStopped loop.")
            clean()
        return

    # Single pass: clean first (deterministic), stream, hold FINAL.
    clean(quiet=True)
    print(f"Streaming {len(frames)} frames of G3 as LIVE {DST_GAME} "
          f"(every {args.interval}s). Open /cv and watch it go live → final.\n")
    n = 0
    try:
        for src in frames:
            line = _write(src)
            n += 1
            if line:
                print(f"  [{n:>2}/{len(frames)}] {line}", flush=True)
            time.sleep(args.interval)
        if args.hold > 0:
            print(f"\nHolding FINAL for {args.hold:.0f}s (win-prob terminal-gated to 0/100). "
                  "Ctrl-C to stop.")
            time.sleep(args.hold)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        print(f"\nDemo wrote {n} frame(s). Run with --clean to revert /cv to pregame.")


if __name__ == "__main__":
    main()
