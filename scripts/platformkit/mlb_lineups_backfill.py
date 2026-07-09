"""scripts.platformkit.mlb_lineups_backfill -- resumable keyless MLB starting-lineup
backfill (statsapi schedule + boxscore), unblocking rung 5's named blocker (commit
2cb54695): the literal batter-vs-pitcher PA-composition test has no lineups for the
2026 eval games. PRIORITY: the in-game eval corpus's dates first (derived straight from
data/cache/ingame_grade/mlb/*.jsonl -- no guessed calendar), then the full 2025 season
(train-time use), reusing domains.mlb.savant_backfill._season_days (same probables.
parquet schedule source, no re-derivation).

DATE LANDMINE: a grade file's first tick 'ts' is UTC and often already mid-game (an
early-inning tick, not first pitch) -- for ~47% of files (2026-07-09 measured) the UTC
hour is 00-05, meaning the true US game date is ts_date MINUS ONE DAY (west-coast/late
starts roll past UTC midnight). Rather than resolve this precisely (would need an extra
per-event ESPN summary call + team-name matching), this module fetches BOTH ts_date and
ts_date-1 candidate dates and pulls every game on both -- guarantees the real eval game's
date is covered without fragile disambiguation, at the cost of a handful of extra no-op
schedule fetches (measured: 20 unique candidate dates for the 271-file 2026 corpus).

OUTPUT: data/cache/mlb_lineups/<date>.jsonl, one line per game that day:
  {game_pk, date, home, away, home_lineup:[{id,name,order,position}, ...9],
   away_lineup:[...], home_sp:{id,name}, away_sp:{id,name}}
Starting lineup = players whose boxscore battingOrder is a clean multiple of 100 (the
'100'..'900' slot codes; a value like '201' is a mid-game substitution, excluded).
Starting pitcher = boxscore.teams.<side>.pitchers[0] (first pitcher used = the starter;
verified live 2026-07-09 against a completed game, gamePk 824663).

REUSE: schedule fetch + JSON GET are the SAME functions the live 3-way id bridge already
uses (scripts.platformkit.ingame.game_pk_bridge_live._fetch_statsapi_games /
_http_get_json) -- not re-derived here.

POLITENESS (binding): 1 req/s -- lighter than savant's 3s pacing (different, much less
loaded host). Per-date file existence = idempotent skip (same resumability pattern as
savant_backfill's per-day parquet cache). A date with a mix of resolved/unresolved games
(e.g. today's slate, still pregame) writes ONLY the resolved rows and is NOT re-fetched
later -- ponytail: acceptable for a backfill lane whose target is completed games; a
live re-poll of in-progress-today dates is a separate concern if ever needed.

WRITES ONLY data/cache/mlb_lineups/. NEVER data/registry/, no sentinel, no flag, no
$/edge. ASCII-only; <=300 LOC. Per-file test in test_mlb_lineups_backfill.py.

CLI: python -m scripts.platformkit.mlb_lineups_backfill --priority eval
     python -m scripts.platformkit.mlb_lineups_backfill --priority season2025 --max-seconds 3000
     python -m scripts.platformkit.mlb_lineups_backfill --priority both --max-seconds 3000
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame.game_pk_bridge_live import (
    _fetch_statsapi_games, _http_get_json,
)

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_GRADE_DIR = _REPO / "data" / "cache" / "ingame_grade" / "mlb"
_OUT_DIR = _REPO / "data" / "cache" / "mlb_lineups"
_REPORT_FP = _REPO / "data" / "domains" / "mlb" / "mlb_lineups_backfill_report.json"

_BOXSCORE_URL = "https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
_DELAY_S = 1.0
_MAX_CONSECUTIVE_FAILURES = 5

HttpGet = Callable[[str], Any]


def eval_dates(grade_dir: Path = _GRADE_DIR) -> List[str]:
    """Sorted unique candidate dates (ts_date AND ts_date-1, see landmine above) from
    every grade file's FIRST tick. Never guesses a calendar range."""
    dates = set()
    for fp in sorted(grade_dir.glob("*.jsonl")) if grade_dir.exists() else []:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                line = f.readline()
            ts = json.loads(line).get("ts", "")
            dt = datetime.strptime(ts[:10], "%Y-%m-%d")
        except Exception as exc:  # noqa: BLE001 -- an unparseable grade file is an honest skip
            log.debug("eval_dates skip %s: %s", fp, exc)
            continue
        dates.add(dt.strftime("%Y-%m-%d"))
        dates.add((dt - timedelta(days=1)).strftime("%Y-%m-%d"))
    return sorted(dates)


