"""domains.basketball_nba.asof_quarter_shape -- leak-free as-of QUARTER-SHAPE features.

A team's scoring DISTRIBUTION across quarters (early vs late margin, close strength,
inter-quarter volatility) is the natural PREGAME PRIOR for in-game conditioning: a team
that habitually outscores opponents late shifts the live win-prob update differently
than one that fades. This builds those priors LEAK-FREE and offline.

Built from data/domains/basketball_nba/linescores.parquet ALONE (home_q1..q4 / away_q1..q4
+ date + home_abbr/away_abbr). Team abbr is the stable per-franchise entity key, and a
team's history accumulates across BOTH its home and away appearances (state keyed by the
global entity id in scripts.platformkit.asof_common -- dogfooded here). Strictly prior-only
(snapshot-before-update); debut -> NaN; no-future-leak assertion inherited from asof_common.

Per team, each game yields these REALIZED (team-perspective, signed for/against) metrics,
which the as-of pass turns into prior-only trailing means:

  q1_margin           = own_q1 - opp_q1                       (how a team starts)
  first_half_margin   = (own_q1+own_q2) - (opp_q1+opp_q2)
  second_half_margin  = (own_q3+own_q4) - (opp_q3+opp_q4)
  q4_margin           = own_q4 - opp_q4                       (how a team closes)
  quarter_volatility  = stdev of the team's four OWN per-quarter POINTS (scoring consistency;
                        own-points not margin, since margins are antisymmetric -> the
                        home-minus-away diff of a margin-vol would be degenerately zero)

JOIN: linescores carries ESPN abbreviations (GS/NO/NY/SA/UTAH/WSH) and an ESPN event_id;
the games corpus uses NBA abbreviations (GSW/NOP/...) and an NBA game_id. The as-of pass
runs on the linescores-native team key (per-franchise history is identical either way);
the output is then joined (date, canonical home/away abbr) -> games game_id so it is keyed
by the SAME game_id the proof harness's Elo base bundle uses. State accumulates on ALL
linescores history regardless of whether a game_id join exists (correct leak-free behaviour;
unmatched rows simply carry game_id=NaN and drop out of the gate alignment).

CROSS-LANE NOTE (Lane A hook): the VALUE of this builder is as an IN-GAME PRIOR for Lane
A's repricer -- a team's realized quarter-shape (strong-close / slow-start tendency) is a
leak-free conditioning prior for live win-prob re-pricing once a partial line is known.
PREGAME it is expected to REJECT (team strength is already in the Elo base). This builder
does NOT wire into Lane A; that is Lane A's lane.

NETWORK: zero. PURE pandas/numpy + asof_common. ASCII only.
ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.platformkit.asof_common import AsofSpec, ExpandingMean, walk_forward_asof

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LINESCORES_DEFAULT = str(
    _REPO_ROOT / "data" / "domains" / "basketball_nba" / "linescores.parquet")
_OUT_DEFAULT = str(
    _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_quarter_shape.parquet")

# ESPN -> NBA canonical team abbreviation (the 6 that differ).
_ESPN_TO_NBA = {
    "GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS",
}

_QCOLS = ("q1", "q2", "q3", "q4")
# Realized per-team metric -> the quarters it reads (all margins are team-minus-opponent).
_METRICS = ("q1_margin", "first_half_margin", "second_half_margin", "q4_margin",
            "quarter_volatility")


def _num(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s, errors="coerce").to_numpy(dtype="float64")


def _canon_abbr(s: pd.Series) -> pd.Series:
    """Map ESPN abbreviations to the games-corpus NBA canonical form."""
    return s.astype(str).map(lambda x: _ESPN_TO_NBA.get(x, x))


def _derive_realized(ls: pd.DataFrame) -> pd.DataFrame:
    """Add home_/away_ realized quarter-shape metrics to a linescores slice."""
    out = pd.DataFrame({
        "event_id": ls["event_id"].to_numpy(),
        "date": ls["date"].to_numpy(),
        "home_key": _canon_abbr(ls["home_abbr"]).to_numpy(),
        "away_key": _canon_abbr(ls["away_abbr"]).to_numpy(),
    })
    h = {q: _num(ls[f"home_{q}"]) for q in _QCOLS}
    a = {q: _num(ls[f"away_{q}"]) for q in _QCOLS}

    def _add(side: str, me: dict, opp: dict) -> None:
        m = [me[q] - opp[q] for q in _QCOLS]  # signed per-quarter margins q1..q4
        out[f"{side}_q1_margin"] = m[0]
        out[f"{side}_first_half_margin"] = m[0] + m[1]
        out[f"{side}_second_half_margin"] = m[2] + m[3]
        out[f"{side}_q4_margin"] = m[3]
        # Volatility is the stdev of the team's OWN per-quarter POINTS (not the margin):
        # margins are antisymmetric (away = -home), so a margin-based vol is identical for
        # both teams and its home-minus-away diff is degenerately zero. Own-points vol is a
        # genuine per-team scoring-consistency prior that differs between the two teams.
        out[f"{side}_quarter_volatility"] = np.std(
            np.column_stack([me[q] for q in _QCOLS]), axis=1)  # NaN if any quarter NaN

    _add("home", h, a)
    _add("away", a, h)
    return out


def _attach_game_id(result: pd.DataFrame, spine: pd.DataFrame,
                    games: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Join (date, canonical home/away abbr) -> games game_id; NaN where unmatched."""
    result = result.merge(
        spine[["event_id", "date", "home_key", "away_key"]], on="event_id", how="left")
    result["game_id"] = np.nan
    if games is None:
        try:
            from domains.basketball_nba.adapter import NBAAdapter  # noqa: PLC0415
            games = NBAAdapter()._get_games()
        except Exception:  # pragma: no cover - guarded; builder still emits event_id
            games = None
    if games is not None and len(games) > 0:
        g = games.copy()
        g["_ds"] = pd.to_datetime(g["date"]).dt.date.astype(str)
        lut = {(r["_ds"], str(r["home_team"]), str(r["away_team"])): str(r["game_id"])
               for _, r in g.iterrows()}
        ds = pd.to_datetime(result["date"]).dt.date.astype(str)
        result["game_id"] = [
            lut.get((d, h, a), np.nan)
            for d, h, a in zip(ds, result["home_key"], result["away_key"])]
    return result.drop(columns=["date", "home_key", "away_key"])


