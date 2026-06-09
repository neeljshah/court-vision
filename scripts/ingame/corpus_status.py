"""corpus_status.py — what's gradeable, what's missing.

Reports the state of the in-game-vs-Vegas grading corpus so the operator can
see whether the daily logging is keeping up.

For every shadow log in ``data/cache/ingame/unified_shadow_<gid>.jsonl`` and
every in-play CSV in ``data/lines/<date>_{dk,fd}_inplay.csv``, prints a single
matrix of dates with three columns:

  shadow    -- True if a non-trivial shadow log exists for any game on that date
  dk_inplay -- True if data/lines/<date>_dk_inplay.csv exists with content
  fd_inplay -- True if data/lines/<date>_fd_inplay.csv exists with content

A date is GRADEABLE only when shadow AND at least one inplay CSV exist.

The script also prints the current count of gradeable (game_id, date) pairs and
how many more games are needed to hit the n>=10 diverse-games bar at which
per-stat in-game calibration becomes principled (see
docs/VS_VEGAS_ASSESSMENT.md section 2).
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
SHADOW_DIR = _ROOT / "data" / "cache" / "ingame"
LINES_DIR = _ROOT / "data" / "lines"


def shadow_dates() -> dict[str, list[str]]:
    """date -> [gid, ...] with usable (>= 50 snapshot) shadow logs."""
    out: dict[str, list[str]] = defaultdict(list)
    for path in sorted(SHADOW_DIR.glob("unified_shadow_*.jsonl")):
        gid = path.stem.replace("unified_shadow_", "")
        seen_eps = 0
        first_ep = None
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ep = rec.get("snapshot_epoch_ms")
            if ep and ep > 1_000_000_000_000:
                seen_eps += 1
                if first_ep is None or ep < first_ep:
                    first_ep = ep
        if seen_eps < 50 or first_ep is None:
            continue
        d = datetime.fromtimestamp(first_ep / 1000,
                                   tz=timezone.utc).strftime("%Y-%m-%d")
        out[d].append(gid)
    return out


def inplay_dates(book: str) -> set[str]:
    out: set[str] = set()
    for path in LINES_DIR.glob(f"*_{book}_inplay.csv"):
        if path.stat().st_size < 200:
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2})_", path.name)
        if m:
            out.add(m.group(1))
    return out


def main() -> int:
    shadows = shadow_dates()
    dks = inplay_dates("dk")
    fds = inplay_dates("fd")
    all_dates = sorted(set(shadows) | dks | fds)
    if not all_dates:
        print("no shadow logs or inplay CSVs found", file=sys.stderr)
        return 1
    print(f"{'date':<12} {'shadow':>7}  {'dk':>3} {'fd':>3}  {'gradeable':>10}  gids")
    # A shadow log's UTC start often falls just past midnight, so the matching
    # inplay CSV is on the PRIOR local date. Try both.
    from datetime import date as _date, timedelta
    gradeable_pairs = 0
    for d in all_dates:
        shad = bool(shadows.get(d))
        dk = d in dks
        fd = d in fds
        # gradeable: shadow on date d AND (dk/fd csv on d OR d-1)
        prior = None
        try:
            y, m, day = (int(x) for x in d.split("-"))
            prior = (_date(y, m, day) - timedelta(days=1)).strftime("%Y-%m-%d")
        except Exception:
            pass
        gradeable = shad and (
            (dk or fd) or (prior and (prior in dks or prior in fds))
        )
        if gradeable:
            gradeable_pairs += len(shadows[d])
        print(f"{d:<12} {('yes' if shad else '-'):>7}  "
              f"{('yes' if dk else '-'):>3} {('yes' if fd else '-'):>3}  "
              f"{('YES' if gradeable else '-'):>10}  "
              f"{','.join(shadows.get(d, [])) or '-'}")
    print()
    print(f"gradeable (game_id, date) pairs: {gradeable_pairs}")
    print(f"target for principled per-stat calibration: 10")
    print(f"games to go: {max(0, 10 - gradeable_pairs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
