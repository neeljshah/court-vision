"""
build_matchup_outcome.py
========================
TEAM-vs-TEAM expected-OUTCOME matchup matrix for 2025-26 (SCOUTING ONLY).

For every one of the 30x30 ordered team pairings (HOME_AWAY) compute the
expected point margin, expected combined total, and the home win probability on
a neutral schedule, plus a quantified STYLE-INTERACTION analysis: do two
high-total teams overshoot the simple additive total prediction (pace / scoring
amplification), and do mismatch games (one high-total + one low-total team)
settle toward the middle?

This is an expected-outcome SCOUTING grid, NOT a betting model. Game lines were
REJECTED as a betting edge in this repo (a sibling agent found full-season-total
features leak in-sample and collapse out-of-sample, and game-line ROI was
negative -3.84% / -8.83% on real closes). The grid is for matchup scouting
("how lopsided is this pairing, how high-scoring an environment") and explicitly
should not be staked.

Method
------
(1) Expected margin (neutral schedule, home venue):
        exp_margin = home_SRS - away_SRS + HOME_COURT
    where home_SRS / away_SRS are the opponent-adjusted SRS ratings from
    team_strength.json and HOME_COURT = +1.73 (league home-court constant).
    exp_home_winprob = 1 / (1 + exp(-k * exp_margin)) with the fitted league k.

(2) Expected total. Each team carries a TOTAL TENDENCY = (its avg game total -
    league baseline) -- a scoring-environment lean that bundles pace and
    efficiency (true possession-pace is null in the source for 2025-26, so the
    game-total lean is the available style axis). The naive additive prediction
    for a pairing is:
        add_total = league_baseline + home_tend + away_tend
    We then fit, on the 1230 actual 2025-26 regular-season games, a regression of
    the ACTUAL game total on the two teams' tendencies plus their INTERACTION:
        total ~ b0 + b1*(home_tend + away_tend) + b2*(home_tend * away_tend)
    b2 is the pace/scoring-amplification coefficient. b2>0 => super-additive (two
    fast teams overshoot the sum; two slow teams undershoot -- the product is
    positive in both cases, so a positive b2 lifts both same-lean pairings and
    means mismatches sit lower than the same-lean extreme). The fitted model
    (not the naive sum) produces exp_total for every pairing.

(3) Surface the most lopsided expected matchups and the highest / lowest
    expected-total matchups.

Leak-safety
-----------
The style-interaction regression is DESCRIPTIVE: it is fit on full-season actual
totals to characterise how this season's games unfolded, and is used only to
build a neutral scouting grid -- it is never used as a forward-looking, bet-
against-the-market predictor (the game_control leak note documents that using a
full-season total predictively is a leakage trap). SRS and the team tendencies
are full-season aggregates; the grid is an as-of-season-end scouting summary, not
a pregame signal. Playoffs (game_id prefix 00425) are excluded; 2025-26 regular
season only.

Output: data/cache/intel_outcome/team_matchup_outcome.json
"""

import json
import pathlib
from datetime import date

import numpy as np

# -- Paths --------------------------------------------------------------------
ROOT = pathlib.Path("C:/Users/neelj/nba-ai-system")
INTEL = ROOT / "data/cache/intel_outcome"
OUT_PATH = INTEL / "team_matchup_outcome.json"

STRENGTH_PATH = INTEL / "team_strength.json"
GAME_CONTROL_PATH = INTEL / "game_control.json"
SCHED_PATH = INTEL / "team_schedule_spots.json"
SEASON_GAMES_PATH = ROOT / "data/nba/season_games_2025-26.json"
LINESCORES_PATH = ROOT / "data/nba/linescores_all.json"

SEASON = "2025-26"
REG_PREFIX = "00225"  # 2025-26 regular season game_id prefix


