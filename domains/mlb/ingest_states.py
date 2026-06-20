"""domains.mlb.ingest_states -- MLB in-game trajectory ingest (half-inning states).

Mirrors domains/basketball_nba/ingest_pbp_states.py for MLB.  Produces per-game
as-of states at every half-inning boundary from ESPN free PBP, leak-free p0 from
walk-forward Elo, and the realized outcome.  Output schema (frozen):

  parquet row = {
    sport         : "mlb"           (str)
    game_id       : str             (games_current event_id)
    asof_idx      : int             (0-based half-inning index within game)
    state_diff    : float           (home_runs - away_runs at that boundary, signed +HOME)
    frac_elapsed  : float [0,1]     (completed half-innings / max(18, total_half_innings))
    p0            : float [0,1]     (leak-free pregame P(home win) from Elo)
    outcome       : int             (1 if home team won, 0 if away won)
  }
  Extra cols: home_team, away_team, date, season, half_inning_label

  BASE-OUT extension (extra cols -- additive, frozen schema unchanged):
    runners       : int [0,7]   (bitmask: bit2=1B, bit1=2B, bit0=3B; 0=unknown)
    outs          : int [0,3]   (outs at end of half-inning; -1=unknown)
    base_out_known: bool        (True if ESPN PBP provided runners+outs)

  base_out semantics: runners/outs are taken from the LAST end-batterpitcher or
  fly-out/ground-out/etc. play just before each end-inning event.  This captures
  the 'left on base' state when the half-inning ended (runners stranded, outs=3).
  UNKNOWN (-1 / 0 / False) when ESPN PBP lacks per-at-bat detail.

LEAK-FREENESS: frac_elapsed/state_diff only use plays up to that half-inning boundary
(strictly past).  p0 uses only games strictly before this game's date.
HONEST: games with missing/broken PBP are DROPPED.  Never fabricated.
ASCII only.  <=300 LOC.  No src/kernel/api imports.
CLI: python -m domains.mlb.ingest_states --season 2023 --sample-k 6
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_GAMES_HIST = _REPO / "data" / "domains" / "mlb" / "games.parquet"
_GAMES_CURR = _REPO / "data" / "domains" / "mlb" / "games_current.parquet"
_OUT_DIR = _REPO / "data" / "cache" / "ingame"
_SCOREBOARD = ("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb"
               "/scoreboard?dates={date}")
_SUMMARY = ("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb"
            "/summary?event={eid}")
_STD_HALF_INNINGS = 18   # 9 innings x 2 half-innings

# games_current team dialect -> ESPN abbreviation
_GC_TO_ESPN: Dict[str, str] = {
    "CUB": "CHC", "CWS": "CHW", "KAN": "KC",
    "SDG": "SD",  "SFO": "SF",  "TAM": "TB",  "WAS": "WSH",
}


def _gc2espn(code: str) -> str:
    return _GC_TO_ESPN.get(str(code).upper(), str(code).upper())


def _default_http_get(url: str) -> dict:
    import json, urllib.request
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=14) as r:
            return json.loads(r.read())
    except Exception as exc:  # noqa: BLE001
        log.debug("fetch failed url=%s err=%s", url, exc)
        return {}


# ---------------------------------------------------------------------------
# Scoreboard -> {(home_espn, away_espn): espn_event_id} per date
# ---------------------------------------------------------------------------

def _scoreboard_map(datestr: str, http_get: Callable) -> Dict[Tuple[str, str], str]:
    """Fetch ESPN scoreboard for YYYYMMDD and return (home_abbr, away_abbr)->event_id."""
    payload = http_get(_SCOREBOARD.format(date=datestr))
    out: Dict[Tuple[str, str], str] = {}
    for evt in payload.get("events", []):
        eid = str(evt.get("id", ""))
        comps = evt.get("competitions", [{}])[0].get("competitors", [])
        home = next((c for c in comps if c.get("homeAway") == "home"), None)
        away = next((c for c in comps if c.get("homeAway") == "away"), None)
        if home and away and eid:
            habbr = home["team"]["abbreviation"].upper()
            aabbr = away["team"]["abbreviation"].upper()
            out[(habbr, aabbr)] = eid
    return out


# ---------------------------------------------------------------------------
# PBP -> half-inning boundary states
# ---------------------------------------------------------------------------

def _extract_half_inning_baseout(plays: List[dict], end_idx: int) -> Tuple[int, int, bool]:
    """Extract runners+outs from the last informative play before plays[end_idx].

    Scans backward from end_idx-1 looking for a play that has 'outs' field and
    belongs to the same inning number.  Returns (runners_bitmask, outs, known)
    where runners is bit2=1B bit1=2B bit0=3B.  Returns (0, -1, False) if no
    usable play found (ESPN PBP gap / extra innings).

    Period-type mapping: the end-inning play uses "Mid"/"End" while the at-bat
    plays within it use "Top"/"Bottom".  We guard only on inning NUMBER to stay
    within the same half-inning when scanning backward.

    This captures 'left on base' state: runners stranded when 3rd out was made.
    outs=3 always at end of a completed inning; runners=non-zero means LOB.
    LEAK-FREE: only looks backward within the just-completed half-inning.
    """
    end_play = plays[end_idx]
    ep_num = end_play.get("period", {}).get("number")
    if ep_num is None:
        return 0, -1, False
    # Determine expected inning-half type: "Mid" maps to "Top", "End" maps to "Bottom"
    ep_type = end_play.get("period", {}).get("type", "")
    inner_type = "Top" if ep_type == "Mid" else ("Bottom" if ep_type == "End" else None)
    for j in range(end_idx - 1, max(-1, end_idx - 80), -1):
        p = plays[j]
        pt = p.get("period", {})
        pnum = pt.get("number")
        ptype = pt.get("type", "")
        # Stop if we've crossed into a different inning number
        if pnum != ep_num:
            break
        # Skip plays from the wrong half of the inning if inner_type is known
        if inner_type and ptype not in (inner_type, ep_type, ""):
            continue
        if "outs" not in p:
            continue
        on1 = 1 if p.get("onFirst") else 0
        on2 = 1 if p.get("onSecond") else 0
        on3 = 1 if p.get("onThird") else 0
        runners = (on1 << 2) | (on2 << 1) | on3
        outs = int(p.get("outs", -1))
        return runners, outs, True
    return 0, -1, False


def parse_half_inning_states(payload: dict) -> List[dict]:
    """ESPN summary payload -> [{asof_idx, state_diff, half_inning_label, ...}], sorted.

    Only `end-inning` plays are used (one per half-inning boundary).
    Mid = after top half (away bats), End = after bottom half (home bats).
    frac_elapsed is computed dynamically after all boundaries are collected.
    Returns [] if no usable end-inning plays found.  Never fabricated.

    EXTRA cols added (additive -- frozen schema unchanged):
      runners (int bitmask), outs (int, -1=unknown), base_out_known (bool).
    """
    plays = payload.get("plays")
    if not isinstance(plays, list) or not plays:
        return []
    # Build index of end-inning play positions for base-out extraction
    end_play_indices = [
        i for i, p in enumerate(plays)
        if p.get("type", {}).get("type") == "end-inning"
    ]
    end_plays = [plays[i] for i in end_play_indices]
    if not end_plays:
        return []
    rows: List[dict] = []
    for k, (idx, p) in enumerate(zip(end_play_indices, end_plays)):
        ptype = p.get("period", {}).get("type", "")
        pnum = p.get("period", {}).get("number")
        hs = p.get("homeScore")
        as_ = p.get("awayScore")
        if pnum is None or hs is None or as_ is None:
            continue
        pnum = int(pnum)
        hs = float(hs)
        as_ = float(as_)
        # half-inning index: Mid N -> 2*N-1 (1-based), End N -> 2*N
        if ptype == "Mid":
            half_idx = 2 * pnum - 1
        elif ptype == "End":
            half_idx = 2 * pnum
        else:
            continue
        label = f"{ptype.lower()}{pnum}"
        runners, outs, known = _extract_half_inning_baseout(plays, idx)
        rows.append({"half_idx": half_idx, "state_diff": hs - as_,
                     "half_inning_label": label,
                     "runners": runners, "outs": outs, "base_out_known": known})
    if not rows:
        return []
    # Sort by half_idx
    rows.sort(key=lambda r: r["half_idx"])
    # Deduplicate: keep last entry per half_idx (should not happen but defensive)
    seen: Dict[int, dict] = {}
    for r in rows:
        seen[r["half_idx"]] = r
    rows = [seen[k] for k in sorted(seen)]
    total_hi = max(r["half_idx"] for r in rows)
    denom = float(max(_STD_HALF_INNINGS, total_hi))
    out: List[dict] = []
    for i, r in enumerate(rows):
        out.append({
            "asof_idx": i,
            "state_diff": r["state_diff"],
            "frac_elapsed": r["half_idx"] / denom,
            "half_inning_label": r["half_inning_label"],
            "runners": r["runners"],
            "outs": r["outs"],
            "base_out_known": r["base_out_known"],
        })
    return out


def _final_score(payload: dict) -> Tuple[Optional[float], Optional[float]]:
    """(home_score, away_score) from the last play with both scores."""
    plays = payload.get("plays") or []
    for p in reversed(plays):
        hs, as_ = p.get("homeScore"), p.get("awayScore")
        if hs is not None and as_ is not None:
            return float(hs), float(as_)
    return None, None


# ---------------------------------------------------------------------------
# Per-game ingest
# ---------------------------------------------------------------------------

def fetch_game_states(espn_eid: str, game_meta: dict,
                      http_get: Callable) -> List[dict]:
    """Fetch one game's PBP and return list of state rows, [] on failure/empty."""
    payload = http_get(_SUMMARY.format(eid=espn_eid))
    if not payload:
        return []
    states = parse_half_inning_states(payload)
    if not states:
        return []
    hf, af = _final_score(payload)
    if hf is None or af is None or hf == af:   # ties (rare rain-shortened) -> drop
        return []
    outcome = int(hf > af)
    out = []
    for s in states:
        row = {
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
            # Base-out extension (additive; frozen cols above unchanged)
            "runners": s.get("runners", 0),
            "outs": s.get("outs", -1),
            "base_out_known": bool(s.get("base_out_known", False)),
        }
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Season ingest
# ---------------------------------------------------------------------------

