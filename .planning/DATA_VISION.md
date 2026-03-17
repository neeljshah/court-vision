# Data Vision: Every Data Point This System Must Collect

> **North Star:** Put in one full NBA broadcast video → get more data than anyone else.
> No public system combines CV spatial tracking + exhaustive NBA API + betting/sentiment/travel web scraping simultaneously.
> Every phase, fix, and feature should be measured against this list.

---

## CV Tracking — Per Frame, Per Player

**Position & Movement**
- Court x, y (2D rectified coordinates)
- Velocity (px/frame), acceleration, direction (degrees)
- Distance traveled — rolling 30 / 90 / 150 frame windows
- Max velocity per window
- Speed zone: standing / walking / jogging / running / sprinting
- Velocity decline Q1 → Q4 (fatigue proxy)

**Court Context**
- Zone: paint / mid-range / corner 3 / above-break 3 / backcourt
- Distance to basket, velocity toward basket
- Paint time % (frames in paint / total)
- Possession side (left / right half-court)

**Spacing**
- Nearest teammate distance, nearest opponent distance
- Team centroid x/y
- Team spacing (avg pairwise distance between 5 teammates)
- Spacing advantage (own spacing − opponent spacing)
- Paint count: own team / opponent

**Ball Interaction**
- Ball possession (boolean)
- Distance to ball
- Handler isolation score
- Drive flag (moving toward basket with ball)
- Fast break flag

**Events per Frame**
- Shot / pass / dribble / none

---

## CV Tracking — Per Possession

team, start_frame, end_frame, duration_frames, duration_sec, shot_attempted, shot_frame, fast_break, drive_attempts, avg_spacing, avg_defensive_pressure, avg_vel_toward_basket, pick_roll_proxy, transition_flag (vs half-court), result (scored/turnover/foul — from NBA API enrichment), outcome_score

---

## CV Tracking — Per Shot (Enriched with Game ID)

court_x, court_y, court_zone, defender_distance_at_release, team_spacing_at_release, possession_duration_before_shot, drive_leading_to_shot, fast_break_shot, made_missed (NBA API), shot_type (NBA API), quarter, game_clock, score_margin, xFG (model output)

---

## CV Tracking — Per Player Per Clip

total_distance, avg_velocity, max_velocity, possession_pct, shots_attempted, drive_attempts, drive_rate, paint_time_pct, avg_dist_to_basket, avg_nearest_opponent, frames_tracked, tracking_pct, court_zone_distribution (% in each zone)

---

## CV Tracking — New Metrics (Phase 2 to build)

- Defensive assignment map (who guards who, per possession)
- Off-ball: cuts per game, curl frequency, back-cuts
- Screens set: pick-roll, pick-pop, off-ball screens
- Help defense positioning (off-ball defender distance from assignment)
- Zone vs man detection
- Post-up detection
- Player fatigue: avg velocity Q1 vs Q4

---

## NBA API — Boxscore (Per Player Per Game)

pts, reb, oreb, dreb, ast, stl, blk, tov, pf, min, fgm, fga, fg_pct, fg3m, fg3a, fg3_pct, ftm, fta, ft_pct, plus_minus, starter

---

## NBA API — Advanced Stats (All 569 Players)

usg_pct, ts_pct, off_rtg, def_rtg, net_rtg, pie, ast_pct, reb_pct, efg_pct, tov_pct, oreb_pct, dreb_pct, pace

---

## NBA API — Scoring Breakdown

pct_pts_paint, pct_pts_mid_range, pct_pts_corner_3, pct_pts_above_break_3, pct_pts_ft, pct_pts_pull_up_2, pct_pts_catch_shoot_3, pct_pts_pull_up_3

---

## NBA API — Misc Stats

pts_off_tov, pts_paint, pts_fb, pts_2nd_chance, blk_pct, stl_pct

---

## NBA API — Hustle Stats

contested_2pt, contested_3pt, deflections, loose_balls_recovered, charges_drawn, screen_assists, screen_assist_pts, box_out_rebounds

---

## NBA API — Tracking Stats (SecondSpectrum)

avg_speed_mph, dist_covered_per_game, touches, frontcourt_touches, elbow_touches, post_touches, paint_touches, pull_up_pts, catch_shoot_pts, restricted_area_pts, drive_pts, drive_passes, drive_fouls_drawn

