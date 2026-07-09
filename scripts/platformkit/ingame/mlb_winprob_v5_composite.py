"""scripts.platformkit.ingame.mlb_winprob_v5_composite -- GAME-level PA-outcome
composition feature for mlb_winprob_v5.py (LOC-cap split; see mlb_winprob_v5.py's
docstring for the full rung-5 design).

COMPOSITION DIRECTIVE (team-level fallback, declared): the REPLICATED PA-outcome
machinery (domains/mlb/matchup/pa_outcome_v2_replicate_2024.py, 31cbd3df -- platoon x
pitch-type + as-of mix features) operates on batter/pitcher STATCAST IDs, which are
only on disk through statcast_fuller/savant_full 2022-2024 -- NO 2025/2026 rows exist
for that corpus, and per-game STARTING LINEUPS are not cheaply available for the
2026 eval corpus either. Both premises of a literal batter-vs-pitcher composition are
missing for exactly the games that matter (2025 val, 2026 eval). FALLBACK (declared,
matches mission's "team-level as-of PA-profile aggregate" clause): reuse the SAME
mlb_pitch_states__<year>.parquet corpus the STATE model already trains on (it has
home_team/away_team/pitch_type/count columns for EVERY needed season, 2022-2026) to
build a TEAM-level analogue of v2b's own pitcher_ahead_breaking_share_asof feature --
the fraction of a team's PITCHING-side pitches thrown while pitcher-ahead
(strikes>balls pre-pitch) that were breaking/offspeed (FASTBALL_TYPES excluded, same
constant imported from domains.mlb.prereg.mlb_hypotheses, not redefined) -- walked
forward BY CALENDAR DATE, STRICTLY PRIOR (cumsum-minus-own, same shape as v2b's
_expanding_asof_share, reimplemented here at team grain rather than parameterizing
that pitcher-keyed function).

LEAK AUDIT: the table is built ONCE from ALL FIVE seasons on disk (2022-2026)
concatenated and sorted by date, but every row's share is the CUMULATIVE SUM OF PRIOR
DATES ONLY (today's own date is subtracted back out) -- structurally identical to how
the state model's own inning/outs/count features are as-of-that-tick. Building the
table from the full corpus is not a leak: a 2022 game's composite can only ever see
pitches thrown on an EARLIER date, regardless of what the table array also contains
for 2026. GAME_COMPOSITE = home_team_share_asof - away_team_share_asof (home's own
pitching-staff tendency minus the opponent's, i.e. a HOME-perspective offset; sign
correctness is not independently verified -- w=0 on the grid is the safety net if it
is wrong, see mlb_winprob_v5.py). Missing team/date (no prior pitches for either side,
e.g. a team's first games on file, or a team absent from the corpus e.g. Athletics
2025/2026 -- a pre-existing pitch_states extraction gap, not introduced here) ->
pa_composite=0.0 (neutral offset, not a fabricated lean), has_composite=False.

Team-abbr note: mlb_pitch_states uses a non-standard abbr set (CUB/CWS/KAN/SDG/SFO/
TAM/WAS/OAK) that diverges from the ESPN-box / Kalshi-ticker abbr space the EVAL side
already normalizes to (iol.parse_mlb_ticker + iol._KALSHI_TO_ESPN) -- PITCH_ABBR_TO_CANON
below maps pitch_states's own abbrs into that same canonical space so train-side and
eval-side team keys actually join.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no network at import; never
writes data/registry/; never flips a flag; pitch_states parquets READ-ONLY.

Per-file test: covered by test_mlb_winprob_v5.py (imports this module directly).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.mlb.prereg.mlb_hypotheses import FASTBALL_TYPES
from scripts.platformkit.ingame import ingame_outcome_label as iol

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PITCH_STATES_DIR = _REPO_ROOT / "data" / "cache" / "ingame"

# pitch_states' own abbr -> canonical (ESPN-box / Kalshi-normalized) abbr space.
# Identity for every team not listed (26 of 30 already agree).
PITCH_ABBR_TO_CANON: Dict[str, str] = {
    "CUB": "CHC", "CWS": "CHW", "KAN": "KC", "SDG": "SD",
    "SFO": "SF", "TAM": "TB", "WAS": "WSH", "OAK": "ATH",
}
CANON_TEAMS = frozenset(
    {"ARI", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE", "COL", "DET", "HOU",
     "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY", "PHI", "PIT", "SD",
     "SEA", "SF", "STL", "TB", "TEX", "TOR", "WSH", "ATH"})
VALID_TICKER_ABBRS = CANON_TEAMS | set(iol._KALSHI_TO_ESPN)

_PITCH_COLS = ["home_team", "away_team", "date", "half_inning_label",
               "count_balls", "count_strikes", "pitch_type"]


def _canon(abbr: Any) -> str:
    a = str(abbr or "").strip().upper()
    return PITCH_ABBR_TO_CANON.get(a, a)


def _load_pitch_rows(seasons: Sequence[int], data_dir: Optional[Path]) -> pd.DataFrame:
    d = Path(data_dir) if data_dir is not None else DEFAULT_PITCH_STATES_DIR
    frames = []
    for yr in seasons:
        p = d / ("mlb_pitch_states__%d.parquet" % yr)
        if not p.exists():
            continue
        frames.append(pd.read_parquet(p, columns=_PITCH_COLS))
    if not frames:
        return pd.DataFrame(columns=_PITCH_COLS)
    return pd.concat(frames, ignore_index=True)


def build_team_daily_asof(seasons: Sequence[int] = (2022, 2023, 2024, 2025, 2026),
                          data_dir: Optional[Path] = None) -> pd.DataFrame:
    """Per (canonical pitching team, date): STRICTLY-PRIOR expanding share of
    pitcher-ahead pitches that were breaking, walked forward across ALL *seasons*
    concatenated and date-sorted (see module LEAK AUDIT). Columns: team, date,
    share_asof (NaN on a team's first date on file -- no prior data, never a guess).
    """
    rows = _load_pitch_rows(seasons, data_dir)
    if rows.empty:
        return pd.DataFrame(columns=["team", "date", "share_asof"])
    half = rows["half_inning_label"].astype(str).str.extract(r"^(top|bottom)")
    is_bottom = half[0] == "bottom"
    # top half: away bats, HOME pitches. bottom half: home bats, AWAY pitches.
    pitching_team = np.where(is_bottom, rows["away_team"], rows["home_team"])
    team = pd.Series(pitching_team, index=rows.index).map(_canon)
    date = pd.to_datetime(rows["date"], errors="coerce")
    is_ahead = rows["count_strikes"].astype(float) > rows["count_balls"].astype(float)
    is_breaking = ~rows["pitch_type"].isin(FASTBALL_TYPES)

    daily = pd.DataFrame({"team": team, "date": date, "is_ahead": is_ahead,
                          "is_breaking_ahead": is_ahead & is_breaking})
    daily = daily.dropna(subset=["date"])
    agg = daily.groupby(["team", "date"], as_index=False).agg(
        n_ahead=("is_ahead", "sum"), n_breaking_ahead=("is_breaking_ahead", "sum"))
    agg = agg.sort_values(["team", "date"]).reset_index(drop=True)
    grp = agg.groupby("team")
    prior_ahead = grp["n_ahead"].cumsum() - agg["n_ahead"]
    prior_breaking = grp["n_breaking_ahead"].cumsum() - agg["n_breaking_ahead"]
    agg["share_asof"] = prior_breaking / prior_ahead.replace(0, np.nan)
    return agg[["team", "date", "share_asof"]]


def _lookup(table: Dict[Tuple[str, Any], float], team: str, date: Any) -> Optional[float]:
    v = table.get((team, date))
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return float(v)


def _as_lookup_dict(daily: pd.DataFrame) -> Dict[Tuple[str, Any], float]:
    return {(r.team, r.date): r.share_asof for r in daily.itertuples()}


def attach_composite_train(df: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """TRAIN/VAL rows carry home_team/away_team/date natively. Adds pa_composite
    (home_share_asof - away_share_asof) and has_composite; missing -> 0.0/False."""
    out = df.copy()
    if out.empty:
        out["pa_composite"] = pd.Series(dtype=float)
        out["has_composite"] = pd.Series(dtype=bool)
        return out
    table = _as_lookup_dict(daily)
    dates = pd.to_datetime(out["date"], errors="coerce")
    home_c = out["home_team"].map(_canon)
    away_c = out["away_team"].map(_canon)
    comp, has = [], []
    for h, a, dt in zip(home_c, away_c, dates):
        hs, asr = _lookup(table, h, dt), _lookup(table, a, dt)
        if hs is None or asr is None:
            comp.append(0.0); has.append(False)
        else:
            comp.append(hs - asr); has.append(True)
    out["pa_composite"] = comp
    out["has_composite"] = has
    return out


def attach_composite_eval(ticks: List[Dict[str, Any]], daily: pd.DataFrame) -> List[Dict[str, Any]]:
    """EVAL ticks carry a Kalshi ticker as game_id; parse it for (date, away, home) --
    already canonical (iol._KALSHI_TO_ESPN normalizes AZ/CWS/WSN/SFG/SDP/TBR/KCR/OAK)."""
    table = _as_lookup_dict(daily)
    out = []
    for t in ticks:
        parsed = iol.parse_mlb_ticker(str(t.get("game_id", "")), VALID_TICKER_ABBRS)
        comp, has = 0.0, False
        if parsed is not None:
            date, away, home, _gnum = parsed
            dt = pd.Timestamp(date)
            hs, asr = _lookup(table, home, dt), _lookup(table, away, dt)
            if hs is not None and asr is not None:
                comp, has = hs - asr, True
        out.append(dict(t, pa_composite=comp, has_composite=has))
    return out


def _side3(res: Dict[str, Any]) -> Dict[str, Any]:
    return {"verdict": res["verdict"], "brier_delta_ci95": res["brier_delta_ci95"],
            "mean_abs_gap": res["mean_abs_gap"]}


def combine_row3(name: str, new_res: Dict[str, Any], old_res: Dict[str, Any],
                 v2_res: Dict[str, Any]) -> Dict[str, Any]:
    """3-way bucket row for mlb_winprob_v5.py's build_benchmark (kept here to keep
    the orchestration module <=300 LOC; zero behavior change)."""
    return {"bucket": name, "n_ticks": new_res["n_ticks"], "n_games": new_res["n_games"],
            "new_model": new_res["model"], "old_pooled_model": old_res["model"],
            "v2_state_model": v2_res["model"], "market": new_res["market"],
            "new_vs_market": _side3(new_res), "old_pooled_vs_market": _side3(old_res),
            "v2_state_vs_market": _side3(v2_res)}


__all__ = [
    "DEFAULT_PITCH_STATES_DIR", "PITCH_ABBR_TO_CANON", "CANON_TEAMS",
    "VALID_TICKER_ABBRS", "build_team_daily_asof", "attach_composite_train",
    "attach_composite_eval", "combine_row3",
]
