"""
Drop a video, get everything.

Usage:
  python -m pipeline.run_all --video game.mp4
  python -m pipeline.run_all --video game.mp4 --home "Celtics" --away "Warriors"
  python -m pipeline.run_all --video game.mp4 --open   # auto-opens browser
"""
import argparse
import webbrowser
import uuid

from pipeline.ingest_game import ingest_video
from pipeline.export_data import export_game
from pipeline.generate_graphs import generate_all


def run(video: str, home: str, away: str, date: str, season: str,
        game_id: str | None, open_browser: bool) -> str:

    game_id = game_id or str(uuid.uuid4())

    print(f"\n{'='*50}")
    print(f"  Step 1/3 — Tracking + Features")
    print(f"{'='*50}")
    ingest_video(video, game_id=game_id,
                 home_team=home, away_team=away,
                 game_date=date, season=season)

    print(f"\n{'='*50}")
    print(f"  Step 2/3 — Exporting Data")
    print(f"{'='*50}")
    export_game(game_id)

    print(f"\n{'='*50}")
    print(f"  Step 3/3 — Generating Graphs")
    print(f"{'='*50}")
    generate_all(game_id)

    url = f"http://localhost:5001/game/{game_id}"
    print(f"\n✓ Done!  game_id: {game_id}")
    print(f"  Dashboard: {url}")
    print(f"  Run 'python -m frontend.app' if not already started.\n")

    if open_browser:
        webbrowser.open(url)

    return game_id


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Process a game video end-to-end")
    p.add_argument("--video",    required=True,          help="Path to video file")
    p.add_argument("--home",     default="Home",          help="Home team name")
    p.add_argument("--away",     default="Away",          help="Away team name")
    p.add_argument("--date",     default="2024-01-01",    help="Game date YYYY-MM-DD")
    p.add_argument("--season",   default="2024-25",       help="Season string")
    p.add_argument("--game-id",  default=None,            help="Reuse an existing game ID")
    p.add_argument("--open",     action="store_true",     help="Open browser when done")
    args = p.parse_args()

    run(args.video, args.home, args.away, args.date, args.season,
        args.game_id, args.open)
