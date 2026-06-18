# Reference Implementation -- runnable, tested code for the keystone

_2026-06-16. This is REAL, RUNNABLE code (not pseudocode) for the pure core of the eval gate
(blueprint N1) -- written here in the private research dir on purpose: it does not touch the
shared/tracked tree or collide with the active `fullsend-ingame-pregame-execution` session.
When you are ready, copy `eval_gate/` into `scripts/platformkit/eval_gate/` and wire the
walk-forward + corpus loaders around it per `blueprints/eval-gate.md`._

## What's here

`eval_gate/` -- the offline, dependency-light (numpy + stdlib only) core:
- `scoring.py` -- brier, log_loss, brier_skill_score (vs the devigged close), ece (diagnostic),
  resolution, sharpness. BSS<=0 is an HONEST result, not a failure.
- `dm_test.py` -- the **cluster-robust** Diebold-Mariano test (clusters by game_id). This is the
  correct version; the package QA caught a non-clustered DM in the in-game blueprint -- this is
  what both gates should reuse.
- `schema.py` -- GameState + `validate_golden()` with the leak guard (availability_date < state_ts)
  and fragile-regime coverage check.
- `walkforward.py` -- the leak-free backtest engine (the blueprint's "long pole"): expanding window,
  purge (same-team < 48h), embargo (same matchup < 3d), vintage assertion, and the select-inside flag
  the gate fails on. This is where leak-freeness is ENFORCED, not assumed.
- `shin.py` -- the CORRECT, tested Shin (1992/93) devig (n-outcome solver that normalizes to 1).
  The QA pass found the Shin closed-form in the older validation-methodology.md does not normalize;
  this is the vetted reference the gate scores the close against.
- `ingame_blend.py` -- the #1 leverage lever (blueprint N3): `blend(p0, p_live, w)` + a 2D weight
  surface fit on one season and evaluated on a DIFFERENT one (the overfitting-trap discipline) +
  exponential smoothing. Reuses the clustered `diebold_mariano`. New information by construction ->
  an honest calibration gain, never a re-pricing.
- `freshness_schema.py` -- the freshness lever (blueprint X1): typed InjuryDelta + schema validation +
  the VINTAGE LEAK GUARD (extracted_at < tip) + the fallback-proxy quarantine (the QA fix -- metrics on
  outcome-conditioned proxy rows are labeled OPTIMISTIC_UPPER_BOUND, never leak-free wins).
- `ledger.py` -- the track-record ledger + calibration-drift monitor (blueprint X3 / the trust moat):
  append-only JSONL of (prediction, outcome) + a rolling Brier drift check that alerts when recent
  calibration degrades > k-sigma vs a 30-day baseline (fail-quiet without data). Logs probabilities +
  outcomes only -- never units/ROI/edge.
- `test_eval_core.py` (8) + `test_walkforward.py` (6) + `test_shin.py` (5) + `test_ingame_blend.py` (4)
  + `test_freshness.py` (6) + `test_ledger.py` (5) -- 34 per-file tests proving the math, cluster-SE
  widening, ECE collapse-guard, the walk-forward no-lookahead/purge/embargo/vintage guards, devig
  normalization, the blend beating pregame-only OUT-OF-SAMPLE, and append-only ledger + drift alerting.

Together these cover the entire NOW phase (N1/N2/N3) plus key NEXT items (X1/X3) as runnable code.

- `run_all.py` -- one-command scoreboard over all 6 test modules (exit 0 iff 34/34 green).
- `demo.py` -- END-TO-END integration: Shin-devig a synthetic close -> blend pregame+live -> score vs
  the devigged close (Brier/BSS/clustered DM) -> log to the ledger -> print an honest verdict. On a
  close built slightly sharper than the prior it reports MATCHES_CLOSE (not a fabricated win) -- the
  discipline working: it claims no edge and records "within noise of the market" as a success.

## Run it (verified passing 2026-06-16)

```
cd docs/research/ai-leverage-2026-06-16/reference-impl/eval_gate
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe test_eval_core.py     # -> 8/8 passed
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe test_shin.py          # -> 5/5 passed
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe test_ingame_blend.py  # -> 4/4 passed
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe test_freshness.py     # -> 6/6 passed
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe test_ledger.py        # -> 5/5 passed
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe test_walkforward.py   # -> 6/6 passed

# OR one command for the whole scoreboard (exit 0 iff all green):
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe run_all.py            # -> TOTAL 34/34, ALL GREEN
```

(Also pytest-discoverable: `python -m pytest test_eval_core.py -q`.)

## What it is NOT (the work that remains -- see blueprints/eval-gate.md)

- No walk-forward / purge / embargo / vintage-alignment harness yet (that's `walkforward.py`).
- No corpus loaders, no golden-set fixture, no `run_gate.py` CLI / exit-code contract, no promptfoo wrapper.
- In production, `scoring.py` should REUSE `kernel/validation/proof_metrics.py` (brier/devig2/ece)
  rather than re-implement -- this standalone version exists only so the math is runnable + tested anywhere.

## Why this matters

It turns the keystone blueprint from a plan into a verified artifact, and it embodies the package's
own principle: generation is cheap, verification is the moat. The hardest-to-get-right piece (the
cluster-robust significance test that decides "did we actually beat the close?") is now real, tested
code -- not a hopeful snippet. Everything stays calibration-first: no $ edge is computed or claimed.
