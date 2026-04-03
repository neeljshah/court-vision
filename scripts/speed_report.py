import csv, os
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

rows = []
with open(os.path.join(PROJECT_DIR, 'data', 'phase_g_metrics.csv')) as f:
    for r in csv.DictReader(f):
        try:
            frames = int(r['frames'])
            dur = float(r['duration_s'])
            fps = frames / dur
            # Exclude: <1000 frames (failed/skipped), >100fps (preflight bail/bad video)
            if frames > 1000 and dur > 100 and fps < 100:
                rows.append({'game': r['game_key'], 'frames': frames,
                             'dur_s': dur, 'fps': fps})
        except Exception:
            pass

rows.sort(key=lambda x: x['fps'])
print(f"{'Game':<16} {'Frames':>8} {'Duration':>10} {'Video FPS':>10} {'vs realtime':>12}")
print('-' * 60)
for r in rows:
    mins = r['dur_s'] / 60
    rt = r['fps'] / 30.0
    flag = '  SLOW' if rt < 0.7 else ('  FAST' if rt > 1.2 else '')
    print(f"{r['game']:<16} {r['frames']:>8,} {mins:>8.1f}min  {r['fps']:>8.1f}fps  {rt:>6.2f}x{flag}")

fps_vals = [r['fps'] for r in rows]
avg = sum(fps_vals) / len(fps_vals)
print(f"\nReal broadcast games : {len(rows)}")
print(f"Avg throughput       : {avg:.1f} video-fps  ({avg/3:.1f} pipeline iters/sec at stride=3)")
print(f"Range                : {min(fps_vals):.1f} – {max(fps_vals):.1f} fps")

print(f"\n--- 10-min clip (18,000 frames @ 30fps) ---")
print(f"  Average  : {18000/avg/60:.1f} min")
print(f"  Slowest  : {18000/min(fps_vals)/60:.1f} min")
print(f"  Fastest  : {18000/max(fps_vals)/60:.1f} min")
print(f"  --parallel 2 avg   : ~{18000/avg/60/2:.1f} min per game (wall clock)")

print(f"\n--- Full game (~130 min, ~234,000 frames) ---")
full = 234000
print(f"  Average  : {full/avg/3600:.1f} hr")
print(f"  Slowest  : {full/min(fps_vals)/3600:.1f} hr")
print(f"  Fastest  : {full/max(fps_vals)/3600:.1f} hr")
print(f"  --parallel 2 avg   : ~{full/avg/3600/2:.1f} hr (wall clock)")
