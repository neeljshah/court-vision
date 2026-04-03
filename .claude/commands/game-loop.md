# CourtVision — Full Game Loop with Accuracy Validation

One iteration: pick next game → run tracker → validate accuracy against NBA API → apply smart fallbacks → fix one CV issue → check today's lines → write report.
Be terse. No explanations. Act.

---

## PHASE 1 — Pick next game to process

**Check what's already clean vs still needed:**
```bash
conda run -n basketball_ai bash -c "cd /c/Users/neelj/nba-ai-system && python scripts/audit_phase_g.py" 2>&1 | tail -40
```

**Priority queue** (process in this order — skip already-clean games):
1. Unprocessed games with videos: `0022401183 0022401185 0022401190 0022401194 0022401196 0022401198`
2. 60fps games: `0022400689 0022400690`
3. Partial reprocesses: `0022400625 0022400687`

Pick the first game from the queue that has a `.mp4` in `data/videos/full_games/`:
```bash
ls data/videos/full_games/*.mp4 2>/dev/null
```

Set `$GAME_ID` and `$CLIP` from the filename. If no video exists at all, skip to Phase 5.

---

## PHASE 2 — Run full tracking pipeline

```bash
conda run -n basketball_ai bash -c "cd /c/Users/neelj/nba-ai-system && python scripts/run_phase_g.py --game-ids $GAME_ID --frames 18000" 2>&1 | tail -30
```

Wait for completion. Check `data/tracking/$GAME_ID/run.log` for errors:
```bash
tail -20 data/tracking/$GAME_ID/run.log 2>/dev/null || echo "no log"
```

---

## PHASE 3 — Accuracy validation: CV vs NBA API

This is the core accuracy check. For every metric, compare what the tracker produced against ground truth from the NBA Stats API.

### 3A — Pull NBA ground truth for this game
```python
# Run this inline Python to get box score + shot chart ground truth
import sys, json, os
sys.path.insert(0, '/c/Users/neelj/nba-ai-system')
from nba_api.stats.endpoints import boxscoretraditionalv2, shotchartdetail
import time

game_id = "$GAME_ID"

# Box score: per-player FGA, PTS, REB, AST, MIN
time.sleep(0.6)
bs = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
players_df = bs.get_data_frames()[0]
teams_df   = bs.get_data_frames()[1]

# Save for cross-reference
players_df.to_csv(f'data/tracking/{game_id}/nba_boxscore_players.csv', index=False)
teams_df.to_csv(f'data/tracking/{game_id}/nba_boxscore_teams.csv', index=False)

total_fga = int(players_df['FGA'].sum())
home_team = teams_df.iloc[0]['TEAM_ABBREVIATION']
away_team = teams_df.iloc[1]['TEAM_ABBREVIATION']
home_pts  = int(teams_df.iloc[0]['PTS'])
away_pts  = int(teams_df.iloc[1]['PTS'])

print(f"NBA BoxScore: {away_team} {away_pts} @ {home_team} {home_pts}")
print(f"Total FGA (NBA): {total_fga}")
print(f"Roster: {list(players_df['PLAYER_NAME'])[:10]}")
```

```bash
conda run -n basketball_ai python -c "
import sys, json, time
sys.path.insert(0, 'C:/Users/neelj/nba-ai-system')
from nba_api.stats.endpoints import boxscoretraditionalv2
import pandas as pd
time.sleep(0.6)
bs = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id='$GAME_ID')
p = bs.get_data_frames()[0]
t = bs.get_data_frames()[1]
p.to_csv('data/tracking/$GAME_ID/nba_boxscore_players.csv', index=False)
t.to_csv('data/tracking/$GAME_ID/nba_boxscore_teams.csv', index=False)
print('FGA:', int(p.FGA.sum()), '| Roster:', list(p.PLAYER_NAME)[:6])
print('Teams:', list(t.TEAM_ABBREVIATION), '| Score:', list(t.PTS))
" 2>&1
```

### 3B — Cross-reference CV output vs NBA ground truth

Check each of these. Record pass/fail and the ratio:

