"""domains.basketball_nba.sim2.corpus -- data preparation for the v2 simulator:
walk the 3-season PBP JSON into a possession table, and derive LEAK-FREE as-of
team off/def/pace terciles. Split out of validate.py so both stay <=300 LOC.

AS-OF STRENGTHS (declared, leak-free): per (game,team) off_rtg=100*pts/poss,
def_rtg=100*opp_pts/opp_poss, pace=poss/48min from the SAME possessions we extract;
the as-of value for a game is the shrink of the team's prior-THIS-season expanding
mean toward its prior-SEASON mean (k=5 pseudo-games; league mean when no prior
season). Terciles use FIT-season thresholds applied unchanged to the test season
(train/inference parity). def tercile is inverted so 2 == strongest defense.

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; no src/kernel imports.
"""
from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from domains.basketball_nba.sim2.possession_model import extract_possessions

_REPO = Path(__file__).resolve().parents[3]
_TS = _REPO / "data" / "cache" / "team_system"
PBP_DIRS = {"2023-24": _TS / "pbp_2023_24", "2024-25": _TS / "pbp_2024_25",
            "2025-26": _TS / "pbp"}
GAMES = _REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
CACHE = _REPO / "data" / "cache" / "ingame" / "sim2_possessions.parquet"
FIT_SEASONS = ("2023-24", "2024-25")
TEST_SEASON = "2025-26"
SHRINK_K = 5.0


def build_corpus(max_games: Optional[int] = None) -> pd.DataFrame:
    """Walk the PBP JSON, extract possessions for all 3 seasons, tag game_id+season.
    A broken/empty game file is skipped -- never fabricate a play."""
    rows: List[Dict[str, Any]] = []
    for season, d in PBP_DIRS.items():
        files = sorted(d.glob("*.json"))
        if max_games:
            files = files[:max_games]
        for fp in files:
            try:
                g = _json.loads(fp.read_text(encoding="utf-8"))["game"]
                ps = extract_possessions(g["actions"])
            except Exception:
                continue
            for p in ps:
                p["game_id"] = str(g["gameId"])
                p["season"] = season
            rows.extend(ps)
    return pd.DataFrame(rows)


def load_corpus(rebuild: bool, max_games: Optional[int]) -> pd.DataFrame:
    if CACHE.exists() and not rebuild:
        return pd.read_parquet(CACHE)
    df = build_corpus(max_games)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE, index=False)
    return df


def _game_team_ratings(poss: pd.DataFrame) -> pd.DataFrame:
    """Per (game_id, is_home) offensive/defensive/pace rating for the game itself."""
    recs = []
    for gid, gdf in poss.groupby("game_id"):
        hp = gdf[gdf["off_is_home"]]
        ap = gdf[~gdf["off_is_home"]]
        if len(hp) < 20 or len(ap) < 20:
            continue
        maxper = int(gdf["period"].max())
        mins = 48.0 + 5.0 * max(0, maxper - 4)
        for is_home, mine, opp in ((True, hp, ap), (False, ap, hp)):
            recs.append({"game_id": gid, "is_home": is_home,
                         "off_rtg": 100.0 * mine["points"].sum() / len(mine),
                         "def_rtg": 100.0 * opp["points"].sum() / len(opp),
                         "pace": len(mine) * 48.0 / mins, "season": gdf["season"].iloc[0]})
    return pd.DataFrame(recs)


def asof_series(vals: List[float], base: float, k: float) -> List[float]:
    """Leak-free expanding as-of: for each game (chronological) return the mean of
    STRICTLY PRIOR games shrunk toward `base` with k pseudo-games. The current
    game's own value is appended AFTER its as-of is recorded -- no game sees itself."""
    out: List[float] = []
    hist: List[float] = []
    for v in vals:
        n = len(hist)
        emean = float(np.mean(hist)) if n else base
        out.append(emean if (n + k) == 0 else (n * emean + k * base) / (n + k))
        hist.append(float(v))
    return out


