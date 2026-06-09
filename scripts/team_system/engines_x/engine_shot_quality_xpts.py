"""engine_shot_quality_xpts.py — Shot-zone profile x league zone FG% => xPTS/100 => margin.

METHODOLOGY: Per team, minute-weight player shot-zone frequencies (8 zones: rim, floater,
putback, post, midrange, corner3, catch-shoot-3, pullup-3) from pbp_attributes.parquet
(13-team 2025-26 substrate). Multiply each zone freq by league-average zone FG% * pts/make
=> xPTS/FGA. Scale by FGA/poss from league_team_game => xFGA/100. Add FT contribution
(fta/poss * 0.75 * 100). Blend with opponent's defensive suppression (minute-weighted
intd_fg_suppress + perd_fg3_suppress from attribute_vault, 0-99 percentile).

  margin = (home_adj_xpts100 - away_adj_xpts100) * avg_poss/100 + HCA
  total  = (home_adj_xpts100 + away_adj_xpts100) * avg_poss/100

DATA COVERAGE: pbp_attributes = 13 teams (ATL CLE GSW LAL MIN NOP NYK OKC ORL PHI POR
SAS WAS). 17 missing teams fall back to league-mean xFGA/100 (~93.5 pts, calibrated on
13-team subset) + team-specific FT from lg. Vault defense = all 30 teams.

honesty_class=research. Decorrelation forecast r~0.5-0.7 (partial); fallback dilutes
independence for non-tracked teams. NOT a betting edge; no playoff edge claim.
"""
from __future__ import annotations

import math
import os
from functools import lru_cache
from typing import Optional

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
_TS   = os.path.join(_ROOT, "data", "cache", "team_system")

_PBP_ATTR_PATH = os.path.join(_TS, "pbp_attributes.parquet")
_RATES_PATH    = os.path.join(_TS, "player_rates.parquet")
_VAULT_PATH    = os.path.join(_TS, "attribute_vault.parquet")
_LG_PATH       = os.path.join(_TS, "league_team_game.parquet")

HOME_EDGE: float      = 2.7
MARGIN_SD: float      = 13.5
MIN_MPG: float        = 12.0
_FALLBACK_XFGA100: float = 93.5   # league-mean calibrated on 13-team subset
_FT_MAKE_RATE: float  = 0.75
_DEF_RIM_WT:  float   = 0.60      # blend: rim D weight
_DEF_3PT_WT:  float   = 0.40      # blend: 3pt D weight
_DEF_SCALE:   float   = 0.00286   # per percentile pt from 50; p95 gap => ~10% xPTS swing

_PBP_TEAMS: frozenset = frozenset(
    ["ATL", "CLE", "GSW", "LAL", "MIN", "NOP", "NYK", "OKC", "ORL", "PHI", "POR", "SAS", "WAS"]
)

# (label, freq_col, pct_col, pts_per_make)
_ZONES = [
    ("rim_finish", "rim_finish_freq",    "rim_finish_pct",    2.0),
    ("floater",    "floater_freq",       "floater_pct",       2.0),
    ("putback",    "putback_freq",       "putback_pct",       2.0),
    ("post",       "post_freq",          "post_pct",          2.0),
    ("midrange",   "midrange_freq",      "midrange_pct",      2.0),
    ("corner_3",   "corner_3_freq",      "corner_3_pct",      3.0),
    ("catch_sh3",  "catch_shoot_3_freq", "catch_shoot_3_pct", 3.0),
    ("pullup_3",   "pullup_3_freq",      "pullup_3_pct",      3.0),
]
_N_ZONES = len(_ZONES)


