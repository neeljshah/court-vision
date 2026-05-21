"""
nba_stats_ingester.py — Backfill and incremental NBA box scores + play-by-play
into data-lake tables `box_scores` and `play_by_play`, resumable via `scraper_runs`.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Optional

from src.data.nba_stats import fetch_full_boxscore  # installs configured session
from src.data.nba_enricher import fetch_playbyplay
from src.data.db import get_connection, execute_batch

log = logging.getLogger(__name__)

_EVENT_LABELS: dict[int, str] = {
    0: "other", 1: "shot_made", 2: "shot_missed", 3: "free_throw",
    4: "rebound", 5: "turnover", 6: "foul", 8: "sub", 13: "period_end",
}

_BOX_SQL = """
INSERT INTO box_scores
    (sport,game_id,player_id,team_id,game_date,season,minutes,points,rebounds,
     assists,steals,blocks,turnovers,fouls,fg_made,fg_attempted,fg3_made,
     fg3_attempted,ft_made,ft_attempted,plus_minus,extras)
VALUES
    (%(sport)s,%(game_id)s,%(player_id)s,%(team_id)s,%(game_date)s,%(season)s,
     %(minutes)s,%(points)s,%(rebounds)s,%(assists)s,%(steals)s,%(blocks)s,
     %(turnovers)s,%(fouls)s,%(fg_made)s,%(fg_attempted)s,%(fg3_made)s,
     %(fg3_attempted)s,%(ft_made)s,%(ft_attempted)s,%(plus_minus)s,%(extras)s)
ON CONFLICT DO NOTHING
"""

_PBP_SQL = """
INSERT INTO play_by_play
    (sport,game_id,event_num,period,clock_seconds,event_type,event_desc,
     player_id,team_id,home_score,away_score,extras)
VALUES
    (%(sport)s,%(game_id)s,%(event_num)s,%(period)s,%(clock_seconds)s,
     %(event_type)s,%(event_desc)s,%(player_id)s,%(team_id)s,
     %(home_score)s,%(away_score)s,%(extras)s)
ON CONFLICT DO NOTHING
"""

_RUN_INS = """
INSERT INTO scraper_runs (id,sport,source,run_type,status,rows_written,last_key)
VALUES (%(id)s,%(sport)s,%(source)s,%(run_type)s,%(status)s,%(rows_written)s,%(last_key)s)
"""

_RUN_UPD = """
UPDATE scraper_runs
SET status=%(status)s,rows_written=%(rows_written)s,last_key=%(last_key)s,
    run_finished_at=CURRENT_TIMESTAMP
