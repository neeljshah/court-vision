"""capture_closing_lines.py — fire a Pinnacle one-shot scrape at (or as close as
possible to) tip-off, then atomic-rename the resulting Pin snapshots to a
labelled "closing-line" file under ``data/lines/snapshots/``.

Why this exists
---------------
Gate-1 CLV (closing-line value) has been blocked for ~12 months because we had
no real Pinnacle CLOSING snapshots — only opening / mid-day. This script makes
the capture deterministic and unattended: schedule it once with Windows Task
Scheduler (or just leave it running), and the snapshot lands on disk whether
or not the operator is at the computer.

Output paths (atomic — temp-then-rename so a partial write is never seen)
------------------------------------------------------------------------
    data/lines/snapshots/<game_id>_close_<YYYYMMDD_HHMM>.csv             (props)
    data/lines/snapshots/<game_id>_close_mainline_<YYYYMMDD_HHMM>.csv    (mainline)

CLI
---
Fire RIGHT NOW (test):
    python scripts/capture_closing_lines.py --game-id 0042500315 --now

Fire at a wall-clock UTC time (e.g. tonight 00:34 UTC for WCF G5):
    python scripts/capture_closing_lines.py --game-id 0042500315 --at-utc 2026-05-27T00:34:00

Schedule TWO captures (00:30 + 00:34 UTC) in-process — sleeps + re-fires:
    python scripts/capture_closing_lines.py --game-id 0042500315 \
        --at-utc 2026-05-27T00:30:00 --then-at-utc 2026-05-27T00:34:00

Windows Task Scheduler one-liner (registers a one-shot task that fires once):
    schtasks /Create /SC ONCE /TN "NBA_ClosingLine_WCF_G5" \
        /TR "C:\\Users\\neelj\\anaconda3\\envs\\basketball_ai\\python.exe \
        C:\\Users\\neelj\\nba-ai-system\\scripts\\capture_closing_lines.py \
        --game-id 0042500315 --now" \
        /ST 20:30 /SD 05/26/2026 /F
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Import the Pinnacle scraper's run_once so we share the exact transport
# (curl_cffi chrome120, dedup cache, schema).
from scripts.pinnacle_scraper import run_once as _pin_run_once  # noqa: E402

_LINES_DIR = _ROOT / "data" / "lines"
_SNAPSHOTS_DIR = _LINES_DIR / "snapshots"
_HEARTBEAT_PATH = _ROOT / "data" / "cache" / "closing_capture_heartbeat.txt"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")


def write_heartbeat(note: str = "alive") -> None:
    """Stamp `data/cache/closing_capture_heartbeat.txt` with current UTC
    timestamp + PID + a short status note. The watchdog (see
    ``scripts/closing_capture_watchdog.py``) reads this file to detect a dead
    capture daemon and respawn it before tip-off.

    Best-effort: any IO error is swallowed so a transient disk issue can't
    break the actual capture path.
    """
    try:
        _HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        _HEARTBEAT_PATH.write_text(
            f"{ts}\tpid={os.getpid()}\tstatus={note}\n",
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[capture_closing_lines][warn] heartbeat write failed: {exc}")


def _today_iso() -> str:
    # Pinnacle scraper writes to data/lines/<local-date>_pin.csv — the date
    # is local. We mirror that here so the source-file path matches.
    return datetime.now().strftime("%Y-%m-%d")


def _atomic_copy(src: Path, dst: Path) -> None:
    """Copy src -> dst via a temp file in dst's dir, then os.replace.
    Guarantees no half-written file is observable by a concurrent reader."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def capture_now(game_id: str, label: str = "close") -> dict:
    """Run a single Pin scrape + copy both day-files into snapshots/.

    Returns a small summary dict including byte sizes and target paths.
    """
    print(f"[capture_closing_lines] firing Pinnacle scrape "
          f"for game_id={game_id} at {datetime.now(timezone.utc).isoformat()} UTC")
    write_heartbeat(note=f"firing_{label}")
    summary = _pin_run_once(fetch_props=True)
    print(f"[capture_closing_lines] scrape summary: "
          f"matchups={summary.get('n_matchups')} "
          f"props={summary.get('n_player_props')} "
          f"prop_rows_written={summary.get('n_prop_rows_written')} "
          f"mainline_rows_written={summary.get('n_mainline_rows_written')}")

    today = _today_iso()
    stamp = _utc_stamp()
    src_props = _LINES_DIR / f"{today}_pin.csv"
    src_main = _LINES_DIR / f"{today}_pin_mainline.csv"
    dst_props = _SNAPSHOTS_DIR / f"{game_id}_{label}_{stamp}.csv"
    dst_main = _SNAPSHOTS_DIR / f"{game_id}_{label}_mainline_{stamp}.csv"

    out: dict = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "game_id": game_id,
        "label": label,
        "src_props": str(src_props),
        "src_mainline": str(src_main),
        "dst_props": str(dst_props),
        "dst_mainline": str(dst_main),
        "props_bytes": 0,
        "mainline_bytes": 0,
        "scrape_summary": summary,
    }

    if src_props.exists():
        _atomic_copy(src_props, dst_props)
        out["props_bytes"] = dst_props.stat().st_size
        print(f"[capture_closing_lines] wrote {out['props_bytes']:,} bytes -> {dst_props}")
    else:
        print(f"[capture_closing_lines][warn] props src missing: {src_props}")

    if src_main.exists():
        _atomic_copy(src_main, dst_main)
        out["mainline_bytes"] = dst_main.stat().st_size
        print(f"[capture_closing_lines] wrote {out['mainline_bytes']:,} bytes -> {dst_main}")
    else:
        print(f"[capture_closing_lines][warn] mainline src missing: {src_main}")
    return out


