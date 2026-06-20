"""domains.basketball_nba.ingest_possession_states -- FINE-RESOLUTION in-game state
ingest WITH a POSSESSION / PACE / SCORING-RUN detail layer (sibling of
ingest_pbp_states + ingest_pbp_foul_states).

The linescore corpus only carries 3 as-of states (end Q1/Q2/Q3); ingest_pbp_states
reconstructs a finer margin trajectory; this module asks the next question the memory
flags as the known next lift: does the PBP POSSESSION / PACE / SCORING-RUN micro-state
-- detail the linescore corpus throws away -- carry extra held-out calibration on top of
the proven (margin, time) base?

PAYLOAD-PROBE (must-fix #6, verified live on event 401704627): ESPN's free summary
endpoint ``payload["plays"]`` exposes, per play: ``homeScore``/``awayScore``,
``period.number``, ``clock.displayValue`` (MM:SS), ``type.text`` (e.g. 'Defensive
Rebound', 'Bad Pass Turnover', '... Jump Shot', 'End Period'), ``team.id``, and
``scoringPlay`` (bool). Every detail field below is derived ZERO-NETWORK from that one
already-fetched array -- no second network tier is needed, so nothing is dropped on a
network-tier reclassification.

A POSSESSION is counted as ENDED at each possession-ending event reconstructed from the
plays in chronological order: a made field goal (scoringPlay on a shot/layup/dunk), a
defensive rebound, a turnover, or End Period. This is a standard, deterministic,
rule-light PBP possession proxy (it does NOT chase every NBA edge case -- it is a stable
count, not an exact official possession ledger). From the running possession count and
the running score we derive, on the SAME ~2-minute regulation as-of grid as the siblings:

Output parquet (one row per grid point) -- FROZEN base schema PLUS additive detail cols:
  game_id, asof_idx, state_diff (home_margin), frac_elapsed, outcome (home_win),
  + possessions_elapsed : cumulative possessions ended at-or-before this as-of moment
  + pace_so_far         : possessions_elapsed / game-seconds elapsed (per-row rate)
  + run_diff            : signed length of the CURRENT uninterrupted scoring run
                          (+ = home scored the last k unanswered points-events,
                           - = away) measured in scoring EVENTS
  + poss_since_lead_change : possessions since the last lead change (sign flip of margin)
  (diagnostics kept: seconds_remaining, home_margin, home_final, away_final, n_plays_seen)

LEAK-FREENESS: every grid row aggregates ONLY plays at-or-before its seconds_remaining
(strictly the past of that as-of moment); pace_so_far divides by elapsed time, never by
total game time; there is NO *_final / *_total quantity on any per-tick row except the
realized label outcome (home_win) and the final-score DIAGNOSTICS, which are never used
as features. asof_idx is a per-game monotone index into the as-of grid.

HONEST: NEVER fabricate a play. Games with a broken/empty plays array are DROPPED.
Reuses the ESPN fetcher + the proven grid/clock helpers from ingest_pbp_states. Pure
stdlib/pandas. No network at import.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only.
CLI: python -m domains.basketball_nba.ingest_possession_states --season 2025_26
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

# Shot-make type tokens (a scoringPlay on one of these = a made FG = possession end).
_MADE_TOKENS = ("shot", "layup", "dunk", "tip")


def _is_possession_end(ttxt: str, scoring: bool) -> bool:
    """True iff this play type ends a possession (made FG / def rebound / TO / end period).

    Rule-light, deterministic proxy: a made field goal (scoringPlay on a shot/layup/
    dunk/tip), a DEFENSIVE rebound, any turnover, or End Period. Free throws and fouls
    are deliberately NOT counted (they do not, on their own, flip possession in this
    proxy) -- this keeps the count stable rather than chasing every NBA edge case.
    """
    t = ttxt.lower()
    if "turnover" in t:
        return True
    if "defensive rebound" in t:
        return True
    if "end period" in t or "end game" in t:
        return True
    if scoring and any(tok in t for tok in _MADE_TOKENS):
        return True
    return False


def parse_possession_trajectory(payload: dict) -> List[dict]:
    """PURE: summary payload -> sorted [{seconds_remaining, home_margin,
    possessions_elapsed, run_diff, poss_since_lead_change}] reconstructed cumulatively
    from the plays in chronological order. Sorted DECREASING sr (chronological). [] if
    unusable. All quantities are as-of the play (strictly past) -- no future leak.
    """
    plays = payload.get("plays")
    if not isinstance(plays, list) or not plays:
        return []
    rows: List[dict] = []
    poss = 0                 # cumulative possessions ended
    run_sign = 0             # +1 home / -1 away owns the current scoring run
    run_len = 0              # length of the current uninterrupted scoring run (events)
    last_lead_sign = 0       # sign of margin at the last observed lead state
    poss_at_lead_change = 0  # possessions count when the lead last flipped
    prev_h = prev_a = 0
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
        hs, as_ = int(hs), int(as_)
        # --- scoring run: who scored on THIS play (compare to previous cumulative) ---
        scored = 0
        if hs > prev_h and as_ == prev_a:
            scored = 1            # home scored
        elif as_ > prev_a and hs == prev_h:
            scored = -1           # away scored
        if scored != 0:
            if scored == run_sign:
                run_len += 1
            else:
                run_sign, run_len = scored, 1
        # --- possession count ---
        ttxt = str((p.get("type") or {}).get("text") or "")
        if _is_possession_end(ttxt, bool(p.get("scoringPlay"))):
            poss += 1
        # --- lead change (sign flip of margin) ---
        margin = hs - as_
        lead_sign = (margin > 0) - (margin < 0)
        if lead_sign != 0 and last_lead_sign != 0 and lead_sign != last_lead_sign:
            poss_at_lead_change = poss
        if lead_sign != 0:
            last_lead_sign = lead_sign
        rows.append({
            "seconds_remaining": float(sr),
            "home_margin": float(margin),
            "possessions_elapsed": int(poss),
            "run_diff": float(run_sign * run_len),
            "poss_since_lead_change": int(poss - poss_at_lead_change),
        })
        prev_h, prev_a = hs, as_
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
    """As-of grid: every `step` reg-seconds, the margin AND possession micro-state from
    the latest PAST play. Leak-free: only plays at-or-before each grid sr inform it.
    asof_idx is a 0-based per-game index into the (decreasing-sr) grid. pace_so_far
    divides possessions by ELAPSED game-seconds (never total) -- no future leak.
    """
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
    last = {"home_margin": 0.0, "possessions_elapsed": 0,
            "run_diff": 0.0, "poss_since_lead_change": 0}
    n_seen = 0
    for idx, sr in enumerate(grid):
        while i < len(traj) and traj[i]["seconds_remaining"] >= sr:
            last = traj[i]
            i += 1
            n_seen += 1
        elapsed = max(1.0, _REG_SEC - float(sr))
        frac = 1.0 - float(sr) / _REG_SEC
        poss = int(last["possessions_elapsed"])
        out.append({
            "game_id": str(event_id), "asof_idx": int(idx), "date": date,
            "seconds_remaining": float(sr), "frac_elapsed": float(frac),
            "state_diff": float(last["home_margin"]),
            "home_margin": float(last["home_margin"]),
            "possessions_elapsed": poss,
            "pace_so_far": float(poss) / elapsed,
            "run_diff": float(last["run_diff"]),
            "poss_since_lead_change": int(last["poss_since_lead_change"]),
            "home_final": float(home_final), "away_final": float(away_final),
            "outcome": home_win, "n_plays_seen": int(n_seen),
        })
    return out


def fetch_game_states(event_id: str, date: str,
                      http_get: Optional[Callable] = None,
                      step: float = _GRID_STEP) -> List[dict]:
    """Fetch one game's summary, reconstruct margin+possession as-of grid ([] on fail)."""
    getter = http_get or _default_http_get
    try:
        payload = getter(_SUMMARY.format(eid=event_id))
    except Exception as exc:  # noqa: BLE001
        log.debug("summary fetch failed eid=%s: %s", event_id, exc)
        return []
    traj = parse_possession_trajectory(payload)
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
    """Ingest fine-grained margin+possession PBP states; write
    possession_states_<season>.parquet. sample_k keeps every k-th game (deterministic).
    """
    out_dir = out_dir or _OUT_DIR
    out = Path(out_dir) / f"possession_states_{season}.parquet"
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
    ap = argparse.ArgumentParser(description="Ingest fine-grained NBA PBP margin+possession states.")
    ap.add_argument("--season", choices=sorted(_LINESCORES), default="2025_26")
    ap.add_argument("--sample-k", type=int, default=1)
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--step", type=float, default=_GRID_STEP)
    args = ap.parse_args(argv)
    out = ingest_season(args.season, sample_k=args.sample_k,
                        max_games=args.max_games, step=args.step)
    if out.exists():
        df = pd.read_parquet(out)
        print(f"season={args.season} states={len(df)} games={df['game_id'].nunique()} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
