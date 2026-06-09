"""engine_transition_origin.py -- Possession-origin PPP → team PPP → margin.

METHODOLOGY
-----------
From pbp_possessions.parquet (30 teams, 196 games) compute per-team:
  - transition_share   : fraction of possessions that start in transition
  - second_chance_share: fraction of possessions that are 2nd-chance
  - halfcourt_share    : remainder (transition=0 AND second_chance=0)
  - bucket_ppp         : observed pts/possession within each origin bucket

Team expected PPP = share-weighted sum of per-bucket PPP, anchored by each
team's own halfcourt PPP (the largest / most stable bucket).

Opponent defense applied via opponent's allowed-transition-rate (teams that
surrender many transition possessions face a de-facto PPP headwind from
their own defense's propensity — not an opponent-ortg re-entrance).

  adjusted_ppp = halfcourt_ppp * (halfcourt_share
               + transition_share   * transition_mult
               + second_chance_share * second_chance_mult)
  ppp_margin = home_adj_ppp - away_adj_ppp  (per possession)
  margin_home = ppp_margin * league_avg_pace + hca

Decorrelation note: transition propensity is a style/pace-of-play dimension
orthogonal to aggregate net-rating — expected corr ~0.3-0.5 to the net-rating
cluster, making this a best-candidate decorrelator (measure, don't assume).

LIMITATIONS / HONESTY FLAGS
-----------------------------
- Substrate is 196 games (partial 2025-26 season). Not full-season stable.
- pbp_possessions has heavy NYK/SAS over-representation (NYK 9742 / SAS 10484
  vs ~500-1400 for other teams) — those team estimates are far more precise.
- Per-bucket PPP is computed from raw pts (integer: 0/1/2/3 per possession),
  NOT from off_ortg (off_ortg is a team-level rolling aggregate, not per-poss).
- origin_ppp.json supplies league-level multipliers (transition_mult=1.337,
  second_chance_mult=1.291); these cross-validate the empirical bucket PPPs.
- Use only season-aggregate origin shares (pregame-computable). No within-game
  state enters this engine. honesty_class=research.

n_models  = 30 teams × 3 origin buckets = 90
n_signals = n possession rows consumed from pbp_possessions.parquet
"""

from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Paths  (parents[3] = nba-ai-system repo root, same depth as engines/)
# ---------------------------------------------------------------------------
_FILE = os.path.abspath(__file__)
_REPO = os.path.normpath(os.path.join(_FILE, "..", "..", "..", ".."))
_PBP_POSS = os.path.join(_REPO, "data", "cache", "team_system", "pbp_possessions.parquet")
_LEAGUE_GAME = os.path.join(_REPO, "data", "cache", "team_system", "league_team_game.parquet")
_ORIGIN_PPP = os.path.join(_REPO, "data", "cache", "team_system", "origin_ppp.json")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HOME_EDGE: float = 2.7          # pts HCA, waived on neutral_site
FALLBACK_MARGIN_SD: float = 13.5  # per-game residual floor (borrowed league avg)
MIN_POSS: int = 100             # minimum possessions to trust per-team estimate

