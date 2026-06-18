# Brier-Skill-Score CI Gate + Golden Dataset

_Design doc, 2026-06-16. For: roadmap item N1 (THE keystone). Build location: `scripts/platformkit/eval_gate/` + git-tracked fixtures under `tests/fixtures/golden/`. Per-file tests in `scripts/platformkit/eval_gate/test_*.py`. NO edits to `src/`, `kernel/`, `api/`, `scripts/team_system`, `intel`._

This is the contract every future change is judged by. If a change does not move the honest metric (Brier Skill Score vs the Shin-devigged close, proven with a Diebold-Mariano test, on BOTH corpora, leak-free), it does not ship. An honest BSS <= 0 (we do not beat the close here) is a recorded SUCCESS, not a failure -- the gate's job is to make that verdict auditable and to block regressions, never to manufacture an edge.

---

## Goal + done-criteria (what "shipped + validated" means, in measurable terms)

**Goal.** A fast, fully-local pytest + promptfoo gate that (1) runs a leak-free walk-forward backtest of our calibrated probability forecaster against the Shin-devigged market close, (2) computes Brier Skill Score, log-loss, reliability/ECE (diagnostic) and a sharpness/Resolution check, (3) proves "beats the close" / "does not regress" with a Diebold-Mariano test on per-game loss differences with clustered SEs and a 95% CI, and (4) **exits 1 on regression on EITHER of two corpora**. Plus a git-tracked golden set of ~100 frozen game states with truth WP so the gate is reproducible by a skeptic in < 60s offline.

**Done-criteria (all measurable, all must hold):**

1. `python -m scripts.platformkit.eval_gate.run_gate --golden` runs in < 60s on the committed fixtures (no network, no `data/`) and prints a one-screen scoreboard.
2. The golden set `tests/fixtures/golden/game_states.json` contains N_golden in [90, 120] states, schema-validated, with `truth_wp`, `outcome`, `devig_close_prob`, and `availability_date < game_date` asserted for every feature field.
3. Two corpora are wired: `corpus_a` = NBA 2023-24, `corpus_b` = NBA 2024-25 (same-sport two-season) AND a cross-sport second leg `corpus_mlb` is supported via the same spec (one of A/B may be MLB once X2 lands; until then NBA-2season satisfies the two-corpus rule and MLB is a registered-but-skipped slot).
4. The gate reports, **per corpus**, with a pre-registered baseline JSON: `BSS = 1 - Brier_model/Brier_close`, `Brier_model +/- 95% CI` (cluster-robust by `game_id`), `log_loss_model`, `ECE` (10 equal-width bins, diagnostic), `Resolution` and `sharpness` (var of preds), and the DM statistic + two-tailed p-value of (loss_close - loss_model).
5. **Regression rule (the contract):** the gate exits 1 if, on EITHER corpus, the candidate's per-game mean Brier is worse than the frozen baseline by more than the pre-registered tolerance AND the DM test confirms the degradation is significant (p < 0.05) -- OR if any leak-guard assertion fails (vintage, purge, embargo, feature-selection-inside-window flag). It exits 0 (PASS) otherwise, and labels each corpus `BEATS_CLOSE` (BSS>0, DM p<0.05, N>=200), `MATCHES_CLOSE` (CI overlaps close), or `BEHIND` (honest, recorded) -- none of these three block; only a regression-vs-our-own-baseline or a leak blocks.
6. A promptfoo config (`scripts/platformkit/eval_gate/promptfoo.yaml`) wraps the same Python gate as a CI assertion so the gate is runnable from the promptfoo runner with the identical exit semantics.
7. Per-file tests (`test_metrics.py`, `test_walkforward.py`, `test_gate.py`) pass via `python -m pytest scripts/platformkit/eval_gate/test_gate.py -q` (NEVER full `pytest tests/`).

A change is "shipped + validated" only when it is green on both corpora here and the baseline JSON has been intentionally re-frozen by a human review of the diff.

---

## Design (architecture, data flow, file/dir layout under an ALLOWED path)

### Data flow

