"""scripts.platformkit.live_edge.tails -- B2 tail/skew distributional-shape
metrics (per-entity empirical distribution + pooled shrinkage), pure compute
module (no ledger writes -- see tail_sweep.py for that).

Stores (premise-checked 2026-07-14):
  NBA player-grain: data/domains/basketball_nba/player_boxscores.parquet
      (77,744 rows / 807 players, per-GAME, capped 2026-04-12 -- known gap,
      fine for discovery). season col in {"2023-24","2024-25","2025-26"}.
      Reserve = "2025-26" (same whole-season reserve unit situation_grid.py
      uses for this box store -- no per-possession date to cut mid-season).
  MLB player-grain: DATA-ABSENT. Only team-grain box exists on disk
      (data/domains/mlb/espn_boxscores.parquet, home/away_bat_* aggregates);
      no per-player MLB batting-line store. Declared DATA_ABSENT, never
      faked -- see tail_sweep.py's structural claim.
  MLB team-grain: data/domains/mlb/espn_boxscores.parquet (3,925 games,
      2025-03-27..2026-07-12, runs non-null 3919/3925). Reserve = 2026
      (whole-calendar-year reserve, same convention: no finer knowable-at
      cutover column on this store).

Pooled shrinkage (S8.6 pattern): league -> archetype (discovery-median
quartile bucket, cheap usage proxy) -> entity. James-Stein-style weight
w = n / (n + K_SHRINK); metric = w*entity_raw + (1-w)*archetype_pooled.

INVARIANTS: pandas/numpy/scipy + stdlib only. <=300 LOC. ASCII stdout.
Never writes data/registry/. No $/edge claims.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
from scipy import stats as sps

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
NBA_PLAYER_BOX_PATH = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
MLB_TEAM_BOX_PATH = REPO_ROOT / "data" / "domains" / "mlb" / "espn_boxscores.parquet"

NBA_RESERVE_SEASON = "2025-26"
MLB_RESERVE_YEAR = 2026

MIN_N = 10          # below this: INSUFFICIENT_DATA, no metric computed
K_SHRINK = 20        # shrinkage strength toward archetype pool
QUANTILES = [0.005, 0.01, 0.025, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.975, 0.99, 0.995]
BENCH_MIN_FRAC = 0.5  # minutes < 0.5x median minutes counts as a blowout-bench tail event


def load_nba_player_box(source=None) -> pd.DataFrame:
    return source.copy() if isinstance(source, pd.DataFrame) else pd.read_parquet(
        source if source is not None else NBA_PLAYER_BOX_PATH)


def split_nba_discovery_reserve(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    is_reserve = df["season"] == NBA_RESERVE_SEASON
    return df.loc[~is_reserve].copy(), df.loc[is_reserve].copy()


def load_mlb_team_runs(source=None) -> pd.DataFrame:
    """Reshape espn_boxscores.parquet's wide home/away row into one row per
    team-game with a `runs` column (team-grain tail metrics only -- MLB has
    no per-player box store on disk)."""
    df = source.copy() if isinstance(source, pd.DataFrame) else pd.read_parquet(
        source if source is not None else MLB_TEAM_BOX_PATH)
    df = df.dropna(subset=["home_bat_runs", "away_bat_runs"])
    home = df.rename(columns={"home_abbr": "team", "away_abbr": "opp", "home_bat_runs": "runs"})
    home = home[["event_id", "date", "team", "opp", "runs"]]
    away = df.rename(columns={"away_abbr": "team", "home_abbr": "opp", "away_bat_runs": "runs"})
    away = away[["event_id", "date", "team", "opp", "runs"]]
    return pd.concat([home, away], ignore_index=True)


def split_mlb_discovery_reserve(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    is_reserve = pd.to_datetime(df["date"]).dt.year >= MLB_RESERVE_YEAR
    return df.loc[~is_reserve].copy(), df.loc[is_reserve].copy()


def _archetype_bucket(median_by_entity: pd.Series) -> pd.Series:
    """Discovery-median quartile bucket -- cheap usage-tier proxy (star /
    rotation / role / fringe), never a modeled archetype."""
    try:
        return pd.qcut(median_by_entity, 4, labels=["q1_low", "q2", "q3", "q4_high"], duplicates="drop")
    except ValueError:
        return pd.Series("q_all", index=median_by_entity.index)


def _entity_dist(vals: np.ndarray) -> dict:
    med = float(np.median(vals))
    breakout = float(np.mean(vals > 1.5 * med)) if med > 0 else float("nan")
    dud = float(np.mean(vals < 0.5 * med))
    return {
        "n": int(len(vals)), "median": med, "mean": float(np.mean(vals)),
        "std": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
        "skew": float(sps.skew(vals)) if len(vals) > 2 else 0.0,
        "breakout_prob": breakout, "dud_prob": dud,
        "quantiles": {str(q): float(np.quantile(vals, q)) for q in QUANTILES},
    }


def _shrink(entity: dict, pooled: dict, key: str) -> float:
    n = entity["n"]
    w = n / (n + K_SHRINK)
    e_val, p_val = entity.get(key), pooled.get(key)
    if e_val is None or (isinstance(e_val, float) and np.isnan(e_val)):
        return p_val
    return w * e_val + (1 - w) * p_val


def compute_tail_metrics(df: pd.DataFrame, entity_col: str, stat_col: str,
                          min_col: str | None = None) -> dict[str, dict]:
    """Per-entity empirical tail metrics with pooled league->archetype->entity
    shrinkage. Returns {entity_id: metrics_dict}; entities below MIN_N still
    get an entry but flagged insufficient=True (caller ledgers INSUFFICIENT_DATA)."""
    out: dict[str, dict] = {}
    groups = {e: g[stat_col].to_numpy(dtype=float) for e, g in df.groupby(entity_col, observed=True)}
    medians = pd.Series({e: float(np.median(v)) for e, v in groups.items() if len(v) >= 3})
    archetypes = _archetype_bucket(medians) if len(medians) else pd.Series(dtype=object)
    league_pool = _entity_dist(df[stat_col].dropna().to_numpy(dtype=float))
    arche_pool = {}
    for a in archetypes.unique() if len(archetypes) else []:
        ids = archetypes[archetypes == a].index
        vals = df[df[entity_col].isin(ids)][stat_col].dropna().to_numpy(dtype=float)
        arche_pool[a] = _entity_dist(vals) if len(vals) >= MIN_N else league_pool

    for e, vals in groups.items():
        n = len(vals)
        if n < MIN_N:
            out[e] = {"insufficient": True, "n": n}
            continue
        raw = _entity_dist(vals)
        pooled = arche_pool.get(archetypes.get(e), league_pool)
        shrunk = dict(raw)
        for key in ("breakout_prob", "dud_prob", "std", "skew"):
            shrunk[key] = _shrink(raw, pooled, key)
        shrunk["insufficient"] = False
        shrunk["archetype"] = str(archetypes.get(e, "q_all"))
        if min_col is not None and min_col in df.columns:
            mvals = df[df[entity_col] == e][min_col].dropna().to_numpy(dtype=float)
            if len(mvals) >= MIN_N:
                med_min = float(np.median(mvals))
                shrunk["bench_tail_prob"] = float(np.mean(mvals < BENCH_MIN_FRAC * med_min)) if med_min > 0 else 0.0
        out[e] = shrunk
    return out


def fit_test_halves(df: pd.DataFrame, date_col: str = "date") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chronological half-split WITHIN discovery (never touches reserve) for
    tail-bin calibration: fit quantiles on the earlier half, check realized
    coverage on the later half."""
    d = df.sort_values(date_col)
    cut = len(d) // 2
    return d.iloc[:cut].copy(), d.iloc[cut:].copy()
