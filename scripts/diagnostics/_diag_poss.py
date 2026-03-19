import csv
rows = list(csv.DictReader(open('data/tracking_data.csv')))
poss_rows = [r for r in rows if r.get('ball_possession') in ('1','True','true')]
print(f'Possession rows: {len(poss_rows)} / {len(rows)}')
for r in poss_rows[:8]:
    bx = float(r.get('ball_x2d') or 0)
    by = float(r.get('ball_y2d') or 0)
    px = float(r.get('x_position') or 0)
    py = float(r.get('y_position') or 0)
    dist = ((bx-px)**2+(by-py)**2)**0.5
    vel = float(r.get('ball_velocity') or 0)
    print(f"  ball=({bx:.0f},{by:.0f}) player=({px:.0f},{py:.0f}) dist={dist:.1f} vel={vel:.2f} event={r.get('event')}")
