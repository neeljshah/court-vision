import pandas as pd
df = pd.read_csv('data/tracking_data.csv')
print('Total tracking rows:', len(df))

# bos_mia_playoffs started at frame 1388 and ended at ~3778
# But earlier runs had different frame numbers. Let's look at the tail (most recent run)
# Actually, find rows with frame >= 3000 (which would only be from bos_mia_playoffs run)
recent = df[df.frame >= 1388].tail(3000)
print('Recent rows (frame>=1388, last 3000):', len(recent))

xpos = recent.x_position.fillna(0).astype(float)
print('x_position: mean=', round(xpos.mean(), 1), 'zero_pct=', round((xpos == 0).mean(), 3))
print('x_position values near 0:', (xpos.between(-10, 10)).sum())

# What does ball_x2d look like in tracking_data?
if 'ball_x2d' in df.columns:
    bx = recent.ball_x2d.fillna(0).astype(float)
    print('ball_x2d > 0:', (bx > 0).sum(), '/', len(recent))
    print('ball_x2d == 0:', (bx == 0).sum())
