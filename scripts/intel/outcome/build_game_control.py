"""
GAME-CONTROL / SCORING-ENVIRONMENT outcome profile.

For each NBA team (2025-26 regular season), describe HOW their games actually
unfold: blowout/close-game variance, quarter-by-quarter game control, halftime
lead protection / comeback rate, and the scoring environment of their games.

Outputs: data/cache/intel_outcome/game_control.json   (SCOUTING / descriptive)

DATA MODEL
----------
- data/nba/season_games_2025-26.json  ({v, rows}): provides game_id -> home_team
  (TRI), away_team (TRI), game_date, home_win. Played games are those with a
  non-null `home_win`. Regular-season game_ids start with "00225"; playoff
  ("00425") rows are excluded (they also have no linescore rows).
- data/nba/linescores_all.json  (dict keyed by game_id): home_q1..q4, away_q1..q4,
  and (newer rows) had_ot, home_pts_ot, away_pts_ot. `home_team_id` is sometimes
  null for 2025-26 PBP-sourced rows, so home/away TRI is taken from season_games,
  NOT from the linescore file.

RECON-VERIFIED (2026-06-01):
- Final score = sum(q1..q4) + (pts_ot or 0). Derived home-winner matches
  season_games.home_win for 1225/1225 played games, 0 mismatch, 0 tie.
- Linescore game total matches player-box parquet total for 299/300 spot-checks
  (1 off-by-one stat-correction case). Linescores is the canonical source.
- 30 TRIs, 79-82 games/team, 1225 unique played games. avg game total ~231.

OT HANDLING
-----------
OT points (home_pts_ot / away_pts_ot) are a LUMP across all OT periods (not
per-OT), so they are included in final margin / final total (blowout, close-game,
total, h2_net via final) but CANNOT be attributed to a regulation quarter. The
per-quarter nets (q1..q4) and h1/h2 quarter-sum nets therefore use REGULATION
columns only; this is the correct read of "Q4 game-control" (regulation Q4).

LEAK SAFETY (house rule)
------------------------
A sibling agent proved a full-season total tendency is a hindsight-leakage trap
(looked +6.6%, collapsed to -10% leak-free). So we emit TWO totals, clearly
separated:
  - total_desc          : DESCRIPTIVE full-season avg game total in the team's
                          games. NOT predictive; pure scouting summary.
  - total_rolling_leakfree : the average, over the team's games, of the team's
                          rolling mean of STRICTLY-PRIOR games' totals (no peeking
                          at the current or future game). This is what you would
                          actually have known going into each game. Games before
                          the team has any prior history are skipped from this
                          average (rolling needs >=1 prior game).
All quarter / blowout / lead-protection numbers are full-season DESCRIPTIVE
profile fields (how their games unfolded), NOT forward-looking predictions.

SCOUTING ONLY. No betting code, no model wiring.
"""

import json
import os
from collections import defaultdict
from statistics import mean

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))  # .../nba-ai-system
SEASON = "2025-26"
REG_PREFIX = "00225"          # 2025-26 regular-season game_id prefix
BLOWOUT_MARGIN = 15           # |final margin| >= 15 -> blowout
CLOSE_MARGIN = 5              # |final margin| <= 5  -> close game

LINESCORES = os.path.join(BASE, "data", "nba", "linescores_all.json")
SEASON_GAMES = os.path.join(BASE, "data", "nba", f"season_games_{SEASON}.json")
OUT_DIR = os.path.join(BASE, "data", "cache", "intel_outcome")
OUT_PATH = os.path.join(OUT_DIR, "game_control.json")


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _final_scores(v):
    """Return (home_final, away_final) including lump OT points."""
    h = (v["home_q1"] + v["home_q2"] + v["home_q3"] + v["home_q4"]
         + (v.get("home_pts_ot") or 0))
    a = (v["away_q1"] + v["away_q2"] + v["away_q3"] + v["away_q4"]
         + (v.get("away_pts_ot") or 0))
    return h, a


