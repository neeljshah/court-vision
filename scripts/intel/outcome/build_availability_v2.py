"""
build_availability_v2.py  --  MARQUEE intel v2: "WHO DECIDES GAMES", schedule-adjusted
=======================================================================================

v1 (build_player_availability.py) measures a team's outcome IN vs OUT for each
player and ranks "who decides games" by the raw margin swing. The known flaw: a
player's OUT games can land on a softer/tougher slate, so part of the swing is
OPPONENT QUALITY, not the player. v1 already flags this (confound_flag) but does
not correct it -- 120/430 players are flagged.

This v2 ADJUSTS the margin swing for opponent quality using opponent SRS
(opponent-adjusted simple rating system, the cleanest point-scaled team-strength
measure we have, from team_strength.json). It then re-ranks on the ADJUSTED swing.

THE ADJUSTMENT (point-scale, no fitted coefficient needed)
----------------------------------------------------------
SRS is already on the point-margin scale: a team with rating R is expected to beat
an average team by R points on a neutral floor, and to beat an opponent of rating
S by (R - S) points. So the part of a single game's margin that is EXPLAINED by
opponent quality is exactly the opponent's SRS, S_opp: facing a +5 opponent costs
you ~5 margin points; facing a -5 opponent gifts you ~5. We therefore neutralize
each game by ADDING BACK the opponent's SRS:

    adj_margin(game)        = raw_margin(game) + opp_SRS(game)
    margin_swing_adj        = mean[adj_margin | IN]  -  mean[adj_margin | OUT]
                            = margin_swing_raw + ( mean[opp_SRS|IN] - mean[opp_SRS|OUT] )
    opp_adjustment          = margin_swing_adj - margin_swing_raw
                            =  opp_SRS_in_mean - opp_SRS_out_mean

Reading: if the player's IN games faced TOUGHER opponents (higher mean opp SRS),
the raw swing UNDERSTATED him -> opp_adjustment > 0 -> adjusted swing grows. If his
OUT games hit a softer slate (lower opp SRS out... wait, opp faced while OUT), the
raw swing was schedule-INFLATED -> opp_adjustment < 0 -> adjusted swing shrinks
toward zero. (Coefficient is 1.0 by construction because SRS is point-scaled; this
is the standard SRS schedule adjustment, not a tuned knob.)

LEAK SAFETY
-----------
We emit TWO opponent-strength variants and adjust with the leak-safe one by default:
  * opp_srs_*_asof : each game is matched to the OPPONENT's AS-OF SRS -- the SRS
    computed from games strictly BEFORE that game's date (team_strength.json
    `as_of[].rating_to_date`). Nothing peeks at the game being adjusted or any
    future game. This is the leak-safe schedule strength and drives margin_swing_adj.
  * opp_srs_*_final : the opponent's END-OF-SEASON SRS. Cleaner estimate of true
    opponent quality but uses full-season info; emitted as a descriptive companion
    (margin_swing_adj_final) and NOT used for the ranked board.
The raw IN/OUT roster-window logic is byte-for-byte the same as v1, so the only new
information is the opponent-quality correction.

SOURCES (all read-only):
  data/cache/intel_outcome/player_availability.json  (v1: per-player IN/OUT swings,
        roles, confound flags -- we re-key off its player set & gates)
  data/cache/intel_outcome/team_strength.json        (opponent SRS: final + as-of)
  data/cache/cv_fix/leaguegamelog_regular_season.parquet  (truth: who played each
        team-game + scores -> per-game IN/OUT split + each game's opponent)
  data/nba/season_games_2025-26.json   (unused here; v1 used it for pace only)
  data/dnp_rows.parquet                 (OUT reason context, carried for parity)

OUTPUT: data/cache/intel_outcome/player_availability_v2.json
Schema mirrors v1 so it can drop into the outcome fold writer.

Run:  python scripts/intel/outcome/build_availability_v2.py
"""
from __future__ import annotations

import json
import pathlib
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[3]
GL_PATH = ROOT / "data/cache/cv_fix/leaguegamelog_regular_season.parquet"
DNP_PATH = ROOT / "data/dnp_rows.parquet"
V1_PATH = ROOT / "data/cache/intel_outcome/player_availability.json"
TS_PATH = ROOT / "data/cache/intel_outcome/team_strength.json"
OUT_PATH = ROOT / "data/cache/intel_outcome/player_availability_v2.json"

