"""domains.mlb.ingest_pitch_states -- MLB in-game trajectory ingest (PER-PITCH states).

INCREMENT 3 of the MOAT plan. The FINEST grid below the per-at-bat layer
(domains/mlb/ingest_atbat_states.py): where that emits one tick per at-bat, this emits
one tick PER PITCH (~250-300 pitch ticks/game) from the SAME already-fetched keyless
ESPN summary plays[] payload (ZERO incremental network -- the bytes ride the identical
fetch loop ingest_atbat_states already runs; they are simply dropped at ingest today).

PAYLOAD PROBE (VERIFIED against a live ESPN MLB summary, 2024-07-01, 494 plays -- see
.planning/product/deepdata/mlb.md Tier-1): individual PITCH plays carry, in addition to
the at-bat-start fields (period, homeScore/awayScore, outs, onFirst/onSecond/onThird):
  pitchCount {balls, strikes}  -- the count BEFORE this pitch resolves (strictly pre-pitch)
  resultCount {balls, strikes} -- the count AFTER (OUTCOME of the pitch -> NEVER a feature)
  pitchType {abbreviation, ...}-- e.g. "FF" (the pitcher's CHOICE, known when thrown)
  pitchVelocity (int mph)      -- e.g. 95 (known when thrown, before result)
  pitchCoordinate {x, y}       -- release/plate location (known when thrown)
  atBatPitchNumber (int)       -- 1-based depth into the at-bat
Probe field-fill: pitchType 244/494, pitchVelocity 244/494, pitchCoordinate 380/494.
A pitch play is identified as one carrying pitchCount AND atBatPitchNumber (NOT the
start-batterpitcher / end-* sentinels). The count on a PITCH play VARIES (1-0, 1-1, 3-2)
-- this is the genuinely-varying count that the at-bat grid CONSTANT-0'd and explicitly
deferred (see ingest_atbat_states.py:17-22).

THE STRUCTURALLY-NEW LEVER this layer exists to MEASURE = WITHIN-START SP velocity
decline / fatigue: a per-pitch flag the half-inning AND at-bat grids cannot see. We
carry the raw pitch_velocity and a leak-free as-of fatigue summary computed ONLY from
PRIOR pitches in the same game on the same pitching side:
  sp_pitch_count_prior  : int   -- # pitches thrown by the fielding side BEFORE this pitch
  velo_decline_vs_early : float -- (mean of FIRST-N velos seen so far) - (this velo),
                                   positive => slower than early => fatigue signal.
                                   Uses ONLY pitches at index < current (prior-N), shift1.

FROZEN base schema (IDENTICAL to ingest_states.py:8-15 so it gates the same way):
  {sport, game_id, asof_idx, state_diff (home-away as-of), frac_elapsed in [0,1],
   p0 (leak-free pregame P(home win)), outcome in {0,1}}
  Extra meta cols: home_team, away_team, date, season, half_inning_label.

ADDITIVE leak-free as-of per-pitch detail cols (the Increment-3 layer):
  count_balls, count_strikes : int  -- pitchCount (STRICTLY pre-pitch; the genuinely
                                       VARYING count the at-bat grid could not express)
  runners                    : int [0,7] bitmask bit2=1B bit1=2B bit0=3B, as-of pre-pitch
  outs                       : int [0,2] outs facing the batter, as-of pre-pitch
  atbat_pitch_number         : int  -- depth into the at-bat (1-based)
  pitch_type                 : str  -- abbreviation ("" if absent on the play)
  pitch_velocity             : float-- mph (NaN if absent)
  pitch_loc_x, pitch_loc_y   : float-- coordinate (NaN if absent)
  sp_pitch_count_prior       : int  -- as-of prior-pitch count for the fielding side
  velo_decline_vs_early      : float-- as-of fatigue lever (prior-N only; NaN until enough)
  base_run_value             : float-- STATIC RE24 lookup (runners,outs) -- pinned 1999-2002
  leverage_bucket            : str  -- STATIC rule over (inning, margin, base-out)

LEAK-FREENESS: every field at pitch k uses ONLY the pre-pitch payload of pitch k
(pitchCount NOT resultCount; score/runners/outs BEFORE the pitch). The fatigue summary
uses ONLY pitches strictly BEFORE k (prior-N / shift1). p0 uses games strictly before
the game date. NO *_final / total column is EVER merged onto a per-pitch row. Games
with missing/broken PBP are DROPPED. Never fabricated.
ASCII only.  <=300 LOC (this DATA spec module may run long).  No src/kernel/api imports.
CLI: python -m domains.mlb.ingest_pitch_states --season 2023 --sample-k 6 --limit 200
"""
from __future__ import annotations