def _starting_lineup(team_box: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Starters only: boxscore battingOrder is a clean multiple of 100 ('100'..'900').
    A value like '201' (slot 2, first substitution) is a mid-game sub, excluded."""
    out: List[Dict[str, Any]] = []
    for p in (team_box.get("players", {}) or {}).values():
        bo = p.get("battingOrder")
        try:
            bo_i = int(bo)
        except (TypeError, ValueError):
            continue
        if bo_i % 100 != 0:
            continue
        person = p.get("person", {}) or {}
        out.append({
            "id": person.get("id"), "name": person.get("fullName"),
            "order": bo_i // 100,
            "position": (p.get("position", {}) or {}).get("abbreviation"),
        })
    out.sort(key=lambda r: r["order"])
    return out


def _starting_pitcher(team_box: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """First pitcher used == the starter (pitchers[] is appearance-ordered)."""
    pitchers = team_box.get("pitchers", []) or []
    if not pitchers:
        return None
    p = (team_box.get("players", {}) or {}).get("ID%s" % pitchers[0])
    if not isinstance(p, dict):
        return None
    person = p.get("person", {}) or {}
    return {"id": person.get("id"), "name": person.get("fullName")}


def _game_lineup_row(date_str: str, game_pk: Any, home_name: str, away_name: str,
                     http: HttpGet) -> Optional[Dict[str, Any]]:
    """One game's lineup row, or None on a boxscore fetch failure."""
    box = http(_BOXSCORE_URL.format(game_pk=game_pk))
    if not isinstance(box, dict):
        return None
    teams = box.get("teams", {}) or {}
    home_box, away_box = teams.get("home", {}) or {}, teams.get("away", {}) or {}
    return {
        "game_pk": int(game_pk), "date": date_str, "home": home_name, "away": away_name,
        "home_lineup": _starting_lineup(home_box), "away_lineup": _starting_lineup(away_box),
        "home_sp": _starting_pitcher(home_box), "away_sp": _starting_pitcher(away_box),
    }


def fetch_date(date_str: str, out_dir: Path, delay_s: float,
               http: HttpGet) -> Dict[str, Any]:
    """One date: idempotent skip if data/cache/mlb_lineups/<date>.jsonl already exists.
    Fetches the day's schedule, then each game's boxscore; stops early after
    _MAX_CONSECUTIVE_FAILURES boxscore misses (politeness stop-rule, same shape as
    savant_backfill). Rows with an empty lineup on BOTH sides (pregame / postponed) are
    dropped, not written -- an honest miss, never a fabricated empty row."""
    fp = out_dir / f"{date_str}.jsonl"
    if fp.exists():
        with open(fp, "r", encoding="ascii", errors="replace") as f:
            n = sum(1 for _ in f)
        return {"date": date_str, "status": "CACHED", "n_games": n}

    games = _fetch_statsapi_games(date_str, http)
    time.sleep(delay_s)
    rows: List[Dict[str, Any]] = []
    consecutive_failures = 0
    for g in games:
        row = _game_lineup_row(date_str, g["game_pk"], g["home"], g["away"], http)
        time.sleep(delay_s)
        if row is None or (not row["home_lineup"] and not row["away_lineup"]):
            consecutive_failures += 1
            log.warning("date %s game_pk %s: no lineup (consecutive=%d)",
                        date_str, g.get("game_pk"), consecutive_failures)
            if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                break
            continue
        consecutive_failures = 0
        rows.append(row)

    if not rows:
        return {"date": date_str, "status": "INSUFFICIENT_DATA" if games else "NO_GAMES",
                "n_games": 0, "n_scheduled": len(games)}
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = fp.with_suffix(".tmp.jsonl")
    with open(tmp, "w", encoding="ascii", errors="replace") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    tmp.replace(fp)
    return {"date": date_str, "status": "OK", "n_games": len(rows),
            "n_scheduled": len(games)}


def run_dates(dates: List[str], out_dir: Path = _OUT_DIR, delay_s: float = _DELAY_S,
             max_seconds: Optional[float] = None,
             http: HttpGet = _http_get_json) -> Dict[str, Any]:
    """Walks `dates` in order, bounded by a wall-clock budget (resumable: a later call
    with the same list picks up wherever the per-date cache files left off)."""
    t0 = time.monotonic()
    results: List[Dict[str, Any]] = []
    for d in dates:
        if max_seconds is not None and (time.monotonic() - t0) > max_seconds:
            results.append({"date": d, "status": "SKIPPED_BUDGET"})
            continue
        results.append(fetch_date(d, out_dir, delay_s, http))
    return {"n_dates": len(dates), "results": results}


def _priority_dates(name: str) -> List[str]:
    if name == "eval":
        return eval_dates()
    if name == "season2025":
        from domains.mlb.savant_backfill import _season_days
        return _season_days(2025)
    if name == "both":
        return eval_dates() + [d for d in _priority_dates("season2025")]
    raise ValueError("unknown --priority %r" % name)


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Resumable keyless MLB starting-lineup backfill.")
    ap.add_argument("--priority", default="eval", choices=["eval", "season2025", "both"])
    ap.add_argument("--max-seconds", type=float, default=None)
    a = ap.parse_args(argv)
    dates = _priority_dates(a.priority)
    res = run_dates(dates, max_seconds=a.max_seconds)
    report = {"priority": a.priority, "as_of": datetime.utcnow().isoformat() + "Z", **res}
    _REPORT_FP.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FP, "w", encoding="ascii", errors="replace") as f:
        json.dump(report, f, indent=2, default=str)
    print(json.dumps({"priority": a.priority, "n_dates": res["n_dates"],
                      "n_ok": sum(1 for r in res["results"] if r["status"] == "OK"),
                      "n_cached": sum(1 for r in res["results"] if r["status"] == "CACHED"),
                      "report_path": str(_REPORT_FP)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["eval_dates", "fetch_date", "run_dates", "_starting_lineup",
           "_starting_pitcher", "_game_lineup_row", "_OUT_DIR", "_GRADE_DIR"]