```
golden_states.json (frozen)            real corpora (data/domains/<sport>, gitignored)
        |                                          |
        v                                          v
  load_golden() ---> GameState[]            load_corpus(spec) ---> GameState[]
        |                                          |
        +---------------------+--------------------+
                              v
                  walk_forward(states, spec)   # expanding window, purge 48h, embargo 3d,
                              |                 # feature-selection INSIDE window (flagged),
                              |                 # vintage assertion availability_date<game_date
                              v
              per-game records: {game_id, season, ts, p_model, p_close_devig, y}
                              |
            +-----------------+------------------+
            v                                    v
   score(records)                       devig is Shin (kernel.devig2 / mberk-shin)
   - brier_model, brier_close
   - bss = 1 - bm/bc
   - log_loss, ece(diag), resolution, sharpness
   - per-game loss diffs d_t = L_close - L_model
            |
            v
   dm_test(d_t, cluster=game_id) -> (dm_stat, p_value, ci95)
            |
            v
   verdict(corpus) -> {BEATS_CLOSE|MATCHES_CLOSE|BEHIND}, regression flag vs baseline
            |
            v
   run_gate over [corpus_a, corpus_b] -> exit 0/1   (exit 1 if EITHER regresses or leaks)
```

### Directory layout (all under ALLOWED paths)

```
scripts/platformkit/eval_gate/
  __init__.py
  schema.py           # GameState dataclass + JSON schema + validate_golden()
  golden_loader.py    # load_golden(path) -> List[GameState]; build helpers (offline)
  walkforward.py      # walk_forward(states, spec): expanding window + purge + embargo + vintage
  scoring.py          # brier/bss/log_loss/ece/resolution/sharpness (thin wrappers over kernel)
  dm_test.py          # diebold_mariano(d, cluster_ids) -> DMResult (HAC + cluster-robust SE)
  baseline.py         # load/freeze pre-registered baselines (JSON), tolerance config
  run_gate.py         # CLI; orchestrates corpora; exit 0/1; prints scoreboard
  promptfoo.yaml      # CI wrapper invoking run_gate as an assertion
  baselines/
    nba_2023_24.json  # frozen baseline metrics (committed)
    nba_2024_25.json
    mlb_2024.json     # registered slot; skip-until-present
  test_metrics.py     # per-file: scoring + dm correctness on synthetic data
  test_walkforward.py # per-file: purge/embargo/vintage assertions fire
  test_gate.py        # per-file: end-to-end on golden fixtures, exit-code semantics

tests/fixtures/golden/
  game_states.json    # ~100 frozen game states (git-tracked, ASCII JSON)
  README.md           # how the set was built + how to regenerate (reproducibility)
  SCHEMA.md           # field-by-field schema + provenance of truth_wp
```

Reuse, do not reimplement: `kernel/validation/proof_metrics.py` already exports `brier`, `devig2` (the Shin two-outcome devig), `ece`, `isotonic_calibrate`, `reliability_slope`. `scoring.py` imports these (read-only) and only ADDS bss / log_loss / resolution / sharpness / dm helpers that do not exist there. The model forecaster comes from the existing entry points the `beat_the_close_scoreboard` already calls (`scripts.platformkit.proof_nba.ml_accuracy.run`, `scripts.platformkit.nba_winprob_model.fit_winprob`); the gate consumes their per-game probabilities, it does not retrain anything in `src/`.

### The golden set (the frozen anchor)

