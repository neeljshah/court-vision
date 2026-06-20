"""domains.basketball_nba.ingest_pbp_foul_states -- FINE-RESOLUTION in-game state
ingest WITH a FOUL-TROUBLE detail layer (sibling of ingest_pbp_states).

The proven base+prior in-game model uses (margin, time, p0). This module asks whether
the PBP FOUL STATE -- a detail the linescore corpus throws away -- carries extra
held-out calibration. ESPN's free summary endpoint exposes a foul event per whistle
(``type.text`` contains 'foul') with the COMMITTING ``team.id``; the header competitors
map team.id -> home/away. From that we reconstruct, on the SAME ~2-minute regulation
as-of grid as ingest_pbp_states, the CUMULATIVE fouls committed by each side and the
signed FOUL DIFFERENTIAL (away_fouls - home_fouls = how much MORE the away side has
fouled = home's foul-position advantage; more opponent free throws coming).

Output parquet (one row per grid point): event_id, date, seconds_remaining,
  home_margin, home_fouls, away_fouls, foul_diff (away-home), home_final, away_final,
  home_win, n_plays_seen. Many rows per game.

LEAK-FREENESS: every grid row aggregates ONLY plays at-or-before its seconds_remaining
(strictly the past of that as-of moment). home_win is the realized label, never a
feature. The pregame Elo p0 is joined later, leak-free.

HONEST: NEVER fabricate a play or a foul. A foul whose committing team.id maps to
neither side is dropped from the count (not guessed). Games with a broken/empty plays
array are DROPPED. Reuses the ESPN fetcher + the proven grid/clock helpers from
ingest_pbp_states. Pure stdlib/pandas. No network at import.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only.
CLI: python -m domains.basketball_nba.ingest_pbp_foul_states --season 2025_26
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from domains.basketball_nba.ingest_espn_box import _default_http_get
from domains.basketball_nba.ingest_pbp_states import (
    _REG_SEC,
    _GRID_STEP,
    _clock_seconds,
    _sec_remaining,
)

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={eid}"
_LINESCORES = {
    "2025_26": _REPO / "data" / "domains" / "basketball_nba" / "linescores.parquet",
    "2024_25": _REPO / "data" / "domains" / "basketball_nba" / "linescores_2024_25.parquet",
}
_OUT_DIR = _REPO / "data" / "cache" / "ingame"


def home_away_ids(payload: dict) -> Tuple[Optional[str], Optional[str]]:
    """(home_team_id, away_team_id) as strings from the summary header competitors."""
    comps = (((payload.get("header") or {}).get("competitions") or [{}])[0]
             .get("competitors") or [])
    home = away = None
    for c in comps:
        if c.get("homeAway") == "home":
            home = str(c.get("id"))
        elif c.get("homeAway") == "away":
            away = str(c.get("id"))
    return home, away


def parse_foul_trajectory(payload: dict) -> List[dict]:
    """PURE: summary payload -> sorted [{seconds_remaining, home_margin, home_fouls,
    away_fouls}] reconstructed cumulatively from the plays.

    A play increments the committing side's running foul count iff its type.text
    contains 'foul' AND its team.id maps to a known side (else the foul is dropped, not
    guessed). Sorted by DECREASING seconds_remaining (chronological). [] if unusable.
    """
    plays = payload.get("plays")
    if not isinstance(plays, list) or not plays:
        return []
    home_id, away_id = home_away_ids(payload)
    if home_id is None or away_id is None:
        return []
    # Walk plays in their native (chronological) order, accumulating fouls.
    rows: List[dict] = []
    hf = af = 0
    for p in plays:
        hs, as_ = p.get("homeScore"), p.get("awayScore")
        per = (p.get("period") or {}).get("number")
        clk = (p.get("clock") or {}).get("displayValue")
        if hs is None or as_ is None or per is None:
            continue
        cs = _clock_seconds(clk)
        if cs is None:
            continue
        sr = _sec_remaining(int(per), cs)
        if sr is None:
            continue
        ttxt = str((p.get("type") or {}).get("text") or "").lower()
        if "foul" in ttxt:
            tid = str((p.get("team") or {}).get("id"))
            if tid == home_id:
                hf += 1
            elif tid == away_id:
                af += 1
        rows.append({"seconds_remaining": float(sr),
                     "home_margin": float(hs) - float(as_),
                     "home_fouls": hf, "away_fouls": af})
    rows.sort(key=lambda r: -r["seconds_remaining"])
    return rows


def _final_scores(payload: dict) -> Tuple[Optional[float], Optional[float]]:
    for p in reversed(payload.get("plays") or []):
        hs, as_ = p.get("homeScore"), p.get("awayScore")
        if hs is not None and as_ is not None:
            return float(hs), float(as_)
    return None, None


def grid_states(traj: List[dict], event_id: str, date: str,
                home_final: float, away_final: float,
                step: float = _GRID_STEP) -> List[dict]:
    """As-of grid: every `step` reg-seconds, the margin AND cumulative foul state from
    the latest PAST play. Leak-free: only plays at-or-before each grid sr inform it."""
    if not traj:
        return []
    home_win = int(home_final > away_final)
    out: List[dict] = []
    i = 0
    grid: List[float] = []
    g = _REG_SEC - step
    while g >= step - 1e-9:
        grid.append(g)
        g -= step
    last = {"home_margin": 0.0, "home_fouls": 0, "away_fouls": 0}
    n_seen = 0
    for sr in grid:
        while i < len(traj) and traj[i]["seconds_remaining"] >= sr:
            last = traj[i]
            i += 1
            n_seen += 1
        hf, af = int(last["home_fouls"]), int(last["away_fouls"])
        out.append({
            "event_id": str(event_id), "date": date,
            "seconds_remaining": float(sr), "home_margin": float(last["home_margin"]),
            "home_fouls": hf, "away_fouls": af, "foul_diff": float(af - hf),
            "home_final": float(home_final), "away_final": float(away_final),
            "home_win": home_win, "n_plays_seen": int(n_seen),
        })
    return out


def fetch_game_states(event_id: str, date: str,
                      http_get: Optional[Callable] = None,
                      step: float = _GRID_STEP) -> List[dict]:
    """Fetch one game's summary, reconstruct fine-grained margin+foul as-of grid ([] fail)."""
    getter = http_get or _default_http_get
    try:
        payload = getter(_SUMMARY.format(eid=event_id))
    except Exception as exc:  # noqa: BLE001
        log.debug("summary fetch failed eid=%s: %s", event_id, exc)
        return []
    traj = parse_foul_trajectory(payload)
    if not traj:
        return []
    hf, af = _final_scores(payload)
    if hf is None or af is None or hf == af:
        return []
    return grid_states(traj, event_id, date, hf, af, step=step)


