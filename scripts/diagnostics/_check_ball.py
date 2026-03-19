import pandas as pd
df = pd.read_csv('data/ball_tracking.csv')
print('Total rows:', len(df))
print('detected=1:', (df.detected==1).sum())
valid = (df.ball_x2d.fillna(0).astype(float) > 0).sum()
print('ball_x2d > 0:', valid, f'= {valid/len(df):.1%}')
d1 = df[df.detected==1]
bad = (d1.ball_x2d.fillna(0).astype(float) <= 0).sum()
print('detected=1 but ball_x2d<=0:', bad)
