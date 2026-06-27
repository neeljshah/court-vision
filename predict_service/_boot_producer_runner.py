"""predict_service._boot_producer_runner -- repeating producer cadence for boot.ps1.

Runs produce_once(sport) for EACH sport in BOOT_SPORTS (comma-separated, default
"nba,mlb,soccer_intl") every cycle, sleeping BOOT_INTERVAL seconds between cycles
(default 1200 = 20 min). Producing every live sport (not just nba) is what keeps the
canonical store fresh for /api/v1/bestbets/<sport> -- nba alone is offseason-empty, so
the mlb + soccer boards used to go stale/unavailable. BOOT_SPORT (singular) is still
honored for backward compatibility. Written by boot.ps1 on first launch; safe to delete.
"""
from __future__ import annotations
import os
import sys
import time
import traceback
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.produce import produce_once

_INTERVAL = max(60, int(os.environ.get("BOOT_INTERVAL", "1200")))


def _sports() -> list:
    """Live sports to produce each cycle. BOOT_SPORTS (csv) wins; else BOOT_SPORT; else
    the default live set. Deduped, order-preserving, blanks dropped."""
    raw = os.environ.get("BOOT_SPORTS") or os.environ.get("BOOT_SPORT") \
        or "nba,mlb,soccer_intl"
    seen: set = set()
    out: list = []
    for s in raw.split(","):
        s = s.strip().lower()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _cycle() -> None:
    for sport in _sports():
        try:
            path = produce_once(sport)
            print("producer | %s saved=%s" % (sport, path), flush=True)
        except Exception as exc:  # one sport must not stop the rest
            traceback.print_exc()
            print("producer | %s error: %s" % (sport, exc), flush=True)


if __name__ == "__main__":
    print("producer | started sports=%s interval=%ss"
          % (",".join(_sports()), _INTERVAL), flush=True)
    _cycle()
    while True:
        time.sleep(_INTERVAL)
        _cycle()
