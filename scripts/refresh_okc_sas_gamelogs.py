"""refresh_okc_sas_gamelogs.py — targeted gamelog refresh for OKC + SAS
rotation players for 2025-26 (Regular Season + Playoffs).

Writes BOTH schema variants because different code paths read each:
  - data/nba/gamelog_full_<pid>_2025-26.json  (lowercase keys, DESC by date)
  - data/nba/gamelog_<pid>_2025-26.json       (UPPERCASE keys, ASC by date)

Pulls RS + Playoffs, merges + dedupes by GAME_ID.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
try:
    import src.data.nba_api_headers_patch  # noqa: F401
except Exception as _e:
    print(f"[warn] no headers patch: {_e}", flush=True)

from nba_api.stats.endpoints import playergamelog

_NBA_DIR = os.path.join(PROJECT_DIR, "data", "nba")
_SEASON = "2025-26"
_SLEEP = 0.6
_BACKOFF = 5.0

# Verified IDs (looked up via nba_api.stats.static.players + CommonAllPlayers)
PLAYERS: Dict[str, int] = {
    # OKC
    "Shai Gilgeous-Alexander": 1628983,
    "Chet Holmgren":           1631096,
    "Jalen Williams":          1631114,
    "Isaiah Hartenstein":      1628392,
    "Lu Dort":                 1629652,
    "Alex Caruso":             1627936,
    "Aaron Wiggins":           1630598,
    "Isaiah Joe":              1629637,
    "Cason Wallace":           1641717,
    "Jaylin Williams":         1631119,
    "Kenrich Williams":        1629026,
    "Ajay Mitchell":           1642349,
    # SAS
    "Victor Wembanyama":       1641705,
    "De'Aaron Fox":            1628368,
    "Stephon Castle":          1642264,
    "Devin Vassell":           1630170,
    "Keldon Johnson":          1629640,
    "Harrison Barnes":         203084,
    "Julian Champagnie":       1630577,
    "Luke Kornet":             1628436,
    "Dylan Harper":            1642844,
}


def _parse_min(m) -> float:
    try:
        if isinstance(m, str) and ":" in m:
            p = m.split(":")
            return round(float(p[0]) + float(p[1]) / 60.0, 2)
        return round(float(m), 2)
    except (ValueError, TypeError):
        return 0.0


def _date_key(d) -> datetime:
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(d).strip(), fmt)
        except (ValueError, TypeError):
            continue
    return datetime.min


def _fetch(pid: int, stype: str) -> List[dict]:
    try:
        df = playergamelog.PlayerGameLog(
            player_id=pid, season=_SEASON,
            season_type_all_star=stype, timeout=60,
        ).get_data_frames()[0]
        return df.to_dict(orient="records")
    except Exception as e:
        err = str(e)
        if "429" in err or "rate" in err.lower():
            print(f"    [429] pid={pid} {stype} — backing off {_BACKOFF}s", flush=True)
            time.sleep(_BACKOFF)
            try:
                df = playergamelog.PlayerGameLog(
                    player_id=pid, season=_SEASON,
                    season_type_all_star=stype, timeout=60,
                ).get_data_frames()[0]
                return df.to_dict(orient="records")
            except Exception as e2:
                print(f"    [SKIP] pid={pid} {stype}: {e2}", flush=True)
                return []
        else:
            # Playoffs may not exist for non-playoff teams; only warn for RS.
            if stype == "Regular Season":
                print(f"    [WARN] pid={pid} {stype}: {e}", flush=True)
            return []


def _normalise_rows(raw: List[dict]) -> List[dict]:
    """Return list with both lowercase + uppercase representations available
    later. Here we keep nba_api raw (UPPERCASE) and normalise MIN to float."""
    out = []
    for r in raw:
        upper = {k.upper(): v for k, v in r.items()}
        if "MIN" in upper:
            upper["MIN"] = _parse_min(upper["MIN"])
        out.append(upper)
    return out


def _write_both_schemas(pid: int, rows: List[dict]) -> Dict[str, int]:
    """Write BOTH file variants for `pid`.

    - gamelog_<pid>_<season>.json: UPPERCASE keys, ASC by GAME_DATE
    - gamelog_full_<pid>_<season>.json: lowercase keys, DESC by GAME_DATE
    """
    # ASC by game date for the uppercase file
    asc = sorted(rows, key=lambda r: _date_key(r.get("GAME_DATE")))
    upper_path = os.path.join(_NBA_DIR, f"gamelog_{pid}_{_SEASON}.json")
    with open(upper_path, "w", encoding="utf-8") as f:
        json.dump(asc, f)

    # DESC for the lowercase-keyed _full_ file
    desc = list(reversed(asc))
    lower_desc = [{k.lower(): v for k, v in r.items()} for r in desc]
    full_path = os.path.join(_NBA_DIR, f"gamelog_full_{pid}_{_SEASON}.json")
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(lower_desc, f)

    return {"n_total": len(asc)}


def _summarise(pid: int, name: str) -> dict:
    path = os.path.join(_NBA_DIR, f"gamelog_{pid}_{_SEASON}.json")
    if not os.path.exists(path):
        return {"name": name, "pid": pid, "status": "missing"}
    rows = json.load(open(path, encoding="utf-8"))
    if not rows:
        return {"name": name, "pid": pid, "status": "empty", "n": 0}

    # ASC sorted — last is most recent
    def _safe(r, k):
        try:
            return float(r.get(k, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def _mean(seq, k):
        if not seq:
            return 0.0
        return round(sum(_safe(r, k) for r in seq) / len(seq), 2)

    last10 = rows[-10:]
    last5 = rows[-5:]
    last4 = rows[-4:]  # presumed WCF (or last 4)
    return {
        "name": name,
        "pid": pid,
        "status": "ok",
        "n_games": len(rows),
        "latest_date": rows[-1].get("GAME_DATE"),
        "latest_matchup": rows[-1].get("MATCHUP"),
        "L5_pts": _mean(last5, "PTS"),
        "L5_reb": _mean(last5, "REB"),
        "L5_ast": _mean(last5, "AST"),
        "L5_min": _mean(last5, "MIN"),
        "L10_pts": _mean(last10, "PTS"),
        "L10_min": _mean(last10, "MIN"),
        "last4_dates": [r.get("GAME_DATE") for r in last4],
        "last4_matchups": [r.get("MATCHUP") for r in last4],
        "last4_pts": [_safe(r, "PTS") for r in last4],
        "last4_min": [_safe(r, "MIN") for r in last4],
        "last4_reb": [_safe(r, "REB") for r in last4],
        "last4_ast": [_safe(r, "AST") for r in last4],
    }


def main() -> None:
    t0 = time.time()
    n_ok = 0
    n_err = 0
    n_zero = 0
    per_player = {}
    print(f"[refresh] season={_SEASON}  players={len(PLAYERS)}", flush=True)
    for name, pid in PLAYERS.items():
        print(f"  [{pid}] {name}", flush=True)
        all_rows: List[dict] = []
        for stype in ("Regular Season", "Playoffs"):
            time.sleep(_SLEEP)
            chunk = _fetch(pid, stype)
            chunk = _normalise_rows(chunk)
            all_rows.extend(chunk)
            print(f"     {stype}: {len(chunk)} rows", flush=True)
        # dedupe by GAME_ID
        seen = set()
        deduped = []
        for r in all_rows:
            gid = r.get("GAME_ID")
            if gid in seen:
                continue
            seen.add(gid)
            deduped.append(r)
        try:
            info = _write_both_schemas(pid, deduped)
            n_ok += 1
            if info["n_total"] == 0:
                n_zero += 1
            per_player[name] = info["n_total"]
        except Exception as e:
            print(f"     [WRITE_ERR] {e}", flush=True)
            n_err += 1
            per_player[name] = -1

    elapsed = time.time() - t0
    print(
        f"[refresh] DONE in {elapsed:.1f}s  ok={n_ok}  err={n_err}  zero={n_zero}",
        flush=True,
    )

    # Spot-check
    spot_names = [
        "Shai Gilgeous-Alexander", "Victor Wembanyama",
        "Chet Holmgren", "Keldon Johnson",
    ]
    print("\n========== SPOT CHECKS ==========", flush=True)
    spot = []
    for name in spot_names:
        pid = PLAYERS[name]
        s = _summarise(pid, name)
        spot.append(s)
        print(json.dumps(s, indent=2, default=str), flush=True)

    out = {
        "refreshed_at": datetime.utcnow().isoformat() + "Z",
        "season": _SEASON,
        "n_ok": n_ok,
        "n_err": n_err,
        "n_zero": n_zero,
        "per_player_rows": per_player,
        "spot_checks": spot,
    }
    out_path = os.path.join(PROJECT_DIR, "data", "cache",
                             "refresh_okc_sas_gamelogs_20260526.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n[refresh] report -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
