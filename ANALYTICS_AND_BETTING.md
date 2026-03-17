# Analytics and Betting Use Cases

How the NBA AI system can be used for basketball analytics and sports betting research.

---

## Basketball Analytics

### Team Performance Analysis
- Measure offensive and defensive efficiency by lineup, quarter, or opponent
- Identify which play types generate the most value for a given roster
- Track spacing and floor balance across different game situations
- Compare team performance in transition vs half-court settings
- Quantify defensive rotation effectiveness and help defense quality

### Player Scouting
- Profile shot quality by zone — where a player shoots efficiently vs inefficiently
- Measure off-ball movement: cuts, relocations, spacing habits
- Evaluate screening effectiveness (screen assists, coverage drawn)
- Track defensive effort: closeout distance, rotation speed, contested shot rate
- Generate movement heatmaps from broadcast video without SportVU access

### Lineup Optimization
- Project net rating for any 5-man combination using historical on/off data
- Identify spacing mismatches in a proposed lineup
- Surface best lineups against a specific opponent's defensive scheme
- Estimate fatigue impact on lineup performance across back-to-backs

### Tactical Analysis
- Classify possessions by play type (ISO, PnR, post, cut, spot-up)
- Identify which play types a defense allows most frequently and most efficiently
- Map transition triggers: which turnovers / misses lead to the fastest breaks
- Analyze ball movement patterns and assist networks by lineup or game state

---

## Sports Betting Analytics

> **Disclaimer:** The following describes technical capabilities for research and analytical purposes only. All sports betting must comply with applicable laws and regulations in your jurisdiction.

### Pre-Game Predictions
- Win probability for each team based on team ratings, rest, travel, and matchup
- Expected point margin and total (over/under) derived from offensive/defensive projections
- Player prop projections (points, rebounds, assists) vs posted sportsbook lines
- Identify statistical mismatches the market may not have fully priced in

### In-Game Win Probability
- Real-time win probability curve updated after each possession
- Detect momentum swings and scoring run probability
- Quantify how lineup changes and foul trouble shift win probability
- Surface live betting opportunities when model probability diverges from live odds

### Matchup Analysis
- Compare team pace vs opponent pace to project total points
- Identify defensive vulnerabilities (zone, help, closeout) that match opponent strengths
- Evaluate how a player's tracked shot profile matches against a specific defense
- Project lineup net ratings for expected rotations in a given game

### Value Identification vs Betting Markets
- Compare model predictions against live sportsbook lines (spread, total, moneyline, props)
- Compute implied probability from odds and compare to model probability
- Flag bets where model edge exceeds a configurable threshold
- Track historical model accuracy vs the closing line to evaluate predictive quality

---

## Data Availability and Limitations

- Tracking features (spacing, shot context, defender distance) require processed video
- Stat-only models (win probability, props) can operate from NBA API data alone
- Model accuracy improves with more processed games — predictions are probabilistic
- Past performance of a predictive model does not guarantee future accuracy
