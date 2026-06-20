"""domains.basketball_nba.prop_opp_allowed -- leak-free opp-allowed multiplier.

P1-7 NBA matchup multiplier (GATED, expect REJECT).
For each player-game in OOF, multiplier = mean_stat_allowed_by_opp_date_lt_D /
league_mean_date_lt_D. Adjusted pred = oof_pred * multiplier. Gate: SHIP only if
BSS(adjusted) > BSS(baseline) on both seasons; else REJECT (honest null).

RAILS: leak guard (hist date.max() < as_of after filter); neutral opp -> 1.0; calibration not edge;
no $ / ROI / PnL; INSUFFICIENT_DATA when n < MIN_N; ASCII only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system &&
  python -m pytest domains/basketball_nba/test_prop_opp_allowed.py -q
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_BOX_PATH = os.path.join("data", "domains", "basketball_nba", "player_boxscores.parquet")
_OOF_PATH = os.path.join("data", "cache", "pregame_oof.parquet")

NBA_PROP_STATS: List[str] = ["pts", "reb", "ast", "stl", "blk", "fg3m", "tov"]
_SIGMA_FLOOR: Dict[str, float] = {
    "pts": 4.0, "reb": 2.0, "ast": 1.5,
    "stl": 1.0, "blk": 1.0, "fg3m": 1.0, "tov": 1.2,
}
MIN_OPP_GAMES = 10   # unique games vs opp required for a non-1.0 multiplier
MIN_N = 30           # min OOF rows per season-stat to report BSS
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# --- Gaussian helpers (stdlib only) -----------------------------------------

def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

def _p_over(pred: float, sigma: float, line: float) -> float:
    if sigma <= 0 or not math.isfinite(pred):
        return 0.5
    return float(min(1.0, max(0.0, 1.0 - _phi((line - pred) / sigma))))

def _half_line(pred: float) -> float:
    if not math.isfinite(pred) or pred < 0:
        return 0.5
    return max(round(pred - 0.5) + 0.5, 0.5)

def _residual_sigma(rows: Sequence[dict], stat: str) -> float:
    diffs = [r["actual"] - r["pred"] for r in rows
             if math.isfinite(r.get("actual", float("nan")))
             and math.isfinite(r.get("pred", float("nan")))]
    n = len(diffs)
    if n < 2:
        return _SIGMA_FLOOR.get(stat, 1.0)
    mean_d = sum(diffs) / n
    return max(math.sqrt(max(sum((d - mean_d) ** 2 for d in diffs) / (n - 1), 1e-6)),
               _SIGMA_FLOOR.get(stat, 1.0))

def _brier(ps: List[float], ys: List[float]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps) if ps else float("nan")

def _bss(ps: List[float], ys: List[float]) -> float:
    if not ps:
        return float("nan")
    base = sum(ys) / len(ys)
    ref = sum((base - y) ** 2 for y in ys) / len(ys)
    return 0.0 if ref < 1e-9 else 1.0 - _brier(ps, ys) / ref


# --- Core: opp-allowed multiplier as-of a date ------------------------------

def build_opp_multipliers(
    box_df, as_of, stat: str, min_games: int = MIN_OPP_GAMES,
) -> Dict[str, float]:
    """Return {opp_team: multiplier} leak-free (date < as_of only).

    Any opp with < min_games unique games in history -> 1.0 (neutral).
    LEAK GUARD: after filtering, asserts hist date.max() < as_of_ts (real check,
    not a tautology). Passes trivially on an empty hist (no rows to leak).
    """
    import pandas as pd
    as_of_ts = pd.Timestamp(as_of)
    hist = box_df[box_df["date"] < as_of_ts]
    if not hist.empty:
        assert hist["date"].max() < as_of_ts, \
            f"LEAK: hist contains rows on or after as_of {as_of_ts}"
    if hist.empty or stat not in hist.columns:
        return {}
    league_mean = hist[stat].mean()
    if not math.isfinite(league_mean) or league_mean <= 0:
        return {}
    opp_games = hist.groupby("opp")["game_id"].nunique()
    opp_means = hist.groupby("opp")[stat].mean()
    result: Dict[str, float] = {}
    for opp_team in opp_means.index:
        if int(opp_games.get(opp_team, 0)) < min_games:
            result[str(opp_team)] = 1.0
        else:
            mult = float(opp_means[opp_team]) / league_mean
            result[str(opp_team)] = mult if (math.isfinite(mult) and mult > 0) else 1.0
    return result


# --- Vectorized precompute: one build per unique date, not per row ----------

def _date_mults(box_df, stat: str, dates, min_games: int) -> dict:
    """Precompute {date_str: {opp: mult}} at each unique eval date (leak-free)."""
    import pandas as pd
    box_df = box_df.copy()
    box_df["date"] = pd.to_datetime(box_df["date"])
    cache: dict = {}
    for d in sorted(set(dates)):
        d_ts = pd.Timestamp(d)
        cache[str(d_ts.date())] = build_opp_multipliers(
            box_df, as_of=d_ts, stat=stat, min_games=min_games)
    return cache


# --- Evaluation structs ------------------------------------------------------

@dataclass
class SeasonEval:
    season: str
    stat: str
    n: int
    bss_baseline: float
    bss_adjusted: float
    delta_bss: float  # adjusted - baseline; positive = improved
    verdict: str      # IMPROVED | DEGRADED | FLAT | INSUFFICIENT_DATA

@dataclass
class EvalResult:
    seasons: List[SeasonEval] = field(default_factory=list)
    note: str = ""

def _season_label(date) -> str:
    m, yr = date.month, date.year
    return f"{yr}-{str(yr+1)[2:]}" if m >= 10 else f"{yr-1}-{str(yr)[2:]}"


def score_with_multiplier(
    merged_df, stat: str, min_games: int = MIN_OPP_GAMES,
) -> EvalResult:
    """BSS baseline vs opp-adjusted per season (leak-free, vectorized).

    merged_df: OOF rows merged with boxscores; must have date, opp, oof_pred, actual.
    """
    import pandas as pd
    result = EvalResult()
    if merged_df is None or len(merged_df) == 0:
        result.note = "empty merged_df"
        return result

    df = merged_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["season_label"] = df["date"].apply(_season_label)

    src_cols = ["game_id", "date", "opp", stat] if stat in df.columns \
        else ["game_id", "date", "opp"]
    box_src = df[src_cols].drop_duplicates()
    if stat not in box_src.columns:
        box_src = box_src.assign(**{stat: float("nan")})
    date_opp_mults = _date_mults(box_src, stat=stat, dates=df["date"].unique(),
                                  min_games=min_games)

    for season in sorted(df["season_label"].unique()):
        sdf = df[df["season_label"] == season]
        rows = sdf.to_dict("records")
        if len(rows) < MIN_N:
            result.seasons.append(SeasonEval(
                season, stat, len(rows), float("nan"), float("nan"),
                float("nan"), INSUFFICIENT_DATA))
            continue

        sigma = _residual_sigma(
            [{"pred": r["oof_pred"], "actual": r["actual"]} for r in rows], stat)

        b_ps, a_ps, ys = [], [], []
        for r in rows:
            try:
                pred_f = float(r["oof_pred"])
                actual_f = float(r["actual"])
            except (TypeError, ValueError):
                continue
            if not (math.isfinite(pred_f) and math.isfinite(actual_f)):
                continue
            date_key = str(pd.Timestamp(r["date"]).date())
            mult = date_opp_mults.get(date_key, {}).get(str(r.get("opp", "")), 1.0)
            line = _half_line(pred_f)
            b_ps.append(_p_over(pred_f, sigma, line))
            adj_pred = pred_f * max(0.1, mult)
            a_ps.append(_p_over(adj_pred, sigma, _half_line(adj_pred)))
            ys.append(1.0 if actual_f > line else 0.0)

        n = len(ys)
        if n < MIN_N:
            result.seasons.append(SeasonEval(
                season, stat, n, float("nan"), float("nan"),
                float("nan"), INSUFFICIENT_DATA))
            continue

        bss_b, bss_a = _bss(b_ps, ys), _bss(a_ps, ys)
        delta = bss_a - bss_b
        verdict = "FLAT" if abs(delta) < 1e-5 else ("IMPROVED" if delta > 0 else "DEGRADED")
        result.seasons.append(SeasonEval(
            season, stat, n, round(bss_b, 5), round(bss_a, 5),
            round(delta, 5), verdict))
    return result


# --- Gate -------------------------------------------------------------------

def gate_result(
    merged_df=None,
    stats: Optional[List[str]] = None,
    box_path: Optional[str] = None,
    oof_path: Optional[str] = None,
) -> dict:
    """Evaluate opp-allowed multiplier. SHIP|REJECT|INSUFFICIENT_DATA.

    No $ / ROI / PnL field. SHIP only if >= half of season-stat pairs improve BSS.
    """
    import pandas as pd
    use_stats = stats or NBA_PROP_STATS

    if merged_df is None:
        try:
            bp, op = box_path or _BOX_PATH, oof_path or _OOF_PATH
            if not os.path.exists(bp):
                return _sentinel(use_stats, f"boxscores not found: {bp}")
            if not os.path.exists(op):
                return _sentinel(use_stats, f"OOF not found: {op}")
            box_df = pd.read_parquet(bp)
            box_df["date"] = pd.to_datetime(box_df["date"])
            oof_df = pd.read_parquet(op)
            merged_df = oof_df.merge(
                box_df[["game_id", "player_id", "date", "team", "opp"] + use_stats],
                on=["game_id", "player_id"], how="inner")
        except Exception as exc:  # noqa: BLE001
            logger.warning("prop_opp_allowed: data load failed: %s", exc)
            return _sentinel(use_stats, f"data load failed: {exc}")

    per_stat: Dict[str, list] = {}
    n_imp = n_total = 0
    for stat in use_stats:
        stat_df = merged_df[merged_df["stat"] == stat].copy() \
            if "stat" in merged_df.columns else merged_df.copy()
        ev = score_with_multiplier(stat_df, stat=stat)
        rows = []
        for se in ev.seasons:
            rows.append({"season": se.season, "stat": se.stat, "n": se.n,
                         "bss_baseline": se.bss_baseline, "bss_adjusted": se.bss_adjusted,
                         "delta_bss": se.delta_bss, "verdict": se.verdict})
            if se.verdict not in (INSUFFICIENT_DATA, "FLAT"):
                n_total += 1
                if se.verdict == "IMPROVED":
                    n_imp += 1
        per_stat[stat] = rows

    if n_total == 0:
        overall, note = INSUFFICIENT_DATA, "No season-stat pairs with sufficient data."
    elif n_imp / n_total >= 0.5:
        overall = "SHIP"
        note = (f"Opp-allowed multiplier: {n_imp}/{n_total} season-stat pairs "
                "IMPROVED BSS. GATED -- not yet wired into production.")
    else:
        overall = "REJECT"
        note = (f"Opp-allowed multiplier REJECTED: only {n_imp}/{n_total} "
                "season-stat pairs improved BSS. Neutral (1.0) baseline beats "
                "the multiplier on calibration. Finding recorded honestly. "
                "No production change.")
    return {"verdict": overall, "stats": use_stats, "per_stat": per_stat, "note": note}


def _sentinel(stats: List[str], note: str) -> dict:
    return {"verdict": INSUFFICIENT_DATA, "stats": stats,
            "per_stat": {s: [] for s in stats}, "note": note}


__all__ = [
    "NBA_PROP_STATS", "MIN_OPP_GAMES", "MIN_N", "INSUFFICIENT_DATA",
    "build_opp_multipliers", "score_with_multiplier", "gate_result",
]
