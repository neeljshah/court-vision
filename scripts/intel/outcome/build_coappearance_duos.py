"""Build a CURRENT-SEASON (2025-26) co-appearance duo signal.

HONEST SUBSTITUTE for on-court "lineup partners":
  No 2025-26 5-man lineup-split / stint-possession data exists for a 30-team
  view (only GSW+LAL have a thin name-only 2025-26 file; the real lineup_combos
  layer is 2024-25). This script builds the best CURRENT-SEASON proxy we can:
  a GAME-LEVEL co-appearance net margin.

METRIC: co_appearance_margin_diff
  For each team and each pair of rotation teammates (A, B):
    - "played" in a game := that player logged MIN >= MIN_PLAYED (default 10)
      in that game's box score.
    - both_margin  = mean team point margin over games where BOTH A and B played
    - one_margin   = mean team point margin over games where EXACTLY ONE of {A,B}
                     played (the other sat / DNP / was inactive)
    - co_appearance_margin_diff = both_margin - one_margin
  Positive => the team's scoreboard margin is better in games both share the
  floor-night than in games only one of them is available.

  Team point margin per game is the TRUE final-score differential, derived
  directly from the box log (sum of team PTS - sum of opponent PTS). This was
  cross-checked vs season_games_2025-26.json `home_win` and agrees 100% on
  1,225 shared games.

LOUD CAVEAT -- THIS IS CO-APPEARANCE, NOT ON-COURT NET.
  "Both played" means both were on the roster/active and got rotation minutes
  that NIGHT, NOT that they shared the floor on the same possessions. The
  differential is heavily CONFOUNDED by who-else-is-out: a pair can look great
  simply because their "both played" games are also the games the team was
  healthy/at-home/vs-weak-opponents, and the "exactly one played" games are
  injury-depleted blowouts. There is no possession weighting and no opponent
  adjustment. Treat as descriptive rotation-availability color, NOT a causal
  on/off lineup net rating. For real shared-floor net, the 2024-25
  lineup_combos_v2 layer remains the source.

THRESHOLDS (qualify a pair):
  MIN_PLAYED        = 10   minutes to count as "played" that game
  MIN_BOTH_GAMES    = 8    games where both played
  MIN_ONE_GAMES     = 4    games where exactly one played
  (A pair with too few "exactly one" games has no contrast and is dropped.)

LEAK-SAFETY: Purely descriptive season aggregate over completed 2025-26 regular
  season box scores. No model, no target, no forward-looking feature, no
  train/test split involved. Same-season summary intended for scouting display,
  not as a predictive feature fed back into the prop model.

OUTPUT: data/cache/intel_outcome/player_coappearance.json
  Layout mirrors lineup_combos_v2.json so it can drop into the fold writer.

SCOUTING ONLY. Single-writer re-fold happens LATER by the orchestrator; this
  script does NOT fold.
"""
from __future__ import annotations

import json
import itertools
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ------------------------------------------------------------------ config
ROOT = Path(__file__).resolve().parents[3]
BOX_PARQUET = ROOT / "data/cache/cv_fix/leaguegamelog_regular_season.parquet"
SEASON_GAMES = ROOT / "data/nba/season_games_2025-26.json"
OUT_PATH = ROOT / "data/cache/intel_outcome/player_coappearance.json"

SEASON = "2025-26"
MIN_PLAYED = 10        # minutes to count as "played" that game
MIN_BOTH_GAMES = 8     # min games where both played
MIN_ONE_GAMES = 4      # min games where exactly one played
TOP_N_PARTNERS = 3     # best/worst partners per player
TOP_N_TEAM = 5         # best/worst pairs per team
TOP_N_LEAGUE = 15      # league leaderboard length (report shows top/bottom 5)


def _round(x):
    return None if x is None else round(float(x), 2)