**Shot count accuracy:**
```bash
conda run -n basketball_ai python -c "
import pandas as pd, sys
sys.path.insert(0, 'C:/Users/neelj/nba-ai-system')
gid = '$GAME_ID'
base = f'data/tracking/{gid}'

try:
    shots_cv  = len(pd.read_csv(f'{base}/shot_log.csv'))
except: shots_cv = 0

try:
    nba_box = pd.read_csv(f'{base}/nba_boxscore_players.csv')
    shots_nba = int(nba_box.FGA.sum())
except: shots_nba = -1

# Scale CV shots by fraction of game tracked (18000 frames / ~43200 full game frames at 30fps)
tracked_fraction = min(1.0, 18000 / 43200)
shots_nba_scaled = int(shots_nba * tracked_fraction) if shots_nba > 0 else -1

ratio = shots_cv / shots_nba_scaled if shots_nba_scaled > 0 else 0
print(f'CV shots: {shots_cv}  |  NBA FGA (scaled): {shots_nba_scaled}  |  ratio: {ratio:.2f}  |  pass={0.4 <= ratio <= 2.5}')
" 2>&1
```

**Player ID resolution accuracy:**
```bash
conda run -n basketball_ai python -c "
import pandas as pd, sys
sys.path.insert(0, 'C:/Users/neelj/nba-ai-system')
gid = '$GAME_ID'
base = f'data/tracking/{gid}'

try:
    td = pd.read_csv(f'{base}/tracking_data.csv')
    total_rows = len(td)
    named_rows = td['player_name'].notna() & (td['player_name'] != '') & (td['player_name'] != '?')
    named_pct = named_rows.sum() / total_rows if total_rows > 0 else 0
except Exception as e:
    named_pct = 0; print(f'err: {e}')

try:
    nba_box = pd.read_csv(f'{base}/nba_boxscore_players.csv')
    nba_names = set(nba_box['PLAYER_NAME'].str.lower())
    # Detect CV names that match NBA roster
    if total_rows > 0:
        cv_names = set(str(n).lower() for n in td['player_name'].dropna().unique() if str(n) not in ('', '?', 'nan'))
        matched = len(cv_names & nba_names)
        roster_hit_rate = matched / len(nba_names) if nba_names else 0
    else:
        roster_hit_rate = 0
except: roster_hit_rate = 0

print(f'Named rows: {named_pct:.1%}  |  Roster hit rate: {roster_hit_rate:.1%}  |  pass={named_pct >= 0.4}')
" 2>&1
```

**Homography quality:**
```bash
conda run -n basketball_ai python -c "
import pandas as pd, sys
gid = '$GAME_ID'
try:
    td = pd.read_csv(f'data/tracking/{gid}/tracking_data.csv')
    if 'homography_valid' in td.columns:
        hom = td['homography_valid'].mean()
    else:
        hom = 1.0  # old format, assume ok
    print(f'homography_valid mean: {hom:.3f}  |  pass={hom >= 0.30}')
except Exception as e:
    print(f'err: {e}')
" 2>&1
```

**Possession count vs expected:**
```bash
conda run -n basketball_ai python -c "
import pandas as pd, sys
gid = '$GAME_ID'
try:
    poss = pd.read_csv(f'data/tracking/{gid}/possessions.csv')
    n_poss = len(poss)
    # NBA average ~100 possessions/48 min; 18000 frames / 30fps = 10 min
    frames_tracked = 18000; fps_est = 30
    mins_tracked = frames_tracked / fps_est / 60
    expected_poss = int(100 * mins_tracked / 48)
    ratio = n_poss / expected_poss if expected_poss > 0 else 0
    print(f'CV possessions: {n_poss}  |  expected (~{expected_poss} for {mins_tracked:.0f} min)  |  ratio: {ratio:.2f}  |  pass={ratio >= 0.3}')
except Exception as e:
    print(f'err: {e}')
" 2>&1
```

---

## PHASE 4 — Smart fallback enrichment

Based on Phase 3 results, apply fallbacks for any failing dimension. These fill gaps in the dataset even when CV is unreliable.

### FALLBACK A — Low homography (< 0.30): inject NBA tracking stats as spatial features

If `homography_valid < 0.30`, CV spatial coordinates (ft_x, ft_y, spacing) are unreliable. Pull from NBA API:

