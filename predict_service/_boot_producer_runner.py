"""predict_service._boot_producer_runner -- repeating producer cadence for boot.ps1.

Runs produce_once(sport='nba') each cycle, sleeping BOOT_INTERVAL seconds between
runs (default 1200 = 20 min). Written by boot.ps1 on first launch; safe to delete.
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
_SPORT = os.environ.get("BOOT_SPORT", "nba")


def _cycle() -> None:
    try:
        path = produce_once(_SPORT)
        print("producer | saved=%s" % path, flush=True)
    except Exception as exc:
        traceback.print_exc()
        print("producer | error: %s" % exc, flush=True)


if __name__ == "__main__":
    print("producer | started sport=%s interval=%ss" % (_SPORT, _INTERVAL), flush=True)
    _cycle()
    while True:
        time.sleep(_INTERVAL)
        _cycle()