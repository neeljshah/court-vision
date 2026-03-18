"""Benchmark pipeline fps on a clip."""
import time
import sys
import subprocess

video = "data/videos/cavs_vs_celtics_2025.mp4"
game_id = "0022400710"

print(f"Benchmarking: {video}")
print(f"Game ID: {game_id}")
print("Running pipeline...\n")

start = time.time()
result = subprocess.run(
    [
        sys.executable,
        "src/pipeline/unified_pipeline.py",
        "--video", video,
        "--game-id", game_id,
        "--no-show",
    ],
    capture_output=True,
    text=True,
)
elapsed = time.time() - start

print("STDOUT (last 50 lines):")
lines = result.stdout.strip().split('\n')
for line in lines[-50:]:
    print(line)

if result.stderr:
    print("\nSTDERR (last 20 lines):")
    errlines = result.stderr.strip().split('\n')
    for line in errlines[-20:]:
        print(line)

print(f"\nTotal wall time: {elapsed:.1f}s ({elapsed/60:.1f}min)")
print(f"Return code: {result.returncode}")

# Try to extract frame count from output
import re
frame_matches = re.findall(r'[Ff]rame[s]?\s*[:\s]\s*(\d+)', result.stdout + result.stderr)
if frame_matches:
    frames = int(frame_matches[-1])
    fps = frames / elapsed
    print(f"\nBenchmark: {fps:.1f} fps, {frames} total frames, {elapsed/60:.1f} minutes")
else:
    # Try to get frame count from ffprobe
    r2 = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-select_streams', 'v:0',
         '-count_packets', '-show_entries', 'stream=nb_read_packets',
         '-of', 'csv=p=0', video],
        capture_output=True, text=True
    )
    try:
        frames = int(r2.stdout.strip())
        fps = frames / elapsed
        print(f"\nBenchmark: {fps:.1f} fps, {frames} total frames (ffprobe), {elapsed/60:.1f} minutes")
    except Exception:
        print("\nCould not determine frame count from output.")
        print(f"Wall time only: {elapsed:.1f}s ({elapsed/60:.1f}min)")