```bash
conda run -n basketball_ai python -c "
import sys, json, time, os, pandas as pd
sys.path.insert(0, 'C:/Users/neelj/nba-ai-system')
from nba_api.stats.endpoints import playertrackingStats  # speed, dist, touches
from nba_api.stats.endpoints import defensehub  # def dist, contestedness

gid = '$GAME_ID'

# Load team abbreviations from box score
try:
    t = pd.read_csv(f'data/tracking/{gid}/nba_boxscore_teams.csv')
    home_team = t.iloc[0]['TEAM_ABBREVIATION']
    away_team = t.iloc[1]['TEAM_ABBREVIATION']
    season_id = '2024-25' if gid[:4] in ('0022', '0012') else '2025-26'
except: home_team = away_team = ''; season_id = '2024-25'

# Pull close defender distance from PlayerDashPtShots
from nba_api.stats.endpoints import playerdashptshots
from nba_api.stats.static import players as nba_players_static

# Get the player IDs for this game
try:
    p_df = pd.read_csv(f'data/tracking/{gid}/nba_boxscore_players.csv')
    player_ids = p_df['PLAYER_ID'].tolist()[:12]  # top 12 by MIN
except: player_ids = []

fallback_rows = []
for pid in player_ids[:6]:  # rate limit — top 6 players only
    time.sleep(0.6)
    try:
        dash = playerdashptshots.PlayerDashPtShots(
            player_id=pid,
            season=season_id,
            per_mode_simple='PerGame',
        ).get_data_frames()[0]
        if not dash.empty:
            row = dash.iloc[0].to_dict()
            row['PLAYER_ID'] = pid
            fallback_rows.append(row)
    except Exception as e:
        print(f'  skip pid={pid}: {e}')

if fallback_rows:
    fb_df = pd.DataFrame(fallback_rows)
    out = f'data/tracking/{gid}/nba_shot_proximity_fallback.csv'
    fb_df.to_csv(out, index=False)
    print(f'[FALLBACK-A] saved {len(fb_df)} rows to {out}')
    # Key cols: CLOSE_DEF_DIST (avg defender dist), FGA_PCT (shooting %)
    if 'CLOSE_DEF_DIST' in fb_df.columns:
        print(fb_df[['PLAYER_ID','CLOSE_DEF_DIST','FGA']].to_string(index=False))
else:
    print('[FALLBACK-A] no rows fetched')
" 2>&1
```

### FALLBACK B — Low player ID rate (< 40%): resolve jersey numbers via NBA roster

If named_rows < 40%, look up who played by jersey number:

```bash
conda run -n basketball_ai python -c "
import sys, pandas as pd, json, time
sys.path.insert(0, 'C:/Users/neelj/nba-ai-system')
from nba_api.stats.endpoints import commonteamroster
gid = '$GAME_ID'

try:
    t = pd.read_csv(f'data/tracking/{gid}/nba_boxscore_teams.csv')
    team_ids = t['TEAM_ID'].tolist()
except: team_ids = []; print('no team IDs'); exit()

# Build jersey → player name lookup
jersey_map = {}
for tid in team_ids:
    time.sleep(0.6)
    try:
        roster = commonteamroster.CommonTeamRoster(team_id=tid, season='2024-25').get_data_frames()[0]
        for _, row in roster.iterrows():
            jersey = str(row.get('NUM', '')).strip()
            name   = str(row.get('PLAYER', '')).strip()
            if jersey and name:
                jersey_map[jersey] = name
    except Exception as e:
        print(f'  skip tid={tid}: {e}')

# Save jersey → name lookup
out = f'data/tracking/{gid}/jersey_name_map.json'
with open(out, 'w') as f:
    json.dump(jersey_map, f, indent=2)
print(f'[FALLBACK-B] jersey map saved: {len(jersey_map)} entries')
print(json.dumps(dict(list(jersey_map.items())[:10]), indent=2))

# Now patch tracking_data.csv — replace '?' / blank player_name using jersey col
try:
    td = pd.read_csv(f'data/tracking/{gid}/tracking_data.csv')
    if 'jersey_number' in td.columns or 'jersey' in td.columns:
        jcol = 'jersey_number' if 'jersey_number' in td.columns else 'jersey'
        patched = 0
        def resolve(row):
            global patched
            name = str(row.get('player_name', '')).strip()
            if name in ('', '?', 'nan'):
                jersey = str(row.get(jcol, '')).strip()
                if jersey in jersey_map:
                    patched += 1
                    return jersey_map[jersey]
            return name
        td['player_name'] = td.apply(resolve, axis=1)
        td.to_csv(f'data/tracking/{gid}/tracking_data.csv', index=False)
        print(f'[FALLBACK-B] patched {patched} rows in tracking_data.csv')
    else:
        print('[FALLBACK-B] no jersey column in tracking_data.csv — cant auto-patch')
except Exception as e:
    print(f'[FALLBACK-B] patch error: {e}')
" 2>&1
```

