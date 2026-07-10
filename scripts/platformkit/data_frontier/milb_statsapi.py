"""scripts.platformkit.data_frontier.milb_statsapi -- MiLB pipeline via
statsapi.mlb.com sportId 11-14 (frontier rank 5, KEYLESS -- same host + JSON GET
the live GUMBO feed already uses; client REUSED from
scripts.platformkit.ingame.game_pk_bridge_live._http_get_json, not re-derived).

WHAT: current-season MiLB active rosters (default AAA, sportId 11) + a recent
transactions window (both the MiLB-side sportIds AND sportId 1, because a
call-up/debut move -- "recalled", "selected the contract of" -- is posted on the
MLB team's ledger, not the AAA team's). This is the roster-freshness signal for
debut games.

Endpoints (all probed live 2026-07-09, 200 + real rows):
  /api/v1/teams?sportId={11..14}&season={Y}            30 AAA teams
  /api/v1/teams/{teamId}/roster?rosterType=active      27-man active roster
  /api/v1/transactions?startDate=..&endDate=..&sportId={id}   504 rows/9d @ 11

OUTPUT (as-of-dated, skip-if-captured-today == the daily watermark):
  data/domains/mlb/milb/rosters_{level}_{as_of}.jsonl   one line per (team, player)
  data/domains/mlb/milb/transactions_{as_of}.jsonl      one line per transaction

UTC/ET: the transactions window is [as_of-15d, as_of+1d] -- a date RANGE, so both
the ET and UTC "today" candidates are inside it at either skew direction; the +1
end date just returns nothing extra when it is still in the future.

POLITENESS (binding): 1 req/s via _politeness.polite_sleep, 35s timeout, honest
FAIL rows logged -- never worked around. ~33 requests/day at AAA-only defaults.

Autoloop seam: run_daily() is the no-arg-required entrypoint for
maintenance_templates.run_all() (job M09, PENDING-RESTART until m38 bounces).

CLI: python -m scripts.platformkit.data_frontier.milb_statsapi [--sport-ids 11]
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.data_frontier._politeness import log_line, polite_sleep
from scripts.platformkit.ingame.game_pk_bridge_live import _http_get_json

_REPO = Path(__file__).resolve().parents[3]
_OUT_DIR = _REPO / "data" / "domains" / "mlb" / "milb"
_LOG_FP = _REPO / "data" / "cache" / "logs" / "milb_statsapi.log"
_MATCHUP_DIR = _REPO / "data" / "domains" / "mlb" / "matchup"

_BASE = "https://statsapi.mlb.com/api/v1"
_SPORT_LEVELS: Dict[int, str] = {11: "aaa", 12: "aa", 13: "high_a", 14: "single_a"}
_TX_WINDOW_DAYS = 15
_DELAY_S = 1.0
_TIMEOUT_S = 35.0

HttpGet = Callable[[str], Any]


def _default_http(url: str) -> Optional[Any]:
    return _http_get_json(url, timeout=_TIMEOUT_S)


def _write_jsonl(fp: Path, rows: List[Dict[str, Any]]) -> None:
    fp.parent.mkdir(parents=True, exist_ok=True)
    tmp = fp.with_suffix(".tmp.jsonl")
    with open(tmp, "w", encoding="ascii", errors="replace") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    tmp.replace(fp)


def _roster_rows(as_of: str, sport_id: int, team: Dict[str, Any],
                 roster: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for slot in roster:
        person = slot.get("person", {}) or {}
        out.append({
            "as_of": as_of, "sport_id": sport_id, "level": _SPORT_LEVELS[sport_id],
            "team_id": team.get("id"), "team_name": team.get("name"),
            "team_abbr": team.get("abbreviation"),
            "parent_org_id": team.get("parentOrgId"),
            "parent_org_name": team.get("parentOrgName"),
            "player_id": person.get("id"), "player_name": person.get("fullName"),
            "position": (slot.get("position", {}) or {}).get("abbreviation"),
            "status_code": (slot.get("status", {}) or {}).get("code"),
            "status_desc": (slot.get("status", {}) or {}).get("description"),
        })
    return out


def _tx_row(as_of: str, sport_id: int, tx: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "as_of": as_of, "tx_sport_id": sport_id, "tx_id": tx.get("id"),
        "player_id": (tx.get("person", {}) or {}).get("id"),
        "player_name": (tx.get("person", {}) or {}).get("fullName"),
        "from_team_id": (tx.get("fromTeam", {}) or {}).get("id"),
        "from_team": (tx.get("fromTeam", {}) or {}).get("name"),
        "to_team_id": (tx.get("toTeam", {}) or {}).get("id"),
        "to_team": (tx.get("toTeam", {}) or {}).get("name"),
        "date": tx.get("date"), "effective_date": tx.get("effectiveDate"),
        "type_code": tx.get("typeCode"), "type_desc": tx.get("typeDesc"),
        "description": tx.get("description"),
    }


def pull(sport_ids: Optional[List[int]] = None, *, as_of: Optional[str] = None,
         season: Optional[int] = None, http: HttpGet = _default_http,
         out_dir: Path = _OUT_DIR, log_path: Path = _LOG_FP,
         delay_s: float = _DELAY_S) -> Dict[str, Any]:
    """One as-of-day capture: rosters per level + one transactions window.
    Idempotent: an existing dated output file is a CACHED skip (the watermark)."""
    sport_ids = sport_ids or [11]
    bad = [s for s in sport_ids if s not in _SPORT_LEVELS]
    if bad:
        raise ValueError("unknown MiLB sportId(s) %r (know %s)" % (bad, sorted(_SPORT_LEVELS)))
    as_of = as_of or date.today().isoformat()
    season = season or int(as_of[:4])
    last: Optional[float] = None
    summary: Dict[str, Any] = {"as_of": as_of, "rosters": {}, "transactions": None,
                               "out_dir": str(out_dir)}

    for sid in sport_ids:
        level = _SPORT_LEVELS[sid]
        fp = out_dir / f"rosters_{level}_{as_of}.jsonl"
        if fp.exists():
            summary["rosters"][level] = {"status": "CACHED",
                                          "n_rows": sum(1 for _ in open(fp, encoding="ascii"))}
            continue
        last = polite_sleep(delay_s, last)
        teams_js = http(f"{_BASE}/teams?sportId={sid}&season={season}")
        teams = (teams_js or {}).get("teams", []) if isinstance(teams_js, dict) else []
        if not teams:
            summary["rosters"][level] = {"status": "FAIL", "n_rows": 0}
            log_line(log_path, f"FAIL teams sportId={sid} season={season}")
            continue
        rows: List[Dict[str, Any]] = []
        n_team_fail = 0
        for team in teams:
            last = polite_sleep(delay_s, last)
            r = http(f"{_BASE}/teams/{team['id']}/roster?rosterType=active&season={season}")
            roster = (r or {}).get("roster", []) if isinstance(r, dict) else []
            if not roster:
                n_team_fail += 1
                log_line(log_path, f"FAIL roster team_id={team.get('id')} ({team.get('name')})")
                continue
            rows.extend(_roster_rows(as_of, sid, team, roster))
        if rows:
            _write_jsonl(fp, rows)
        summary["rosters"][level] = {
            "status": "OK" if rows else "FAIL", "n_teams": len(teams),
            "n_team_fail": n_team_fail, "n_rows": len(rows)}
        log_line(log_path, f"OK rosters {level} {as_of} teams={len(teams)} rows={len(rows)}")

    tx_fp = out_dir / f"transactions_{as_of}.jsonl"
    if tx_fp.exists():
        summary["transactions"] = {"status": "CACHED",
                                   "n_rows": sum(1 for _ in open(tx_fp, encoding="ascii"))}
        return summary
    d0 = date.fromisoformat(as_of)
    start = (d0 - timedelta(days=_TX_WINDOW_DAYS)).isoformat()
    end = (d0 + timedelta(days=1)).isoformat()  # UTC/ET both-candidates cover
    tx_rows: List[Dict[str, Any]] = []
    tx_fail = 0
    for sid in sorted(set(sport_ids) | {1}):  # sportId 1: MLB-side call-up ledger
        last = polite_sleep(delay_s, last)
        js = http(f"{_BASE}/transactions?startDate={start}&endDate={end}&sportId={sid}")
        txs = (js or {}).get("transactions", []) if isinstance(js, dict) else []
        if not txs:
            tx_fail += 1
            log_line(log_path, f"FAIL/EMPTY transactions sportId={sid} {start}..{end}")
            continue
        tx_rows.extend(_tx_row(as_of, sid, t) for t in txs)
    if tx_rows:
        _write_jsonl(tx_fp, tx_rows)
    summary["transactions"] = {"status": "OK" if tx_rows else "FAIL",
                               "window": [start, end], "n_empty_sports": tx_fail,
                               "n_rows": len(tx_rows)}
    log_line(log_path, f"OK transactions {as_of} rows={len(tx_rows)} window={start}..{end}")
    return summary


def run_daily(watermarks: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Autoloop maintenance-job seam (M09). File existence IS the watermark --
    the `watermarks` dict is accepted for call-shape uniformity, unused."""
    return pull()