def sleep_until_utc(target: datetime) -> None:
    """Block until UTC wall-clock reaches `target`. Handles 'already past' as no-op."""
    now = datetime.now(timezone.utc)
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    delta = (target - now).total_seconds()
    if delta <= 0:
        print(f"[capture_closing_lines] target {target.isoformat()} already past "
              f"(by {-delta:.0f}s) — firing immediately")
        return
    print(f"[capture_closing_lines] sleeping {delta:.0f}s "
          f"(until {target.isoformat()} UTC)")
    # Sleep in 60s chunks so a Ctrl-C is responsive AND we can heartbeat.
    # The watchdog (scripts/closing_capture_watchdog.py) treats a stale
    # heartbeat (>10 min) as proof the daemon is dead and will respawn it.
    end = time.monotonic() + delta
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        write_heartbeat(note=f"sleeping_until_{target.isoformat()}")
        time.sleep(min(60.0, remaining))


def _parse_utc(s: str) -> datetime:
    # Accept '2026-05-27T00:34:00' or '2026-05-27 00:34' or '2026-05-27T00:34:00Z'
    s = s.strip().rstrip("Z")
    fmts = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")
    for f in fmts:
        try:
            return datetime.strptime(s, f).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"unparseable --at-utc value: {s!r}")


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-id", required=True, help="NBA game_id label (e.g. 0042500315)")
    ap.add_argument("--label", default="close",
                    help="Snapshot label (default 'close'; e.g. 'close', 'pre_close', 'open')")
    ap.add_argument("--now", action="store_true",
                    help="Fire immediately and exit")
    ap.add_argument("--at-utc", default=None,
                    help="Sleep until this UTC time then fire (e.g. 2026-05-27T00:34:00)")
    ap.add_argument("--then-at-utc", default=None,
                    help="Optional second fire UTC time (e.g. tip+4min). Useful "
                         "to bracket the actual tip-off.")
    args = ap.parse_args(argv)

    if not args.now and not args.at_utc:
        ap.error("must specify --now or --at-utc")

    # Stamp heartbeat at startup so the watchdog knows we're alive from t=0.
    write_heartbeat(note="startup")

    if args.now:
        capture_now(args.game_id, args.label)
        return 0

    sleep_until_utc(_parse_utc(args.at_utc))
    capture_now(args.game_id, args.label)

    if args.then_at_utc:
        sleep_until_utc(_parse_utc(args.then_at_utc))
        capture_now(args.game_id, args.label)

    return 0


if __name__ == "__main__":
    sys.exit(main())