### FALLBACK C — Shot log undercounting (ratio < 0.4): supplement with NBA shot chart

```bash
conda run -n basketball_ai python -c "
import sys, pandas as pd, time
sys.path.insert(0, 'C:/Users/neelj/nba-ai-system')
from nba_api.stats.endpoints import shotchartdetail
gid = '$GAME_ID'

time.sleep(0.6)
try:
    sc = shotchartdetail.ShotChartDetail(
        team_id=0,
        player_id=0,
        game_id_nullable=gid,
        context_measure_simple='FGA',
    ).get_data_frames()[0]

    if sc.empty:
        print('[FALLBACK-C] no shot chart data')
    else:
        out = f'data/tracking/{gid}/nba_shot_chart.csv'
        sc.to_csv(out, index=False)
        # Key columns: LOC_X, LOC_Y (in 1/10 feet from basket), SHOT_MADE_FLAG, PLAYER_NAME, SHOT_TYPE, SHOT_DISTANCE
        print(f'[FALLBACK-C] saved {len(sc)} shots to {out}')
        print(sc[['PLAYER_NAME','SHOT_TYPE','SHOT_MADE_FLAG','SHOT_DISTANCE','LOC_X','LOC_Y']].head(10).to_string(index=False))
        # Convert LOC_X/LOC_Y from 1/10-ft to ft for compatibility with CV ft_x/ft_y
        sc['ft_x'] = sc['LOC_X'] / 10.0 + 25.0  # center court offset
        sc['ft_y'] = sc['LOC_Y'] / 10.0 + 5.25  # hoop to baseline
        sc[['PLAYER_NAME','SHOT_MADE_FLAG','SHOT_DISTANCE','ft_x','ft_y','SHOT_TYPE']].to_csv(
            f'data/tracking/{gid}/nba_shot_chart_ft.csv', index=False)
        print(f'[FALLBACK-C] ft-coordinate version saved')
except Exception as e:
    print(f'[FALLBACK-C] error: {e}')
" 2>&1
```

### FALLBACK D — Pull PBP for possession ground truth

Always run this — it enriches possessions with play types even when CV is clean:

```bash
conda run -n basketball_ai python -c "
import sys, pandas as pd, time
sys.path.insert(0, 'C:/Users/neelj/nba-ai-system')
from nba_api.stats.endpoints import playbyplayv2
gid = '$GAME_ID'

time.sleep(0.6)
try:
    pbp = playbyplayv2.PlayByPlayV2(game_id=gid).get_data_frames()[0]
    out = f'data/nba/pbp_{gid}.json'
    pbp.to_json(out, orient='records', indent=2)
    print(f'[FALLBACK-D] PBP saved: {len(pbp)} events to {out}')
    # Possession-changing events: turnovers, made FG, missed FG + rebound
    poss_events = pbp[pbp['EVENTMSGTYPE'].isin([1,2,5])]  # 1=made, 2=miss, 5=turnover
    print(f'  Possession events: {len(poss_events)} | Made FG: {len(pbp[pbp.EVENTMSGTYPE==1])} | Turnovers: {len(pbp[pbp.EVENTMSGTYPE==5])}')
except Exception as e:
    print(f'[FALLBACK-D] error: {e}')
" 2>&1
```

---

## PHASE 5 — Accuracy scorecard

Compile everything into a scorecard:

