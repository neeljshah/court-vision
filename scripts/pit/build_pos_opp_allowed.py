"""Point-in-time (PIT) opponent-stat-allowed BY POSITION builder.

H2: a center facing a team that surrenders many rebounds/points to opposing
CENTERS (not just overall) has inflated opportunity the box-score average misses.

For each game, for each defending team, we compute what that team ALLOWED to
each POSITION (G/F/C) of the OPPONENT's players. Then we build an expanding
shift(1) as-of mean per (team, position) -> opp_<stat>_allowed_to_<P>_asof.
Also compute a league-by-position baseline -> _vs_league signal.

Focus stats: reb, pts  (ast is less position-driven per H2 hypothesis).

Output: data/cache/pit/opp_pos_allowed_asof_<tag>.parquet
  keyed (team, position, game_date)
  columns: opp_<stat>_allowed_to_<P>_asof, opp_<stat>_allowed_to_<P>_vs_league,
           n_games_asof_<P>

Read-only except writing under data/cache/pit/.
NEVER edits build_opp_allowed_asof.py or any other existing file.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_opp_allowed_asof as ba  # reuse loaders — read-only import

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "data", "cache", "pit")
POS_FILE = os.path.join(ROOT, "data", "player_positions.parquet")

FOCUS_STATS = ["reb", "pts"]
POSITIONS = ["G", "F", "C"]


# ---------------------------------------------------------------- position map

def load_pos_map() -> Dict[int, str]:
    """Returns {player_id -> 'G'|'F'|'C'}. Compound positions use first token."""
    df = pd.read_parquet(POS_FILE)
    out: Dict[int, str] = {}
    _map = {
        "guard": "G",
        "forward": "F",
        "center": "C",
    }
    for r in df.itertuples(index=False):
        raw = (r.position or "").strip()
        if not raw:
            continue  # null position -> drop
        first = raw.split("-")[0].strip().lower()
        pos = _map.get(first)
        if pos is None:
            continue
        out[int(r.player_id)] = pos
    return out


# ---------------------------------------------------------------- per-game positional allowed

def pos_game_allowed(df: pd.DataFrame, pos_map: Dict[int, str]) -> pd.DataFrame:
    """Per (game_date, defending_team=team, position):
    sum of OPPONENT players' stat of that position = what 'team' ALLOWED to position P.

    Steps:
      1. Attach each player's position.
      2. Compute team-game totals per position group (the OPPONENT players' side).
      3. Align: for each (date, def_team), the 'allowed_to_P' = the OFF team's P-group total.
    """
    # attach position; drop players with no known position
    df = df.copy()
    df["pos"] = df["pid"].map(pos_map)
    df = df.dropna(subset=["pos"])

    # team-game-position totals (sum players of that position on that team that game)
    grp = df.groupby(["game_date", "team", "opp", "pos"], as_index=False)[FOCUS_STATS].sum(min_count=1)

    # lookup: (date, OFF_team, pos) -> stats
    lut: Dict[tuple, dict] = {}
    for r in grp.itertuples(index=False):
        key = (r.game_date, r.team, r.pos)
        lut[key] = {s: getattr(r, s) for s in FOCUS_STATS}

    # for each (date, DEF_team, pos): DEF_team allowed to that pos = OPP team's pos-group total
    out_rows: List[dict] = []
    for r in grp.itertuples(index=False):
        # r.team is the offensive team; r.opp is the defensive team (= def_team)
        # what r.opp ALLOWED to position r.pos ON this date = r's own stats
        row = {
            "game_date": r.game_date,
            "team": r.opp,      # defending team
            "opp": r.team,      # offensive team (for reference only)
            "position": r.pos,
        }
        for s in FOCUS_STATS:
            row[f"allowed_{s}"] = getattr(r, s)
        out_rows.append(row)

    res = pd.DataFrame(out_rows)
    res = res.sort_values(["team", "position", "game_date"]).reset_index(drop=True)
    return res


# ---------------------------------------------------------------- expanding as-of

def build_pos_asof(pg: pd.DataFrame) -> pd.DataFrame:
    """Expanding shift(1) mean per (team, position) + league-by-position baseline.
    Outputs one row per (team, position, game_date)."""
    pg = pg.sort_values(["team", "position", "game_date"]).reset_index(drop=True)

    # build expanding means per (team, position)
    out_frames = []
    for (team, pos), sub in pg.groupby(["team", "position"], sort=False):
        sub = sub.reset_index(drop=True)
        asof = sub[["game_date", "team", "opp", "position"]].copy()
        for s in FOCUS_STATS:
            asof[f"opp_{s}_allowed_to_{pos}_asof"] = sub[f"allowed_{s}"].shift(1).expanding().mean()
        asof[f"n_games_asof_{pos}"] = sub["game_date"].reset_index(drop=True).index  # 0,1,2,...
        out_frames.append(asof)

    combined = pd.concat(out_frames, ignore_index=True)

    # league-by-position baseline (expanding, strictly-before each row's date)
    for pos in POSITIONS:
        for s in FOCUS_STATS:
            col = f"allowed_{s}"
            asof_col = f"opp_{s}_allowed_to_{pos}_asof"
            # get all games for this position sorted by date
            pos_rows = pg[pg["position"] == pos].sort_values("game_date").reset_index(drop=True)
            if pos_rows.empty:
                continue
            # cumulative league mean strictly before each date
            pos_rows["league_cummean"] = pos_rows[col].expanding().mean().shift(1)
            # map (date, position) -> league_cummean
            league_lut: Dict[tuple, float] = {
                (r.game_date, pos): r.league_cummean
                for r in pos_rows.itertuples(index=False)
            }
            # attach to combined
            mask = combined["position"] == pos
            combined.loc[mask, f"_lg_{s}_{pos}"] = combined.loc[mask, "game_date"].map(
                lambda d, p=pos, s=s: league_lut.get((d, p), np.nan)
            )
            combined.loc[mask, f"opp_{s}_allowed_to_{pos}_vs_league"] = (
                combined.loc[mask, asof_col] - combined.loc[mask, f"_lg_{s}_{pos}"]
            )
            combined.drop(columns=[f"_lg_{s}_{pos}"], inplace=True, errors="ignore")

    return combined.sort_values(["team", "position", "game_date"]).reset_index(drop=True)


# ---------------------------------------------------------------- self-test

def leakfree_selftest(pg: pd.DataFrame, asof: pd.DataFrame) -> None:
    """Mirror template: verify each (team,pos) expanding mean uses only strictly-prior games."""
    pg = pg.sort_values(["team", "position", "game_date"]).reset_index(drop=True)
    asof = asof.sort_values(["team", "position", "game_date"]).reset_index(drop=True)
    checks = 0
    stat = FOCUS_STATS[0]  # reb
    col_raw = f"allowed_{stat}"
    for (team, pos), sub in pg.groupby(["team", "position"]):
        sub = sub.reset_index(drop=True)
        a = asof[(asof["team"] == team) & (asof["position"] == pos)].reset_index(drop=True)
        if len(a) == 0:
            continue
        asof_col = f"opp_{stat}_allowed_to_{pos}_asof"
        n_col = f"n_games_asof_{pos}"
        for k in range(len(sub)):
            if k >= len(a):
                break
            # n_games_asof should equal k
            assert int(a.loc[k, n_col]) == k, (
                f"n_games_asof mismatch ({team},{pos}) game{k}: "
                f"{a.loc[k, n_col]} != {k}"
            )
            if k == 0:
                assert pd.isna(a.loc[k, asof_col]), (
                    f"first game must be NaN as-of ({team},{pos})"
                )
            else:
                exp = sub.loc[:k - 1, col_raw].mean()
                got = a.loc[k, asof_col]
                assert abs(exp - got) < 1e-6, (
                    f"as-of leak ({team},{pos}) g{k}: {got} != {exp}"
                )
            checks += 1
            if checks > 4000:
                break
        if checks > 4000:
            break
    print(f"  leak-free self-test PASSED ({checks} (team,pos,game) cells verified)")


# ---------------------------------------------------------------- build

def build_tag(tag: str) -> pd.DataFrame:
    print(f"\n[{tag}] loading league log...")
    df = ba.load_league_log(tag)
    print(f"  {len(df):,} player-game rows, {df['game_date'].nunique()} dates, "
          f"{df['team'].nunique()} teams, {df['game_date'].min()} -> {df['game_date'].max()}")

    pos_map = load_pos_map()
    print(f"  position map: {len(pos_map):,} players with G/F/C classification")

    pg = pos_game_allowed(df, pos_map)
    print(f"  {len(pg):,} (team, position, game) rows after joining positions "
          f"[{pg['position'].value_counts().to_dict()}]")

    asof = build_pos_asof(pg)
    leakfree_selftest(pg, asof)

    # face-validity: late-season spread for REB by C
    for pos in POSITIONS:
        col = f"opp_reb_allowed_to_{pos}_asof"
        n_col = f"n_games_asof_{pos}"
        if col not in asof.columns:
            continue
        late = asof[(asof["position"] == pos) & (asof[n_col] >= 20)]
        if len(late):
            v = late.groupby("team")[col].last().sort_values()
            print(f"  REB-allowed-to-{pos} as-of (late, per team) range: "
                  f"{v.min():.1f} ({v.index[0]}) .. {v.max():.1f} ({v.index[-1]})")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"opp_pos_allowed_asof_{tag}.parquet")
    asof.to_parquet(out_path, index=False)
    print(f"  wrote {out_path}  ({len(asof):,} rows)")
    return asof


if __name__ == "__main__":
    tags = sys.argv[1:] or ["2025_26_reg", "2024_25"]
    for t in tags:
        build_tag(t)
