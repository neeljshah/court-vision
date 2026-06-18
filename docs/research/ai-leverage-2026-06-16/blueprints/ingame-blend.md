# In-Game Blend: Condition the Calibrated Pregame Prior on Realized Game State
_Design doc, 2026-06-16. For: roadmap N3 (NBA blend) + X2 (MLB second corpus). Build location: domains/basketball_nba/ and domains/mlb/ (NO src/ or kernel/ edits -- the pregame sim is consumed as a BLACK-BOX prior). Helpers shared via scripts/platformkit/._

This is the #1 leverage lever. The pregame Monte Carlo (P0) already MATCHES the devigged market
close (per project notes: pregame markets are efficient). In-game conditioning is NOT a re-pricing of
the same information -- realized score margin, time elapsed, foul state, and bonus are information the
pregame line could NOT have had. By construction this is NEW information, so a measured Brier
improvement here is an HONEST calibration gain, not a market-beating $ claim. We claim accuracy, never ROI.

---

## Goal + done-criteria

Build a live win-probability head `final = w(t, margin) * P_live + (1 - w) * P0` that improves OOS,
per-quarter calibration over both the pregame-only prior AND the current `pbp_replay.py` win-prob
baseline (today Q1-Q3 Brier 0.34-0.40 -- a Phi(proj_margin/sigma) closed form with NO trained P_live
and NO empirical weight surface).

"Shipped + validated" means ALL of the following hold, written to a committed JSON proof:

1. **Beats the in-game baseline.** Blended win-prob Brier < the `pbp_replay.py` Phi-margin Brier in
   EVERY quarter bucket Q1-Q4, on a held-out NBA SEASON the weight surface `w` was NOT fit on.
   Target: Q1-Q3 from 0.34-0.40 down to < 0.25 (Q1-Q3 is where the prior matters most and the current
   closed form fails); Q4 down to < 0.10 (literature: ~0.085).
2. **Beats pregame-only.** Blended Brier < pregame-only Brier (w forced to 0) with Diebold-Mariano
   p < 0.05 on the pooled OOS set, errors clustered by game_id.
3. **Calibrated, not just sharp.** Per-quarter reliability diagram (10 equal-width bins) closer to the
   diagonal than the baseline; Murphy decomposition shows LOWER reliability term AND >= equal resolution.
   ECE reported per quarter (never optimized directly).
4. **Two corpora, two ways.** Holds on (a) NBA fit-on-season-A / eval-on-season-B AND
   (b) MLB (X2): blended per-inning Brier beats MLB's own published win probability as the live baseline,
   fit on one set of seasons, eval on Retrosheet-derived seasons.
5. **No overfitting tell.** The in-sample-vs-OOS Brier gap on `w` is < 0.01 (the documented Statsurge
   trap: a `w` fit and evaluated on the same games inflates the gain). If the gap is large, the surface
   is over-resolved -> coarsen the grid or regularize and re-run. An honest REJECT here is a success.

If after this any feature (e.g. heat/momentum) fails to lower OOS Brier+reliability, it is dropped and
recorded as an honest reject -- exactly as the prior `pbp_replay.py` ablations dropped share/heat/cap.

---

## Design

### Data flow

```
                 [P0]  pregame sim (BLACK BOX)
                 src.sim.basketball_sim.TeamModel + fast_sim.simulate_game_fast
                 -> home win prob from simulated margin distribution
                    (read EXACTLY as pbp_replay.pregame_anchor does today; we do NOT edit it)
                       |
live PBP state  ----> [feature builder] --(score_diff, sec_remaining, foul_diff, bonus, gt_flag)-->
data/live/<gid>_*.json (NBA)                                  |
statsapi feed/live      (MLB)                                 v
                                              [P_live]  trained logistic / XGBoost  -> p_live
                                                              |
                       [w-surface]  w(t, margin)  empirical 2D table fit on a HELD-OUT season
                                                              |
                                                              v
            final_raw = w * p_live + (1 - w) * P0
                                                              |
            [garbage-time clamp]  if |margin| > T_gt and sec_remaining < S_gt -> clamp to {0.02, 0.98}
                                                              |
            [exp smoothing]  p_t = alpha * final_raw_t + (1 - alpha) * p_(t-1)  over last 3-5 possessions
                                                              |
                                                              v
                                          calibrated live win prob  (per-quarter isotonic post-hoc)
```

