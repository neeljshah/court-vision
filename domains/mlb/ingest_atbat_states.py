"""domains.mlb.ingest_atbat_states -- MLB in-game trajectory ingest (PER-AT-BAT states).

INCREMENT 2 of the MOAT plan. A finer-grid sibling of domains/mlb/ingest_states.py:
where that module emits ~18 half-inning boundary ticks/game, this emits ~60-70 PER-AT-BAT
ticks/game from the SAME ESPN summary plays[] payload we ALREADY fetch (ZERO network),
plus additive leak-free as-of detail columns the half-inning grid cannot express.

PAYLOAD PROBE (MUST-FIX #6 -- VERIFIED zero-network against a live ESPN MLB summary):
  Every play in plays[] carries: atBatId (group key), type.type (start-batterpitcher /
  end-batterpitcher / pitch types / end-inning), period.{type,number}, homeScore,
  awayScore, outs (outs AFTER the play), onFirst/onSecond/onThird (present iff a runner
  is there), pitchCount {balls,strikes} (count BEFORE the pitch), resultCount (after).
  The FIRST play of each real at-bat is type 'start-batterpitcher' and its outs / runners
  / scores are the AS-OF state FACING the batter (leak-free: before this at-bat resolves).
  -> per-at-bat base-out + score state is genuinely zero-network and is emitted here.

  HONEST RECLASSIFICATION (MUST-FIX #6): count_balls / count_strikes AT THE START of an
  at-bat are ALWAYS 0-0 (a new batter starts 0-0); a *varying* count is a PITCH-grid
  feature, which is the deferred 2nd network tier (StatsAPI, ingest_pitch_states.py). So
  count_balls/count_strikes are emitted (present, zero-network) but are CONSTANT 0 at this
  at-bat grid and carry NO as-of signal here -- documented, never fabricated, never sold
  as a per-at-bat detail. The real per-at-bat details are runners/outs/RE24/leverage.

FROZEN base schema (identical to ingest_states.py:8-15 so it gates the same way):
  {sport, game_id, asof_idx, state_diff (home-away as-of), frac_elapsed in [0,1],
   p0 (leak-free pregame P(home win)), outcome in {0,1}}
  Extra cols: home_team, away_team, date, season, half_inning_label.

ADDITIVE leak-free as-of detail cols (the Increment-2 layer):
  count_balls    : int   (as-of start-of-AB count -- CONSTANT 0 at this grid; see above)
  count_strikes  : int   (as-of start-of-AB count -- CONSTANT 0 at this grid; see above)
  runners        : int [0,7]  bitmask bit2=1B bit1=2B bit0=3B, AS-OF at-bat start
  outs           : int [0,2]  outs FACING the batter (as-of start of at-bat)
  base_run_value : float  STATIC RE24 table lookup keyed (runners,outs) -- MUST-FIX #8:
                   a PINNED published constant (Tango/Lichtman/Dolphin "The Book", est.
                   1999-2002 MLB), seasons DISJOINT from the 2022/2023 gate corpora; NO
                   runtime / test-season data-derivation (asserted in the test).
  leverage_bucket: str in {low,mid,high}  STATIC rule over (inning, margin, base-out) --
                   never future-fit.

LEAK-FREENESS: every detail at at-bat k uses ONLY the start-of-AB-k payload (scores,
runners, outs strictly before AB k resolves). p0 uses only games strictly before the
game's date. NO *_final / total column is EVER merged onto a per-tick row.
HONEST: games with missing/broken PBP are DROPPED. Never fabricated.
ASCII only.  <=300 LOC.  No src/kernel/api imports.
CLI: python -m domains.mlb.ingest_atbat_states --season 2023 --sample-k 6
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

# Reuse the half-inning module's verified ESPN plumbing (scoreboard map, http_get,
# team-code dialect, game loader, final score) -- DRY, no re-derivation.
from domains.mlb.ingest_states import (
    _default_http_get,
    _final_score,
    _gc2espn,
    _load_all_games,
    _scoreboard_map,
    _SUMMARY,
    _STD_HALF_INNINGS,
)
from domains.mlb.re24_table import RE24, base_run_value, leverage_bucket

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_OUT_DIR = _REPO / "data" / "cache" / "ingame"

_START_TYPE = "start-batterpitcher"
_END_INNING = "end-inning"


def _runners_bitmask(play: dict) -> int:
    """bit2=1B bit1=2B bit0=3B from onFirst/onSecond/onThird (present iff occupied)."""
    on1 = 1 if play.get("onFirst") else 0
    on2 = 1 if play.get("onSecond") else 0
    on3 = 1 if play.get("onThird") else 0
    return (on1 << 2) | (on2 << 1) | on3


def parse_atbat_states(payload: dict) -> List[dict]:
    """ESPN summary payload -> per-at-bat as-of state rows, in game order.

    Tick = the FIRST play of each at-bat (type 'start-batterpitcher'): its outs / runners
    / scores are the AS-OF state facing the batter (leak-free, before the AB resolves).
    Returns [] if no usable start-batterpitcher plays found.  Never fabricated.

    frac_elapsed is computed from the half-inning the at-bat sits in (matching the
    half-inning grid's denominator) so the at-bat grid and half-inning grid share the
    SAME time axis and BASE slope semantics.
    """
    plays = payload.get("plays")
    if not isinstance(plays, list) or not plays:
        return []
    # Establish the half-inning span for the frac_elapsed denominator (same rule as the
    # half-inning ingest: max(18, total half-innings seen)).
    max_half_idx = 0
    for p in plays:
        per = p.get("period", {})
        pnum = per.get("number")
        ptype = per.get("type", "")
        if pnum is None:
            continue
        # Top/Mid -> first half (2N-1); Bottom/End -> second half (2N)
        if ptype in ("Top", "Mid"):
            hi = 2 * int(pnum) - 1
        elif ptype in ("Bottom", "End"):
            hi = 2 * int(pnum)
        else:
            continue
        max_half_idx = max(max_half_idx, hi)
    denom = float(max(_STD_HALF_INNINGS, max_half_idx))

    rows: List[dict] = []
    for p in plays:
        if p.get("type", {}).get("type") != _START_TYPE:
            continue
        per = p.get("period", {})
        pnum = per.get("number")
        ptype = per.get("type", "")
        hs = p.get("homeScore")
        as_ = p.get("awayScore")
        outs = p.get("outs")
        if pnum is None or hs is None or as_ is None or outs is None:
            continue
        pnum = int(pnum)
        if ptype in ("Top", "Mid"):
            half_idx = 2 * pnum - 1
            label = f"top{pnum}"
        elif ptype in ("Bottom", "End"):
            half_idx = 2 * pnum
            label = f"bottom{pnum}"
        else:
            continue
        outs = int(outs)
        if outs < 0 or outs > 2:   # start-of-AB outs must be 0,1,2 (3 => inning over)
            continue
        runners = _runners_bitmask(p)
        state_diff = float(hs) - float(as_)
        rows.append({
            "half_idx": half_idx,
            "state_diff": state_diff,
            "frac_elapsed": half_idx / denom,
            "half_inning_label": label,
            "inning": pnum,
            "runners": runners,
            "outs": outs,
            # start-of-AB count is always 0-0 (new batter) -- present, zero-network, but
            # CONSTANT at this grid; varying count is the deferred pitch tier.
            "count_balls": 0,
            "count_strikes": 0,
            "base_run_value": base_run_value(runners, outs),
            "leverage_bucket": leverage_bucket(pnum, state_diff, runners, outs),
        })
    if not rows:
        return []
    out: List[dict] = []
    for i, r in enumerate(rows):
        row = dict(r)
        row["asof_idx"] = i
        out.append(row)
    return out


def fetch_game_atbat_states(espn_eid: str, game_meta: dict,
                            http_get: Callable) -> List[dict]:
    """Fetch one game's PBP and return per-at-bat state rows, [] on failure/empty."""
    payload = http_get(_SUMMARY.format(eid=espn_eid))
    if not payload:
        return []
    states = parse_atbat_states(payload)
    if not states:
        return []
    hf, af = _final_score(payload)
    if hf is None or af is None or hf == af:   # ties (rain-shortened) -> drop
        return []
    outcome = int(hf > af)
    out: List[dict] = []
    for s in states:
        out.append({
            "sport": "mlb",
            "game_id": game_meta["game_id"],
            "asof_idx": s["asof_idx"],
            "state_diff": s["state_diff"],
            "frac_elapsed": s["frac_elapsed"],
            "p0": game_meta["p0"],
            "outcome": outcome,
            "home_team": game_meta["home_team"],
            "away_team": game_meta["away_team"],
            "date": game_meta["date"],
            "season": game_meta["season"],
            "half_inning_label": s["half_inning_label"],
            # additive at-bat detail layer (leak-free as-of)
            "count_balls": s["count_balls"],
            "count_strikes": s["count_strikes"],
            "runners": s["runners"],
            "outs": s["outs"],
            "base_run_value": s["base_run_value"],
            "leverage_bucket": s["leverage_bucket"],
        })
    return out


def ingest_season(season: int, sample_k: int = 1,
                  http_get: Optional[Callable] = None,
                  out_dir: Optional[Path] = None) -> Path:
    """Ingest per-at-bat states for one MLB season; write mlb_atbat_states__<season>.parquet.

    sample_k=k takes every k-th game (deterministic, chronological). sample_k=1=full.
    Drops games with missing/broken PBP. Reports coverage honestly.
    """
    from domains.mlb.ratings import walk_forward_elo
    getter = http_get or _default_http_get
    out_dir = Path(out_dir or _OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"mlb_atbat_states__{season}.parquet"

    all_games = _load_all_games()
    wf = walk_forward_elo(all_games)
    season_df = wf[wf["season"] == season].copy()
    if season_df.empty:
        log.warning("No games found for season=%d", season)
        return out
    if sample_k > 1:
        season_df = season_df.iloc[::sample_k].reset_index(drop=True)
    log.info("season=%d attempting=%d games (sample_k=%d)", season, len(season_df), sample_k)

    scoreboard_cache: Dict[str, Dict[Tuple[str, str], str]] = {}
    rows: List[dict] = []
    ok = dropped = 0
    for _, row in season_df.iterrows():
        date_str = str(pd.to_datetime(row["date"]).strftime("%Y%m%d"))
        if date_str not in scoreboard_cache:
            scoreboard_cache[date_str] = _scoreboard_map(date_str, getter)
        sb = scoreboard_cache[date_str]
        espn_eid = sb.get((_gc2espn(str(row["home_team"])), _gc2espn(str(row["away_team"]))))
        if espn_eid is None:
            dropped += 1
            continue
        meta = {
            "game_id": str(row["event_id"]),
            "p0": float(row["p_home_elo"]),
            "home_team": str(row["home_team"]),
            "away_team": str(row["away_team"]),
            "date": str(row["date"].date()),
            "season": int(row["season"]),
        }
        states = fetch_game_atbat_states(espn_eid, meta, getter)
        if states:
            rows.extend(states)
            ok += 1
        else:
            dropped += 1

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        df.to_parquet(out, index=False)
    spg = (len(df) / ok) if ok else 0.0
    brate = df["outcome"].mean() if not df.empty else float("nan")
    log.info("season=%d ok=%d dropped=%d states=%d ticks/game=%.1f base_rate=%.3f -> %s",
             season, ok, dropped, len(df), spg, brate, out)
    return out


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ingest MLB per-at-bat in-game states.")
    ap.add_argument("--season", type=int, required=True, help="Season year (e.g. 2023)")
    ap.add_argument("--sample-k", type=int, default=1, help="Keep every k-th game (1=full)")
    args = ap.parse_args(argv)
    out = ingest_season(args.season, sample_k=args.sample_k)
    if out.exists():
        df = pd.read_parquet(out)
        ng = df["game_id"].nunique()
        print(f"season={args.season} games={ng} states={len(df)} "
              f"ticks/game={len(df)/max(1,ng):.1f} "
              f"p0_range=[{df['p0'].min():.3f},{df['p0'].max():.3f}] "
              f"base_rate={df['outcome'].mean():.3f} "
              f"re24_range=[{df['base_run_value'].min():.3f},{df['base_run_value'].max():.3f}]"
              f" -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
