import pandas as pd
df = pd.read_csv('data/ball_tracking.csv')
df['detected'] = df['detected'].astype(int)

runs = []
cur_det = df['detected'].iloc[0]
cur_len = 1
for d in df['detected'].iloc[1:]:
    if d == cur_det:
        cur_len += 1
    else:
        runs.append((cur_det, cur_len))
        cur_det = d
        cur_len = 1
runs.append((cur_det, cur_len))

no_det_runs = sorted([r[1] for r in runs if r[0] == 0], reverse=True)
print('No-detection run lengths (top 15):', no_det_runs[:15])
print('Total no-detect runs:', len(no_det_runs))
print('Total frames:', len(df))
print('Detected:', df.detected.sum(), '/', len(df))
print('Avg no-det run length:', round(sum(no_det_runs)/len(no_det_runs), 1) if no_det_runs else 0)
print('Pct of frames in no-det runs > 30 frames:',
      round(sum(r for r in no_det_runs if r > 30) / len(df), 3))
