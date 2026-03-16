"""Temporary verification script for player_identity.py — safe to delete."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.player_identity import persist_identity_map, update_tracking_frames, load_identity_map
print("Import OK — all 3 functions importable")
print(f"  persist_identity_map: {callable(persist_identity_map)}")
print(f"  update_tracking_frames: {callable(update_tracking_frames)}")
print(f"  load_identity_map: {callable(load_identity_map)}")
sys.exit(0)
