import pandas as pd
df = pd.read_csv('data/ball_tracking.csv')
df['detected'] = df['detected'].astype(int)
df_sorted = df.sort_values('frame')

# Find the big no-detection runs and when they occur
runs = []
cur_det = df_sorted['detected'].iloc[0]
cur_start = df_sorted['frame'].iloc[0]
cur_len = 1
for i in range(1, len(df_sorted)):
    d = df_sorted['detected'].iloc[i]
    f = df_sorted['frame'].iloc[i]
    if d == cur_det:
        cur_len += 1
    else:
        runs.append((cur_det, cur_len, cur_start, f - 1))
        cur_det = d
        cur_start = f
        cur_len = 1
runs.append((cur_det, cur_len, cur_start, df_sorted['frame'].iloc[-1]))

print('Detection pattern (det, length, start_frame, end_frame):')
for r in runs:
    print(f'  det={r[0]}  len={r[1]:4d}  frames {r[2]}-{r[3]}')