```bash
conda run -n basketball_ai python -c "
import pandas as pd, json, os, sys
gid = '$GAME_ID'
base = f'data/tracking/{gid}'

results = {}

# 1. Homography
try:
    td = pd.read_csv(f'{base}/tracking_data.csv')
    hom = td['homography_valid'].mean() if 'homography_valid' in td.columns else 1.0
    results['homography'] = {'value': round(hom,3), 'pass': hom >= 0.30, 'source': 'CV'}
except: results['homography'] = {'value': 0, 'pass': False, 'source': 'CV'}

# 2. Shot accuracy vs NBA
try:
    shots_cv = len(pd.read_csv(f'{base}/shot_log.csv'))
    nba_fga  = int(pd.read_csv(f'{base}/nba_boxscore_players.csv').FGA.sum())
    tracked_frac = min(1.0, 18000 / 43200)
    nba_scaled   = max(1, int(nba_fga * tracked_frac))
    ratio = shots_cv / nba_scaled
    results['shot_accuracy'] = {'cv': shots_cv, 'nba_scaled': nba_scaled, 'ratio': round(ratio,2), 'pass': 0.4 <= ratio <= 2.5}
except Exception as e:
    results['shot_accuracy'] = {'error': str(e), 'pass': False}

# 3. Player ID resolution
try:
    total = len(td)
    named = ((td['player_name'].notna()) & (td['player_name'] != '') & (td['player_name'] != '?')).sum()
    results['player_id_rate'] = {'value': round(named/total,3) if total else 0, 'pass': named/total >= 0.4 if total else False}
except: results['player_id_rate'] = {'value': 0, 'pass': False}

# 4. Possession count
try:
    n_poss = len(pd.read_csv(f'{base}/possessions.csv'))
    expected = int(100 * (18000/30/60) / 48)
    ratio_p = n_poss / max(1, expected)
    results['possession_ratio'] = {'cv': n_poss, 'expected': expected, 'ratio': round(ratio_p,2), 'pass': ratio_p >= 0.3}
except: results['possession_ratio'] = {'cv': 0, 'expected': 0, 'ratio': 0, 'pass': False}

# 5. Fallback files created
results['fallbacks'] = {
    'shot_chart':    os.path.exists(f'{base}/nba_shot_chart.csv'),
    'jersey_map':    os.path.exists(f'{base}/jersey_name_map.json'),
    'proximity':     os.path.exists(f'{base}/nba_shot_proximity_fallback.csv'),
    'pbp':           os.path.exists(f'data/nba/pbp_{gid}.json'),
}

print(json.dumps(results, indent=2))
" 2>&1
```

---

## PHASE 6 — Benchmark + fix one CV issue

**Benchmark (300 frames):**
```bash
conda run -n basketball_ai bash -c "cd /c/Users/neelj/nba-ai-system && python scripts/run_clip.py --video data/videos/full_games/$GAME_ID.mp4 --no-show --frames 300 --game-id $GAME_ID" 2>&1 | tail -20
```

Extract metrics: fps, ball_valid%, shots, id_switches, possessions.

**Read last improvement log entry (last 80 lines only):**
```
vault/Improvements/Tracker Improvements Log.md  (read from offset ~last 80 lines)
```

**Identify worst metric vs target:**
| Metric | Target |
|--------|--------|
| fps | ≥ 20 |
| ball_valid % | ≥ 60% (combined detected+inferred) |
| shots | ≥ 1 per 2 min clip |
| id_switches | 0 |
| possessions | ≥ 5 per 167s clip |

Do NOT repeat the last attempted fix. Apply ONE targeted code edit to the file directly responsible.

**Verify fix (150 frames):**
```bash
conda run -n basketball_ai bash -c "cd /c/Users/neelj/nba-ai-system && python scripts/run_clip.py --video data/videos/full_games/$GAME_ID.mp4 --no-show --frames 150 --game-id $GAME_ID" 2>&1 | tail -10
```

If improved → keep. If regressed → revert immediately.

**Re-run audit after fix:**
```bash
conda run -n basketball_ai bash -c "cd /c/Users/neelj/nba-ai-system && python scripts/audit_phase_g.py --game-ids $GAME_ID" 2>&1
```

---

## PHASE 7 — Sportsbook lines + prediction edges

**Pull today's lines and run predictions:**
```bash
conda run -n basketball_ai python scripts/run_daily_slate.py 2>&1 | tail -60
```

**Check model outputs:**
```bash
# Most recent slate
ls -t data/output/slate_*.json 2>/dev/null | head -1 | xargs python -c "
import json, sys
data = json.load(open(sys.argv[1] if len(sys.argv)>1 else sys.stdin.read().strip()))
# Top edges
props = sorted(data.get('props', []), key=lambda x: abs(x.get('edge_pct', 0)), reverse=True)[:5]
games = data.get('games', [])[:5]
print('=== TOP PROP EDGES ===')
for p in props:
    print(f'  {p.get(\"player\")} {p.get(\"stat\")} {p.get(\"line\")} | edge={p.get(\"edge_pct\",0):.1%} | kelly={p.get(\"kelly_fraction\",0):.3f}')
print()
print('=== GAME PREDICTIONS ===')
for g in games:
    print(f'  {g.get(\"away\")} @ {g.get(\"home\")} | home_win={g.get(\"home_win_prob\",0):.1%}')
" 2>&1 || echo "no slate output yet"
```