def _load_all_games() -> pd.DataFrame:
    """Concatenate games.parquet (2010-2021) and games_current.parquet (2022+)."""
    parts = []
    if _GAMES_HIST.exists():
        parts.append(pd.read_parquet(_GAMES_HIST))
    if _GAMES_CURR.exists():
        parts.append(pd.read_parquet(_GAMES_CURR))
    if not parts:
        raise FileNotFoundError("Neither games.parquet nor games_current.parquet found.")
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["date", "home_team", "away_team", "game_seq"],
                          kind="mergesort").reset_index(drop=True)


def ingest_season(season: int, sample_k: int = 1,
                  http_get: Optional[Callable] = None,
                  out_dir: Optional[Path] = None) -> Path:
    """Ingest half-inning states for one MLB season; write mlb_states__<season>.parquet.

    sample_k=k takes every k-th game (deterministic, chronological).  sample_k=1=full.
    Drops games with missing/broken PBP.  Reports coverage honestly.
    """
    from domains.mlb.ratings import walk_forward_elo
    getter = http_get or _default_http_get
    out_dir = Path(out_dir or _OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"mlb_states__{season}.parquet"

    all_games = _load_all_games()
    wf = walk_forward_elo(all_games)  # leak-free p0 for every row

    season_df = wf[wf["season"] == season].copy()
    if season_df.empty:
        log.warning("No games found for season=%d", season)
        return out

    # Deterministic sample
    if sample_k > 1:
        season_df = season_df.iloc[::sample_k].reset_index(drop=True)
    log.info("season=%d attempting=%d games (sample_k=%d)", season, len(season_df), sample_k)

    # Build scoreboard cache per unique date to minimize ESPN calls
    scoreboard_cache: Dict[str, Dict[Tuple[str, str], str]] = {}

    rows: List[dict] = []
    ok = dropped = 0
    for _, row in season_df.iterrows():
        date_str = str(pd.to_datetime(row["date"]).strftime("%Y%m%d"))
        if date_str not in scoreboard_cache:
            scoreboard_cache[date_str] = _scoreboard_map(date_str, getter)
        sb = scoreboard_cache[date_str]
        home_espn = _gc2espn(str(row["home_team"]))
        away_espn = _gc2espn(str(row["away_team"]))
        espn_eid = sb.get((home_espn, away_espn))
        if espn_eid is None:
            log.debug("no ESPN match for %s vs %s on %s", row["home_team"], row["away_team"], date_str)
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
        states = fetch_game_states(espn_eid, meta, getter)
        if states:
            rows.extend(states)
            ok += 1
        else:
            dropped += 1
            log.debug("dropped eid=%s (empty/broken PBP)", espn_eid)

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        df.to_parquet(out, index=False)
    spg = (len(df) / ok) if ok else 0.0
    brate = df["outcome"].mean() if not df.empty else float("nan")
    bo_known = int(df["base_out_known"].sum()) if not df.empty else 0
    bo_pct = (bo_known / len(df) * 100.0) if not df.empty else 0.0
    log.info("season=%d ok=%d dropped=%d states=%d spg=%.1f base_rate=%.3f "
             "base_out_known=%d (%.1f%%) -> %s",
             season, ok, dropped, len(df), spg, brate, bo_known, bo_pct, out)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ingest MLB half-inning in-game states.")
    ap.add_argument("--season", type=int, required=True,
                    help="Season year (e.g. 2023 or 2024)")
    ap.add_argument("--sample-k", type=int, default=1,
                    help="Keep every k-th game (1=full season)")
    args = ap.parse_args(argv)
    out = ingest_season(args.season, sample_k=args.sample_k)
    if out.exists():
        df = pd.read_parquet(out)
        bo = df["base_out_known"].sum() if "base_out_known" in df.columns else 0
        bo_pct = bo / len(df) * 100.0 if len(df) > 0 else 0.0
        print(f"season={args.season} games={df['game_id'].nunique()} "
              f"states={len(df)} spg={len(df)/max(1,df['game_id'].nunique()):.1f} "
              f"p0_range=[{df['p0'].min():.3f},{df['p0'].max():.3f}] "
              f"base_rate={df['outcome'].mean():.3f} "
              f"base_out_known={int(bo)}/{len(df)} ({bo_pct:.1f}%) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