def latest_roster_fp(level: str = "aaa", out_dir: Path = _OUT_DIR) -> Optional[Path]:
    files = sorted(out_dir.glob(f"rosters_{level}_????-??-??.jsonl"))
    return files[-1] if files else None


def join_rate_vs_savant(roster_fp: Optional[Path] = None,
                        matchup_dir: Path = _MATCHUP_DIR) -> Dict[str, Any]:
    """Honest join rate: MiLB roster player ids vs the mlbam ids present in the
    savant-built profile parquets (batter/pitcher pitch profiles). Low is EXPECTED
    -- only MiLB players with prior MLB pitch data can join."""
    import pandas as pd
    roster_fp = roster_fp or latest_roster_fp()
    if roster_fp is None or not roster_fp.exists():
        return {"status": "NO_ROSTER"}
    roster_ids = set()
    with open(roster_fp, encoding="ascii", errors="replace") as f:
        for line in f:
            pid = json.loads(line).get("player_id")
            if pid is not None:
                roster_ids.add(int(pid))
    savant_ids: set = set()
    n_profiles = 0
    for name, col in (("batter_pitch_profiles.parquet", "batter"),
                      ("pitcher_pitch_profiles.parquet", "pitcher")):
        fp = matchup_dir / name
        if not fp.exists():
            continue
        n_profiles += 1
        savant_ids |= set(pd.read_parquet(fp, columns=[col])[col].astype("int64"))
    if not roster_ids or not n_profiles:
        return {"status": "NO_DATA", "n_roster_ids": len(roster_ids),
                "n_profile_files": n_profiles}
    joined = roster_ids & savant_ids
    return {"status": "OK", "roster_fp": str(roster_fp),
            "n_roster_ids": len(roster_ids), "n_savant_ids": len(savant_ids),
            "n_joined": len(joined),
            "join_rate": round(len(joined) / len(roster_ids), 4)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="MiLB rosters + transactions via statsapi (sportId 11-14).")
    ap.add_argument("--sport-ids", nargs="+", type=int, default=[11])
    ap.add_argument("--join-check", action="store_true",
                    help="also print the savant join-rate for the latest AAA roster")
    a = ap.parse_args(argv)
    res = pull(a.sport_ids)
    if a.join_check:
        res["savant_join"] = join_rate_vs_savant()
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["pull", "run_daily", "join_rate_vs_savant", "latest_roster_fp",
           "_SPORT_LEVELS", "_OUT_DIR"]
