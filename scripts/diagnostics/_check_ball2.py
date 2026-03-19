import pandas as pd
df = pd.read_csv('data/ball_tracking.csv')
df['ball_x2d_f'] = df.ball_x2d.fillna(0).astype(float)

d1 = df[df.detected == 1]
bad = d1[d1.ball_x2d_f <= 0]
good = d1[d1.ball_x2d_f > 0]

print('detected=1 rows total:', len(d1))
print('--- BAD (x2d <= 0) ---')
print('  count:', len(bad))
print('  ball_x2d sample:', bad.ball_x2d_f.head(20).tolist())
print('  ball_x2d stats:', bad.ball_x2d_f.describe())

print('--- GOOD (x2d > 0) ---')
print('  count:', len(good))
print('  ball_x2d range:', good.ball_x2d_f.min(), '-', good.ball_x2d_f.max())