def build_asof_quarter_shape(
    linescores: Optional[pd.DataFrame] = None,
    games: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build leak-free as-of quarter-shape features; write parquet, return Path.

    Output: one row per linescores game with ``event_id`` (ESPN), a joined NBA
    ``game_id`` (NaN where the date+abbr join misses), home_/away_ trailing as-of
    means + n_prior counts, and home-minus-away diff_*_asof columns per metric.
    """
    if linescores is None:
        linescores = pd.read_parquet(_LINESCORES_DEFAULT)
    spine = _derive_realized(linescores)

    result = pd.DataFrame({"event_id": spine["event_id"].to_numpy()})
    for i, m in enumerate(_METRICS):
        spec = AsofSpec(
            sort_keys=["date", "event_id"],
            slots=[("home_key", f"home_{m}", f"home_{m}"),
                   ("away_key", f"away_{m}", f"away_{m}")],
        )
        res = walk_forward_asof(spine, spec, ExpandingMean)
        cols = ["event_id", f"home_{m}_asof", f"away_{m}_asof"]
        if i == 0:  # n_prior is metric-independent (same appearances) -> keep once
            res = res.rename(columns={f"home_{m}_n_prior": "home_n_prior",
                                      f"away_{m}_n_prior": "away_n_prior"})
            cols += ["home_n_prior", "away_n_prior"]
        result = result.merge(res[cols], on="event_id", how="left")
        result[f"diff_{m}_asof"] = result[f"home_{m}_asof"] - result[f"away_{m}_asof"]

    result = _attach_game_id(result, spine, games)

    dest = Path(out_path) if out_path is not None else Path(_OUT_DEFAULT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(result, preserve_index=False), dest)
    return dest


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Build leak-free NBA as-of quarter-shape features")
    parser.add_argument("--linescores", default=_LINESCORES_DEFAULT)
    parser.add_argument("--out-path", default=_OUT_DEFAULT)
    args = parser.parse_args()
    from domains.basketball_nba.asof_quarter_shape_eval import run_eval  # noqa: PLC0415
    run_eval(args.linescores, args.out_path)


if __name__ == "__main__":
    _cli()


__all__ = [
    "build_asof_quarter_shape", "_derive_realized", "_attach_game_id", "_canon_abbr",
    "_METRICS", "_ESPN_TO_NBA", "_LINESCORES_DEFAULT", "_OUT_DEFAULT",
]