import argparse
import logging
import math
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

# Reuse the half-inning module's verified ESPN plumbing (DRY, no re-derivation).
from domains.mlb.ingest_states import (
    _default_http_get,
    _final_score,
    _gc2espn,
    _load_all_games,
    _scoreboard_map,
    _SUMMARY,
    _STD_HALF_INNINGS,
)
from domains.mlb.re24_table import base_run_value, leverage_bucket

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_OUT_DIR = _REPO / "data" / "cache" / "ingame"

# Number of earliest pitches (per side) that establish the "fresh" velocity baseline.
_VELO_BASELINE_N = 5

# Sentinel / non-pitch play types we must NOT emit as pitch ticks.
_NON_PITCH_TYPES = {"start-batterpitcher", "end-batterpitcher", "end-inning", "end-period"}


def _runners_bitmask(play: dict) -> int:
    """bit2=1B bit1=2B bit0=3B from onFirst/onSecond/onThird (present iff occupied)."""
    on1 = 1 if play.get("onFirst") else 0
    on2 = 1 if play.get("onSecond") else 0
    on3 = 1 if play.get("onThird") else 0
    return (on1 << 2) | (on2 << 1) | on3


def _pre_pitch_count(play: dict) -> Optional[Tuple[int, int]]:
    """(balls, strikes) BEFORE this pitch resolves, from pitchCount (NOT resultCount).

    Returns None if the play lacks a usable pre-pitch count (-> not a pitch tick).
    """
    pc = play.get("pitchCount")
    if not isinstance(pc, dict):
        return None
    b = pc.get("balls")
    s = pc.get("strikes")
    if b is None or s is None:
        return None
    # Clamp to the valid STRICTLY pre-pitch maxima (3 balls / 2 strikes); a count
    # of 4 balls or 3 strikes ends the at-bat, so values above these are ESPN payload
    # edge cases (post-resolution / non-standard plays). Clamp (not drop) so the count
    # column stays clean if ever used as a feature in a future candidate.
    return min(max(int(b), 0), 3), min(max(int(s), 0), 2)


def _is_pitch_play(play: dict) -> bool:
    """A real pitch tick: carries a pre-pitch pitchCount AND atBatPitchNumber, and is
    not a start/end sentinel. This stays robust to ESPN's many pitch type.type labels
    (ball / strike-looking / strike-swinging / foul / in play ...) without enumerating
    them -- we key on the structural pitch fields, not the label whitelist."""
    if play.get("type", {}).get("type") in _NON_PITCH_TYPES:
        return False
    if play.get("atBatPitchNumber") is None:
        return False
    return _pre_pitch_count(play) is not None


def _pitch_side(play: dict) -> Optional[str]:
    """Which side is PITCHING at this play: 'home' pitches in the Top/Mid half (away
    bats), 'away' pitches in the Bottom/End half (home bats). None if unknown."""
    ptype = play.get("period", {}).get("type", "")
    if ptype in ("Top", "Mid"):
        return "home"
    if ptype in ("Bottom", "End"):
        return "away"
    return None