def _build_games():
    """Join season_games (teams/date/winner) with linescores (quarter scores).

    Returns a list of per-game dicts, one entry per played regular-season game,
    sorted by (game_date, game_id) for chronological/leak-free ordering.
    """
    sg = _load_json(SEASON_GAMES)
    ls = _load_json(LINESCORES)
    games = []
    skipped_no_linescore = 0
    for r in sg["rows"]:
        gid = r["game_id"]
        if not gid.startswith(REG_PREFIX):
            continue                      # exclude playoffs / other seasons
        if r.get("home_win") is None:
            continue                      # unplayed / scheduled game
        v = ls.get(gid)
        if v is None:
            skipped_no_linescore += 1
            continue
        hf, af = _final_scores(v)
        games.append({
            "game_id": gid,
            "date": r["game_date"],
            "home": r["home_team"],
            "away": r["away_team"],
            "home_win": int(r["home_win"]),
            "home_final": hf,
            "away_final": af,
            "total": hf + af,
            "had_ot": bool(v.get("had_ot")),
            # regulation quarter scores
            "h_q": [v["home_q1"], v["home_q2"], v["home_q3"], v["home_q4"]],
            "a_q": [v["away_q1"], v["away_q2"], v["away_q3"], v["away_q4"]],
            "h_h1": v["home_q1"] + v["home_q2"],
            "a_h1": v["away_q1"] + v["away_q2"],
        })
    games.sort(key=lambda g: (g["date"], g["game_id"]))
    return games, skipped_no_linescore


def _team_perspective(g, tri):
    """Return that team's view of a game g: signed quarter nets, margin, total,
    won-flag, halftime lead/deficit, comeback/protect outcomes."""
    if tri == g["home"]:
        my_q, opp_q = g["h_q"], g["a_q"]
        my_final, opp_final = g["home_final"], g["away_final"]
        my_h1, opp_h1 = g["h_h1"], g["a_h1"]
        won = g["home_win"] == 1
    else:
        my_q, opp_q = g["a_q"], g["h_q"]
        my_final, opp_final = g["away_final"], g["home_final"]
        my_h1, opp_h1 = g["a_h1"], g["h_h1"]
        won = g["home_win"] == 0
    q_net = [my_q[i] - opp_q[i] for i in range(4)]          # regulation quarters
    h1_net = my_h1 - opp_h1
    # h2 net derived from final-minus-halftime (includes OT, regulation-symmetric
    # caveat documented in meta). Use regulation-only for quarter consistency:
    h2_reg_net = (my_q[2] + my_q[3]) - (opp_q[2] + opp_q[3])
    margin = my_final - opp_final
    return {
        "q_net": q_net,
        "h1_net": h1_net,
        "h2_net": h2_reg_net,
        "margin": margin,
        "total": g["total"],
        "won": won,
        "led_at_half": my_h1 > opp_h1,
        "trailed_at_half": my_h1 < opp_h1,
        "tied_at_half": my_h1 == opp_h1,
    }


def _rolling_leakfree_total(team_totals_in_order):
    """For each game (in chrono order), the mean of the team's STRICTLY-PRIOR
    game totals; games with no prior history are skipped. Returns the average of
    those leak-free expectations across the season (what you'd have known going
    in, averaged). None if fewer than 2 games."""
    prior_means = []
    running_sum = 0.0
    running_n = 0
    for t in team_totals_in_order:
        if running_n >= 1:                       # strictly-prior only
            prior_means.append(running_sum / running_n)
        running_sum += t
        running_n += 1
    if not prior_means:
        return None
    return round(mean(prior_means), 2)


