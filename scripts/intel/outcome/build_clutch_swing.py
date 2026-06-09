#!/usr/bin/env python
"""
build_clutch_swing.py  --  WHO DECIDES GAMES IN THE CLUTCH (player on/off, CLOSE games)
=======================================================================================

Answers: which specific players swing the OUTCOME of CLOSE games -- i.e. for each
player, how does his team's CLOSE-game win% change between the games he plays (IN)
and the games he sits (OUT)?  This is the clutch-specific cousin of the general
"who decides games" availability layer: instead of all games, it restricts the
IN-vs-OUT comparison to the team's close finishes, so it isolates the players whose
presence actually tips tight games rather than padding blowouts.

WHAT IT ADDS OVER player_availability.json
------------------------------------------
* player_availability swings are over ALL games (margin-weighted; a 30-pt blowout
  moves margin_swing a lot but tells you nothing about clutch). This layer throws
  away the blowouts and keeps only games that finished within 5, then asks the
  binary question that matters in the clutch: did the team WIN the close one?
* We also carry each player's personal NBA-Stats clutch box line (clutch +/-,
  clutch scoring) from clutch_outcome.json and cross-reference the closers
  leaderboard, to answer: do the best individual closers also SWING close-game
  outcomes, or are those two different lists?

CLUTCH / CLOSE DEFINITION (final-margin proxy, same as clutch_outcome team record)
---------------------------------------------------------------------------------
A team-game is "CLOSE" if the FINAL score margin was <= 5 points. This is a proxy
for a close finish, NOT the exact NBA last-5-min/<=5-pt clutch-game flag (which
needs the LeagueDashTeamClutch endpoint, absent from this repo). It is STRICTER
than the true clutch-game rate -- a game tied at the 5-minute mark that then blows
open is not counted -- so n_clutch_* here are lower bounds.  301 of 1230 2025-26
games (24.5%) finished within 5; that is the universe this layer splits IN vs OUT.

IN / OUT SET (roster-window-bounded, reused from build_player_availability)
---------------------------------------------------------------------------
For a player's PRIMARY team (most games), IN = the team's CLOSE games in which he
appeared in the box score; OUT = the team's CLOSE games in the SAME roster-date
window in which he did not appear. Bounding to [first_appearance, last_appearance]
with the team avoids charging a traded/late-arriving player for games before he
joined or after he left.

THE (VERY REAL) SMALL-SAMPLE CAVEAT
-----------------------------------
A team plays only ~20 close games all season; a healthy starter's OUT subset is
typically 0-3 of those. Clutch AND absence is a DOUBLY thin cut, so a single
close win/loss flips the IN/OUT win% by 25-50 pp. clutch_winpct_swing is therefore
NOISY for almost everyone: we hard-gate (n_clutch_in >= 6 AND n_clutch_out >= 3 to
be ranked) and tag confidence accordingly. Treat the ranking as SCOUTING COLOR --
who *coincided* with close-game wins -- not as causal clutch value. ASSOCIATION,
NOT CAUSATION: when a player sits, opponent quality and other injuries move too.

LEAK NOTE
---------
Purely DESCRIPTIVE / within-season (2025-26 regular season only). Every number is
a summary of games that already happened; nothing peeks at a future game. As a
pregame prior it is leak-safe (it never includes the game being predicted), but it
is not tuned or fit -- it is a scouting split, not a model.

SOURCES (all read-only; recon'd)
--------------------------------
* data/cache/cv_fix/leaguegamelog_regular_season.parquet  (TRUTH: who played each
      2025-26 team-game + per-team final PTS -> close-game flag + IN/OUT split)
* data/cache/intel_outcome/clutch_outcome.json  (personal NBA-clutch box line:
      clutch_plus_minus / clutch_pts / n_clutch; + closers_leaderboard for x-ref)
* data/cache/intel_outcome/player_availability.json  (vault_slug + role/min_in
      context for the player; consistency of player->team mapping)

OUTPUT: data/cache/intel_outcome/player_clutch_swing.json   (string player_id keys)

Run:  python scripts/intel/outcome/build_clutch_swing.py
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
import pandas as pd

# Windows console defaults to cp1252; force UTF-8 so accented names don't crash
# the summary print. Does not affect the JSON (json.dump escapes non-ASCII).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parents[3]
GL_PATH = ROOT / "data/cache/cv_fix/leaguegamelog_regular_season.parquet"
CLUTCH_OUTCOME_PATH = ROOT / "data/cache/intel_outcome/clutch_outcome.json"
AVAILABILITY_PATH = ROOT / "data/cache/intel_outcome/player_availability.json"
OUT_PATH = ROOT / "data/cache/intel_outcome/player_clutch_swing.json"

SEASON = "2025-26"
CLOSE_MARGIN = 5          # final-margin proxy: |margin| <= 5 => close game

# Inclusion / gating. Clutch+absence is doubly thin, so gates are deliberately
# stiffer than the all-games availability layer.
MIN_CLUTCH_IN = 4         # must have >= this many CLOSE games played to appear at all
MIN_CLUTCH_OUT = 2        # must have >= this many CLOSE games missed to appear at all
RANK_MIN_IN = 6           # ranking ("difference-makers") requires >= this many IN
RANK_MIN_OUT = 3          # ranking requires >= this many OUT
HIGH_CONF_IN = 12         # confidence=high needs both this many IN ...
HIGH_CONF_OUT = 6         # ... and this many OUT close games


def _round(x, n=3):
    if x is None:
        return None
    try:
        xf = float(x)
        if math.isnan(xf) or math.isinf(xf):
            return None
        return round(xf, n)
    except (TypeError, ValueError):
        return None


def load_team_games(gl: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, team): final pts, opp pts, margin, win, close flag, date.

    Margin from per-team SUM of player PTS (the box-score truth), NOT summed
    PLUS_MINUS (that double-counts on-court slots ~5x). Same derivation as
    build_clutch_outcome / build_player_availability so counts reconcile.
    """
    tg = (
        gl.groupby(["GAME_ID", "TEAM_ABBREVIATION"], as_index=False)
        .agg(team_pts=("PTS", "sum"), game_date=("GAME_DATE", "first"))
    )
    tot = tg.groupby("GAME_ID")["team_pts"].sum().rename("game_total")
    tg = tg.merge(tot, on="GAME_ID")
    # drop any malformed game without exactly two teams
    cnt = tg.groupby("GAME_ID")["TEAM_ABBREVIATION"].transform("size")
    tg = tg[cnt == 2].copy()
    tg["opp_pts"] = tg["game_total"] - tg["team_pts"]
    tg["margin"] = tg["team_pts"] - tg["opp_pts"]
    tg["win"] = (tg["margin"] > 0).astype(int)
    tg["close"] = (tg["margin"].abs() <= CLOSE_MARGIN)
    return tg.rename(columns={"TEAM_ABBREVIATION": "TEAM", "game_date": "GAME_DATE"})


