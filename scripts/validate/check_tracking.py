"""
Quick visual check of tracking data correctness.
Plots player positions on court map and saves to data/tracking_check.png
"""
import pandas as pd
import numpy as np
import cv2

df = pd.read_csv("data/tracking_data.csv")
court = cv2.imread("resources/2d_map.png")

x_min, x_max = df.x_position.min(), df.x_position.max()
y_min, y_max = df.y_position.min(), df.y_position.max()
ch, cw = court.shape[:2]

print(f"Court image: {cw}w x {ch}h")
print(f"Data x range: {x_min:.0f} - {x_max:.0f}")
print(f"Data y range: {y_min:.0f} - {y_max:.0f}")
print(f"Scale factors: x={cw/(x_max-x_min):.3f}, y={ch/(y_max-y_min):.3f}")

# Scale positions to court image dimensions
def to_court_px(x, y):
    px = int((x - x_min) / (x_max - x_min) * (cw - 1))
    py = int((y - y_min) / (y_max - y_min) * (ch - 1))
    return px, py

COLORS = {"green": (0, 200, 0), "white": (230, 230, 230), "referee": (128, 128, 128)}

# Draw heatmap canvas (darker court for visibility)
canvas = (court * 0.4).astype(np.uint8)

# Sample every 5th frame so it's not too cluttered
sampled = df[df.frame % 5 == 0]

for _, row in sampled.iterrows():
    px, py = to_court_px(row.x_position, row.y_position)
    color = COLORS.get(row.team, (255, 0, 0))
    cv2.circle(canvas, (px, py), 5, color, -1)

# Draw frame 0 positions larger for reference
frame0 = df[df.frame == df.frame.min()]
for _, row in frame0.iterrows():
    px, py = to_court_px(row.x_position, row.y_position)
    color = COLORS.get(row.team, (255, 0, 0))
    cv2.circle(canvas, (px, py), 12, color, 2)
    cv2.putText(canvas, f"p{row.player_id}", (px+5, py-5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

cv2.imwrite("data/tracking_check.png", canvas)
print("\nSaved: data/tracking_check.png")
print("Open it and check: do the dots form court-shaped clusters?")
print()

# Stats
print("=== Per-team count ===")
print(df.groupby("team").size())
print()
print("=== Avg players per frame ===")
print(df.groupby(["frame","team"]).size().unstack(fill_value=0).mean().round(1))
print()
print("=== Velocity sanity (should be < 100px/frame for realistic motion) ===")
print(df.velocity.describe().round(1))
