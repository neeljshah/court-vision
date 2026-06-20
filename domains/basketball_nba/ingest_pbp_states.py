"""domains.basketball_nba.ingest_pbp_states -- FINE-RESOLUTION in-game state ingest.

The linescore corpus only reconstructs 3 as-of states per game (end Q1/Q2/Q3). But the
in-game model SERVES at any clock / any margin. ESPN's free summary endpoint carries the
FULL play-by-play array (``payload["plays"]``), and EVERY play exposes cumulative
``homeScore``/``awayScore`` plus ``period.number`` + ``clock.displayValue`` (MM:SS). From
that we reconstruct the score-margin TRAJECTORY at ~2-minute (120 game-second) regulation
intervals -- a much finer as-of grid than the 3 quarter boundaries.

Output parquet (one row per as-of GRID POINT): event_id, date, seconds_remaining,
  home_margin, home_final, away_final, home_win, n_plays_seen. Many rows per game.

LEAK-FREENESS: each grid row is the cumulative score from the LAST play at-or-before the
grid's seconds_remaining -- strictly the PAST of that as-of moment. home_win is the realized
final (the label), never fed as a feature. The pregame Elo p0 is joined later, leak-free.

HONEST: NEVER fabricate a play. Games with a broken/empty plays array are DROPPED.
Reuses the ESPN fetchers (ingest_espn_box). Pure stdlib/pandas. No network at import.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only.
CLI: python -m domains.basketball_nba.ingest_pbp_states --season 2025_26 --sample-k 1
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from domains.basketball_nba.ingest_espn_box import _default_http_get

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={eid}"
_LINESCORES = {
    "2025_26": _REPO / "data" / "domains" / "basketball_nba" / "linescores.parquet",
    "2024_25": _REPO / "data" / "domains" / "basketball_nba" / "linescores_2024_25.parquet",
}
_OUT_DIR = _REPO / "data" / "cache" / "ingame"

_REG_PERIODS = 4
_PERIOD_SEC = 720.0          # 12-minute NBA quarter
_REG_SEC = _REG_PERIODS * _PERIOD_SEC   # 2880
_GRID_STEP = 120.0           # ~2-minute as-of grid


def _clock_seconds(disp: str) -> Optional[float]:
    """Parse an ESPN clock displayValue (MM:SS or SS.s) -> seconds left in the period."""
    try:
        s = str(disp).strip()
        if ":" in s:
            mm, ss = s.split(":")
            return float(mm) * 60.0 + float(ss)
        return float(s)
    except (TypeError, ValueError):
        return None


def _sec_remaining(period: int, clock_sec: float) -> Optional[float]:
    """Regulation seconds remaining from (period, clock-in-period). OT folds to 0."""
    if period < 1:
        return None
    if period > _REG_PERIODS:
        return 0.0                     # any OT moment is end-of-regulation as-of
    return (_REG_PERIODS - period) * _PERIOD_SEC + max(0.0, clock_sec)


def parse_trajectory(payload: dict) -> List[dict]:
    """PURE: ESPN summary payload -> sorted [{seconds_remaining, home_margin}] from plays.

    One entry per play that carries cumulative scores + a parseable clock. Sorted by
    DECREASING seconds_remaining (chronological). Returns [] if the plays array is
    missing/empty/unusable -- the caller then DROPS the game (never fabricated).
    """
    plays = payload.get("plays")
    if not isinstance(plays, list) or not plays:
        return []
    traj: List[dict] = []
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
        traj.append({"seconds_remaining": float(sr),
                     "home_margin": float(hs) - float(as_)})
    traj.sort(key=lambda r: -r["seconds_remaining"])
    return traj


def _final_from_traj(traj: List[dict], payload: dict):
    """(home_final, away_final) from the last play's cumulative scores; (None,None) if absent."""
    plays = payload.get("plays") or []
    for p in reversed(plays):
        hs, as_ = p.get("homeScore"), p.get("awayScore")
        if hs is not None and as_ is not None:
            return float(hs), float(as_)
    return None, None


def grid_states(traj: List[dict], event_id: str, date: str,
                home_final: float, away_final: float,
                step: float = _GRID_STEP) -> List[dict]:
    """As-of grid: every `step` regulation seconds, the margin from the latest PAST play.

    Grid points run from REG_SEC-step down to step (interior of regulation -- we skip the
    trivial sr=REG_SEC tip where margin is always 0 and the post-final sr=0 boundary). For
    each grid sr we take the last trajectory entry with seconds_remaining >= sr (the as-of
    state). Leak-free: only plays at-or-before that moment inform the margin.
    """
    if not traj:
        return []
    home_win = int(home_final > away_final)
    out: List[dict] = []
    i = 0  # pointer into traj (sorted decreasing sr); advances as grid sr decreases
    grid = []
    g = _REG_SEC - step
    while g >= step - 1e-9:
        grid.append(g)
        g -= step
    last_margin = 0.0
    n_seen = 0
    for sr in grid:
        while i < len(traj) and traj[i]["seconds_remaining"] >= sr:
            last_margin = traj[i]["home_margin"]
            i += 1
            n_seen += 1
        out.append({
            "event_id": str(event_id), "date": date,
            "seconds_remaining": float(sr), "home_margin": float(last_margin),
            "home_final": float(home_final), "away_final": float(away_final),
            "home_win": home_win, "n_plays_seen": int(n_seen),
        })
    return out


def fetch_game_states(event_id: str, date: str,
                      http_get: Optional[Callable] = None,
                      step: float = _GRID_STEP) -> List[dict]:
    """Fetch one game's summary and reconstruct its fine-grained as-of grid states ([] on fail)."""
    getter = http_get or _default_http_get
    try:
        payload = getter(_SUMMARY.format(eid=event_id))
    except Exception as exc:  # noqa: BLE001
        log.debug("summary fetch failed eid=%s: %s", event_id, exc)
        return []
    traj = parse_trajectory(payload)
    if not traj:
        return []
    hf, af = _final_from_traj(traj, payload)
    if hf is None or af is None or hf == af:   # need a decided regulation/OT winner
        return []
    return grid_states(traj, event_id, date, hf, af, step=step)


def _season_games(season: str) -> pd.DataFrame:
    """event_id + date for the season, from the existing linescore corpus (date-sorted)."""
    path = _LINESCORES[season]
    df = pd.read_parquet(path)
    df = df.sort_values("date").reset_index(drop=True)
    return df[["event_id", "date"]].copy()


def ingest_season(season: str, sample_k: int = 1, max_games: Optional[int] = None,
                  http_get: Optional[Callable] = None,
                  out_dir: Optional[Path] = None, step: float = _GRID_STEP) -> Path:
    """Ingest fine-grained PBP states for a season; write pbp_states_<season>.parquet.

    sample_k=k keeps every k-th game (deterministic, chronological order) -- a seeded,
    reproducible sample when a full 2-season ingest is too slow. sample_k=1 = full.
    Drops games with broken PBP (never fabricated) and reports coverage in the log.
    """
    out_dir = out_dir or _OUT_DIR
    out = Path(out_dir) / f"pbp_states_{season}.parquet"
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
        else:
            log.debug("dropped game eid=%s (broken/empty PBP)", g["event_id"])
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
    ap = argparse.ArgumentParser(description="Ingest fine-grained NBA PBP in-game states.")
    ap.add_argument("--season", choices=sorted(_LINESCORES), default="2025_26")
    ap.add_argument("--sample-k", type=int, default=1,
                    help="keep every k-th game (deterministic); 1 = full season")
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
