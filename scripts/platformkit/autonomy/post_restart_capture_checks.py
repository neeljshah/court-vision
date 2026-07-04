"""scripts.platformkit.autonomy.post_restart_capture_checks -- checks (d) and
(e) of LANE 4's post-`boot.ps1` verifier: per-sport capture-dir freshness and
the wnba shadow-field check. Split out of post_restart_checks.py so both
modules stay under the <=300 LOC rail (behavior-preserving split; mirrors the
http_wedge_reaper/_probe/_io split already used in this package).

See post_restart_verify.py's module docstring for the full check narrative.
Read-only: no flag flip, no data/registry/ write, no PID touched.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_post_restart_verify.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List

from scripts.platformkit.autonomy.post_restart_checks import (
    FAIL,
    PASS,
    PENDING,
    row,
)

_REPO = Path(__file__).resolve().parents[3]
_LINE_HIST = _REPO / "data" / "cache" / "line_history"
_INGAME_GRADE = _REPO / "data" / "cache" / "ingame_grade"

# Capture sports the m2/m6 daemons are declared to cover post-restart
# (inplay_snapshot_daemon.DEFAULT_SPORTS / line_snapshot_daemon.DEFAULT_SPORTS
# -- both 8 sports as of this lane; see verify module docstring for the count).
CAPTURE_SPORTS: List[str] = [
    "nba", "mlb", "soccer", "soccer_intl", "tennis", "wnba", "npb", "kbo",
]

# Shadow fields to look for in a fresh capture row, per sport (only wired for
# wnba as of this lane -- see wnba_ingame_shadow.py / inplay_capture_loop.py).
SHADOW_FIELDS: Dict[str, str] = {"wnba": "model_prob_wnba_shadow"}


def check_capture_dirs(now: float, *,
                       live_game_fn: Callable[[str], bool],
                       fresh_sec: float = 1800.0) -> List[Dict[str, Any]]:
    """(d) capture dirs exist + fresh tick, per sport, ONLY when a live game is
    on. No live game -> PENDING with cause, never FAIL."""
    rows: List[Dict[str, Any]] = []
    for sport in CAPTURE_SPORTS:
        try:
            live = bool(live_game_fn(sport))
        except Exception as exc:  # noqa: BLE001 -- an unknown live state is NOT a FAIL
            rows.append(row(sport, PENDING,
                            "live-game lookup raised %s" % type(exc).__name__))
            continue
        if not live:
            rows.append(row(sport, PENDING, "no live game right now"))
            continue
        line_dir = _LINE_HIST / sport
        if not line_dir.exists():
            rows.append(row(sport, FAIL,
                            "live game but no capture dir data/cache/line_history/%s"
                            % sport))
            continue
        try:
            files = sorted(line_dir.glob("*.jsonl")) + sorted(line_dir.glob("*.json"))
        except Exception as exc:  # noqa: BLE001
            rows.append(row(sport, FAIL, "glob raised %s" % type(exc).__name__))
            continue
        if not files:
            rows.append(row(sport, FAIL,
                            "live game, capture dir exists, but no tick files"))
            continue
        newest = max(f.stat().st_mtime for f in files)
        age = now - newest
        if age <= fresh_sec:
            rows.append(row(sport, PASS,
                            "live game, freshest tick %.0fs old (<=%.0fs)"
                            % (age, fresh_sec)))
        else:
            rows.append(row(sport, FAIL,
                            "live game but freshest tick %.0fs old (>%.0fs)"
                            % (age, fresh_sec)))
    return rows


def check_shadow_field(now: float, *,
                       live_game_fn: Callable[[str], bool],
                       fresh_sec: float = 1800.0) -> List[Dict[str, Any]]:
    """(e) a fresh capture row carries the sport's shadow field, when wired."""
    rows: List[Dict[str, Any]] = []
    for sport, field in SHADOW_FIELDS.items():
        try:
            live = bool(live_game_fn(sport))
        except Exception as exc:  # noqa: BLE001
            rows.append(row("%s_shadow" % sport, PENDING,
                            "live-game lookup raised %s" % type(exc).__name__))
            continue
        if not live:
            rows.append(row("%s_shadow" % sport, PENDING,
                            "no live game right now -- cannot confirm %s" % field))
            continue
        sport_dir = _INGAME_GRADE / sport
        if not sport_dir.exists():
            rows.append(row("%s_shadow" % sport, PENDING,
                            "live game but no ingame_grade capture dir for %s "
                            "yet (known gap -- no dedicated ProcSpec wired)" % sport))
            continue
        try:
            files = sorted(sport_dir.glob("*.jsonl"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception as exc:  # noqa: BLE001
            rows.append(row("%s_shadow" % sport, FAIL, "glob raised %s" % type(exc).__name__))
            continue
        if not files:
            rows.append(row("%s_shadow" % sport, PENDING,
                            "live game, dir exists, but no capture files yet"))
            continue
        newest = files[0]
        age = now - newest.stat().st_mtime
        if age > fresh_sec:
            rows.append(row("%s_shadow" % sport, PENDING,
                            "newest capture file %.0fs old (>%.0fs) -- stale, "
                            "not a confirmed fresh tick" % (age, fresh_sec)))
            continue
        try:
            last_line = None
            with newest.open("r", encoding="ascii", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        last_line = line
            parsed = json.loads(last_line) if last_line else {}
        except Exception as exc:  # noqa: BLE001
            rows.append(row("%s_shadow" % sport, FAIL,
                            "reading last tick raised %s" % type(exc).__name__))
            continue
        if isinstance(parsed, dict) and field in parsed:
            rows.append(row("%s_shadow" % sport, PASS,
                            "fresh tick carries %s=%r" % (field, parsed.get(field))))
        else:
            rows.append(row("%s_shadow" % sport, FAIL,
                            "fresh tick present but missing field %s" % field))
    return rows


__all__ = ["CAPTURE_SPORTS", "SHADOW_FIELDS", "check_capture_dirs", "check_shadow_field"]