def _velocity(play: dict) -> float:
    v = play.get("pitchVelocity")
    try:
        return float(v) if v is not None else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def parse_pitch_states(payload: dict) -> List[dict]:
    """ESPN summary payload -> per-pitch as-of state rows, in game order.

    Tick = each individual pitch play, using STRICTLY pre-pitch state (pitchCount,
    score, runners, outs before the pitch resolves). The fatigue summary
    (sp_pitch_count_prior, velo_decline_vs_early) is built from a running per-side
    history of PRIOR pitches only (shift1 / prior-N) -- never the current or future pitch.
    Returns [] if no usable pitch plays found. Never fabricated.

    frac_elapsed reuses the half-inning denominator (same time axis + BASE slope
    semantics as the half-inning and at-bat grids).
    """
    plays = payload.get("plays")
    if not isinstance(plays, list) or not plays:
        return []
    # Half-inning span for the frac_elapsed denominator (same rule as the sibling grids).
    max_half_idx = 0
    for p in plays:
        per = p.get("period", {})
        pnum = per.get("number")
        ptype = per.get("type", "")
        if pnum is None:
            continue
        if ptype in ("Top", "Mid"):
            hi = 2 * int(pnum) - 1
        elif ptype in ("Bottom", "End"):
            hi = 2 * int(pnum)
        else:
            continue
        max_half_idx = max(max_half_idx, hi)
    denom = float(max(_STD_HALF_INNINGS, max_half_idx))

    # Per-side running history of PRIOR-pitch velocities (leak-free fatigue baseline).
    velos_seen: Dict[str, List[float]] = {"home": [], "away": []}
    count_seen: Dict[str, int] = {"home": 0, "away": 0}

    rows: List[dict] = []
    for p in plays:
        if not _is_pitch_play(p):
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
        if outs < 0 or outs > 2:   # pre-pitch outs must be 0,1,2 (3 => inning over)
            continue
        pre = _pre_pitch_count(p)
        if pre is None:
            continue
        balls, strikes = pre
        runners = _runners_bitmask(p)
        state_diff = float(hs) - float(as_)
        side = _pitch_side(p)
        velo = _velocity(p)

        # AS-OF fatigue summary: PRIOR pitches only (computed BEFORE updating history).
        if side is None:
            prior_n = 0
            velo_decline = float("nan")
        else:
            prior_n = count_seen[side]
            prior_velos = [v for v in velos_seen[side] if not math.isnan(v)]
            if prior_velos and not math.isnan(velo):
                baseline = prior_velos[:_VELO_BASELINE_N]
                early_mean = sum(baseline) / len(baseline)
                velo_decline = early_mean - velo   # positive => slower than early
            else:
                velo_decline = float("nan")

        atbat_pn = p.get("atBatPitchNumber")
        try:
            atbat_pn = int(atbat_pn)
        except (TypeError, ValueError):
            atbat_pn = -1
        ptype_abbr = ""
        pt = p.get("pitchType")
        if isinstance(pt, dict):
            ptype_abbr = str(pt.get("abbreviation", "") or "")
        loc = p.get("pitchCoordinate")
        if isinstance(loc, dict):
            lx = float(loc["x"]) if loc.get("x") is not None else float("nan")
            ly = float(loc["y"]) if loc.get("y") is not None else float("nan")
        else:
            lx = ly = float("nan")

        rows.append({
            "half_idx": half_idx,
            "state_diff": state_diff,
            "frac_elapsed": half_idx / denom,
            "half_inning_label": label,
            "inning": pnum,
            "runners": runners,
            "outs": outs,
            "count_balls": balls,         # VARYING pre-pitch count (the new lever)
            "count_strikes": strikes,
            "atbat_pitch_number": atbat_pn,
            "pitch_type": ptype_abbr,
            "pitch_velocity": velo,
            "pitch_loc_x": lx,
            "pitch_loc_y": ly,
            "sp_pitch_count_prior": prior_n,
            "velo_decline_vs_early": velo_decline,
            "base_run_value": base_run_value(runners, outs),
            "leverage_bucket": leverage_bucket(pnum, state_diff, runners, outs),
        })

        # Update per-side history AFTER emitting (so the row used only prior pitches).
        if side is not None:
            count_seen[side] += 1
            velos_seen[side].append(velo)

    if not rows:
        return []
    out: List[dict] = []
    for i, r in enumerate(rows):
        row = dict(r)
        row["asof_idx"] = i
        out.append(row)
    return out