- **Size + coverage.** ~100 states, stratified so the gate exercises every regime where calibration is fragile (per the briefs): pregame (~40), in-game by quarter Q1/Q2/Q3/Q4 (~40), and edge regimes (~20): blowouts, foul-trouble differential, garbage time, 4th-quarter-within-5, early-season games 1-20 (the structural-window trap), heavy favorites/longshots (FLB stress). Each tagged with `regime` for per-regime reliability slicing.
- **Truth WP provenance (two sources, both leak-free for the state's timestamp):**
  - *Pregame states:* `truth_wp` is NOT a magic number; it is the **devigged Pinnacle close** stored as `devig_close_prob` AND the realized binary `outcome`. The gate scores the model's pregame prob against `outcome` (Brier) and against `devig_close_prob` (the reference for BSS). The "truth" for calibration is the realized outcome; the close is the reference forecaster.
  - *In-game states:* `truth_wp` is the empirical win frequency from PBP replay -- the project's existing `scripts/team_system/pbp_replay.py` harness replays many historical games, and for a given `(score_diff, seconds_remaining, possession, foul_state)` bucket the realized win rate across the replay corpus is the truth label's basis. Store the bucket's `truth_wp` (empirical frequency) AND the single-game realized `outcome`. Per-game scoring uses `outcome`; bucket `truth_wp` is the calibration target for the in-game head's reliability diagram.
- **How states are picked for coverage.** A one-time offline builder (`golden_loader.build_golden(...)`, run by a human from the real `data/`) samples states by stratum, attaches `devig_close_prob` (Shin) and `outcome`, runs `assert_no_leak()` on each, then writes ASCII JSON. The builder lives in the repo but the gate NEVER calls it at gate time -- the gate only READS the committed `game_states.json`. This keeps the gate offline/deterministic and the fixture a stable regression anchor.
- **Storage.** Git-tracked JSON in `tests/fixtures/golden/` (NOT `data/`, which is gitignored). ASCII only. Numbers rounded to 6 dp for stable diffs. Each state carries `availability_date` per feature so the vintage assertion runs even on the fixture.

---

## Implementation sketch (concrete, copyable)

### `schema.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

GOLDEN_SCHEMA_VERSION = 1

@dataclass(frozen=True)
class GameState:
    game_id: str            # cluster key for SEs
    season: str             # "2023-24" ; second cluster level
    sport: str              # "nba" | "mlb" | ...
    regime: str             # "pregame" | "q1".."q4" | "blowout" | "foul_trouble" | ...
    game_date: str          # ISO date of tip (the prediction-time boundary)
    state_ts: str           # ISO datetime of the in-game state (== game_date for pregame)
    # features available as-of state_ts; each has an availability_date
    features: Dict[str, float]
    feature_avail: Dict[str, str]   # feature_name -> ISO date it became known
    devig_close_prob: float         # Shin-devigged Pinnacle close P(home/over win)
    truth_wp: float                 # empirical/replay WP for the state's bucket (in-game)
    outcome: int                    # realized binary outcome (0/1) -- the scoring label

REQUIRED = ("game_id", "season", "sport", "regime", "game_date", "state_ts",
            "features", "feature_avail", "devig_close_prob", "truth_wp", "outcome")

def validate_golden(states: List[dict]) -> None:
    assert 90 <= len(states) <= 120, f"golden set size {len(states)} out of [90,120]"
    seen = set()
    for s in states:
        for k in REQUIRED:
            assert k in s, f"missing field {k} in state {s.get('game_id')}"
        assert s["outcome"] in (0, 1)
        assert 0.0 <= s["devig_close_prob"] <= 1.0
        assert 0.0 <= s["truth_wp"] <= 1.0
        # vintage: every feature must be known strictly before the prediction time
        for f, avail in s["feature_avail"].items():
            assert avail < s["state_ts"], (
                f"LEAK: feature {f} availability {avail} >= state_ts {s['state_ts']} "
                f"in {s['game_id']}")
        key = (s["game_id"], s["state_ts"])
        assert key not in seen, f"duplicate state {key}"
        seen.add(key)
    # coverage guard: every fragile regime represented
    regimes = {s["regime"] for s in states}
    for r in ("pregame", "q4", "blowout", "foul_trouble"):
        assert r in regimes, f"coverage gap: regime {r} missing"
```

### `walkforward.py` (leak-free is enforced here, not assumed)

```python
from datetime import datetime, timedelta

PURGE_HOURS = 48        # drop same-team games within 48h of the test game
EMBARGO_DAYS = 3        # gap between train-end and test-start

def walk_forward(states, predict_fn, *, select_features_inside=True):
    """Expanding-window WF. predict_fn(train_states, test_state) -> p_model in [0,1].
    Returns per-game records. Asserts purge/embargo/vintage so a leak fails the gate."""
    states = sorted(states, key=lambda s: s.state_ts)
    records = []
    for i, test in enumerate(states):
        t = datetime.fromisoformat(test.state_ts)
        train = []
        for s in states[:i]:
            ts = datetime.fromisoformat(s.state_ts)
            if ts >= t:                       # never look ahead
                continue
            if (t - ts) < timedelta(days=EMBARGO_DAYS) and _same_teams(s, test):
                continue                      # embargo same-matchup near boundary
            if _same_team(s, test) and (t - ts) < timedelta(hours=PURGE_HOURS):
                continue                      # purge same-team back-to-back
            train.append(s)
        # vintage assertion (defense in depth -- schema also checks it)
        for f, avail in test.feature_avail.items():
            assert avail < test.state_ts, f"LEAK at gate-time: {f} in {test.game_id}"
        # feature selection / tuning MUST happen inside the window, on `train` only.
        p = predict_fn(train, test, select_inside=select_features_inside)
        assert 0.0 <= p <= 1.0
        records.append({"game_id": test.game_id, "season": test.season,
                        "ts": test.state_ts, "regime": test.regime,
                        "p_model": p, "p_close": test.devig_close_prob,
                        "y": test.outcome})
    return records
```

`select_inside=True` is a hard flag the gate records in its output; if any `predict_fn` selects features or tunes on the full set it must set it False, and the gate FAILS the run (feature-selection-inside-window is non-negotiable per the invariants and the evals brief gotcha).

### `scoring.py` (thin over kernel; adds only what kernel lacks)

```python
import numpy as np
from kernel.validation.proof_metrics import brier, ece  # reuse, do not reimplement

def log_loss(p, y):
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return float(-np.mean(y*np.log(p) + (1-y)*np.log(1-p)))

def brier_skill_score(p_model, p_ref, y):           # ref = devigged close
    bm, br = brier(p_model, y), brier(p_ref, y)
    return float(1.0 - bm/br) if br > 0 else 0.0

def resolution(p, y, bins=10):                      # Murphy resolution component
    o_bar = float(np.mean(y)); edges = np.linspace(0,1,bins+1); res = 0.0
    for k in range(bins):
        m = (p >= edges[k]) & (p < edges[k+1] if k < bins-1 else p <= edges[k+1])
        if m.sum() == 0: continue
        res += (m.mean()) * (y[m].mean() - o_bar)**2
    return float(res)

def sharpness(p):                                   # guard against collapse-to-0.5
    return float(np.var(p))
```

### `dm_test.py` (the significance test, cluster-robust)

```python
from dataclasses import dataclass
import numpy as np

@dataclass
class DMResult:
    dm_stat: float; p_value: float; mean_diff: float; ci95: tuple; n: int; n_clusters: int

def diebold_mariano(d, cluster_ids):
    """d_t = loss_close(t) - loss_model(t)  (positive => model better).
    Cluster-robust SE by game_id/season (naive SE runs ~3x too narrow)."""
    d = np.asarray(d, float); md = d.mean(); n = len(d)
    groups = {}
    for di, c in zip(d, cluster_ids): groups.setdefault(c, []).append(di)
    G = len(groups)
    # cluster-robust variance of the mean
    gsum = np.array([np.sum(v) - len(v)*md for v in groups.values()])
    var = (gsum @ gsum) / (n*n) * (G/(G-1)) if G > 1 else d.var(ddof=1)/n
    se = float(np.sqrt(var)); dm = md/se if se > 0 else 0.0
    from scipy import stats
    p = 2*(1 - stats.norm.cdf(abs(dm)))
    ci = (md - 1.96*se, md + 1.96*se)
    return DMResult(float(dm), float(p), float(md), ci, n, G)
```

### `run_gate.py` (the contract; exit semantics)

```python
import argparse, json, sys
from .golden_loader import load_golden
from .walkforward import walk_forward
from . import scoring as S
from .dm_test import diebold_mariano
from .baseline import load_baseline

CORPORA = ["nba_2023_24", "nba_2024_25"]   # mlb_2024 registered, skip-until-present
DM_MIN_N = 200
BRIER_REGRESS_TOL = 0.005                   # pre-registered min meaningful delta

def evaluate_corpus(name, predict_fn, golden_path=None):
    states = load_golden(golden_path) if golden_path else load_corpus(name)
    recs = walk_forward(states, predict_fn)
    pm = _arr(recs, "p_model"); pc = _arr(recs, "p_close"); y = _arr(recs, "y")
    gid = [r["game_id"] for r in recs]
    bm, bc = float(S.brier(pm, y)), float(S.brier(pc, y))
    bss = S.brier_skill_score(pm, pc, y)
    d = (pc - y)**2 - (pm - y)**2            # close loss - model loss, per game
    dm = diebold_mariano(d, gid)
    base = load_baseline(name)               # frozen JSON
    out = {"corpus": name, "n": len(recs), "brier_model": bm, "brier_close": bc,
           "bss": bss, "log_loss": S.log_loss(pm, y), "ece": float(S.ece(pm, y)),
           "resolution": S.resolution(pm, y), "sharpness": S.sharpness(pm),
           "dm_stat": dm.dm_stat, "dm_p": dm.p_value, "ci95": dm.ci95}
    # verdict (none of these block on their own)
    if bss > 0 and dm.p_value < 0.05 and dm.n >= DM_MIN_N:
        out["verdict"] = "BEATS_CLOSE"
    elif abs(bm - bc) <= 1.96*(dm.ci95[1]-dm.ci95[0])/3.92:
        out["verdict"] = "MATCHES_CLOSE"
    else:
        out["verdict"] = "BEHIND"            # honest, recorded, NON-blocking
    # REGRESSION rule (this DOES block): worse than our own frozen baseline,
    # by more than tolerance, with DM confirming significance.
    worsened = bm > base["brier_model"] + BRIER_REGRESS_TOL
    d_vs_base = (base["per_game_model_loss"] - (pm - y)**2)  # base better => positive
    dm_base = diebold_mariano(d_vs_base, gid)
    out["regressed"] = bool(worsened and dm_base.p_value < 0.05)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", action="store_true")
    ap.add_argument("--corpus", default=None)   # path to a real corpus dir
    args = ap.parse_args()
    predict_fn = _load_model_predictor()         # from existing proof_nba entry points
    rows = []
    for name in CORPORA:
        gp = "tests/fixtures/golden/game_states.json" if args.golden else None
        try:
            rows.append(evaluate_corpus(name, predict_fn, golden_path=gp))
        except FileNotFoundError:
            rows.append({"corpus": name, "status": "CORPUS_ABSENT (skip)"})
    _print_scoreboard(rows)
    measured = [r for r in rows if "regressed" in r]
    fail = any(r["regressed"] for r in measured) or not measured
    sys.exit(1 if fail else 0)
```

### `baselines/nba_2023_24.json` (frozen, human re-blessed on intentional change)

```json
{
  "corpus": "nba_2023_24", "schema": 1, "frozen_at": "2026-06-16",
  "n": 240, "brier_model": 0.2080, "brier_close": 0.1980,
  "bss": -0.0505, "verdict": "MATCHES_CLOSE",
  "tolerance_brier": 0.005,
  "note": "BSS<0 here is the HONEST result (pregame efficient). The gate blocks REGRESSION vs this baseline, not the non-beat.",
  "per_game_model_loss_path": "baselines/nba_2023_24_pergame.npy"
}
```

### `promptfoo.yaml` (CI wrapper, identical exit semantics, fully local)

```yaml
# scripts/platformkit/eval_gate/promptfoo.yaml -- runs the SAME python gate.
description: "Brier-Skill-Score CI gate (calibration vs devigged close; local-only)"
providers:
  - id: exec
    config:
      command: "python -m scripts.platformkit.eval_gate.run_gate --golden"
prompts: ["{{input}}"]
tests:
  - vars: {input: "run"}
    assert:
      - type: javascript
        # promptfoo marks pass iff the gate exited 0 (no regression on either corpus)
        value: "output.exitCode === 0"
      - type: contains
        value: "verdict"
defaultTest:
  options:
    runSerially: true
```

### Sample assertion (the contract, in `test_gate.py`)

```python
def test_gate_blocks_regression_on_either_corpus(tmp_path):
    # synthetic candidate that degrades corpus_b Brier by > tolerance, significantly
    rows = run_gate_in_process(predict_fn=_degraded_on_b())
    a = next(r for r in rows if r["corpus"] == "nba_2023_24")
    b = next(r for r in rows if r["corpus"] == "nba_2024_25")
    assert a["regressed"] is False
    assert b["regressed"] is True          # the degraded corpus
    assert gate_exit_code(rows) == 1       # EITHER corpus regressing -> exit 1

def test_gate_passes_when_matches_close_no_regression():
    rows = run_gate_in_process(predict_fn=_frozen_baseline_model())
    assert all(not r["regressed"] for r in rows)
    assert gate_exit_code(rows) == 0       # BEHIND/MATCHES do NOT block; only regression does

def test_vintage_assertion_fires_on_leak():
    bad = _golden_with_future_feature()    # availability_date >= state_ts
    with pytest.raises(AssertionError, match="LEAK"):
        walk_forward(bad, _trivial_predict)

def test_dm_cluster_se_wider_than_naive():
    # per evals brief: clustered SE must be ~ wider; naive over-rejects
    d, gid = _clustered_loss_diffs()
    assert diebold_mariano(d, gid).p_value > _naive_p(d)
```

---

## Validation plan (leak-free; the metric, test, thresholds)

**Backtest design (baked into `walk_forward`, not optional):**
- Expanding window: train on all states with `state_ts < t`, predict t, advance. No K-fold (correctness bug on time-ordered data).
- Purge: drop same-team games within `PURGE_HOURS = 48` of the test game (kills back-to-back autocorrelation).
- Embargo: `EMBARGO_DAYS = 3` gap on the same matchup near the train/test boundary (rolling-window spillover).
- Feature selection + hyperparameter tuning happen INSIDE the window (`predict_fn(..., select_inside=True)`); the gate records the flag and FAILS if it is False.
- Vintage alignment: `assert availability_date < state_ts` for every feature, in BOTH `schema.validate_golden` and `walk_forward` (defense in depth).

**Corpora (>= 2 independent):** `nba_2023_24` and `nba_2024_25` for same-sport two-season; `mlb_2024` registered as a cross-sport slot that becomes a hard second leg once X2 (MLB in-game) lands. Per-corpus metrics reported separately (never pooled) -- a lift on A with a drop on B is the overfit red flag and trips the regression rule.

**Metric stack (per corpus):**
- Primary: `BSS = 1 - Brier_model / Brier_close` where the close is **Shin-devigged Pinnacle** (`kernel.proof_metrics.devig2`), never a soft book, never multiplicative on lopsided markets.
- Brier_model with **95% CI, cluster-robust by `game_id`** (and by `season` for the pooled view). Naive SE runs ~3x too narrow.
- Log-loss alongside Brier (catches confident-wrong the quadratic misses); report median per-game log-loss too (one blowup can dominate the mean).
- ECE (10 equal-width bins) -- DIAGNOSTIC ONLY, never the optimization target; always paired with `sharpness` (var of preds) and `resolution` so a collapse-to-0.5 cannot look good.
- Reliability slope (`kernel.reliability_slope`) overlaying model vs devigged close, per regime.

**Statistical test (the bar for "beats the close"):** Diebold-Mariano on per-game `d_t = loss_close - loss_model`, asymptotically N(0,1), cluster-robust SE. Require **p < 0.05 AND N >= 200** to label `BEATS_CLOSE`. N >= 200 is reached by pooling the golden set across seasons/regimes (single NBA season per market is underpowered). `BEHIND` and `MATCHES_CLOSE` are honest, recorded, non-blocking verdicts.

**Regression threshold (the blocking rule):** pre-registered `BRIER_REGRESS_TOL = 0.005` absolute (the minimum meaningful delta from the Anthropic statistical-eval discipline). A candidate is `regressed=True` on a corpus iff its mean Brier exceeds the frozen baseline by > tolerance AND a DM test of candidate-vs-baseline per-game losses is significant (p < 0.05). Any corpus `regressed=True` -> `exit(1)`. Any leak assertion -> `exit(1)`. Empty measured set -> `exit(1)` (fail closed).

**Per-regime slicing (attribution honesty):** separate reliability + Brier for games 1-20 vs 21+ (early-season structural window != model skill) and for pregame vs each quarter (live models are documented overconfident in Q1). Reported, not blocking, but surfaces where a "win" is really a timing artifact.

---

## Effort + sequencing (rough days; dependencies; first move)

- **Day 1 -- metrics + DM (lowest risk, no data).** Write `scoring.py`, `dm_test.py`, `schema.py` + `test_metrics.py`. Unit-test BSS/log-loss/resolution/sharpness and the cluster-robust DM on synthetic data with a known answer. No corpus needed. Depends on nothing.
- **Day 1-2 -- golden set builder + fixture.** `golden_loader.build_golden` (offline, human-run once from real `data/` + `pbp_replay.py` + Shin-devigged closes), produce `tests/fixtures/golden/game_states.json` (~100 stratified states) + `SCHEMA.md` + `README.md`. Validate with `validate_golden`. Depends on `schema.py`.
- **Day 2-3 -- walk-forward + gate orchestration.** `walkforward.py` (purge/embargo/vintage), `baseline.py`, `run_gate.py`, `test_walkforward.py`, `test_gate.py`. Freeze `baselines/*.json` from a first clean run (human blesses). Depends on Days 1-2.
- **Day 3-4 -- promptfoo wrapper + docs.** `promptfoo.yaml`, wire `make gate` / one-line CLI, confirm < 60s offline, write the contract into the eval_gate `README`. Depends on `run_gate.py`.

**First move:** Day 1 metrics/DM + the golden schema -- they are pure functions, fully testable offline, and unblock everything else. The golden fixture is the long pole (human curation), so kick its build off in parallel.

**Dependencies / collision avoidance:** the active branch `fullsend-ingame-pregame-execution` is editing in-game/pregame code -- this blueprint adds ONLY new files under `scripts/platformkit/eval_gate/` and `tests/fixtures/golden/`, touching no shared file. It CONSUMES the model's per-game probabilities through existing read-only entry points (`proof_nba.ml_accuracy.run`, `nba_winprob_model.fit_winprob`), so it never edits the live forecaster. The one shared-config item -- adding a PreToolUse/CI hook in `.claude/settings.json` to run the gate -- is **human-confirm before applying** (deferred to roadmap N4, not done here).

---

## Gotchas + how the honest discipline applies

- **The gate must not chase an edge.** BSS <= 0 on pregame NBA is the CORRECT, recorded result (markets efficient on price). The gate's blocking rule is REGRESSION-vs-our-own-frozen-baseline + LEAK, NOT "fails to beat the close." Conflating the two would resurrect the defeatist-or-fabricated dichotomy the north star forbids.
- **Shin, not multiplicative, not soft books.** Use `kernel.devig2` (Shin) for the close; keep multiplicative only at near -110/-110 for speed. A multiplicative devig flatters the model on lopsided markets (FLB) and would make a non-win look like a win. Benchmark against devigged Pinnacle only.
- **Clustered SEs are mandatory.** Multiple game-states per game/season cluster; naive SE is ~3x too narrow and over-rejects, manufacturing fake "beats." The DM SE clusters by `game_id`; the pooled view clusters by `season`. `test_dm_cluster_se_wider_than_naive` guards this.
- **ECE is a trap as a target.** Predicting 0.5 everywhere gives near-zero ECE and zero value. ECE is diagnostic-only; the gate pairs it with `sharpness`/`resolution` so collapse cannot pass.
- **Feature selection inside the window.** Even a leak-free walk-forward is optimistic if features were chosen on the full history first. The `select_inside` flag is recorded and a False value FAILS the run.
- **Single-corpus lift is an artifact.** The gate evaluates BOTH corpora and the regression rule fires if EITHER degrades; a lift on A with a drop on B is the classic overfit signature and trips it. Two-corpus is non-negotiable.
- **Golden-set distribution drift.** A frozen 100-state fixture can stop resembling the live distribution as seasons turn; `SCHEMA.md` records provenance and the human re-blesses the fixture + baselines on intentional re-freeze. The fixture is a regression ANCHOR, not the production eval -- the real-corpus path (`--corpus`) is the full bar.
- **Local-only, fail-closed, fast.** No network at gate time, no `data/registry/` writes, no flag flips. Empty measured set -> exit 1 (never silently pass). < 60s on fixtures so it can run on every commit via per-file pytest (never full `pytest tests/`, which freezes the box).
- **LLM never in the loop.** This gate scores numeric probabilities only; no LLM judges Brier. The quantitative pipeline computes every number; the LLM layer (narrative/extraction) is evaluated separately with `model_graded_qa`, out of scope here.

---

## Sources / cross-refs
- `docs/research/ai-leverage-2026-06-16/05-elevation-roadmap.md` (N1, invariants), `briefs/evals-quality.md` (BSS gate, SEM discipline, golden set, two-corpus, promptfoo), `briefs/calibration-scoring.md` (Murphy decomposition, DM test, Shin baseline, sharpness), `briefs/market-efficiency-clv.md` (Shin devig, purge/embargo, CLV-as-calibration-benchmark).
- `docs/research/validation-methodology.md` (walk-forward + 48h purge, Shin devig, calibration check), `docs/research/edge-taxonomy.md`.
- Existing code reused read-only: `kernel/validation/proof_metrics.py` (`brier`, `devig2`, `ece`, `reliability_slope`, `isotonic_calibrate`); `scripts/platformkit/beat_the_close_scoreboard.py`, `scripts/platformkit/proof_nba/{ml_accuracy,asof_box_accuracy}.py`, `scripts/platformkit/proof_common/runner.py`; `scripts/team_system/pbp_replay.py` (in-game truth-WP source, human-run only).