### File / dir layout (all under ALLOWED paths; all <= 300 LOC; new files only -> no collision with the
active `fullsend-ingame-pregame-execution` branch, which edits `src/prediction/live_engine.py`)

```
domains/basketball_nba/
  ingame_blend.py            # blend_prob(), garbage_clamp(), smooth_series() -- pure functions, the core
  ingame_features.py         # build_state_features(live_state) -> dict (NBA: foul_diff, bonus, gt_flag)
  ingame_weight_surface.py   # fit_weight_surface(games) -> WeightSurface ; WeightSurface.w(t, margin)
  ingame_plive.py            # fit_plive(rows) -> sklearn estimator ; predict_plive(model, feats)
domains/mlb/
  ingame_blend_mlb.py        # X2: same blend, MLB state adapter (count/runners/inning/score)
  ingame_features_mlb.py     # build_state_features_mlb(feed_live) -> dict
  ingame_feed_mlb.py         # poll statsapi.mlb.com/.../game/<pk>/feed/live -> normalized states + mlb_wp
scripts/platformkit/
  ingame_blend_eval.py       # the leak-free harness: walk-forward, DM test, per-quarter reliability, two-corpus
  ingame_reliability.py      # reliability_diagram(), murphy_decompose(), ece() -- shared NBA+MLB
domains/basketball_nba/tests/
  test_ingame_blend.py       # per-file pytest ONLY (never pytest tests/ -- freezes the box)
data/cache/ingame/           # gitignored: fitted w-surface + P_live pickle + proof JSON (NOT data/registry/)
```

The pregame prior is reused verbatim from `pbp_replay.py` (`pregame_anchor` already returns a
simulated margin distribution; we add one line to derive `P0 = P(home margin > 0)` from `res.home_total
- res.away_total`). No change to `src/sim/`.

---

## Implementation sketch

### Core blend (domains/basketball_nba/ingame_blend.py) -- pure, sport-agnostic-ready

```python
from __future__ import annotations
import numpy as np

def blend_prob(p_live: float, p0: float, w: float) -> float:
    """final = w * p_live + (1 - w) * p0.  w in [0, 1] from the empirical surface."""
    w = float(np.clip(w, 0.0, 1.0))
    return w * float(p_live) + (1.0 - w) * float(p0)

def garbage_clamp(p: float, margin_abs: float, sec_remaining: float,
                  t_gt: float = 18.0, s_gt: float = 120.0,
                  lo: float = 0.02, hi: float = 0.98, leader_is_home: bool = True) -> float:
    """Late-game blowout: a score/time model is over-confident in the trailing team -> hard clamp.
    margin_abs >= t_gt AND sec_remaining < s_gt -> push to the deterministic outcome."""
    if margin_abs >= t_gt and sec_remaining < s_gt:
        return hi if leader_is_home else lo
    return p

def smooth_series(probs: list[float], alpha: float = 0.4) -> list[float]:
    """EMA over last 3-5 possessions (alpha ~0.3-0.5). Kills jagged single-possession jumps;
    improves PERCEIVED calibration and the reliability diagram. Causal: uses only past values."""
    out, prev = [], None
    for p in probs:
        prev = p if prev is None else alpha * p + (1.0 - alpha) * prev
        out.append(prev)
    return out
```

### State features (domains/basketball_nba/ingame_features.py)

