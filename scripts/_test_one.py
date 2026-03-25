"""Quick single-game test — 500 frames only."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.unified_pipeline import UnifiedPipeline

video = "data/videos/lal_sas_2025.mp4"
game_id = "0022400015"

print(f"Testing pipeline on {video} (500 frames)...")
t0 = time.time()
try:
    p = UnifiedPipeline(
        video_path=video,
        yolo_weight_path=None,
        max_frames=500,
        show=False,
        game_id=game_id,
    )
    result = p.run()
    elapsed = time.time() - t0
    fps = result.get("total_frames", 0) / max(elapsed, 1)
    print(f"SUCCESS: {result.get('total_frames')} frames @ {fps:.1f} fps")
    print(f"  stability={result.get('stability')}")
    print(f"  id_switches={result.get('id_switches')}")
    print(f"  duration={elapsed:.1f}s")
except Exception as e:
    import traceback
    print(f"FAILED: {e}")
    traceback.print_exc()