def _load_json(p: pathlib.Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    strength = _load_json(STRENGTH_PATH)
    gctrl = _load_json(GAME_CONTROL_PATH)
    sched = _load_json(SCHED_PATH)
    season_games = _load_json(SEASON_GAMES_PATH)
    linescores = _load_json(LINESCORES_PATH)

    league = strength["league"]
    home_court = float(league["home_court_margin_pts"])         # +1.73
    logistic_k = float(league["logistic_k"])                    # 0.1153
    league_total = float(league["avg_game_total_pts"])          # 231.21

    teams_strength = strength["teams"]
    teams_gctrl = gctrl["teams"]
    teams_sched = sched.get("teams", {})

    tris = sorted(teams_strength.keys())
    assert len(tris) == 30, f"expected 30 teams, got {len(tris)}"

    # -- Per-team scouting fields --------------------------------------------
    # SRS (opponent-adjusted neutral-floor margin vs avg team)
    srs = {t: float(teams_strength[t]["srs_rating"]) for t in tris}
    full_name = {t: teams_strength[t].get("full_name", t) for t in tris}
    record = {t: (int(teams_strength[t]["wins"]), int(teams_strength[t]["losses"])) for t in tris}

    # TOTAL TENDENCY: team avg game total minus league baseline (scoring-environment lean).
    # Prefer game_control's descriptive total_vs_league (computed off linescores incl. OT);
    # fall back to team_strength.game_total_vs_league. These agree closely.
    total_tend = {}
    for t in tris:
        gc = teams_gctrl.get(t, {})
        v = gc.get("total_vs_league_desc")
        if v is None:
            v = teams_strength[t].get("game_total_vs_league")
        total_tend[t] = float(v) if v is not None else 0.0

    # variance / blowout profile (scouting color on how "settled" a team's games are)
    blow = {t: float(teams_gctrl.get(t, {}).get("blowout_win_pct", 0.0)
                     + teams_gctrl.get(t, {}).get("blowout_loss_pct", 0.0)) for t in tris}
    close = {t: float(teams_gctrl.get(t, {}).get("close_game_rate", 0.0)) for t in tris}
    b2b_fade = {t: float(teams_sched.get(t, {}).get("b2b_margin_delta", 0.0)) for t in tris}

    # -- (2) STYLE-INTERACTION REGRESSION on actual 2025-26 games -------------
    # Build per-game (home_tend, away_tend, actual_total) from season_games + linescores.
    rows = season_games.get("rows", season_games if isinstance(season_games, list) else [])
    X_sum, X_prod, y_total = [], [], []
    n_join = 0
    n_ot = 0
    for r in rows:
        gid = r.get("game_id", "")
        if not gid.startswith(REG_PREFIX):
            continue  # regular season only (excludes 00425 playoffs)
        ht, at = r.get("home_team"), r.get("away_team")
        if ht not in total_tend or at not in total_tend:
            continue
        ls = linescores.get(gid)
        if not ls or ls.get("home_q1") is None or ls.get("away_q1") is None:
            continue
        home_pts = sum(float(ls.get(f"home_q{q}", 0) or 0) for q in (1, 2, 3, 4))
        away_pts = sum(float(ls.get(f"away_q{q}", 0) or 0) for q in (1, 2, 3, 4))
        home_pts += float(ls.get("home_pts_ot", 0) or 0)
        away_pts += float(ls.get("away_pts_ot", 0) or 0)
        if ls.get("had_ot"):
            n_ot += 1
        tot = home_pts + away_pts
        if tot <= 0:
            continue
        n_join += 1
        hth, att = total_tend[ht], total_tend[at]
        X_sum.append(hth + att)
        X_prod.append(hth * att)
        y_total.append(tot)

    X_sum = np.asarray(X_sum, float)
    X_prod = np.asarray(X_prod, float)
    y_total = np.asarray(y_total, float)

    # OLS: total ~ b0 + b1*sum + b2*prod
    A = np.column_stack([np.ones_like(X_sum), X_sum, X_prod])
    coef, *_ = np.linalg.lstsq(A, y_total, rcond=None)
    b0, b1, b2 = (float(c) for c in coef)
    yhat = A @ coef
    resid = y_total - yhat
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y_total - y_total.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    rmse = float(np.sqrt(np.mean(resid ** 2)))

    # Standard error of b2 (interaction) for significance read
    n_obs = len(y_total)
    dof = n_obs - 3
    sigma2 = ss_res / dof if dof > 0 else float("nan")
    cov = sigma2 * np.linalg.inv(A.T @ A)
    se = np.sqrt(np.diag(cov))
    se_b1, se_b2 = float(se[1]), float(se[2])
    t_b2 = b2 / se_b2 if se_b2 > 0 else float("nan")

    # Naive additive model (b2 forced to 0) for comparison: total ~ c0 + c1*sum
    A2 = np.column_stack([np.ones_like(X_sum), X_sum])
    coef2, *_ = np.linalg.lstsq(A2, y_total, rcond=None)
    c0, c1 = float(coef2[0]), float(coef2[1])
    yhat2 = A2 @ coef2
    r2_add = 1.0 - float(np.sum((y_total - yhat2) ** 2)) / ss_tot if ss_tot > 0 else 0.0

    # Mismatch settling: average total in same-lean (prod>0) vs mismatch (prod<0) games,
    # each net of the additive sum effect, to show where mismatches sit.
    prod = X_prod
    same_lean = prod > 0
    mismatch = prod < 0
    # residual of total vs the SUM-only model => what the interaction term is explaining
    resid_add = y_total - yhat2
    same_resid = float(resid_add[same_lean].mean()) if same_lean.any() else 0.0
    mismatch_resid = float(resid_add[mismatch].mean()) if mismatch.any() else 0.0

    def model_total(hth: float, att: float) -> float:
        return b0 + b1 * (hth + att) + b2 * (hth * att)

    def expit(x: float) -> float:
        return 1.0 / (1.0 + np.exp(-x))

    # -- (1)+(2) Build the 30x30 grid ----------------------------------------
    pairings = {}
    for h in tris:
        for a in tris:
            if h == a:
                continue
            exp_margin = srs[h] - srs[a] + home_court
            exp_total = model_total(total_tend[h], total_tend[a])
            add_total = league_total + total_tend[h] + total_tend[a]
            wp = float(expit(logistic_k * exp_margin))
            pairings[f"{h}_{a}"] = {
                "home": h,
                "away": a,
                "exp_margin": round(exp_margin, 2),
                "exp_total": round(exp_total, 1),
                "additive_total": round(add_total, 1),
                "amplification_pts": round(exp_total - add_total, 1),
                "exp_home_winprob": round(wp, 4),
                "home_srs": round(srs[h], 2),
                "away_srs": round(srs[a], 2),
            }

    # -- (3) Extremes ---------------------------------------------------------
    pl = list(pairings.values())

    # Most lopsided = largest |exp_margin| (home blowouts dominate due to +HCA;
    # report by absolute expected margin so both directions surface).
    by_margin = sorted(pl, key=lambda d: abs(d["exp_margin"]), reverse=True)
    biggest_mismatches = [
        {
            "matchup": f"{d['home']} (home) vs {d['away']}",
            "home": d["home"], "away": d["away"],
            "exp_margin": d["exp_margin"],
            "exp_home_winprob": d["exp_home_winprob"],
            "exp_total": d["exp_total"],
        }
        for d in by_margin[:10]
    ]

    by_total_hi = sorted(pl, key=lambda d: d["exp_total"], reverse=True)
    by_total_lo = sorted(pl, key=lambda d: d["exp_total"])
    highest_total_matchups = [
        {"matchup": f"{d['home']} vs {d['away']}", "home": d["home"], "away": d["away"],
         "exp_total": d["exp_total"], "additive_total": d["additive_total"],
         "amplification_pts": d["amplification_pts"], "exp_margin": d["exp_margin"]}
        for d in by_total_hi[:10]
    ]
    lowest_total_matchups = [
        {"matchup": f"{d['home']} vs {d['away']}", "home": d["home"], "away": d["away"],
         "exp_total": d["exp_total"], "additive_total": d["additive_total"],
         "amplification_pts": d["amplification_pts"], "exp_margin": d["exp_margin"]}
        for d in by_total_lo[:10]
    ]

    # Per-team summary table (scouting card)
    team_cards = {}
    srs_rank = {t: i + 1 for i, t in enumerate(sorted(tris, key=lambda x: srs[x], reverse=True))}
    for t in tris:
        team_cards[t] = {
            "full_name": full_name[t],
            "record": f"{record[t][0]}-{record[t][1]}",
            "srs": round(srs[t], 2),
            "srs_rank": srs_rank[t],
            "total_tendency": round(total_tend[t], 1),
            "blowout_game_pct": round(blow[t], 1),
            "close_game_pct": round(close[t], 1),
            "b2b_margin_delta": round(b2b_fade[t], 1),
        }

    # -- Assemble output ------------------------------------------------------
    out = {
        "meta": {
            "artifact": "team_matchup_outcome",
            "season": SEASON,
            "generated": date.today().isoformat(),
            "scope": "2025-26 regular season (game_id prefix 00225); playoffs excluded",
            "purpose": "SCOUTING expected-outcome grid — NOT a betting model",
            "method": (
                "exp_margin = home_SRS - away_SRS + home_court(+1.73); "
                "exp_home_winprob = logistic(k * exp_margin); "
                "exp_total from a fitted total ~ (home_tend+away_tend) + "
                "(home_tend*away_tend) interaction regression on 2025-26 actual totals "
                "(the interaction is the pace/scoring-amplification term)."
            ),
            "home_court": home_court,
            "logistic_k": logistic_k,
            "league_baseline_total": league_total,
            "n_games_in_style_fit": n_obs,
            "sources": [
                "data/cache/intel_outcome/team_strength.json (SRS ratings, league constants)",
                "data/cache/intel_outcome/game_control.json (total tendency, variance profile)",
                "data/cache/intel_outcome/team_schedule_spots.json (b2b fade)",
                "data/nba/season_games_2025-26.json (game home/away join)",
                "data/nba/linescores_all.json (actual per-game totals incl. OT)",
            ],
            "caveats": [
                "SCOUTING ONLY. Game lines were REJECTED as a betting edge in this repo "
                "(full-season-total features leak in-sample and collapse leak-free; "
                "game-line ROI was negative on real closes). Do NOT stake this grid.",
                "exp_margin is a neutral-SCHEDULE expectation with the home team at home; "
                "it ignores same-day injuries, rest, and travel (size with schedule_spots).",
                "TOTAL TENDENCY bundles pace AND efficiency: true possession-pace is null "
                "in team_strength for 2025-26, so a team's game-total lean is the available "
                "scoring-environment style axis (not pure tempo).",
                "The style-interaction regression is DESCRIPTIVE (full-season fit) and is "
                "used only to shape the neutral grid, never as a forward-looking predictor.",
                "Totals include OT (had_ot games kept whole); margins are neutral-schedule, "
                "OT-agnostic SRS expectations.",
            ],
        },
        "league": {
            "home_court_margin_pts": home_court,
            "logistic_k": logistic_k,
            "baseline_total": league_total,
            "n_teams": len(tris),
        },
        "style_interaction": {
            "model": "total ~ b0 + b1*(home_tend+away_tend) + b2*(home_tend*away_tend)",
            "intercept_b0": round(b0, 3),
            "sum_coef_b1": round(b1, 4),
            "pace_amplification_coef_b2": round(b2, 6),
            "pace_amplification_coef_b2_se": round(se_b2, 6),
            "pace_amplification_t_stat": round(t_b2, 2),
            "super_additive": bool(b2 > 0),
            "interpretation": (
                ("SUPER-additive: two high-total (or two low-total) teams produce games "
                 "ABOVE the naive sum of their leans; the amplification grows with the "
                 "product of their tendencies."
                 ) if b2 > 0 else
                ("SUB-additive: extreme same-lean pairings regress toward the league total; "
                 "the sum-of-leans over-states how far the combined total moves."
                 ) if b2 < 0 else
                "Additive: no measurable interaction between the two teams' total leans."
            ),
            "n_games": n_obs,
            "n_ot_games": n_ot,
            "model_r2": round(r2, 4),
            "model_rmse": round(rmse, 2),
            "additive_only_r2": round(r2_add, 4),
            "sum_coef_b1_se": round(se_b1, 4),
            "mismatch_settling": {
                "same_lean_resid_vs_additive": round(same_resid, 3),
                "mismatch_resid_vs_additive": round(mismatch_resid, 3),
                "note": (
                    "Residual of actual total vs the SUM-only model. Same-lean games "
                    "(both teams lean the same way) sit at the first value, mismatch games "
                    "(one high + one low) at the second; a positive same-lean / negative "
                    "mismatch gap is the super-additive signature."
                ),
            },
        },
        "team_cards": team_cards,
        "pairings": pairings,
        "biggest_mismatches": biggest_mismatches,
        "highest_total_matchups": highest_total_matchups,
        "lowest_total_matchups": lowest_total_matchups,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    # -- Console summary ------------------------------------------------------
    print(f"[ok] wrote {OUT_PATH}")
    print(f"  pairings: {len(pairings)} (30x29)")
    print(f"  style fit: n={n_obs} games ({n_ot} OT), R2={r2:.4f} (additive-only R2={r2_add:.4f})")
    print(f"  b1 (sum) = {b1:+.4f} (se {se_b1:.4f}); "
          f"b2 (amplification) = {b2:+.6f} (se {se_b2:.6f}, t={t_b2:+.2f})")
    print(f"  super-additive: {b2 > 0}  |  "
          f"same-lean resid {same_resid:+.2f} vs mismatch resid {mismatch_resid:+.2f}")
    print("  -- top-5 lopsided (|exp_margin|) --")
    for d in biggest_mismatches[:5]:
        print(f"    {d['matchup']:>18}  margin {d['exp_margin']:+6.2f}  "
              f"home WP {d['exp_home_winprob']:.3f}  total {d['exp_total']:.1f}")
    print("  -- top-5 highest total --")
    for d in highest_total_matchups[:5]:
        print(f"    {d['matchup']:>14}  total {d['exp_total']:.1f}  "
              f"(additive {d['additive_total']:.1f}, ampl {d['amplification_pts']:+.1f})")
    print("  -- top-5 lowest total --")
    for d in lowest_total_matchups[:5]:
        print(f"    {d['matchup']:>14}  total {d['exp_total']:.1f}  "
              f"(additive {d['additive_total']:.1f}, ampl {d['amplification_pts']:+.1f})")


if __name__ == "__main__":
    main()