def _season_games(season: str) -> pd.DataFrame:
    df = pd.read_parquet(_LINESCORES[season]).sort_values("date").reset_index(drop=True)
    return df[["event_id", "date"]].copy()


def ingest_season(season: str, sample_k: int = 1, max_games: Optional[int] = None,
                  http_get: Optional[Callable] = None,
                  out_dir: Optional[Path] = None, step: float = _GRID_STEP) -> Path:
    """Ingest fine-grained margin+foul PBP states; write pbp_foul_states_<season>.parquet."""
    out_dir = out_dir or _OUT_DIR
    out = Path(out_dir) / f"pbp_foul_states_{season}.parquet"
    games = _season_games(season)
    if sample_k > 1:
        games = games.iloc[::sample_k].reset_index(drop=True)
    if max_games is not None:
        games = games.head(max_games)
    rows: List[dict] = []
    ok = 0
    for _, g in games.iterrows():
        date = g["date"].strftime("%Y%m%d") if hasattr(g["date"], "strftime") else str(g["date"])
        st = fetch_game_states(str(g["event_id"]), date, http_get=http_get, step=step)
        if st:
            rows.extend(st)
            ok += 1
    df = pd.DataFrame(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
        df.to_parquet(out, index=False)
    spg = (len(df) / ok) if ok else 0.0
    log.info("season=%s attempted=%d ok=%d states=%d states/game=%.1f -> %s",
             season, len(games), ok, len(df), spg, out)
    return out


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ingest fine-grained NBA PBP margin+foul states.")
    ap.add_argument("--season", choices=sorted(_LINESCORES), default="2025_26")
    ap.add_argument("--sample-k", type=int, default=1)
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--step", type=float, default=_GRID_STEP)
    args = ap.parse_args(argv)
    out = ingest_season(args.season, sample_k=args.sample_k,
                        max_games=args.max_games, step=args.step)
    if out.exists():
        df = pd.read_parquet(out)
        print(f"season={args.season} states={len(df)} games={df['event_id'].nunique()} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