def fetch_game_pitch_states(espn_eid: str, game_meta: dict,
                            http_get: Callable) -> List[dict]:
    """Fetch one game's PBP and return per-pitch state rows, [] on failure/empty."""
    payload = http_get(_SUMMARY.format(eid=espn_eid))
    if not payload:
        return []
    states = parse_pitch_states(payload)
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
            # additive per-pitch detail layer (leak-free as-of)
            "count_balls": s["count_balls"],
            "count_strikes": s["count_strikes"],
            "runners": s["runners"],
            "outs": s["outs"],
            "atbat_pitch_number": s["atbat_pitch_number"],
            "pitch_type": s["pitch_type"],
            "pitch_velocity": s["pitch_velocity"],
            "pitch_loc_x": s["pitch_loc_x"],
            "pitch_loc_y": s["pitch_loc_y"],
            "sp_pitch_count_prior": s["sp_pitch_count_prior"],
            "velo_decline_vs_early": s["velo_decline_vs_early"],
            "base_run_value": s["base_run_value"],
            "leverage_bucket": s["leverage_bucket"],
        })
    return out


def ingest_season(season: int, sample_k: int = 1,
                  http_get: Optional[Callable] = None,
                  out_dir: Optional[Path] = None,
                  limit: Optional[int] = None) -> Path:
    """Ingest per-pitch states for one MLB season; write mlb_pitch_states__<season>.parquet.

    sample_k=k takes every k-th game (deterministic, chronological). sample_k=1=full.
    limit=N caps the number of games ATTEMPTED (after sampling) so a materialization
    stays bounded + rate-polite on the keyless ESPN feed; None=no cap.
    Drops games with missing/broken PBP. Reports coverage honestly.
    """
    from domains.mlb.ratings import walk_forward_elo
    getter = http_get or _default_http_get
    out_dir = Path(out_dir or _OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"mlb_pitch_states__{season}.parquet"

    all_games = _load_all_games()
    wf = walk_forward_elo(all_games)   # leak-free p0 for every row
    season_df = wf[wf["season"] == season].copy()
    if season_df.empty:
        log.warning("No games found for season=%d", season)
        return out
    if sample_k > 1:
        season_df = season_df.iloc[::sample_k].reset_index(drop=True)
    if limit is not None and limit > 0:
        season_df = season_df.iloc[:limit].reset_index(drop=True)
    log.info("season=%d attempting=%d games (sample_k=%d limit=%s)",
             season, len(season_df), sample_k, limit)

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
        states = fetch_game_pitch_states(espn_eid, meta, getter)
        if states:
            rows.extend(states)
            ok += 1
        else:
            dropped += 1

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        df.to_parquet(out, index=False)
    ppg = (len(df) / ok) if ok else 0.0
    brate = df["outcome"].mean() if not df.empty else float("nan")
    velo_cov = (df["pitch_velocity"].notna().mean() if not df.empty else float("nan"))
    log.info("season=%d ok=%d dropped=%d pitches=%d pitches/game=%.1f base_rate=%.3f "
             "velo_coverage=%.3f -> %s",
             season, ok, dropped, len(df), ppg, brate, velo_cov, out)
    return out


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ingest MLB per-pitch in-game states.")
    ap.add_argument("--season", type=int, required=True, help="Season year (e.g. 2023)")
    ap.add_argument("--sample-k", type=int, default=1, help="Keep every k-th game (1=full)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap games ATTEMPTED after sampling (bounded/rate-polite; None=all)")
    args = ap.parse_args(argv)
    out = ingest_season(args.season, sample_k=args.sample_k, limit=args.limit)
    if out.exists():
        df = pd.read_parquet(out)
        ng = df["game_id"].nunique()
        print(f"season={args.season} games={ng} pitches={len(df)} "
              f"pitches/game={len(df)/max(1,ng):.1f} "
              f"p0_range=[{df['p0'].min():.3f},{df['p0'].max():.3f}] "
              f"base_rate={df['outcome'].mean():.3f} "
              f"velo_cov={df['pitch_velocity'].notna().mean():.3f} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
