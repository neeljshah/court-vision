"""domains.mlb.pitch_engine.rung6_composite -- RUNG 6 of the MLB in-game win-prob
ladder: the LITERAL named-batter-vs-pitcher composition (task 44), the sharper twin
of rung 5's TEAM-level pitch-mix fallback (mlb_winprob_v5_composite, 2cb54695, which
picked w=0 -- added nothing beyond state).

WHAT IS DIFFERENT FROM RUNG 5 (the ONLY thing, per the matched-OOS protocol): rung 5
built a team-level pitcher-ahead-breaking-share scalar. Rung 6 builds a per-GAME win
prob from the ACTUAL nine named batters in each lineup, each carrying their own AS-OF
PA-event distribution, tilted by the OPPOSING starting pitcher's as-of allowed
distribution (event-level log5), chained through the pitch_engine game Monte-Carlo
(game_sim.simulate_game + BaseOutTransition). composite = logit(P(home win)). This is
literal player IDENTITY, the diagnosed missing ingredient (the live model sees only
~8 crude state features and no players).

LINEUPS (declared, lazy + uniform + leak-free-on-outcomes): the starting nine for a
game are the FIRST NINE DISTINCT batters each team sends up (in appearance order),
read from that game's own savant rows -- identity/order is pregame-observable, and the
batter's as-of distribution EXCLUDES this game's date, so no outcome leaks. This
sidesteps the mlb_lineups name->abbr join and the 2022-2024 lineup gap (mlb_lineups is
2025+ only) -- savant self-supplies lineups for every season uniformly. Starting
pitchers: the pitcher of the first top-1st PA (home SP) / first bottom-1st PA (away SP).

AS-OF / LEAK AUDIT: per-batter and per-pitcher event counts are aggregated per
(id, game_date), sorted, and read STRICTLY-PRIOR (cumsum-minus-own-date), pooled across
ALL seasons on disk (2023-2026) -- a 2025 game can only ever see dates < its own, so a
2026 date in the pooled array is invisible to it (identical argument to rung 5's LEAK
AUDIT). The league prior + base-out transition are LEAGUE-level normalizers fit on
2023+2024 ONLY, which wholly precede both VAL(2025) and EVAL(2026) -- strictly prior,
mild staleness declared. Missing id/date (a player's first game) -> league prior, never
a guess. Missing whole game (team absent) -> pa_composite=0.0/has_composite=False.

Team-abbr note: composite keyed in rung 5's CANON space so VAL (pitch_states abbrs,
via comp._canon) and EVAL (Kalshi ticker, already canon) both join. savant->canon is
just {AZ:ARI, CWS:CHW}; all-star AL/NL rows dropped.

INVARIANTS: domains-only; corpus/parquets READ-ONLY; ASCII; numpy/pandas; <=300 LOC;
never writes data/registry/; never flips a flag. edge_claimed=False everywhere.
Tests: python -m pytest domains/mlb/pitch_engine/test_rung6_composite.py -q
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine import corpus as cp
from domains.mlb.pitch_engine.game_sim import BaseOutTransition, GameStart, simulate_game
from domains.mlb.pitch_engine.pa_chain import _PA_IX  # OUT,K,BB,HBP,1B,2B,3B,HR
from scripts.platformkit.ingame import mlb_winprob_v5_composite as comp
from scripts.platformkit.ingame import ingame_outcome_label as iol

logger = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_CACHE = _REPO / "data" / "cache" / "ingame" / "mlb_rung6_composite.parquet"

ASOF_SEASONS: Tuple[int, ...] = (2023, 2024, 2025, 2026)
LEAGUE_SEASONS: Tuple[int, ...] = (2023, 2024)   # strictly prior to VAL 2025 + EVAL 2026
TARGET_SEASONS: Tuple[int, ...] = (2025, 2026)    # games needing a composite (val + eval)
N_EVT = len(_PA_IX)
SAVANT_TO_CANON: Dict[str, str] = {"AZ": "ARI", "CWS": "CHW"}
_PRIOR_STRENGTH = 120.0   # Dirichlet pseudo-count toward league prior (~120 PA)

_PA_COLS = ["game_pk", "game_date", "inning", "inning_topbot", "at_bat_number",
            "pitcher", "batter", "events", "on_1b", "on_2b", "on_3b",
            "outs_when_up", "bat_score", "post_home_score", "post_away_score",
            "home_team", "away_team"]


def _canon_savant(a: Any) -> str:
    s = str(a or "").strip().upper()
    return SAVANT_TO_CANON.get(s, s)


def load_pa(seasons: Sequence[int]) -> pd.DataFrame:
    """Lean PA frame (one row / plate appearance) with pa_evt + base_out_state + runs,
    straight from savant terminal pitches. All-star (AL/NL) rows dropped. Reuses
    corpus.pa_event / base_state_bits so labels match the pitch_engine exactly."""
    frames = []
    for yr in seasons:
        p = cp.parquet_path(yr)
        if not p.exists():
            continue
        frames.append(pd.read_parquet(p, columns=_PA_COLS))
    if not frames:
        return pd.DataFrame(columns=_PA_COLS + ["pa_evt", "base_out_state", "runs"])
    df = pd.concat(frames, ignore_index=True)
    df = df[df["events"].notna()].copy()
    df = df[~df["home_team"].isin(["AL", "NL"])].copy()
    df["batter"] = df["batter"].astype("int64")
    df["pitcher"] = df["pitcher"].astype("int64")
    df["pa_evt"] = cp.pa_event(df["events"])
    bits = cp.base_state_bits(df)
    outs = np.clip(df["outs_when_up"].to_numpy().astype(int), 0, 2)
    bat_is_home = df["inning_topbot"].astype(str).str.startswith("Bot").to_numpy()
    post_bat = np.where(bat_is_home, df["post_home_score"].to_numpy(),
                        df["post_away_score"].to_numpy())
    df["runs"] = np.maximum(post_bat - df["bat_score"].to_numpy(), 0).astype(int)
    df["base_mask"] = bits
    df["outs_start"] = outs
    df["base_out_state"] = bits * 3 + outs
    df["evix"] = df["pa_evt"].map(_PA_IX).astype(int)
    df["date"] = pd.to_datetime(df["game_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df.dropna(subset=["date"]).reset_index(drop=True)


def _asof_counts(pa: pd.DataFrame, id_col: str) -> Dict[Tuple[int, str], np.ndarray]:
    """{(id, date): STRICTLY-PRIOR event-count vector[8]} via cumsum-minus-own-date."""
    oneh = np.zeros((len(pa), N_EVT), dtype=np.int64)
    oneh[np.arange(len(pa)), pa["evix"].to_numpy()] = 1
    g = pa.groupby([id_col, "date"], sort=True)
    daily = pd.DataFrame(oneh, columns=[f"e{i}" for i in range(N_EVT)])
    daily[id_col] = pa[id_col].to_numpy()
    daily["date"] = pa["date"].to_numpy()
    agg = daily.groupby([id_col, "date"], as_index=False, sort=True).sum()
    ecols = [f"e{i}" for i in range(N_EVT)]
    grp = agg.groupby(id_col)
    prior = grp[ecols].cumsum() - agg[ecols]
    out: Dict[Tuple[int, str], np.ndarray] = {}
    ids = agg[id_col].to_numpy()
    dts = agg["date"].to_numpy()
    pv = prior.to_numpy()
    for i in range(len(agg)):
        out[(int(ids[i]), str(dts[i]))] = pv[i].astype(float)
    return out


def _norm(v: np.ndarray) -> np.ndarray:
    s = v.sum()
    return v / s if s > 0 else np.ones(N_EVT) / N_EVT


def _dist(counts: Optional[np.ndarray], prior: np.ndarray) -> np.ndarray:
    """Dirichlet-smoothed event dist toward the league prior (thin as-of N -> prior)."""
    c = counts if counts is not None else np.zeros(N_EVT)
    return _norm(c + _PRIOR_STRENGTH * prior)


def _tilt(bat: np.ndarray, pit_allowed: np.ndarray, league: np.ndarray) -> np.ndarray:
    """Event-level log5: combine batter dist and pitcher-allowed dist against the
    league baseline. normalize(b * q / l)."""
    l = np.where(league > 1e-9, league, 1e-9)
    return _norm(bat * pit_allowed / l)


def _lineups(g: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """First-9-distinct batters per half (appearance order) + the two starters."""
    g = g.sort_values(["inning", "at_bat_number"])
    top = g[g["inning_topbot"].astype(str).str.startswith("Top")]
    bot = g[g["inning_topbot"].astype(str).str.startswith("Bot")]
    away_b = list(dict.fromkeys(top["batter"].tolist()))[:9]
    home_b = list(dict.fromkeys(bot["batter"].tolist()))[:9]
    if len(away_b) < 9 or len(home_b) < 9 or top.empty or bot.empty:
        return None
    return {"away_batters": away_b, "home_batters": home_b,
            "home_sp": int(top["pitcher"].iloc[0]), "away_sp": int(bot["pitcher"].iloc[0])}


def build_composite_table(pa_asof: pd.DataFrame, pa_target: pd.DataFrame,
                          bat_asof, pit_asof, league: np.ndarray,
                          trans: BaseOutTransition, n_sims: int = 1200,
                          seed: int = 7) -> pd.DataFrame:
    """Per target game: named-lineup PA-chain game MC -> composite=logit(P(home win)).
    Keyed (date, home_canon, away_canon) in CANON space."""
    rows: List[Dict[str, Any]] = []
    for gpk, g in pa_target.groupby("game_pk", sort=False):
        lu = _lineups(g)
        if lu is None:
            continue
        date = str(g["date"].iloc[0])
        home = _canon_savant(g["home_team"].iloc[0])
        away = _canon_savant(g["away_team"].iloc[0])
        q_home = _dist(pit_asof.get((lu["home_sp"], date)), league)  # home SP allows
        q_away = _dist(pit_asof.get((lu["away_sp"], date)), league)  # away SP allows
        pa_home = np.array([_tilt(_dist(bat_asof.get((b, date)), league), q_away, league)
                            for b in lu["home_batters"]])            # home bats vs away SP
        pa_away = np.array([_tilt(_dist(bat_asof.get((b, date)), league), q_home, league)
                            for b in lu["away_batters"]])            # away bats vs home SP
        sh, sa = simulate_game(pa_away, pa_home, trans, n=n_sims,
                               seed=seed + (int(gpk) % 1000), start=GameStart())
        p_home = float(np.clip((sh > sa).mean(), 1e-3, 1 - 1e-3))
        rows.append({"date": date, "home": home, "away": away,
                     "composite": float(np.log(p_home / (1 - p_home))), "p_home": p_home})
    return pd.DataFrame(rows, columns=["date", "home", "away", "composite", "p_home"])


def build(cache_path: Optional[Path] = None, n_sims: int = 1200) -> pd.DataFrame:
    """Full pipeline (heavy; cached). Returns the composite table."""
    pa_asof = load_pa(ASOF_SEASONS)
    pa_league = pa_asof[pa_asof["game_date"].astype(str).str[:4].isin(
        [str(y) for y in LEAGUE_SEASONS])]
    league = _norm(np.bincount(pa_league["evix"].to_numpy(), minlength=N_EVT).astype(float))
    trans = BaseOutTransition.fit(pa_league)
    bat_asof = _asof_counts(pa_asof, "batter")
    pit_asof = _asof_counts(pa_asof, "pitcher")
    pa_target = pa_asof[pa_asof["game_date"].astype(str).str[:4].isin(
        [str(y) for y in TARGET_SEASONS])]
    table = build_composite_table(pa_target, pa_target, bat_asof, pit_asof, league,
                                  trans, n_sims=n_sims)
    cp_path = Path(cache_path) if cache_path is not None else DEFAULT_CACHE
    cp_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(cp_path, index=False)
    return table


def load_or_build(cache_path: Optional[Path] = None, n_sims: int = 1200) -> pd.DataFrame:
    cp_path = Path(cache_path) if cache_path is not None else DEFAULT_CACHE
    if cp_path.exists():
        return pd.read_parquet(cp_path)
    return build(cp_path, n_sims=n_sims)


def _table_dict(table: pd.DataFrame) -> Dict[Tuple[str, str, str], float]:
    return {(str(r.date), str(r.home), str(r.away)): float(r.composite)
            for r in table.itertuples()}


def _lookup_dated(td: Dict[Tuple[str, str, str], float], date: str, home: str,
                  away: str) -> Optional[float]:
    """Exact (date, home, away); fall back to +-1 day for the UTC-rollover landmine."""
    v = td.get((date, home, away))
    if v is not None:
        return v
    try:
        d0 = pd.Timestamp(date)
    except Exception:  # noqa: BLE001
        return None
    for delta in (-1, 1):
        alt = str((d0 + pd.Timedelta(days=delta)).date())
        v = td.get((alt, home, away))
        if v is not None:
            return v
    return None


def attach_composite_train(df: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """VAL/train rows (pitch_states: date + home_team/away_team in pitch_states abbrs).
    comp._canon maps those into CANON. missing -> 0.0/False."""
    out = df.copy()
    if out.empty:
        out["pa_composite"] = pd.Series(dtype=float)
        out["has_composite"] = pd.Series(dtype=bool)
        return out
    td = _table_dict(table)
    dates = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    home_c = out["home_team"].map(comp._canon)
    away_c = out["away_team"].map(comp._canon)
    val, has = [], []
    for h, a, dt in zip(home_c, away_c, dates):
        v = _lookup_dated(td, str(dt), str(h), str(a)) if isinstance(dt, str) else None
        val.append(v if v is not None else 0.0)
        has.append(v is not None)
    out["pa_composite"] = val
    out["has_composite"] = has
    return out


def attach_composite_eval(ticks: List[Dict[str, Any]], table: pd.DataFrame
                          ) -> List[Dict[str, Any]]:
    """EVAL ticks: game_id is a Kalshi ticker -> (date, away, home) in CANON."""
    td = _table_dict(table)
    out = []
    for t in ticks:
        parsed = iol.parse_mlb_ticker(str(t.get("game_id", "")), comp.VALID_TICKER_ABBRS)
        v = None
        if parsed is not None:
            date, away, home, _g = parsed
            v = _lookup_dated(td, str(pd.Timestamp(date).date()), str(home), str(away))
        out.append(dict(t, pa_composite=v if v is not None else 0.0,
                        has_composite=v is not None))
    return out


__all__ = ["DEFAULT_CACHE", "ASOF_SEASONS", "LEAGUE_SEASONS", "TARGET_SEASONS",
           "load_pa", "build_composite_table", "build", "load_or_build",
           "attach_composite_train", "attach_composite_eval", "SAVANT_TO_CANON"]
