# Prompt: Wire 23 Trained Models + 3 Data Sources Into player_props.py

## Context

NBA player prop prediction system in `C:\Users\neelj\nba-ai-system\`.

- **Working dir**: `C:\Users\neelj\nba-ai-system\`
- **Conda env**: `basketball_ai` (Python 3.10)
- **Read first**: `CLAUDE.md` + `vault/Improvements/Tracker Improvements Log.md`

### Current state

- `src/prediction/player_props.py` — main prop model (XGBoost, 7 stats: pts/reb/ast/fg3m/stl/blk/tov)
- `_build_player_features()` — builds the feature dict; currently **105 features** in `_ALL_FEATS`
- `_ALL_FEATS` — list at the bottom of the file; this is the source of truth for feature order
- 23 models in `data/models/` are trained and saved but **never called inside `_build_player_features()`**
- 3 data files exist with rich features not yet extracted

### Where to add wiring code

In `_build_player_features()`, before the final `return feats` line, add each new block wrapped in `try/except`. Every block must have a hardcoded fallback so the function never fails. After each block, call `feats.update({...})`.

Add all new feature names to `_ALL_FEATS` in grouped comment sections at the bottom of the list.

---

## Task

Wire **all 23 models** and **3 data sources** below as new features in `_build_player_features()` and `_ALL_FEATS`. Then add smoke tests to `tests/test_new_models.py`.

---

## Part 1 — Game Context Models (Group A)

These tell you what kind of game tonight will be. Call with data available in `feats` already.

### A1. Back-to-back multipliers
```python
from src.prediction.back_to_back_model import predict_b2b_mult
# Input: features dict — reads feats.get("is_b2b", 0); derive: is_b2b = 1 if feats["rest_days"] <= 1 else 0
# Output: {"pts": float, "reb": float, "ast": float, "min": float}  — multipliers (1.0 = no change)
# Model file: data/models/back_to_back_model.pkl
```
**Wire**: `b2b_pts_mult`, `b2b_min_mult`
**Fallback**: `1.0`

### A2. Travel fatigue
```python
from src.prediction.travel_impact_model import predict_travel_adj
# Input: features dict — reads team, opp, is_home etc.
# Output: {"adj": float}  — multiplier (e.g. 0.98 = 2% decline)
# Model file: data/models/travel_impact_model.pkl
```
**Wire**: `travel_adj`
**Fallback**: `1.0`

### A3. Altitude adjustment
```python
from src.prediction.altitude_model import predict_altitude_adj
# Input: features dict — reads feats["team"] + feats.get("is_home", 0) + opp_team
# Output: {"adj": float}
# Model file: data/models/altitude_model.pkl
# Only triggers for DEN/UTA home games when player is road team
```
**Wire**: `altitude_adj`
**Fallback**: `1.0`

### A4. Rest-day performance multiplier
```python
from src.prediction.rest_day_model import predict_rest_mult
# Input: features dict — reads feats["rest_days"]
# Output: {"mult": float}  — performance multiplier
# Model file: data/models/rest_day_model.pkl
# More precise than raw rest_days count: non-linear curve
```
**Wire**: `rest_day_mult`
**Fallback**: `1.0`

### A5. Overtime probability
```python
from src.prediction.overtime_probability import predict_ot_prob
# Input: spread (float) — absolute point spread (use feats.get("game_spread_pred", 5.0))
# Output: float — P(overtime)
# Model file: data/models/overtime_probability.pkl
# OT adds ~10% to all counting stats; wire so XGBoost can learn this
```
**Wire**: `ot_prob`
**Fallback**: `0.05`

### A6. Garbage time
```python
from src.prediction.garbage_time_detector import predict_garbage_time
# Input: features dict — reads blowout_prob, spread, etc.
# Output: {"garbage_time_prob": float, "garbage_time_min_lost": float}
# Model file: data/models/garbage_time.pkl
```
**Wire**: `garbage_time_prob`, `garbage_time_min_lost`
**Fallback**: `0.0`, `0.0`

### A7. Game model outputs (spread, total, blowout, pace)
```python
from src.prediction.game_models import load_models
gm = load_models()
# Call: gm.predict(home_team, away_team, season)  [home_team = feats.get("team","")]
# Output: {
#   "spread":    float,   # predicted point spread (home - away)
#   "game_total": float,  # predicted game total
#   "blowout_prob": float,
#   "pace":      float,   # predicted game pace/possessions
#   "first_half_total": float
# }
# Model files: data/models/game_spread.json, game_game_total.json,
#              game_blowout.json, game_pace.json, game_first_half.json
# IMPORTANT: cache the result in a module-level dict keyed by (home, away, season)
#            to avoid repeated model loads during batch predictions (same pattern as _blowout_cache)
```
**Wire**: `game_spread_pred`, `game_total_pred`, `game_blowout_pred`, `game_pace_pred`
**Fallback**: `0.0`, `215.0`, `0.0`, `100.0`

---

## Part 2 — Player Efficiency Models (Group B)

These refine each player's projected efficiency and usage.

### B1. Usage rate (projected)
```python
from src.prediction.usage_rate_model import predict_usage
# Input: features dict — reads min_l10, season_avg_min, on_off_diff, etc.
# Output: {"proj_usg_pct": float}  — projected usage % (0.0–0.5)
# Model file: data/models/usage_rate_model.pkl
# Key signal: usage * pace * possessions ≈ shot volume → pts
```
**Wire**: `usage_pct_pred`
**Fallback**: `0.20`

### B2. True shooting % (projected)
```python
from src.prediction.true_shooting_model import predict_ts
# Input: features dict — reads fg_pct, fg3_pct, fta, bbref_ts_pct, etc.
# Output: {"proj_ts_pct": float}
# Model file: data/models/true_shooting_model.pkl
```
**Wire**: `ts_pct_pred`
**Fallback**: `0.565`

### B3. Age discount multiplier
```python
from src.prediction.age_curve_model import predict_age_discount
# Input: features dict — reads player_id and season to look up career curve
# Output: {"discount": float}  — 1.0 = prime, <1.0 = decline, >1.0 = rising
# Model file: data/models/age_curve_model.pkl
```
**Wire**: `age_discount`
**Fallback**: `1.0`

### B4. Home/away boost
```python
from src.prediction.home_away_model import predict_home_away
# Input: features dict — reads player_id, is_home (derive: 0 by default since we don't track it yet)
# Output: {"pts": float, "reb": float, "ast": float, "min": float}
#   — positive = home boost; negative = road penalty
#   Apply: add to projected stats when is_home=1; pass through when is_home=0
# Model file: data/models/home_away_model.pkl
```
**Wire**: `ha_pts_boost`, `ha_min_boost`
**Fallback**: `0.0`, `0.0`

### B5. Foul trouble
```python
from src.prediction.foul_trouble_predictor import predict_foul_trouble
# Input: player_id (int), features dict
# Output: {"foul_out_prob": float, "expected_foul_count": float, "min_reduction": float}
# Model file: data/models/foul_trouble.pkl
# High impact: expected_foul_count > 3.5 means likely reduced minutes
```
**Wire**: `foul_out_prob`, `expected_foul_count`, `foul_min_reduction`
**Fallback**: `0.0`, `2.5`, `0.0`

### B6. Minutes floor (projected playing time)
```python
from src.prediction.minutes_floor_model import predict_minutes
# Input: player_id (int), features dict — reads min_l10, season_avg_min
# Output: {"proj_min": float}
# Model file: data/models/minutes_floor.pkl
# Complements coach_expected_min; provides a model-trained floor
```
**Wire**: `min_floor_pred`
**Fallback**: `feats.get("season_min", 24.0)`

### B7. Load management probability
```python
from src.prediction.load_management import predict_load_management
# Input: player_name (str), season (str)
# Output: {"load_prob": float, "expected_min": float, ...}
# Model file: data/models/load_management.pkl
# Separate from DNP predictor — captures partial rest (20-min load games)
```
**Wire**: `load_mgmt_prob`
**Fallback**: `0.0`

---

## Part 3 — Player vs Matchup Models (Group C)

These require knowing the opponent context.

### C1. Matchup suppression score
```python
from src.prediction.matchup_model import predict_matchup, get_defender_quality
# Call: predict_matchup(player_name, likely_defender_name, season)
#   where likely_defender_name = feats.get("likely_defender_name", "")
#   (populated by defensive_matchup_classifier from previous session)
# Output: {
#   "adjusted_pts_per_100": float,
#   "pts_adj_pct": float,   # e.g. -0.08 = 8% suppression
#   "off_player": str, "def_player": str
# }
# Falls back to get_defender_quality(opp_team, season) if no specific defender name
# Model file: data/models/matchup_model.json
```
**Wire**: `matchup_suppression_pct`
**Fallback**: `0.0`

### C2. Beneficiary cascade boost
```python
from src.prediction.beneficiary_cascade import predict_beneficiary_boost
# Richer than usage_surge_detector — models the full cascade chain
# Input:
#   team_abbrev = feats.get("team", "")
#   dnp_player_ids: list[int] — players confirmed out tonight
#     → get from InjuryMonitor: [pid for pid in team_pids if monitor.get_status(pid) == "Out"]
#   all_player_ids: list[int] — all players on team (from player_avgs cache)
# Output: {player_id: {"min_boost": float, "pts_boost": float}}
# Extract: result.get(feats["player_id"], {})
# Model file: data/models/beneficiary_cascade.pkl
```
**Wire**: `cascade_pts_boost`, `cascade_min_boost`
**Fallback**: `0.0`, `0.0`

---

## Part 4 — Data Extractions (Group D)

These extract features from existing data files that are already on disk.

### D1. Lineup net rating (player's lineup context)

Data: `data/nba/lineups/lineup_splits_{team}_{season}.json`

Structure of each record:
```json
{
  "lineup": ["D. Finney-Smith", "L. Dončić", "R. Hachimura", "G. Vincent", "A. Reaves"],
  "minutes": 32.0,
  "net_rating": 57.9,
  "off_rating": 132.9,
  "def_rating": 75.0,
  "pace": 107.56,
  "efg_pct": 0.669
}
```

Logic:
1. Load the file for `feats["team"]` + season
2. Match player to lineups using a partial last-name match against the player's full name
3. Weight `net_rating` and `off_rating` by `minutes` across all lineups containing this player
4. Result: player's weighted average lineup net_rating and off_rating

**Wire**: `player_lineup_net_rtg`, `player_lineup_off_rtg`
**Fallback**: `0.0`, `100.0`

### D2. xFG luck delta (shooting luck signal)

Data: `data/nba/xfg_calibration.json` + `data/nba/shot_tendency_features.json`

Logic:
1. From `xfg_calibration.json`, load zone-level `{zone: {actual_fg_pct, pred_fg_pct}}`
2. From `shot_tendency_features.json`, load this player's zone rates: `{paint_rate, above_break_3_rate, corner_3_rate, mid_rate}`
3. Compute `xfg_weighted = paint_rate * xfg_paint + above_break_3_rate * xfg_3pt + mid_rate * xfg_mid + ...`
4. `fg_luck_delta = feats["fg_pct"] - xfg_weighted`
   - Positive = outperforming xFG → likely regression
   - Negative = underperforming xFG → likely bounce-back

**Wire**: `xfg_weighted`, `fg_luck_delta`
**Fallback**: `feats["fg_pct"]`, `0.0`

### D3. Opponent's rolling 5-game defensive rating

Data: `data/nba/scored_games_{season}.json`

Logic:
1. Load `scored_games_{season}.json` — list of completed games with `home_team`, `away_team`, `home_def_rtg`, `away_def_rtg`, `game_date`
2. Filter to last 5 games where `opp_team` played (either side)
3. Average their defensive rating in those 5 games
4. `opp_def_rtg_l5` — more current than season `opp_def_rtg`

**Wire**: `opp_def_rtg_l5`
**Fallback**: `feats["opp_def_rtg"]` (season average)

---

## Implementation Rules

1. **Every block is wrapped in try/except** with the stated fallback — the function must never raise.
2. **Call models in this order** in `_build_player_features()`, near the end, after all existing blocks:
   - Group A (game context) first — `game_spread_pred` is needed by `ot_prob` call
   - Group B (player efficiency) next
   - Group C (matchup) last — needs `likely_defender_name` from `defensive_matchup_classifier` (already wired from previous session)
   - Group D (data) anywhere — these are pure data reads
3. **Cache game_models.load_models()** at module level (like `_blowout_cache`) — it loads 5 model files and is expensive. Use a module-level `_game_models_cache = None` singleton.
4. **Derive `is_b2b`** for back_to_back_model from `feats["rest_days"] <= 1` since `is_b2b` isn't in `_ALL_FEATS` yet.
5. **Total new features**: should add ~23 features to `_ALL_FEATS`, grouped by comments.

---

## Smoke Tests

Add to `tests/test_new_models.py` (currently 66 tests):

- One test per Group (A, B, C, D) — monkeypatched stubs, no disk/API calls
- Final integration test: verify all 23 new keys appear in `predict_props(...)["features"]`
- All stubs must work with the existing `_MINIMAL_FEATURES` dict already in the test file
- No new test fixtures needed — use `monkeypatch.setattr` on module-level functions

### Test skeleton pattern
```python
def test_game_models_wired(monkeypatch):
    import src.prediction.player_props as _pp
    # stub game_models singleton
    monkeypatch.setattr(_pp, "_game_models_cache", _FakeGM())
    # ... call predict_props with full stubs ...
    feats = result["features"]
    assert "game_spread_pred" in feats
    assert "game_total_pred" in feats
```

---

## After Building

1. Run: `python -m pytest tests/test_new_models.py -v --tb=short`
   - All 66 existing tests must still pass
   - All new tests must pass
2. Run: `python scripts/retrain_all.py --model props`
   - Retrains all 7 XGBoost prop models with expanded feature set
3. Log results to `vault/Improvements/Tracker Improvements Log.md`
