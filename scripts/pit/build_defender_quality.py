"""Point-in-time (PIT) defender team quality builder — H3 signal substrate.

Aggregates NBA defender_matchups_2025-26.parquet (individual defender rows) to
team-game totals, then builds expanding shift(1) as-of rolling signals per
defending team, keyed (def_team_tricode, game_date).

Signals:
  team_def_pts_allowed_pm_asof   -- per-matchup-minute scoring rate allowed (pts / matchup_mins)
  team_def_fg_pct_allowed_asof   -- team FG% allowed (sum fg_made / sum fg_att)
  team_def_fg3_pct_allowed_asof  -- team FG3% allowed
  team_switch_rate_asof          -- team switches per matchup

All four also exported as _vs_league: value - league_asof_baseline.

Leak-free by construction: the as-of for game k uses ONLY games 1..k-1
(expanding mean, shift(1) per def_team_tricode). No future data used.

Output: data/cache/pit/defender_team_quality_asof.parquet

Read-only except writing under data/cache/pit/.
Only 2025-26 season covered (defender_matchups_2025-26.parquet is single season).
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(DATA, "cache", "pit")
SRC = os.path.join(DATA, "defender_matchups_2025-26.parquet")
OUT_PATH = os.path.join(OUT_DIR, "defender_team_quality_asof.parquet")

# The raw per-game signals we build asof values for (all additive for sum-aggregation)
_SUM_COLS = [
    "points_allowed",
    "fg_made_allowed",
    "fg_attempted_allowed",
    "fg3_made_allowed",
    "fg3_attempted_allowed",
    "switches_on",
    "matchup_minutes_total",
    "matchups_count",
]

# The four derived signals (computed from aggregated sums) that we build asof for
_SIGNAL_NAMES = [
    "def_pts_pm",        # points_allowed / matchup_minutes_total (per minute)
    "def_fg_pct",        # fg_made_allowed / fg_attempted_allowed
    "def_fg3_pct",       # fg3_made_allowed / fg3_attempted_allowed
    "def_switch_rate",   # switches_on / matchups_count
]


def load_team_games() -> pd.DataFrame:
    """Load defender_matchups, aggregate to (def_team_tricode, game_date) team totals.

    Returns one row per (def_team_tricode, game_date) with summed raw columns.
    """
    df = pd.read_parquet(SRC)
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.normalize()

    tg = (
        df.groupby(["def_team_tricode", "game_date"], as_index=False)[_SUM_COLS]
        .sum(min_count=1)
        .rename(columns={"def_team_tricode": "team"})
        .sort_values(["team", "game_date"])
        .reset_index(drop=True)
    )

    # Derived per-game signals
    tg["def_pts_pm"] = tg["points_allowed"] / tg["matchup_minutes_total"].clip(lower=1e-3)
    tg["def_fg_pct"] = tg["fg_made_allowed"] / tg["fg_attempted_allowed"].clip(lower=1)
    tg["def_fg3_pct"] = tg["fg3_made_allowed"] / tg["fg3_attempted_allowed"].clip(lower=1)
    tg["def_switch_rate"] = tg["switches_on"] / tg["matchups_count"].clip(lower=1)

    return tg


def build_asof(tg: pd.DataFrame) -> pd.DataFrame:
    """Expanding shift(1) per team -> team_def_<signal>_asof + _vs_league.

    League baseline: expanding mean across ALL teams (shift(1) by sorted date
    so baseline for date d uses only games on dates strictly before d).
    """
    tg = tg.sort_values(["team", "game_date"]).reset_index(drop=True)
    out = tg[["team", "game_date"]].copy()

    # per-team as-of (expanding mean, shift 1)
    for sig in _SIGNAL_NAMES:
        col_asof = f"team_{sig}_asof"
        out[col_asof] = (
            tg.groupby("team")[sig]
            .apply(lambda x: x.shift(1).expanding().mean())
            .reset_index(level=0, drop=True)
        )

    # n_games_asof (cumcount before this game)
    out["n_games_asof"] = tg.groupby("team").cumcount()

    # League as-of baseline: expanding mean of the raw signal across all games,
    # strictly-before each row's date (shift by sorted date to avoid leaking today).
    # Method: sort all rows by date, cumulative mean of raw signal, shift(1) to exclude today.
    for sig in _SIGNAL_NAMES:
        col_asof = f"team_{sig}_asof"
        col_vs_league = f"team_{sig}_vs_league"

        # Build date-sorted league cumulative mean
        srt = tg[["game_date", sig]].copy().sort_values("game_date").reset_index()
        srt["league_cummean"] = srt[sig].expanding().mean().shift(1)
        league_map = srt.set_index("index")["league_cummean"]

        out[f"_league_{sig}"] = out.index.map(league_map)
        # vs_league: positive => allows MORE than league avg => softer defense
        out[col_vs_league] = out[col_asof] - out[f"_league_{sig}"]
        out.drop(columns=[f"_league_{sig}"], inplace=True)

    return out


def leakfree_selftest(tg: pd.DataFrame, asof: pd.DataFrame) -> None:
    """Assert each team's as-of value == expanding mean of strictly-prior games.

    Checks all teams up to 5000 (team, game) cells total.
    """
    tg = tg.sort_values(["team", "game_date"]).reset_index(drop=True)
    asof = asof.sort_values(["team", "game_date"]).reset_index(drop=True)

    checks = 0
    failures = 0
    for team, sub in tg.groupby("team"):
        sub = sub.reset_index(drop=True)
        a = asof[asof.team == team].reset_index(drop=True)

        for k in range(len(sub)):
            expect_n = k
            got_n = int(a.loc[k, "n_games_asof"])
            if got_n != expect_n:
                print(f"  FAIL n_games_asof {team} game{k}: {got_n} != {expect_n}")
                failures += 1

            if k == 0:
                # first game must be NaN (no prior data)
                if not pd.isna(a.loc[k, "team_def_fg_pct_asof"]):
                    print(f"  FAIL first game must be NaN ({team})")
                    failures += 1
            else:
                # check def_fg_pct as-of equals mean of prior games
                exp = sub.loc[: k - 1, "def_fg_pct"].mean()
                got = a.loc[k, "team_def_fg_pct_asof"]
                if not np.isnan(got) and abs(exp - got) > 1e-6:
                    print(f"  FAIL as-of leak {team} g{k}: got={got:.8f} expected={exp:.8f}")
                    failures += 1

            checks += 1
            if checks >= 5000:
                break
        if checks >= 5000:
            break

    if failures == 0:
        print(f"  leak-free self-test PASSED ({checks} (team,game) cells verified, 0 failures)")
    else:
        raise AssertionError(f"leak-free self-test FAILED: {failures} failures in {checks} checks")


def build() -> pd.DataFrame:
    print("[build_defender_quality] loading defender_matchups_2025-26.parquet ...")
    tg = load_team_games()
    print(f"  {len(tg):,} team-games  |  {tg['team'].nunique()} teams  |  "
          f"dates {tg['game_date'].min().date()} -> {tg['game_date'].max().date()}")

    print("  building as-of expanding signals ...")
    asof = build_asof(tg)

    print("  running leak-free self-test ...")
    leakfree_selftest(tg, asof)

    os.makedirs(OUT_DIR, exist_ok=True)
    asof.to_parquet(OUT_PATH, index=False)
    print(f"  wrote {OUT_PATH}  ({len(asof):,} rows)")

    # Face validity: late-season spread of FG% allowed
    late = asof[asof.n_games_asof >= 20]
    if len(late):
        v = late.groupby("team")["team_def_fg_pct_asof"].last().sort_values()
        print(f"  FG%-allowed as-of (late, per team) range: "
              f"{v.min():.3f} ({v.index[0]}) .. {v.max():.3f} ({v.index[-1]})")
        v2 = late.groupby("team")["team_def_pts_pm_asof"].last().sort_values()
        print(f"  pts/min-allowed as-of (late, per team) range: "
              f"{v2.min():.3f} ({v2.index[0]}) .. {v2.max():.3f} ({v2.index[-1]})")

    return asof


if __name__ == "__main__":
    build()