WHERE id=%(id)s
"""


def _parse_score(score_str: str) -> tuple[Optional[int], Optional[int]]:
    """Parse '105-98' → (105, 98). Returns (None, None) on failure."""
    if not score_str or "-" not in score_str:
        return None, None
    parts = score_str.split("-", 1)
    try:
        return int(parts[0]), int(parts[1])
    except (ValueError, TypeError):
        return None, None


class NBAStatsIngester:
    """Ingest NBA box scores and play-by-play into the data lake."""

    def __init__(self, sport: str = "nba", rate_limit_s: float = 1.5) -> None:
        self.sport = sport
        self.rate_limit_s = rate_limit_s

    def list_season_games(self, season: str) -> list[dict]:
        """
        Return all regular-season home games for the given NBA season.

        Args:
            season: NBA season string e.g. '2024-25'.

        Returns:
            List of {'game_id': str, 'game_date': str} sorted by date ascending.
        """
        from nba_api.stats.endpoints.leaguegamefinder import LeagueGameFinder
        finder = LeagueGameFinder(
            season_nullable=season,
            season_type_nullable="Regular Season",
            league_id_nullable="00",
        )
        df = finder.get_data_frames()[0]
        home = df[df["MATCHUP"].str.contains("vs\\.", na=False)].sort_values("GAME_DATE")
        return [
            {"game_id": str(r["GAME_ID"]), "game_date": str(r["GAME_DATE"])}
            for _, r in home.iterrows()
        ]

    def ingest_game(self, game_id: str, game_date: str, season: str) -> tuple[int, int]:
        """
        Fetch and store box score + play-by-play for one game.

        Args:
            game_id:   NBA Stats game ID.
            game_date: ISO date string for the game.
            season:    Season string e.g. '2024-25'.

        Returns:
            (box_rows_inserted, pbp_rows_inserted)
        """
        conn = get_connection()
        try:
            cur = conn.cursor()

            # ── Box score ──────────────────────────────────────────────────────
            bs = fetch_full_boxscore(game_id)
            box_params = []
            if bs and bs.get("players"):
                for p in bs["players"]:
                    box_params.append({
                        "sport": self.sport, "game_id": game_id,
                        "player_id": str(p["player_id"]),
                        "team_id": p.get("team_abbreviation"),
                        "game_date": game_date, "season": season,
                        "minutes": p.get("min"), "points": p.get("pts"),
                        "rebounds": p.get("reb"), "assists": p.get("ast"),
                        "steals": p.get("stl"), "blocks": p.get("blk"),
                        "turnovers": p.get("tov"), "fouls": p.get("pf"),
                        "fg_made": p.get("fgm"), "fg_attempted": p.get("fga"),
                        "fg3_made": p.get("fg3m"), "fg3_attempted": p.get("fg3a"),
                        "ft_made": p.get("ftm"), "ft_attempted": p.get("fta"),
                        "plus_minus": p.get("plus_minus"),
                        "extras": json.dumps({
                            "starter": p.get("starter"), "oreb": p.get("oreb"),
                            "dreb": p.get("dreb"), "jersey_num": p.get("jersey_num"),
                            "home_team": bs.get("home_team"), "away_team": bs.get("away_team"),
                            "home_score": bs.get("home_score"), "away_score": bs.get("away_score"),
                        }),
                    })
                execute_batch(cur, _BOX_SQL, box_params)

            # ── Play-by-play — periods 1-4, then overtime until empty ─────────
            pbp_params: list[dict] = []
            event_num = 0
            for period in range(1, 20):
                events = fetch_playbyplay(game_id, period)
                if not events and period > 4:
                    break
                for ev in events:
                    hs, as_ = _parse_score(ev.get("score", ""))
                    pbp_params.append({
                        "sport": self.sport, "game_id": game_id,
                        "event_num": event_num,
                        "period": ev.get("period"),
                        "clock_seconds": ev.get("game_clock_sec"),
                        "event_type": _EVENT_LABELS.get(ev.get("event_type", 0), "other"),
                        "event_desc": ev.get("event_desc"),
                        "player_id": None,
                        "team_id": ev.get("team_abbrev"),
                        "home_score": hs, "away_score": as_,
                        "extras": json.dumps({
                            "player_name": ev.get("player_name"),
                            "score_margin": ev.get("score_margin"),
                            "raw_event_type": ev.get("event_type"),
                        }),
                    })
                    event_num += 1
                if period <= 4 and not events:
                    continue  # tolerate missing regular periods, stop OT on empty

            if pbp_params:
                execute_batch(cur, _PBP_SQL, pbp_params)
            conn.commit()
        finally:
            conn.close()

        return len(box_params), len(pbp_params)

    def backfill(
        self,
        season: str,
        limit: Optional[int] = None,
        resume_from: Optional[str] = None,
    ) -> dict:
        """
        Backfill all games for a season, resumable via resume_from.

        Args:
            season:      NBA season string e.g. '2024-25'.
            limit:       Cap number of games to process.
            resume_from: game_id — slice to games strictly after this id.

        Returns:
            Summary dict: run_id, games_processed, box_rows, pbp_rows, status, errors.
        """
        games = self.list_season_games(season)
        if resume_from:
            ids = [g["game_id"] for g in games]
            try:
                games = games[ids.index(resume_from) + 1:]
            except ValueError:
                pass
        if limit:
            games = games[:limit]

        run_id = str(uuid.uuid4())
        conn = get_connection()
        try:
            conn.cursor().execute(_RUN_INS, {
                "id": run_id, "sport": self.sport, "source": "nba_api",
                "run_type": "backfill", "status": "running",
                "rows_written": 0, "last_key": None,
            })
            conn.commit()
        finally:
            conn.close()

        total_box = total_pbp = 0
        errors: list[str] = []
        last_game_id: Optional[str] = None

        for game in games:
            gid = game["game_id"]
            time.sleep(self.rate_limit_s)
            try:
                box, pbp = self.ingest_game(gid, game["game_date"], season)
                total_box += box
                total_pbp += pbp
                last_game_id = gid
                log.info("ingested %s: box=%d pbp=%d", gid, box, pbp)
            except Exception as exc:
                log.error("failed %s: %s", gid, exc)
                errors.append(f"{gid}: {exc}")
                continue

            conn = get_connection()
            try:
                conn.cursor().execute(_RUN_UPD, {
                    "id": run_id, "status": "running",
                    "rows_written": total_box + total_pbp, "last_key": last_game_id,
                })
                conn.commit()
            finally:
                conn.close()

        final_status = "partial" if errors else "success"
        conn = get_connection()
        try:
            conn.cursor().execute(_RUN_UPD, {
                "id": run_id, "status": final_status,
                "rows_written": total_box + total_pbp, "last_key": last_game_id,
            })
            conn.commit()
        finally:
            conn.close()

        return {
            "run_id": run_id, "games_processed": len(games) - len(errors),
            "box_rows": total_box, "pbp_rows": total_pbp,
            "status": final_status, "errors": errors,
        }

    def incremental(self, season: str) -> dict:
        """
        Resume ingestion from the last successful/partial run's last_key.

        Args:
            season: NBA season string e.g. '2024-25'.

        Returns:
            Summary dict from backfill.
        """
        conn = get_connection()
        last_key: Optional[str] = None
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT last_key FROM scraper_runs
                   WHERE sport=%(sport)s AND source=%(source)s
                     AND status IN ('success','partial')
                   ORDER BY run_started_at DESC LIMIT 1""",
                {"sport": self.sport, "source": "nba_api"},
            )
            row = cur.fetchone()
            if row:
                last_key = row[0]
        finally:
            conn.close()
        return self.backfill(season, resume_from=last_key)