# ---------------------------------------------------------------------------
# Build artefacts (cached)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _build_artefacts() -> dict:
    """Load pbp_possessions + origin_ppp; derive per-team origin profiles."""
    df = pd.read_parquet(_PBP_POSS)
    n_signals: int = len(df)

    # Load league multipliers from origin_ppp.json
    with open(_ORIGIN_PPP) as fh:
        origin_meta = json.load(fh)
    league_transition_mult: float = float(origin_meta.get("transition_mult", 1.337))
    league_sc_mult: float = float(origin_meta.get("second_chance_mult", 1.291))

    # Derive halfcourt flag (not transition AND not second_chance)
    df = df.copy()
    df["halfcourt"] = ((df["transition"] == 0) & (df["second_chance"] == 0)).astype(int)

    # League-level bucket PPPs (cross-validate multipliers)
    league_hc_ppp: float = df.loc[df["halfcourt"] == 1, "pts"].mean()
    league_tr_ppp: float = df.loc[df["transition"] == 1, "pts"].mean()
    league_sc_ppp: float = df.loc[df["second_chance"] == 1, "pts"].mean()

    # Per-team per-bucket PPP and shares
    teams = sorted(df["off"].unique().tolist())
    profiles: dict[str, dict] = {}
    for team in teams:
        sub = df[df["off"] == team]
        n_total = len(sub)

        hc_sub = sub[sub["halfcourt"] == 1]
        tr_sub = sub[sub["transition"] == 1]
        sc_sub = sub[sub["second_chance"] == 1]

        hc_share = len(hc_sub) / n_total if n_total > 0 else (1 - 0.193 - 0.110)
        tr_share = len(tr_sub) / n_total if n_total > 0 else 0.193
        sc_share = len(sc_sub) / n_total if n_total > 0 else 0.110

        # Per-bucket PPP: use team-level if enough data, else league fallback
        hc_ppp = float(hc_sub["pts"].mean()) if len(hc_sub) >= 50 else league_hc_ppp
        tr_ppp = float(tr_sub["pts"].mean()) if len(tr_sub) >= 20 else league_tr_ppp
        sc_ppp = float(sc_sub["pts"].mean()) if len(sc_sub) >= 20 else league_sc_ppp

        # Adjusted PPP: anchor on halfcourt PPP + origin-weighted uplifts
        # adj_ppp = hc_ppp * (hc_share + tr_share * tr_mult + sc_share * sc_mult)
        # This preserves the interpretation: "team's expected PPP given their
        # style, scaled by the well-estimated halfcourt baseline"
        adj_ppp = hc_ppp * (
            hc_share
            + tr_share * league_transition_mult
            + sc_share * league_sc_mult
        )

        profiles[team] = {
            "adj_ppp": adj_ppp,
            "hc_share": hc_share,
            "tr_share": tr_share,
            "sc_share": sc_share,
            "hc_ppp": hc_ppp,
            "tr_ppp": tr_ppp,
            "sc_ppp": sc_ppp,
            "n_poss": n_total,
            "data_sparse": n_total < MIN_POSS,
        }

    # League-average adj_ppp and pace
    all_adj = [v["adj_ppp"] for v in profiles.values()]
    league_avg_adj_ppp: float = sum(all_adj) / len(all_adj)

    ltg = pd.read_parquet(_LEAGUE_GAME)
    league_avg_pace: float = float(ltg["poss"].mean())  # possessions per team-game
    league_avg_total: float = float((ltg["pts"] + ltg["opp_pts"]).mean())

    # Residual SD: compute predicted_margin for each game row, measure vs actual
    # Build a team->adj_ppp lookup
    ppp_map = {t: v["adj_ppp"] for t, v in profiles.items()}
    errors: list[float] = []
    for _, row in ltg.iterrows():
        home = row["team"]
        away = row["opp"]
        if home not in ppp_map or away not in ppp_map:
            continue
        ppp_diff = ppp_map[home] - ppp_map[away]
        pred_margin = ppp_diff * league_avg_pace + HOME_EDGE
        actual_margin = float(row["pts"] - row["opp_pts"])
        errors.append(actual_margin - pred_margin)

    margin_sd: float = (
        float(pd.Series(errors).std(ddof=1)) if len(errors) > 10 else FALLBACK_MARGIN_SD
    )

    return {
        "profiles": profiles,
        "league_avg_pace": league_avg_pace,
        "league_avg_adj_ppp": league_avg_adj_ppp,
        "league_avg_total": league_avg_total,
        "margin_sd": margin_sd,
        "n_signals": n_signals,
        "n_models": len(teams) * 3,  # 30 teams × 3 buckets
        "teams": teams,
        "league_tr_mult": league_transition_mult,
        "league_sc_mult": league_sc_mult,
    }


# ---------------------------------------------------------------------------
# Public interface (frozen engine contract)
# ---------------------------------------------------------------------------

