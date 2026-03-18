import csv, sys, collections, statistics
sys.stdout.reconfigure(encoding='utf-8')
rows = list(csv.DictReader(open('data/tracking_data.csv', encoding='utf-8')))
print('total rows:', len(rows))
if not rows:
    print('NO DATA'); exit()
frames = collections.Counter(r['frame'] for r in rows)
vals = sorted(frames.values())
avg = sum(vals)/len(vals)
print(f'frames: {len(frames)} avg_players={avg:.2f} max={vals[-1]} median={vals[len(vals)//2]}')
pct10 = sum(1 for v in vals if v >= 10)/len(vals)
print(f'pct_frames_10+: {pct10:.1%}')
events = collections.Counter(r.get('event','') for r in rows)
print('events:', dict(events))
bvels = [float(r.get('ball_velocity','0') or 0) for r in rows]
print(f'ball_vel max: {max(bvels):.0f} median: {statistics.median(bvels):.1f}')
bx = [float(r.get('ball_x2d','0') or 0) for r in rows if r.get('ball_x2d','') not in ('','None')]
if bx: print(f'ball_x2d range: {min(bx):.0f} to {max(bx):.0f}')
teams = collections.Counter(r.get('team','') for r in rows)
print('teams:', dict(teams))