def build_asof_terciles(poss: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Leak-free as-of off/def/pace per (game_id,is_home) -> per-game wide tercile
    table (home_off_t, home_def_t, away_off_t, away_def_t, pace_t, season) indexed by
    game_id, plus the fit-season tercile thresholds."""
    gt = _game_team_ratings(poss)
    games = pd.read_parquet(GAMES)[["game_id", "date", "home_team", "away_team"]]
    games["game_id"] = games["game_id"].astype(str)
    date_by = dict(zip(games["game_id"], pd.to_datetime(games["date"])))
    gt["date"] = gt["game_id"].map(date_by)
    gt = gt.dropna(subset=["date"]).sort_values("date")
    tri = {str(r.game_id): (r.home_team, r.away_team) for r in games.itertuples(index=False)}
    gt["team"] = [tri[g][0] if h else tri[g][1] for g, h in zip(gt["game_id"], gt["is_home"])]
    seas_order = sorted(gt["season"].unique())
    prev_season = {s: (seas_order[i - 1] if i > 0 else None) for i, s in enumerate(seas_order)}
    league = {c: gt[c].mean() for c in ("off_rtg", "def_rtg", "pace")}
    prior_mean = (gt.groupby(["season", "team"])[["off_rtg", "def_rtg", "pace"]]
                  .mean().to_dict("index"))
    asof_rows = []
    for (team, s), tdf in gt.groupby(["team", "season"]):
        tdf = tdf.sort_values("date")
        ps = prev_season[s]
        rec = {"game_id": list(tdf["game_id"]), "is_home": list(tdf["is_home"])}
        for col in ("off_rtg", "def_rtg", "pace"):
            base = (prior_mean.get((ps, team), {}).get(col) if ps else None) or league[col]
            rec[col] = asof_series(list(tdf[col]), base, SHRINK_K)
        asof_rows.append(pd.DataFrame(rec))
    a = pd.concat(asof_rows, ignore_index=True)
    a = a.merge(gt[["game_id", "is_home", "season"]], on=["game_id", "is_home"])
    fit = a[a["season"].isin(FIT_SEASONS)]
    thr = {c: [float(fit[c].quantile(1 / 3)), float(fit[c].quantile(2 / 3))]
           for c in ("off_rtg", "def_rtg", "pace")}

    def terc(v, c):
        return int((v >= thr[c][0]) + (v >= thr[c][1]))
    for c in ("off_rtg", "def_rtg", "pace"):
        a[c + "_t"] = [terc(v, c) for v in a[c]]
    a["def_rtg_t"] = 2 - a["def_rtg_t"]           # higher tercile == stronger defense
    home = a[a["is_home"]].set_index("game_id")
    away = a[~a["is_home"]].set_index("game_id")
    wide = pd.DataFrame({
        "season": home["season"],
        "home_off_t": home["off_rtg_t"], "home_def_t": home["def_rtg_t"],
        "away_off_t": away["off_rtg_t"], "away_def_t": away["def_rtg_t"],
        "pace_t": ((home["pace_t"] + away["pace_t"]) // 2).clip(0, 2),
    }).dropna().astype({"home_off_t": int, "home_def_t": int, "away_off_t": int,
                        "away_def_t": int, "pace_t": int})
    return wide, thr


def attach_terciles(poss: pd.DataFrame, wide: pd.DataFrame) -> pd.DataFrame:
    """Attach off_t/def_t/pace_t to each possession from the per-game wide table.
    `wide` carries its own `season` column (same value as `poss.season` for a given
    game_id) -- drop it before merging so pandas never suffixes season_x/season_y
    (bdc6b03e bug class: a silent suffix collision hid an axis from downstream fits)."""
    w = wide.reset_index().drop(columns=["season"])
    m = poss.merge(w, on="game_id", how="inner")
    m["off_t"] = np.where(m["off_is_home"], m["home_off_t"], m["away_off_t"])
    m["def_t"] = np.where(m["off_is_home"], m["away_def_t"], m["home_def_t"])
    return m


__all__ = ["PBP_DIRS", "GAMES", "CACHE", "FIT_SEASONS", "TEST_SEASON", "build_corpus",
           "load_corpus", "asof_series", "build_asof_terciles", "attach_terciles"]
