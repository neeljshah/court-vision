"""assemble(home, away, date) -> one JSON-able dict: every activated piece of
intelligence for one NBA matchup. Read-only composition only -- no new
modeling, no fitting. Unknown team/date returns a clear {"error": ...} dict
instead of raising, so cli.py can print a clean message.
"""
from __future__ import annotations

from typing import Any, Dict

from scripts.platformkit.gamebrief import elo as elo_mod
from scripts.platformkit.gamebrief import honesty, sections_intel, sections_team, sources, team_ids


def assemble(home: str, away: str, date: str) -> Dict[str, Any]:
    home, away = str(home).upper(), str(away).upper()
    for abbr in (home, away):
        if not team_ids.is_known_abbr(abbr):
            return {"error": f"unknown NBA team abbreviation: {abbr!r}"}

    games_df = sources.games()
    if games_df is None:
        return {"error": "data/domains/basketball_nba/games.parquet not found"}

    elo = elo_mod.pregame_prob(games_df, home, away, date)
    if elo is None:
        return {"error": f"no game found for {away} @ {home} on {date}"}

    home_id, away_id = team_ids.team_id_for(home), team_ids.team_id_for(away)
    box = sources.player_boxscores()

    def team_block(team: str, team_id) -> Dict[str, Any]:
        top3 = sections_team.top3_fga(box, team, date)
        return {
            "top3_fga_season_to_date": top3,
            "injuries": sections_team.injury_section(team, date, top3),
            "news": sections_team.news_section(team, date),
            "gravity": sections_intel.gravity_leaders(team_id),
            "lineup_synergy": sections_intel.lineup_synergy_top(team_id),
            "on_off": sections_intel.on_off_top(team_id),
            "shooting_luck_last5": sections_intel.shooting_luck(team_id, games_df, date),
        }

    return {
        "matchup": {"home": home, "away": away, "date": str(date), "game_id": elo["game_id"]},
        "elo_win_prob": elo,
        "rest_and_schedule": sections_team.rest_and_schedule(games_df, home, away, date),
        "teams": {home: team_block(home, home_id), away: team_block(away, away_id)},
        "concession_matchup": sections_intel.concession_matchup(home, away, home_id, away_id),
        "honesty_labels": {
            "gravity": honesty.label_for_section("gravity"),
            "lineup_synergy": honesty.label_for_section("lineup_spacing"),
            "on_off": honesty.label_for_section("on_off"),
            "shooting_luck": honesty.label_for_section("shooting"),
            "concession_matchup": honesty.label_for_section("concession"),
        },
    }