---

## NBA API — Gamelogs (All Active Players × 3 Seasons)

All boxscore stats per individual game + opponent + home/away + win/loss
Rolling computed: last_5 / last_10 / last_15 / last_20 for all stats

---

## NBA API — Splits (Per Player)

Home vs away, win vs loss, pre/post All-Star, by month, by opponent, clutch (within 5pts last 5min), by rest (0 / 1 / 2+ days)

---

## NBA API — Shot Charts (ShotChartDetail — target 50K+ shots)

court_x, court_y, shot_distance, shot_zone_basic, shot_zone_area, made_missed, shot_type, quarter, game_clock, score_margin, opponent, home_away

---

## NBA API — Play-by-Play (All 1,225+ Games)

Every event: shot / rebound / turnover / foul / FT / sub / timeout / violation
Per event: player, team, period, game_clock, score, score_margin

---

## NBA API — Lineup Data (All 30 Teams × 3 Seasons)

Per 5-man unit: minutes, net_rtg, off_rtg, def_rtg, pace, efg_pct, tov_pct, oreb_pct, ft_per_fga
Also: 2-man combo stats (pick-roll partners, defensive pairs)

---

## NBA API — Schedule Context

rest_days, back_to_back, travel_miles, home_away, games_last_7, road_trip_length (consecutive away)

---

## NBA API — Referee

Per game: referee assignments (all 3 refs)
Per referee historical: foul_rate, pace_impact, home_win_pct, techs_per_game, over_under_tendency, charge_vs_block_tendency

---

## NBA API — Draft Combine (Physical Profile)

height_no_shoes, height_with_shoes, wingspan, standing_reach, weight, body_fat_pct, hand_length, hand_width, standing_vertical, max_vertical, bench_press_reps, lane_agility_time, sprint_time

---

## Web Scraping — Betting Lines

Per market per book (DraftKings, FanDuel, BetMGM, Caesars, PointsBet):
opening_spread, current_spread, closing_spread, moneyline_home, moneyline_away, total_line, total_direction

Player props per player: pts_line, reb_line, ast_line, fg3m_line, pra_line, stl_line, blk_line

---

## Web Scraping — Sharp Money Signals

clv (closing line value — did model beat closing?), line_movement_direction, pct_bets_home, pct_money_home (public vs sharp divergence), steam_move_flag (rapid cross-book movement)

---

## Web Scraping — Injury & Health

Per player: nba_official_status, espn_status, rotowire_status, rotowire_timeline, beat_writer_flag (Twitter load management / questionable / illness), historical_injury_log (type + games_missed), return_game_performance (first 5 games back stats)

---

## Web Scraping — Travel & Fatigue

flight_distance_miles, time_zones_crossed, consecutive_road_games, home_after_road_trip, red_eye_flag, altitude_ft (Denver = 5280), days_since_last_game

---

## Web Scraping — News & Sentiment

espn_keyword_flags (trade/injury/suspended/illness/personal), beat_writer_sentiment_score, reddit_rnba_sentiment_per_team, locker_room_flag, coaching_change_flag, scheme_change_flag

---

## Web Scraping — Contract & Motivation

contract_year_flag (expiring = effort proxy), salary_tier (max/near-max/role/minimum), trade_rumor_flag, avg_roster_experience_years

---

## Web Scraping — Arena & Crowd

attendance_pct_capacity, home_court_advantage_score, neutral_site_flag, arena_altitude_ft

---

## Data Volume Per Fully Processed Game

| Source | Volume |
|--------|--------|
| CV tracking frames | ~30,000 rows (per frame × per player) |
| CV possessions labeled | ~200 |
| CV shots enriched | ~90 with full spatial context |
| NBA boxscore | ~25 players × 22 stats |
| NBA advanced/hustle/tracking | ~25 players × 50+ stats |
| NBA play-by-play | ~450 events |
| NBA lineup combos | ~50 five-man units |
| Schedule + referee context | ~20 features |
| External (odds/injury/travel/sentiment) | ~60 features |

---

## Current Status (2026-03-16): ~10% of Target

**Phase 2 (tracker bugs) → Phase 3 (NBA API exhaustive) = ~60% with zero video processing**

See `.planning/ROADMAP.md` for 14-phase build plan.
See `.planning/REQUIREMENTS.md` for full per-phase requirements.