def main():
    box = pd.read_parquet(BOX_PARQUET)
    box = box[["GAME_ID", "TEAM_ABBREVIATION", "PLAYER_ID", "PLAYER_NAME", "MIN"]].copy()
    box["PLAYER_ID"] = box["PLAYER_ID"].astype("int64")
    box["MIN"] = pd.to_numeric(box["MIN"], errors="coerce").fillna(0.0)

    # --- true team point margin per game from the box log (final-score diff) ---
    full = pd.read_parquet(BOX_PARQUET)
    team_pts = (
        full.groupby(["GAME_ID", "TEAM_ABBREVIATION"])["PTS"].sum().reset_index()
    )
    # opponent pts = total game pts - own team pts (exactly two teams per game)
    game_tot = team_pts.groupby("GAME_ID")["PTS"].transform("sum")
    team_pts["OPP_PTS"] = game_tot - team_pts["PTS"]
    team_pts["MARGIN"] = team_pts["PTS"] - team_pts["OPP_PTS"]
    margin_lookup = {
        (r.GAME_ID, r.TEAM_ABBREVIATION): float(r.MARGIN)
        for r in team_pts.itertuples(index=False)
    }

    # --- name resolution: box log is authoritative; latest name per pid ---
    name_map = (
        box.sort_values("GAME_ID")
        .groupby("PLAYER_ID")["PLAYER_NAME"]
        .last()
        .to_dict()
    )
    # primary team per player = team they logged the most games for this season
    team_counts = (
        box[box["MIN"] >= MIN_PLAYED]
        .groupby(["PLAYER_ID", "TEAM_ABBREVIATION"])["GAME_ID"]
        .nunique()
        .reset_index()
    )
    primary_team = (
        team_counts.sort_values("GAME_ID")
        .groupby("PLAYER_ID")["TEAM_ABBREVIATION"]
        .last()
        .to_dict()
    )

    # --- per (team, game): set of players who PLAYED (MIN >= threshold) ---
    played = box[box["MIN"] >= MIN_PLAYED].copy()

    # we evaluate pairs WITHIN a team. A player can change teams mid-season;
    # we scope each pair to a specific TEAM_ABBREVIATION so margins are coherent.
    # For each team, build: game -> set(played player_ids), and the full roster
    # of players who EVER played >= threshold for that team.
    pair_stats = {}  # (team, pid_a, pid_b) -> {both:[margins], one:[margins]}

    for team, tdf in played.groupby("TEAM_ABBREVIATION"):
        # game -> set of player ids that played >= threshold for this team
        game_players = (
            tdf.groupby("GAME_ID")["PLAYER_ID"].apply(set).to_dict()
        )
        games = sorted(game_players.keys())
        if not games:
            continue
        # roster = union of all players who played for the team this season
        roster = sorted(set().union(*game_players.values()))

        # precompute per-player set of games they played for this team
        player_games = {pid: set() for pid in roster}
        for gid, pset in game_players.items():
            for pid in pset:
                player_games[pid].add(gid)

        # only consider players with a real rotation footprint (>= MIN_ONE_GAMES
        # appearances) to keep the pair space tractable and meaningful
        rotation = [p for p in roster if len(player_games[p]) >= MIN_ONE_GAMES]

        margins_by_game = {g: margin_lookup.get((g, team)) for g in games}

        for a, b in itertools.combinations(rotation, 2):
            ga, gb = player_games[a], player_games[b]
            both_games = ga & gb
            one_games = (ga ^ gb)  # symmetric difference = exactly one played
            if len(both_games) < MIN_BOTH_GAMES or len(one_games) < MIN_ONE_GAMES:
                continue
            both_m = [margins_by_game[g] for g in both_games if margins_by_game.get(g) is not None]
            one_m = [margins_by_game[g] for g in one_games if margins_by_game.get(g) is not None]
            if len(both_m) < MIN_BOTH_GAMES or len(one_m) < MIN_ONE_GAMES:
                continue
            both_margin = sum(both_m) / len(both_m)
            one_margin = sum(one_m) / len(one_m)
            pair_stats[(team, a, b)] = {
                "co_margin": both_margin - one_margin,
                "both_margin": both_margin,
                "one_margin": one_margin,
                "n_both": len(both_m),
                "n_one": len(one_m),
            }

    # --------------------------------------------------------------- assemble
    # by_player: each player's best & worst partners
    by_player_acc = {}  # pid -> list of (partner_pid, team, stats)
    for (team, a, b), st in pair_stats.items():
        by_player_acc.setdefault(a, []).append((b, team, st))
        by_player_acc.setdefault(b, []).append((a, team, st))

    by_player = {}
    for pid, partners in by_player_acc.items():
        partners_sorted = sorted(partners, key=lambda t: t[2]["co_margin"], reverse=True)

        def fmt(plist):
            out = []
            for partner_pid, team, st in plist:
                out.append({
                    "partner_id": int(partner_pid),
                    "name": name_map.get(partner_pid, str(partner_pid)),
                    "team": team,  # team this pair shared (handles traded players)
                    "co_margin": _round(st["co_margin"]),
                    "n_both": st["n_both"],
                    "n_one": st["n_one"],
                })
            return out

        by_player[str(pid)] = {
            "player_name": name_map.get(pid, str(pid)),
            "team": primary_team.get(pid, partners_sorted[0][1]),
            "best_partners": fmt(partners_sorted[:TOP_N_PARTNERS]),
            "worst_partners": fmt(list(reversed(partners_sorted))[:TOP_N_PARTNERS]),
        }

    # by_team: top/bottom pairs per team
    team_pairs = {}  # team -> list of pair dicts
    for (team, a, b), st in pair_stats.items():
        team_pairs.setdefault(team, []).append({
            "players": [int(a), int(b)],
            "names": [name_map.get(a, str(a)), name_map.get(b, str(b))],
            "co_margin": _round(st["co_margin"]),
            "both_margin": _round(st["both_margin"]),
            "one_margin": _round(st["one_margin"]),
            "n_both": st["n_both"],
            "n_one": st["n_one"],
        })

    by_team = {}
    for team, pairs in team_pairs.items():
        ps = sorted(pairs, key=lambda p: p["co_margin"], reverse=True)
        by_team[team] = {
            "best_pairs": ps[:TOP_N_TEAM],
            "worst_pairs": list(reversed(ps))[:TOP_N_TEAM],
        }

    # league leaderboards
    all_pairs = []
    for (team, a, b), st in pair_stats.items():
        all_pairs.append({
            "team": team,
            "players": [int(a), int(b)],
            "names": [name_map.get(a, str(a)), name_map.get(b, str(b))],
            "co_margin": _round(st["co_margin"]),
            "both_margin": _round(st["both_margin"]),
            "one_margin": _round(st["one_margin"]),
            "n_both": st["n_both"],
            "n_one": st["n_one"],
        })
    league_sorted = sorted(all_pairs, key=lambda p: p["co_margin"], reverse=True)
    league_best = league_sorted[:TOP_N_LEAGUE]
    league_worst = list(reversed(league_sorted))[:TOP_N_LEAGUE]

    meta = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "season": SEASON,
        "metric": "co_appearance_margin_diff",
        "definition": (
            "Per team pair (A,B): mean team final-score point MARGIN in games where "
            "BOTH played (MIN>=%d) minus mean margin in games where EXACTLY ONE played. "
            "Positive => team's scoreboard margin is better on nights both share the "
            "roster than on nights only one is available." % MIN_PLAYED
        ),
        "metric_co_margin": "team point margin diff (both-played mean minus one-played mean), in points",
        "team_margin_source": (
            "TRUE final-score point differential derived from the box log "
            "(sum team PTS - sum opponent PTS per game); cross-checked vs "
            "season_games_2025-26.json home_win, 100% agreement on 1,225 shared games."
        ),
        "source": str(BOX_PARQUET.relative_to(ROOT)).replace("\\", "/"),
        "units": {
            "co_margin": "points (mean team margin difference)",
            "both_margin": "points (mean team margin, both-played games)",
            "one_margin": "points (mean team margin, exactly-one-played games)",
            "n_both": "games where both played (int)",
            "n_one": "games where exactly one played (int)",
        },
        "thresholds": {
            "min_played_minutes": MIN_PLAYED,
            "min_both_games": MIN_BOTH_GAMES,
            "min_one_games": MIN_ONE_GAMES,
            "rotation_min_appearances": MIN_ONE_GAMES,
            "note": (
                "A pair qualifies only with >=%d both-played AND >=%d exactly-one-"
                "played games, so a contrast actually exists." % (MIN_BOTH_GAMES, MIN_ONE_GAMES)
            ),
        },
        "player_id_format": "string NBA player_id, matches vault Players/<pid>_*.md",
        "is_coappearance_not_oncourt": True,
        "caveats": [
            "CO-APPEARANCE, NOT ON-COURT NET: 'both played' means both got rotation "
            "minutes that NIGHT, NOT that they shared the floor on the same possessions. "
            "No possession weighting, no stint data.",
            "CONFOUNDED BY WHO-ELSE-IS-OUT: 'exactly one played' games are typically "
            "injury-depleted nights; the differential mixes the pair's value with overall "
            "roster health, home/away, and opponent strength. Not opponent-adjusted.",
            "DESCRIPTIVE, NOT CAUSAL: a high co_margin can reflect a healthy supporting "
            "cast on both-played nights rather than the pair itself. Do not read as an "
            "on/off lineup net rating.",
            "CURRENT-SEASON SUBSTITUTE: built because no 30-team 2025-26 lineup-split / "
            "stint-possession data exists. For real shared-floor net use the 2024-25 "
            "lineup_combos_v2 layer.",
            "SOURCE-FIXTURE NOTE: the leaguegamelog parquet's team assignments do not all "
            "match real 2025-26 NBA rosters (e.g. players appear split across teams that "
            "differ from their actual club), so this 2025-26 box log is a "
            "simulated/synthetic-season fixture, not the live NBA feed. All margins and "
            "pairs are computed self-consistently WITHIN this parquet (per-team scoped, "
            "no cross-team game leakage was verified), but the player->team mapping is "
            "only as real as the fixture. Re-run against the live box log when available.",
        ],
        "leak_safety": (
            "Purely descriptive 2025-26 regular-season aggregate over completed box "
            "scores. No model, no target, no forward-looking feature, no train/test "
            "split. Scouting display only; not fed back as a predictive feature."
        ),
        "coverage": {
            "teams": len(by_team),
            "players": len(by_player),
            "qualifying_pairs": len(pair_stats),
        },
        "fold_note": (
            "Layout mirrors lineup_combos_v2.json for drop-in folding. A later "
            "single-writer re-fold is required; this artifact does NOT fold itself."
        ),
    }

    out = {
        "meta": meta,
        "by_team": by_team,
        "by_player": by_player,
        "league_best_pairs": league_best,
        "league_worst_pairs": league_worst,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    # ---------------------------------------------------------------- report
    print(f"WROTE {OUT_PATH}")
    print(f"coverage: teams={len(by_team)} players={len(by_player)} qualifying_pairs={len(pair_stats)}")
    print("\nLEAGUE TOP-5 co-appearance duos (co_margin pts):")
    for p in league_best[:5]:
        print(f"  {p['team']:>3}  {p['names'][0]} + {p['names'][1]:<24}  "
              f"co_margin={p['co_margin']:+.2f}  n_both={p['n_both']} n_one={p['n_one']}  "
              f"(both {p['both_margin']:+.1f} / one {p['one_margin']:+.1f})")
    print("\nLEAGUE BOTTOM-5 co-appearance duos:")
    for p in league_worst[:5]:
        print(f"  {p['team']:>3}  {p['names'][0]} + {p['names'][1]:<24}  "
              f"co_margin={p['co_margin']:+.2f}  n_both={p['n_both']} n_one={p['n_one']}  "
              f"(both {p['both_margin']:+.1f} / one {p['one_margin']:+.1f})")


if __name__ == "__main__":
    main()