SEASON = "2025-26"
MIN_OUT = 4
MIN_IN = 10
HIGH_CONF_OUT = 8
HIGH_CONF_IN = 25
# After opponent adjustment the residual schedule confound is tiny; we re-flag on
# the leak-safe opp-SRS gap that REMAINS implicit in the adjustment magnitude.
CONFOUND_ADJ_PTS = 2.0   # |opp_adjustment| >= 2.0 margin pts => raw swing was schedule-tilted

# --- as-of SRS robustness ---------------------------------------------------
# The iterative SRS solve DIVERGES in the first ~2 weeks (sparse, poorly-connected
# schedule): early as-of ratings hit |R| ~ 100-330, pure noise. We make the
# leak-safe opp strength robust WITHOUT peeking forward:
#   (1) CLAMP the raw as-of rating to +-SRS_CLAMP FIRST. Below ~60 prior games the
#       iterative solve produces |R| up to 330 (pure noise; measured MAE-vs-final
#       ~34, corr +0.19); clamping to the plausible final-SRS envelope (+-12.4 real)
#       removes the blow-up before it can pollute a mean.
#   (2) SHRINK toward 0 (the league mean -- known a-priori, NOT a future outcome) by
#       weight w = n_prior / (n_prior + SRS_SHRINK_K). Uses only n_games_prior,
#       which is itself leak-safe, so the corrected value still never sees the game
#       being adjusted or any later game. With K=60 a <60-prior game is down-weighted
#       to <=0.5 (the bucket where as-of barely correlates with final), while
#       reliable mid/late-season ratings (corr +0.85-0.98 past 200) pass ~unchanged.
SRS_SHRINK_K = 60.0      # half-shrink at ~60 prior games (~3 weeks of league play)
SRS_CLAMP = 15.0         # plausible-rating cap (real final SRS in [-12.4, +11.6])


def robust_asof_srs(rating: float | None, n_prior: int) -> float:
    """Leak-safe robustification of an opponent's as-of SRS.

    rating is the opponent's SRS from games STRICTLY PRIOR to the game in
    question (team_strength as_of.rating_to_date). We CLAMP the raw rating to the
    plausible envelope, then SHRINK toward 0 by a weight that grows with the number
    of prior games. Both steps use only leak-safe inputs (the prior-only rating and
    its prior-game count); neither peeks at the game being adjusted or any later
    game. None -> 0 (league-mean prior).
    """
    if rating is None:
        return 0.0
    clamped = max(-SRS_CLAMP, min(SRS_CLAMP, rating))
    w = n_prior / (n_prior + SRS_SHRINK_K) if n_prior > 0 else 0.0
    return float(w * clamped)


# ---------------------------------------------------------------------------
# team-game truth frame (identical construction to v1 load_team_games)
# ---------------------------------------------------------------------------
def load_team_games(gl: pd.DataFrame) -> pd.DataFrame:
    tg = (
        gl.groupby(["GAME_ID", "TEAM_ABBREVIATION"], as_index=False)
        .agg(team_pts=("PTS", "sum"), game_date=("GAME_DATE", "first"))
    )
    rows = []
    for gid, sub in tg.groupby("GAME_ID"):
        if len(sub) != 2:
            continue
        a, b = sub.iloc[0], sub.iloc[1]
        for me, opp in ((a, b), (b, a)):
            rows.append(
                {
                    "GAME_ID": gid,
                    "TEAM": me["TEAM_ABBREVIATION"],
                    "GAME_DATE": str(me["game_date"]),
                    "team_pts": int(me["team_pts"]),
                    "OPP": opp["TEAM_ABBREVIATION"],
                    "opp_pts": int(opp["team_pts"]),
                }
            )
    tgf = pd.DataFrame(rows)
    tgf["margin"] = tgf["team_pts"] - tgf["opp_pts"]
    tgf["total"] = tgf["team_pts"] + tgf["opp_pts"]
    tgf["win"] = (tgf["margin"] > 0).astype(int)
    return tgf


def load_opp_srs(ts: dict):
    """Return:
       final_srs[tri]                 -> end-of-season SRS (descriptive)
       asof_srs[(game_id, tri)]       -> (rating_to_date, n_games_prior) going INTO
                                         game_id (leak-safe; pre-robustification)
    Each game's OPPONENT-as-of-SRS is then asof_srs[(game_id, OPP)].
    """
    teams = ts["teams"]
    final_srs = {tri: float(td["srs_rating"]) for tri, td in teams.items()}
    asof_srs: dict[tuple[str, str], tuple[float, int]] = {}
    for tri, td in teams.items():
        for e in td.get("as_of", []):
            asof_srs[(str(e["game_id"]), tri)] = (
                float(e["rating_to_date"]), int(e.get("n_games_prior", 0))
            )
    return final_srs, asof_srs