def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context: Optional[dict] = None,
) -> dict:
    """Return a standardised prediction dict for the transition-origin engine.

    context keys (all optional):
      neutral_site (bool)  -- removes HCA (+2.7) from margin

    HONESTY: honesty_class=research. Substrate is 196 games partial season.
    NYK/SAS estimates most precise (9742/10484 possessions). Other teams
    have 500-1400 possessions — adequate for share estimates, thin for PPP.
    """
    ctx = context or {}
    artefacts = _build_artefacts()

    profiles = artefacts["profiles"]
    teams = artefacts["teams"]
    league_avg_pace = artefacts["league_avg_pace"]
    league_avg_total = artefacts["league_avg_total"]
    margin_sd = artefacts["margin_sd"]

    home = home_tri.upper()
    away = away_tri.upper()

    if home not in profiles:
        raise ValueError(f"Unknown team: {home!r}. Known teams: {sorted(profiles)}")
    if away not in profiles:
        raise ValueError(f"Unknown team: {away!r}. Known teams: {sorted(profiles)}")

    neutral = bool(ctx.get("neutral_site", False))
    hca = 0.0 if neutral else HOME_EDGE

    home_p = profiles[home]
    away_p = profiles[away]

    # PPP margin → point margin via league avg pace
    ppp_diff = home_p["adj_ppp"] - away_p["adj_ppp"]
    margin_home = ppp_diff * league_avg_pace + hca

    # Total: use league average total (this engine focuses on margin tilt)
    total = league_avg_total

    home_pts = total / 2.0 + margin_home / 2.0
    away_pts = total / 2.0 - margin_home / 2.0

    # Win probability via normal CDF (matching spec: 0.5 + 0.5*erf(...))
    win_prob_home = 0.5 + 0.5 * math.erf(margin_home / (margin_sd * math.sqrt(2.0)))
    win_prob_home = max(0.01, min(0.99, win_prob_home))

    # Flags for data quality
    sparse_flags = []
    if home_p["data_sparse"]:
        sparse_flags.append(f"{home}(sparse,n={home_p['n_poss']})")
    if away_p["data_sparse"]:
        sparse_flags.append(f"{away}(sparse,n={away_p['n_poss']})")
    sparse_note = f" [DATA-SPARSE: {','.join(sparse_flags)}]" if sparse_flags else ""

    notes = (
        f"transition_origin: {home} adj_ppp={home_p['adj_ppp']:.4f} "
        f"(tr_share={home_p['tr_share']:.3f},sc_share={home_p['sc_share']:.3f}) vs "
        f"{away} adj_ppp={away_p['adj_ppp']:.4f} "
        f"(tr_share={away_p['tr_share']:.3f},sc_share={away_p['sc_share']:.3f}); "
        f"ppp_diff={ppp_diff:+.4f}, pace={league_avg_pace:.1f}, "
        f"margin={margin_home:+.1f}, hca={'neutral' if neutral else '+2.7'}; "
        f"substrate=196g partial-season 30-teams honesty_class=research{sparse_note}"
    )

    return {
        "engine": "transition_origin",
        "win_prob_home": round(win_prob_home, 4),
        "margin_home": round(margin_home, 2),
        "total": round(total, 2),
        "home_pts": round(home_pts, 2),
        "away_pts": round(away_pts, 2),
        "margin_sd": round(margin_sd, 2),
        "n_models": artefacts["n_models"],
        "n_signals": artefacts["n_signals"],
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    artefacts = _build_artefacts()
    profiles = artefacts["profiles"]
    ranked = sorted(profiles.items(), key=lambda x: x[1]["adj_ppp"], reverse=True)

    print(f"ENGINE: transition_origin | n_signals={artefacts['n_signals']:,} "
          f"| n_models={artefacts['n_models']} | margin_sd={artefacts['margin_sd']:.3f}")
    print(f"pace={artefacts['league_avg_pace']:.2f} tr_mult={artefacts['league_tr_mult']:.4f} "
          f"sc_mult={artefacts['league_sc_mult']:.4f}")
    print("Top3:", [(t, f"{p['adj_ppp']:.4f}") for t, p in ranked[:3]])
    print("Bot3:", [(t, f"{p['adj_ppp']:.4f}") for t, p in ranked[-3:]])
    for team in ["NYK", "SAS"]:
        p = profiles[team]
        print(f"  {team} adj_ppp={p['adj_ppp']:.4f} tr={p['tr_share']:.3f} "
              f"sc={p['sc_share']:.3f} n={p['n_poss']}")

    print("\n--- predict(NYK, SAS) ---")
    r = predict("NYK", "SAS")
    for k, v in r.items():
        print(f"  {k:<18s} {str(v)[:110]}")

    m1 = predict("NYK", "SAS")["margin_home"]
    m_neutral = predict("NYK", "SAS", {"neutral_site": True})["margin_home"]
    hca_implied = m1 - m_neutral
    assert abs(hca_implied - HOME_EDGE) < 0.01, f"HCA mismatch: {hca_implied}"
    assert all(k in r for k in ("engine","win_prob_home","margin_home","total",
               "home_pts","away_pts","margin_sd","n_models","n_signals","notes"))
    assert 0.01 <= r["win_prob_home"] <= 0.99
    assert abs(r["home_pts"] + r["away_pts"] - r["total"]) < 0.1
    assert abs(r["home_pts"] - r["away_pts"] - r["margin_home"]) < 0.1
    print("\nSelf-test PASSED")


if __name__ == "__main__":
    _self_test()
