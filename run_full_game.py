"""Run the full 2016 Finals Game 7 through the pipeline."""
import sys, os, time

# Unbuffered log file so we can tail progress
_LOG = open("data/full_game_run.log", "w", buffering=1)
class _Tee:
    def __init__(self, *files): self._files = files
    def write(self, s):
        for f in self._files:
            f.write(s); f.flush()
    def flush(self):
        for f in self._files: f.flush()
sys.stdout = _Tee(sys.__stdout__, _LOG)
sys.stderr = _Tee(sys.__stderr__, _LOG)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VIDEO = "data/videos/cavs_vs_celtics_2025.mp4"
GAME_ID = "0022400710"  # CLE vs BOS, Feb 04 2025 — verified in gamelogs_all_2024-25.json

# Full 2016 Finals G7 (uncomment for overnight run — use after cavs_vs_celtics validates pipeline)
# VIDEO = "data/videos/[FULL GAME] Cleveland Cavaliers vs. Golden State Warriors \uff5c 2016 NBA Finals Game 7 \uff5c NBA on ESPN.mp4"
# GAME_ID = "0022400307"  # CLE vs BOS Dec 01 2024 — closest season matchup in DB

if not os.path.exists(VIDEO):
    print(f"ERROR: video not found: {VIDEO}")
    sys.exit(1)

print(f"Running full game pipeline:")
print(f"  Video: {os.path.basename(VIDEO)}")
print(f"  Game ID: {GAME_ID}")

from src.pipeline.unified_pipeline import UnifiedPipeline

pipe = UnifiedPipeline(
    video_path=VIDEO,
    game_id=GAME_ID,
    show=False,
)

t0 = time.time()
results = pipe.run()
elapsed = time.time() - t0

print(f"\nDone in {elapsed/60:.1f} min")
print(f"Total frames processed: {results.get('total_frames', '?')}")
print(f"Tracking rows: {results.get('tracking_rows', '?')}")
print(f"Possessions: {results.get('possession_rows', '?')}")
print(f"Shots: {results.get('shot_rows', '?')}")
