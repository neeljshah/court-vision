"""Profile what's slow in atl_ind_2025 pipeline run."""
import sys, time, cProfile, pstats, io
sys.path.insert(0, '.')

from src.pipeline.unified_pipeline import UnifiedPipeline

prof = cProfile.Profile()
prof.enable()

pipeline = UnifiedPipeline(
    video_path='data/videos/atl_ind_2025.mp4',
    max_frames=100,
    show=False,
)
results = pipeline.run()

prof.disable()

s = io.StringIO()
ps = pstats.Stats(prof, stream=s).sort_stats('cumulative')
ps.print_stats(20)
print(s.getvalue())
print(f"\ntotal_frames={results['total_frames']}  fps estimate={results['total_frames']/results.get('elapsed',1):.1f}")