Minimal-feature discipline from the in-game brief: (score_diff, sec_remaining) explain >90% of
variance; foul_diff + bonus + gt_flag are the only two additions justified by evidence (foul-out is the
one in-game modifier that survived this project's own replay validation). NO PBP sequence embeddings.

```python
def build_state_features(st: dict, home: str, away: str) -> dict:
    """st = one normalized live snapshot (period, clock_s, scores, per-player pf, on-court).
    Returns the P_live feature row. Leak-safe: every field is observable at state time."""
    sec_remaining = _sec_remaining(st["period"], st["clock_s"])   # 0 at final buzzer
    score_diff = st["home_score"] - st["away_score"]              # home perspective, signed
    # foul-trouble differential: count players with pf>=4 (1 from bench, near foul-out)
    home_trouble = sum(1 for p in st["players"].values() if p["team"] == home and (p.get("pf") or 0) >= 4)
    away_trouble = sum(1 for p in st["players"].values() if p["team"] == away and (p.get("pf") or 0) >= 4)
    foul_diff = away_trouble - home_trouble                       # +ve favors home
    bonus = _team_bonus_flag(st, home) - _team_bonus_flag(st, away)  # in penalty -> free FTs
    margin_abs = abs(score_diff)
    return dict(score_diff=score_diff, sec_remaining=sec_remaining,
                foul_diff=foul_diff, bonus=bonus, margin_abs=margin_abs,
                time_pressure=score_diff * (1.0 / max(sec_remaining, 30.0)))  # iWinRNFL composite
```

### P_live (domains/basketball_nba/ingame_plive.py)

```python
from sklearn.linear_model import LogisticRegression  # XGBoost is the upgrade if logistic saturates

PLIVE_FEATS = ["score_diff", "sec_remaining", "foul_diff", "bonus", "time_pressure"]

def fit_plive(rows: "pd.DataFrame"):
    """rows: one row per (game, state) with PLIVE_FEATS + label home_won in {0,1}.
    Fit on the FIT season(s) ONLY. Logistic first (NFL evidence: 10-var logit beats deeper nets)."""
    X, y = rows[PLIVE_FEATS].to_numpy(), rows["home_won"].to_numpy()
    return LogisticRegression(max_iter=1000, C=1.0).fit(X, y)

def predict_plive(model, feats: dict) -> float:
    import numpy as np
    return float(model.predict_proba(np.array([[feats[k] for k in PLIVE_FEATS]]))[0, 1])
```

### The 2D empirical weight surface (domains/basketball_nba/ingame_weight_surface.py)

The asymmetric-by-strength weight: trust P_live more when realized state is large/late; trust P0 more
early. Fit as an empirical lookup on a HELD-OUT season, NOT the eval season.

```python
import numpy as np

# grid edges chosen coarse to AVOID over-resolution (the Statsurge overfitting trap)
TIME_EDGES   = np.array([2880, 2160, 1440, 720, 360, 120, 0])    # sec_remaining, Q-ish boundaries
MARGIN_EDGES = np.array([0, 3, 6, 10, 16, 25, 1e9])              # |margin| buckets

class WeightSurface:
    def __init__(self, grid: np.ndarray):   # grid[i, j] in [0,1]
        self.grid = grid

    def w(self, sec_remaining: float, margin_abs: float) -> float:
        i = int(np.clip(np.searchsorted(-TIME_EDGES, -sec_remaining) - 1, 0, self.grid.shape[0]-1))
        j = int(np.clip(np.searchsorted(MARGIN_EDGES, margin_abs) - 1, 0, self.grid.shape[1]-1))
        return float(self.grid[i, j])

def fit_weight_surface(rows, p_live_col="p_live", p0_col="p0", label="home_won") -> WeightSurface:
    """For each (time, margin) cell, choose w* in [0,1] that MINIMIZES Brier of
    w*p_live + (1-w)*p0 vs realized home_won, over rows falling in that cell (grid-search w in 0..1
    step 0.05). Empty/sparse cells (n<200) inherit the neighbor with more time (default: trust P0)."""
    grid = np.zeros((len(TIME_EDGES)-1, len(MARGIN_EDGES)-1))
    ws = np.arange(0.0, 1.0001, 0.05)
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            cell = _rows_in_cell(rows, i, j)              # by TIME_EDGES / MARGIN_EDGES
            if len(cell) < 200:
                grid[i, j] = grid[i-1, j] if i > 0 else 0.0
                continue
            pl, p0, y = cell[p_live_col].to_numpy(), cell[p0_col].to_numpy(), cell[label].to_numpy()
            briers = [(np.mean((w*pl + (1-w)*p0 - y) ** 2)) for w in ws]
            grid[i, j] = float(ws[int(np.argmin(briers))])
    return WeightSurface(grid)
```

Expected shape (sanity, not hard-coded): w near 0 in the top-left (early, close), rising toward 1 in the
bottom-right (late, large margin). If the fitted grid is NOT roughly monotone in both axes, the cells are
under-populated -> coarsen.

### MLB adapter (X2 -- domains/mlb/)

Same blend; MLB state replaces NBA state. Free feed: `https://statsapi.mlb.com/api/v1.1/game/<gamePk>/feed/live`.

```python
# ingame_features_mlb.py
MLB_FEATS = ["score_diff", "outs_remaining_est", "inning", "is_home_batting",
             "runners_score_state", "leverage_proxy"]
def build_state_features_mlb(play: dict, home_pk, away_pk) -> dict:
    """play = one liveData.plays.allPlays entry. score_diff signed (home), inning, half,
    runners (base-out state), outs. outs_remaining_est = (9 - inning)*6 + (3 - outs) ... half-aware.
    Leak-safe: state as-of the pitch/play boundary."""
    ...
# ingame_blend_mlb.py reuses blend_prob/smooth_series from the NBA core (import the pure functions).
# MLB's own published win probability (liveData...winProbability) is the BASELINE to beat per inning.
```

---

## Validation plan (leak-free; the whole point)

Harness: `scripts/platformkit/ingame_blend_eval.py`, reusing the per-quarter bucketing and pregame
anchor logic already in `pbp_replay.py`. The current `pbp_replay.py` win-prob (Phi(proj_margin/sigma),
NO P_live, NO surface) is the explicit baseline to beat.

### Leak-free protocol
- **Walk-forward by season.** Fit `w` and `P_live` ONLY on season A states; evaluate ONLY on season B
  states (and vice-versa). The pregame P0 anchor must be the as-of cache for the eval game's date
  (availability_date < game_date) -- reuse `pbp_replay.py`'s leak note discipline.
- **Purge + embargo.** A "sample" here is a (game, state) row; many rows share a game and are highly
  autocorrelated. Cluster by game_id for all SEs. Embargo: no game from the eval season may appear in
  the fit set; purge any game within 48h of an eval game involving a shared team (kills schedule
  autocorrelation) -- mirrors `src/prediction/prop_backtester.py`.
- **Feature selection inside the window.** foul_diff/bonus/gt-params chosen on fit-season hold-out only.

### Metrics + tests + thresholds
1. **Per-quarter Brier** (NBA: Q1-Q4; MLB: per-inning 1-9+). Bucketed exactly as `pbp_replay.py` does.
   Threshold: blended Brier < baseline Brier in every bucket on OOS.
2. **Diebold-Mariano** on pooled OOS loss-difference (blended Brier vs pregame-only, and vs the
   Phi-margin baseline). `ingame_reliability.dm_test(loss_a, loss_b, game_ids)` -> DMResult.
   SE is cluster-robust by game_id (reuses `eval_gate/dm_test.diebold_mariano`); do NOT use
   Newey-West HAC over the flat state series -- that pairs lags across game boundaries and
   runs ~3x too narrow. Threshold: p_value < 0.05 for "beats".
3. **Reliability + Murphy.** `reliability_diagram(p, y, n_bins=10)` per quarter; `murphy_decompose`
   reports Reliability - Resolution + Uncertainty. Threshold: lower Reliability AND >= equal Resolution
   vs baseline; plot blended vs baseline curve. ECE reported per quarter, NEVER optimized.
4. **Overfitting tell.** Report in-sample (fit-season) Brier vs OOS (eval-season) Brier of the `w`
   surface. Threshold: gap < 0.01. Larger -> coarsen grid / raise min-cell-n / regularize, re-run.
5. **Two corpora.** (a) NBA A->B and B->A; (b) MLB modern-seasons fit, Retrosheet-derived seasons eval,
   beating MLB published WP per inning. A gain that holds on only ONE corpus is an artifact -> REJECT.

### Statistical-test helper (scripts/platformkit/ingame_reliability.py)

Reuse `scripts/platformkit/eval_gate/dm_test.diebold_mariano`, clustering by game_id.
Do NOT inline a Newey-West HAC over the flattened pooled per-state series -- pooling
manufactures fake significance because per-state losses within a game are highly correlated
and Newey-West lags pair autocovariances ACROSS game boundaries.

> **DM SE clusters by game_id (per-state losses within a game are highly correlated); do NOT pool states as one HAC series.**

```python
# ingame_reliability.py -- import and re-export; do NOT reimplement DM here.
from scripts.platformkit.eval_gate.dm_test import diebold_mariano  # cluster-robust by game_id

def dm_test(loss_a, loss_b, game_ids):
    """Thin wrapper: d_t = loss_a_t - loss_b_t; clusters by game_id.
    Returns DMResult(dm_stat, p_value, mean_diff, ci95, n, n_clusters).
    Caller must pass game_ids aligned with loss_a/loss_b (one entry per state row).
    Negative dm_stat with p_value < 0.05 => model A (blended) is significantly better.
    SE is cluster-robust (naive SE runs ~3x too narrow on within-game state rows)."""
    import numpy as np
    d = np.asarray(loss_a) - np.asarray(loss_b)
    return diebold_mariano(d, game_ids)
```

The underlying `diebold_mariano(d, cluster_ids)` from `eval_gate/dm_test.py` sums residuals
within each game cluster, computes the between-cluster variance, and applies the
`G/(G-1)` small-sample correction -- see that file for the full implementation.

---

## Effort + sequencing (~1 week NBA, +1-2 weeks MLB)

Do FIRST (day 0): add the one line in a NEW wrapper (not in pbp_replay.py) that turns the existing
pregame sim margin distribution into `P0 = P(home_margin > 0)`. This unblocks everything and touches no
shared code.

1. **Day 1-2 -- NBA P_live + features.** `ingame_features.py` + `ingame_plive.py`. Build the
   (game, state, label) training table by replaying `data/live/<gid>_*.json` through `build_state_features`.
   Fit logistic; sanity-check Brier improves with time elapsed.
2. **Day 2-3 -- weight surface + blend.** `ingame_weight_surface.py` + `ingame_blend.py`
   (garbage_clamp, smooth_series). Wire `blend_prob`.
3. **Day 3-4 -- eval harness.** `ingame_blend_eval.py` + `ingame_reliability.py`. Run NBA A->B; confirm
   the five done-criteria; per-quarter reliability + DM. This is the gate.
4. **Day 5 -- ablate features.** Drop foul_diff/bonus/gt/smoothing one at a time; keep ONLY what lowers
   OOS Brier+reliability (mirror the existing pbp_replay ablation table). Record honest rejects.
5. **Week 2-3 -- X2 MLB.** `ingame_feed_mlb.py` (statsapi), `ingame_features_mlb.py`,
   `ingame_blend_mlb.py` (imports the NBA core pure functions). Eval vs MLB published WP per inning,
   Retrosheet as the independent second MLB corpus. Run NBA + MLB pipelines as PARALLEL subagents
   (Sectioning) -- they are independent.

Dependencies: P_live + surface before blend; blend before harness; harness before ablation; NBA pattern
proven before MLB. The pregame P0 wrapper gates all of it.

---

## Gotchas + how the honest discipline applies

- **The Statsurge overfitting trap is the #1 risk.** A `w` surface fit AND evaluated on the same games
  inflates the gain. Enforced by criterion 5 (in-sample vs OOS gap < 0.01) and the A->B / B->A
  cross-season split. A coarse grid (6x6) with min-cell-n=200 is deliberately under-resolved to resist
  this. If it still overfits, that is an honest REJECT -- report it.
- **Within-game autocorrelation faked significance.** Thousands of states from one game are NOT
  independent. ALL SEs cluster by game_id; DM uses HAC variance. Do not report a naive t-test on rows.
- **Calibration != accuracy != sharpness.** Criterion 3 requires LOWER reliability AND >= equal
  resolution (Murphy). A model can look calibrated but lose resolution by collapsing toward P0; the
  decomposition catches it.
- **Garbage time breaks score-and-time.** A linear blend stays over-confident in the trailing team in
  blowouts -> the hard `garbage_clamp`. Tune T_gt/S_gt on the fit season only.
- **Foul-out is the highest-impact unpriced event** and the only in-game modifier that survived this
  project's prior replay validation -> foul_diff is a first-class feature, not optional.
- **This is NEW information, so the claim is CALIBRATION, never $.** We say "blended live Brier beats
  the pregame prior and the prior baseline by X with DM p<0.05 on two corpora." We NEVER translate that
  to ROI/edge. The pregame model still MATCHES the close; the gain comes only from information the close
  could not have had (realized state) -- that is exactly why it is honest.
- **Invariants respected:** no src/ or kernel/ edits (P0 is a black box); all new files in
  domains/<sport> + scripts/platformkit, <= 300 LOC each; per-file tests only (NEVER pytest tests/ --
  freezes the box: `python -m pytest domains/basketball_nba/tests/test_ingame_blend.py -q`); no flag
  flipped ON; nothing written to data/registry/ (fitted artifacts go to gitignored data/cache/ingame/);
  local-only, never push origin; targeted git add.
- **Branch-collision avoidance:** the active `fullsend-ingame-pregame-execution` branch edits
  `src/prediction/live_engine.py`. This blueprint adds only NEW files under domains/ and
  scripts/platformkit and touches NO shared config. It does NOT modify `.claude/settings.json`. If a
  future step wants a hook (e.g. N4) or any settings.json change, flag it human-confirm-before-applying.
- **bash cwd is flaky:** prefix every bash command with `cd /c/Users/neelj/nba-ai-system &&`.
  stdout is cp1252 -> ASCII only in any printed report (no unicode arrows).