def build():
    games, skipped = _build_games()

    # accumulate per-team perspectives in chronological order
    per_team = defaultdict(list)          # tri -> list of perspective dicts
    per_team_totals = defaultdict(list)   # tri -> chrono list of game totals
    for g in games:
        for tri in (g["home"], g["away"]):
            per_team[tri].append(_team_perspective(g, tri))
            per_team_totals[tri].append(g["total"])

    league_total_sum = sum(g["total"] for g in games)
    league_avg_total = league_total_sum / len(games) if games else 0.0
    league_blowouts = sum(1 for g in games
                          if abs(g["home_final"] - g["away_final"]) >= BLOWOUT_MARGIN)

    teams_out = {}
    for tri, persp in sorted(per_team.items()):
        n = len(persp)
        wins_by_blowout = sum(1 for p in persp if p["won"] and p["margin"] >= BLOWOUT_MARGIN)
        loss_by_blowout = sum(1 for p in persp if (not p["won"]) and p["margin"] <= -BLOWOUT_MARGIN)
        close = sum(1 for p in persp if abs(p["margin"]) <= CLOSE_MARGIN)

        led_half = [p for p in persp if p["led_at_half"]]
        trailed_half = [p for p in persp if p["trailed_at_half"]]
        protected = sum(1 for p in led_half if p["won"])
        comebacks = sum(1 for p in trailed_half if p["won"])

        q_nets = [[p["q_net"][i] for p in persp] for i in range(4)]

        teams_out[tri] = {
            # --- blowout / variance profile ---
            "blowout_win_pct": round(100 * wins_by_blowout / n, 1),
            "blowout_loss_pct": round(100 * loss_by_blowout / n, 1),
            "close_game_rate": round(100 * close / n, 1),
            "avg_abs_margin": round(mean(abs(p["margin"]) for p in persp), 2),
            "avg_margin": round(mean(p["margin"] for p in persp), 2),
            # --- quarter game-control (regulation, signed net pts) ---
            "q1_net": round(mean(q_nets[0]), 2),
            "q2_net": round(mean(q_nets[1]), 2),
            "q3_net": round(mean(q_nets[2]), 2),
            "q4_net": round(mean(q_nets[3]), 2),
            "h1_net": round(mean(p["h1_net"] for p in persp), 2),
            "h2_net": round(mean(p["h2_net"] for p in persp), 2),
            # --- lead protection / comeback ---
            "lead_at_half_winpct": (round(100 * protected / len(led_half), 1)
                                    if led_half else None),
            "n_led_at_half": len(led_half),
            "comeback_rate": (round(100 * comebacks / len(trailed_half), 1)
                              if trailed_half else None),
            "n_trailed_at_half": len(trailed_half),
            # --- scoring environment ---
            "total_desc": round(mean(p["total"] for p in persp), 1),
            "total_rolling_leakfree": _rolling_leakfree_total(per_team_totals[tri]),
            "total_vs_league_desc": round(mean(p["total"] for p in persp) - league_avg_total, 1),
            "n_games": n,
        }

    # league summary
    margins = [abs(g["home_final"] - g["away_final"]) for g in games]
    closes = sum(1 for m in margins if m <= CLOSE_MARGIN)
    league = {
        "avg_total": round(league_avg_total, 1),
        "blowout_rate": round(100 * league_blowouts / len(games), 1),
        "close_game_rate": round(100 * closes / len(games), 1),
        "avg_abs_margin": round(mean(margins), 2),
        "n_games": len(games),
        "blowout_margin_threshold": BLOWOUT_MARGIN,
        "close_margin_threshold": CLOSE_MARGIN,
    }

    out = {
        "meta": {
            "artifact": "game_control",
            "season": SEASON,
            "scope": "regular season (game_id prefix 00225); playoffs excluded",
            "generated": "2026-06-01",
            "source": "scouting / descriptive — NOT a betting model",
            "sources": [
                "data/nba/linescores_all.json (quarter + OT scores)",
                "data/nba/season_games_2025-26.json (team TRI, date, home_win)",
            ],
            "units": {
                "*_net": "signed point differential from the team's perspective "
                         "(team minus opponent), averaged over games (regulation "
                         "quarters; OT not attributed to a quarter)",
                "*_pct / *_rate / *winpct": "percent (0-100)",
                "avg_abs_margin / avg_margin": "final-score point margin incl. OT",
                "total_desc / total_rolling_leakfree / avg_total": "combined "
                         "both-teams final game points incl. OT",
            },
            "definitions": {
                "blowout_win_pct": ">=15-pt win as share of all games",
                "blowout_loss_pct": ">=15-pt loss as share of all games",
                "close_game_rate": "abs final margin <=5 as share of all games",
                "q1_net..q4_net": "avg per-quarter net (team minus opp), regulation",
                "h1_net": "avg first-half net; h2_net = avg regulation second-half net",
                "lead_at_half_winpct": "win% in games led at halftime (lead protection)",
                "comeback_rate": "win% in games trailed at halftime (comeback ability)",
            },
            "leak_note": (
                "total_desc is DESCRIPTIVE full-season aggregate (hindsight; a "
                "sibling agent proved using a full-season total as predictive is a "
                "leakage trap: +6.6% in-sample collapsed to -10% leak-free). "
                "total_rolling_leakfree is the leak-safe analogue: average over the "
                "team's games of the mean of STRICTLY-PRIOR games' totals (no current/"
                "future peeking). Only total_rolling_leakfree should ever inform a "
                "forward-looking total view; all other fields are descriptive scouting."
            ),
            "ot_note": (
                "OT points are a lump (home_pts_ot/away_pts_ot), included in final "
                "margin & total but NOT attributable to a quarter; per-quarter and "
                "h1/h2 nets are regulation-only."
            ),
            "caveats": [
                "Descriptive season profile of how games unfolded; not a predictor.",
                f"{skipped} played season_games rows lacked a linescore and were skipped.",
                "lead_at_half_winpct / comeback_rate exclude games tied at halftime.",
                "Quarter nets use regulation columns; a regulation tie that went to OT "
                "still shows a 0 h2 regulation net even though the game was decided in OT.",
            ],
        },
        "league": league,
        "teams": teams_out,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    return out


if __name__ == "__main__":
    out = build()
    teams = out["teams"]
    lg = out["league"]
    print(f"WROTE {OUT_PATH}")
    print(f"teams={len(teams)}  league_games={lg['n_games']}  "
          f"avg_total={lg['avg_total']}  blowout_rate={lg['blowout_rate']}%  "
          f"close_rate={lg['close_game_rate']}%")

    def top(metric, n=5, rev=True, key=None):
        kf = key or (lambda t: teams[t][metric])
        return sorted(teams, key=kf, reverse=rev)[:n]

    blow = top(None, key=lambda t: teams[t]["blowout_win_pct"] + teams[t]["blowout_loss_pct"])
    print("\nHighest-variance (blowout-prone, win%+loss% by >=15):")
    for t in blow:
        print(f"  {t}: blow_win {teams[t]['blowout_win_pct']}% + blow_loss "
              f"{teams[t]['blowout_loss_pct']}% = "
              f"{round(teams[t]['blowout_win_pct']+teams[t]['blowout_loss_pct'],1)}%, "
              f"avg_abs_margin {teams[t]['avg_abs_margin']}")

    print("\nBest Q4 (close strong):")
    for t in top("q4_net"):
        print(f"  {t}: q4_net {teams[t]['q4_net']:+.2f}")
    print("Worst Q4 (faders):")
    for t in top("q4_net", rev=False):
        print(f"  {t}: q4_net {teams[t]['q4_net']:+.2f}")

    print("\nBest lead-protectors (win% led at half, min 20 such games):")
    elig = [t for t in teams if (teams[t]["n_led_at_half"] or 0) >= 20
            and teams[t]["lead_at_half_winpct"] is not None]
    for t in sorted(elig, key=lambda t: teams[t]["lead_at_half_winpct"], reverse=True)[:5]:
        print(f"  {t}: {teams[t]['lead_at_half_winpct']}% "
              f"(n_led={teams[t]['n_led_at_half']})")

    print("\nBest comeback teams (win% trailed at half, min 20 such games):")
    elig = [t for t in teams if (teams[t]["n_trailed_at_half"] or 0) >= 20
            and teams[t]["comeback_rate"] is not None]
    for t in sorted(elig, key=lambda t: teams[t]["comeback_rate"], reverse=True)[:5]:
        print(f"  {t}: {teams[t]['comeback_rate']}% "
              f"(n_trailed={teams[t]['n_trailed_at_half']})")

    print("\nTotal: descriptive vs leak-free rolling (sample 6 teams):")
    for t in sorted(teams)[:6]:
        print(f"  {t}: desc {teams[t]['total_desc']}  "
              f"rolling_leakfree {teams[t]['total_rolling_leakfree']}")
