"""One-shot script to fetch referee tendencies and player bio data."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.ref_tracker import scrape_ref_tendencies
from src.data.nba_tracking_stats import fetch_player_bio

print("--- Ref tendencies ---")
refs = scrape_ref_tendencies("2024-25")
print(f"Refs scraped: {len(refs)}")

print("\n--- Player bio ---")
bio = fetch_player_bio()
print(f"Players with bio: {len(bio)}")
