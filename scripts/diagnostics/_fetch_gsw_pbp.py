"""Fetch GSW Lakers PBP for game 0022401117."""
import sys
sys.path.insert(0, "C:/Users/neelj/nba-ai-system")
from src.data.pbp_scraper import scrape_game_pbp
rows = scrape_game_pbp("0022401117", force=False)
print(f"GSW PBP: {len(rows)} rows cached")