def main() -> None:
    gl = pd.read_parquet(GL_PATH)
    seasons = set(gl["SEASON_ID"].astype(str).unique())
    assert seasons == {"22025"}, f"unexpected seasons in leaguegamelog: {seasons}"
    gl["GAME_ID"] = gl["GAME_ID"].astype(str)
    gl["GAME_DATE"] = gl["GAME_DATE"].astype(str)

    tg = load_team_games(gl)
    n_close_games = int(tg["close"].sum() // 2)
    n_games_total = int(tg["GAME_ID"].nunique())

    # team -> its team-game rows indexed by GAME_ID (for the roster-window slice)
    team_game_index = {
        t: sub.set_index("GAME_ID") for t, sub in tg.groupby("TEAM")
    }

    # player -> primary team (most appearances) and traded flag
    pt = gl.groupby(["PLAYER_ID", "TEAM_ABBREVIATION"]).size().reset_index(name="n")
    primary = pt.sort_values("n").groupby("PLAYER_ID").tail(1).set_index("PLAYER_ID")
    n_teams_per_player = pt.groupby("PLAYER_ID").size()

    # per (player, team): set of GAME_IDs played + roster date window
    player_team_games = (
        gl.groupby(["PLAYER_ID", "TEAM_ABBREVIATION"])
        .agg(
            gids=("GAME_ID", lambda s: set(s)),
            name=("PLAYER_NAME", "first"),
            first_date=("GAME_DATE", "min"),
            last_date=("GAME_DATE", "max"),
        )
    )

    # ----- side intel: personal NBA-clutch box line + closers leaderboard -----
    co = json.load(open(CLUTCH_OUTCOME_PATH))
    co_players = co.get("players", {})            # spid -> box dict
    closers = co.get("closers_leaderboard", [])   # ranked by clutch_impact
    closer_rank = {c["player_id"]: c["rank"] for c in closers}
    closer_impact = {c["player_id"]: c["clutch_impact"] for c in closers}

    avail = json.load(open(AVAILABILITY_PATH))
    avail_players = avail.get("players", {})       # spid -> {role, min_in, vault_slug,...}

    players_out: dict[str, dict] = {}

    for pid in primary.index:
        spid = str(int(pid))
        team = primary.loc[pid, "TEAM_ABBREVIATION"]
        traded = bool(n_teams_per_player.get(pid, 1) > 1)

        ptg = player_team_games.loc[(pid, team)]
        name = str(ptg["name"])
        first_d, last_d, played_gids = ptg["first_date"], ptg["last_date"], ptg["gids"]

        team_idx = team_game_index.get(team)
        if team_idx is None:
            continue

        # team's games inside this player's roster window, restricted to CLOSE ones
        cand = team_idx[
            (team_idx["GAME_DATE"] >= first_d) & (team_idx["GAME_DATE"] <= last_d)
        ]
        close = cand[cand["close"]]
        if len(close) == 0:
            continue

        in_mask = close.index.isin(played_gids)
        cin, cout = close[in_mask], close[~in_mask]
        n_in, n_out = len(cin), len(cout)

        # inclusion gate: need a real IN and a real OUT close-game sample
        if n_in < MIN_CLUTCH_IN or n_out < MIN_CLUTCH_OUT:
            continue

        win_in = float(cin["win"].mean())
        win_out = float(cout["win"].mean())
        winpct_swing = win_in - win_out

        # personal clutch box line (NBA-Stats clutch window) for context + ranking
        box = co_players.get(spid, {})
        clutch_pm = box.get("clutch_plus_minus")
        clutch_pts = box.get("clutch_pts")
        n_clutch_box = box.get("n_clutch")

        # availability-layer role context (helps flag deep-bench artifacts)
        av = avail_players.get(spid, {})
        role = av.get("role")
        min_in = av.get("min_in")
        vault_slug = av.get("vault_slug")

        # confidence: doubly-thin clutch cut -> stiff thresholds
        if n_in >= HIGH_CONF_IN and n_out >= HIGH_CONF_OUT:
            conf = "high"
        elif n_in >= RANK_MIN_IN and n_out >= RANK_MIN_OUT:
            conf = "medium"
        else:
            conf = "low"
        low_n = (n_in < RANK_MIN_IN) or (n_out < RANK_MIN_OUT)

        # clutch_impact = the swing itself, lightly shrunk toward 0 by sample size
        # (so a 2-OUT-game 100pp swing doesn't outrank a 6-OUT-game 40pp one).
        # shrink factor = n_out / (n_out + k); k=4 is one "prior" close game of doubt.
        k = 4.0
        shrink = n_out / (n_out + k)
        clutch_impact = winpct_swing * shrink

        players_out[spid] = {
            "name": name,
            "team": team,
            "traded_midseason": traded,
            "role": role,
            "min_in": _round(min_in, 1),
            "vault_slug": vault_slug,
            # the headline split
            "clutch_win_in": _round(win_in),
            "clutch_win_out": _round(win_out),
            "clutch_winpct_swing": _round(winpct_swing),
            "n_clutch_in": n_in,
            "n_clutch_out": n_out,
            "clutch_in_record": f"{int(cin['win'].sum())}-{n_in - int(cin['win'].sum())}",
            "clutch_out_record": f"{int(cout['win'].sum())}-{n_out - int(cout['win'].sum())}",
            # sample-shrunk ranking score
            "clutch_impact": _round(clutch_impact),
            # personal NBA-clutch box line (different lens: individual closing, not on/off)
            "personal_clutch_plus_minus": _round(clutch_pm, 2),
            "personal_clutch_pts": _round(clutch_pts, 2),
            "n_personal_clutch_games": n_clutch_box,
            # closer cross-reference
            "closer_rank": closer_rank.get(spid),
            "closer_impact": closer_impact.get(spid),
            "confidence": conf,
            "low_n": low_n,
        }

    # ---- ranked clutch difference-makers (positive swing, gated to credible n) ----
    rankable = [
        (spid, p) for spid, p in players_out.items()
        if p["n_clutch_in"] >= RANK_MIN_IN and p["n_clutch_out"] >= RANK_MIN_OUT
    ]
    rankable.sort(key=lambda kv: (kv[1]["clutch_impact"] or -9), reverse=True)
    diff_makers = []
    for rank, (spid, p) in enumerate(rankable, start=1):
        diff_makers.append({
            "rank": rank,
            "player_id": spid,
            "name": p["name"],
            "team": p["team"],
            "clutch_winpct_swing": p["clutch_winpct_swing"],
            "clutch_impact": p["clutch_impact"],
            "clutch_win_in": p["clutch_win_in"],
            "clutch_win_out": p["clutch_win_out"],
            "clutch_in_record": p["clutch_in_record"],
            "clutch_out_record": p["clutch_out_record"],
            "n_clutch_in": p["n_clutch_in"],
            "n_clutch_out": p["n_clutch_out"],
            "closer_rank": p["closer_rank"],
            "confidence": p["confidence"],
        })

    # ---- closer-vs-swinger cross-reference summary -----------------------------
    # For the top-N individual closers, how often are they also positive close-game
    # swingers (and do they even clear the swing-ranking n-gate)?
    TOPN_CLOSERS = 30
    overlap_rows = []
    n_closer_positive_swing = 0
    n_closer_ranked = 0
    for c in closers[:TOPN_CLOSERS]:
        spid = c["player_id"]
        p = players_out.get(spid)
        ranked = bool(p and p["n_clutch_in"] >= RANK_MIN_IN
                      and p["n_clutch_out"] >= RANK_MIN_OUT)
        swing = p["clutch_winpct_swing"] if p else None
        if ranked:
            n_closer_ranked += 1
            if swing is not None and swing > 0:
                n_closer_positive_swing += 1
        overlap_rows.append({
            "closer_rank": c["rank"],
            "name": c["name"],
            "team": c["team"],
            "closer_impact": c["clutch_impact"],
            "clutch_winpct_swing": swing,
            "n_clutch_out": (p or {}).get("n_clutch_out"),
            "swing_ranked": ranked,
        })

    # correlation between closer_impact and clutch_winpct_swing across the players
    # who have BOTH a closer score and a credible swing sample
    pair_x, pair_y = [], []
    for spid, p in players_out.items():
        ci = p.get("closer_impact")
        sw = p.get("clutch_winpct_swing")
        if (ci is not None and sw is not None
                and p["n_clutch_in"] >= RANK_MIN_IN and p["n_clutch_out"] >= RANK_MIN_OUT):
            pair_x.append(ci)
            pair_y.append(sw)
    if len(pair_x) >= 5:
        corr = float(np.corrcoef(pair_x, pair_y)[0, 1])
    else:
        corr = None

    n_lown = sum(1 for p in players_out.values() if p["low_n"])

    out = {
        "meta": {
            "artifact": "player_clutch_swing",
            "agent": "OUTCOME-IMPACT / who-decides-games-in-the-clutch",
            "season": SEASON,
            "scope": "2025-26 regular season (PRIMARY); descriptive, within-season, leak-free",
            "generated_by": "scripts/intel/outcome/build_clutch_swing.py",
            "question": (
                "Which players swing the OUTCOME of CLOSE games? For each player, "
                "split his team's CLOSE games (final margin <=5) into IN (he played) "
                "vs OUT (he sat) and compare the team's win% IN vs OUT."
            ),
            "clutch_def": (
                f"CLOSE game = FINAL score margin <= {CLOSE_MARGIN} pts (per-team final "
                "PTS from leaguegamelog). PROXY for a close finish, NOT NBA's exact "
                "last-5-min/<=5-pt clutch-game flag; STRICTER, so n_clutch_* are lower "
                f"bounds. {n_close_games} of {n_games_total} 2025-26 games finished "
                "within 5."
            ),
            "fields": {
                "clutch_win_in/out": "team win fraction in the player's IN/OUT CLOSE games [0,1]",
                "clutch_winpct_swing": "clutch_win_in - clutch_win_out (positive => team wins close games MORE with him)",
                "n_clutch_in/out": "count of the team's CLOSE games the player played / missed (in his roster window)",
                "clutch_in/out_record": "team W-L in those close games",
                "clutch_impact": "clutch_winpct_swing shrunk by OUT sample: swing * n_out/(n_out+4) (ranking score)",
                "personal_clutch_plus_minus/pts": "the player's OWN NBA-Stats clutch box line (last 5 min, <=5 pts) from clutch_outcome.json -- a DIFFERENT lens (individual on-court closing, not team on/off)",
                "n_personal_clutch_games": "his NBA-clutch games played (box-stat n; differs from n_clutch_in)",
                "closer_rank/closer_impact": "his rank/score on clutch_outcome.json closers_leaderboard (individual closing prowess), for cross-reference",
                "confidence": f"high = n_in>={HIGH_CONF_IN} & n_out>={HIGH_CONF_OUT}; medium = n_in>={RANK_MIN_IN} & n_out>={RANK_MIN_OUT}; else low",
            },
            "inclusion": {
                "min_clutch_in": MIN_CLUTCH_IN,
                "min_clutch_out": MIN_CLUTCH_OUT,
                "rank_min_in": RANK_MIN_IN,
                "rank_min_out": RANK_MIN_OUT,
            },
            "closer_xref": {
                "definition": (
                    "Do good individual CLOSERS also SWING close-game outcomes? "
                    "Two different lists: closers_leaderboard ranks individual clutch "
                    "scoring/+- ; clutch difference-makers ranks team win% IN vs OUT."
                ),
                "topN_closers_checked": TOPN_CLOSERS,
                "n_topN_closers_with_credible_swing_sample": n_closer_ranked,
                "n_of_those_with_positive_swing": n_closer_positive_swing,
                "corr_closer_impact_vs_winpct_swing": _round(corr),
                "corr_note": (
                    "Pearson corr between individual closer_impact and team "
                    "clutch_winpct_swing across players with a credible swing sample. "
                    "Near-zero => being a great individual closer does NOT reliably "
                    "coincide with the team winning more close games when you play "
                    "(team on/off swing is dominated by sample noise + supporting cast)."
                ),
            },
            "caveats": [
                "DOUBLY THIN SAMPLE. A team plays only ~20 CLOSE games all season; a "
                "healthy starter's OUT subset is typically 0-3 of them. One flipped "
                "close result moves clutch_winpct_swing by 25-50 pp. Treat the ranking "
                "as scouting COLOR (who coincided with close-game wins), not causal "
                "clutch value. clutch_impact shrinks the swing by OUT sample to temper "
                "this, but it cannot manufacture signal that the data does not have.",
                "ASSOCIATION, NOT CAUSATION. When a player sits, opponent quality and "
                "OTHER injuries move too; this is not adjusted for here.",
                "CLOSE is a FINAL-margin <=5 proxy, stricter than NBA's last-5-min "
                "clutch-game flag; n_clutch_* are lower bounds on true clutch games.",
                "Player->team is the team with the most 2025-26 games; traded players "
                "are scored only over their primary-team roster window.",
                "personal_clutch_* and closer_rank are from clutch_outcome.json (the "
                "NBA-Stats clutch box, a DIFFERENT definition than the team-outcome "
                "swing) and are provided for cross-reference, not summed into the swing.",
                f"{n_lown} of {len(players_out)} included players are flagged low_n "
                "(below the ranking n-gate) and are EXCLUDED from clutch_difference_makers.",
            ],
            "leak_note": (
                "Descriptive, within-season 2025-26 only. Every number summarizes "
                "games that already happened; nothing peeks at a future game. Valid as "
                "a leak-safe pregame prior (never includes the predicted game), but it "
                "is a scouting split, not a fitted model."
            ),
            "n_players": len(players_out),
            "n_difference_makers_ranked": len(diff_makers),
            "n_low_n_flagged": n_lown,
            "n_close_games": n_close_games,
            "n_games_total": n_games_total,
        },
        "players": players_out,
        "clutch_difference_makers": diff_makers,
        "closer_vs_swinger_xref": overlap_rows,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    # ----------------------------- console summary -----------------------------
    print(f"WROTE {OUT_PATH}")
    print(f"  players={len(players_out)}  ranked_difference_makers={len(diff_makers)}  "
          f"low_n_flagged={n_lown}  close_games={n_close_games}/{n_games_total}")

    print("\n  TOP 10 CLUTCH DIFFERENCE-MAKERS (team win% swing in CLOSE games, IN vs OUT):")
    print("      (clutch_impact = swing shrunk by OUT sample; n shown as IN/OUT)")
    for d in diff_makers[:10]:
        cr = f"closer#{d['closer_rank']}" if d["closer_rank"] else "not-a-listed-closer"
        print(
            f"    {d['rank']:>2}. {d['name']:<24} {str(d['team']):>3}  "
            f"swing={d['clutch_winpct_swing']:+.3f}  impact={d['clutch_impact']:+.3f}  "
            f"in {d['clutch_in_record']}({d['clutch_win_in']:.2f}) "
            f"out {d['clutch_out_record']}({d['clutch_win_out']:.2f})  "
            f"n={d['n_clutch_in']}/{d['n_clutch_out']}  [{cr}, {d['confidence']}]"
        )

    print("\n  CLOSER vs SWINGER cross-reference:")
    cx = out["meta"]["closer_xref"]
    print(f"    of top {cx['topN_closers_checked']} individual closers, "
          f"{cx['n_topN_closers_with_credible_swing_sample']} have a credible swing sample; "
          f"{cx['n_of_those_with_positive_swing']} of those swing POSITIVE.")
    print(f"    corr(closer_impact, clutch_winpct_swing) = {cx['corr_closer_impact_vs_winpct_swing']}")


if __name__ == "__main__":
    main()
