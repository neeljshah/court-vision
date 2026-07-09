"""domains.basketball_nba.composition.player_offense_events -- per-(game,
player) WIDE offense event table: shot-zone breakout (5 geometry zones,
classify_zone/zone_geometry.py), transition vs halfcourt vs late-shot-clock
splits (transition_flag.py/shot_clock_proxy.py's SAME possession-segment
chain, resolved ONCE per game here rather than walking the corpus twice
more), and clutch (Q4/OT, <=5min, <=10pt) FGA/FGM/FG3M/FTA -- one row per
(game_id, player_id), one FILE PER SEASON so downstream last_n_games
window_spec slicing (scripts/platformkit/intel_validation/aggregate_
recompute.py) can never cross a season boundary.

WHY A WIDE PER-GAME TABLE (not a long per-shot one): the claims validator's
aggregate grammar (safe_formula.py) only whitelists sum/mean/count/
count_distinct of a BARE column -- no row filtering (no "zone=='rim'"). By
pre-splitting each bucket (zone, transition/halfcourt, late-clock, clutch)
into its OWN numeric column here, a claim formula is just sum(rim_fga)/
sum(total_fga) -- an independently recomputable ratio, same discipline as
shot_diet.py's zone columns.

ASSISTED: concession_profiles._is_assisted (assistPersonId OR "assist" in
description text -- covers both CDN-native and ESPN-derived shapes).

SHARED DENOMINATOR SIMPLIFICATION: attempt_share for transition/halfcourt/
late_clock uses total_fga (ALL zone attempts) as the denominator, not a
narrower "valid-chain-only" count -- the possession chain is unresolved for
only a handful of actions per period (the first action(s) after a period
boundary, before any anchor event fixes team possession -- see shot_clock_
proxy.py's own docstring), so this is a documented, harmless undercount of
share, not a bug.

CLUTCH FT-RATE uses FTA/FGA (not FTA/36) -- true clutch on-court MINUTES (a
per-36 denominator) needs joint roster+running-score tracking this table
doesn't carry; profiles/player_offense_zones.py substitutes clutch_fga_per_
game instead (see that module's docstring).

OUTPUT: data/cache/team_system/composition/player_offense_events_<season>.parquet
NETWORK: zero. CLI: python -m domains.basketball_nba.composition.player_offense_events --season 2025_26
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from domains.basketball_nba.composition.concession_profiles import _is_assisted
from domains.basketball_nba.composition.shot_clock_proxy import (
    SHOT_CLOCK_S, _detect_mode, resolve_segments,
)
from domains.basketball_nba.composition.transition_flag import TRANSITION_WINDOW_S
from domains.basketball_nba.composition.zone_geometry import ZONES, classify_zone
from domains.basketball_nba.lineups.on_off import _attach_player_names
from domains.basketball_nba.lineups.pbp_lineups import _BOX_SRC, _CLOCK_RE, _PBP_DIR

REPO_ROOT = Path(__file__).resolve().parents[3]
_OUT_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "composition"
_GAMES_SRC = REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"

PBP_BY_SEASON = {
    "2023_24": REPO_ROOT / "data" / "cache" / "team_system" / "pbp_2023_24",
    "2024_25": REPO_ROOT / "data" / "cache" / "team_system" / "pbp_2024_25",
    "2025_26": _PBP_DIR,
}

CLUTCH_PERIOD_MIN = 4
CLUTCH_REMAIN_S = 300.0
CLUTCH_MARGIN_PTS = 10.0


def _remaining_s(period: int, clock: Optional[str]) -> Optional[float]:
    m = _CLOCK_RE.match(clock or "")
    return float(m.group(1)) * 60.0 + float(m.group(2)) if m else None


def is_clutch_row(period: int, remaining_s: Optional[float], margin: Optional[float]) -> bool:
    """Q4+OT, <=5min remaining, <=10pt margin -- pure function, unit-tested
    on edge cases in test_player_offense_events.py (no disk I/O needed)."""
    return (
        remaining_s is not None and margin is not None
        and period >= CLUTCH_PERIOD_MIN and remaining_s <= CLUTCH_REMAIN_S and margin <= CLUTCH_MARGIN_PTS
    )


def load_game_events(game_json: dict[str, Any]) -> pd.DataFrame:
    """One row per shot/freethrow ATTEMPT for one game -- zone/assisted/
    transition/late-clock/clutch already resolved, long format (pivoted to
    the wide per-(game,player) table by build_player_offense_table)."""
    game_id = str(game_json["game"]["gameId"])
    actions = game_json["game"]["actions"]
    mode = _detect_mode(actions)
    resolved = {r["action_number"]: r for r in resolve_segments(actions, mode=mode)}
    rows: list[dict[str, Any]] = []
    for a in actions:
        at, tid, pid = a.get("actionType"), a.get("teamId"), a.get("personId")
        if not tid or not pid or a.get("period") is None:
            continue
        period = a["period"]
        remaining = _remaining_s(period, a.get("clock"))
        sh, sa = a.get("scoreHome"), a.get("scoreAway")
        margin = abs(int(sh) - int(sa)) if sh is not None and sa is not None else None
        is_clutch = int(is_clutch_row(period, remaining, margin))

        if at == "freethrow":
            rows.append({
                "game_id": game_id, "player_id": pid, "team_id": tid, "kind": "ft",
                "zone": None, "is_3": 0, "made": int(a.get("shotResult") == "Made"),
                "assisted": 0, "is_transition": None, "is_late_clock": None, "is_clutch": is_clutch,
            })
            continue
        if at not in ("2pt", "3pt") or a.get("x") is None:
            continue
        is_3 = int(at == "3pt")
        made = a.get("shotResult") == "Made"
        r = resolved.get(a["actionNumber"])
        since_start = r["elapsed_s"] - r["seg_start_s"] if r and r["seg_team"] is not None else None
        is_transition = int(0.0 <= since_start <= TRANSITION_WINDOW_S) if since_start is not None else None
        is_late = None
        if since_start is not None:
            proxy = min(max(SHOT_CLOCK_S - since_start, 0.0), SHOT_CLOCK_S)
            is_late = int(proxy <= 7.0)
        rows.append({
            "game_id": game_id, "player_id": pid, "team_id": tid, "kind": "fg",
            "zone": classify_zone(float(a["x"]), float(a["y"]), bool(is_3)), "is_3": is_3,
            "made": int(made), "assisted": int(_is_assisted(a, made)),
            "is_transition": is_transition, "is_late_clock": is_late, "is_clutch": is_clutch,
        })
    return pd.DataFrame(rows)


def _pivot_zone(fg: pd.DataFrame) -> pd.DataFrame:
    g = fg.groupby(["game_id", "player_id", "zone"]).agg(
        fga=("made", "size"), fgm=("made", "sum"), assisted=("assisted", "sum"),
    ).reset_index()
    parts = []
    for metric, suffix in [("fga", "_fga"), ("fgm", "_fgm"), ("assisted", "_assisted")]:
        p = g.pivot(index=["game_id", "player_id"], columns="zone", values=metric)
        p.columns = [f"{z}{suffix}" for z in p.columns]
        parts.append(p)
    out = pd.concat(parts, axis=1).fillna(0.0)
    for z in ZONES:
        for suffix in ("_fga", "_fgm", "_assisted"):
            if f"{z}{suffix}" not in out.columns:
                out[f"{z}{suffix}"] = 0.0
    return out.reset_index()


def _bucket_agg(fg: pd.DataFrame, mask: pd.Series, prefix: str) -> pd.DataFrame:
    sub = fg[mask]
    if sub.empty:
        return pd.DataFrame(columns=["game_id", "player_id", f"{prefix}_fga", f"{prefix}_fgm", f"{prefix}_fg3m"])
    return sub.groupby(["game_id", "player_id"]).agg(**{
        f"{prefix}_fga": ("made", "size"), f"{prefix}_fgm": ("made", "sum"), f"{prefix}_fg3m": ("fg3m_flag", "sum"),
    }).reset_index()


def _game_dates() -> Optional[pd.DataFrame]:
    if not _GAMES_SRC.exists():
        return None
    g = pd.read_parquet(_GAMES_SRC, columns=["game_id", "date"]).copy()
    g["game_id"] = g["game_id"].astype(str)
    return g


def build_player_offense_table(season: str, limit: Optional[int] = None) -> pd.DataFrame:
    pbp_dir = PBP_BY_SEASON.get(season)
    if pbp_dir is None or not pbp_dir.exists():
        return pd.DataFrame()
    files = sorted(pbp_dir.glob("*.json"))
    if limit:
        files = files[:limit]
    frames = [load_game_events(json.loads(fp.read_text(encoding="utf-8"))) for fp in files]
    events = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if events.empty:
        return pd.DataFrame()
    events["player_id"] = events["player_id"].astype("int64")
    events["team_id"] = events["team_id"].astype("int64")
    events = events[events["player_id"] >= 0]

    fg = events[events["kind"] == "fg"].copy()
    fg["fg3m_flag"] = fg["made"] * fg["is_3"]
    ft = events[events["kind"] == "ft"]

    totals = fg.groupby(["game_id", "player_id"]).agg(
        total_fga=("made", "size"), total_fgm=("made", "sum"), team_id=("team_id", "first"),
    ).reset_index()
    parts = [
        _pivot_zone(fg),
        _bucket_agg(fg, fg["is_transition"] == 1, "transition"),
        _bucket_agg(fg, fg["is_transition"] == 0, "halfcourt"),
        _bucket_agg(fg, fg["is_late_clock"] == 1, "late_clock"),
        _bucket_agg(fg, fg["is_clutch"] == 1, "clutch"),
        (ft[ft["is_clutch"] == 1].groupby(["game_id", "player_id"]).agg(clutch_fta=("made", "size")).reset_index()
         if not ft.empty else pd.DataFrame(columns=["game_id", "player_id", "clutch_fta"])),
    ]
    out = totals
    for part in parts:
        out = out.merge(part, on=["game_id", "player_id"], how="left")
    num_cols = [c for c in out.columns if c not in ("game_id", "player_id", "team_id")]
    out[num_cols] = out[num_cols].fillna(0.0)

    dates = _game_dates()
    out = out.merge(dates, on="game_id", how="left") if dates is not None else out.assign(date=pd.NaT)
    out = _attach_player_names(out, pd.read_parquet(_BOX_SRC))
    return out.sort_values(["date", "game_id", "player_id"]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NBA per-game player offense event table")
    parser.add_argument("--season", type=str, default="2025_26", choices=list(PBP_BY_SEASON))
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    table = build_player_offense_table(args.season, limit=args.limit)
    out_path = Path(args.out) if args.out else _OUT_DIR / f"player_offense_events_{args.season}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_path, index=False)
    n_players = table["player_id"].nunique() if not table.empty else 0
    print(f"season={args.season} rows={len(table)} players={n_players} -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