---

## PHASE 8 — Write session report

Write to `vault/Sessions/pipeline_summary_YYYY-MM-DD.md` (use today's actual date).
If file exists today, append a new `## Iteration N` section.

```markdown
# Pipeline Summary — YYYY-MM-DD (Iteration N)

## Game Processed
- Game ID: $GAME_ID
- Frames: 18,000
- Source: data/videos/full_games/$GAME_ID.mp4

## CV Accuracy Scorecard
| Metric | CV Value | NBA Ground Truth | Ratio | Pass |
|--------|----------|-----------------|-------|------|
| Shots | X | X (scaled) | X.XX | ✅/❌ |
| Player ID rate | X% | - | - | ✅/❌ |
| Homography | X.XX | - | - | ✅/❌ |
| Possessions | X | ~X expected | X.XX | ✅/❌ |

## Fallbacks Applied
| Fallback | Applied | File |
|----------|---------|------|
| NBA shot chart (LOC_X/Y) | ✅/❌ | nba_shot_chart_ft.csv |
| Jersey→name map | ✅/❌ | jersey_name_map.json |
| Shot proximity (def dist) | ✅/❌ | nba_shot_proximity_fallback.csv |
| PBP possession events | ✅/❌ | data/nba/pbp_GAMEID.json |

## Tracker Health
| Metric | Before | After | Target | Status |
|--------|--------|-------|--------|--------|
| FPS | | | ≥ 20 | ✅/❌ |
| Ball valid % | | | ≥ 60% | ✅/❌ |
| Shots | | | ≥ 1/2m | ✅/❌ |
| ID switches | | | 0 | ✅/❌ |
| Possessions | | | ≥ 5 | ✅/❌ |

## Fix This Iteration
- **File:** `src/tracking/X.py:LINE`
- **Change:** one sentence
- **Result:** ✅ kept / ❌ reverted

## Audit Result (post-fix)
- Criteria passed: X/6
- Failures: (list any)

## Today's Predictions
| Game | Home Win% | Away Win% |
|------|-----------|-----------|
| | | |

## Top Prop Edges
| Player | Stat | Line | Edge% | Kelly% |
|--------|------|------|-------|--------|
| | | | | |

## Phase G Progress
- Clean games (6/6): X / 20
- Next game to process: GAME_ID

## Next Fix
- Worst metric: X (current: X, target: X)
- Likely file: `src/tracking/X.py`
- Approach: one sentence
```

---

## PHASE 9 — Log to improvement tracker

Append to `vault/Improvements/Tracker Improvements Log.md`:

```
### YYYY-MM-DD — Game Loop Iteration N
**Game:** $GAME_ID · 18,000 frames
**CV Accuracy:** shots_ratio=X.XX  player_id=X%  homography=X.XX  possessions=X
**Fallbacks:** shot_chart=✅/❌  jersey_map=✅/❌  proximity=✅/❌  pbp=✅/❌
**Fix:** `<file>:<line>` — <what changed> — kept/reverted
**Audit:** X/6 criteria pass
**Next:** <worst metric and planned approach>
```

---

## DATA SOURCE PRIORITY (for any feature — always use best available)

```
defender_distance:  CV ft coords (homography ≥ 0.85) > NBA CLOSE_DEF_DIST (per season) > NaN
player_name:        CV jersey OCR > jersey_name_map.json fallback > "?"
shot_location:      CV ft_x/ft_y (homography ≥ 0.85) > NBA shot chart LOC_X/Y > NaN
possession_events:  CV possessions.csv > NBA PBP possession events > NaN
shot_count:         CV shot_log.csv (if ratio 0.4-2.5× NBA) > NBA shot chart > NaN
team_identity:      CV team_abbrev (if not UNK) > NBA boxscore team → color mapping
scoring:            NBA boxscore (always authoritative) > CV scoreboard OCR
```