@lru_cache(maxsize=1)
def _build() -> dict:
    """Load parquets; compute team profiles and pace. Cached after first call."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pbp   = pd.read_parquet(_PBP_ATTR_PATH)
        rates = pd.read_parquet(_RATES_PATH)
        vault = pd.read_parquet(_VAULT_PATH)
        lg    = pd.read_parquet(_LG_PATH)

    # League-average zone FG% (from 13-team pbp_attributes subset)
    lg_pct: dict[str, float] = {
        pct_c: float(pbp[pct_c].dropna().mean()) if pbp[pct_c].notna().any() else 0.45
        for _, _, pct_c, _ in _ZONES
    }

    all_teams = sorted(lg["team"].unique().tolist())

    def _xpts100(tri: str):
        """(xfga_100, xft_100, n_players, source_tag, n_signals)"""
        pbp_t   = pbp[pbp["team"] == tri]
        rates_t = rates[(rates["team"] == tri) & (rates["mpg"] >= MIN_MPG)]
        merged  = pbp_t.merge(rates_t[["pid", "mpg"]], on="pid", how="inner")
        lg_t    = lg[lg["team"] == tri]
        fta_pp  = (
            lg_t["fta"].mean() / lg_t["poss"].mean()
            if len(lg_t) > 0 and lg_t["poss"].mean() > 0 else 0.231
        )
        xft_100 = fta_pp * _FT_MAKE_RATE * 100.0

        if len(merged) < 3:
            return _FALLBACK_XFGA100, xft_100, len(merged), "league_mean_fallback", 0

        total_w  = merged["mpg"].sum()
        xfga_raw = 0.0
        n_sig    = 0
        for _, fc, pc, pts in _ZONES:
            w_freq = float((merged[fc].fillna(0.0) * merged["mpg"]).sum() / total_w)
            w_pct  = float((merged[pc].fillna(lg_pct[pc]) * merged["mpg"]).sum() / total_w)
            xfga_raw += w_freq * w_pct * pts
            n_sig    += int(merged[pc].notna().sum())

        fga_pp   = (
            lg_t["fga"].mean() / lg_t["poss"].mean()
            if len(lg_t) > 0 and lg_t["poss"].mean() > 0 else 0.874
        )
        return xfga_raw * fga_pp * 100.0, xft_100, len(merged), "pbp_attributes", n_sig

    def _def_score(tri: str) -> float:
        """Minute-weighted composite defense percentile (50=avg)."""
        rates_t = rates[(rates["team"] == tri) & (rates["mpg"] >= MIN_MPG)]
        vault_t = vault[vault["team"] == tri]
        if len(vault_t) == 0:
            return 50.0
        m = rates_t[["player", "mpg"]].merge(
            vault_t[["player", "intd_fg_suppress", "perd_fg3_suppress"]], on="player", how="inner"
        )
        if len(m) == 0 or m["mpg"].sum() <= 0:
            return 50.0
        comp = m["intd_fg_suppress"].fillna(50.0) * _DEF_RIM_WT + \
               m["perd_fg3_suppress"].fillna(50.0) * _DEF_3PT_WT
        return float((comp * m["mpg"]).sum() / m["mpg"].sum())

    profiles: dict[str, dict] = {}
    for tri in all_teams:
        xfga, xft, n_p, src, n_sig = _xpts100(tri)
        profiles[tri] = {
            "xfga_100":   xfga,
            "xft_100":    xft,
            "xtotal_100": xfga + xft,
            "def_score":  _def_score(tri),
            "n_players":  n_p,
            "source":     src,
            "n_signals":  n_sig,
        }

    return {
        "profiles":        profiles,
        "poss_by_team":    lg.groupby("team")["poss"].mean().to_dict(),
        "league_avg_poss": float(lg["poss"].mean()),
        "all_teams":       all_teams,
    }


def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context: Optional[dict] = None,
) -> dict:
    """Shot-quality xPTS engine. Returns standard 10-key engine dict.

    DATA LIMIT: pbp_attributes covers 13/30 teams; others fall back to league-mean xFGA.
    honesty_class=research; NOT a betting edge.
    """
    ctx     = context or {}
    neutral = bool(ctx.get("neutral_site", False))
    hca     = 0.0 if neutral else HOME_EDGE

    art      = _build()
    profiles = art["profiles"]
    home     = home_tri.upper()
    away     = away_tri.upper()

    if home not in art["all_teams"]:
        raise ValueError(f"Unknown team: {home!r}. Valid: {sorted(art['all_teams'])}")
    if away not in art["all_teams"]:
        raise ValueError(f"Unknown team: {away!r}. Valid: {sorted(art['all_teams'])}")

    h = profiles[home]
    a = profiles[away]

    # Opponent defense score (>50 = better than avg) suppresses offense
    a_def_adj = (a["def_score"] - 50.0) * _DEF_SCALE
    h_def_adj = (h["def_score"] - 50.0) * _DEF_SCALE
    home_adj  = h["xtotal_100"] * (1.0 - a_def_adj)
    away_adj  = a["xtotal_100"] * (1.0 - h_def_adj)

    poss_h   = art["poss_by_team"].get(home, art["league_avg_poss"])
    poss_a   = art["poss_by_team"].get(away, art["league_avg_poss"])
    avg_poss = (poss_h + poss_a) / 2.0

    margin_home = (home_adj - away_adj) * avg_poss / 100.0 + hca
    total       = (home_adj + away_adj) * avg_poss / 100.0
    home_pts    = total / 2.0 + margin_home / 2.0
    away_pts    = total / 2.0 - margin_home / 2.0

    win_prob_home = 0.5 + 0.5 * math.erf(margin_home / (MARGIN_SD * math.sqrt(2.0)))
    win_prob_home = max(0.01, min(0.99, float(win_prob_home)))

    n_models  = _N_ZONES * sum(1 for t in [home, away] if t in _PBP_TEAMS)
    n_signals = h["n_signals"] + a["n_signals"]

    notes = (
        f"shot_quality_xpts: {home}:{h['source']}({h['n_players']}p) | "
        f"{away}:{a['source']}({a['n_players']}p); "
        f"home_xpts100={h['xtotal_100']:.1f}(adj={home_adj:.1f}) "
        f"away_xpts100={a['xtotal_100']:.1f}(adj={away_adj:.1f}); "
        f"def_scores: {home}={h['def_score']:.1f} {away}={a['def_score']:.1f}; "
        f"avg_poss={avg_poss:.1f}; margin={margin_home:+.2f} total={total:.1f}; "
        f"pbp_coverage=13/30 teams (2025-26 partial); fallback=league_mean_xfga; "
        f"honesty=research; no playoff edge claim"
    )

    return {
        "engine":        "shot_quality_xpts",
        "win_prob_home": round(win_prob_home, 4),
        "margin_home":   round(margin_home, 2),
        "total":         round(total, 1),
        "home_pts":      round(home_pts, 2),
        "away_pts":      round(away_pts, 2),
        "margin_sd":     MARGIN_SD,
        "n_models":      n_models,
        "n_signals":     n_signals,
        "notes":         notes,
    }


def _self_test() -> None:
    print("=" * 70)
    print("ENGINE: shot_quality_xpts  --  self-test: NYK (home) vs SAS (away)")
    print("=" * 70)

    result = predict("NYK", "SAS")
    for k in ["engine","win_prob_home","margin_home","total",
               "home_pts","away_pts","margin_sd","n_models","n_signals"]:
        print(f"  {k:<20}: {result[k]}")

    print("\n  Notes:")
    for part in result["notes"].split(";"):
        print(f"    {part.strip()}")

    r_neut = predict("NYK", "SAS", {"neutral_site": True})
    diff   = result["margin_home"] - r_neut["margin_home"]
    print(f"\n  HCA check: default={result['margin_home']:+.2f}  neutral={r_neut['margin_home']:+.2f}  diff={diff:+.2f} (expect ~2.7)")

    required = {"engine","win_prob_home","margin_home","total",
                "home_pts","away_pts","margin_sd","n_models","n_signals","notes"}
    missing  = required - set(result.keys())
    assert not missing, f"Missing keys: {missing}"
    assert abs(result["home_pts"] + result["away_pts"] - result["total"]) < 0.1, "pts sum != total"
    assert abs(result["home_pts"] - result["away_pts"] - result["margin_home"]) < 0.1, "pts diff != margin"
    assert 0.01 <= result["win_prob_home"] <= 0.99
    assert result["margin_sd"] > 0

    r_bkn = predict("NYK", "BKN")
    assert "league_mean_fallback" in r_bkn["notes"], "BKN should use fallback"
    print(f"\n  BKN fallback: margin={r_bkn['margin_home']:+.2f}  source confirmed in notes")

    print("\nSelf-test PASSED")


if __name__ == "__main__":
    _self_test()