def main() -> None:
    gl = pd.read_parquet(GL_PATH)
    gl = gl[gl["SEASON_ID"].astype(str) == "22025"].copy()
    gl["GAME_DATE"] = gl["GAME_DATE"].astype(str)
    gl["GAME_ID"] = gl["GAME_ID"].astype(str)

    v1 = json.loads(V1_PATH.read_text())
    v1_players = v1["players"]
    ts = json.loads(TS_PATH.read_text())
    final_srs, asof_srs = load_opp_srs(ts)

    tgf = load_team_games(gl)
    team_game_index = {t: sub.set_index("GAME_ID") for t, sub in
                       tgf.sort_values(["TEAM", "GAME_DATE", "GAME_ID"]).groupby("TEAM")}

    # player -> primary team + roster window (identical to v1)
    pt = gl.groupby(["PLAYER_ID", "TEAM_ABBREVIATION"]).size().reset_index(name="n")
    primary = pt.sort_values("n").groupby("PLAYER_ID").tail(1).set_index("PLAYER_ID")
    player_team_games = (
        gl.groupby(["PLAYER_ID", "TEAM_ABBREVIATION"])
        .agg(gids=("GAME_ID", lambda s: set(s)),
             first_date=("GAME_DATE", "min"),
             last_date=("GAME_DATE", "max"))
    )

    dnp = pd.read_parquet(DNP_PATH)
    dnp = dnp[dnp["season"] == SEASON].copy()
    dnp["game_id"] = dnp["game_id"].astype(str)
    dnp_reason = {(int(r.player_id), r.game_id): r.dnp_reason
                  for r in dnp.itertuples(index=False)}

    players_out: dict[str, dict] = {}
    n_missing_asof = 0
    n_games_total = 0

    for pid in primary.index:
        pid_s = str(pid)
        # only players v1 deemed measurable (same inclusion gates) so v2 drops
        # cleanly into the same fold; this also gives us v1 raw fields to carry.
        v1d = v1_players.get(pid_s)
        if v1d is None:
            continue

        team = primary.loc[pid, "TEAM_ABBREVIATION"]
        team_idx = team_game_index.get(team)
        if team_idx is None:
            continue

        ptg = player_team_games.loc[(pid, team)]
        first_d, last_d = ptg["first_date"], ptg["last_date"]
        played_gids = ptg["gids"]

        cand = team_idx[(team_idx["GAME_DATE"] >= first_d) & (team_idx["GAME_DATE"] <= last_d)].copy()
        in_mask = cand.index.isin(played_gids)
        in_games = cand[in_mask]
        out_games = cand[~in_mask]
        n_in, n_out = len(in_games), len(out_games)
        if n_in < MIN_IN or n_out < MIN_OUT:
            continue

        # opponent SRS per game -- leak-safe as-of (primary) and final (companion)
        def opp_srs_means(df):
            asof_vals, final_vals = [], []
            nonlocal n_missing_asof, n_games_total
            for gid, row in df.iterrows():
                opp = row["OPP"]
                n_games_total += 1
                rec = asof_srs.get((gid, opp))
                if rec is None:
                    n_missing_asof += 1
                    a = 0.0   # no as-of entry -> league-mean prior (leak-safe)
                else:
                    raw_rating, n_prior = rec
                    a = robust_asof_srs(raw_rating, n_prior)  # shrink+clamp, leak-safe
                asof_vals.append(a)
                final_vals.append(final_srs.get(opp, 0.0))
            return (float(np.mean(asof_vals)) if asof_vals else 0.0,
                    float(np.mean(final_vals)) if final_vals else 0.0)

        opp_srs_in_asof, opp_srs_in_final = opp_srs_means(in_games)
        opp_srs_out_asof, opp_srs_out_final = opp_srs_means(out_games)

        margin_in = float(in_games["margin"].mean())
        margin_out = float(out_games["margin"].mean())
        margin_swing_raw = margin_in - margin_out

        # ---- the adjustment (point-scaled, coeff = 1.0 by SRS construction) ----
        # adj_margin = raw_margin + opp_SRS ; swing_adj = swing_raw + (opp_in - opp_out)
        opp_adjustment = opp_srs_in_asof - opp_srs_out_asof          # leak-safe
        opp_adjustment_final = opp_srs_in_final - opp_srs_out_final  # companion
        margin_swing_adj = margin_swing_raw + opp_adjustment
        margin_swing_adj_final = margin_swing_raw + opp_adjustment_final

        # re-stabilize: keep v1's Welch SE of the RAW swing (the opponent
        # adjustment is a deterministic shift of the means, so the difference-of-
        # means sampling noise is unchanged to first order). z on adjusted swing.
        se = float(v1d.get("margin_swing_se") or 0.0)
        # v1 rounds margin_swing; recompute SE-consistent z on adjusted value
        margin_z_adj = round(margin_swing_adj / se, 3) if se > 0 else 0.0

        # confidence: start from v1, then DEMOTE if the adjustment moved the swing
        # a lot (raw was schedule-tilted) and PROMOTE clean cases that v1 only
        # flagged on the winpct-based confound.
        confound_adj = bool(abs(opp_adjustment) >= CONFOUND_ADJ_PTS)
        n_ok = (n_out >= HIGH_CONF_OUT and n_in >= HIGH_CONF_IN)
        if n_ok and not confound_adj:
            confidence = "high"
        elif confound_adj:
            confidence = "low"
        else:
            confidence = "medium"

        reasons = defaultdict(int)
        for gid in out_games.index:
            r = dnp_reason.get((int(pid), gid))
            reasons[r if r else "not_listed"] += 1

        players_out[pid_s] = {
            "name": v1d["name"],
            "team": team,
            "vault_slug": v1d.get("vault_slug"),
            "traded_midseason": v1d.get("traded_midseason", False),
            "min_in": v1d["min_in"],
            "role": v1d["role"],
            "n_in": int(n_in),
            "n_out": int(n_out),
            "margin_in": round(margin_in, 3),
            "margin_out": round(margin_out, 3),
            "margin_swing_raw": round(margin_swing_raw, 3),
            "opp_srs_in": round(opp_srs_in_asof, 3),
            "opp_srs_out": round(opp_srs_out_asof, 3),
            "opp_srs_in_final": round(opp_srs_in_final, 3),
            "opp_srs_out_final": round(opp_srs_out_final, 3),
            "opp_adjustment": round(opp_adjustment, 3),
            "opp_adjustment_final": round(opp_adjustment_final, 3),
            "margin_swing_adj": round(margin_swing_adj, 3),
            "margin_swing_adj_final": round(margin_swing_adj_final, 3),
            "margin_swing_se": round(se, 3),
            "margin_swing_z": round(margin_swing_adj / se, 3) if se > 0 else 0.0,
            "winpct_swing": v1d.get("winpct_swing"),
            "confidence": confidence,
            "confound_flag": confound_adj,
            "confound_note": (
                f"Opponent-SRS adjustment shifted the swing by {opp_adjustment:+.2f} pts "
                f"({'IN faced tougher slate -> raw understated' if opp_adjustment > 0 else 'OUT hit softer slate -> raw inflated'}); "
                f"raw {margin_swing_raw:+.2f} -> adjusted {margin_swing_adj:+.2f}."
            ) if confound_adj else "",
            "out_reasons": dict(reasons),
        }

    # ---- adjusted leaderboard (same gates as v1 who_decides_games) ----
    def _entry(pid, d):
        return {
            "player_id": pid,
            "name": d["name"],
            "team": d["team"],
            "role": d["role"],
            "min_in": d["min_in"],
            "margin_swing_raw": d["margin_swing_raw"],
            "margin_swing_adj": d["margin_swing_adj"],
            "opp_adjustment": d["opp_adjustment"],
            "margin_swing_z": d["margin_swing_z"],
            "n_in": d["n_in"],
            "n_out": d["n_out"],
            "confidence": d["confidence"],
            "confound_flag": d["confound_flag"],
        }

    credible = [
        (pid, d) for pid, d in players_out.items()
        if d["n_out"] >= MIN_OUT and abs(d["margin_swing_z"]) >= 1.0 and d["min_in"] >= 20.0
    ]
    who_decides_adj = [
        _entry(pid, d) for pid, d in
        sorted(credible, key=lambda kv: abs(kv[1]["margin_swing_adj"]), reverse=True)
    ][:40]

    payload = {
        "meta": {
            "artifact": "player_availability_v2",
            "agent": "MARQUEE / who-decides-games (opponent-adjusted)",
            "season": SEASON,
            "method": (
                "v2 = v1 IN-vs-OUT margin swing with the OPPONENT-QUALITY component "
                "removed via opponent SRS. SRS is point-scaled, so the opponent's "
                "rating IS the expected margin contribution; we neutralize each game "
                "by adding back the opponent's SRS, then re-take the IN-OUT difference."
            ),
            "formula": (
                "adj_margin(game) = raw_margin(game) + opp_SRS_asof(game); "
                "margin_swing_adj = mean(adj_margin|IN) - mean(adj_margin|OUT) "
                "= margin_swing_raw + (mean opp_SRS_in - mean opp_SRS_out); "
                "opp_adjustment = mean opp_SRS_in - mean opp_SRS_out. "
                "Coefficient on SRS is 1.0 by construction (SRS is on the point-margin "
                "scale); no fitted knob. opp_SRS_asof uses team_strength as_of "
                "rating_to_date (games strictly prior to each game's date) => leak-safe."
            ),
            "sources": [
                "data/cache/intel_outcome/player_availability.json (v1 IN/OUT swings, roles, gates)",
                "data/cache/intel_outcome/team_strength.json (opponent SRS: final + leak-safe as-of)",
                "data/cache/cv_fix/leaguegamelog_regular_season.parquet (per-game IN/OUT split + opponent)",
                "data/dnp_rows.parquet (OUT reason context)",
            ],
            "definitions": {
                "margin_swing_raw": "v1 swing: mean team margin IN minus OUT (positive => team better with him)",
                "opp_srs_in/out": "avg LEAK-SAFE as-of opponent SRS faced in IN/OUT games (point scale)",
                "opp_srs_in_final/out_final": "avg END-OF-SEASON opponent SRS faced (descriptive companion)",
                "opp_adjustment": "opp_srs_in - opp_srs_out; the schedule-quality shift added to the raw swing",
                "margin_swing_adj": "PRIMARY. raw swing + opp_adjustment (leak-safe opponent-quality removed)",
                "margin_swing_adj_final": "same using end-of-season opponent SRS (companion, not leak-safe)",
                "margin_swing_z": "margin_swing_adj / v1 Welch SE; t-like, |z|>=2 clears its own noise",
                "confound_flag": f"True when |opp_adjustment| >= {CONFOUND_ADJ_PTS} pts (raw swing was schedule-tilted)",
                "confidence": f"high = n_out>={HIGH_CONF_OUT} & n_in>={HIGH_CONF_IN} & |opp_adjustment|<{CONFOUND_ADJ_PTS}; low if schedule-tilted; else medium",
            },
            "inclusion": {"min_out_games": MIN_OUT, "min_in_games": MIN_IN},
            "leaderboard": {
                "who_decides_games_adj": (
                    "PRIMARY. Rotation difference-makers (min_in>=20 mpg, n_out>=4, "
                    "|z|>=1 on adjusted swing) ranked by |margin_swing_adj|. The "
                    "opponent-quality confound has been removed, so schedule-artifact "
                    "swings (soft OUT slates) shrink toward zero."
                ),
            },
            "caveat": (
                "STILL ASSOCIATION, NOT CAUSATION -- we remove the OPPONENT-QUALITY "
                "confound but other co-varying factors (other injuries, rest, "
                "tank/load-management spots, home/road balance) remain. SRS itself is "
                "an opponent-adjusted point rating; the as-of variant is leak-safe but "
                "noisier early-season. Scouting intelligence; a betting edge only if "
                "graded vs real totals/spreads on >=2 corpora."
            ),
            "n_players": len(players_out),
            "n_confounded_v1": sum(1 for d in v1_players.values() if d.get("confound_flag")),
            "n_confounded_v2": sum(d["confound_flag"] for d in players_out.values()),
            "asof_coverage": round(1.0 - (n_missing_asof / n_games_total), 4) if n_games_total else None,
        },
        "players": players_out,
        "who_decides_games_adj": who_decides_adj,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))

    # ---- console summary ----
    print(f"Wrote {OUT_PATH}")
    print(f"  players: {len(players_out)}")
    print(f"  v1 confounded: {payload['meta']['n_confounded_v1']}  ->  v2 confounded: {payload['meta']['n_confounded_v2']}")
    print(f"  as-of opp-SRS coverage: {payload['meta']['asof_coverage']}")
    print("\nADJUSTED TOP-15 WHO DECIDES GAMES (opponent-quality removed):")
    print(f"  {'name':22s} {'tm':3s} {'mpg':>4s} {'raw':>7s} {'adj':>7s} {'oppΔ':>6s} {'z':>5s} {'n_in':>4s} {'n_out':>5s} {'conf':>6s}")
    for e in who_decides_adj[:15]:
        print(
            f"  {e['name'][:22]:22s} {e['team']:3s} {e['min_in']:4.0f} {e['margin_swing_raw']:+7.2f} "
            f"{e['margin_swing_adj']:+7.2f} {e['opp_adjustment']:+6.2f} {e['margin_swing_z']:+5.1f} "
            f"{e['n_in']:4d} {e['n_out']:5d} {e['confidence']:>6s}"
        )


if __name__ == "__main__":
    main()
